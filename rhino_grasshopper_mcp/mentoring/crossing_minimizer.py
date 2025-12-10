"""
Crossing Minimizer
==================

와이어 교차 최소화 최적화 알고리즘

Features:
- Barycenter 휴리스틱: 연결된 노드들의 Y 평균으로 정렬
- Adjacent Swap: 인접 노드 교환으로 교차 감소
- ML 초기값 + 규칙 기반 최적화 하이브리드
"""

from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict
import copy

try:
    from .wire_crossing_detector import Wire, WireCrossingDetector, get_crossing_detector
except ImportError:
    from wire_crossing_detector import Wire, WireCrossingDetector, get_crossing_detector


class CrossingMinimizer:
    """와이어 교차 최소화 최적화"""

    def __init__(self, detector: WireCrossingDetector = None):
        self.detector = detector or get_crossing_detector()

    def barycenter_order(
        self,
        level_nodes: List[str],
        node_positions: Dict[str, Tuple[float, float]],
        incoming_connections: Dict[str, List[str]],
        outgoing_connections: Dict[str, List[str]],
        prioritize_incoming: bool = True,
        wire_order_to_target: Dict[str, List[str]] = None
    ) -> List[str]:
        """
        Barycenter 휴리스틱 (순방향 레이아웃 최적화)

        각 노드를 연결된 소스 노드들의 Y 평균으로 정렬
        순방향 레이아웃에서는 incoming 연결을 우선시하여 와이어 꼬임 방지

        Args:
            level_nodes: 현재 레벨의 노드 GUID 목록
            node_positions: 모든 노드의 현재 위치 {guid: (x, y)}
            incoming_connections: 각 노드로 들어오는 연결 {target: [sources]}
            outgoing_connections: 각 노드에서 나가는 연결 {source: [targets]}
            prioritize_incoming: True면 incoming 연결을 우선 사용 (순방향 레이아웃)
            wire_order_to_target: 타겟별 소스 와이어 순서 {target: [sources in port order]}

        Returns:
            Y 순서로 정렬된 노드 GUID 목록
        """
        barycenters = {}

        for node in level_nodes:
            incoming_ys = []
            outgoing_ys = []

            # 들어오는 연결의 Y 좌표 (소스 노드들)
            for source in incoming_connections.get(node, []):
                if source in node_positions:
                    incoming_ys.append(node_positions[source][1])

            # 나가는 연결의 Y 좌표 (타겟 노드들)
            for target in outgoing_connections.get(node, []):
                if target in node_positions:
                    outgoing_ys.append(node_positions[target][1])

            if prioritize_incoming:
                # 순방향 레이아웃: incoming 연결 우선
                # 노드는 소스들의 Y 위치를 따라가야 와이어가 꼬이지 않음
                if incoming_ys:
                    # 소스들의 Y 평균으로 정렬
                    barycenters[node] = sum(incoming_ys) / len(incoming_ys)
                elif outgoing_ys:
                    # incoming이 없으면 outgoing 사용 (레벨 0 노드)
                    # 타겟의 입력 포트 순서를 반영
                    if wire_order_to_target:
                        # 타겟의 입력 포트 순서 기반으로 정렬 키 계산
                        targets = list(outgoing_connections.get(node, []))
                        if targets:
                            first_target = targets[0]
                            sources_to_target = wire_order_to_target.get(first_target, [])
                            if node in sources_to_target:
                                # 포트 순서를 Y 좌표처럼 사용 (순서 * 큰 값)
                                port_order = sources_to_target.index(node)
                                barycenters[node] = port_order * 1000  # 큰 값으로 구분
                            else:
                                barycenters[node] = sum(outgoing_ys) / len(outgoing_ys)
                        else:
                            barycenters[node] = sum(outgoing_ys) / len(outgoing_ys)
                    else:
                        barycenters[node] = sum(outgoing_ys) / len(outgoing_ys)
                else:
                    # 연결이 없으면 현재 위치 유지
                    barycenters[node] = node_positions.get(node, (0, 0))[1]
            else:
                # 기존 방식: 모든 연결 동일하게 사용
                connected_ys = incoming_ys + outgoing_ys
                if connected_ys:
                    barycenters[node] = sum(connected_ys) / len(connected_ys)
                else:
                    barycenters[node] = node_positions.get(node, (0, 0))[1]

        # Barycenter 값으로 정렬
        sorted_nodes = sorted(level_nodes, key=lambda n: barycenters[n])
        return sorted_nodes

    def count_crossings_for_order(
        self,
        level_nodes: List[str],
        node_x: Dict[str, float],
        node_y_order: List[str],  # Y 순서 (위→아래)
        y_spacing: float,
        base_y: float,
        all_wires: List[Wire]
    ) -> int:
        """
        특정 Y 순서에서의 교차 수 계산

        Args:
            level_nodes: 현재 레벨 노드들
            node_x: 노드별 X 좌표
            node_y_order: Y 순서대로 정렬된 노드 목록
            y_spacing: Y 간격
            base_y: 시작 Y 좌표
            all_wires: 전체 와이어 목록

        Returns:
            교차 수
        """
        # 임시 Y 좌표 맵 생성
        temp_y = {}
        for i, node in enumerate(node_y_order):
            temp_y[node] = base_y + i * y_spacing

        # 와이어 위치 업데이트
        temp_wires = []
        for wire in all_wires:
            new_wire = Wire(
                source_guid=wire.source_guid,
                target_guid=wire.target_guid,
                source_x=wire.source_x,
                source_y=temp_y.get(wire.source_guid, wire.source_y),
                target_x=wire.target_x,
                target_y=temp_y.get(wire.target_guid, wire.target_y)
            )
            temp_wires.append(new_wire)

        return self.detector.count_crossings(temp_wires)

    def adjacent_swap_optimize(
        self,
        level_nodes: List[str],
        node_x: Dict[str, float],
        initial_order: List[str],
        y_spacing: float,
        base_y: float,
        all_wires: List[Wire],
        max_iterations: int = 50
    ) -> List[str]:
        """
        인접 교환 최적화

        교차가 줄어드는 방향으로 인접 노드를 반복 스왑

        Args:
            level_nodes: 현재 레벨 노드들
            node_x: 노드별 X 좌표
            initial_order: 초기 Y 순서
            y_spacing: Y 간격
            base_y: 시작 Y 좌표
            all_wires: 전체 와이어 목록
            max_iterations: 최대 반복 횟수

        Returns:
            최적화된 Y 순서
        """
        current_order = list(initial_order)
        n = len(current_order)

        if n < 2:
            return current_order

        current_crossings = self.count_crossings_for_order(
            level_nodes, node_x, current_order, y_spacing, base_y, all_wires
        )

        improved = True
        iteration = 0

        while improved and iteration < max_iterations:
            improved = False
            iteration += 1

            for i in range(n - 1):
                # 인접 노드 스왑 시도
                new_order = current_order.copy()
                new_order[i], new_order[i + 1] = new_order[i + 1], new_order[i]

                new_crossings = self.count_crossings_for_order(
                    level_nodes, node_x, new_order, y_spacing, base_y, all_wires
                )

                if new_crossings < current_crossings:
                    current_order = new_order
                    current_crossings = new_crossings
                    improved = True

        return current_order

    def minimize_crossings(
        self,
        level_nodes: List[str],
        node_positions: Dict[str, Tuple[float, float]],
        incoming_connections: Dict[str, List[str]],
        outgoing_connections: Dict[str, List[str]],
        all_wires: List[Wire],
        y_spacing: float = 50.0,
        base_y: float = 100.0,
        ml_initial_order: List[str] = None,
        wire_order_to_target: Dict[str, List[str]] = None
    ) -> Tuple[List[str], int]:
        """
        통합 교차 최소화 파이프라인

        1. ML 예측 또는 Barycenter로 초기 순서 결정
        2. Adjacent Swap으로 개선

        Args:
            level_nodes: 현재 레벨의 노드 목록
            node_positions: 모든 노드의 위치
            incoming_connections: 들어오는 연결
            outgoing_connections: 나가는 연결
            all_wires: 전체 와이어 목록
            y_spacing: Y 간격
            base_y: 시작 Y 좌표
            ml_initial_order: ML 예측 초기 순서 (선택)
            wire_order_to_target: 타겟별 소스 와이어 순서 {target: [sources in port order]}

        Returns:
            (최적화된 순서, 최종 교차 수)
        """
        if len(level_nodes) < 2:
            return level_nodes, 0

        node_x = {guid: pos[0] for guid, pos in node_positions.items()}

        # Step 1: 초기 순서 결정
        if ml_initial_order and set(ml_initial_order) == set(level_nodes):
            initial_order = ml_initial_order
        else:
            # Barycenter 휴리스틱 사용
            initial_order = self.barycenter_order(
                level_nodes, node_positions, incoming_connections, outgoing_connections,
                wire_order_to_target=wire_order_to_target
            )

        # Step 2: Adjacent Swap 최적화
        optimized_order = self.adjacent_swap_optimize(
            level_nodes, node_x, initial_order, y_spacing, base_y, all_wires
        )

        # 최종 교차 수 계산
        final_crossings = self.count_crossings_for_order(
            level_nodes, node_x, optimized_order, y_spacing, base_y, all_wires
        )

        return optimized_order, final_crossings

    def optimize_all_levels(
        self,
        levels_map: Dict[int, List[str]],
        node_positions: Dict[str, Tuple[float, float]],
        incoming_connections: Dict[str, List[str]],
        outgoing_connections: Dict[str, List[str]],
        all_wires: List[Wire],
        y_spacing: float = 50.0,
        ml_order_predictor=None,  # YOrderLearner.predict_order 함수
        max_sweeps: int = 3
    ) -> Dict[str, float]:
        """
        전체 레벨에 대한 교차 최소화 (Sugiyama 스타일)

        여러 번 순방향/역방향 스윕하며 최적화

        Args:
            levels_map: 레벨별 노드 목록 {level: [guids]}
            node_positions: 노드별 위치
            incoming_connections: 들어오는 연결
            outgoing_connections: 나가는 연결
            all_wires: 전체 와이어 목록
            y_spacing: Y 간격
            ml_order_predictor: ML 순서 예측 함수 (선택)
            max_sweeps: 최대 스윕 횟수

        Returns:
            최적화된 Y 좌표 맵 {guid: y}
        """
        if not levels_map:
            return {}

        max_level = max(levels_map.keys())
        min_level = min(levels_map.keys())

        # 현재 Y 좌표 맵
        current_y = {guid: pos[1] for guid, pos in node_positions.items()}

        # 레벨별 Y 범위 계산
        level_base_y = {}
        current_base = 100.0
        for lvl in sorted(levels_map.keys()):
            level_base_y[lvl] = current_base
            level_height = len(levels_map[lvl]) * y_spacing
            current_base += level_height + y_spacing * 2  # 레벨 간 여백

        for sweep in range(max_sweeps):
            # 순방향 스윕 (레벨 0 → max)
            for lvl in range(min_level, max_level + 1):
                if lvl not in levels_map or len(levels_map[lvl]) < 2:
                    continue

                level_nodes = levels_map[lvl]
                base_y = level_base_y[lvl]

                # ML 예측 순서 (있으면)
                ml_order = None
                if ml_order_predictor:
                    try:
                        # ml_order_predictor(source_name, source_type, sibling_names, sibling_types)
                        # 여기서는 단순화하여 사용하지 않음
                        pass
                    except:
                        pass

                # 현재 위치 기반 node_positions 업데이트
                current_positions = {
                    guid: (node_positions[guid][0], current_y.get(guid, node_positions[guid][1]))
                    for guid in node_positions
                }

                optimized_order, _ = self.minimize_crossings(
                    level_nodes=level_nodes,
                    node_positions=current_positions,
                    incoming_connections=incoming_connections,
                    outgoing_connections=outgoing_connections,
                    all_wires=all_wires,
                    y_spacing=y_spacing,
                    base_y=base_y,
                    ml_initial_order=ml_order
                )

                # Y 좌표 업데이트
                for i, guid in enumerate(optimized_order):
                    current_y[guid] = base_y + i * y_spacing

            # 역방향 스윕 (레벨 max → 0)
            for lvl in range(max_level, min_level - 1, -1):
                if lvl not in levels_map or len(levels_map[lvl]) < 2:
                    continue

                level_nodes = levels_map[lvl]
                base_y = level_base_y[lvl]

                current_positions = {
                    guid: (node_positions[guid][0], current_y.get(guid, node_positions[guid][1]))
                    for guid in node_positions
                }

                optimized_order, _ = self.minimize_crossings(
                    level_nodes=level_nodes,
                    node_positions=current_positions,
                    incoming_connections=incoming_connections,
                    outgoing_connections=outgoing_connections,
                    all_wires=all_wires,
                    y_spacing=y_spacing,
                    base_y=base_y
                )

                for i, guid in enumerate(optimized_order):
                    current_y[guid] = base_y + i * y_spacing

        return current_y


# Singleton
_minimizer: Optional[CrossingMinimizer] = None


def get_crossing_minimizer() -> CrossingMinimizer:
    """싱글톤 인스턴스 반환"""
    global _minimizer
    if _minimizer is None:
        _minimizer = CrossingMinimizer()
    return _minimizer
