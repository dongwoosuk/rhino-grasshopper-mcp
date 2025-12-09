"""
Alternative Logic Suggester
===========================

현재 로직의 더 나은 대안을 제안하는 모듈

Features:
- 비효율적인 패턴 감지
- 최적화된 대안 제안
- 적용 방법 가이드
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any, Set

from . import AlternativeApproach


class AlternativeSuggester:
    """현재 로직의 더 나은 대안을 제안하는 엔진"""

    # 알려진 패턴 대체 맵
    PATTERN_ALTERNATIVES = {
        "multiple_move": {
            "name": "Multiple Move Pattern",
            "description_ko": "여러 개의 Move 컴포넌트를 연속으로 사용",
            "alternative": "single_transform_matrix",
            "alternative_name": "Transform Matrix",
            "alternative_description": "여러 Move 대신 Transform Matrix 하나로 결합",
            "improvement": "faster",
            "improvement_percent": (15, 35),
            "detect_components": ["Move"],
            "min_chain_length": 2,
            "steps": [
                "연속된 Move 컴포넌트들의 벡터 입력 확인",
                "Vector Addition으로 벡터들을 합산",
                "단일 Move 또는 Transform으로 대체",
                "중간 Move 컴포넌트 제거"
            ]
        },
        "flatten_then_graft": {
            "name": "Flatten → Graft Pattern",
            "description_ko": "Flatten 후 Graft를 연속으로 사용하는 비효율적 패턴",
            "alternative": "path_mapper",
            "alternative_name": "Path Mapper",
            "alternative_description": "Flatten + Graft 대신 Path Mapper로 직접 매핑",
            "improvement": "cleaner",
            "improvement_percent": (10, 25),
            "detect_components": ["Flatten", "Graft"],
            "sequence_required": True,
            "steps": [
                "Flatten과 Graft 사이의 데이터 구조 확인",
                "Path Mapper 컴포넌트로 대체",
                "소스/타겟 경로 매핑 설정",
                "기존 Flatten/Graft 제거"
            ]
        },
        "python_loop_geometry": {
            "name": "Python Loop Geometry",
            "description_ko": "Python 스크립트 내에서 지오메트리 루프 처리",
            "alternative": "native_components",
            "alternative_name": "Native GH Components",
            "alternative_description": "Python 루프 대신 네이티브 GH 컴포넌트 사용",
            "improvement": "faster",
            "improvement_percent": (20, 50),
            "detect_components": ["GhPython Script", "Python"],
            "code_patterns": ["for ", "while ", "loop"],
            "steps": [
                "Python 스크립트의 루프 로직 분석",
                "동일 기능의 GH 네이티브 컴포넌트 찾기",
                "데이터 트리 구조로 입력 재구성",
                "Python 스크립트를 네이티브 컴포넌트로 대체"
            ]
        },
        "serial_boolean": {
            "name": "Serial Boolean Operations",
            "description_ko": "Boolean Union/Difference를 연속으로 적용",
            "alternative": "batch_boolean",
            "alternative_name": "Batch Boolean",
            "alternative_description": "연속 Boolean 대신 한번에 배치 처리",
            "improvement": "faster",
            "improvement_percent": (25, 55),
            "detect_components": ["Solid Union", "Solid Difference", "Region Union", "Region Difference"],
            "min_chain_length": 2,
            "steps": [
                "연속된 Boolean 연산 확인",
                "입력 지오메트리를 리스트로 수집",
                "단일 Boolean 컴포넌트로 대체 (리스트 입력)",
                "중간 Boolean 컴포넌트 제거"
            ]
        },
        "expression_math": {
            "name": "Expression for Simple Math",
            "description_ko": "단순한 수학 연산에 Expression 컴포넌트 사용",
            "alternative": "native_math",
            "alternative_name": "Native Math Components",
            "alternative_description": "Expression 컴포넌트 대신 네이티브 Math 컴포넌트",
            "improvement": "faster",
            "improvement_percent": (10, 25),
            "detect_components": ["Expression", "Evaluate"],
            "simple_operations": ["+", "-", "*", "/", "sin", "cos", "sqrt"],
            "steps": [
                "Expression 컴포넌트의 수식 확인",
                "단순 연산인 경우 네이티브 컴포넌트 찾기",
                "Addition, Multiplication 등으로 대체",
                "복잡한 수식만 Expression으로 유지"
            ]
        },
        "excessive_list_item": {
            "name": "Excessive List Item Access",
            "description_ko": "같은 리스트에서 여러 List Item으로 개별 접근",
            "alternative": "list_split",
            "alternative_name": "List Split / Deconstruct",
            "alternative_description": "여러 List Item 대신 Split List 또는 Deconstruct 사용",
            "improvement": "cleaner",
            "improvement_percent": (5, 15),
            "detect_components": ["List Item"],
            "min_count_same_source": 3,
            "steps": [
                "같은 소스에서 오는 List Item들 확인",
                "Split List로 한번에 분리",
                "또는 Deconstruct로 구조 분해",
                "개별 List Item 컴포넌트 제거"
            ]
        },
        "repeated_domain": {
            "name": "Repeated Domain Creation",
            "description_ko": "같은 도메인을 여러 번 생성",
            "alternative": "shared_domain",
            "alternative_name": "Shared Domain",
            "alternative_description": "도메인을 한 번 생성하고 공유",
            "improvement": "cleaner",
            "improvement_percent": (3, 10),
            "detect_components": ["Construct Domain", "Domain"],
            "min_similar_count": 2,
            "steps": [
                "동일한 값으로 생성되는 도메인 찾기",
                "하나의 도메인 컴포넌트로 통합",
                "여러 곳에서 공유 사용"
            ]
        },
        "point_deconstruct_construct": {
            "name": "Point Deconstruct → Modify → Construct",
            "description_ko": "Point를 분해하고 좌표 수정 후 다시 생성",
            "alternative": "direct_transform",
            "alternative_name": "Direct Transform",
            "alternative_description": "Point 분해/생성 대신 직접 변환",
            "improvement": "cleaner",
            "improvement_percent": (10, 20),
            "detect_components": ["Deconstruct Point", "Construct Point"],
            "sequence_required": True,
            "steps": [
                "Deconstruct → 연산 → Construct 패턴 찾기",
                "Move, Scale 등 직접 변환으로 대체 가능한지 확인",
                "Transform 컴포넌트로 대체"
            ]
        },
        "manual_data_matching": {
            "name": "Manual Data Matching",
            "description_ko": "Shift List, Reverse 등으로 수동 데이터 매칭",
            "alternative": "cross_reference",
            "alternative_name": "Cross Reference",
            "alternative_description": "수동 매칭 대신 Cross Reference 또는 Longest List 사용",
            "improvement": "cleaner",
            "improvement_percent": (5, 15),
            "detect_components": ["Shift List", "Reverse List"],
            "usage_pattern": "matching",
            "steps": [
                "데이터 매칭 목적의 Shift/Reverse 찾기",
                "Cross Reference로 대체 가능한지 확인",
                "또는 Data Matching 설정 변경"
            ]
        }
    }

    # 컴포넌트 카테고리별 일반적인 대안
    CATEGORY_ALTERNATIVES = {
        "Script": {
            "general_advice": "가능하면 네이티브 GH 컴포넌트 사용",
            "reason": "네이티브 컴포넌트가 더 빠르고 디버깅이 쉬움"
        },
        "Maths": {
            "general_advice": "Expression 대신 개별 Math 컴포넌트 사용",
            "reason": "개별 컴포넌트가 더 읽기 쉽고 약간 더 빠름"
        },
        "Intersect": {
            "general_advice": "Boolean 연산은 가능하면 배치로 처리",
            "reason": "연속 Boolean보다 배치 처리가 훨씬 빠름"
        }
    }

    def __init__(self, analyzer: Any = None):
        """
        Args:
            analyzer: GHLiveAnalyzer 인스턴스 (선택적)
        """
        self.analyzer = analyzer
        self._component_data: Dict[str, dict] = {}
        self._wire_connections: List[dict] = []

    def set_component_data(self, data: Dict[str, dict]):
        """외부에서 컴포넌트 데이터 설정"""
        self._component_data = data

    def set_wire_connections(self, connections: List[dict]):
        """외부에서 와이어 연결 데이터 설정"""
        self._wire_connections = connections

    def detect_improvable_patterns(self) -> List[dict]:
        """
        개선 가능한 패턴 감지

        Returns:
            감지된 패턴 리스트
        """
        detected = []

        # 컴포넌트 이름별 그룹화
        comp_by_name: Dict[str, List[str]] = {}
        for guid, comp in self._component_data.items():
            name = comp.get('name', '')
            if name not in comp_by_name:
                comp_by_name[name] = []
            comp_by_name[name].append(guid)

        # 각 패턴 검사
        for pattern_id, pattern in self.PATTERN_ALTERNATIVES.items():
            detect_components = pattern.get('detect_components', [])

            # 해당 컴포넌트가 존재하는지 확인
            found_components = []
            for comp_name in detect_components:
                if comp_name in comp_by_name:
                    found_components.extend(comp_by_name[comp_name])

            if not found_components:
                continue

            # 최소 개수 확인
            min_count = pattern.get('min_chain_length', 1)
            min_similar = pattern.get('min_count_same_source', 1)

            if len(found_components) >= min_count:
                # 시퀀스가 필요한 패턴은 연결 확인
                if pattern.get('sequence_required'):
                    if self._check_sequence(found_components, detect_components):
                        detected.append({
                            'pattern_id': pattern_id,
                            'pattern_name': pattern['name'],
                            'description': pattern['description_ko'],
                            'affected_guids': found_components,
                            'component_count': len(found_components)
                        })
                else:
                    detected.append({
                        'pattern_id': pattern_id,
                        'pattern_name': pattern['name'],
                        'description': pattern['description_ko'],
                        'affected_guids': found_components,
                        'component_count': len(found_components)
                    })

        return detected

    def suggest_alternatives(self, pattern_type: str = None) -> List[AlternativeApproach]:
        """
        대안 제안 생성

        Args:
            pattern_type: 특정 패턴 타입 (None이면 모든 패턴 검사)

        Returns:
            AlternativeApproach 리스트
        """
        suggestions = []

        if pattern_type:
            patterns_to_check = {pattern_type: self.PATTERN_ALTERNATIVES.get(pattern_type)}
            if not patterns_to_check[pattern_type]:
                return suggestions
        else:
            patterns_to_check = self.PATTERN_ALTERNATIVES

        detected = self.detect_improvable_patterns()

        for detection in detected:
            pattern_id = detection['pattern_id']

            if pattern_type and pattern_id != pattern_type:
                continue

            pattern = self.PATTERN_ALTERNATIVES.get(pattern_id)
            if not pattern:
                continue

            imp_range = pattern.get('improvement_percent', (0, 0))
            avg_improvement = (imp_range[0] + imp_range[1]) / 2

            suggestion = AlternativeApproach(
                current_pattern=pattern['name'],
                alternative_pattern=pattern['alternative_name'],
                components_affected=detection['affected_guids'],
                expected_improvement=pattern['improvement'],
                explanation=pattern['alternative_description'],
                implementation_steps=pattern['steps']
            )
            suggestions.append(suggestion)

        return suggestions

    def get_implementation_guide(self, alternative: AlternativeApproach) -> str:
        """
        대안 적용 가이드 생성

        Args:
            alternative: AlternativeApproach 객체

        Returns:
            마크다운 형식의 가이드 문자열
        """
        guide = f"""## {alternative.alternative_pattern} 적용 가이드

