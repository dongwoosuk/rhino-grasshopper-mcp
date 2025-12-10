"""
GH Analyzer Mentoring Module
=============================

AI 멘토링 피드백을 위한 분석 모듈

Features:
- Performance Prediction (성능 예측)
- Alternative Logic Suggestion (대안 로직 제안)
- Auto Grouping (자동 그룹화)
- Component Highlighting (컴포넌트 시각화)
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Set, Any

# ============================================================
# Shared Data Types
# ============================================================

@dataclass
class ComponentInfo:
    """Standard component information"""
    guid: str
    name: str
    nickname: str
    category: str
    subcategory: str
    position: Tuple[float, float]


@dataclass
class WireConnection:
    """Wire connection between components"""
    source_guid: str
    source_param_index: int
    target_guid: str
    target_param_index: int


@dataclass
class PerformanceMetrics:
    """Performance metrics for a component or group"""
    execution_time_ms: float
    percentage_of_total: float
    iteration_count: int


# ============================================================
# Performance Prediction Types
# ============================================================

@dataclass
class OptimizationPrediction:
    """Prediction result for a potential optimization"""
    optimization_type: str           # e.g., "disable_preview", "add_data_dam"
    target_components: List[str]     # GUIDs of affected components
    current_time_ms: float           # Current execution time
    predicted_time_ms: float         # Predicted time after optimization
    improvement_percent: float       # Expected improvement (0-100)
    confidence: float                # 0.0-1.0 confidence level
    effort_level: str                # "low", "medium", "high"
    description: str                 # Human-readable description
    steps: List[str]                 # Implementation steps


# ============================================================
# Alternative Logic Types
# ============================================================

@dataclass
class AlternativeApproach:
    """Alternative approach suggestion"""
    current_pattern: str             # Current pattern being used
    alternative_pattern: str         # Suggested alternative
    components_affected: List[str]   # GUIDs of affected components
    expected_improvement: str        # "faster", "cleaner", "more_flexible"
    explanation: str                 # Why this is better
    implementation_steps: List[str]  # How to apply


# ============================================================
# Auto Grouping Types
# ============================================================

@dataclass
class FunctionalCluster:
    """A detected functional cluster"""
    component_guids: List[str]
    suggested_name: str
    suggested_color: Tuple[int, int, int]  # RGB
    function_type: str               # "input", "transform", "output", "calculation"
    confidence: float
    boundary_rect: Optional[Tuple[float, float, float, float]] = None  # x, y, width, height


@dataclass
class GroupingRecommendation:
    """Complete grouping recommendation"""
    clusters: List[FunctionalCluster]
    layout_suggestions: List[str]
    color_scheme: Dict[str, Tuple[int, int, int]]
    ungrouped_count: int


# ============================================================
# Component Highlighting Types
# ============================================================

@dataclass
class HighlightRequest:
    """Request to highlight components"""
    component_guids: List[str]
    color: Tuple[int, int, int]      # RGB
    context: str                      # "problem", "suggestion", "optimized", "reference"
    duration_ms: int = 0              # 0 = permanent until cleared
    label: Optional[str] = None       # Optional label to display


# ============================================================
# Module Exports
# ============================================================

__all__ = [
    # Shared types
    'ComponentInfo',
    'WireConnection',
    'PerformanceMetrics',
    # Performance prediction
    'OptimizationPrediction',
    # Alternative logic
    'AlternativeApproach',
    # Auto grouping
    'FunctionalCluster',
    'GroupingRecommendation',
    # Highlighting
    'HighlightRequest',
]
