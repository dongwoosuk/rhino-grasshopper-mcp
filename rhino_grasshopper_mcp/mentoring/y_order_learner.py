"""
Y Order Learner
===============

ML 기반 Y순서 패턴 학습 및 예측

Features:
- 사용자가 수동 정렬한 레이아웃에서 Y순서 패턴 학습
- 컴포넌트 이름별, 타입별 패턴 저장
- 분기 시 형제 컴포넌트들의 최적 Y순서 예측
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime

try:
    from .persistent_layout_learner import classify_component_type, ComponentType
except ImportError:
    from persistent_layout_learner import classify_component_type, ComponentType


@dataclass
class SiblingOrderFeature:
    """같은 소스에서 분기된 형제 컴포넌트들의 Y순서 피처"""
    source_guid: str              # 소스 컴포넌트 GUID
    source_name: str              # 소스 컴포넌트 이름
    source_type: str              # 소스 타입 (ComponentType)
    sibling_guids: List[str]      # Y순서대로 정렬된 형제 GUID들
    sibling_names: List[str]      # 형제들의 이름
    sibling_types: List[str]      # 형제들의 타입
    y_positions: List[float]      # 실제 Y 위치들


@dataclass
class YOrderPattern:
    """Y순서 패턴 (학습 결과)"""
    pattern_key: str              # 패턴 키 (예: "Number Slider -> [MATH, GEOMETRY]")
    type_order: List[str]         # 타입별 Y순서 (위→아래)
    name_order: List[str]         # 이름별 Y순서 (선택적)
    sample_count: int             # 학습 샘플 수
    confidence: float             # 신뢰도 (0~1)
    avg_spacing: float            # 평균 간격

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'YOrderPattern':
        return cls(**data)


class YOrderLearner:
    """Y순서 패턴 학습 및 예측 시스템"""

    VERSION = "1.0"

    def __init__(self, storage_path: str = None):
        # 학습 데이터
        self.source_type_patterns: Dict[str, YOrderPattern] = {}  # "INPUT_PARAM -> [MATH, GEOMETRY]"
        self.source_name_patterns: Dict[str, YOrderPattern] = {}  # "Number Slider -> [Addition, Circle]"
        self.type_priority: Dict[str, float] = {}  # 타입별 기본 Y 우선순위

        # 통계
        self.total_sessions = 0
        self.total_patterns_learned = 0
        self.last_updated = None

        # 저장 경로
        if storage_path:
            self.storage_path = storage_path
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.storage_path = os.path.join(current_dir, "y_order_learning_data.json")

        # 기본 타입 우선순위 초기화 (낮을수록 위쪽)
        self._init_default_type_priority()

        # 기존 데이터 로드
        self.load()

    def _init_default_type_priority(self):
        """기본 타입별 Y 우선순위 초기화"""
        self.type_priority = {
            ComponentType.INPUT_PARAM.value: 1.0,    # 입력이 위쪽
            ComponentType.MATH.value: 2.0,
            ComponentType.LOGIC.value: 3.0,
            ComponentType.LIST.value: 4.0,
            ComponentType.TREE.value: 5.0,
            ComponentType.GEOMETRY.value: 6.0,
            ComponentType.TRANSFORM.value: 7.0,
            ComponentType.UTIL.value: 8.0,
            ComponentType.OUTPUT_PARAM.value: 9.0,   # 출력이 아래쪽
            ComponentType.UNKNOWN.value: 5.0,
        }

    def extract_sibling_orders(
        self,
        components: List[dict],
        wires: List[dict]
    ) -> List[SiblingOrderFeature]:
        """
        캔버스에서 형제 순서 피처 추출

        Args:
            components: 컴포넌트 정보 리스트
            wires: 와이어 연결 리스트

        Returns:
            SiblingOrderFeature 목록
        """
        # 컴포넌트 맵 구축
        comp_map = {}
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid:
                comp_map[str(guid)] = comp

        # 소스별 타겟 그룹화
        source_to_targets = defaultdict(list)
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                source_to_targets[src_guid].append(tgt_guid)

        features = []

        # 분기가 있는 소스만 처리 (타겟 2개 이상)
        for src_guid, target_guids in source_to_targets.items():
            if len(target_guids) < 2:
                continue

            src_comp = comp_map[src_guid]
            src_name = src_comp.get('name', '')
            src_type = classify_component_type(
                name=src_name,
                category=src_comp.get('category', ''),
                subcategory=src_comp.get('subcategory', '')
            ).value

            # 타겟들의 정보 수집
            siblings_info = []
            for tgt_guid in target_guids:
                tgt_comp = comp_map[tgt_guid]
                tgt_y = float(tgt_comp.get('y') or tgt_comp.get('position_y') or 0)
                tgt_name = tgt_comp.get('name', '')
                tgt_type = classify_component_type(
                    name=tgt_name,
                    category=tgt_comp.get('category', ''),
                    subcategory=tgt_comp.get('subcategory', '')
                ).value

                siblings_info.append({
                    'guid': tgt_guid,
                    'name': tgt_name,
                    'type': tgt_type,
                    'y': tgt_y
                })

            # Y 순서대로 정렬
            siblings_info.sort(key=lambda x: x['y'])

            features.append(SiblingOrderFeature(
                source_guid=src_guid,
                source_name=src_name,
                source_type=src_type,
                sibling_guids=[s['guid'] for s in siblings_info],
                sibling_names=[s['name'] for s in siblings_info],
                sibling_types=[s['type'] for s in siblings_info],
                y_positions=[s['y'] for s in siblings_info]
            ))

        return features

    def learn_y_order(self, feature: SiblingOrderFeature):
        """
        단일 형제 순서 패턴 학습

        Args:
            feature: 형제 순서 피처
        """
        if len(feature.sibling_types) < 2:
            return

        # 1. 소스 타입 → 타겟 타입 순서 패턴
        type_key = f"{feature.source_type} -> {feature.sibling_types}"
        self._update_type_pattern(type_key, feature)

        # 2. 소스 이름 → 타겟 이름 순서 패턴 (구체적)
        name_key = f"{feature.source_name} -> {feature.sibling_names}"
        self._update_name_pattern(name_key, feature)

        # 3. 타입별 우선순위 업데이트
        self._update_type_priority(feature)

        self.total_patterns_learned += 1

    def _update_type_pattern(self, key: str, feature: SiblingOrderFeature):
        """타입 기반 패턴 업데이트"""
        if key in self.source_type_patterns:
            pattern = self.source_type_patterns[key]
            pattern.sample_count += 1
            pattern.confidence = min(0.95, 0.5 + pattern.sample_count * 0.05)

            # 평균 간격 업데이트
            if len(feature.y_positions) >= 2:
                spacings = [feature.y_positions[i+1] - feature.y_positions[i]
                           for i in range(len(feature.y_positions) - 1)]
                avg_spacing = sum(spacings) / len(spacings)
                pattern.avg_spacing = (pattern.avg_spacing * (pattern.sample_count - 1) + avg_spacing) / pattern.sample_count
        else:
            # 새 패턴 생성
            avg_spacing = 50.0
            if len(feature.y_positions) >= 2:
                spacings = [feature.y_positions[i+1] - feature.y_positions[i]
                           for i in range(len(feature.y_positions) - 1)]
                avg_spacing = sum(spacings) / len(spacings) if spacings else 50.0

            self.source_type_patterns[key] = YOrderPattern(
                pattern_key=key,
                type_order=feature.sibling_types.copy(),
                name_order=[],
                sample_count=1,
                confidence=0.5,
                avg_spacing=avg_spacing
            )

    def _update_name_pattern(self, key: str, feature: SiblingOrderFeature):
        """이름 기반 패턴 업데이트"""
        if key in self.source_name_patterns:
            pattern = self.source_name_patterns[key]
            pattern.sample_count += 1
            pattern.confidence = min(0.95, 0.5 + pattern.sample_count * 0.05)
        else:
            avg_spacing = 50.0
            if len(feature.y_positions) >= 2:
                spacings = [feature.y_positions[i+1] - feature.y_positions[i]
                           for i in range(len(feature.y_positions) - 1)]
                avg_spacing = sum(spacings) / len(spacings) if spacings else 50.0

            self.source_name_patterns[key] = YOrderPattern(
                pattern_key=key,
                type_order=feature.sibling_types.copy(),
                name_order=feature.sibling_names.copy(),
                sample_count=1,
                confidence=0.5,
                avg_spacing=avg_spacing
            )

    def _update_type_priority(self, feature: SiblingOrderFeature):
        """타입별 우선순위 학습 (Y 위치 기반)"""
        for i, (comp_type, y_pos) in enumerate(zip(feature.sibling_types, feature.y_positions)):
            # 상대적 순서를 우선순위에 반영
            relative_order = i / max(1, len(feature.sibling_types) - 1)  # 0~1

            if comp_type in self.type_priority:
                # 기존 값과 새 값의 가중 평균
                old_priority = self.type_priority[comp_type]
                # 새 우선순위: 0에 가까울수록 위쪽 (작은 값)
                new_priority = 1.0 + relative_order * 8.0  # 1~9 범위
                self.type_priority[comp_type] = old_priority * 0.9 + new_priority * 0.1

    def predict_order(
        self,
        source_name: str,
        source_type: str,
        sibling_names: List[str],
        sibling_types: List[str]
    ) -> List[int]:
        """
        형제들의 최적 Y순서 예측

        Args:
            source_name: 소스 컴포넌트 이름
            source_type: 소스 컴포넌트 타입
            sibling_names: 형제 컴포넌트 이름들
            sibling_types: 형제 컴포넌트 타입들

        Returns:
            순서 인덱스 리스트 (예: [2, 0, 1] = 원래 2번이 맨 위)
        """
        n = len(sibling_names)
        if n < 2:
            return list(range(n))

        # 1순위: 이름 기반 패턴 (가장 구체적)
        name_key = f"{source_name} -> {sibling_names}"
        if name_key in self.source_name_patterns:
            pattern = self.source_name_patterns[name_key]
            if pattern.confidence >= 0.6:
                return self._get_order_indices(sibling_names, pattern.name_order)

        # 2순위: 타입 기반 패턴
        type_key = f"{source_type} -> {sibling_types}"
        if type_key in self.source_type_patterns:
            pattern = self.source_type_patterns[type_key]
            if pattern.confidence >= 0.5:
                return self._get_order_indices(sibling_types, pattern.type_order)

        # 3순위: 기본 타입 우선순위
        return self._get_default_order(sibling_types)

    def _get_order_indices(self, items: List[str], reference_order: List[str]) -> List[int]:
        """참조 순서에 따른 인덱스 반환"""
        if len(items) != len(reference_order):
            return list(range(len(items)))

        # 참조 순서대로 현재 아이템의 인덱스 반환
        order_map = {item: i for i, item in enumerate(reference_order)}
        indexed = [(order_map.get(item, i), i) for i, item in enumerate(items)]
        indexed.sort(key=lambda x: x[0])
        return [x[1] for x in indexed]

    def _get_default_order(self, sibling_types: List[str]) -> List[int]:
        """기본 타입 우선순위에 따른 순서"""
        indexed = [(self.type_priority.get(t, 5.0), i) for i, t in enumerate(sibling_types)]
        indexed.sort(key=lambda x: x[0])
        return [x[1] for x in indexed]

    def get_predicted_spacing(self, source_name: str, source_type: str, sibling_count: int) -> float:
        """예측된 Y 간격 반환"""
        # 이름 기반 패턴에서 찾기
        for key, pattern in self.source_name_patterns.items():
            if key.startswith(source_name + " ->") and pattern.sample_count >= 2:
                return pattern.avg_spacing

        # 타입 기반 패턴에서 찾기
        for key, pattern in self.source_type_patterns.items():
            if key.startswith(source_type + " ->") and pattern.sample_count >= 2:
                return pattern.avg_spacing

        return 50.0  # 기본값

    def learn_from_canvas(self, components: List[dict], wires: List[dict], source_name: str = "manual"):
        """
        캔버스에서 Y순서 패턴 학습

        Args:
            components: 컴포넌트 정보 리스트
            wires: 와이어 연결 리스트
            source_name: 학습 소스 이름
        """
        features = self.extract_sibling_orders(components, wires)

        for feature in features:
            self.learn_y_order(feature)

        self.total_sessions += 1
        self.last_updated = datetime.now().isoformat()
        self.save()

        return {
            "success": True,
            "features_extracted": len(features),
            "total_type_patterns": len(self.source_type_patterns),
            "total_name_patterns": len(self.source_name_patterns)
        }

    def save(self):
        """학습 데이터 저장"""
        data = {
            'version': self.VERSION,
            'meta': {
                'total_sessions': self.total_sessions,
                'total_patterns_learned': self.total_patterns_learned,
                'last_updated': self.last_updated
            },
            'source_type_patterns': {
                k: v.to_dict() for k, v in self.source_type_patterns.items()
            },
            'source_name_patterns': {
                k: v.to_dict() for k, v in list(self.source_name_patterns.items())[-100:]  # 최근 100개만
            },
            'type_priority': self.type_priority
        }

        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving Y order learning data: {e}")

    def load(self):
        """학습 데이터 로드"""
        if not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if data.get('version') != self.VERSION:
                print(f"Y order learning data version mismatch, starting fresh")
                return

            meta = data.get('meta', {})
            self.total_sessions = meta.get('total_sessions', 0)
            self.total_patterns_learned = meta.get('total_patterns_learned', 0)
            self.last_updated = meta.get('last_updated')

            # 타입 패턴 로드
            for k, v in data.get('source_type_patterns', {}).items():
                self.source_type_patterns[k] = YOrderPattern.from_dict(v)

            # 이름 패턴 로드
            for k, v in data.get('source_name_patterns', {}).items():
                self.source_name_patterns[k] = YOrderPattern.from_dict(v)

            # 타입 우선순위 로드
            if 'type_priority' in data:
                self.type_priority.update(data['type_priority'])

        except Exception as e:
            print(f"Error loading Y order learning data: {e}")

    def clear(self):
        """학습 데이터 초기화"""
        self.source_type_patterns.clear()
        self.source_name_patterns.clear()
        self._init_default_type_priority()
        self.total_sessions = 0
        self.total_patterns_learned = 0
        self.last_updated = None

        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)

        return {"success": True, "message": "Y order learning data cleared"}

    def get_summary(self) -> dict:
        """학습 요약 반환"""
        return {
            'version': self.VERSION,
            'total_sessions': self.total_sessions,
            'total_patterns_learned': self.total_patterns_learned,
            'type_patterns_count': len(self.source_type_patterns),
            'name_patterns_count': len(self.source_name_patterns),
            'last_updated': self.last_updated,
            'top_type_patterns': [
                {'key': k, 'samples': v.sample_count, 'confidence': round(v.confidence, 2)}
                for k, v in sorted(
                    self.source_type_patterns.items(),
                    key=lambda x: x[1].sample_count,
                    reverse=True
                )[:5]
            ]
        }


# Singleton
_y_order_learner: Optional[YOrderLearner] = None


def get_y_order_learner(storage_path: str = None) -> YOrderLearner:
    """싱글톤 인스턴스 반환"""
    global _y_order_learner
    if _y_order_learner is None:
        _y_order_learner = YOrderLearner(storage_path)
    return _y_order_learner


def reset_y_order_learner():
    """싱글톤 리셋"""
    global _y_order_learner
    _y_order_learner = None
