"""
Wire Crossing Detector
======================

CCW (Counter-Clockwise) 알고리즘을 사용한 와이어 교차 감지

Features:
- 두 선분(와이어)의 교차 여부 판단
- 전체 와이어 세트의 교차 수 계산
- 교차하는 와이어 쌍 목록 반환
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Set
from collections import defaultdict


@dataclass
class Wire:
    """와이어 표현 (선분)"""
    source_guid: str
    target_guid: str
    source_x: float
    source_y: float
    target_x: float
    target_y: float

    @property
    def source_point(self) -> Tuple[float, float]:
        return (self.source_x, self.source_y)

    @property
    def target_point(self) -> Tuple[float, float]:
        return (self.target_x, self.target_y)

    def __hash__(self):
        return hash((self.source_guid, self.target_guid))

    def __eq__(self, other):
        if not isinstance(other, Wire):
            return False
        return self.source_guid == other.source_guid and self.target_guid == other.target_guid


class WireCrossingDetector:
    """와이어 교차 감지 및 분석"""

    def ccw(self, A: Tuple[float, float], B: Tuple[float, float], C: Tuple[float, float]) -> float:
        """
        세 점의 방향 판단 (Counter-Clockwise)

        Returns:
            > 0: 반시계 방향 (CCW)
            < 0: 시계 방향 (CW)
            = 0: 일직선
        """
        return (C[1] - A[1]) * (B[0] - A[0]) - (B[1] - A[1]) * (C[0] - A[0])

    def segments_intersect(
        self,
        A: Tuple[float, float],
        B: Tuple[float, float],
        C: Tuple[float, float],
        D: Tuple[float, float]
    ) -> bool:
        """
        선분 AB와 CD가 교차하는지 판단

        두 선분이 "진짜" 교차하는지 확인 (끝점이 겹치는 경우 제외)
        """
        # 같은 점에서 시작/끝나는 와이어는 교차가 아님
        if A == C or A == D or B == C or B == D:
            return False

        ccw1 = self.ccw(A, C, D)
        ccw2 = self.ccw(B, C, D)
        ccw3 = self.ccw(A, B, C)
        ccw4 = self.ccw(A, B, D)

        # 두 선분이 교차하려면:
        # - A와 B가 CD의 반대편에 있어야 함
        # - C와 D가 AB의 반대편에 있어야 함
        if ccw1 * ccw2 < 0 and ccw3 * ccw4 < 0:
            return True

        return False

    def detect_crossing(self, wire1: Wire, wire2: Wire) -> bool:
        """
        두 와이어의 교차 여부 판단

        Args:
            wire1: 첫 번째 와이어
            wire2: 두 번째 와이어

        Returns:
            교차하면 True, 아니면 False
        """
        # 같은 소스 또는 타겟을 공유하면 교차가 아님
        if wire1.source_guid == wire2.source_guid:
            return False
        if wire1.target_guid == wire2.target_guid:
            return False
        if wire1.source_guid == wire2.target_guid:
            return False
        if wire1.target_guid == wire2.source_guid:
            return False

        return self.segments_intersect(
            wire1.source_point, wire1.target_point,
            wire2.source_point, wire2.target_point
        )

    def count_crossings(self, wires: List[Wire]) -> int:
        """
        전체 와이어 세트의 교차 수 계산

        Args:
            wires: 와이어 목록

        Returns:
            교차 수
        """
        count = 0
        n = len(wires)

        for i in range(n):
            for j in range(i + 1, n):
                if self.detect_crossing(wires[i], wires[j]):
                    count += 1

        return count

    def get_crossing_pairs(self, wires: List[Wire]) -> List[Tuple[Wire, Wire]]:
        """
        교차하는 와이어 쌍 목록 반환

        Args:
            wires: 와이어 목록

        Returns:
            교차하는 (wire1, wire2) 튜플 목록
        """
        pairs = []
        n = len(wires)

        for i in range(n):
            for j in range(i + 1, n):
                if self.detect_crossing(wires[i], wires[j]):
                    pairs.append((wires[i], wires[j]))

        return pairs

    def count_crossings_for_node(self, node_guid: str, wires: List[Wire]) -> int:
        """
        특정 노드와 연결된 와이어의 교차 수

        Args:
            node_guid: 노드 GUID
            wires: 전체 와이어 목록

        Returns:
            해당 노드 관련 교차 수
        """
        # 해당 노드와 연결된 와이어 찾기
        node_wires = [w for w in wires if w.source_guid == node_guid or w.target_guid == node_guid]
        other_wires = [w for w in wires if w.source_guid != node_guid and w.target_guid != node_guid]

        count = 0
        for nw in node_wires:
            for ow in other_wires:
                if self.detect_crossing(nw, ow):
                    count += 1

        return count

    def build_wires_from_layout(
        self,
        components: List[dict],
        wire_connections: List[dict],
        position_map: dict = None
    ) -> List[Wire]:
        """
        컴포넌트와 연결 정보로부터 Wire 객체 목록 생성

        Args:
            components: 컴포넌트 정보 리스트
            wire_connections: 와이어 연결 리스트 [{source_guid, target_guid}]
            position_map: 선택적 위치 오버라이드 {guid: (x, y)}

        Returns:
            Wire 객체 목록
        """
        # 컴포넌트 위치 맵 구축
        comp_positions = {}
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid:
                guid = str(guid)
                if position_map and guid in position_map:
                    x, y = position_map[guid]
                else:
                    x = float(comp.get('x') or comp.get('position_x') or 0)
                    y = float(comp.get('y') or comp.get('position_y') or 0)
                comp_positions[guid] = (x, y)

        # Wire 객체 생성
        wires = []
        for conn in wire_connections:
            src_guid = str(conn.get('source_guid', ''))
            tgt_guid = str(conn.get('target_guid', ''))

            if src_guid in comp_positions and tgt_guid in comp_positions:
                src_x, src_y = comp_positions[src_guid]
                tgt_x, tgt_y = comp_positions[tgt_guid]

                wires.append(Wire(
                    source_guid=src_guid,
                    target_guid=tgt_guid,
                    source_x=src_x,
                    source_y=src_y,
                    target_x=tgt_x,
                    target_y=tgt_y
                ))

        return wires

    def update_wire_positions(
        self,
        wires: List[Wire],
        position_map: dict
    ) -> List[Wire]:
        """
        와이어 목록의 위치를 새 position_map으로 업데이트

        Args:
            wires: 기존 와이어 목록
            position_map: 새 위치 {guid: (x, y)}

        Returns:
            업데이트된 Wire 객체 목록
        """
        updated = []
        for wire in wires:
            src_pos = position_map.get(wire.source_guid, (wire.source_x, wire.source_y))
            tgt_pos = position_map.get(wire.target_guid, (wire.target_x, wire.target_y))

            updated.append(Wire(
                source_guid=wire.source_guid,
                target_guid=wire.target_guid,
                source_x=src_pos[0],
                source_y=src_pos[1],
                target_x=tgt_pos[0],
                target_y=tgt_pos[1]
            ))

        return updated

    def get_crossing_statistics(self, wires: List[Wire]) -> dict:
        """
        와이어 교차 통계 반환

        Returns:
            {
                'total_wires': int,
                'total_crossings': int,
                'crossing_pairs': List[Tuple[str, str]],
                'nodes_with_most_crossings': List[Tuple[str, int]]
            }
        """
        crossing_pairs = self.get_crossing_pairs(wires)

        # 노드별 교차 수 계산
        node_crossings = defaultdict(int)
        for w1, w2 in crossing_pairs:
            node_crossings[w1.source_guid] += 1
            node_crossings[w1.target_guid] += 1
            node_crossings[w2.source_guid] += 1
            node_crossings[w2.target_guid] += 1

        # 교차 많은 순으로 정렬
        sorted_nodes = sorted(node_crossings.items(), key=lambda x: x[1], reverse=True)

        return {
            'total_wires': len(wires),
            'total_crossings': len(crossing_pairs),
            'crossing_pairs': [(w1.source_guid + '->' + w1.target_guid,
                               w2.source_guid + '->' + w2.target_guid)
                              for w1, w2 in crossing_pairs[:10]],  # Top 10
            'nodes_with_most_crossings': sorted_nodes[:10]  # Top 10
        }


# Singleton instance
_detector: Optional[WireCrossingDetector] = None


def get_crossing_detector() -> WireCrossingDetector:
    """싱글톤 인스턴스 반환"""
    global _detector
    if _detector is None:
        _detector = WireCrossingDetector()
    return _detector
