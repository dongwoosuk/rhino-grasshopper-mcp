"""
Auto Grouper
============

와이어 연결 기반으로 논리적 그룹을 자동 감지하고 생성하는 모듈

Features:
- 연결된 컴포넌트 클러스터 감지
- 기능별 그룹 분류
- 의미 있는 이름 생성
- 색상 스킴 제안
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any, Set
from collections import defaultdict

from . import FunctionalCluster, GroupingRecommendation


class AutoGrouper:
    """와이어 연결 기반 자동 그룹화 엔진"""

    # 기능 타입별 색상 스킴
    COLOR_SCHEMES = {
        "default": {
            "input": (200, 230, 200),       # 연한 초록 - 입력
            "transform": (200, 200, 230),   # 연한 파랑 - 변환
            "calculation": (230, 230, 200), # 연한 노랑 - 계산
            "output": (230, 200, 200),      # 연한 빨강 - 출력
            "utility": (220, 220, 220),     # 연한 회색 - 유틸리티
            "geometry": (200, 220, 230),    # 연한 청록 - 지오메트리
            "data": (230, 210, 200),        # 연한 주황 - 데이터 처리
        },
        "vibrant": {
            "input": (150, 255, 150),
            "transform": (150, 150, 255),
            "calculation": (255, 255, 150),
            "output": (255, 150, 150),
            "utility": (200, 200, 200),
            "geometry": (150, 220, 255),
            "data": (255, 200, 150),
        },
        "monochrome": {
            "input": (180, 180, 180),
            "transform": (160, 160, 160),
            "calculation": (140, 140, 140),
            "output": (120, 120, 120),
            "utility": (200, 200, 200),
            "geometry": (170, 170, 170),
            "data": (150, 150, 150),
        }
    }

    # 카테고리 → 기능 타입 매핑
    CATEGORY_TO_FUNCTION = {
        # 입력
        "Params": "input",

        # 지오메트리 생성/조작
        "Curve": "geometry",
        "Surface": "geometry",
        "Mesh": "geometry",
        "SubD": "geometry",

        # 변환
        "Transform": "transform",
        "Vector": "transform",

        # 계산
        "Maths": "calculation",
        "Script": "calculation",

        # 데이터 처리
        "Sets": "data",
        "Tree": "data",

        # 출력/디스플레이
        "Display": "output",

        # 분석/교차
        "Intersect": "calculation",

        # 기타
        "Params:Util": "utility",
    }

    # 기능 타입별 한글 이름 템플릿
    FUNCTION_NAMES_KO = {
        "input": ["입력 파라미터", "시작 데이터", "초기값"],
        "transform": ["변환 처리", "지오메트리 변환", "이동/회전"],
        "calculation": ["계산 로직", "수학 연산", "스크립트 처리"],
        "output": ["출력 결과", "최종 지오메트리", "디스플레이"],
        "utility": ["유틸리티", "보조 기능", "데이터 정리"],
        "geometry": ["지오메트리 생성", "형태 생성", "곡선/서피스"],
        "data": ["데이터 처리", "리스트 관리", "트리 조작"],
    }

    # 기능 타입별 영어 이름 템플릿
    FUNCTION_NAMES_EN = {
        "input": ["Input Parameters", "Initial Data", "Source"],
        "transform": ["Transform", "Geometry Transform", "Move/Rotate"],
        "calculation": ["Calculation", "Math Operations", "Script"],
        "output": ["Output", "Final Geometry", "Display"],
        "utility": ["Utility", "Helper", "Data Cleanup"],
        "geometry": ["Geometry Creation", "Shape Generation", "Curves/Surfaces"],
        "data": ["Data Processing", "List Management", "Tree Operations"],
    }

    def __init__(self, analyzer: Any = None):
        """
        Args:
            analyzer: GHLiveAnalyzer 인스턴스 (선택적)
        """
        self.analyzer = analyzer
        self._component_data: Dict[str, dict] = {}
        self._wire_connections: List[dict] = []
        self._language = "en"  # "en" or "ko"

    def set_component_data(self, data: Dict[str, dict]):
        """외부에서 컴포넌트 데이터 설정"""
        self._component_data = data

    def set_wire_connections(self, connections: List[dict]):
        """외부에서 와이어 연결 데이터 설정"""
        self._wire_connections = connections

    def set_language(self, lang: str):
        """이름 생성 언어 설정 ('en' or 'ko')"""
        self._language = lang

    def detect_functional_clusters(
        self,
        min_size: int = 2,
        max_clusters: int = 10
    ) -> List[FunctionalCluster]:
        """
        기능별 클러스터 감지

        Args:
            min_size: 최소 클러스터 크기
            max_clusters: 최대 클러스터 수

        Returns:
            FunctionalCluster 리스트
        """
        # 연결 그래프 구축
        adjacency = self._build_connectivity_graph()

        # 연결된 컴포넌트 찾기 (BFS/DFS)
        connected_components = self._find_connected_subgraphs(adjacency)

        # 최소 크기 필터링
        valid_components = [
            cc for cc in connected_components
            if len(cc) >= min_size
        ]

        # 크기순 정렬 (큰 것 먼저)
        valid_components.sort(key=len, reverse=True)

        # 최대 개수 제한
        valid_components = valid_components[:max_clusters]

        # 클러스터 생성
        clusters = []
        for i, component_guids in enumerate(valid_components):
            guids_list = list(component_guids)

            # 기능 타입 분류
            function_type = self._classify_cluster_function(guids_list)

            # 이름 생성
            name = self._generate_cluster_name(guids_list, function_type, i)

            # 색상 할당
            color = self.COLOR_SCHEMES["default"].get(
                function_type,
                (200, 200, 200)
            )

            # 바운딩 박스 계산
            boundary = self._calculate_boundary(guids_list)

            # 신뢰도 계산 (클러스터 크기와 연결 밀도 기반)
            confidence = self._calculate_cluster_confidence(guids_list, adjacency)

            cluster = FunctionalCluster(
                component_guids=guids_list,
                suggested_name=name,
                suggested_color=color,
                function_type=function_type,
                confidence=confidence,
                boundary_rect=boundary
            )
            clusters.append(cluster)

        return clusters

    def get_grouping_recommendation(
        self,
        min_size: int = 2,
        max_clusters: int = 10,
        color_scheme: str = "default"
    ) -> GroupingRecommendation:
        """
        전체 그룹화 권장사항 생성

        Args:
            min_size: 최소 클러스터 크기
            max_clusters: 최대 클러스터 수
            color_scheme: 색상 스킴 ("default", "vibrant", "monochrome")

        Returns:
            GroupingRecommendation 객체
        """
        clusters = self.detect_functional_clusters(min_size, max_clusters)

        # 색상 스킴 적용
        scheme = self.COLOR_SCHEMES.get(color_scheme, self.COLOR_SCHEMES["default"])
        for cluster in clusters:
            cluster.suggested_color = scheme.get(
                cluster.function_type,
                (200, 200, 200)
            )

        # 그룹화되지 않은 컴포넌트 수
        grouped_guids = set()
        for cluster in clusters:
            grouped_guids.update(cluster.component_guids)
        ungrouped_count = len(self._component_data) - len(grouped_guids)

        # 레이아웃 제안
        layout_suggestions = self._generate_layout_suggestions(clusters)

        # 색상 스킴 정보
        color_scheme_info = {
            func_type: scheme.get(func_type, (200, 200, 200))
            for func_type in set(c.function_type for c in clusters)
        }

        return GroupingRecommendation(
            clusters=clusters,
            layout_suggestions=layout_suggestions,
            color_scheme=color_scheme_info,
            ungrouped_count=ungrouped_count
        )

    def _build_connectivity_graph(self) -> Dict[str, Set[str]]:
        """와이어 연결 기반 양방향 인접 그래프 생성"""
        adj: Dict[str, Set[str]] = defaultdict(set)

        for wire in self._wire_connections:
            src = wire.get('source_guid') or wire.get('Source')
            tgt = wire.get('target_guid') or wire.get('Target')

            if src and tgt:
                src = str(src)
                tgt = str(tgt)
                # 양방향 연결 (무방향 그래프)
                adj[src].add(tgt)
                adj[tgt].add(src)

        # 연결 없는 컴포넌트도 추가
        for guid in self._component_data:
            if guid not in adj:
                adj[guid] = set()

        return dict(adj)

    def _find_connected_subgraphs(
        self,
        adjacency: Dict[str, Set[str]]
    ) -> List[Set[str]]:
        """BFS로 연결된 컴포넌트 찾기"""
        visited = set()
        components = []

        for start_node in adjacency:
            if start_node in visited:
                continue

            # BFS로 연결된 모든 노드 찾기
            component = set()
            queue = [start_node]

            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue

                visited.add(node)
                component.add(node)

                for neighbor in adjacency.get(node, []):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if component:
                components.append(component)

        return components

    def _classify_cluster_function(self, guids: List[str]) -> str:
        """클러스터의 주요 기능 타입 분류"""
        function_counts: Dict[str, int] = defaultdict(int)

        for guid in guids:
            comp = self._component_data.get(guid, {})
            category = comp.get('category', '')

            # 카테고리를 기능 타입으로 변환
            func_type = self.CATEGORY_TO_FUNCTION.get(
                category,
                "utility"
            )
            function_counts[func_type] += 1

        if not function_counts:
            return "utility"

        # 가장 많은 기능 타입 반환
        return max(function_counts, key=function_counts.get)

    def _generate_cluster_name(
        self,
        guids: List[str],
        function_type: str,
        index: int
    ) -> str:
        """클러스터 이름 생성"""
        if self._language == "ko":
            names = self.FUNCTION_NAMES_KO.get(function_type, ["그룹"])
        else:
            names = self.FUNCTION_NAMES_EN.get(function_type, ["Group"])

        # 클러스터 내 컴포넌트 이름 분석
        comp_names = []
        for guid in guids[:5]:  # 처음 5개만 확인
            comp = self._component_data.get(guid, {})
            name = comp.get('name', '')
            if name:
                comp_names.append(name)

        # 공통 키워드가 있으면 이름에 포함
        if comp_names:
            # 가장 흔한 단어 찾기
            words = []
            for name in comp_names:
                words.extend(name.split())

            if words:
                from collections import Counter
                common = Counter(words).most_common(1)
                if common and common[0][1] > 1:
                    return f"{names[0]} - {common[0][0]}"

        # 기본 이름 + 번호
        return f"{names[0]} {index + 1}"

    def _calculate_boundary(
        self,
        guids: List[str]
    ) -> Optional[Tuple[float, float, float, float]]:
        """클러스터의 바운딩 박스 계산"""
        positions = []

        for guid in guids:
            comp = self._component_data.get(guid, {})
            x = comp.get('x') or comp.get('position_x')
            y = comp.get('y') or comp.get('position_y')

            if x is not None and y is not None:
                positions.append((float(x), float(y)))

        if not positions:
            return None

        min_x = min(p[0] for p in positions)
        max_x = max(p[0] for p in positions)
        min_y = min(p[1] for p in positions)
        max_y = max(p[1] for p in positions)

        # 약간의 패딩 추가
        padding = 50
        return (
            min_x - padding,
            min_y - padding,
            max_x - min_x + padding * 2,
            max_y - min_y + padding * 2
        )

    def _calculate_cluster_confidence(
        self,
        guids: List[str],
        adjacency: Dict[str, Set[str]]
    ) -> float:
        """클러스터 신뢰도 계산 (0.0 ~ 1.0)"""
        if len(guids) < 2:
            return 0.5

        # 내부 연결 밀도 계산
        internal_edges = 0
        guid_set = set(guids)

        for guid in guids:
            for neighbor in adjacency.get(guid, []):
                if neighbor in guid_set:
                    internal_edges += 1

        # 양방향이므로 2로 나눔
        internal_edges //= 2

        # 최대 가능 엣지 수 (완전 그래프)
        n = len(guids)
        max_edges = n * (n - 1) // 2

        if max_edges == 0:
            return 0.5

        density = internal_edges / max_edges

        # 밀도 + 크기 기반 신뢰도
        size_factor = min(1.0, len(guids) / 10)
        confidence = 0.5 * density + 0.5 * size_factor

        return round(min(1.0, confidence), 2)

    def _generate_layout_suggestions(
        self,
        clusters: List[FunctionalCluster]
    ) -> List[str]:
        """레이아웃 개선 제안 생성"""
        suggestions = []

        # 입력 그룹을 왼쪽에 배치
        input_clusters = [c for c in clusters if c.function_type == "input"]
        if input_clusters:
            suggestions.append("입력 파라미터 그룹을 캔버스 왼쪽에 배치하세요")

        # 출력 그룹을 오른쪽에 배치
        output_clusters = [c for c in clusters if c.function_type == "output"]
        if output_clusters:
            suggestions.append("출력/디스플레이 그룹을 캔버스 오른쪽에 배치하세요")

        # 중간 처리 그룹
        middle_clusters = [
            c for c in clusters
            if c.function_type not in ["input", "output"]
        ]
        if middle_clusters:
            suggestions.append("변환/계산 그룹을 데이터 흐름 순서대로 중앙에 배치하세요")

        # 그룹 간 간격
        if len(clusters) > 1:
            suggestions.append("그룹 간 최소 100px 간격을 유지하세요")

        return suggestions


# ============================================================
# Utility Functions
# ============================================================

def create_grouper_from_canvas_data(
    components: List[dict],
    wires: List[dict] = None
) -> AutoGrouper:
    """
    캔버스 데이터로부터 AutoGrouper 생성

    Args:
        components: 컴포넌트 정보 리스트
        wires: 와이어 연결 정보 리스트

    Returns:
        설정된 AutoGrouper 인스턴스
    """
    grouper = AutoGrouper()

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

    grouper.set_component_data(comp_data)

    if wires:
        grouper.set_wire_connections(wires)

    return grouper