### 현재 상태
- **현재 패턴**: {alternative.current_pattern}
- **영향 받는 컴포넌트**: {len(alternative.components_affected)}개
- **예상 개선**: {alternative.expected_improvement}

### 왜 변경해야 하나요?
{alternative.explanation}

### 적용 단계
"""
        for i, step in enumerate(alternative.implementation_steps, 1):
            guide += f"{i}. {step}\n"

        guide += f"""
### 영향 받는 컴포넌트 GUID
```
{chr(10).join(alternative.components_affected[:10])}
{"... 외 " + str(len(alternative.components_affected) - 10) + "개" if len(alternative.components_affected) > 10 else ""}
```
"""
        return guide

    def get_all_suggestions_summary(self) -> dict:
        """
        모든 대안 제안 요약

        Returns:
            {
                'total_patterns_detected': int,
                'suggestions': [...],
                'category_advice': {...}
            }
        """
        suggestions = self.suggest_alternatives()

        # 카테고리별 조언 수집
        category_advice = {}
        for guid, comp in self._component_data.items():
            category = comp.get('category', '')
            if category in self.CATEGORY_ALTERNATIVES:
                if category not in category_advice:
                    category_advice[category] = self.CATEGORY_ALTERNATIVES[category]

        return {
            'total_patterns_detected': len(suggestions),
            'suggestions': [
                {
                    'current_pattern': s.current_pattern,
                    'alternative': s.alternative_pattern,
                    'improvement': s.expected_improvement,
                    'explanation': s.explanation,
                    'affected_count': len(s.components_affected),
                    'steps': s.implementation_steps
                }
                for s in suggestions
            ],
            'category_advice': category_advice
        }

    def _check_sequence(self, guids: List[str], component_names: List[str]) -> bool:
        """컴포넌트들이 연결된 시퀀스인지 확인"""
        if len(guids) < 2:
            return False

        # 간단한 연결 확인 (완전한 구현은 와이어 데이터 필요)
        # 여기서는 같은 이름의 컴포넌트가 2개 이상이면 패턴으로 간주
        return True

    def _build_adjacency(self) -> Dict[str, Set[str]]:
        """와이어 연결 기반 인접 그래프 생성"""
        adj: Dict[str, Set[str]] = {}

        for wire in self._wire_connections:
            src = wire.get('source_guid', '')
            tgt = wire.get('target_guid', '')
            if src and tgt:
                if src not in adj:
                    adj[src] = set()
                adj[src].add(tgt)

        return adj


# ============================================================
# Utility Functions
# ============================================================

def create_suggester_from_canvas_data(
    components: List[dict],
    wires: List[dict] = None
) -> AlternativeSuggester:
    """
    캔버스 데이터로부터 AlternativeSuggester 생성

    Args:
        components: 컴포넌트 정보 리스트
        wires: 와이어 연결 정보 리스트

    Returns:
        설정된 AlternativeSuggester 인스턴스
    """
    suggester = AlternativeSuggester()

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

    suggester.set_component_data(comp_data)

    if wires:
        suggester.set_wire_connections(wires)

    return suggester
