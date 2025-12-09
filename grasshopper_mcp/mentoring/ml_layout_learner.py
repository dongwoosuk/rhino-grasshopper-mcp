"""
ML-based Layout Learner
=======================

머신러닝 기반 Grasshopper 캔버스 레이아웃 학습 및 예측 모듈

Features:
- DBSCAN/K-means 기반 컴포넌트 클러스터링
- 로직 패턴 분류 (입력→처리→출력)
- 컨텍스트 기반 최적 위치 예측
- 이상 탐지 (비정상적 배치/연결)

Dependencies:
- scikit-learn (optional, graceful fallback if not available)
- numpy
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any, Set
from collections import defaultdict
import json
import math

# ML libraries (optional)
_ML_AVAILABLE = False
try:
    import numpy as np
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import NearestNeighbors
    _ML_AVAILABLE = True
except ImportError:
    # Fallback to basic implementation
    np = None


@dataclass
class ComponentCluster:
    """ML로 감지된 컴포넌트 클러스터"""
    cluster_id: int
    component_guids: List[str]
    centroid: Tuple[float, float]
    pattern_type: str  # "input", "processing", "output", "analysis", "utility"
    confidence: float
    bounding_box: Optional[Tuple[float, float, float, float]] = None  # x, y, w, h
    suggested_name: str = ""
    suggested_color: Tuple[int, int, int] = (200, 200, 200)


@dataclass
class LayoutPrediction:
    """레이아웃 위치 예측 결과"""
    x: float
    y: float
    confidence: float
    reasoning: str
    alternatives: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class AnomalyDetection:
    """레이아웃 이상 탐지 결과"""
    component_guid: str
    anomaly_type: str  # "isolated", "overlapping", "misaligned", "wrong_flow"
    severity: float  # 0.0 ~ 1.0
    suggestion: str
    expected_position: Optional[Tuple[float, float]] = None


class MLLayoutLearner:
    """
    ML 기반 레이아웃 학습 및 예측 엔진

    통계 기반 LayoutLearner를 확장하여 ML 기능 추가:
    - 클러스터링: DBSCAN, K-means
    - 패턴 인식: 컴포넌트 카테고리 + 위치 기반 분류
    - 위치 예측: K-NN 기반 컨텍스트 학습
    - 이상 탐지: 거리 기반 이상치 검출
    """

    # 패턴 분류를 위한 카테고리 매핑
    CATEGORY_TO_PATTERN = {
        # 입력 패턴
        "Params": "input",
        "Params:Input": "input",
        "Params:Primitive": "input",

        # 처리 패턴
        "Maths": "processing",
        "Sets": "processing",
        "Vector": "processing",
        "Transform": "processing",

        # 지오메트리 생성
        "Curve": "geometry",
        "Surface": "geometry",
        "Mesh": "geometry",
        "SubD": "geometry",

        # 분석
        "Intersect": "analysis",
        "Curve:Analysis": "analysis",
        "Surface:Analysis": "analysis",

        # 출력
        "Display": "output",
        "Params:Output": "output",

        # 유틸리티
        "Params:Util": "utility",
    }

    # 패턴별 색상
    PATTERN_COLORS = {
        "input": (180, 230, 180),      # 연한 초록
        "processing": (180, 180, 230),  # 연한 파랑
        "geometry": (180, 220, 230),    # 연한 청록
        "analysis": (230, 220, 180),    # 연한 노랑
        "output": (230, 180, 180),      # 연한 빨강
        "utility": (210, 210, 210),     # 연한 회색
    }

    # 패턴별 이름 템플릿
    PATTERN_NAMES = {
        "input": ["Input Parameters", "Data Sources", "Initial Values"],
        "processing": ["Data Processing", "Calculations", "Transformations"],
        "geometry": ["Geometry Creation", "Shape Generation", "Form Making"],
        "analysis": ["Analysis", "Evaluation", "Measurement"],
        "output": ["Output", "Results", "Display"],
        "utility": ["Utilities", "Helpers", "Tools"],
    }

    def __init__(self):
        self._component_data: Dict[str, dict] = {}
        self._wire_connections: List[dict] = []
        self._learned_patterns: List[dict] = []  # 학습된 패턴 저장
        self._scaler = None  # StandardScaler for position normalization

    @property
    def ml_available(self) -> bool:
        """ML 라이브러리 사용 가능 여부"""
        return _ML_AVAILABLE

    def set_component_data(self, data: Dict[str, dict]):
        """컴포넌트 데이터 설정"""
        self._component_data = data

    def set_wire_connections(self, connections: List[dict]):
        """와이어 연결 데이터 설정"""
        self._wire_connections = connections

    # =========================================================================
    # Clustering Methods
    # =========================================================================

    def detect_clusters_dbscan(
        self,
        eps: float = 150,
        min_samples: int = 2
    ) -> List[ComponentCluster]:
        """
        DBSCAN으로 컴포넌트 자동 그룹화

        Args:
            eps: 이웃 거리 임계값 (픽셀)
            min_samples: 클러스터 최소 포인트 수

        Returns:
            ComponentCluster 리스트
        """
        if not _ML_AVAILABLE:
            return self._fallback_clustering()

        # 위치 데이터 추출
        guids = []
        coords = []

        for guid, comp in self._component_data.items():
            x = comp.get('x') or comp.get('position_x')
            y = comp.get('y') or comp.get('position_y')
            if x is not None and y is not None:
                guids.append(guid)
                coords.append([float(x), float(y)])

        if len(coords) < min_samples:
            return []

        # DBSCAN 클러스터링
        X = np.array(coords)
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(X)

        # 클러스터별 그룹화 (convert numpy int64 to Python int)
        clusters_dict: Dict[int, List[int]] = defaultdict(list)
        for idx, label in enumerate(clustering.labels_):
            label_int = int(label)  # Convert numpy.int64 to Python int
            if label_int != -1:  # -1은 노이즈
                clusters_dict[label_int].append(idx)

        # ComponentCluster 객체 생성
        clusters = []
        for cluster_id, indices in clusters_dict.items():
            cluster_guids = [guids[i] for i in indices]
            cluster_coords = [coords[i] for i in indices]

            # Centroid 계산 (ensure native Python types)
            centroid = (
                float(sum(c[0] for c in cluster_coords) / len(cluster_coords)),
                float(sum(c[1] for c in cluster_coords) / len(cluster_coords))
            )

            # 패턴 타입 분류
            pattern_type = self._classify_cluster_pattern(cluster_guids)

            # Bounding box
            min_x = min(c[0] for c in cluster_coords)
            max_x = max(c[0] for c in cluster_coords)
            min_y = min(c[1] for c in cluster_coords)
            max_y = max(c[1] for c in cluster_coords)
            padding = 30
            bbox = (min_x - padding, min_y - padding,
                    max_x - min_x + 2*padding, max_y - min_y + 2*padding)

            # 이름 및 색상
            name = self._generate_cluster_name(pattern_type, cluster_id)
            color = self.PATTERN_COLORS.get(pattern_type, (200, 200, 200))

            # 신뢰도 (클러스터 밀도 기반)
            confidence = self._calculate_cluster_confidence(cluster_coords)

            cluster = ComponentCluster(
                cluster_id=int(cluster_id),  # Ensure native Python int
                component_guids=cluster_guids,
                centroid=centroid,
                pattern_type=pattern_type,
                confidence=float(confidence),  # Ensure native Python float
                bounding_box=tuple(float(v) for v in bbox),  # Ensure native Python floats
                suggested_name=name,
                suggested_color=tuple(int(v) for v in color)  # Ensure native Python ints
            )
            clusters.append(cluster)

        # X 좌표 순으로 정렬 (데이터 흐름 순서)
        clusters.sort(key=lambda c: c.centroid[0])

        return clusters

    def detect_clusters_kmeans(
        self,
        n_clusters: int = None,
        max_clusters: int = 10
    ) -> List[ComponentCluster]:
        """
        K-means로 컴포넌트 그룹화

        Args:
            n_clusters: 클러스터 수 (None이면 자동 결정)
            max_clusters: 최대 클러스터 수

        Returns:
            ComponentCluster 리스트
        """
        if not _ML_AVAILABLE:
            return self._fallback_clustering()

        # 위치 데이터 추출
        guids = []
        coords = []

        for guid, comp in self._component_data.items():
            x = comp.get('x') or comp.get('position_x')
            y = comp.get('y') or comp.get('position_y')
            if x is not None and y is not None:
                guids.append(guid)
                coords.append([float(x), float(y)])

        if len(coords) < 2:
            return []

        X = np.array(coords)

        # 클러스터 수 자동 결정 (Elbow method 간소화)
        if n_clusters is None:
            n_clusters = min(max_clusters, max(2, len(coords) // 5))

        # K-means 클러스터링
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        # 클러스터별 그룹화 (convert numpy int to Python int)
        clusters_dict: Dict[int, List[int]] = defaultdict(list)
        for idx, label in enumerate(labels):
            clusters_dict[int(label)].append(idx)

        # ComponentCluster 객체 생성
        clusters = []
        for cluster_id, indices in clusters_dict.items():
            cluster_guids = [guids[i] for i in indices]
            cluster_coords = [coords[i] for i in indices]

            centroid = tuple(float(v) for v in kmeans.cluster_centers_[cluster_id])
            pattern_type = self._classify_cluster_pattern(cluster_guids)

            min_x = min(c[0] for c in cluster_coords)
            max_x = max(c[0] for c in cluster_coords)
            min_y = min(c[1] for c in cluster_coords)
            max_y = max(c[1] for c in cluster_coords)
            padding = 30
            bbox = (min_x - padding, min_y - padding,
                    max_x - min_x + 2*padding, max_y - min_y + 2*padding)

            name = self._generate_cluster_name(pattern_type, cluster_id)
            color = self.PATTERN_COLORS.get(pattern_type, (200, 200, 200))
            confidence = self._calculate_cluster_confidence(cluster_coords)

            cluster = ComponentCluster(
                cluster_id=int(cluster_id),  # Ensure native Python int
                component_guids=cluster_guids,
                centroid=centroid,
                pattern_type=pattern_type,
                confidence=float(confidence),  # Ensure native Python float
                bounding_box=tuple(float(v) for v in bbox),  # Ensure native Python floats
                suggested_name=name,
                suggested_color=tuple(int(v) for v in color)  # Ensure native Python ints
            )
            clusters.append(cluster)

        clusters.sort(key=lambda c: c.centroid[0])
        return clusters

    def _fallback_clustering(self) -> List[ComponentCluster]:
        """ML 없이 간단한 그리드 기반 클러스터링"""
        # 연결 기반 클러스터링 (BFS)
        adjacency = self._build_adjacency()
        visited = set()
        clusters = []
        cluster_id = 0

        for start_guid in self._component_data:
            if start_guid in visited:
                continue

            # BFS
            component = []
            queue = [start_guid]
            while queue:
                guid = queue.pop(0)
                if guid in visited:
                    continue
                visited.add(guid)
                component.append(guid)
                for neighbor in adjacency.get(guid, []):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if len(component) >= 2:
                # Centroid 계산
                coords = []
                for guid in component:
                    comp = self._component_data.get(guid, {})
                    x = comp.get('x') or comp.get('position_x')
                    y = comp.get('y') or comp.get('position_y')
                    if x is not None and y is not None:
                        coords.append((float(x), float(y)))

                if coords:
                    centroid = (
                        sum(c[0] for c in coords) / len(coords),
                        sum(c[1] for c in coords) / len(coords)
                    )
                    pattern_type = self._classify_cluster_pattern(component)

                    cluster = ComponentCluster(
                        cluster_id=cluster_id,
                        component_guids=component,
                        centroid=centroid,
                        pattern_type=pattern_type,
                        confidence=0.7,
                        suggested_name=self._generate_cluster_name(pattern_type, cluster_id),
                        suggested_color=self.PATTERN_COLORS.get(pattern_type, (200, 200, 200))
                    )
                    clusters.append(cluster)
                    cluster_id += 1

        return clusters

    # =========================================================================
    # Pattern Classification
    # =========================================================================

    def _classify_cluster_pattern(self, guids: List[str]) -> str:
        """클러스터의 주요 패턴 분류"""
        pattern_counts: Dict[str, int] = defaultdict(int)

        for guid in guids:
            comp = self._component_data.get(guid, {})
            category = comp.get('category', '')

            # 카테고리를 패턴으로 변환
            pattern = self.CATEGORY_TO_PATTERN.get(category)
            if not pattern:
                # 부분 매칭
                for cat_key, pat in self.CATEGORY_TO_PATTERN.items():
                    if category.startswith(cat_key.split(':')[0]):
                        pattern = pat
                        break
            if not pattern:
                pattern = "utility"

            pattern_counts[pattern] += 1

        if not pattern_counts:
            return "utility"

        return max(pattern_counts, key=pattern_counts.get)

    def classify_data_flow(self) -> Dict[str, List[str]]:
        """
        전체 데이터 흐름 분류 (입력 → 처리 → 출력)

        Returns:
            {"input": [...], "processing": [...], "output": [...]}
        """
        adjacency = self._build_adjacency()
        reverse_adj = self._build_reverse_adjacency()

        flow = {
            "input": [],
            "processing": [],
            "output": []
        }

        for guid in self._component_data:
            # 입력이 없으면 input
            if not reverse_adj.get(guid):
                flow["input"].append(guid)
            # 출력이 없으면 output
            elif not adjacency.get(guid):
                flow["output"].append(guid)
            else:
                flow["processing"].append(guid)

        return flow

    # =========================================================================
    # Position Prediction
    # =========================================================================

    def predict_next_position(
        self,
        component_name: str,
        connected_to: str = None,
        direction: str = "right"
    ) -> LayoutPrediction:
        """
        다음 컴포넌트 최적 위치 예측

        Args:
            component_name: 추가할 컴포넌트 이름
            connected_to: 연결될 컴포넌트 GUID
            direction: 배치 방향 ("right", "down", "left", "up")

        Returns:
            LayoutPrediction 객체
        """
        # 기본 오프셋
        offsets = {
            "right": (200, 0),
            "down": (0, 100),
            "left": (-200, 0),
            "up": (0, -100)
        }
        base_offset = offsets.get(direction, (200, 0))

        if connected_to and connected_to in self._component_data:
            comp = self._component_data[connected_to]
            base_x = float(comp.get('x') or comp.get('position_x') or 0)
            base_y = float(comp.get('y') or comp.get('position_y') or 0)

            predicted_x = base_x + base_offset[0]
            predicted_y = base_y + base_offset[1]

            # ML이 있으면 K-NN으로 미세 조정
            if _ML_AVAILABLE and len(self._learned_patterns) > 5:
                adjustment = self._knn_position_adjustment(
                    component_name, predicted_x, predicted_y
                )
                predicted_x += adjustment[0]
                predicted_y += adjustment[1]

            return LayoutPrediction(
                x=predicted_x,
                y=predicted_y,
                confidence=0.8,
                reasoning=f"Based on connection to {connected_to}, direction: {direction}"
            )
        else:
            # 캔버스 중앙 근처에 배치
            if self._component_data:
                all_x = []
                all_y = []
                for comp in self._component_data.values():
                    x = comp.get('x') or comp.get('position_x')
                    y = comp.get('y') or comp.get('position_y')
                    if x is not None and y is not None:
                        all_x.append(float(x))
                        all_y.append(float(y))

                if all_x and all_y:
                    center_x = sum(all_x) / len(all_x)
                    center_y = sum(all_y) / len(all_y)
                    return LayoutPrediction(
                        x=center_x + 300,
                        y=center_y,
                        confidence=0.5,
                        reasoning="Placed near canvas center"
                    )

            return LayoutPrediction(
                x=500,
                y=300,
                confidence=0.3,
                reasoning="Default position (no context)"
            )

    def _knn_position_adjustment(
        self,
        component_name: str,
        base_x: float,
        base_y: float
    ) -> Tuple[float, float]:
        """K-NN 기반 위치 미세 조정"""
        if not _ML_AVAILABLE or len(self._learned_patterns) < 3:
            return (0, 0)

        # 유사한 컴포넌트의 과거 위치 패턴 찾기
        similar_patterns = [
            p for p in self._learned_patterns
            if p.get('name', '').lower() == component_name.lower()
        ]

        if len(similar_patterns) < 2:
            return (0, 0)

        # K-NN으로 가장 가까운 패턴 찾기
        positions = np.array([[p['offset_x'], p['offset_y']] for p in similar_patterns])
        knn = NearestNeighbors(n_neighbors=min(3, len(positions)))
        knn.fit(positions)

        # 평균 오프셋 반환
        avg_offset_x = sum(p['offset_x'] for p in similar_patterns) / len(similar_patterns)
        avg_offset_y = sum(p['offset_y'] for p in similar_patterns) / len(similar_patterns)

        return (avg_offset_x * 0.3, avg_offset_y * 0.3)  # 30% 적용

    # =========================================================================
    # Anomaly Detection
    # =========================================================================

    def detect_layout_anomalies(
        self,
        isolation_threshold: float = 300,
        overlap_threshold: float = 50
    ) -> List[AnomalyDetection]:
        """
        레이아웃 이상 탐지

        Args:
            isolation_threshold: 고립 판단 거리 (픽셀)
            overlap_threshold: 겹침 판단 거리 (픽셀)

        Returns:
            AnomalyDetection 리스트
        """
        anomalies = []

        # 위치 데이터 수집
        positions = {}
        for guid, comp in self._component_data.items():
            x = comp.get('x') or comp.get('position_x')
            y = comp.get('y') or comp.get('position_y')
            if x is not None and y is not None:
                positions[guid] = (float(x), float(y))

        adjacency = self._build_adjacency()

        for guid, (x, y) in positions.items():
            # 1. 고립 검사: 연결이 있는데 거리가 너무 먼 경우
            connected = adjacency.get(guid, set())
            if connected:
                for neighbor_guid in connected:
                    if neighbor_guid in positions:
                        nx, ny = positions[neighbor_guid]
                        dist = math.sqrt((x - nx)**2 + (y - ny)**2)
                        if dist > isolation_threshold:
                            anomalies.append(AnomalyDetection(
                                component_guid=guid,
                                anomaly_type="isolated",
                                severity=min(1.0, dist / (isolation_threshold * 2)),
                                suggestion=f"이 컴포넌트가 연결된 {neighbor_guid[:8]}...와 너무 멀리 떨어져 있습니다",
                                expected_position=(nx + 200, ny)
                            ))
                            break

            # 2. 겹침 검사
            for other_guid, (ox, oy) in positions.items():
                if other_guid == guid:
                    continue
                dist = math.sqrt((x - ox)**2 + (y - oy)**2)
                if dist < overlap_threshold:
                    anomalies.append(AnomalyDetection(
                        component_guid=guid,
                        anomaly_type="overlapping",
                        severity=1.0 - (dist / overlap_threshold),
                        suggestion=f"{other_guid[:8]}...와 겹치고 있습니다. 간격을 넓히세요"
                    ))
                    break

            # 3. 흐름 방향 검사 (입력이 출력 오른쪽에 있는 경우)
            # (간단한 휴리스틱)
            comp = self._component_data.get(guid, {})
            category = comp.get('category', '')
            if 'Params' in category or 'Input' in category:
                # 입력 컴포넌트가 다른 컴포넌트보다 오른쪽에 있으면 경고
                avg_x = sum(p[0] for p in positions.values()) / len(positions)
                if x > avg_x + 200:
                    anomalies.append(AnomalyDetection(
                        component_guid=guid,
                        anomaly_type="wrong_flow",
                        severity=0.6,
                        suggestion="입력 컴포넌트가 캔버스 오른쪽에 있습니다. 왼쪽으로 이동하세요"
                    ))

        return anomalies

    # =========================================================================
    # Learning Methods
    # =========================================================================

    def learn_from_canvas(self) -> dict:
        """
        현재 캔버스에서 레이아웃 패턴 학습

        Returns:
            학습 결과 요약
        """
        learned = {
            "spacing_patterns": [],
            "flow_direction": None,
            "cluster_patterns": []
        }

        if len(self._component_data) < 2:
            return learned

        # 간격 패턴 학습
        adjacency = self._build_adjacency()
        spacings = []

        for guid, neighbors in adjacency.items():
            if guid not in self._component_data:
                continue
            comp = self._component_data[guid]
            x1 = comp.get('x') or comp.get('position_x')
            y1 = comp.get('y') or comp.get('position_y')

            if x1 is None or y1 is None:
                continue

            for neighbor_guid in neighbors:
                if neighbor_guid not in self._component_data:
                    continue
                neighbor = self._component_data[neighbor_guid]
                x2 = neighbor.get('x') or neighbor.get('position_x')
                y2 = neighbor.get('y') or neighbor.get('position_y')

                if x2 is None or y2 is None:
                    continue

                dx = float(x2) - float(x1)
                dy = float(y2) - float(y1)
                spacings.append((dx, dy))

                # 패턴 저장
                self._learned_patterns.append({
                    'name': comp.get('name', ''),
                    'offset_x': dx,
                    'offset_y': dy
                })

        if spacings:
            avg_dx = sum(s[0] for s in spacings) / len(spacings)
            avg_dy = sum(s[1] for s in spacings) / len(spacings)
            learned["spacing_patterns"] = {
                "avg_x": round(avg_dx, 1),
                "avg_y": round(avg_dy, 1),
                "samples": len(spacings)
            }

            # 흐름 방향 판단
            if avg_dx > 50:
                learned["flow_direction"] = "left_to_right"
            elif avg_dx < -50:
                learned["flow_direction"] = "right_to_left"
            elif avg_dy > 50:
                learned["flow_direction"] = "top_to_bottom"
            else:
                learned["flow_direction"] = "mixed"

        return learned

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_adjacency(self) -> Dict[str, Set[str]]:
        """와이어 연결 기반 인접 그래프 (정방향)"""
        adj: Dict[str, Set[str]] = defaultdict(set)
        for wire in self._wire_connections:
            src = str(wire.get('source_guid') or wire.get('Source') or '')
            tgt = str(wire.get('target_guid') or wire.get('Target') or '')
            if src and tgt:
                adj[src].add(tgt)
        return dict(adj)

    def _build_reverse_adjacency(self) -> Dict[str, Set[str]]:
        """와이어 연결 기반 역방향 인접 그래프"""
        adj: Dict[str, Set[str]] = defaultdict(set)
        for wire in self._wire_connections:
            src = str(wire.get('source_guid') or wire.get('Source') or '')
            tgt = str(wire.get('target_guid') or wire.get('Target') or '')
            if src and tgt:
                adj[tgt].add(src)
        return dict(adj)

    def _calculate_cluster_confidence(self, coords: List[Tuple[float, float]]) -> float:
        """클러스터 신뢰도 계산 (밀도 기반)"""
        if len(coords) < 2:
            return 0.5

        # 평균 거리 계산
        distances = []
        for i, (x1, y1) in enumerate(coords):
            for j, (x2, y2) in enumerate(coords):
                if i < j:
                    dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    distances.append(dist)

        if not distances:
            return 0.5

        avg_dist = sum(distances) / len(distances)

        # 거리가 작을수록 신뢰도 높음 (최대 300px 기준)
        confidence = max(0.3, min(1.0, 1.0 - (avg_dist / 500)))
        return round(confidence, 2)

    def _generate_cluster_name(self, pattern_type: str, cluster_id: int) -> str:
        """클러스터 이름 생성"""
        names = self.PATTERN_NAMES.get(pattern_type, ["Cluster"])
        return f"{names[0]} {cluster_id + 1}"

    # =========================================================================
    # Summary Methods
    # =========================================================================

    def get_layout_analysis(self) -> dict:
        """
        전체 레이아웃 분석 요약

        Returns:
            {
                "ml_available": bool,
                "component_count": int,
                "clusters": [...],
                "data_flow": {...},
                "anomalies": [...],
                "learned_patterns": {...}
            }
        """
        clusters = self.detect_clusters_dbscan() if _ML_AVAILABLE else self._fallback_clustering()
        data_flow = self.classify_data_flow()
        anomalies = self.detect_layout_anomalies()
        learned = self.learn_from_canvas()

        return {
            "ml_available": _ML_AVAILABLE,
            "component_count": len(self._component_data),
            "clusters": [
                {
                    "id": c.cluster_id,
                    "name": c.suggested_name,
                    "pattern": c.pattern_type,
                    "count": len(c.component_guids),
                    "centroid": c.centroid,
                    "confidence": c.confidence,
                    "color": c.suggested_color
                }
                for c in clusters
            ],
            "data_flow": {
                "input_count": len(data_flow.get("input", [])),
                "processing_count": len(data_flow.get("processing", [])),
                "output_count": len(data_flow.get("output", []))
            },
            "anomalies": [
                {
                    "guid": a.component_guid[:8] + "...",
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "suggestion": a.suggestion
                }
                for a in anomalies
            ],
            "learned_patterns": learned
        }


# ============================================================
# Utility Functions
# ============================================================

def create_ml_learner_from_canvas_data(
    components: List[dict],
    wires: List[dict] = None
) -> MLLayoutLearner:
    """
    캔버스 데이터로부터 MLLayoutLearner 생성

    Args:
        components: 컴포넌트 정보 리스트
        wires: 와이어 연결 정보 리스트

    Returns:
        설정된 MLLayoutLearner 인스턴스
    """
    learner = MLLayoutLearner()

    # 컴포넌트 데이터 변환
    comp_data = {}
    for comp in components:
        guid = comp.get('guid') or comp.get('InstanceGuid')
        if guid:
            guid_str = str(guid)
            comp_data[guid_str] = {
                'name': comp.get('name', ''),
                'category': comp.get('category', ''),
                'nickname': comp.get('nickname', ''),
                'x': comp.get('x') or comp.get('position_x'),
                'y': comp.get('y') or comp.get('position_y'),
            }

    learner.set_component_data(comp_data)

    if wires:
        learner.set_wire_connections(wires)

    return learner


# ============================================================
# Pattern Export Functions (for standalone integration)
# ============================================================

def export_ml_patterns_to_json(
    learner: MLLayoutLearner,
    output_path: str
) -> dict:
    """
    ML 학습 결과를 JSON 파일로 내보내기

    standalone 스크립트에서 사용할 수 있도록 ML 분석 결과를
    JSON 형식으로 저장합니다.

    Args:
        learner: MLLayoutLearner 인스턴스
        output_path: 저장할 JSON 파일 경로

    Returns:
        내보낸 패턴 데이터
    """
    from datetime import datetime
    from pathlib import Path

    # 전체 분석 수행
    analysis = learner.get_layout_analysis()
    learned = analysis.get("learned_patterns", {})

    # 컴포넌트별 패턴 추출
    component_patterns = {}
    for pattern in learner._learned_patterns:
        name = pattern.get('name', '')
        if name:
            if name not in component_patterns:
                component_patterns[name] = {
                    'samples': [],
                    'offset_x': 0,
                    'offset_y': 0
                }
            component_patterns[name]['samples'].append({
                'offset_x': pattern.get('offset_x', 0),
                'offset_y': pattern.get('offset_y', 0)
            })

    # 평균 계산
    for name, data in component_patterns.items():
        samples = data['samples']
        if samples:
            data['offset_x'] = round(sum(s['offset_x'] for s in samples) / len(samples), 1)
            data['offset_y'] = round(sum(s['offset_y'] for s in samples) / len(samples), 1)
            data['sample_count'] = len(samples)
            del data['samples']  # 샘플 데이터 제거 (용량 절약)

    # 클러스터 패턴 정보
    cluster_patterns = []
    for cluster in analysis.get("clusters", []):
        cluster_patterns.append({
            "id": cluster.get("id"),
            "name": cluster.get("name"),
            "pattern_type": cluster.get("pattern"),
            "component_count": cluster.get("count"),
            "centroid": cluster.get("centroid"),
            "confidence": cluster.get("confidence"),
            "color": cluster.get("color")
        })

    # 간격 정보 추출
    spacing_info = learned.get("spacing_patterns", {})
    if isinstance(spacing_info, dict):
        spacing = {
            "x": spacing_info.get("avg_x", 200),
            "y": spacing_info.get("avg_y", 80),
            "samples": spacing_info.get("samples", 0)
        }
    else:
        spacing = {"x": 200, "y": 80, "samples": 0}

    # 최종 패턴 데이터
    export_data = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "ml_available": learner.ml_available,
        "component_count": analysis.get("component_count", 0),

        # 핵심 데이터
        "spacing": spacing,
        "flow_direction": learned.get("flow_direction", "left_to_right"),

        # 컴포넌트별 패턴 (ML 기반)
        "component_patterns": component_patterns,

        # 클러스터 패턴 (DBSCAN/K-means 결과)
        "cluster_patterns": cluster_patterns,

        # 데이터 흐름 분석
        "data_flow": analysis.get("data_flow", {}),

        # 이상 탐지 결과
        "anomalies": analysis.get("anomalies", [])
    }

    # JSON 파일 저장
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    return export_data


def analyze_gh_files_and_export(
    gh_file_paths: List[str],
    output_path: str
) -> dict:
    """
    여러 .gh 파일을 분석하여 통합 패턴 JSON 생성

    Args:
        gh_file_paths: 분석할 .gh 파일 경로들
        output_path: 저장할 JSON 파일 경로

    Returns:
        통합 패턴 데이터
    """
    import gzip
    import xml.etree.ElementTree as ET
    from datetime import datetime
    from pathlib import Path

    all_component_patterns = {}
    all_spacings_x = []
    all_spacings_y = []
    flow_directions = {"left_to_right": 0, "right_to_left": 0, "top_to_bottom": 0}
    total_components = 0
    files_analyzed = 0

    for file_path in gh_file_paths:
        try:
            path = Path(file_path)
            if not path.exists():
                continue

            # GH 파일 읽기
            if path.suffix.lower() == '.gh':
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    content = f.read()
            else:  # .ghx
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

            root = ET.fromstring(content)

            # 컴포넌트 추출
            components = {}
            for obj in root.iter():
                if obj.tag == "Object":
                    guid = obj.get("Id", "")
                    name = obj.get("Name", "")

                    pivot = obj.find(".//Pivot")
                    if pivot is not None:
                        x_elem = pivot.get("X") or pivot.find("X")
                        y_elem = pivot.get("Y") or pivot.find("Y")

                        if x_elem is not None and y_elem is not None:
                            try:
                                x = float(x_elem.text if hasattr(x_elem, 'text') and x_elem.text else x_elem)
                                y = float(y_elem.text if hasattr(y_elem, 'text') and y_elem.text else y_elem)
                                components[guid] = {"name": name, "x": x, "y": y}
                                total_components += 1
                            except (ValueError, TypeError):
                                pass

            # 와이어 추출 및 간격 계산
            for wire in root.iter("Wire"):
                source = wire.find("Source")
                target = wire.find("Target")

                if source is not None and target is not None:
                    src_guid = source.get("Id", "")
                    tgt_guid = target.get("Id", "")

                    if src_guid in components and tgt_guid in components:
                        src = components[src_guid]
                        tgt = components[tgt_guid]

                        dx = tgt["x"] - src["x"]
                        dy = tgt["y"] - src["y"]

                        all_spacings_x.append(abs(dx))
                        all_spacings_y.append(abs(dy))

                        # 컴포넌트별 패턴 저장
                        src_name = src["name"]
                        if src_name:
                            if src_name not in all_component_patterns:
                                all_component_patterns[src_name] = {
                                    'offset_x_samples': [],
                                    'offset_y_samples': []
                                }
                            all_component_patterns[src_name]['offset_x_samples'].append(dx)
                            all_component_patterns[src_name]['offset_y_samples'].append(dy)

                        # 흐름 방향
                        if abs(dx) > abs(dy):
                            if dx > 0:
                                flow_directions["left_to_right"] += 1
                            else:
                                flow_directions["right_to_left"] += 1
                        else:
                            flow_directions["top_to_bottom"] += 1

            files_analyzed += 1

        except Exception as e:
            continue

    # 컴포넌트별 평균 계산
    component_patterns_final = {}
    for name, data in all_component_patterns.items():
        x_samples = data['offset_x_samples']
        y_samples = data['offset_y_samples']
        if x_samples and y_samples:
            component_patterns_final[name] = {
                'offset_x': round(sum(x_samples) / len(x_samples), 1),
                'offset_y': round(sum(y_samples) / len(y_samples), 1),
                'sample_count': len(x_samples)
            }

    # 전체 간격 평균
    spacing = {
        "x": round(sum(all_spacings_x) / len(all_spacings_x), 1) if all_spacings_x else 200,
        "y": round(sum(all_spacings_y) / len(all_spacings_y), 1) if all_spacings_y else 80,
        "samples": len(all_spacings_x)
    }

    # 주요 흐름 방향
    main_flow = max(flow_directions, key=flow_directions.get) if flow_directions else "left_to_right"

    # 최종 데이터
    export_data = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "ml_available": _ML_AVAILABLE,
        "files_analyzed": files_analyzed,
        "component_count": total_components,

        "spacing": spacing,
        "flow_direction": main_flow,
        "component_patterns": component_patterns_final,

        # 클러스터 패턴은 개별 파일 분석에서만 가능
        "cluster_patterns": [],
        "data_flow": {},
        "anomalies": []
    }

    # JSON 저장
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    return export_data
