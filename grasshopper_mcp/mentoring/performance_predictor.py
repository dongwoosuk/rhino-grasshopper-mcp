"""
Performance Predictor
=====================

최적화 적용 전 성능 개선을 예측하는 모듈

Features:
- 최적화 타입별 개선율 예측
- 신뢰도(confidence) 계산
- 노력 수준(effort) 표시
- 적용 단계 가이드
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any
import random

from . import OptimizationPrediction


class PerformancePredictor:
    """최적화 적용 전 성능 개선을 예측하는 엔진"""

    # 최적화 패턴별 경험적 개선율 데이터
    OPTIMIZATION_PATTERNS = {
        "disable_heavy_preview": {
            "improvement_range": (0.15, 0.40),  # 15-40% 개선
            "confidence_base": 0.85,
            "effort": "low",
            "description": "무거운 프리뷰 지오메트리가 있는 컴포넌트의 프리뷰를 끕니다",
            "steps": [
                "대상 컴포넌트 선택",
                "우클릭 → Preview 해제",
                "또는 Ctrl+Q로 프리뷰 토글"
            ],
            "applicable_categories": ["Mesh", "Surface", "Brep", "SubD"]
        },
        "add_data_dam": {
            "improvement_range": (0.20, 0.50),
            "confidence_base": 0.75,
            "effort": "low",
            "description": "자주 변경되지 않는 데이터 흐름에 Data Dam을 추가하여 불필요한 재계산 방지",
            "steps": [
                "안정적인 데이터 출력 지점 찾기",
                "Data Dam 컴포넌트 삽입",
                "필요할 때만 Dam 열기"
            ],
            "applicable_categories": ["Params", "Sets"]
        },
        "simplify_tree_operations": {
            "improvement_range": (0.10, 0.35),
            "confidence_base": 0.70,
            "effort": "medium",
            "description": "과도한 Flatten/Graft 연산을 Path Mapper로 단순화",
            "steps": [
                "연속된 Flatten/Graft 패턴 찾기",
                "Path Mapper로 대체",
                "데이터 구조 확인"
            ],
            "applicable_patterns": ["flatten_graft_chain", "excessive_tree_ops"]
        },
        "cache_expensive_geometry": {
            "improvement_range": (0.30, 0.60),
            "confidence_base": 0.80,
            "effort": "high",
            "description": "비용이 큰 지오메트리 연산 결과를 캐싱 (Internalize 또는 Data Dam)",
            "steps": [
                "느린 지오메트리 연산 컴포넌트 찾기",
                "결과를 Internalize하거나 Data Dam 추가",
                "업스트림 변경 시에만 재계산"
            ],
            "applicable_categories": ["Intersect", "Mesh", "Surface"]
        },
        "use_native_components": {
            "improvement_range": (0.10, 0.25),
            "confidence_base": 0.90,
            "effort": "medium",
            "description": "Expression/Python 스크립트 대신 네이티브 GH 컴포넌트 사용",
            "steps": [
                "Expression 또는 Python 컴포넌트 찾기",
                "동일 기능의 네이티브 컴포넌트로 대체",
                "성능 비교 테스트"
            ],
            "applicable_categories": ["Script", "Maths"]
        },
        "reduce_list_operations": {
            "improvement_range": (0.05, 0.20),
            "confidence_base": 0.75,
            "effort": "low",
            "description": "불필요한 리스트 연산 (Sort, Reverse, Shift) 제거",
            "steps": [
                "데이터 흐름에서 리스트 연산 확인",
                "실제로 필요한 연산인지 검토",
                "불필요한 컴포넌트 제거"
            ],
            "applicable_categories": ["Sets"]
        },
        "batch_boolean_operations": {
            "improvement_range": (0.25, 0.55),
            "confidence_base": 0.80,
            "effort": "medium",
            "description": "연속 Boolean 연산을 배치 처리로 결합",
            "steps": [
                "직렬 Boolean Union/Difference 찾기",
                "Solid Union/Difference 배치 컴포넌트로 대체",
                "입력을 리스트로 결합"
            ],
            "applicable_categories": ["Intersect"]
        },
        "reduce_mesh_resolution": {
            "improvement_range": (0.20, 0.50),
            "confidence_base": 0.85,
            "effort": "low",
            "description": "메쉬 해상도를 적절한 수준으로 낮춤",
            "steps": [
                "Mesh Settings 확인",
                "적절한 해상도로 조정",
                "품질과 성능 밸런스 확인"
            ],
            "applicable_categories": ["Mesh"]
        }
    }

    # 컴포넌트 카테고리별 기본 실행 시간 가중치
    CATEGORY_WEIGHTS = {
        "Params": 0.1,
        "Maths": 0.2,
        "Sets": 0.3,
        "Vector": 0.3,
        "Curve": 0.5,
        "Surface": 1.0,
        "Mesh": 1.2,
        "Intersect": 2.0,
        "Transform": 0.4,
        "Display": 0.2,
        "Script": 1.5,
    }

    def __init__(self, analyzer: Any = None):
        """
        Args:
            analyzer: GHLiveAnalyzer 인스턴스 (선택적)
        """
        self.analyzer = analyzer
        self._component_data: Dict[str, dict] = {}
        self._performance_data: Dict[str, float] = {}

    def set_component_data(self, data: Dict[str, dict]):
        """외부에서 컴포넌트 데이터 설정"""
        self._component_data = data

    def set_performance_data(self, data: Dict[str, float]):
        """외부에서 성능 데이터 설정 (guid -> execution_time_ms)"""
        self._performance_data = data

    def predict_optimization_impact(
        self,
        optimization_type: str,
        target_guids: List[str] = None
    ) -> OptimizationPrediction:
        """
        특정 최적화의 영향을 예측

        Args:
            optimization_type: 최적화 타입 (OPTIMIZATION_PATTERNS의 키)
            target_guids: 대상 컴포넌트 GUID 목록 (None이면 자동 탐지)

        Returns:
            OptimizationPrediction 객체
        """
        if optimization_type not in self.OPTIMIZATION_PATTERNS:
            raise ValueError(f"Unknown optimization type: {optimization_type}")

        pattern = self.OPTIMIZATION_PATTERNS[optimization_type]

        # 대상 컴포넌트 결정
        if target_guids is None:
            target_guids = self._find_applicable_components(optimization_type)

        # 현재 실행 시간 계산
        current_time = self._calculate_current_time(target_guids)

        # 개선율 예측
        improvement_range = pattern["improvement_range"]

        # 컴포넌트 특성에 따른 개선율 조정
        improvement_factor = self._calculate_improvement_factor(
            target_guids,
            improvement_range
        )

        predicted_time = current_time * (1 - improvement_factor)
        improvement_percent = improvement_factor * 100

        # 신뢰도 계산
        confidence = self._calculate_confidence(
            pattern["confidence_base"],
            target_guids,
            optimization_type
        )

        return OptimizationPrediction(
            optimization_type=optimization_type,
            target_components=target_guids,
            current_time_ms=current_time,
            predicted_time_ms=predicted_time,
            improvement_percent=improvement_percent,
            confidence=confidence,
            effort_level=pattern["effort"],
            description=pattern["description"],
            steps=pattern["steps"]
        )

    def analyze_all_optimizations(self) -> List[OptimizationPrediction]:
        """
        모든 가능한 최적화를 분석하고 개선율 순으로 정렬

        Returns:
            개선율 내림차순 정렬된 OptimizationPrediction 리스트
        """
        predictions = []

        for opt_type in self.OPTIMIZATION_PATTERNS:
            applicable_guids = self._find_applicable_components(opt_type)
            if applicable_guids:
                try:
                    prediction = self.predict_optimization_impact(opt_type, applicable_guids)
                    if prediction.improvement_percent > 0:
                        predictions.append(prediction)
                except Exception:
                    continue

        # 개선율 * 신뢰도로 정렬 (실질적 기대 효과 순)
        predictions.sort(
            key=lambda p: p.improvement_percent * p.confidence,
            reverse=True
        )

        return predictions

    def get_optimization_summary(self) -> dict:
        """
        전체 최적화 가능성 요약

        Returns:
            {
                'total_current_time_ms': float,
                'total_potential_improvement_ms': float,
                'total_potential_improvement_percent': float,
                'top_optimizations': List[dict],
                'effort_breakdown': dict
            }
        """
        predictions = self.analyze_all_optimizations()

        if not predictions:
            return {
                'total_current_time_ms': 0,
                'total_potential_improvement_ms': 0,
                'total_potential_improvement_percent': 0,
                'top_optimizations': [],
                'effort_breakdown': {'low': 0, 'medium': 0, 'high': 0}
            }

        # 중복 컴포넌트를 고려한 총 개선 시간 계산
        seen_guids = set()
        total_improvement_ms = 0
        total_current = 0

        for pred in predictions:
            new_guids = [g for g in pred.target_components if g not in seen_guids]
            if new_guids:
                ratio = len(new_guids) / len(pred.target_components)
                total_improvement_ms += (pred.current_time_ms - pred.predicted_time_ms) * ratio
                total_current += pred.current_time_ms * ratio
                seen_guids.update(new_guids)

        # 노력 수준별 분류
        effort_breakdown = {'low': 0, 'medium': 0, 'high': 0}
        for pred in predictions:
            effort_breakdown[pred.effort_level] += 1

        return {
            'total_current_time_ms': total_current,
            'total_potential_improvement_ms': total_improvement_ms,
            'total_potential_improvement_percent': (total_improvement_ms / total_current * 100) if total_current > 0 else 0,
            'top_optimizations': [
                {
                    'type': p.optimization_type,
                    'improvement_percent': p.improvement_percent,
                    'confidence': p.confidence,
                    'effort': p.effort_level,
                    'component_count': len(p.target_components)
                }
                for p in predictions[:5]  # Top 5
            ],
            'effort_breakdown': effort_breakdown
        }

    def _find_applicable_components(self, optimization_type: str) -> List[str]:
        """최적화 타입에 해당하는 컴포넌트 찾기"""
        pattern = self.OPTIMIZATION_PATTERNS[optimization_type]
        applicable = []

        applicable_categories = pattern.get("applicable_categories", [])

        for guid, comp in self._component_data.items():
            category = comp.get("category", "")

            # 카테고리 매칭
            if applicable_categories and category in applicable_categories:
                applicable.append(guid)

            # 느린 컴포넌트 (성능 데이터가 있는 경우)
            if guid in self._performance_data:
                exec_time = self._performance_data[guid]
                if exec_time > 100:  # 100ms 이상
                    if optimization_type in ["disable_heavy_preview", "cache_expensive_geometry"]:
                        applicable.append(guid)

        return list(set(applicable))

    def _calculate_current_time(self, guids: List[str]) -> float:
        """컴포넌트들의 현재 실행 시간 계산"""
        total = 0.0
        for guid in guids:
            if guid in self._performance_data:
                total += self._performance_data[guid]
            elif guid in self._component_data:
                # 성능 데이터 없으면 카테고리 기반 추정
                category = self._component_data[guid].get("category", "Params")
                weight = self.CATEGORY_WEIGHTS.get(category, 0.5)
                total += weight * 50  # 기본 50ms * 가중치
            else:
                total += 25  # 기본값
        return total

    def _calculate_improvement_factor(
        self,
        guids: List[str],
        improvement_range: Tuple[float, float]
    ) -> float:
        """개선율 팩터 계산 (0.0 ~ 1.0)"""
        min_imp, max_imp = improvement_range

        if not guids:
            return 0.0

        # 컴포넌트 수에 따른 스케일링
        # 컴포넌트가 많을수록 개선 효과가 큼
        component_factor = min(1.0, len(guids) / 10)

        # 범위 내에서 팩터 계산
        return min_imp + (max_imp - min_imp) * component_factor

    def _calculate_confidence(
        self,
        base_confidence: float,
        guids: List[str],
        optimization_type: str
    ) -> float:
        """신뢰도 계산"""
        confidence = base_confidence

        # 실제 성능 데이터가 있으면 신뢰도 증가
        measured_count = sum(1 for g in guids if g in self._performance_data)
        if guids:
            data_ratio = measured_count / len(guids)
            confidence = confidence * (0.8 + 0.2 * data_ratio)

        # 컴포넌트 수가 너무 적으면 신뢰도 감소
        if len(guids) < 2:
            confidence *= 0.7

        return min(1.0, confidence)


# ============================================================
# Utility Functions
# ============================================================

def create_predictor_from_canvas_data(
    components: List[dict],
    performance_times: Dict[str, float] = None
) -> PerformancePredictor:
    """
    캔버스 데이터로부터 PerformancePredictor 생성

    Args:
        components: 컴포넌트 정보 리스트
        performance_times: GUID -> 실행시간(ms) 매핑

    Returns:
        설정된 PerformancePredictor 인스턴스
    """
    predictor = PerformancePredictor()

    # 컴포넌트 데이터 변환
    comp_data = {}
    for comp in components:
        guid = comp.get('guid') or comp.get('InstanceGuid')
        if guid:
            comp_data[str(guid)] = {
                'name': comp.get('name', ''),
                'category': comp.get('category', ''),
                'nickname': comp.get('nickname', ''),
            }

    predictor.set_component_data(comp_data)

    if performance_times:
        predictor.set_performance_data(performance_times)

    return predictor
