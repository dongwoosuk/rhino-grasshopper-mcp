"""
Persistent Layout Learner
=========================

영속적 ML 레이아웃 학습 시스템

Features:
- 학습 결과를 JSON 파일로 영속 저장
- 다중 GH 정의에서 누적 학습
- 패턴 가중치 최적화 (자주 사용되는 패턴에 높은 가중치)
- 학습 히스토리 관리
- 학습된 패턴 기반 레이아웃 적용
- **컴포넌트 타입 분류** (InputParam, OutputParam, Geometry, Math, Transform 등)
- **연결 유형별 간격 패턴** (Param→Comp, Comp→Comp, Comp→Param)
- **와이어 교차 최소화** (Barycenter + Adjacent Swap)
- **Y순서 ML 학습** (사용자 레이아웃 패턴 학습)

Usage:
    learner = PersistentLayoutLearner()
    learner.learn_from_canvas(components, wires, source_file="my_definition.gh")
    learner.save()

    # Later...
    learner = PersistentLayoutLearner()
    learner.load()
    position = learner.get_optimal_position("Addition", connected_to_guid)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum
import math

# Wire crossing minimization imports
_crossing_modules_available = False
try:
    from .wire_crossing_detector import Wire, WireCrossingDetector, get_crossing_detector
    from .y_order_learner import YOrderLearner, get_y_order_learner
    from .crossing_minimizer import CrossingMinimizer, get_crossing_minimizer
    _crossing_modules_available = True
except ImportError:
    pass


# ============================================================
# Component Type Classification (컴포넌트 타입 분류)
# ============================================================

class ComponentType(Enum):
    """컴포넌트 타입 분류 (15개 세분화)"""
    # 입출력 파라미터
    INPUT_PARAM = "input_param"           # 입력 파라미터 (Number Slider, Boolean Toggle)
    OUTPUT_PARAM = "output_param"         # 출력 파라미터 (Panel output, Data Recorder)
    DATA_PARAM = "data_param"             # 중간 데이터 전달 (Relay, Data)

    # 지오메트리 (세분화)
    GEOMETRY_PRIMITIVE = "geom_prim"      # 기본 지오메트리 (Point, Line, Circle, Arc)
    GEOMETRY_SURFACE = "geom_surf"        # 서피스 (Surface, Brep, Loft, Sweep)
    GEOMETRY_MESH = "geom_mesh"           # 메쉬 (Mesh, Mesh Box, Mesh Sphere)

    # 수학 연산 (세분화)
    MATH_BASIC = "math_basic"             # 기본 연산 (+, -, *, /, Expression)
    MATH_DOMAIN = "math_domain"           # 도메인 연산 (Domain, Remap, Range, Series)
    MATH_TRIG = "math_trig"               # 삼각함수 (Sin, Cos, Tan)

    # 데이터 조작
    LIST_ACCESS = "list_access"           # 리스트 접근 (List Item, First, Last)
    LIST_MODIFY = "list_modify"           # 리스트 수정 (Replace, Insert, Cull)
    TREE_MODIFY = "tree_modify"           # 트리 연산 (Flatten, Graft, Explode Tree)

    # 변환/로직
    TRANSFORM = "transform"               # 변환 (Move, Rotate, Scale, Mirror)
    LOGIC = "logic"                       # 논리 연산 (Gate, Equality, Larger Than)
    UTIL = "util"                         # 유틸리티 (Stream Filter, Data Dam)
    UNKNOWN = "unknown"


class ClusterShape(Enum):
    """클러스터 형태 분류 (v9 레이아웃용)"""
    HORIZONTAL_FLOW = "horizontal"    # 좌→우 직선 흐름 (A→B→C)
    BRANCHING = "branching"           # 1→N 분기 (한 소스에서 여러 타겟)
    MERGING = "merging"               # N→1 병합 (여러 소스가 한 타겟)
    DIAMOND = "diamond"               # 분기 후 병합 (다이아몬드 형태)
    COMPLEX = "complex"               # 복합 구조


# 컴포넌트 이름 → 타입 매핑 (세분화된 15개 타입 사용)
COMPONENT_TYPE_MAP = {
    # =========================================================================
    # INPUT_PARAM - 입력 파라미터 (항상 입력 역할)
    # =========================================================================
    "Number Slider": ComponentType.INPUT_PARAM,
    "Panel": ComponentType.INPUT_PARAM,  # 동적 분류 함수에서 연결 기반으로 재판정
    "Boolean Toggle": ComponentType.INPUT_PARAM,
    "Value List": ComponentType.INPUT_PARAM,
    "MD Slider": ComponentType.INPUT_PARAM,
    "Digit Scroller": ComponentType.INPUT_PARAM,
    "Colour Swatch": ComponentType.INPUT_PARAM,
    "Gradient": ComponentType.INPUT_PARAM,
    "Graph Mapper": ComponentType.INPUT_PARAM,
    "Image Sampler": ComponentType.INPUT_PARAM,

    # DATA_PARAM - 데이터 파라미터 (동적 분류에서 재판정됨)
    "Point": ComponentType.DATA_PARAM,
    "Curve": ComponentType.DATA_PARAM,
    "Surface": ComponentType.DATA_PARAM,
    "Brep": ComponentType.DATA_PARAM,
    "Mesh": ComponentType.DATA_PARAM,
    "Geometry": ComponentType.DATA_PARAM,
    "Integer": ComponentType.DATA_PARAM,
    "Number": ComponentType.DATA_PARAM,
    "Text": ComponentType.DATA_PARAM,
    "Data": ComponentType.DATA_PARAM,
    "Relay": ComponentType.DATA_PARAM,

    # OUTPUT_PARAM - 출력 파라미터 (항상 출력 역할)
    "Data Recorder": ComponentType.OUTPUT_PARAM,
    "Param Viewer": ComponentType.OUTPUT_PARAM,

    # =========================================================================
    # GEOMETRY_PRIMITIVE - 기본 지오메트리 (Point, Line, Circle, Arc 등)
    # =========================================================================
    "Circle": ComponentType.GEOMETRY_PRIMITIVE,
    "Circle CNR": ComponentType.GEOMETRY_PRIMITIVE,
    "Arc": ComponentType.GEOMETRY_PRIMITIVE,
    "Arc 3Pt": ComponentType.GEOMETRY_PRIMITIVE,
    "Line": ComponentType.GEOMETRY_PRIMITIVE,
    "Line SDL": ComponentType.GEOMETRY_PRIMITIVE,
    "Polyline": ComponentType.GEOMETRY_PRIMITIVE,
    "Rectangle": ComponentType.GEOMETRY_PRIMITIVE,
    "Polygon": ComponentType.GEOMETRY_PRIMITIVE,
    "Construct Point": ComponentType.GEOMETRY_PRIMITIVE,
    "Deconstruct Point": ComponentType.GEOMETRY_PRIMITIVE,
    "Pt": ComponentType.GEOMETRY_PRIMITIVE,
    "Plane": ComponentType.GEOMETRY_PRIMITIVE,
    "XY Plane": ComponentType.GEOMETRY_PRIMITIVE,
    "XZ Plane": ComponentType.GEOMETRY_PRIMITIVE,
    "YZ Plane": ComponentType.GEOMETRY_PRIMITIVE,

    # =========================================================================
    # GEOMETRY_SURFACE - 서피스/Brep (Loft, Sweep, Extrude 등)
    # =========================================================================
    "Sphere": ComponentType.GEOMETRY_SURFACE,
    "Box": ComponentType.GEOMETRY_SURFACE,
    "Cylinder": ComponentType.GEOMETRY_SURFACE,
    "Cone": ComponentType.GEOMETRY_SURFACE,
    "Extrude": ComponentType.GEOMETRY_SURFACE,
    "Loft": ComponentType.GEOMETRY_SURFACE,
    "Sweep1": ComponentType.GEOMETRY_SURFACE,
    "Sweep2": ComponentType.GEOMETRY_SURFACE,
    "Pipe": ComponentType.GEOMETRY_SURFACE,
    "Cap Holes": ComponentType.GEOMETRY_SURFACE,
    "Boundary Surface": ComponentType.GEOMETRY_SURFACE,
    "Solid Union": ComponentType.GEOMETRY_SURFACE,
    "Solid Difference": ComponentType.GEOMETRY_SURFACE,
    "Solid Intersection": ComponentType.GEOMETRY_SURFACE,
    "Region Union": ComponentType.GEOMETRY_SURFACE,
    "Region Difference": ComponentType.GEOMETRY_SURFACE,

    # =========================================================================
    # GEOMETRY_MESH - 메쉬 관련
    # =========================================================================
    "Mesh Box": ComponentType.GEOMETRY_MESH,
    "Mesh Sphere": ComponentType.GEOMETRY_MESH,
    "Mesh Surface": ComponentType.GEOMETRY_MESH,
    "Mesh Brep": ComponentType.GEOMETRY_MESH,
    "Mesh Join": ComponentType.GEOMETRY_MESH,
    "Mesh Split": ComponentType.GEOMETRY_MESH,
    "Deconstruct Mesh": ComponentType.GEOMETRY_MESH,
    "Construct Mesh": ComponentType.GEOMETRY_MESH,
    "Mesh Faces": ComponentType.GEOMETRY_MESH,
    "Mesh Vertices": ComponentType.GEOMETRY_MESH,

    # =========================================================================
    # MATH_BASIC - 기본 연산 (+, -, *, /, Expression)
    # =========================================================================
    "Addition": ComponentType.MATH_BASIC,
    "Subtraction": ComponentType.MATH_BASIC,
    "Multiplication": ComponentType.MATH_BASIC,
    "Division": ComponentType.MATH_BASIC,
    "Negative": ComponentType.MATH_BASIC,
    "Absolute": ComponentType.MATH_BASIC,
    "Power": ComponentType.MATH_BASIC,
    "Square Root": ComponentType.MATH_BASIC,
    "Modulus": ComponentType.MATH_BASIC,
    "Pi": ComponentType.MATH_BASIC,
    "Expression": ComponentType.MATH_BASIC,
    "Evaluate": ComponentType.MATH_BASIC,
    "Mass Addition": ComponentType.MATH_BASIC,
    "Average": ComponentType.MATH_BASIC,
    "Minimum": ComponentType.MATH_BASIC,
    "Maximum": ComponentType.MATH_BASIC,
    "Round": ComponentType.MATH_BASIC,
    "Truncate": ComponentType.MATH_BASIC,
    "Ceiling": ComponentType.MATH_BASIC,
    "Floor": ComponentType.MATH_BASIC,

    # =========================================================================
    # MATH_TRIG - 삼각함수 (Sin, Cos, Tan)
    # =========================================================================
    "Sine": ComponentType.MATH_TRIG,
    "Cosine": ComponentType.MATH_TRIG,
    "Tangent": ComponentType.MATH_TRIG,
    "ArcSine": ComponentType.MATH_TRIG,
    "ArcCosine": ComponentType.MATH_TRIG,
    "ArcTangent": ComponentType.MATH_TRIG,

    # =========================================================================
    # MATH_DOMAIN - 도메인 연산 (Domain, Remap, Range, Series)
    # =========================================================================
    "Domain": ComponentType.MATH_DOMAIN,
    "Construct Domain": ComponentType.MATH_DOMAIN,
    "Deconstruct Domain": ComponentType.MATH_DOMAIN,
    "Remap Numbers": ComponentType.MATH_DOMAIN,
    "Bounds": ComponentType.MATH_DOMAIN,
    "Range": ComponentType.MATH_DOMAIN,
    "Series": ComponentType.MATH_DOMAIN,
    "Random": ComponentType.MATH_DOMAIN,
    "Jitter": ComponentType.MATH_DOMAIN,
    "Fibonacci": ComponentType.MATH_DOMAIN,

    # TRANSFORM - 변환
    "Move": ComponentType.TRANSFORM,
    "Rotate": ComponentType.TRANSFORM,
    "Rotate Axis": ComponentType.TRANSFORM,
    "Scale": ComponentType.TRANSFORM,
    "Scale NU": ComponentType.TRANSFORM,
    "Mirror": ComponentType.TRANSFORM,
    "Orient": ComponentType.TRANSFORM,
    "Project": ComponentType.TRANSFORM,
    "Offset Curve": ComponentType.TRANSFORM,
    "Offset Surface": ComponentType.TRANSFORM,
    "Array": ComponentType.TRANSFORM,
    "Linear Array": ComponentType.TRANSFORM,
    "Rectangular Array": ComponentType.TRANSFORM,
    "Polar Array": ComponentType.TRANSFORM,
    "Box Morph": ComponentType.TRANSFORM,
    "Surface Morph": ComponentType.TRANSFORM,
    "Twist": ComponentType.TRANSFORM,
    "Bend": ComponentType.TRANSFORM,
    "Shear": ComponentType.TRANSFORM,

    # =========================================================================
    # LIST_ACCESS - 리스트 접근 (List Item, First, Last)
    # =========================================================================
    "List Item": ComponentType.LIST_ACCESS,
    "List Length": ComponentType.LIST_ACCESS,
    "First Item": ComponentType.LIST_ACCESS,
    "Last Item": ComponentType.LIST_ACCESS,
    "Null Item": ComponentType.LIST_ACCESS,
    "Tree Item": ComponentType.LIST_ACCESS,
    "Tree Branch": ComponentType.LIST_ACCESS,
    "Relative Item": ComponentType.LIST_ACCESS,
    "Pick'n'Choose": ComponentType.LIST_ACCESS,
    "Item Index": ComponentType.LIST_ACCESS,
    "Member Index": ComponentType.LIST_ACCESS,

    # =========================================================================
    # LIST_MODIFY - 리스트 수정 (Replace, Insert, Cull)
    # =========================================================================
    "Reverse List": ComponentType.LIST_MODIFY,
    "Shift List": ComponentType.LIST_MODIFY,
    "Sort List": ComponentType.LIST_MODIFY,
    "Partition List": ComponentType.LIST_MODIFY,
    "Split List": ComponentType.LIST_MODIFY,
    "Cull Pattern": ComponentType.LIST_MODIFY,
    "Cull Index": ComponentType.LIST_MODIFY,
    "Cull Nth": ComponentType.LIST_MODIFY,
    "Dispatch": ComponentType.LIST_MODIFY,
    "Sift Pattern": ComponentType.LIST_MODIFY,
    "Replace Items": ComponentType.LIST_MODIFY,
    "Insert Items": ComponentType.LIST_MODIFY,
    "Merge": ComponentType.LIST_MODIFY,
    "Entwine": ComponentType.LIST_MODIFY,
    "Cross Reference": ComponentType.LIST_MODIFY,
    "Longest List": ComponentType.LIST_MODIFY,
    "Shortest List": ComponentType.LIST_MODIFY,
    "Clean Tree": ComponentType.LIST_MODIFY,
    "Repeat Data": ComponentType.LIST_MODIFY,
    "Duplicate Data": ComponentType.LIST_MODIFY,
    "Sequence": ComponentType.LIST_MODIFY,
    "Stack Data": ComponentType.LIST_MODIFY,
    "Concatenate": ComponentType.LIST_MODIFY,

    # =========================================================================
    # TREE_MODIFY - 트리 연산 (Flatten, Graft, Explode Tree)
    # =========================================================================
    "Flatten": ComponentType.TREE_MODIFY,
    "Flatten Tree": ComponentType.TREE_MODIFY,
    "Graft": ComponentType.TREE_MODIFY,
    "Graft Tree": ComponentType.TREE_MODIFY,
    "Simplify Tree": ComponentType.TREE_MODIFY,
    "Unflatten": ComponentType.TREE_MODIFY,
    "Path Mapper": ComponentType.TREE_MODIFY,
    "Explode Tree": ComponentType.TREE_MODIFY,
    "Trim Tree": ComponentType.TREE_MODIFY,
    "Prune Tree": ComponentType.TREE_MODIFY,
    "Tree Statistics": ComponentType.TREE_MODIFY,
    "Flip Matrix": ComponentType.TREE_MODIFY,
    "Match Tree": ComponentType.TREE_MODIFY,
    "Replace Paths": ComponentType.TREE_MODIFY,
    "Split Tree": ComponentType.TREE_MODIFY,
    "Construct Path": ComponentType.TREE_MODIFY,
    "Deconstruct Path": ComponentType.TREE_MODIFY,

    # =========================================================================
    # LOGIC - 논리 연산
    # =========================================================================
    "Gate And": ComponentType.LOGIC,
    "Gate Or": ComponentType.LOGIC,
    "Gate Not": ComponentType.LOGIC,
    "Gate Xor": ComponentType.LOGIC,
    "Equality": ComponentType.LOGIC,
    "Similarity": ComponentType.LOGIC,
    "Larger Than": ComponentType.LOGIC,
    "Smaller Than": ComponentType.LOGIC,
    "Mass Or": ComponentType.LOGIC,
    "Mass And": ComponentType.LOGIC,

    # =========================================================================
    # UTIL - 유틸리티 (Stream Filter, Data Dam 등)
    # =========================================================================
    "Stream Filter": ComponentType.UTIL,
    "Stream Gate": ComponentType.UTIL,
    "Data Dam": ComponentType.UTIL,
    "Trigger": ComponentType.UTIL,
    "Timer": ComponentType.UTIL,
    "Button": ComponentType.UTIL,
    "Cluster": ComponentType.UTIL,
    "Group": ComponentType.UTIL,
    "Subroutine": ComponentType.UTIL,
    "Scribble": ComponentType.UTIL,
    "Jump": ComponentType.UTIL,
    "Populate 2D": ComponentType.UTIL,
    "Populate 3D": ComponentType.UTIL,
    "Populate Geometry": ComponentType.UTIL,

    # =========================================================================
    # 누락된 기본 GH 컴포넌트
    # =========================================================================

    # Vector - 벡터 연산
    "Vector 2Pt": ComponentType.GEOMETRY_PRIMITIVE,
    "Vector XYZ": ComponentType.GEOMETRY_PRIMITIVE,
    "Unit X": ComponentType.GEOMETRY_PRIMITIVE,
    "Unit Y": ComponentType.GEOMETRY_PRIMITIVE,
    "Unit Z": ComponentType.GEOMETRY_PRIMITIVE,
    "Vector Length": ComponentType.MATH_BASIC,
    "Amplitude": ComponentType.TRANSFORM,
    "Dot Product": ComponentType.MATH_BASIC,
    "Cross Product": ComponentType.MATH_BASIC,
    "Angle": ComponentType.MATH_BASIC,
    "Deconstruct Vector": ComponentType.GEOMETRY_PRIMITIVE,
    "Reverse": ComponentType.TRANSFORM,
    "Rotate Vector": ComponentType.TRANSFORM,

    # Display - 시각화
    "Colour RGB": ComponentType.OUTPUT_PARAM,
    "Colour HSL": ComponentType.OUTPUT_PARAM,
    "Colour CMYK": ComponentType.OUTPUT_PARAM,
    "Custom Preview": ComponentType.OUTPUT_PARAM,
    "Preview": ComponentType.OUTPUT_PARAM,
    "Point List": ComponentType.OUTPUT_PARAM,
    "Gradient": ComponentType.INPUT_PARAM,

    # Curve Analysis
    "Length": ComponentType.MATH_BASIC,
    "Area": ComponentType.MATH_BASIC,
    "Volume": ComponentType.MATH_BASIC,
    "Curvature": ComponentType.MATH_BASIC,
    "Evaluate Curve": ComponentType.MATH_BASIC,
    "Evaluate Surface": ComponentType.MATH_BASIC,
    "Deconstruct Brep": ComponentType.GEOMETRY_SURFACE,
    "Brep | Plane": ComponentType.GEOMETRY_SURFACE,
    "Curve | Curve": ComponentType.GEOMETRY_PRIMITIVE,
    "Curve | Plane": ComponentType.GEOMETRY_PRIMITIVE,
    "Surface | Curve": ComponentType.GEOMETRY_SURFACE,

    # Curve Util
    "Extend Curve": ComponentType.TRANSFORM,
    "Trim with Region": ComponentType.TRANSFORM,
    "Trim with Regions": ComponentType.TRANSFORM,
    "Fillet": ComponentType.GEOMETRY_PRIMITIVE,
    "Offset": ComponentType.TRANSFORM,
    "Divide Curve": ComponentType.MATH_DOMAIN,
    "Divide Length": ComponentType.MATH_DOMAIN,
    "Divide Distance": ComponentType.MATH_DOMAIN,
    "Shatter": ComponentType.LIST_MODIFY,
    "Explode": ComponentType.LIST_MODIFY,
    "Join Curves": ComponentType.GEOMETRY_PRIMITIVE,

    # Surface
    "Center Box": ComponentType.GEOMETRY_SURFACE,
    "Bounding Box": ComponentType.GEOMETRY_SURFACE,
    "Deconstruct Box": ComponentType.GEOMETRY_SURFACE,
    "Box 2Pt": ComponentType.GEOMETRY_SURFACE,
    "Domain Box": ComponentType.GEOMETRY_SURFACE,

    # Script
    "Python 3 Script": ComponentType.MATH_BASIC,
    "GhPython Script": ComponentType.MATH_BASIC,
    "C# Script": ComponentType.MATH_BASIC,
    "VB Script": ComponentType.MATH_BASIC,

    # Intersect
    "Brep | Brep": ComponentType.GEOMETRY_SURFACE,
    "Mesh | Ray": ComponentType.GEOMETRY_MESH,
    "Curve | Self": ComponentType.GEOMETRY_PRIMITIVE,
    "Multiple Curves": ComponentType.GEOMETRY_PRIMITIVE,
    "Point In Curve": ComponentType.LOGIC,
    "Point In Brep": ComponentType.LOGIC,
    "Point In Curves": ComponentType.LOGIC,
    "Point In Breps": ComponentType.LOGIC,

    # Distance
    "Distance": ComponentType.MATH_BASIC,
    "Closest Point": ComponentType.MATH_BASIC,
    "Closest Points": ComponentType.MATH_BASIC,
    "Pull Point": ComponentType.TRANSFORM,
    "Project Point": ComponentType.TRANSFORM,

    # =========================================================================
    # 플러그인 컴포넌트 - Wombat
    # =========================================================================
    "Foot Inch To Decimal Foot": ComponentType.MATH_BASIC,
    "Decimal Foot To Foot Inch": ComponentType.MATH_BASIC,
    "Divide by Target Length": ComponentType.MATH_DOMAIN,
    "Divide by Target Count": ComponentType.MATH_DOMAIN,
    "Text Tag 3D": ComponentType.OUTPUT_PARAM,
    "Curve Frame At Parameter": ComponentType.GEOMETRY_PRIMITIVE,
    "Offset Multiple": ComponentType.TRANSFORM,
    "Flip Curve": ComponentType.TRANSFORM,
    "Join Curves Ordered": ComponentType.GEOMETRY_PRIMITIVE,
    "Extend Curve Simple": ComponentType.TRANSFORM,
    "Point At Parameter": ComponentType.GEOMETRY_PRIMITIVE,
    "Evaluate Box": ComponentType.MATH_BASIC,
    "Remap Domain": ComponentType.MATH_DOMAIN,

    # =========================================================================
    # 플러그인 컴포넌트 - LunchBox
    # =========================================================================
    "Random Split List": ComponentType.LIST_MODIFY,
    "LunchBox Random": ComponentType.MATH_DOMAIN,
    "Diamond Panels": ComponentType.GEOMETRY_SURFACE,
    "Hexagon Cells": ComponentType.GEOMETRY_SURFACE,
    "Quad Panels": ComponentType.GEOMETRY_SURFACE,
    "Triangle Panels A": ComponentType.GEOMETRY_SURFACE,
    "Triangle Panels B": ComponentType.GEOMETRY_SURFACE,
    "Stagger Pattern": ComponentType.LIST_MODIFY,
    "Random Split": ComponentType.LIST_MODIFY,
    "Sort Points": ComponentType.LIST_MODIFY,
    "Create Set": ComponentType.LIST_MODIFY,
    "Set Difference": ComponentType.LIST_MODIFY,
    "Set Intersection": ComponentType.LIST_MODIFY,
    "Set Union": ComponentType.LIST_MODIFY,
    "Excel Read": ComponentType.INPUT_PARAM,
    "Excel Write": ComponentType.OUTPUT_PARAM,

    # =========================================================================
    # 플러그인 컴포넌트 - Elefront
    # =========================================================================
    "EF Data Description (R6)": ComponentType.INPUT_PARAM,
    "Bake Objects (R6)": ComponentType.OUTPUT_PARAM,
    "Bake Objects": ComponentType.OUTPUT_PARAM,
    "Define Object Attributes (R6)": ComponentType.UTIL,
    "Define Object Attributes": ComponentType.UTIL,
    "Define Layer (R6)": ComponentType.UTIL,
    "Define Layer": ComponentType.UTIL,
    "Reference by Layer": ComponentType.INPUT_PARAM,
    "Reference by Type": ComponentType.INPUT_PARAM,
    "Reference by Name": ComponentType.INPUT_PARAM,
    "Deconstruct Attributes": ComponentType.UTIL,
    "Get User Keys": ComponentType.UTIL,
    "Get User Values": ComponentType.UTIL,
    "Filter by Key-Value": ComponentType.LIST_ACCESS,
    "Key-Value Search": ComponentType.LIST_ACCESS,

    # =========================================================================
    # 플러그인 컴포넌트 - Pufferfish
    # =========================================================================
    "List Indices": ComponentType.LIST_ACCESS,
    "Tween Through Curves": ComponentType.GEOMETRY_PRIMITIVE,
    "Tween Two Curves": ComponentType.GEOMETRY_PRIMITIVE,
    "Offset Curve Loose": ComponentType.TRANSFORM,
    "Offset Curve Variable": ComponentType.TRANSFORM,
    "Interpolate Data": ComponentType.MATH_DOMAIN,
    "Remap Tree": ComponentType.TREE_MODIFY,
    "Tree Branch Indices": ComponentType.TREE_MODIFY,
    "Relative Items": ComponentType.TREE_MODIFY,
    "Shift Paths": ComponentType.TREE_MODIFY,
    "Rebuild Curve Variable": ComponentType.GEOMETRY_PRIMITIVE,
    "Gradient Between Points": ComponentType.MATH_DOMAIN,

    # =========================================================================
    # 플러그인 컴포넌트 - Human / Human UI
    # =========================================================================
    "Create Window": ComponentType.OUTPUT_PARAM,
    "Value Listener": ComponentType.INPUT_PARAM,
    "Slider": ComponentType.INPUT_PARAM,
    "Button (HUI)": ComponentType.INPUT_PARAM,
    "Checkbox": ComponentType.INPUT_PARAM,
    "Dropdown": ComponentType.INPUT_PARAM,
    "Label": ComponentType.OUTPUT_PARAM,
    "Text Box": ComponentType.INPUT_PARAM,
    "Capture View": ComponentType.OUTPUT_PARAM,
    "Create Layout": ComponentType.UTIL,

    # =========================================================================
    # 플러그인 컴포넌트 - Kangaroo
    # =========================================================================
    "Solver": ComponentType.UTIL,
    "Bouncy Solver": ComponentType.UTIL,
    "Zombie Solver": ComponentType.UTIL,
    "Anchor": ComponentType.GEOMETRY_PRIMITIVE,
    "Spring": ComponentType.GEOMETRY_PRIMITIVE,
    "Length (Line)": ComponentType.GEOMETRY_PRIMITIVE,
    "Angle (Goal)": ComponentType.GEOMETRY_PRIMITIVE,
    "Floor": ComponentType.GEOMETRY_SURFACE,
    "Unary Force": ComponentType.TRANSFORM,
    "Load": ComponentType.TRANSFORM,
    "Grab": ComponentType.INPUT_PARAM,
    "Show": ComponentType.OUTPUT_PARAM,

    # =========================================================================
    # 플러그인 컴포넌트 - Ladybug / Honeybee
    # =========================================================================
    "LB Import EPW": ComponentType.INPUT_PARAM,
    "LB Sunpath": ComponentType.GEOMETRY_PRIMITIVE,
    "LB Sun": ComponentType.GEOMETRY_PRIMITIVE,
    "LB Radiation Rose": ComponentType.OUTPUT_PARAM,
    "LB Wind Rose": ComponentType.OUTPUT_PARAM,
    "LB Legend Parameters": ComponentType.UTIL,
    "HB Room": ComponentType.GEOMETRY_SURFACE,
    "HB Face": ComponentType.GEOMETRY_SURFACE,
    "HB Shade": ComponentType.GEOMETRY_SURFACE,
    "HB Model": ComponentType.GEOMETRY_SURFACE,
    "HB Visualize All": ComponentType.OUTPUT_PARAM,

    # =========================================================================
    # 플러그인 컴포넌트 - Heteroptera
    # =========================================================================
    "List Match": ComponentType.LIST_MODIFY,
    "Text Split": ComponentType.LIST_MODIFY,
    "Text Replace": ComponentType.UTIL,
    "Text Contains": ComponentType.LOGIC,
    "Number to Text": ComponentType.UTIL,
    "Text to Number": ComponentType.UTIL,

    # =========================================================================
    # 플러그인 컴포넌트 - Anemone
    # =========================================================================
    "Loop Start": ComponentType.UTIL,
    "Loop End": ComponentType.UTIL,
    "Anemone": ComponentType.UTIL,

    # =========================================================================
    # 플러그인 컴포넌트 - Metahopper
    # =========================================================================
    "Get All Objects": ComponentType.INPUT_PARAM,
    "Get All Wires": ComponentType.INPUT_PARAM,
    "Cluster Input": ComponentType.INPUT_PARAM,
    "Cluster Output": ComponentType.OUTPUT_PARAM,
    "Enable Object": ComponentType.UTIL,
    "Disable Object": ComponentType.UTIL,
    "Create Cluster": ComponentType.UTIL,
    "Explode Cluster": ComponentType.UTIL,

    # =========================================================================
    # Rhino 8 - 새 컴포넌트
    # =========================================================================
    "Model Hatch": ComponentType.OUTPUT_PARAM,
    "Hatch": ComponentType.OUTPUT_PARAM,
    "Text Entity": ComponentType.OUTPUT_PARAM,
    "Dimension": ComponentType.OUTPUT_PARAM,
    "Leader": ComponentType.OUTPUT_PARAM,
    "SubD": ComponentType.GEOMETRY_SURFACE,
    "SubD from Mesh": ComponentType.GEOMETRY_SURFACE,
    "Mesh from SubD": ComponentType.GEOMETRY_MESH,
    "SubD Edges": ComponentType.GEOMETRY_SURFACE,
    "SubD Faces": ComponentType.GEOMETRY_SURFACE,
    "SubD Vertices": ComponentType.GEOMETRY_SURFACE,
}

# 카테고리 → 기본 타입 매핑 (컴포넌트 이름이 없을 때 폴백)
# 새로운 세분화된 타입 사용
CATEGORY_TYPE_MAP = {
    # Params 카테고리
    "Params": ComponentType.DATA_PARAM,
    "Input": ComponentType.INPUT_PARAM,
    "Primitive": ComponentType.INPUT_PARAM,
    "Geometry": ComponentType.DATA_PARAM,  # Params > Geometry (참조 파라미터)

    # Maths 카테고리
    "Maths": ComponentType.MATH_BASIC,
    "Operators": ComponentType.MATH_BASIC,
    "Script": ComponentType.MATH_BASIC,
    "Polynomials": ComponentType.MATH_BASIC,
    "Trig": ComponentType.MATH_TRIG,
    "Domain": ComponentType.MATH_DOMAIN,
    "Matrix": ComponentType.MATH_BASIC,
    "Time": ComponentType.MATH_DOMAIN,

    # Transform 카테고리
    "Transform": ComponentType.TRANSFORM,
    "Euclidean": ComponentType.TRANSFORM,
    "Affine": ComponentType.TRANSFORM,
    "Morph": ComponentType.TRANSFORM,
    "Array": ComponentType.TRANSFORM,

    # Curve 카테고리
    "Curve": ComponentType.GEOMETRY_PRIMITIVE,
    "Analysis": ComponentType.MATH_BASIC,  # Curve/Surface > Analysis
    "Division": ComponentType.MATH_DOMAIN,
    "Spline": ComponentType.GEOMETRY_PRIMITIVE,

    # Surface 카테고리
    "Surface": ComponentType.GEOMETRY_SURFACE,
    "Freeform": ComponentType.GEOMETRY_SURFACE,
    "SubD": ComponentType.GEOMETRY_SURFACE,

    # Mesh 카테고리
    "Mesh": ComponentType.GEOMETRY_MESH,
    "Triangulation": ComponentType.GEOMETRY_MESH,

    # Intersect 카테고리
    "Intersect": ComponentType.GEOMETRY_SURFACE,
    "Mathematical": ComponentType.GEOMETRY_SURFACE,
    "Physical": ComponentType.GEOMETRY_SURFACE,
    "Region": ComponentType.GEOMETRY_SURFACE,
    "Shape": ComponentType.GEOMETRY_SURFACE,

    # Vector 카테고리
    "Vector": ComponentType.GEOMETRY_PRIMITIVE,
    "Point": ComponentType.GEOMETRY_PRIMITIVE,
    "Plane": ComponentType.GEOMETRY_PRIMITIVE,
    "Grid": ComponentType.GEOMETRY_PRIMITIVE,

    # Sets 카테고리
    "Sets": ComponentType.LIST_MODIFY,
    "List": ComponentType.LIST_ACCESS,
    "Sequence": ComponentType.LIST_MODIFY,
    "Tree": ComponentType.TREE_MODIFY,
    "Text": ComponentType.LIST_MODIFY,

    # Logic
    "Boolean": ComponentType.LOGIC,

    # Util
    "Util": ComponentType.UTIL,

    # Display 카테고리
    "Display": ComponentType.OUTPUT_PARAM,
    "Colour": ComponentType.OUTPUT_PARAM,
    "Preview": ComponentType.OUTPUT_PARAM,
    "Dimensions": ComponentType.OUTPUT_PARAM,
    "Drafting": ComponentType.OUTPUT_PARAM,

    # Rhino 카테고리
    "Rhino": ComponentType.OUTPUT_PARAM,

    # =========================================================================
    # 플러그인 카테고리
    # =========================================================================

    # Elefront
    "Elefront (R6)": ComponentType.UTIL,
    "Elefront": ComponentType.UTIL,
    "06 Bake": ComponentType.OUTPUT_PARAM,
    "03 Attributes": ComponentType.UTIL,
    "08 Params": ComponentType.INPUT_PARAM,

    # Wombat
    "Wombat": ComponentType.MATH_BASIC,
    "Document": ComponentType.MATH_BASIC,

    # LunchBox
    "LunchBox": ComponentType.UTIL,

    # Pufferfish
    "Pufferfish": ComponentType.UTIL,

    # Kangaroo
    "Kangaroo": ComponentType.UTIL,
    "Kangaroo2": ComponentType.UTIL,

    # Ladybug / Honeybee
    "Ladybug": ComponentType.UTIL,
    "Honeybee": ComponentType.UTIL,
    "LB-Legacy": ComponentType.UTIL,
    "HB-Legacy": ComponentType.UTIL,

    # Human / Human UI
    "Human": ComponentType.OUTPUT_PARAM,
    "Human UI": ComponentType.OUTPUT_PARAM,

    # Heteroptera
    "Heteroptera": ComponentType.UTIL,

    # Anemone
    "Anemone": ComponentType.UTIL,

    # Metahopper
    "Metahopper": ComponentType.UTIL,

    # TreeSloth
    "TreeSloth": ComponentType.TREE_MODIFY,

    # Bifocals
    "Bifocals": ComponentType.OUTPUT_PARAM,

    # OpenNest
    "OpenNest": ComponentType.TRANSFORM,

    # Clipper
    "Clipper": ComponentType.GEOMETRY_PRIMITIVE,
}


def classify_component_type(
    name: str,
    category: str = "",
    subcategory: str = "",
    has_inputs: bool = True,
    has_outputs: bool = True
) -> ComponentType:
    """
    컴포넌트 이름과 카테고리로 타입 분류

    Args:
        name: 컴포넌트 이름
        category: 카테고리 (예: "Params", "Maths")
        subcategory: 서브카테고리
        has_inputs: 입력 파라미터 유무
        has_outputs: 출력 파라미터 유무

    Returns:
        ComponentType enum
    """
    # 1. 이름으로 직접 매칭
    if name in COMPONENT_TYPE_MAP:
        comp_type = COMPONENT_TYPE_MAP[name]

        # Panel 특별 처리: 출력만 있으면 OUTPUT_PARAM
        if name == "Panel" and not has_inputs:
            return ComponentType.OUTPUT_PARAM

        return comp_type

    # 2. 카테고리로 매칭
    if category in CATEGORY_TYPE_MAP:
        return CATEGORY_TYPE_MAP[category]

    if subcategory in CATEGORY_TYPE_MAP:
        return CATEGORY_TYPE_MAP[subcategory]

    # 3. 휴리스틱: 입출력 구조로 추론
    if not has_inputs and has_outputs:
        return ComponentType.INPUT_PARAM
    elif has_inputs and not has_outputs:
        return ComponentType.OUTPUT_PARAM

    return ComponentType.UNKNOWN


def classify_by_connection(
    guid: str,
    incoming: Dict[str, Set[str]],
    outgoing: Dict[str, Set[str]],
    comp_map: Dict[str, Dict]
) -> ComponentType:
    """
    연결 방향 기반으로 컴포넌트 타입 동적 분류

    Panel 같은 파라미터 컴포넌트는 연결 방향에 따라:
    - 입력만 받음 (출력 확인용) → OUTPUT_PARAM
    - 출력만 함 (입력용) → INPUT_PARAM
    - 둘 다 → UTIL (중간 연결)

    Args:
        guid: 컴포넌트 GUID
        incoming: {guid: set of source guids} - 이 컴포넌트로 들어오는 연결
        outgoing: {guid: set of target guids} - 이 컴포넌트에서 나가는 연결
        comp_map: {guid: component_data} - 컴포넌트 데이터

    Returns:
        ComponentType enum
    """
    comp = comp_map.get(guid, {})
    name = comp.get('name', '')
    category = comp.get('category', '')
    subcategory = comp.get('subcategory', '')

    has_incoming = len(incoming.get(guid, set())) > 0
    has_outgoing = len(outgoing.get(guid, set())) > 0

    # 파라미터 컴포넌트 목록 (연결 방향에 따라 역할이 바뀔 수 있는 컴포넌트들)
    DYNAMIC_PARAM_COMPONENTS = {
        "Panel", "Point", "Curve", "Surface", "Brep", "Mesh", "Geometry",
        "Integer", "Number", "Text", "Data", "Boolean"
    }

    # Panel 및 동적 파라미터 컴포넌트 특수 처리
    if name in DYNAMIC_PARAM_COMPONENTS:
        if has_incoming and not has_outgoing:
            return ComponentType.OUTPUT_PARAM  # 출력 확인용 (sink)
        elif has_outgoing and not has_incoming:
            return ComponentType.INPUT_PARAM   # 입력용 (source)
        elif has_incoming and has_outgoing:
            return ComponentType.DATA_PARAM    # 중간 데이터 전달
        else:
            # 연결 없음 - 기본 INPUT_PARAM
            return ComponentType.INPUT_PARAM

    # Number Slider, Boolean Toggle 등은 항상 INPUT_PARAM
    if name in {"Number Slider", "Boolean Toggle", "Value List", "MD Slider",
                "Digit Scroller", "Colour Swatch", "Gradient", "Graph Mapper",
                "Image Sampler"}:
        return ComponentType.INPUT_PARAM

    # Data Recorder, Param Viewer 등은 항상 OUTPUT_PARAM
    if name in {"Data Recorder", "Param Viewer"}:
        return ComponentType.OUTPUT_PARAM

    # 기존 정적 분류 사용 (나머지 컴포넌트)
    # has_inputs/has_outputs는 메타데이터 기반이 아닌 실제 연결 기반으로 변경
    return classify_component_type(name, category, subcategory, has_incoming, has_outgoing)


def get_connection_type(src_type: ComponentType, tgt_type: ComponentType) -> str:
    """
    연결 유형 분류

    Returns:
        "param_to_comp": 파라미터 → 컴포넌트
        "comp_to_comp": 컴포넌트 → 컴포넌트
        "comp_to_param": 컴포넌트 → 파라미터
        "param_to_param": 파라미터 → 파라미터 (드묾)
    """
    src_is_param = src_type in (ComponentType.INPUT_PARAM, ComponentType.OUTPUT_PARAM)
    tgt_is_param = tgt_type in (ComponentType.INPUT_PARAM, ComponentType.OUTPUT_PARAM)

    if src_is_param and not tgt_is_param:
        return "param_to_comp"
    elif not src_is_param and tgt_is_param:
        return "comp_to_param"
    elif src_is_param and tgt_is_param:
        return "param_to_param"
    else:
        return "comp_to_comp"


# ============================================================
# Connection Type Spacing Pattern (연결 유형별 간격 패턴)
# ============================================================

@dataclass
class ConnectionSpacingPattern:
    """연결 유형별 간격 패턴"""
    connection_type: str  # param_to_comp, comp_to_comp, comp_to_param
    avg_x: float = 150.0
    avg_y: float = 0.0
    x_samples: List[float] = field(default_factory=list)
    y_samples: List[float] = field(default_factory=list)
    sample_count: int = 0

    def add_sample(self, dx: float, dy: float):
        """간격 샘플 추가"""
        self.x_samples.append(dx)
        self.y_samples.append(dy)

        # 최근 100개 샘플만 유지
        if len(self.x_samples) > 100:
            self.x_samples = self.x_samples[-100:]
            self.y_samples = self.y_samples[-100:]

        self.sample_count = len(self.x_samples)

        # 가중 평균 계산 (최근 샘플에 더 높은 가중치)
        n = len(self.x_samples)
        weights = [1 + i * 0.1 for i in range(n)]
        total_weight = sum(weights)

        self.avg_x = sum(x * w for x, w in zip(self.x_samples, weights)) / total_weight
        self.avg_y = sum(y * w for y, w in zip(self.y_samples, weights)) / total_weight


@dataclass
class ComponentPattern:
    """컴포넌트별 학습된 패턴"""
    name: str
    avg_offset_x: float = 0.0
    avg_offset_y: float = 0.0
    sample_count: int = 0
    weight: float = 1.0  # 가중치 (자주 사용될수록 높음)
    last_updated: str = ""

    # 상세 통계
    offset_x_samples: List[float] = field(default_factory=list)
    offset_y_samples: List[float] = field(default_factory=list)

    def add_sample(self, offset_x: float, offset_y: float):
        """새 샘플 추가 및 평균 업데이트"""
        self.offset_x_samples.append(offset_x)
        self.offset_y_samples.append(offset_y)

        # 최근 100개 샘플만 유지
        if len(self.offset_x_samples) > 100:
            self.offset_x_samples = self.offset_x_samples[-100:]
            self.offset_y_samples = self.offset_y_samples[-100:]

        # 가중 평균 계산 (최근 샘플에 더 높은 가중치)
        n = len(self.offset_x_samples)
        weights = [1 + i * 0.1 for i in range(n)]  # 점진적 가중치
        total_weight = sum(weights)

        self.avg_offset_x = sum(x * w for x, w in zip(self.offset_x_samples, weights)) / total_weight
        self.avg_offset_y = sum(y * w for y, w in zip(self.offset_y_samples, weights)) / total_weight

        self.sample_count = n
        self.weight = min(2.0, 1.0 + (n / 50))  # 샘플이 많을수록 가중치 증가 (최대 2.0)
        self.last_updated = datetime.now().isoformat()


@dataclass
class SpacingPattern:
    """전역 간격 패턴"""
    avg_x: float = 150.0
    avg_y: float = 0.0
    x_samples: List[float] = field(default_factory=list)
    y_samples: List[float] = field(default_factory=list)
    sample_count: int = 0

    def add_sample(self, dx: float, dy: float):
        """간격 샘플 추가"""
        self.x_samples.append(dx)
        self.y_samples.append(dy)

        # 최근 200개 샘플만 유지
        if len(self.x_samples) > 200:
            self.x_samples = self.x_samples[-200:]
            self.y_samples = self.y_samples[-200:]

        self.sample_count = len(self.x_samples)

        # 평균 계산
        if self.x_samples:
            self.avg_x = sum(self.x_samples) / len(self.x_samples)
        if self.y_samples:
            self.avg_y = sum(self.y_samples) / len(self.y_samples)


@dataclass
class CategoryPattern:
    """카테고리별 레이아웃 패턴"""
    category: str
    typical_x_range: Tuple[float, float] = (0.0, 1000.0)
    typical_y_range: Tuple[float, float] = (0.0, 500.0)
    flow_position: str = "middle"  # "start", "middle", "end"
    sample_count: int = 0


@dataclass
class ConnectionPairSample:
    """KNN용 연결 쌍 샘플 - (소스, 타겟) → 오프셋"""
    source_name: str
    target_name: str
    source_type: str  # ComponentType.value
    target_type: str  # ComponentType.value
    offset_x: float
    offset_y: float
    source_output_index: int = 0
    target_input_index: int = 0


@dataclass
class BranchingPattern:
    """분기 패턴 - 한 소스에서 여러 타겟으로"""
    source_name: str
    source_type: str
    target_count: int  # 분기 개수
    y_spacing: float  # 타겟 간 Y 간격
    y_offsets: List[float] = field(default_factory=list)  # 각 타겟의 Y 오프셋
    sample_count: int = 1


@dataclass
class MergingPattern:
    """병합 패턴 - 여러 소스가 한 타겟으로"""
    target_name: str
    target_type: str
    source_count: int  # 병합되는 소스 개수
    y_spacing: float  # 소스 간 Y 간격
    y_offsets: List[float] = field(default_factory=list)  # 각 소스의 Y 오프셋
    sample_count: int = 1


@dataclass
class SequencePattern:
    """시퀀스 패턴 - 연속 체인 (A→B→C)"""
    component_sequence: List[str]  # 컴포넌트 이름 순서
    x_spacings: List[float]  # 각 연결의 X 간격
    sample_count: int = 1


@dataclass
class InputGroupPattern:
    """입력 그룹 패턴 - 같은 타입 입력 컴포넌트들의 배치"""
    component_type: str  # e.g., "Number Slider", "Panel"
    avg_y_spacing: float  # 평균 Y 간격
    typical_count: int  # 일반적인 개수
    sample_count: int = 1


@dataclass
class ClusterSpacingPattern:
    """클러스터 간격 패턴 - 독립 서브그래프 간 간격"""
    avg_y_gap: float = 200.0  # 클러스터 간 평균 Y 간격
    avg_x_gap: float = 0.0    # 클러스터 간 평균 X 간격
    sample_count: int = 0


@dataclass
class PortAlignmentPattern:
    """포트 정렬 패턴 - 타겟 입력 포트 순서에 따른 소스 Y 배치"""
    target_name: str
    source_y_order: List[str]  # 소스 컴포넌트 이름 순서 (Y 위→아래)
    sample_count: int = 1


@dataclass
class WireCrossingPattern:
    """와이어 교차 패턴 - 연결 시 Y 순서 선호"""
    # key: (source_type, target_type) 또는 (source_name, target_name)
    preferred_y_order: str  # "above" = 소스가 타겟 위, "below" = 아래, "same" = 같은 레벨
    confidence: float = 0.5
    sample_count: int = 1


@dataclass
class DensityPattern:
    """밀도 패턴 - 영역당 컴포넌트 밀도"""
    avg_components_per_row: float = 5.0  # 행당 평균 컴포넌트 수
    avg_x_span: float = 1000.0  # 평균 X 범위
    avg_y_span: float = 500.0   # 평균 Y 범위
    sample_count: int = 0


@dataclass
class SubgraphNode:
    """서브그래프 내 노드 정보"""
    name: str  # 컴포넌트 이름
    comp_type: str  # 컴포넌트 타입
    relative_x: float  # 템플릿 내 상대 X (첫 노드 기준)
    relative_y: float  # 템플릿 내 상대 Y (첫 노드 기준)
    index: int  # 템플릿 내 인덱스


@dataclass
class SubgraphTemplate:
    """서브그래프 템플릿 - 자주 나오는 연결 패턴과 레이아웃"""
    # 식별 키: 컴포넌트 이름 시퀀스 (정규화된 문자열)
    pattern_key: str  # e.g., "Number Slider->Series->List Item"
    nodes: List[SubgraphNode]  # 노드 정보 (상대 위치 포함)
    edges: List[Tuple[int, int]]  # 연결 (노드 인덱스 쌍)
    node_count: int
    sample_count: int = 1

    # 레이아웃 정보 (학습된 평균)
    avg_width: float = 0.0  # 전체 X 범위
    avg_height: float = 0.0  # 전체 Y 범위


@dataclass
class LearningSession:
    """학습 세션 기록"""
    session_id: str
    timestamp: str
    source_file: str
    component_count: int
    wire_count: int
    patterns_learned: int


@dataclass
class YOrderPattern:
    """Y 순서 패턴 - 같은 X 레벨에서 컴포넌트 쌍의 Y 순서"""
    # key: (comp_name_a, comp_name_b) 정렬된 튜플
    comp_a: str  # 첫 번째 컴포넌트 이름
    comp_b: str  # 두 번째 컴포넌트 이름
    a_above_count: int = 0  # A가 B 위에 있는 횟수
    b_above_count: int = 0  # B가 A 위에 있는 횟수
    sample_count: int = 0

    @property
    def preferred_order(self) -> str:
        """선호하는 순서 반환: 'a_above', 'b_above', 또는 'neutral'"""
        if self.a_above_count > self.b_above_count * 1.2:  # 20% 이상 차이
            return "a_above"
        elif self.b_above_count > self.a_above_count * 1.2:
            return "b_above"
        return "neutral"

    @property
    def confidence(self) -> float:
        """순서 신뢰도 (0~1)"""
        if self.sample_count == 0:
            return 0.0
        dominant = max(self.a_above_count, self.b_above_count)
        return dominant / self.sample_count


@dataclass
class YOrderByTypePattern:
    """타입 기반 Y 순서 패턴 - 컴포넌트 타입 쌍의 Y 순서"""
    type_a: str  # 첫 번째 컴포넌트 타입
    type_b: str  # 두 번째 컴포넌트 타입
    a_above_count: int = 0
    b_above_count: int = 0
    sample_count: int = 0

    @property
    def preferred_order(self) -> str:
        if self.a_above_count > self.b_above_count * 1.2:
            return "a_above"
        elif self.b_above_count > self.a_above_count * 1.2:
            return "b_above"
        return "neutral"


@dataclass
class TopologyLevelPattern:
    """
    토폴로지 레벨 패턴 - 컴포넌트가 데이터 흐름에서 몇 번째 단계에 위치하는지 학습

    예: 입력(레벨0) → 처리1(레벨1) → 처리2(레벨2) → 출력(레벨3)
    """
    component_name: str  # 컴포넌트 이름
    level_counts: Dict[int, int] = field(default_factory=dict)  # {레벨: 횟수}
    total_samples: int = 0

    @property
    def avg_level(self) -> float:
        """평균 레벨 계산"""
        if self.total_samples == 0:
            return 0.0
        total = sum(level * count for level, count in self.level_counts.items())
        return total / self.total_samples

    @property
    def dominant_level(self) -> int:
        """가장 빈번한 레벨"""
        if not self.level_counts:
            return 0
        return max(self.level_counts.keys(), key=lambda k: self.level_counts[k])


@dataclass
class TopologyLevelByTypePattern:
    """타입 기반 토폴로지 레벨 패턴"""
    component_type: str
    level_counts: Dict[int, int] = field(default_factory=dict)
    total_samples: int = 0

    @property
    def avg_level(self) -> float:
        if self.total_samples == 0:
            return 0.0
        total = sum(level * count for level, count in self.level_counts.items())
        return total / self.total_samples


@dataclass
class XSpacingByLevelPattern:
    """레벨 간 X 간격 패턴 - 레벨 N에서 레벨 N+1로 갈 때 X 간격"""
    from_level: int
    to_level: int
    x_spacings: List[float] = field(default_factory=list)
    sample_count: int = 0

    @property
    def avg_x_spacing(self) -> float:
        if not self.x_spacings:
            return 200.0  # 기본값
        return sum(self.x_spacings) / len(self.x_spacings)


@dataclass
class RelativePositionPattern:
    """
    v8.0: 연결 대상 기반 상대 위치 패턴

    "이 컴포넌트가 연결된 대상 기준으로 어디에 위치하는가"
    예: Panel이 Series에 연결될 때 → Panel은 Series 왼쪽 200px
    """
    source_name: str  # 소스 컴포넌트 이름
    target_name: str  # 타겟 컴포넌트 이름
    x_offsets: List[float] = field(default_factory=list)  # 소스X - 타겟X (음수면 소스가 왼쪽)
    y_offsets: List[float] = field(default_factory=list)  # 소스Y - 타겟Y
    sample_count: int = 0

    @property
    def avg_x_offset(self) -> float:
        if not self.x_offsets:
            return -200.0  # 기본: 소스가 왼쪽
        return sum(self.x_offsets) / len(self.x_offsets)

    @property
    def avg_y_offset(self) -> float:
        if not self.y_offsets:
            return 0.0
        return sum(self.y_offsets) / len(self.y_offsets)

    @property
    def source_left_ratio(self) -> float:
        """소스가 타겟 왼쪽에 있는 비율 (0~1)"""
        if not self.x_offsets:
            return 0.5
        left_count = sum(1 for x in self.x_offsets if x < 0)
        return left_count / len(self.x_offsets)


@dataclass
class RelativePositionByTypePattern:
    """타입 기반 상대 위치 패턴"""
    source_type: str
    target_type: str
    x_offsets: List[float] = field(default_factory=list)
    y_offsets: List[float] = field(default_factory=list)
    sample_count: int = 0

    @property
    def avg_x_offset(self) -> float:
        if not self.x_offsets:
            return -200.0
        return sum(self.x_offsets) / len(self.x_offsets)

    @property
    def avg_y_offset(self) -> float:
        if not self.y_offsets:
            return 0.0
        return sum(self.y_offsets) / len(self.y_offsets)

    @property
    def source_left_ratio(self) -> float:
        if not self.x_offsets:
            return 0.5
        left_count = sum(1 for x in self.x_offsets if x < 0)
        return left_count / len(self.x_offsets)


class PersistentLayoutLearner:
    """
    영속적 레이아웃 학습 시스템

    학습 데이터를 JSON 파일로 저장하여 세션 간에 유지하고,
    여러 GH 정의에서 학습한 패턴을 누적하여 최적화합니다.
    """

    VERSION = "3.0"  # 연결 유형별 패턴 추가

    def __init__(self, storage_path: Optional[str] = None):
        """
        Args:
            storage_path: 학습 데이터 저장 경로 (기본: 모듈 디렉토리/layout_learning_data.json)
        """
        if storage_path is None:
            self.storage_path = Path(__file__).parent / "layout_learning_data.json"
        else:
            self.storage_path = Path(storage_path)

        # 학습 데이터
        self.component_patterns: Dict[str, ComponentPattern] = {}
        self.spacing_pattern: SpacingPattern = SpacingPattern()
        self.category_patterns: Dict[str, CategoryPattern] = {}
        self.learning_sessions: List[LearningSession] = []

        # NEW: 연결 유형별 간격 패턴
        self.connection_spacing: Dict[str, ConnectionSpacingPattern] = {
            "param_to_comp": ConnectionSpacingPattern(connection_type="param_to_comp", avg_x=120, avg_y=0),
            "comp_to_comp": ConnectionSpacingPattern(connection_type="comp_to_comp", avg_x=180, avg_y=0),
            "comp_to_param": ConnectionSpacingPattern(connection_type="comp_to_param", avg_x=150, avg_y=0),
            "param_to_param": ConnectionSpacingPattern(connection_type="param_to_param", avg_x=100, avg_y=0),
        }

        # NEW: 컴포넌트 타입별 통계
        self.type_statistics: Dict[str, dict] = {}

        # NEW: KNN용 연결 쌍 샘플 (최대 5000개 유지)
        self.connection_pair_samples: List[ConnectionPairSample] = []
        self.max_knn_samples: int = 5000

        # NEW: 추가 패턴들
        self.branching_patterns: Dict[str, BranchingPattern] = {}  # source_name -> pattern
        self.merging_patterns: Dict[str, MergingPattern] = {}  # target_name -> pattern
        self.sequence_patterns: List[SequencePattern] = []  # 시퀀스 패턴 목록
        self.input_group_patterns: Dict[str, InputGroupPattern] = {}  # component_type -> pattern

        # NEW v4.0: 추가 고급 패턴들
        self.cluster_spacing_pattern: ClusterSpacingPattern = ClusterSpacingPattern()
        self.port_alignment_patterns: Dict[str, PortAlignmentPattern] = {}  # target_name -> pattern
        self.wire_crossing_patterns: Dict[str, WireCrossingPattern] = {}  # (src_type, tgt_type) -> pattern
        self.density_pattern: DensityPattern = DensityPattern()

        # NEW v5.0: 서브그래프 템플릿 (pattern_key -> template)
        self.subgraph_templates: Dict[str, SubgraphTemplate] = {}
        self.max_subgraph_templates: int = 500  # 최대 템플릿 수

        # NEW v6.0: Y 순서 패턴 (같은 X 레벨에서 컴포넌트 쌍의 Y 순서)
        self.y_order_patterns: Dict[str, YOrderPattern] = {}  # "(name_a, name_b)" -> pattern
        self.y_order_by_type: Dict[str, YOrderByTypePattern] = {}  # "(type_a, type_b)" -> pattern

        # NEW v7.0: 토폴로지 레벨 패턴 (좌→우 수평 배치를 위한 레벨 학습)
        self.topology_level_patterns: Dict[str, TopologyLevelPattern] = {}  # comp_name -> pattern
        self.topology_level_by_type: Dict[str, TopologyLevelByTypePattern] = {}  # comp_type -> pattern
        self.x_spacing_by_level: Dict[str, XSpacingByLevelPattern] = {}  # "(from_level, to_level)" -> pattern
        self.max_topology_level: int = 0  # 학습된 최대 레벨

        # NEW v8.0: 연결 대상 기반 상대 위치 패턴
        self.relative_position_patterns: Dict[str, RelativePositionPattern] = {}  # "(src_name, tgt_name)" -> pattern
        self.relative_position_by_type: Dict[str, RelativePositionByTypePattern] = {}  # "(src_type, tgt_type)" -> pattern

        # 메타데이터
        self.version = self.VERSION
        self.created_at: Optional[str] = None
        self.last_updated: Optional[str] = None
        self.total_sessions: int = 0
        self.total_components_learned: int = 0

        # 자동 로드
        self.load()

    # =========================================================================
    # Persistence (저장/로드)
    # =========================================================================

    def save(self) -> dict:
        """학습 데이터를 JSON 파일로 저장"""
        self.last_updated = datetime.now().isoformat()

        if self.created_at is None:
            self.created_at = self.last_updated

        data = {
            "version": self.version,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "total_sessions": self.total_sessions,
            "total_components_learned": self.total_components_learned,

            # 컴포넌트 패턴
            "component_patterns": {
                name: {
                    "name": p.name,
                    "avg_offset_x": round(p.avg_offset_x, 2),
                    "avg_offset_y": round(p.avg_offset_y, 2),
                    "sample_count": p.sample_count,
                    "weight": round(p.weight, 3),
                    "last_updated": p.last_updated,
                    # 샘플은 최근 20개만 저장 (용량 절약)
                    "offset_x_samples": [round(x, 1) for x in p.offset_x_samples[-20:]],
                    "offset_y_samples": [round(y, 1) for y in p.offset_y_samples[-20:]]
                }
                for name, p in self.component_patterns.items()
            },

            # 간격 패턴
            "spacing_pattern": {
                "avg_x": round(self.spacing_pattern.avg_x, 2),
                "avg_y": round(self.spacing_pattern.avg_y, 2),
                "sample_count": self.spacing_pattern.sample_count,
                "x_samples": [round(x, 1) for x in self.spacing_pattern.x_samples[-50:]],
                "y_samples": [round(y, 1) for y in self.spacing_pattern.y_samples[-50:]]
            },

            # 카테고리 패턴
            "category_patterns": {
                name: {
                    "category": p.category,
                    "typical_x_range": p.typical_x_range,
                    "typical_y_range": p.typical_y_range,
                    "flow_position": p.flow_position,
                    "sample_count": p.sample_count
                }
                for name, p in self.category_patterns.items()
            },

            # NEW: 연결 유형별 간격 패턴
            "connection_spacing": {
                conn_type: {
                    "connection_type": pattern.connection_type,
                    "avg_x": round(pattern.avg_x, 2),
                    "avg_y": round(pattern.avg_y, 2),
                    "sample_count": pattern.sample_count,
                    "x_samples": [round(x, 1) for x in pattern.x_samples[-30:]],
                    "y_samples": [round(y, 1) for y in pattern.y_samples[-30:]]
                }
                for conn_type, pattern in self.connection_spacing.items()
            },

            # NEW: 컴포넌트 타입별 통계
            "type_statistics": self.type_statistics,

            # NEW: KNN용 연결 쌍 샘플 (최근 max_knn_samples개만 저장)
            "connection_pair_samples": [
                {
                    "source_name": s.source_name,
                    "target_name": s.target_name,
                    "source_type": s.source_type,
                    "target_type": s.target_type,
                    "offset_x": round(s.offset_x, 1),
                    "offset_y": round(s.offset_y, 1),
                    "source_output_index": s.source_output_index,
                    "target_input_index": s.target_input_index
                }
                for s in self.connection_pair_samples[-self.max_knn_samples:]
            ],

            # 최근 10개 학습 세션만 저장
            "learning_sessions": [
                {
                    "session_id": s.session_id,
                    "timestamp": s.timestamp,
                    "source_file": s.source_file,
                    "component_count": s.component_count,
                    "wire_count": s.wire_count,
                    "patterns_learned": s.patterns_learned
                }
                for s in self.learning_sessions[-10:]
            ],

            # NEW: 추가 패턴들
            "branching_patterns": {
                key: {
                    "source_name": p.source_name,
                    "source_type": p.source_type,
                    "target_count": p.target_count,
                    "y_spacing": round(p.y_spacing, 1),
                    "sample_count": p.sample_count
                }
                for key, p in self.branching_patterns.items()
            },
            "merging_patterns": {
                key: {
                    "target_name": p.target_name,
                    "target_type": p.target_type,
                    "source_count": p.source_count,
                    "y_spacing": round(p.y_spacing, 1),
                    "sample_count": p.sample_count
                }
                for key, p in self.merging_patterns.items()
            },
            "input_group_patterns": {
                key: {
                    "component_type": p.component_type,
                    "avg_y_spacing": round(p.avg_y_spacing, 1),
                    "typical_count": p.typical_count,
                    "sample_count": p.sample_count
                }
                for key, p in self.input_group_patterns.items()
            },
            "sequence_patterns": [
                {
                    "component_sequence": p.component_sequence,
                    "x_spacings": [round(x, 1) for x in p.x_spacings],
                    "sample_count": p.sample_count
                }
                for p in self.sequence_patterns[-50:]  # 최근 50개만
            ],

            # NEW v4.0: 추가 고급 패턴들
            "cluster_spacing_pattern": {
                "avg_y_gap": round(self.cluster_spacing_pattern.avg_y_gap, 1),
                "avg_x_gap": round(self.cluster_spacing_pattern.avg_x_gap, 1),
                "sample_count": self.cluster_spacing_pattern.sample_count
            },
            "port_alignment_patterns": {
                key: {
                    "target_name": p.target_name,
                    "source_y_order": p.source_y_order,
                    "sample_count": p.sample_count
                }
                for key, p in self.port_alignment_patterns.items()
            },
            "wire_crossing_patterns": {
                key: {
                    "preferred_y_order": p.preferred_y_order,
                    "confidence": round(p.confidence, 2),
                    "sample_count": p.sample_count
                }
                for key, p in self.wire_crossing_patterns.items()
            },
            "density_pattern": {
                "avg_components_per_row": round(self.density_pattern.avg_components_per_row, 1),
                "avg_x_span": round(self.density_pattern.avg_x_span, 1),
                "avg_y_span": round(self.density_pattern.avg_y_span, 1),
                "sample_count": self.density_pattern.sample_count
            },

            # NEW v5.0: 서브그래프 템플릿
            "subgraph_templates": {
                key: {
                    "pattern_key": t.pattern_key,
                    "nodes": [
                        {
                            "name": n.name,
                            "comp_type": n.comp_type,
                            "relative_x": round(n.relative_x, 1),
                            "relative_y": round(n.relative_y, 1),
                            "index": n.index
                        }
                        for n in t.nodes
                    ],
                    "edges": t.edges,
                    "node_count": t.node_count,
                    "sample_count": t.sample_count,
                    "avg_width": round(t.avg_width, 1),
                    "avg_height": round(t.avg_height, 1)
                }
                for key, t in sorted(
                    self.subgraph_templates.items(),
                    key=lambda x: x[1].sample_count,
                    reverse=True
                )[:200]  # 상위 200개만 저장
            },

            # NEW v6.0: Y 순서 패턴
            "y_order_patterns": {
                key: {
                    "comp_a": p.comp_a,
                    "comp_b": p.comp_b,
                    "a_above_count": p.a_above_count,
                    "b_above_count": p.b_above_count,
                    "sample_count": p.sample_count
                }
                for key, p in sorted(
                    self.y_order_patterns.items(),
                    key=lambda x: x[1].sample_count,
                    reverse=True
                )[:500]  # 상위 500개만 저장
            },
            "y_order_by_type": {
                key: {
                    "type_a": p.type_a,
                    "type_b": p.type_b,
                    "a_above_count": p.a_above_count,
                    "b_above_count": p.b_above_count,
                    "sample_count": p.sample_count
                }
                for key, p in self.y_order_by_type.items()
            },

            # NEW v7.0: 토폴로지 레벨 패턴
            "topology_level_patterns": {
                name: {
                    "component_name": p.component_name,
                    "level_counts": p.level_counts,
                    "total_samples": p.total_samples
                }
                for name, p in sorted(
                    self.topology_level_patterns.items(),
                    key=lambda x: x[1].total_samples,
                    reverse=True
                )[:500]  # 상위 500개만 저장
            },
            "topology_level_by_type": {
                t: {
                    "component_type": p.component_type,
                    "level_counts": p.level_counts,
                    "total_samples": p.total_samples
                }
                for t, p in self.topology_level_by_type.items()
            },
            "x_spacing_by_level": {
                key: {
                    "from_level": p.from_level,
                    "to_level": p.to_level,
                    "avg_x_spacing": round(p.avg_x_spacing, 1),
                    "sample_count": p.sample_count
                }
                for key, p in self.x_spacing_by_level.items()
            },
            "max_topology_level": self.max_topology_level,

            # NEW v8.0: 연결 대상 기반 상대 위치 패턴
            "relative_position_patterns": {
                key: {
                    "source_name": p.source_name,
                    "target_name": p.target_name,
                    "avg_x_offset": round(p.avg_x_offset, 1),
                    "avg_y_offset": round(p.avg_y_offset, 1),
                    "source_left_ratio": round(p.source_left_ratio, 2),
                    "sample_count": p.sample_count
                }
                for key, p in sorted(
                    self.relative_position_patterns.items(),
                    key=lambda x: x[1].sample_count,
                    reverse=True
                )[:500]  # 상위 500개만 저장
            },
            "relative_position_by_type": {
                key: {
                    "source_type": p.source_type,
                    "target_type": p.target_type,
                    "avg_x_offset": round(p.avg_x_offset, 1),
                    "avg_y_offset": round(p.avg_y_offset, 1),
                    "source_left_ratio": round(p.source_left_ratio, 2),
                    "sample_count": p.sample_count
                }
                for key, p in self.relative_position_by_type.items()
            }
        }

        # 저장
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "path": str(self.storage_path),
            "component_patterns_count": len(self.component_patterns),
            "total_sessions": self.total_sessions
        }

    def load(self) -> dict:
        """저장된 학습 데이터 로드"""
        if not self.storage_path.exists():
            return {
                "success": True,
                "loaded": False,
                "message": "No existing learning data found. Starting fresh."
            }

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 메타데이터
            self.version = data.get("version", self.VERSION)
            self.created_at = data.get("created_at")
            self.last_updated = data.get("last_updated")
            self.total_sessions = data.get("total_sessions", 0)
            self.total_components_learned = data.get("total_components_learned", 0)

            # 컴포넌트 패턴 로드
            for name, p_data in data.get("component_patterns", {}).items():
                pattern = ComponentPattern(
                    name=p_data.get("name", name),
                    avg_offset_x=p_data.get("avg_offset_x", 0),
                    avg_offset_y=p_data.get("avg_offset_y", 0),
                    sample_count=p_data.get("sample_count", 0),
                    weight=p_data.get("weight", 1.0),
                    last_updated=p_data.get("last_updated", ""),
                    offset_x_samples=p_data.get("offset_x_samples", []),
                    offset_y_samples=p_data.get("offset_y_samples", [])
                )
                self.component_patterns[name] = pattern

            # 간격 패턴 로드
            sp_data = data.get("spacing_pattern", {})
            self.spacing_pattern = SpacingPattern(
                avg_x=sp_data.get("avg_x", 150),
                avg_y=sp_data.get("avg_y", 0),
                x_samples=sp_data.get("x_samples", []),
                y_samples=sp_data.get("y_samples", []),
                sample_count=sp_data.get("sample_count", 0)
            )

            # 카테고리 패턴 로드
            for name, c_data in data.get("category_patterns", {}).items():
                self.category_patterns[name] = CategoryPattern(
                    category=c_data.get("category", name),
                    typical_x_range=tuple(c_data.get("typical_x_range", [0, 1000])),
                    typical_y_range=tuple(c_data.get("typical_y_range", [0, 500])),
                    flow_position=c_data.get("flow_position", "middle"),
                    sample_count=c_data.get("sample_count", 0)
                )

            # 학습 세션 로드
            for s_data in data.get("learning_sessions", []):
                session = LearningSession(
                    session_id=s_data.get("session_id", ""),
                    timestamp=s_data.get("timestamp", ""),
                    source_file=s_data.get("source_file", ""),
                    component_count=s_data.get("component_count", 0),
                    wire_count=s_data.get("wire_count", 0),
                    patterns_learned=s_data.get("patterns_learned", 0)
                )
                self.learning_sessions.append(session)

            # NEW: 연결 유형별 간격 패턴 로드
            for conn_type, cs_data in data.get("connection_spacing", {}).items():
                if conn_type in self.connection_spacing:
                    pattern = self.connection_spacing[conn_type]
                    pattern.avg_x = cs_data.get("avg_x", pattern.avg_x)
                    pattern.avg_y = cs_data.get("avg_y", pattern.avg_y)
                    pattern.sample_count = cs_data.get("sample_count", 0)
                    pattern.x_samples = cs_data.get("x_samples", [])
                    pattern.y_samples = cs_data.get("y_samples", [])

            # NEW: 타입별 통계 로드
            self.type_statistics = data.get("type_statistics", {})

            # NEW: KNN용 연결 쌍 샘플 로드
            self.connection_pair_samples = []
            for s_data in data.get("connection_pair_samples", []):
                sample = ConnectionPairSample(
                    source_name=s_data.get("source_name", ""),
                    target_name=s_data.get("target_name", ""),
                    source_type=s_data.get("source_type", "UNKNOWN"),
                    target_type=s_data.get("target_type", "UNKNOWN"),
                    offset_x=s_data.get("offset_x", 0),
                    offset_y=s_data.get("offset_y", 0),
                    source_output_index=s_data.get("source_output_index", 0),
                    target_input_index=s_data.get("target_input_index", 0)
                )
                self.connection_pair_samples.append(sample)

            # NEW: 추가 패턴 로드
            self.branching_patterns = {}
            for key, p_data in data.get("branching_patterns", {}).items():
                self.branching_patterns[key] = BranchingPattern(
                    source_name=p_data.get("source_name", ""),
                    source_type=p_data.get("source_type", "UNKNOWN"),
                    target_count=p_data.get("target_count", 2),
                    y_spacing=p_data.get("y_spacing", 80),
                    sample_count=p_data.get("sample_count", 1)
                )

            self.merging_patterns = {}
            for key, p_data in data.get("merging_patterns", {}).items():
                self.merging_patterns[key] = MergingPattern(
                    target_name=p_data.get("target_name", ""),
                    target_type=p_data.get("target_type", "UNKNOWN"),
                    source_count=p_data.get("source_count", 2),
                    y_spacing=p_data.get("y_spacing", 80),
                    sample_count=p_data.get("sample_count", 1)
                )

            self.input_group_patterns = {}
            for key, p_data in data.get("input_group_patterns", {}).items():
                self.input_group_patterns[key] = InputGroupPattern(
                    component_type=p_data.get("component_type", ""),
                    avg_y_spacing=p_data.get("avg_y_spacing", 50),
                    typical_count=p_data.get("typical_count", 2),
                    sample_count=p_data.get("sample_count", 1)
                )

            self.sequence_patterns = []
            for p_data in data.get("sequence_patterns", []):
                self.sequence_patterns.append(SequencePattern(
                    component_sequence=p_data.get("component_sequence", []),
                    x_spacings=p_data.get("x_spacings", []),
                    sample_count=p_data.get("sample_count", 1)
                ))

            # NEW v4.0: 추가 고급 패턴 로드
            csp_data = data.get("cluster_spacing_pattern", {})
            self.cluster_spacing_pattern = ClusterSpacingPattern(
                avg_y_gap=csp_data.get("avg_y_gap", 200),
                avg_x_gap=csp_data.get("avg_x_gap", 0),
                sample_count=csp_data.get("sample_count", 0)
            )

            self.port_alignment_patterns = {}
            for key, p_data in data.get("port_alignment_patterns", {}).items():
                self.port_alignment_patterns[key] = PortAlignmentPattern(
                    target_name=p_data.get("target_name", ""),
                    source_y_order=p_data.get("source_y_order", []),
                    sample_count=p_data.get("sample_count", 1)
                )

            self.wire_crossing_patterns = {}
            for key, p_data in data.get("wire_crossing_patterns", {}).items():
                self.wire_crossing_patterns[key] = WireCrossingPattern(
                    preferred_y_order=p_data.get("preferred_y_order", "same"),
                    confidence=p_data.get("confidence", 0.5),
                    sample_count=p_data.get("sample_count", 1)
                )

            dp_data = data.get("density_pattern", {})
            self.density_pattern = DensityPattern(
                avg_components_per_row=dp_data.get("avg_components_per_row", 5),
                avg_x_span=dp_data.get("avg_x_span", 1000),
                avg_y_span=dp_data.get("avg_y_span", 500),
                sample_count=dp_data.get("sample_count", 0)
            )

            # NEW v5.0: 서브그래프 템플릿 로드
            self.subgraph_templates = {}
            for key, t_data in data.get("subgraph_templates", {}).items():
                nodes = []
                for n_data in t_data.get("nodes", []):
                    nodes.append(SubgraphNode(
                        name=n_data.get("name", ""),
                        comp_type=n_data.get("comp_type", "unknown"),
                        relative_x=n_data.get("relative_x", 0),
                        relative_y=n_data.get("relative_y", 0),
                        index=n_data.get("index", 0)
                    ))
                self.subgraph_templates[key] = SubgraphTemplate(
                    pattern_key=t_data.get("pattern_key", key),
                    nodes=nodes,
                    edges=[tuple(e) for e in t_data.get("edges", [])],
                    node_count=t_data.get("node_count", len(nodes)),
                    sample_count=t_data.get("sample_count", 1),
                    avg_width=t_data.get("avg_width", 0),
                    avg_height=t_data.get("avg_height", 0)
                )

            # NEW v6.0: Y 순서 패턴 로드
            self.y_order_patterns = {}
            for key, p_data in data.get("y_order_patterns", {}).items():
                self.y_order_patterns[key] = YOrderPattern(
                    comp_a=p_data.get("comp_a", ""),
                    comp_b=p_data.get("comp_b", ""),
                    a_above_count=p_data.get("a_above_count", 0),
                    b_above_count=p_data.get("b_above_count", 0),
                    sample_count=p_data.get("sample_count", 0)
                )

            self.y_order_by_type = {}
            for key, p_data in data.get("y_order_by_type", {}).items():
                self.y_order_by_type[key] = YOrderByTypePattern(
                    type_a=p_data.get("type_a", ""),
                    type_b=p_data.get("type_b", ""),
                    a_above_count=p_data.get("a_above_count", 0),
                    b_above_count=p_data.get("b_above_count", 0),
                    sample_count=p_data.get("sample_count", 0)
                )

            # NEW v7.0: 토폴로지 레벨 패턴 로드
            self.topology_level_patterns = {}
            for name, p_data in data.get("topology_level_patterns", {}).items():
                # level_counts의 키를 정수로 변환
                level_counts = {int(k): v for k, v in p_data.get("level_counts", {}).items()}
                self.topology_level_patterns[name] = TopologyLevelPattern(
                    component_name=p_data.get("component_name", name),
                    level_counts=level_counts,
                    total_samples=p_data.get("total_samples", 0)
                )

            self.topology_level_by_type = {}
            for t, p_data in data.get("topology_level_by_type", {}).items():
                level_counts = {int(k): v for k, v in p_data.get("level_counts", {}).items()}
                self.topology_level_by_type[t] = TopologyLevelByTypePattern(
                    component_type=p_data.get("component_type", t),
                    level_counts=level_counts,
                    total_samples=p_data.get("total_samples", 0)
                )

            self.x_spacing_by_level = {}
            for key, p_data in data.get("x_spacing_by_level", {}).items():
                self.x_spacing_by_level[key] = XSpacingByLevelPattern(
                    from_level=p_data.get("from_level", 0),
                    to_level=p_data.get("to_level", 0),
                    x_spacings=[p_data.get("avg_x_spacing", 200.0)],  # 평균값만 저장했으므로 리스트로 변환
                    sample_count=p_data.get("sample_count", 0)
                )

            self.max_topology_level = data.get("max_topology_level", 0)

            # NEW v8.0: 연결 대상 기반 상대 위치 패턴 로드
            self.relative_position_patterns = {}
            for key, p_data in data.get("relative_position_patterns", {}).items():
                self.relative_position_patterns[key] = RelativePositionPattern(
                    source_name=p_data.get("source_name", ""),
                    target_name=p_data.get("target_name", ""),
                    x_offsets=[p_data.get("avg_x_offset", -200.0)],
                    y_offsets=[p_data.get("avg_y_offset", 0.0)],
                    sample_count=p_data.get("sample_count", 0)
                )

            self.relative_position_by_type = {}
            for key, p_data in data.get("relative_position_by_type", {}).items():
                self.relative_position_by_type[key] = RelativePositionByTypePattern(
                    source_type=p_data.get("source_type", ""),
                    target_type=p_data.get("target_type", ""),
                    x_offsets=[p_data.get("avg_x_offset", -200.0)],
                    y_offsets=[p_data.get("avg_y_offset", 0.0)],
                    sample_count=p_data.get("sample_count", 0)
                )

            return {
                "success": True,
                "loaded": True,
                "component_patterns_count": len(self.component_patterns),
                "total_sessions": self.total_sessions,
                "last_updated": self.last_updated
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def clear(self) -> dict:
        """모든 학습 데이터 초기화"""
        self.component_patterns = {}
        self.spacing_pattern = SpacingPattern()
        self.category_patterns = {}
        self.learning_sessions = []
        self.total_sessions = 0
        self.total_components_learned = 0
        self.created_at = None
        self.last_updated = None

        # NEW: 연결 유형별 패턴 초기화
        self.connection_spacing = {
            "param_to_comp": ConnectionSpacingPattern(connection_type="param_to_comp", avg_x=120, avg_y=0),
            "comp_to_comp": ConnectionSpacingPattern(connection_type="comp_to_comp", avg_x=180, avg_y=0),
            "comp_to_param": ConnectionSpacingPattern(connection_type="comp_to_param", avg_x=150, avg_y=0),
            "param_to_param": ConnectionSpacingPattern(connection_type="param_to_param", avg_x=100, avg_y=0),
        }
        self.type_statistics = {}

        # KNN용 연결 쌍 샘플 초기화
        self.connection_pair_samples = []

        # 추가 패턴 초기화
        self.branching_patterns = {}
        self.merging_patterns = {}
        self.sequence_patterns = []
        self.input_group_patterns = {}

        # NEW v4.0: 추가 고급 패턴 초기화
        self.cluster_spacing_pattern = ClusterSpacingPattern()
        self.port_alignment_patterns = {}
        self.wire_crossing_patterns = {}
        self.density_pattern = DensityPattern()

        # NEW v5.0: 서브그래프 템플릿 초기화
        self.subgraph_templates = {}

        # NEW v6.0: Y 순서 패턴 초기화
        self.y_order_patterns = {}
        self.y_order_by_type = {}

        # NEW v7.0: 토폴로지 레벨 패턴 초기화
        self.topology_level_patterns = {}
        self.topology_level_by_type = {}
        self.x_spacing_by_level = {}
        self.max_topology_level = 0

        # NEW v8.0: 연결 대상 기반 상대 위치 패턴 초기화
        self.relative_position_patterns = {}
        self.relative_position_by_type = {}

        # 파일도 삭제
        if self.storage_path.exists():
            self.storage_path.unlink()

        return {"success": True, "message": "All learning data cleared"}

    # =========================================================================
    # Learning (학습)
    # =========================================================================

    def learn_from_canvas(
        self,
        components: List[dict],
        wires: List[dict],
        source_file: str = "unknown"
    ) -> dict:
        """
        현재 캔버스에서 레이아웃 패턴 학습

        Args:
            components: 컴포넌트 정보 리스트 [{guid, name, x, y, category, ...}]
            wires: 와이어 연결 리스트 [{source_guid, target_guid}]
            source_file: 소스 파일 이름 (기록용)

        Returns:
            학습 결과 요약
        """
        if len(components) < 2:
            return {"success": False, "error": "Not enough components to learn"}

        # GUID → 컴포넌트 맵 생성
        comp_map = {}
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid:
                comp_map[str(guid)] = comp

        patterns_learned = 0

        # 컴포넌트 타입 분류 먼저 수행
        comp_types: Dict[str, ComponentType] = {}
        for guid, comp in comp_map.items():
            name = comp.get('name', '')
            category = comp.get('category', '')
            subcategory = comp.get('subcategory', '')

            # 입출력 여부 확인 (가능한 경우)
            inputs = comp.get('inputs', [])
            outputs = comp.get('outputs', [])
            has_inputs = len(inputs) > 0 if inputs else True
            has_outputs = len(outputs) > 0 if outputs else True

            comp_type = classify_component_type(
                name=name,
                category=category,
                subcategory=subcategory,
                has_inputs=has_inputs,
                has_outputs=has_outputs
            )
            comp_types[guid] = comp_type

            # 타입별 통계 업데이트
            type_key = comp_type.value
            if type_key not in self.type_statistics:
                self.type_statistics[type_key] = {"count": 0, "components": []}
            self.type_statistics[type_key]["count"] += 1
            if name not in self.type_statistics[type_key]["components"]:
                self.type_statistics[type_key]["components"].append(name)

        # 연결 유형별 통계
        connection_type_counts = defaultdict(int)

        # 와이어 연결에서 간격 패턴 학습
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))

            if src_guid not in comp_map or tgt_guid not in comp_map:
                continue

            src = comp_map[src_guid]
            tgt = comp_map[tgt_guid]

            src_x = src.get('x') or src.get('position_x')
            src_y = src.get('y') or src.get('position_y')
            tgt_x = tgt.get('x') or tgt.get('position_x')
            tgt_y = tgt.get('y') or tgt.get('position_y')

            if None in (src_x, src_y, tgt_x, tgt_y):
                continue

            dx = float(tgt_x) - float(src_x)
            dy = float(tgt_y) - float(src_y)

            # 전역 간격 패턴 업데이트
            self.spacing_pattern.add_sample(dx, dy)

            # 컴포넌트별 패턴 업데이트
            src_name = src.get('name', '')
            if src_name:
                if src_name not in self.component_patterns:
                    self.component_patterns[src_name] = ComponentPattern(name=src_name)
                self.component_patterns[src_name].add_sample(dx, dy)
                patterns_learned += 1

            # NEW: 연결 유형별 간격 패턴 업데이트
            src_type = comp_types.get(src_guid, ComponentType.UNKNOWN)
            tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN)
            conn_type = get_connection_type(src_type, tgt_type)

            if conn_type in self.connection_spacing:
                self.connection_spacing[conn_type].add_sample(dx, dy)
                connection_type_counts[conn_type] += 1

            # NEW: KNN용 연결 쌍 샘플 저장
            tgt_name = tgt.get('name', '')
            if src_name and tgt_name:
                pair_sample = ConnectionPairSample(
                    source_name=src_name,
                    target_name=tgt_name,
                    source_type=src_type.value,
                    target_type=tgt_type.value,
                    offset_x=dx,
                    offset_y=dy,
                    source_output_index=wire.get('source_output', 0),
                    target_input_index=wire.get('target_input', 0)
                )
                self.connection_pair_samples.append(pair_sample)

                # 최대 개수 유지
                if len(self.connection_pair_samples) > self.max_knn_samples:
                    self.connection_pair_samples = self.connection_pair_samples[-self.max_knn_samples:]

        # 카테고리별 위치 패턴 학습
        category_positions = defaultdict(list)
        all_x = []

        for comp in components:
            x = comp.get('x') or comp.get('position_x')
            if x is not None:
                all_x.append(float(x))
                category = comp.get('category', 'Unknown')
                category_positions[category].append(float(x))

        if all_x:
            min_x, max_x = min(all_x), max(all_x)
            x_range = max_x - min_x if max_x > min_x else 1

            for category, positions in category_positions.items():
                avg_x = sum(positions) / len(positions)
                relative_pos = (avg_x - min_x) / x_range  # 0~1 범위

                if relative_pos < 0.33:
                    flow_position = "start"
                elif relative_pos > 0.66:
                    flow_position = "end"
                else:
                    flow_position = "middle"

                if category not in self.category_patterns:
                    self.category_patterns[category] = CategoryPattern(category=category)

                self.category_patterns[category].flow_position = flow_position
                self.category_patterns[category].sample_count += len(positions)

        # =====================================================================
        # NEW: 추가 패턴 학습
        # =====================================================================

        # 1. 분기 패턴 학습 (한 소스 → 여러 타겟)
        outgoing_map = defaultdict(list)  # source_guid -> [(target_guid, y_offset)]
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                src = comp_map[src_guid]
                tgt = comp_map[tgt_guid]
                src_y = float(src.get('y') or src.get('position_y') or 0)
                tgt_y = float(tgt.get('y') or tgt.get('position_y') or 0)
                outgoing_map[src_guid].append((tgt_guid, tgt_y - src_y))

        for src_guid, targets in outgoing_map.items():
            if len(targets) >= 2:  # 분기
                src = comp_map[src_guid]
                src_name = src.get('name', '')
                src_type = comp_types.get(src_guid, ComponentType.UNKNOWN).value

                # Y 오프셋 정렬
                y_offsets = sorted([t[1] for t in targets])
                y_spacing = (y_offsets[-1] - y_offsets[0]) / (len(y_offsets) - 1) if len(y_offsets) > 1 else 0

                key = f"{src_name}_{len(targets)}"
                if key in self.branching_patterns:
                    # 기존 패턴 업데이트
                    existing = self.branching_patterns[key]
                    existing.y_spacing = (existing.y_spacing * existing.sample_count + y_spacing) / (existing.sample_count + 1)
                    existing.sample_count += 1
                else:
                    self.branching_patterns[key] = BranchingPattern(
                        source_name=src_name,
                        source_type=src_type,
                        target_count=len(targets),
                        y_spacing=y_spacing,
                        y_offsets=y_offsets
                    )

        # 2. 병합 패턴 학습 (여러 소스 → 한 타겟)
        incoming_map = defaultdict(list)  # target_guid -> [(source_guid, y_offset)]
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                src = comp_map[src_guid]
                tgt = comp_map[tgt_guid]
                src_y = float(src.get('y') or src.get('position_y') or 0)
                tgt_y = float(tgt.get('y') or tgt.get('position_y') or 0)
                incoming_map[tgt_guid].append((src_guid, src_y - tgt_y))

        for tgt_guid, sources in incoming_map.items():
            if len(sources) >= 2:  # 병합
                tgt = comp_map[tgt_guid]
                tgt_name = tgt.get('name', '')
                tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN).value

                # Y 오프셋 정렬
                y_offsets = sorted([s[1] for s in sources])
                y_spacing = (y_offsets[-1] - y_offsets[0]) / (len(y_offsets) - 1) if len(y_offsets) > 1 else 0

                key = f"{tgt_name}_{len(sources)}"
                if key in self.merging_patterns:
                    existing = self.merging_patterns[key]
                    existing.y_spacing = (existing.y_spacing * existing.sample_count + y_spacing) / (existing.sample_count + 1)
                    existing.sample_count += 1
                else:
                    self.merging_patterns[key] = MergingPattern(
                        target_name=tgt_name,
                        target_type=tgt_type,
                        source_count=len(sources),
                        y_spacing=y_spacing,
                        y_offsets=y_offsets
                    )

        # 3. 입력 그룹 패턴 학습 (같은 타입 입력 컴포넌트들)
        input_components = defaultdict(list)  # component_name -> [y_positions]
        for guid, comp in comp_map.items():
            comp_type = comp_types.get(guid, ComponentType.UNKNOWN)
            if comp_type == ComponentType.INPUT_PARAM:
                name = comp.get('name', '')
                y = float(comp.get('y') or comp.get('position_y') or 0)
                input_components[name].append(y)

        for name, y_positions in input_components.items():
            if len(y_positions) >= 2:
                sorted_ys = sorted(y_positions)
                spacings = [sorted_ys[i+1] - sorted_ys[i] for i in range(len(sorted_ys)-1)]
                avg_spacing = sum(spacings) / len(spacings) if spacings else 0

                if name in self.input_group_patterns:
                    existing = self.input_group_patterns[name]
                    existing.avg_y_spacing = (existing.avg_y_spacing * existing.sample_count + avg_spacing) / (existing.sample_count + 1)
                    existing.typical_count = max(existing.typical_count, len(y_positions))
                    existing.sample_count += 1
                else:
                    self.input_group_patterns[name] = InputGroupPattern(
                        component_type=name,
                        avg_y_spacing=avg_spacing,
                        typical_count=len(y_positions)
                    )

        # 4. 시퀀스 패턴 학습 (연속 체인)
        # 간단한 체인 감지: A→B→C (A가 유일한 출력, B가 유일한 입력/출력)
        for src_guid in comp_map:
            if len(outgoing_map[src_guid]) == 1:  # 단일 출력
                chain = [comp_map[src_guid].get('name', '')]
                x_spacings = []
                current = src_guid

                while True:
                    targets = outgoing_map.get(current, [])
                    if len(targets) != 1:
                        break
                    next_guid = targets[0][0]
                    if next_guid not in comp_map:
                        break

                    # X 간격 계산
                    curr_x = float(comp_map[current].get('x') or 0)
                    next_x = float(comp_map[next_guid].get('x') or 0)
                    x_spacings.append(next_x - curr_x)

                    chain.append(comp_map[next_guid].get('name', ''))
                    current = next_guid

                    # 체인 최대 5개
                    if len(chain) >= 5:
                        break

                if len(chain) >= 3:  # 최소 3개 연속
                    self.sequence_patterns.append(SequencePattern(
                        component_sequence=chain,
                        x_spacings=x_spacings
                    ))

        # 시퀀스 패턴 최대 100개 유지
        if len(self.sequence_patterns) > 100:
            self.sequence_patterns = self.sequence_patterns[-100:]

        # =====================================================================
        # NEW v4.0: 추가 고급 패턴 학습
        # =====================================================================

        # 5. 클러스터 간격 패턴 학습
        # 연결되지 않은 컴포넌트 그룹 간 간격 분석
        neighbors = defaultdict(set)
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                neighbors[src_guid].add(tgt_guid)
                neighbors[tgt_guid].add(src_guid)

        visited_for_cluster = set()
        clusters = []
        for start_guid in comp_map:
            if start_guid in visited_for_cluster:
                continue
            cluster = set()
            queue = [start_guid]
            while queue:
                guid = queue.pop(0)
                if guid in visited_for_cluster:
                    continue
                visited_for_cluster.add(guid)
                cluster.add(guid)
                for neighbor in neighbors[guid]:
                    if neighbor not in visited_for_cluster:
                        queue.append(neighbor)
            if cluster:
                clusters.append(cluster)

        if len(clusters) >= 2:
            # 클러스터 간 Y 간격 계산
            cluster_bounds = []
            for cluster in clusters:
                ys = [float(comp_map[g].get('y') or 0) for g in cluster]
                xs = [float(comp_map[g].get('x') or 0) for g in cluster]
                if ys and xs:
                    cluster_bounds.append({
                        'min_y': min(ys), 'max_y': max(ys),
                        'min_x': min(xs), 'max_x': max(xs),
                        'center_y': sum(ys) / len(ys)
                    })

            cluster_bounds.sort(key=lambda c: c['center_y'])
            y_gaps = []
            for i in range(len(cluster_bounds) - 1):
                gap = cluster_bounds[i + 1]['min_y'] - cluster_bounds[i]['max_y']
                if gap > 0:
                    y_gaps.append(gap)

            if y_gaps:
                avg_gap = sum(y_gaps) / len(y_gaps)
                old_count = self.cluster_spacing_pattern.sample_count
                old_avg = self.cluster_spacing_pattern.avg_y_gap
                self.cluster_spacing_pattern.avg_y_gap = (old_avg * old_count + avg_gap) / (old_count + 1)
                self.cluster_spacing_pattern.sample_count += 1

        # 6. 포트 정렬 패턴 학습 (타겟의 입력 포트 순서에 따른 소스 Y 배치)
        for tgt_guid, sources in incoming_map.items():
            if len(sources) >= 2:
                tgt = comp_map[tgt_guid]
                tgt_name = tgt.get('name', '')

                # 소스들을 입력 포트 순서대로 정렬
                sources_with_port = []
                for wire in wires:
                    if str(wire.get('target_guid', '')) == tgt_guid:
                        src_guid = str(wire.get('source_guid', ''))
                        if src_guid in comp_map:
                            port_index = wire.get('target_input', 0)
                            src_name = comp_map[src_guid].get('name', '')
                            src_y = float(comp_map[src_guid].get('y') or 0)
                            sources_with_port.append((port_index, src_y, src_name))

                # 포트 순서와 Y 순서 비교
                port_sorted = sorted(sources_with_port, key=lambda x: x[0])
                y_sorted = sorted(sources_with_port, key=lambda x: x[1])

                # 포트 순서대로 Y 배치되어 있으면 패턴 학습
                port_order_names = [s[2] for s in port_sorted]
                y_order_names = [s[2] for s in y_sorted]

                if port_order_names == y_order_names:
                    # 포트 순서 = Y 순서 (좋은 배치)
                    if tgt_name in self.port_alignment_patterns:
                        self.port_alignment_patterns[tgt_name].sample_count += 1
                    else:
                        self.port_alignment_patterns[tgt_name] = PortAlignmentPattern(
                            target_name=tgt_name,
                            source_y_order=port_order_names
                        )

        # 7. 와이어 교차 선호 패턴 학습 (소스-타겟 Y 관계)
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))

            if src_guid in comp_map and tgt_guid in comp_map:
                src = comp_map[src_guid]
                tgt = comp_map[tgt_guid]
                src_y = float(src.get('y') or 0)
                tgt_y = float(tgt.get('y') or 0)

                src_type = comp_types.get(src_guid, ComponentType.UNKNOWN).value
                tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN).value
                key = f"{src_type}_{tgt_type}"

                # Y 관계 판단
                diff = tgt_y - src_y
                if abs(diff) < 30:
                    y_order = "same"
                elif diff > 0:
                    y_order = "above"  # 소스가 위
                else:
                    y_order = "below"  # 소스가 아래

                if key in self.wire_crossing_patterns:
                    existing = self.wire_crossing_patterns[key]
                    existing.sample_count += 1
                    # 다수결로 선호 순서 결정
                    if y_order == existing.preferred_y_order:
                        existing.confidence = min(1.0, existing.confidence + 0.05)
                else:
                    self.wire_crossing_patterns[key] = WireCrossingPattern(
                        preferred_y_order=y_order,
                        confidence=0.5
                    )

        # 8. 밀도 패턴 학습
        if all_x:
            x_span = max(all_x) - min(all_x) if len(all_x) > 1 else 100
            all_y = [float(comp.get('y') or 0) for comp in components if comp.get('y')]
            y_span = max(all_y) - min(all_y) if len(all_y) > 1 else 100

            # X 레벨 수 계산 (대략적인 행 수)
            x_groups = defaultdict(int)
            for x in all_x:
                x_group = round(x / 150) * 150  # 150 단위로 그룹화
                x_groups[x_group] += 1

            num_rows = len(x_groups) if x_groups else 1
            avg_per_row = len(components) / num_rows

            old_count = self.density_pattern.sample_count
            if old_count > 0:
                self.density_pattern.avg_components_per_row = (
                    self.density_pattern.avg_components_per_row * old_count + avg_per_row
                ) / (old_count + 1)
                self.density_pattern.avg_x_span = (
                    self.density_pattern.avg_x_span * old_count + x_span
                ) / (old_count + 1)
                self.density_pattern.avg_y_span = (
                    self.density_pattern.avg_y_span * old_count + y_span
                ) / (old_count + 1)
            else:
                self.density_pattern.avg_components_per_row = avg_per_row
                self.density_pattern.avg_x_span = x_span
                self.density_pattern.avg_y_span = y_span

            self.density_pattern.sample_count += 1

        # =====================================================================
        # NEW v5.0: 서브그래프 템플릿 추출
        # =====================================================================
        subgraph_templates_learned = 0

        # 서브그래프 추출: 2~5개 노드의 연결된 서브그래프 찾기
        def extract_subgraphs(start_guid: str, max_depth: int = 4) -> List[List[str]]:
            """BFS로 시작 노드에서 max_depth까지의 서브그래프들 추출"""
            subgraphs = []

            def bfs_subgraph(start: str, depth: int):
                if depth == 0:
                    return [[start]]

                result = [[start]]
                visited = {start}
                queue = [(start, 0)]

                while queue:
                    current, d = queue.pop(0)
                    if d >= depth:
                        continue

                    # 나가는 연결만 따라감 (순방향 서브그래프)
                    for next_guid in outgoing_map.get(current, []):
                        next_g = next_guid[0] if isinstance(next_guid, tuple) else next_guid
                        if next_g not in visited and next_g in comp_map:
                            visited.add(next_g)
                            # 현재까지의 모든 경로에 새 노드 추가
                            new_paths = []
                            for path in result:
                                if current in path:
                                    new_path = path + [next_g]
                                    new_paths.append(new_path)
                            result.extend(new_paths)
                            queue.append((next_g, d + 1))

                # 2개 이상 노드를 가진 서브그래프만 반환
                return [sg for sg in result if len(sg) >= 2]

            return bfs_subgraph(start_guid, max_depth)

        # 모든 소스 노드(입력이 없는 노드)에서 서브그래프 추출
        source_nodes = [g for g in comp_map if len(incoming_map.get(g, [])) == 0]

        for src_guid in source_nodes:
            subgraphs = extract_subgraphs(src_guid, max_depth=4)

            for sg_guids in subgraphs:
                if len(sg_guids) < 2 or len(sg_guids) > 5:
                    continue

                # 서브그래프 키 생성 (컴포넌트 이름 시퀀스)
                sg_names = [comp_map[g].get('name', '') for g in sg_guids]
                pattern_key = "->".join(sg_names)

                # 이미 학습된 템플릿인지 확인
                if pattern_key in self.subgraph_templates:
                    # 기존 템플릿 업데이트 (평균 위치 갱신)
                    existing = self.subgraph_templates[pattern_key]
                    existing.sample_count += 1
                    continue

                # 새 템플릿 생성
                # 첫 노드 기준 상대 좌표 계산
                first_x = float(comp_map[sg_guids[0]].get('x') or 0)
                first_y = float(comp_map[sg_guids[0]].get('y') or 0)

                nodes = []
                for i, g in enumerate(sg_guids):
                    comp = comp_map[g]
                    x = float(comp.get('x') or 0)
                    y = float(comp.get('y') or 0)
                    nodes.append(SubgraphNode(
                        name=comp.get('name', ''),
                        comp_type=comp_types.get(g, ComponentType.UNKNOWN).value,
                        relative_x=x - first_x,
                        relative_y=y - first_y,
                        index=i
                    ))

                # 엣지 정보 (서브그래프 내 연결)
                edges = []
                guid_to_idx = {g: i for i, g in enumerate(sg_guids)}
                for i, src_g in enumerate(sg_guids):
                    for tgt_info in outgoing_map.get(src_g, []):
                        tgt_g = tgt_info[0] if isinstance(tgt_info, tuple) else tgt_info
                        if tgt_g in guid_to_idx:
                            edges.append((i, guid_to_idx[tgt_g]))

                # 레이아웃 범위 계산
                xs = [n.relative_x for n in nodes]
                ys = [n.relative_y for n in nodes]
                width = max(xs) - min(xs) if xs else 0
                height = max(ys) - min(ys) if ys else 0

                template = SubgraphTemplate(
                    pattern_key=pattern_key,
                    nodes=nodes,
                    edges=edges,
                    node_count=len(nodes),
                    avg_width=width,
                    avg_height=height
                )
                self.subgraph_templates[pattern_key] = template
                subgraph_templates_learned += 1

        # 템플릿 최대 개수 유지 (sample_count가 낮은 것 제거)
        if len(self.subgraph_templates) > self.max_subgraph_templates:
            sorted_templates = sorted(
                self.subgraph_templates.items(),
                key=lambda x: x[1].sample_count,
                reverse=True
            )
            self.subgraph_templates = dict(sorted_templates[:self.max_subgraph_templates])

        # =====================================================================
        # NEW v6.0: Y 순서 패턴 학습 (같은 X 레벨에서 컴포넌트 쌍의 Y 순서)
        # =====================================================================
        y_order_patterns_learned = 0

        # X 레벨별로 컴포넌트 그룹화 (150 단위)
        x_level_groups = defaultdict(list)
        for guid, comp in comp_map.items():
            x = float(comp.get('x') or comp.get('position_x') or 0)
            x_level = round(x / 150) * 150
            x_level_groups[x_level].append(guid)

        # 각 X 레벨에서 컴포넌트 쌍의 Y 순서 학습
        for x_level, guids in x_level_groups.items():
            if len(guids) < 2:
                continue

            # 모든 쌍에 대해 Y 순서 학습
            for i in range(len(guids)):
                for j in range(i + 1, len(guids)):
                    guid_a, guid_b = guids[i], guids[j]
                    comp_a, comp_b = comp_map[guid_a], comp_map[guid_b]

                    name_a = comp_a.get('name', '')
                    name_b = comp_b.get('name', '')
                    type_a = comp_types.get(guid_a, ComponentType.UNKNOWN).value
                    type_b = comp_types.get(guid_b, ComponentType.UNKNOWN).value

                    y_a = float(comp_a.get('y') or comp_a.get('position_y') or 0)
                    y_b = float(comp_b.get('y') or comp_b.get('position_y') or 0)

                    if not name_a or not name_b:
                        continue

                    # 이름 기반 키 (정렬하여 일관성 유지)
                    if name_a <= name_b:
                        key = f"({name_a}, {name_b})"
                        a_is_first = True
                    else:
                        key = f"({name_b}, {name_a})"
                        a_is_first = False

                    # 패턴 가져오거나 생성
                    if key not in self.y_order_patterns:
                        if a_is_first:
                            self.y_order_patterns[key] = YOrderPattern(comp_a=name_a, comp_b=name_b)
                        else:
                            self.y_order_patterns[key] = YOrderPattern(comp_a=name_b, comp_b=name_a)

                    pattern = self.y_order_patterns[key]

                    # Y 순서 업데이트 (Y가 작을수록 위)
                    if a_is_first:
                        if y_a < y_b:  # A가 위
                            pattern.a_above_count += 1
                        else:
                            pattern.b_above_count += 1
                    else:
                        if y_a < y_b:  # A(원래)가 위 = B(키에서)가 아래
                            pattern.b_above_count += 1
                        else:
                            pattern.a_above_count += 1

                    pattern.sample_count += 1
                    y_order_patterns_learned += 1

                    # 타입 기반 Y 순서도 학습
                    if type_a <= type_b:
                        type_key = f"({type_a}, {type_b})"
                        type_a_is_first = True
                    else:
                        type_key = f"({type_b}, {type_a})"
                        type_a_is_first = False

                    if type_key not in self.y_order_by_type:
                        if type_a_is_first:
                            self.y_order_by_type[type_key] = YOrderByTypePattern(type_a=type_a, type_b=type_b)
                        else:
                            self.y_order_by_type[type_key] = YOrderByTypePattern(type_a=type_b, type_b=type_a)

                    type_pattern = self.y_order_by_type[type_key]

                    if type_a_is_first:
                        if y_a < y_b:
                            type_pattern.a_above_count += 1
                        else:
                            type_pattern.b_above_count += 1
                    else:
                        if y_a < y_b:
                            type_pattern.b_above_count += 1
                        else:
                            type_pattern.a_above_count += 1

                    type_pattern.sample_count += 1

        # =====================================================================
        # NEW v7.0: 토폴로지 레벨 학습 (좌→우 수평 배치를 위한 레벨 학습)
        # =====================================================================
        topology_patterns_learned = 0

        # 연결 관계 구축 (incoming, outgoing)
        incoming: Dict[str, set] = defaultdict(set)
        outgoing: Dict[str, set] = defaultdict(set)
        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                outgoing[src_guid].add(tgt_guid)
                incoming[tgt_guid].add(src_guid)

        # BFS로 토폴로지 레벨 계산 (소스 노드에서 시작)
        # incoming이 없는 노드 = 소스 노드 (레벨 0)
        source_nodes = [guid for guid in comp_map if len(incoming.get(guid, set())) == 0]

        # BFS로 각 노드의 레벨 계산
        node_levels: Dict[str, int] = {}
        queue = [(guid, 0) for guid in source_nodes]
        visited = set()

        while queue:
            guid, level = queue.pop(0)
            if guid in visited:
                # 이미 방문한 노드는 더 큰 레벨로 업데이트 (가장 긴 경로 기준)
                if guid in node_levels and level > node_levels[guid]:
                    node_levels[guid] = level
                continue

            visited.add(guid)
            node_levels[guid] = max(node_levels.get(guid, 0), level)

            # 다음 노드들 추가
            for tgt_guid in outgoing.get(guid, set()):
                queue.append((tgt_guid, level + 1))

        # 연결 안 된 노드들 처리 (X 좌표 기준으로 레벨 추정)
        if node_levels:
            max_level = max(node_levels.values())
            self.max_topology_level = max(self.max_topology_level, max_level)

            # X 좌표별 평균 레벨 계산
            level_x_coords = defaultdict(list)
            for guid, level in node_levels.items():
                comp = comp_map.get(guid, {})
                x = float(comp.get('x') or comp.get('position_x') or 0)
                level_x_coords[level].append(x)

            level_avg_x = {level: sum(xs)/len(xs) for level, xs in level_x_coords.items()}

            # 연결 안 된 노드들은 X 좌표로 레벨 추정
            for guid in comp_map:
                if guid not in node_levels:
                    comp = comp_map.get(guid, {})
                    x = float(comp.get('x') or comp.get('position_x') or 0)

                    # 가장 가까운 레벨 찾기
                    closest_level = 0
                    min_diff = float('inf')
                    for level, avg_x in level_avg_x.items():
                        diff = abs(x - avg_x)
                        if diff < min_diff:
                            min_diff = diff
                            closest_level = level

                    node_levels[guid] = closest_level

        # 컴포넌트별 토폴로지 레벨 학습
        for guid, level in node_levels.items():
            comp = comp_map.get(guid, {})
            name = comp.get('name', '')
            comp_type = comp_types.get(guid, ComponentType.UNKNOWN).value

            if not name:
                continue

            # 이름 기반 패턴
            if name not in self.topology_level_patterns:
                self.topology_level_patterns[name] = TopologyLevelPattern(component_name=name)

            pattern = self.topology_level_patterns[name]
            if level not in pattern.level_counts:
                pattern.level_counts[level] = 0
            pattern.level_counts[level] += 1
            pattern.total_samples += 1
            topology_patterns_learned += 1

            # 타입 기반 패턴
            if comp_type not in self.topology_level_by_type:
                self.topology_level_by_type[comp_type] = TopologyLevelByTypePattern(component_type=comp_type)

            type_pattern = self.topology_level_by_type[comp_type]
            if level not in type_pattern.level_counts:
                type_pattern.level_counts[level] = 0
            type_pattern.level_counts[level] += 1
            type_pattern.total_samples += 1

        # 레벨 간 X 간격 학습
        for src_guid in comp_map:
            src_level = node_levels.get(src_guid, 0)
            src_comp = comp_map.get(src_guid, {})
            src_x = float(src_comp.get('x') or src_comp.get('position_x') or 0)

            for tgt_guid in outgoing.get(src_guid, set()):
                tgt_level = node_levels.get(tgt_guid, 0)
                tgt_comp = comp_map.get(tgt_guid, {})
                tgt_x = float(tgt_comp.get('x') or tgt_comp.get('position_x') or 0)

                if tgt_level > src_level:  # 순방향 연결만
                    x_spacing = tgt_x - src_x

                    level_key = f"({src_level}, {tgt_level})"
                    if level_key not in self.x_spacing_by_level:
                        self.x_spacing_by_level[level_key] = XSpacingByLevelPattern(
                            from_level=src_level,
                            to_level=tgt_level
                        )

                    spacing_pattern = self.x_spacing_by_level[level_key]
                    spacing_pattern.x_spacings.append(x_spacing)
                    if len(spacing_pattern.x_spacings) > 100:  # 최대 100개 샘플
                        spacing_pattern.x_spacings = spacing_pattern.x_spacings[-100:]
                    spacing_pattern.sample_count += 1

        # =====================================================================
        # NEW v8.0: 연결 대상 기반 상대 위치 학습
        # =====================================================================
        relative_patterns_learned = 0

        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))

            if src_guid not in comp_map or tgt_guid not in comp_map:
                continue

            src_comp = comp_map[src_guid]
            tgt_comp = comp_map[tgt_guid]

            src_name = src_comp.get('name', '')
            tgt_name = tgt_comp.get('name', '')
            src_type = comp_types.get(src_guid, ComponentType.UNKNOWN).value
            tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN).value

            src_x = float(src_comp.get('x') or src_comp.get('position_x') or 0)
            src_y = float(src_comp.get('y') or src_comp.get('position_y') or 0)
            tgt_x = float(tgt_comp.get('x') or tgt_comp.get('position_x') or 0)
            tgt_y = float(tgt_comp.get('y') or tgt_comp.get('position_y') or 0)

            # 상대 오프셋 계산 (소스 - 타겟)
            x_offset = src_x - tgt_x  # 음수면 소스가 왼쪽
            y_offset = src_y - tgt_y

            if not src_name or not tgt_name:
                continue

            # 이름 기반 패턴 (방향성 있음: src -> tgt)
            name_key = f"({src_name}, {tgt_name})"
            if name_key not in self.relative_position_patterns:
                self.relative_position_patterns[name_key] = RelativePositionPattern(
                    source_name=src_name,
                    target_name=tgt_name
                )

            pattern = self.relative_position_patterns[name_key]
            pattern.x_offsets.append(x_offset)
            pattern.y_offsets.append(y_offset)
            if len(pattern.x_offsets) > 100:
                pattern.x_offsets = pattern.x_offsets[-100:]
                pattern.y_offsets = pattern.y_offsets[-100:]
            pattern.sample_count += 1
            relative_patterns_learned += 1

            # 타입 기반 패턴
            type_key = f"({src_type}, {tgt_type})"
            if type_key not in self.relative_position_by_type:
                self.relative_position_by_type[type_key] = RelativePositionByTypePattern(
                    source_type=src_type,
                    target_type=tgt_type
                )

            type_pattern = self.relative_position_by_type[type_key]
            type_pattern.x_offsets.append(x_offset)
            type_pattern.y_offsets.append(y_offset)
            if len(type_pattern.x_offsets) > 200:
                type_pattern.x_offsets = type_pattern.x_offsets[-200:]
                type_pattern.y_offsets = type_pattern.y_offsets[-200:]
            type_pattern.sample_count += 1

        # 세션 기록
        session = LearningSession(
            session_id=f"session_{self.total_sessions + 1}",
            timestamp=datetime.now().isoformat(),
            source_file=source_file,
            component_count=len(components),
            wire_count=len(wires),
            patterns_learned=patterns_learned
        )
        self.learning_sessions.append(session)

        self.total_sessions += 1
        self.total_components_learned += len(components)

        # 자동 저장
        self.save()

        return {
            "success": True,
            "session_id": session.session_id,
            "patterns_learned": patterns_learned,
            "total_component_patterns": len(self.component_patterns),
            "spacing_samples": self.spacing_pattern.sample_count,
            "avg_spacing_x": round(self.spacing_pattern.avg_x, 1),
            "avg_spacing_y": round(self.spacing_pattern.avg_y, 1),

            # NEW: 연결 유형별 통계
            "connection_type_stats": {
                conn_type: {
                    "count": count,
                    "avg_x": round(self.connection_spacing[conn_type].avg_x, 1),
                    "avg_y": round(self.connection_spacing[conn_type].avg_y, 1)
                }
                for conn_type, count in connection_type_counts.items()
            },

            # NEW: 타입별 컴포넌트 수
            "component_types": {
                comp_type.value: sum(1 for t in comp_types.values() if t == comp_type)
                for comp_type in set(comp_types.values())
            }
        }

    # =========================================================================
    # GH File Learning (GH 파일 학습)
    # =========================================================================

    def learn_from_gh_file(self, file_path: str) -> dict:
        """
        단일 GH 파일에서 레이아웃 패턴 학습

        Args:
            file_path: GH 파일 경로 (.gh 또는 .ghx)

        Returns:
            학습 결과 (patterns_learned, success 등)
        """
        try:
            # gh_file_ops 모듈에서 파싱 함수 임포트
            from ..gh_file_ops import parse_gh_definition

            # GH 파일 파싱
            definition = parse_gh_definition(file_path)

            # 컴포넌트를 learn_from_canvas 형식으로 변환
            components = []
            for comp in definition.components:
                components.append({
                    'guid': comp.instance_guid or comp.guid,
                    'name': comp.name,
                    'nickname': comp.nickname,
                    'category': comp.category,
                    'subcategory': comp.subcategory,
                    'x': comp.position_x,
                    'y': comp.position_y,
                    'position_x': comp.position_x,
                    'position_y': comp.position_y,
                })

            # 와이어를 learn_from_canvas 형식으로 변환
            wires = []
            for wire in definition.wires:
                wires.append({
                    'source_guid': wire.source_component,
                    'target_guid': wire.target_component,
                    'source_output': int(wire.source_param) if wire.source_param.isdigit() else 0,
                    'target_input': int(wire.target_param) if wire.target_param.isdigit() else 0,
                })

            # 기존 learn_from_canvas 호출
            result = self.learn_from_canvas(
                components=components,
                wires=wires,
                source_file=file_path
            )

            return {
                **result,
                'file': file_path,
                'components_in_file': len(components),
                'wires_in_file': len(wires),
            }

        except FileNotFoundError:
            return {
                'success': False,
                'error': f'File not found: {file_path}',
                'file': file_path
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'file': file_path
            }

    def learn_from_gh_files(self, file_paths: List[str]) -> dict:
        """
        여러 GH 파일에서 레이아웃 패턴 일괄 학습

        Args:
            file_paths: GH 파일 경로 리스트

        Returns:
            학습 결과 요약 (files_processed, total_patterns 등)
        """
        results = []
        total_patterns = 0
        successful_files = 0

        for path in file_paths:
            result = self.learn_from_gh_file(path)
            results.append(result)

            if result.get('success', False):
                successful_files += 1
                total_patterns += result.get('patterns_learned', 0)

        return {
            'success': successful_files > 0,
            'files_processed': len(file_paths),
            'successful_files': successful_files,
            'failed_files': len(file_paths) - successful_files,
            'total_patterns': total_patterns,
            'total_component_patterns': len(self.component_patterns),
            'spacing_samples': self.spacing_pattern.sample_count,
            'details': results
        }

    # =========================================================================
    # Position Prediction (위치 예측)
    # =========================================================================

    def get_optimal_position(
        self,
        component_name: str,
        connected_to: Optional[dict] = None,
        direction: str = "right",
        source_component_name: Optional[str] = None
    ) -> dict:
        """
        학습된 패턴을 기반으로 최적 위치 예측

        Args:
            component_name: 추가할 컴포넌트 이름
            connected_to: 연결될 컴포넌트 정보 {x, y, guid, name, category}
            direction: 배치 방향 ("right", "down", "left", "up")
            source_component_name: 소스 컴포넌트 이름 (연결 유형 판단용)

        Returns:
            {x, y, confidence, reasoning, source, connection_type, component_types}
        """
        # 기본 오프셋
        direction_offsets = {
            "right": (150, 0),
            "down": (0, 80),
            "left": (-150, 0),
            "up": (0, -80)
        }

        offset_x = 150.0
        offset_y = 0.0
        confidence = 0.3
        source = "default"
        conn_type = None

        # 타겟 컴포넌트 타입 분류
        target_type = classify_component_type(
            name=component_name,
            category=connected_to.get('category', '') if connected_to else '',
        )

        # 소스 컴포넌트 타입 분류 (connected_to에서 가져오거나 source_component_name 사용)
        source_name = source_component_name or (connected_to.get('name', '') if connected_to else '')
        source_type = classify_component_type(
            name=source_name,
            category=connected_to.get('category', '') if connected_to else '',
        ) if source_name else ComponentType.UNKNOWN

        # 연결 유형 결정 (소스 → 타겟 방향)
        if source_type != ComponentType.UNKNOWN:
            conn_type = get_connection_type(source_type, target_type)

        # 우선순위: 연결 유형별 패턴 > 컴포넌트별 패턴 > 전역 패턴 > 기본값

        # 1. 연결 유형별 패턴 확인 (NEW!)
        if conn_type and conn_type in self.connection_spacing:
            conn_pattern = self.connection_spacing[conn_type]
            if conn_pattern.sample_count >= 5:
                offset_x = conn_pattern.avg_x
                offset_y = conn_pattern.avg_y
                confidence = min(0.90, 0.65 + (conn_pattern.sample_count / 100) * 0.25)
                source = f"connection_type:{conn_type} ({conn_pattern.sample_count} samples)"

        # 2. 컴포넌트별 학습된 패턴으로 보정
        if source_name and source_name in self.component_patterns:
            pattern = self.component_patterns[source_name]
            if pattern.sample_count >= 3:
                # 컴포넌트별 패턴과 연결 유형 패턴을 가중 평균
                if conn_type and source != "default":
                    # 둘 다 있으면 가중 평균 (연결 유형 60%, 컴포넌트 40%)
                    offset_x = offset_x * 0.6 + pattern.avg_offset_x * 0.4
                    offset_y = offset_y * 0.6 + pattern.avg_offset_y * 0.4
                    confidence = min(0.95, confidence + 0.05)
                    source = f"{source} + component:{source_name}"
                else:
                    # 연결 유형 패턴이 없으면 컴포넌트 패턴 사용
                    offset_x = pattern.avg_offset_x
                    offset_y = pattern.avg_offset_y
                    confidence = min(0.90, 0.6 + pattern.weight * 0.15)
                    source = f"component_pattern:{source_name} ({pattern.sample_count} samples)"

        # 3. 전역 패턴 폴백
        if source == "default" and self.spacing_pattern.sample_count >= 5:
            offset_x = self.spacing_pattern.avg_x
            offset_y = self.spacing_pattern.avg_y
            confidence = 0.55
            source = f"global_spacing ({self.spacing_pattern.sample_count} samples)"

        # 4. 최종 기본값
        if source == "default":
            base = direction_offsets.get(direction, (150, 0))
            offset_x, offset_y = float(base[0]), float(base[1])

        # 방향 반영
        if direction == "left":
            offset_x = -abs(offset_x)
        elif direction == "up":
            offset_y = -abs(offset_y)
        elif direction == "down":
            offset_y = abs(offset_y) if offset_y != 0 else 80.0

        # 연결 대상이 있으면 상대 위치 계산
        if connected_to:
            base_x = float(connected_to.get('x') or connected_to.get('position_x') or 0)
            base_y = float(connected_to.get('y') or connected_to.get('position_y') or 0)

            predicted_x = base_x + offset_x
            predicted_y = base_y + offset_y

            reasoning = f"Based on {source}, offset ({offset_x:.1f}, {offset_y:.1f}) from connected component"
        else:
            predicted_x = 500 + offset_x
            predicted_y = 300 + offset_y
            reasoning = f"Default position with {source} offset"

        return {
            "x": round(predicted_x, 1),
            "y": round(predicted_y, 1),
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
            "source": source,
            "offset_used": {"x": round(offset_x, 1), "y": round(offset_y, 1)},
            # NEW: 타입 정보 추가
            "connection_type": conn_type,
            "source_type": source_type.value if source_type else None,
            "target_type": target_type.value
        }

    # =========================================================================
    # Statistics & Summary
    # =========================================================================

    def get_learning_summary(self) -> dict:
        """학습 상태 요약"""
        top_patterns = sorted(
            self.component_patterns.values(),
            key=lambda p: p.sample_count,
            reverse=True
        )[:10]

        return {
            "version": self.version,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "storage_path": str(self.storage_path),

            "statistics": {
                "total_sessions": self.total_sessions,
                "total_components_learned": self.total_components_learned,
                "unique_component_patterns": len(self.component_patterns),
                "category_patterns": len(self.category_patterns),
                "spacing_samples": self.spacing_pattern.sample_count
            },

            "global_spacing": {
                "avg_x": round(self.spacing_pattern.avg_x, 1),
                "avg_y": round(self.spacing_pattern.avg_y, 1)
            },

            # NEW: 연결 유형별 간격 패턴
            "connection_spacing": {
                conn_type: {
                    "avg_x": round(pattern.avg_x, 1),
                    "avg_y": round(pattern.avg_y, 1),
                    "samples": pattern.sample_count
                }
                for conn_type, pattern in self.connection_spacing.items()
                if pattern.sample_count > 0
            },

            # NEW: 타입별 통계
            "type_statistics": self.type_statistics,

            "top_component_patterns": [
                {
                    "name": p.name,
                    "samples": p.sample_count,
                    "avg_offset": f"({p.avg_offset_x:.1f}, {p.avg_offset_y:.1f})",
                    "weight": round(p.weight, 2)
                }
                for p in top_patterns
            ],

            "recent_sessions": [
                {
                    "id": s.session_id,
                    "file": s.source_file,
                    "components": s.component_count,
                    "timestamp": s.timestamp
                }
                for s in self.learning_sessions[-5:]
            ]
        }

    def get_pattern_for_component(self, component_name: str) -> Optional[dict]:
        """특정 컴포넌트의 학습된 패턴 조회"""
        if component_name not in self.component_patterns:
            return None

        p = self.component_patterns[component_name]
        return {
            "name": p.name,
            "avg_offset_x": round(p.avg_offset_x, 1),
            "avg_offset_y": round(p.avg_offset_y, 1),
            "sample_count": p.sample_count,
            "weight": round(p.weight, 2),
            "last_updated": p.last_updated
        }

    # =========================================================================
    # KNN Prediction (KNN 예측)
    # =========================================================================

    def predict_offset_knn(
        self,
        source_name: str,
        target_name: str,
        source_type: str = "UNKNOWN",
        target_type: str = "UNKNOWN",
        k: int = 5
    ) -> Tuple[float, float, float]:
        """
        KNN 기반 오프셋 예측

        유사도 기준 (우선순위):
        1. 정확히 같은 (source_name, target_name) 쌍
        2. source_name만 같은 경우
        3. target_name만 같은 경우
        4. source_type, target_type이 같은 경우

        Args:
            source_name: 소스 컴포넌트 이름
            target_name: 타겟 컴포넌트 이름
            source_type: 소스 컴포넌트 타입
            target_type: 타겟 컴포넌트 타입
            k: 사용할 최근접 이웃 수

        Returns:
            (offset_x, offset_y, confidence): 예측된 오프셋과 신뢰도 (0~1)
        """
        if not self.connection_pair_samples:
            return (200.0, 0.0, 0.0)  # 학습 데이터 없음

        # 유사도 점수 계산
        scored_samples = []
        for sample in self.connection_pair_samples:
            score = 0.0

            # 정확한 매칭 (최고 점수)
            if sample.source_name == source_name and sample.target_name == target_name:
                score = 4.0
            # 소스만 매칭
            elif sample.source_name == source_name:
                score = 2.0
            # 타겟만 매칭
            elif sample.target_name == target_name:
                score = 1.5
            # 타입 매칭
            elif sample.source_type == source_type and sample.target_type == target_type:
                score = 1.0
            elif sample.source_type == source_type or sample.target_type == target_type:
                score = 0.5

            if score > 0:
                scored_samples.append((score, sample))

        if not scored_samples:
            # 학습 데이터에 유사한 케이스 없음 - 전역 평균 사용
            return (self.spacing_pattern.avg_x, self.spacing_pattern.avg_y, 0.1)

        # 점수순 정렬 후 상위 K개 선택
        scored_samples.sort(key=lambda x: x[0], reverse=True)
        top_k = scored_samples[:k]

        # 가중 평균 계산
        total_weight = sum(s[0] for s in top_k)
        offset_x = sum(s[0] * s[1].offset_x for s in top_k) / total_weight
        offset_y = sum(s[0] * s[1].offset_y for s in top_k) / total_weight

        # 신뢰도: 최고 점수 기반 (4.0이면 1.0)
        max_score = top_k[0][0]
        confidence = min(1.0, max_score / 4.0)

        return (offset_x, offset_y, confidence)

    # =========================================================================
    # Subgraph Template Matching (서브그래프 템플릿 매칭)
    # =========================================================================

    def find_matching_templates(
        self,
        comp_map: Dict[str, dict],
        outgoing: Dict[str, set],
        min_confidence: float = 0.8
    ) -> List[Tuple[str, List[str], SubgraphTemplate]]:
        """
        현재 캔버스에서 학습된 서브그래프 템플릿과 매칭되는 패턴 찾기

        Args:
            comp_map: GUID -> 컴포넌트 정보 맵
            outgoing: GUID -> 나가는 연결 GUID 집합
            min_confidence: 최소 매칭 신뢰도 (0~1)

        Returns:
            매칭된 (pattern_key, [guids], template) 리스트
        """
        if not self.subgraph_templates:
            return []

        matches = []
        used_guids = set()

        # 모든 소스 노드에서 시작하여 서브그래프 탐색
        source_guids = [g for g in comp_map if len(outgoing.get(g, set())) > 0]

        for start_guid in source_guids:
            if start_guid in used_guids:
                continue

            # BFS로 서브그래프 추출 및 템플릿 매칭
            queue = [(start_guid, [start_guid])]
            visited_paths = set()

            while queue:
                current_guid, path = queue.pop(0)
                path_key = tuple(path)

                if path_key in visited_paths:
                    continue
                visited_paths.add(path_key)

                # 현재 경로를 패턴 키로 변환
                path_names = [comp_map[g].get('name', '') for g in path]
                pattern_key = "->".join(path_names)

                # 템플릿 매칭 확인
                if pattern_key in self.subgraph_templates:
                    template = self.subgraph_templates[pattern_key]
                    # 중복 방지: 이미 사용된 GUID 제외
                    if not any(g in used_guids for g in path):
                        matches.append((pattern_key, path, template))
                        for g in path:
                            used_guids.add(g)
                        continue  # 매칭되면 더 확장하지 않음

                # 경로 확장 (최대 5개)
                if len(path) < 5:
                    for next_guid in outgoing.get(current_guid, set()):
                        if next_guid in comp_map and next_guid not in path:
                            new_path = path + [next_guid]
                            queue.append((next_guid, new_path))

        # sample_count 높은 순으로 정렬
        matches.sort(key=lambda x: x[2].sample_count, reverse=True)
        return matches

    def apply_template_positions(
        self,
        guids: List[str],
        template: SubgraphTemplate,
        base_x: float,
        base_y: float
    ) -> Dict[str, Tuple[float, float]]:
        """
        매칭된 템플릿의 상대 위치를 적용하여 절대 좌표 반환

        Args:
            guids: 매칭된 컴포넌트 GUID 리스트 (템플릿 노드 순서와 동일)
            template: 서브그래프 템플릿
            base_x: 첫 노드의 기준 X 좌표
            base_y: 첫 노드의 기준 Y 좌표

        Returns:
            {guid: (x, y)} 좌표 맵
        """
        positions = {}
        for i, guid in enumerate(guids):
            if i < len(template.nodes):
                node = template.nodes[i]
                positions[guid] = (
                    base_x + node.relative_x,
                    base_y + node.relative_y
                )
        return positions

    # =========================================================================
    # Auto Layout (자동 정렬) - 완전 KNN 기반 + 서브그래프 템플릿
    # =========================================================================

    def calculate_auto_layout(
        self,
        components: List[dict],
        wires: List[dict],
        start_x: float = 100.0,
        start_y: float = 100.0,
        row_height: float = 50.0
    ) -> dict:
        """
        완전 KNN 기반 레이아웃 계산

        전략:
        1. 연결된 컴포넌트 클러스터 분리 (BFS)
        2. 각 클러스터의 소스 노드(입력 없는 노드) 찾기
        3. BFS 순회: 각 타겟 위치 = 소스 위치 + KNN 예측 오프셋
        4. 겹침 방지 후처리

        Args:
            components: 컴포넌트 정보 리스트 [{guid, name, x, y, category, ...}]
            wires: 와이어 연결 리스트 [{source_guid, target_guid}]
            start_x: 시작 X 위치
            start_y: 시작 Y 위치
            row_height: 행 간격 (컴포넌트 높이 + 여백)

        Returns:
            {moves: [{guid, old_x, old_y, new_x, new_y}], summary}
        """
        if len(components) < 2:
            return {"success": False, "error": "Not enough components to layout", "moves": []}

        # =====================================================================
        # 1. 기본 데이터 구조 구축
        # =====================================================================

        comp_map = {}
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid:
                comp_map[str(guid)] = comp

        neighbors = defaultdict(set)
        outgoing = defaultdict(set)
        incoming = defaultdict(set)

        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                outgoing[src_guid].add(tgt_guid)
                incoming[tgt_guid].add(src_guid)
                neighbors[src_guid].add(tgt_guid)
                neighbors[tgt_guid].add(src_guid)

        # 컴포넌트 타입 분류
        comp_types = {}
        for guid, comp in comp_map.items():
            # 연결 기반 동적 타입 분류 사용 (Panel 등의 역할을 정확히 판단)
            comp_types[guid] = classify_by_connection(
                guid=guid,
                incoming=incoming,
                outgoing=outgoing,
                comp_map=comp_map
            )

        default_spacing = self.spacing_pattern.avg_x if self.spacing_pattern.sample_count > 5 else 200

        # Advanced ML learner integration
        try:
            from .advanced_layout_learner import get_advanced_learner
            advanced_learner = get_advanced_learner()
        except ImportError:
            advanced_learner = None

        def get_spacing(src_guid: str, tgt_guid: str) -> Tuple[float, float]:
            """Get spacing with KNN priority: exact pair > source match > type match > default
            Returns: (offset_x, offset_y)
            """
            src_comp = comp_map.get(src_guid, {})
            tgt_comp = comp_map.get(tgt_guid, {})
            src_name = src_comp.get('name', '')
            tgt_name = tgt_comp.get('name', '')
            src_type = comp_types.get(src_guid, ComponentType.UNKNOWN)
            tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN)

            # Priority 1: KNN prediction (새로 추가)
            if self.connection_pair_samples:
                offset_x, offset_y, confidence = self.predict_offset_knn(
                    source_name=src_name,
                    target_name=tgt_name,
                    source_type=src_type.value,
                    target_type=tgt_type.value,
                    k=5
                )
                if confidence >= 0.25:  # 25% 이상 신뢰도면 사용
                    return (offset_x, offset_y)

            # Priority 2: Advanced ML learned pair pattern (기존)
            if advanced_learner:
                learned = advanced_learner.get_learned_spacing(src_name, tgt_name)
                if learned:
                    dx, dy, confidence = learned
                    if confidence >= 0.5:
                        return (dx, dy)

            # Priority 3: Connection type pattern (기존)
            conn_type = get_connection_type(src_type, tgt_type)
            if conn_type in self.connection_spacing:
                pattern = self.connection_spacing[conn_type]
                if pattern.sample_count >= 3:
                    return (pattern.avg_x, pattern.avg_y)

            return (default_spacing, 0.0)

        def get_comp_height(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('height') or 50)

        def get_comp_width(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('width') or 100)

        def get_original_y(guid: str) -> float:
            comp = comp_map.get(guid, {})
            return float(comp.get('y') or comp.get('position_y') or 0)

        # =====================================================================
        # NEW v7.0: 토폴로지 레벨 계산 (좌→우 수평 배치)
        # =====================================================================

        def calculate_topology_levels() -> Dict[str, int]:
            """BFS로 각 컴포넌트의 토폴로지 레벨 계산"""
            node_levels: Dict[str, int] = {}

            # 소스 노드 찾기 (incoming이 없는 노드)
            source_nodes = [guid for guid in comp_map if len(incoming.get(guid, set())) == 0]

            # BFS로 레벨 할당
            queue = [(guid, 0) for guid in source_nodes]
            visited = set()

            while queue:
                guid, level = queue.pop(0)
                if guid in visited:
                    # 더 큰 레벨로 업데이트 (가장 긴 경로 기준)
                    if guid in node_levels and level > node_levels[guid]:
                        node_levels[guid] = level
                        # 후속 노드들도 업데이트 필요
                        for tgt_guid in outgoing.get(guid, set()):
                            queue.append((tgt_guid, level + 1))
                    continue

                visited.add(guid)
                node_levels[guid] = max(node_levels.get(guid, 0), level)

                for tgt_guid in outgoing.get(guid, set()):
                    queue.append((tgt_guid, level + 1))

            # 연결 안 된 노드들 처리
            for guid in comp_map:
                if guid not in node_levels:
                    # 학습된 패턴에서 레벨 추정
                    comp = comp_map.get(guid, {})
                    name = comp.get('name', '')
                    comp_type = comp_types.get(guid, ComponentType.UNKNOWN).value

                    estimated_level = 0

                    # 이름 기반 패턴 확인
                    if name in self.topology_level_patterns:
                        pattern = self.topology_level_patterns[name]
                        if pattern.total_samples >= 3:
                            estimated_level = pattern.dominant_level

                    # 타입 기반 패턴 확인
                    elif comp_type in self.topology_level_by_type:
                        type_pattern = self.topology_level_by_type[comp_type]
                        if type_pattern.total_samples >= 5:
                            estimated_level = int(type_pattern.avg_level + 0.5)

                    node_levels[guid] = estimated_level

            return node_levels

        # 토폴로지 레벨 계산
        topology_levels = calculate_topology_levels()

        def get_level_x_position(level: int, base_x: float) -> float:
            """레벨에 따른 X 위치 계산"""
            if level == 0:
                return base_x

            # 학습된 레벨 간 간격 사용
            total_x = base_x
            for l in range(level):
                level_key = f"({l}, {l+1})"
                if level_key in self.x_spacing_by_level:
                    spacing = self.x_spacing_by_level[level_key].avg_x_spacing
                else:
                    spacing = default_spacing + 50  # 기본 간격

                total_x += spacing

            return total_x

        # =====================================================================
        # 2. 연결된 컴포넌트 클러스터 찾기 (BFS)
        # =====================================================================

        visited = set()
        clusters = []

        for start_guid in comp_map:
            if start_guid in visited:
                continue

            cluster = set()
            queue = [start_guid]

            while queue:
                guid = queue.pop(0)
                if guid in visited:
                    continue
                visited.add(guid)
                cluster.add(guid)

                for neighbor in neighbors[guid]:
                    if neighbor not in visited:
                        queue.append(neighbor)

            if cluster:
                clusters.append(cluster)

        def cluster_avg_y(cluster):
            ys = [float(comp_map[g].get('y') or 0) for g in cluster]
            return sum(ys) / len(ys) if ys else 0

        # 클러스터를 Y 기준으로 정렬 (위→아래 배치, 독립 로직들)
        clusters.sort(key=cluster_avg_y)

        # =====================================================================
        # 2.5 NEW v5.0: 서브그래프 템플릿 매칭 및 적용
        # =====================================================================

        template_applied_guids = set()
        template_positions = {}
        templates_matched = 0

        if self.subgraph_templates:
            # 템플릿 매칭 찾기
            matches = self.find_matching_templates(comp_map, outgoing)

            # 매칭된 템플릿 적용
            template_base_y = start_y
            for pattern_key, guids, template in matches:
                if any(g in template_applied_guids for g in guids):
                    continue  # 이미 적용된 GUID 건너뛰기

                # 첫 노드의 기준 위치 결정
                first_guid = guids[0]
                first_comp = comp_map.get(first_guid, {})

                # 기준 X: 시작 위치
                base_x = start_x

                # 기준 Y: 이전 템플릿 아래
                base_y = template_base_y

                # 템플릿 위치 적용
                positions = self.apply_template_positions(guids, template, base_x, base_y)
                template_positions.update(positions)

                # 사용된 GUID 기록
                for g in guids:
                    template_applied_guids.add(g)

                # 다음 템플릿 Y 위치 계산
                if positions:
                    max_y = max(pos[1] for pos in positions.values())
                    template_base_y = max_y + row_height * 2

                templates_matched += 1

        # =====================================================================
        # 3. v8.0: 연결 대상 기반 상대 위치 레이아웃
        # =====================================================================

        new_positions = dict(template_positions)  # 템플릿 위치 먼저 적용
        current_cluster_y = template_base_y if template_positions else start_y

        for cluster in clusters:
            # 템플릿으로 이미 처리된 컴포넌트 제외
            remaining_cluster = cluster - template_applied_guids
            if not remaining_cluster:
                continue  # 모든 컴포넌트가 템플릿으로 처리됨

            cluster_incoming = {g: incoming[g] & remaining_cluster for g in remaining_cluster}
            cluster_outgoing = {g: outgoing[g] & remaining_cluster for g in remaining_cluster}

            # =====================================================================
            # NEW v8.2: Forward BFS - 소스에서 타겟으로 배치 (좌→우 흐름 보장)
            # =====================================================================

            cluster_positions = {}  # guid -> (x, y)
            processed = set()

            def get_target_offset(src_guid: str, tgt_guid: str) -> Tuple[float, float]:
                """소스 기준 타겟의 오프셋 (양수 x = 타겟이 오른쪽)"""
                src_comp = comp_map.get(src_guid, {})
                tgt_comp = comp_map.get(tgt_guid, {})
                src_name = src_comp.get('name', '')
                tgt_name = tgt_comp.get('name', '')
                src_type = comp_types.get(src_guid, ComponentType.UNKNOWN).value
                tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN).value

                # Priority 1: 이름 기반 상대 위치 패턴 (반전: tgt_x - src_x)
                name_key = f"({src_name}, {tgt_name})"
                if name_key in self.relative_position_patterns:
                    pattern = self.relative_position_patterns[name_key]
                    if pattern.sample_count >= 3:
                        # 학습된 오프셋은 src_x - tgt_x 이므로 반전
                        return (-pattern.avg_x_offset, -pattern.avg_y_offset)

                # Priority 2: 타입 기반 상대 위치 패턴
                type_key = f"({src_type}, {tgt_type})"
                if type_key in self.relative_position_by_type:
                    type_pattern = self.relative_position_by_type[type_key]
                    if type_pattern.sample_count >= 5:
                        return (-type_pattern.avg_x_offset, -type_pattern.avg_y_offset)

                # Priority 3: KNN 기반 간격 (기존 - 이미 src→tgt 방향)
                offset_x, offset_y = get_spacing(src_guid, tgt_guid)
                return (offset_x, offset_y)

            # 소스 노드 찾기 (incoming이 없는 노드) - 왼쪽 시작점
            sources = [g for g in remaining_cluster if len(cluster_incoming.get(g, set())) == 0]
            if not sources:
                # 소스가 없으면 가장 왼쪽 X를 가진 노드 선택
                sources = [min(remaining_cluster, key=lambda g: float(comp_map[g].get('x') or 0))]

            # 소스 노드들을 원본 Y 순서로 정렬하여 배치
            source_y = current_cluster_y
            for src_guid in sorted(sources, key=lambda g: get_original_y(g)):
                cluster_positions[src_guid] = (start_x, source_y)
                processed.add(src_guid)
                source_y += get_comp_height(src_guid) + row_height

            # Forward BFS: 소스에서 타겟으로 상대 위치 적용
            queue = list(sources)
            max_iterations = len(remaining_cluster) * 3

            for iteration in range(max_iterations):
                if not queue:
                    break

                current_guid = queue.pop(0)
                if current_guid not in cluster_positions:
                    continue

                current_x, current_y = cluster_positions[current_guid]

                # 현재 노드의 타겟들 (outgoing)
                targets = list(cluster_outgoing.get(current_guid, []))

                for i, tgt_guid in enumerate(targets):
                    if tgt_guid in processed:
                        continue

                    # 소스 기준 타겟 오프셋
                    x_offset, y_offset = get_target_offset(current_guid, tgt_guid)

                    # 타겟 위치 = 소스 위치 + 오프셋 (양수면 타겟이 오른쪽)
                    new_x = current_x + x_offset
                    new_y = current_y + y_offset

                    # 같은 소스에서 여러 타겟으로 연결된 경우 Y 분산
                    if len(targets) > 1:
                        y_spacing = row_height + 20
                        branch_offset = (i - (len(targets) - 1) / 2) * y_spacing
                        new_y = current_y + branch_offset

                    cluster_positions[tgt_guid] = (new_x, new_y)
                    processed.add(tgt_guid)

                    if tgt_guid not in queue:
                        queue.append(tgt_guid)

            # 처리되지 않은 노드들 (연결 없는 독립 노드)
            unprocessed_y = current_cluster_y
            for guid in remaining_cluster:
                if guid not in cluster_positions:
                    # 원본 X 상대 위치 유지
                    original_x = float(comp_map[guid].get('x') or 0)
                    original_xs_list = [float(comp_map[g].get('x') or 0) for g in remaining_cluster]
                    min_orig_x = min(original_xs_list) if original_xs_list else 0
                    relative_x = original_x - min_orig_x
                    cluster_positions[guid] = (start_x + relative_x, unprocessed_y)
                    unprocessed_y += get_comp_height(guid) + row_height

            # 병합 노드 Y 위치 조정 (소스들의 중앙으로)
            for guid in remaining_cluster:
                tgt_sources = list(cluster_incoming.get(guid, []))
                if len(tgt_sources) > 1:
                    source_ys = []
                    for src in tgt_sources:
                        if src in cluster_positions:
                            source_ys.append(cluster_positions[src][1])

                    if source_ys:
                        avg_y = sum(source_ys) / len(source_ys)
                        old_x = cluster_positions.get(guid, (0, 0))[0]
                        cluster_positions[guid] = (old_x, avg_y)

            # =====================================================================
            # NEW v4.0: 와이어 교차 최소화 (X 레벨별 Y 순서 최적화)
            # =====================================================================

            # X를 레벨로 그룹화
            sorted_by_x = defaultdict(list)
            for guid, (x, y) in cluster_positions.items():
                x_group = round(x / 100) * 100  # 100 단위로 그룹화
                sorted_by_x[x_group].append((guid, y))

            # 와이어 교차 최소화를 위한 레벨별 Y 순서 최적화
            if _crossing_modules_available:
                try:
                    minimizer = get_crossing_minimizer()

                    # 레벨별 노드 맵 생성
                    levels_map = {}
                    for i, x_group in enumerate(sorted(sorted_by_x.keys())):
                        levels_map[i] = [g for g, y in sorted_by_x[x_group]]

                    # 현재 위치 맵
                    current_positions = {g: (cluster_positions[g][0], cluster_positions[g][1]) for g in cluster_positions}

                    # 와이어 목록 생성
                    from .wire_crossing_detector import Wire
                    wire_list = []
                    for src_guid in remaining_cluster:
                        for tgt_guid in cluster_outgoing.get(src_guid, []):
                            if src_guid in current_positions and tgt_guid in current_positions:
                                src_x, src_y = current_positions[src_guid]
                                tgt_x, tgt_y = current_positions[tgt_guid]
                                wire_list.append(Wire(src_guid, tgt_guid, src_x, src_y, tgt_x, tgt_y))

                    if wire_list and len(levels_map) > 0:
                        # 포트 정렬 패턴 활용: 타겟별 소스 와이어 순서
                        wire_order_to_target = {}
                        for tgt_guid in remaining_cluster:
                            sources_to_target = list(cluster_incoming.get(tgt_guid, []))
                            if len(sources_to_target) >= 2:
                                # 학습된 포트 정렬 패턴 확인
                                tgt_name = comp_map.get(tgt_guid, {}).get('name', '')
                                if tgt_name in self.port_alignment_patterns:
                                    # 학습된 순서 적용
                                    learned_order = self.port_alignment_patterns[tgt_name].source_y_order
                                    # 소스들을 학습된 순서로 정렬
                                    def sort_key(src_guid):
                                        src_name = comp_map.get(src_guid, {}).get('name', '')
                                        if src_name in learned_order:
                                            return learned_order.index(src_name)
                                        return 999
                                    sources_to_target.sort(key=sort_key)
                                wire_order_to_target[tgt_guid] = sources_to_target

                        # 레벨별 교차 최소화
                        optimized_y = minimizer.optimize_all_levels(
                            levels_map=levels_map,
                            node_positions=current_positions,
                            incoming_connections={g: list(cluster_incoming.get(g, [])) for g in cluster},
                            outgoing_connections={g: list(cluster_outgoing.get(g, [])) for g in cluster},
                            all_wires=wire_list,
                            y_spacing=row_height + 20,
                            max_sweeps=2
                        )

                        # 최적화된 Y 좌표 적용
                        for guid, new_y in optimized_y.items():
                            if guid in cluster_positions:
                                old_x, _ = cluster_positions[guid]
                                cluster_positions[guid] = (old_x, new_y)

                except Exception as e:
                    # 와이어 교차 최소화 실패 시 기존 방식 사용
                    pass

            # 겹침 방지: Y 위치 정렬 (와이어 교차 최소화 후 적용)
            sorted_by_x = defaultdict(list)
            for guid, (x, y) in cluster_positions.items():
                x_group = round(x / 100) * 100  # 100 단위로 그룹화
                sorted_by_x[x_group].append((guid, y))

            for x_group in sorted_by_x:
                nodes = sorted_by_x[x_group]

                # NEW v6.0: 학습된 Y 순서 패턴 기반 정렬
                if len(nodes) >= 2 and (self.y_order_patterns or self.y_order_by_type):
                    # 쌍별 비교 점수 계산
                    def get_pair_score(guid_a: str, guid_b: str) -> float:
                        """A가 B 위에 있어야 할 점수 (양수: A 위, 음수: B 위)"""
                        comp_a = comp_map.get(guid_a, {})
                        comp_b = comp_map.get(guid_b, {})
                        name_a = comp_a.get('name', '')
                        name_b = comp_b.get('name', '')

                        score = 0.0

                        # 이름 기반 패턴 확인
                        sorted_names = tuple(sorted([name_a, name_b]))
                        key = f"({sorted_names[0]}, {sorted_names[1]})"

                        if key in self.y_order_patterns:
                            pattern = self.y_order_patterns[key]
                            if pattern.confidence >= 0.5:  # 50% 이상 신뢰도
                                if pattern.preferred_order == "a_above":
                                    # sorted_names[0]이 위에 있어야 함
                                    if name_a == sorted_names[0]:
                                        score += pattern.confidence * 100
                                    else:
                                        score -= pattern.confidence * 100
                                elif pattern.preferred_order == "b_above":
                                    # sorted_names[1]이 위에 있어야 함
                                    if name_a == sorted_names[1]:
                                        score += pattern.confidence * 100
                                    else:
                                        score -= pattern.confidence * 100

                        # 타입 기반 패턴 확인 (이름 패턴이 없을 때)
                        if score == 0.0:
                            type_a = comp_types.get(guid_a, ComponentType.UNKNOWN).value
                            type_b = comp_types.get(guid_b, ComponentType.UNKNOWN).value
                            sorted_types = tuple(sorted([type_a, type_b]))
                            type_key = f"({sorted_types[0]}, {sorted_types[1]})"

                            if type_key in self.y_order_by_type:
                                type_pattern = self.y_order_by_type[type_key]
                                if type_pattern.sample_count >= 3:
                                    if type_pattern.a_above_count > type_pattern.b_above_count:
                                        if type_a == sorted_types[0]:
                                            score += 50
                                        else:
                                            score -= 50
                                    elif type_pattern.b_above_count > type_pattern.a_above_count:
                                        if type_a == sorted_types[1]:
                                            score += 50
                                        else:
                                            score -= 50

                        return score

                    # 버블 정렬 스타일로 쌍별 비교 점수 기반 정렬
                    node_list = list(nodes)
                    for i in range(len(node_list)):
                        for j in range(i + 1, len(node_list)):
                            guid_i, y_i = node_list[i]
                            guid_j, y_j = node_list[j]

                            # i가 j 위에 있어야 할 점수 계산
                            score = get_pair_score(guid_i, guid_j)

                            # 점수가 음수면 j가 i 위에 있어야 함 → 교환
                            if score < -10:  # 임계값 이상 차이가 나야 교환
                                node_list[i], node_list[j] = node_list[j], node_list[i]

                    nodes = node_list
                else:
                    nodes.sort(key=lambda n: n[1])  # 기본: Y 순 정렬

                for i, (guid, orig_y) in enumerate(nodes):
                    if i == 0:
                        min_y = current_cluster_y
                    else:
                        prev_guid = nodes[i-1][0]
                        prev_y = cluster_positions[prev_guid][1]
                        min_y = prev_y + get_comp_height(prev_guid) + row_height

                    x = cluster_positions[guid][0]
                    new_y = max(orig_y, min_y)
                    cluster_positions[guid] = (x, new_y)

            # 클러스터 위치 저장
            for guid, (x, y) in cluster_positions.items():
                new_positions[guid] = (x, y)

            # 다음 클러스터 시작 Y (학습된 클러스터 간격 사용)
            if cluster_positions:
                max_y = max(pos[1] for pos in cluster_positions.values())
                cluster_gap = self.cluster_spacing_pattern.avg_y_gap if self.cluster_spacing_pattern.sample_count > 0 else row_height * 4
                current_cluster_y = max_y + cluster_gap

        # =====================================================================
        # 4. 결과 생성
        # =====================================================================

        moves = []

        for guid, comp in comp_map.items():
            old_x = float(comp.get('x') or comp.get('position_x') or 0)
            old_y = float(comp.get('y') or comp.get('position_y') or 0)

            if guid in new_positions:
                new_x, new_y = new_positions[guid]
            else:
                new_x, new_y = old_x, old_y

            if abs(new_x - old_x) > 5 or abs(new_y - old_y) > 5:
                moves.append({
                    "guid": guid,
                    "name": comp.get('name', ''),
                    "old_x": round(old_x, 1),
                    "old_y": round(old_y, 1),
                    "new_x": round(new_x, 1),
                    "new_y": round(new_y, 1)
                })

        # 토폴로지 레벨 통계
        max_level = max(topology_levels.values()) if topology_levels else 0
        level_counts = {}
        for level in topology_levels.values():
            level_counts[level] = level_counts.get(level, 0) + 1

        return {
            "success": True,
            "moves": moves,
            "total_components": len(components),
            "components_moved": len(moves),
            "clusters_found": len(clusters),
            "templates_matched": templates_matched,
            "template_applied_components": len(template_applied_guids),
            "y_order_patterns_count": len(self.y_order_patterns),
            "y_order_by_type_count": len(self.y_order_by_type),
            "topology_levels_used": max_level + 1,
            "topology_level_patterns_count": len(self.topology_level_patterns),
            "x_spacing_by_level_count": len(self.x_spacing_by_level),
            "relative_position_patterns_count": len(self.relative_position_patterns),
            "relative_position_by_type_count": len(self.relative_position_by_type),
            "spacing_used": {
                "default": round(default_spacing, 1),
                "row_height": row_height,
                "connection_types": {
                    ct: round(p.avg_x, 1)
                    for ct, p in self.connection_spacing.items()
                    if p.sample_count >= 3
                }
            }
        }

    # =========================================================================
    # Auto Layout v9 - 완전 재설계된 패턴 기반 레이아웃
    # =========================================================================

    # 최소 간격 상수
    MIN_X_SPACING = 180.0  # 컴포넌트 폭 + 여백
    MIN_Y_SPACING = 60.0   # 컴포넌트 높이 + 여백

    def _classify_cluster_shape(
        self,
        cluster: Set[str],
        incoming: Dict[str, Set[str]],
        outgoing: Dict[str, Set[str]]
    ) -> ClusterShape:
        """
        클러스터 형태 분류

        - HORIZONTAL_FLOW: 모든 노드가 최대 1개의 입력과 1개의 출력
        - BRANCHING: 1→N 분기가 있음
        - MERGING: N→1 병합이 있음
        - DIAMOND: 분기와 병합 모두 있음
        - COMPLEX: 그 외
        """
        has_branching = False
        has_merging = False

        for guid in cluster:
            out_count = len(outgoing.get(guid, set()) & cluster)
            in_count = len(incoming.get(guid, set()) & cluster)

            if out_count > 1:
                has_branching = True
            if in_count > 1:
                has_merging = True

        if has_branching and has_merging:
            return ClusterShape.DIAMOND
        elif has_branching:
            return ClusterShape.BRANCHING
        elif has_merging:
            return ClusterShape.MERGING
        else:
            return ClusterShape.HORIZONTAL_FLOW

    def _calculate_topology_levels(
        self,
        cluster: Set[str],
        incoming: Dict[str, Set[str]],
        outgoing: Dict[str, Set[str]]
    ) -> Dict[str, int]:
        """
        BFS로 각 노드의 토폴로지 레벨 계산
        소스 노드 = 레벨 0, 타겟으로 갈수록 레벨 증가

        Returns:
            {guid: level} 딕셔너리
        """
        levels = {}

        # 소스 노드 찾기 (클러스터 내 incoming이 없는 노드)
        sources = [g for g in cluster if len(incoming.get(g, set()) & cluster) == 0]

        # 소스가 없으면 (사이클인 경우) 가장 왼쪽 노드를 소스로 취급
        if not sources:
            sources = list(cluster)[:1]

        # BFS로 레벨 할당
        queue = [(g, 0) for g in sources]
        visited = set()

        while queue:
            guid, level = queue.pop(0)

            # 더 큰 레벨로 업데이트 (가장 긴 경로 기준)
            if guid in levels:
                if level > levels[guid]:
                    levels[guid] = level
                else:
                    continue  # 이미 더 큰 레벨로 방문함
            else:
                levels[guid] = level

            # 타겟 노드들 큐에 추가
            for tgt in outgoing.get(guid, set()) & cluster:
                queue.append((tgt, level + 1))

        # 연결 안 된 노드는 레벨 0
        for g in cluster:
            if g not in levels:
                levels[g] = 0

        return levels

    def _calculate_max_depth(
        self,
        cluster: Set[str],
        incoming: Dict[str, Set[str]],
        sinks: List[str]
    ) -> int:
        """
        클러스터의 최대 깊이 계산 (Sink에서 Source까지의 최대 경로 길이)
        Reverse BFS로 계산
        """
        if not sinks:
            return 0

        depths = {sink: 0 for sink in sinks}
        queue = list(sinks)
        max_depth = 0

        while queue:
            current = queue.pop(0)
            current_depth = depths.get(current, 0)

            for source in incoming.get(current, set()) & cluster:
                new_depth = current_depth + 1
                if source not in depths or new_depth > depths[source]:
                    depths[source] = new_depth
                    max_depth = max(max_depth, new_depth)
                    if source not in queue:
                        queue.append(source)

        return max_depth

    def _detect_chains(
        self,
        cluster: Set[str],
        incoming: Dict[str, Set[str]],
        outgoing: Dict[str, Set[str]],
        comp_map: Dict[str, dict]
    ) -> List[List[str]]:
        """
        클러스터에서 체인(시퀀스) 감지
        체인: A→B→C 형태의 직선 연결
        """
        chains = []
        visited = set()

        # 소스 노드들 찾기
        sources = [g for g in cluster if len(incoming.get(g, set()) & cluster) == 0]

        for start in sources:
            if start in visited:
                continue

            chain = [start]
            visited.add(start)
            current = start

            # 체인 따라가기 (단일 출력만)
            while True:
                targets = list(outgoing.get(current, set()) & cluster)
                if len(targets) != 1:
                    break  # 분기 또는 끝

                next_node = targets[0]

                # 다음 노드도 단일 입력이어야 체인
                if len(incoming.get(next_node, set()) & cluster) != 1:
                    break

                if next_node in visited:
                    break

                chain.append(next_node)
                visited.add(next_node)
                current = next_node

            if len(chain) >= 2:
                chains.append(chain)

        return chains

    def _get_learned_offset(
        self,
        source_name: str,
        target_name: str,
        min_samples: int = 2,
        max_dy_threshold: float = 150.0
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        connection_pair_samples에서 학습된 (dx, dy) 오프셋 조회

        중앙값(median)을 사용하여 이상치 영향 감소
        Y 오프셋이 임계값 초과시 0으로 처리 (연결된 컴포넌트는 보통 비슷한 Y 레벨)

        Args:
            source_name: 소스 컴포넌트 이름
            target_name: 타겟 컴포넌트 이름
            min_samples: 최소 샘플 수 (신뢰도)
            max_dy_threshold: Y 오프셋 최대 허용치 (초과시 0 반환)

        Returns:
            (dx, dy) 또는 (None, None) - 학습 데이터 없으면 None
        """
        if not self.connection_pair_samples:
            return (None, None)

        # 매칭되는 샘플 수집
        matching_samples = [
            s for s in self.connection_pair_samples
            if s.source_name == source_name and s.target_name == target_name
        ]

        if len(matching_samples) < min_samples:
            return (None, None)

        # 중앙값(median) 계산 - 이상치 영향 감소
        dx_values = sorted([s.offset_x for s in matching_samples])
        dy_values = sorted([s.offset_y for s in matching_samples])

        n = len(matching_samples)
        if n % 2 == 0:
            median_dx = (dx_values[n//2 - 1] + dx_values[n//2]) / 2
            median_dy = (dy_values[n//2 - 1] + dy_values[n//2]) / 2
        else:
            median_dx = dx_values[n//2]
            median_dy = dy_values[n//2]

        # Y 오프셋이 임계값 초과시 0으로 (연결된 컴포넌트는 보통 같은 Y 레벨)
        if abs(median_dy) > max_dy_threshold:
            median_dy = 0.0

        return (median_dx, median_dy)

    def _find_matching_sequence_pattern(
        self,
        chain: List[str],
        comp_map: Dict[str, dict]
    ) -> Optional['SequencePattern']:
        """
        체인에 매칭되는 SequencePattern 찾기
        """
        if not self.sequence_patterns:
            return None

        # 체인의 컴포넌트 이름 시퀀스
        chain_names = [comp_map.get(g, {}).get('name', '') for g in chain]

        # 정확한 매칭 시도 (sequence_patterns는 list)
        for pattern in self.sequence_patterns:
            if len(pattern.component_sequence) == len(chain_names):
                if pattern.component_sequence == chain_names:
                    return pattern

        # 부분 매칭 시도 (체인이 패턴의 시작 부분과 일치)
        for pattern in self.sequence_patterns:
            if len(pattern.component_sequence) >= len(chain_names):
                if pattern.component_sequence[:len(chain_names)] == chain_names:
                    return pattern

        return None

    def _apply_sequence_pattern(
        self,
        chain: List[str],
        pattern: 'SequencePattern',
        base_x: float,
        base_y: float,
        comp_map: Dict[str, dict]
    ) -> Dict[str, Tuple[float, float]]:
        """
        SequencePattern을 체인에 적용하여 위치 계산
        """
        positions = {}
        current_x = base_x

        for i, guid in enumerate(chain):
            positions[guid] = (current_x, base_y)

            if i < len(pattern.x_spacings):
                spacing = max(pattern.x_spacings[i], self.MIN_X_SPACING)
            else:
                spacing = self.MIN_X_SPACING

            current_x += spacing

        return positions

    def _layout_branching_nodes(
        self,
        source_guid: str,
        targets: List[str],
        source_pos: Tuple[float, float],
        comp_map: Dict[str, dict],
        comp_types: Dict[str, 'ComponentType']
    ) -> Dict[str, Tuple[float, float]]:
        """
        분기 노드 레이아웃 (1→N)
        학습된 BranchingPattern 사용
        """
        positions = {}
        source_name = comp_map.get(source_guid, {}).get('name', '')
        source_x, source_y = source_pos

        # 학습된 분기 패턴 확인
        y_spacing = self.MIN_Y_SPACING + 20
        if source_name in self.branching_patterns:
            pattern = self.branching_patterns[source_name]
            if pattern.sample_count >= 2:
                y_spacing = max(pattern.y_spacing, self.MIN_Y_SPACING)

        # X 간격 계산 (타입 기반)
        src_type = comp_types.get(source_guid, ComponentType.UNKNOWN)
        x_spacing = self.MIN_X_SPACING

        # 연결 타입 패턴에서 간격 가져오기
        for tgt_guid in targets[:1]:  # 첫 타겟 기준
            tgt_type = comp_types.get(tgt_guid, ComponentType.UNKNOWN)
            conn_type = get_connection_type(src_type, tgt_type)
            if conn_type in self.connection_spacing:
                pattern = self.connection_spacing[conn_type]
                if pattern.sample_count >= 3:
                    x_spacing = max(pattern.avg_x, self.MIN_X_SPACING)
                    break

        # 타겟 위치 계산 (중앙 정렬)
        total_height = (len(targets) - 1) * y_spacing
        start_y = source_y - total_height / 2

        for i, tgt_guid in enumerate(targets):
            tgt_x = source_x + x_spacing
            tgt_y = start_y + i * y_spacing
            positions[tgt_guid] = (tgt_x, tgt_y)

        return positions

    def _layout_merging_nodes(
        self,
        sources: List[str],
        target_guid: str,
        target_pos: Tuple[float, float],
        comp_map: Dict[str, dict],
        comp_types: Dict[str, 'ComponentType']
    ) -> Dict[str, Tuple[float, float]]:
        """
        병합 노드 레이아웃 (N→1)
        학습된 MergingPattern 사용
        """
        positions = {}
        target_name = comp_map.get(target_guid, {}).get('name', '')
        target_x, target_y = target_pos

        # 학습된 병합 패턴 확인
        y_spacing = self.MIN_Y_SPACING + 20
        if target_name in self.merging_patterns:
            pattern = self.merging_patterns[target_name]
            if pattern.sample_count >= 2:
                y_spacing = max(pattern.y_spacing, self.MIN_Y_SPACING)

        # X 간격 계산
        x_spacing = self.MIN_X_SPACING
        tgt_type = comp_types.get(target_guid, ComponentType.UNKNOWN)

        for src_guid in sources[:1]:
            src_type = comp_types.get(src_guid, ComponentType.UNKNOWN)
            conn_type = get_connection_type(src_type, tgt_type)
            if conn_type in self.connection_spacing:
                pattern = self.connection_spacing[conn_type]
                if pattern.sample_count >= 3:
                    x_spacing = max(pattern.avg_x, self.MIN_X_SPACING)
                    break

        # 소스 위치 계산 (중앙 정렬, 타겟 왼쪽)
        total_height = (len(sources) - 1) * y_spacing
        start_y = target_y - total_height / 2

        for i, src_guid in enumerate(sources):
            src_x = target_x - x_spacing
            src_y = start_y + i * y_spacing
            positions[src_guid] = (src_x, src_y)

        return positions

    def _ensure_no_overlap(
        self,
        positions: Dict[str, Tuple[float, float]],
        comp_map: Dict[str, dict]
    ) -> Dict[str, Tuple[float, float]]:
        """
        v9.4: 실제 겹침이 발생한 경우에만 최소한으로 조정
        학습된 배치를 최대한 보존
        """
        if not positions:
            return positions

        new_positions = dict(positions)  # 원본 복사

        # 모든 컴포넌트를 (x, y) 순으로 정렬
        sorted_nodes = sorted(
            positions.items(),
            key=lambda item: (item[1][0], item[1][1])  # X 우선, Y 차선
        )

        # 각 컴포넌트에 대해 실제 겹침 검사
        for i, (guid, (x, y)) in enumerate(sorted_nodes):
            comp = comp_map.get(guid, {})
            comp_width = float(comp.get('width') or 100)
            comp_height = float(comp.get('height') or 50)

            # 이 컴포넌트와 겹치는 다른 컴포넌트 찾기
            for other_guid, (other_x, other_y) in new_positions.items():
                if other_guid == guid:
                    continue

                other_comp = comp_map.get(other_guid, {})
                other_width = float(other_comp.get('width') or 100)
                other_height = float(other_comp.get('height') or 50)

                # X 범위 겹침 확인 (50px 이내면 같은 열로 간주)
                x_overlap = abs(x - other_x) < 50

                if x_overlap:
                    # Y 범위 겹침 확인
                    my_top = new_positions[guid][1]
                    my_bottom = my_top + comp_height
                    other_top = other_y
                    other_bottom = other_top + other_height

                    # 실제 겹침 발생 시
                    if my_top < other_bottom + self.MIN_Y_SPACING and my_bottom + self.MIN_Y_SPACING > other_top:
                        # 위에 있는 컴포넌트 기준으로 아래로 밀기
                        if my_top >= other_top:
                            # 내가 아래에 있으면 내 위치 조정
                            new_y = other_bottom + self.MIN_Y_SPACING
                            new_positions[guid] = (x, new_y)

        return new_positions

    def _get_type_hash(self, comp_names: List[str], comp_map: Dict[str, dict]) -> str:
        """
        컴포넌트 이름 리스트의 타입 기반 해시 생성
        이름이 달라도 타입이 같으면 같은 해시
        """
        types = []
        for name in comp_names:
            # 이름으로 타입 찾기
            comp_type = COMPONENT_TYPE_MAP.get(name, ComponentType.UNKNOWN)
            types.append(comp_type.value)
        return "->".join(types)

    def calculate_auto_layout_v9(
        self,
        components: List[dict],
        wires: List[dict],
        start_x: float = 100.0,
        start_y: float = 100.0,
        row_height: float = 50.0
    ) -> dict:
        """
        v9.5 레이아웃 계산 - Chain 기반 ML 학습 패턴 방식

        핵심 원칙:
        1. 각 Source에서 시작하는 독립 Chain 추출
        2. Chain 내에서 학습된 (dx, dy) 적용
        3. Chain 간 Y 간격으로 시각적 분리
        4. Merge 지점은 먼저 배치된 Chain 기준

        v9.4 문제:
        - BFS로 전체가 하나의 클러스터가 됨
        - Sources가 모두 X=100에 세로 나열 → Y로 7000px+ 늘어남
        """
        if len(components) < 2:
            return {"success": False, "error": "Not enough components", "moves": []}

        # =====================================================================
        # 1. 기본 데이터 구조 구축
        # =====================================================================

        comp_map = {}
        skipped_groups = 0
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid:
                comp_name = comp.get('name', '')
                if comp_name == 'Group':
                    skipped_groups += 1
                    continue
                comp_map[str(guid)] = comp

        if skipped_groups > 0:
            print(f"[v9.5] Skipped {skipped_groups} Group components")

        outgoing = defaultdict(set)
        incoming = defaultdict(set)

        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))
            if src_guid in comp_map and tgt_guid in comp_map:
                outgoing[src_guid].add(tgt_guid)
                incoming[tgt_guid].add(src_guid)

        def get_comp_height(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('height') or 50)

        def get_comp_width(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('width') or 100)

        # =====================================================================
        # 2. Chain 추출 - Source에서 시작하는 독립적인 흐름
        # =====================================================================

        # Sources: incoming이 없는 노드들
        sources = [g for g in comp_map if len(incoming.get(g, set())) == 0]

        # Sources가 없으면 (모두 연결된 경우) outgoing-incoming이 가장 큰 노드
        if not sources:
            def source_score(g):
                return len(outgoing.get(g, set())) - len(incoming.get(g, set()))
            sources = [max(comp_map.keys(), key=source_score)]

        # Sources를 outgoing 개수로 정렬 (영향력 큰 것 먼저)
        sources.sort(key=lambda g: len(outgoing.get(g, set())), reverse=True)

        print(f"[v9.5] Found {len(sources)} sources")

        # =====================================================================
        # 3. Chain별 레이아웃 (DFS로 각 Source에서 흐름 따라가기)
        # =====================================================================

        new_positions = {}
        placed = set()
        current_chain_y = start_y
        total_learned_offsets = 0
        CHAIN_GAP = 150  # Chain 간 Y 간격

        def layout_chain_from_source(source_guid: str, chain_start_y: float) -> Tuple[int, float]:
            """
            Source에서 시작하여 DFS로 흐름을 따라가며 배치
            Returns: (learned_offsets_count, max_y_used)
            """
            nonlocal new_positions, placed

            if source_guid in placed:
                return 0, chain_start_y

            # BFS로 이 Source에서 도달 가능한 모든 노드 수집 (위상 정렬 순서)
            chain_nodes = []
            queue = [source_guid]
            chain_visited = set()

            while queue:
                node = queue.pop(0)
                if node in chain_visited:
                    continue
                chain_visited.add(node)
                chain_nodes.append(node)

                # 다음 노드들 (outgoing)
                for next_node in sorted(outgoing.get(node, set())):
                    if next_node not in chain_visited:
                        # 모든 incoming이 이 chain에 있거나 이미 배치되었으면 추가
                        node_incoming = incoming.get(next_node, set())
                        if all(inc in chain_visited or inc in placed for inc in node_incoming):
                            queue.append(next_node)

            # Chain 내 컴포넌트 배치
            chain_positions = {}
            learned_count = 0
            min_y = chain_start_y
            max_y = chain_start_y

            # Source 배치
            if source_guid not in placed:
                chain_positions[source_guid] = (start_x, chain_start_y)
                placed.add(source_guid)
                max_y = chain_start_y + get_comp_height(source_guid)

            # 나머지 노드들 배치 (위상 정렬 순서)
            for node in chain_nodes[1:]:
                if node in placed:
                    continue

                # incoming 중 배치된 노드 찾기
                node_incoming = [inc for inc in incoming.get(node, set())
                                 if inc in chain_positions or inc in new_positions]

                if not node_incoming:
                    # incoming이 없으면 Source 옆에 배치
                    node_x = start_x
                    node_y = max_y + self.MIN_Y_SPACING
                else:
                    # 가장 왼쪽 incoming 기준
                    def get_pos(g):
                        if g in chain_positions:
                            return chain_positions[g]
                        return new_positions.get(g, (start_x, chain_start_y))

                    leftmost = min(node_incoming, key=lambda g: get_pos(g)[0])
                    source_pos = get_pos(leftmost)
                    source_name = comp_map.get(leftmost, {}).get('name', '')
                    target_name = comp_map.get(node, {}).get('name', '')

                    # 학습된 오프셋 조회
                    dx, dy = self._get_learned_offset(source_name, target_name)

                    if dx is not None:
                        learned_count += 1
                    else:
                        dx = self.MIN_X_SPACING

                    if dy is None:
                        dy = 0

                    node_x = source_pos[0] + dx
                    node_y = source_pos[1] + dy

                chain_positions[node] = (node_x, node_y)
                placed.add(node)
                max_y = max(max_y, node_y + get_comp_height(node))
                min_y = min(min_y, node_y)

            # 겹침 방지
            chain_positions = self._ensure_no_overlap(chain_positions, comp_map)

            # 위치 저장
            new_positions.update(chain_positions)

            # max_y 재계산
            if chain_positions:
                max_y = max(pos[1] + get_comp_height(g) for g, pos in chain_positions.items())

            return learned_count, max_y

        # 각 Source에서 Chain 시작
        for source in sources:
            if source in placed:
                continue

            learned, max_y = layout_chain_from_source(source, current_chain_y)
            total_learned_offsets += learned

            # 다음 Chain Y 위치
            current_chain_y = max_y + CHAIN_GAP

        # =====================================================================
        # 4. 배치되지 않은 노드 처리 (isolated 노드)
        # =====================================================================

        for guid in comp_map:
            if guid not in placed:
                # 연결된 노드 중 배치된 것 찾기
                connected_placed = [g for g in (list(incoming.get(guid, set())) +
                                                list(outgoing.get(guid, set())))
                                    if g in new_positions]

                if connected_placed:
                    ref_pos = new_positions[connected_placed[0]]
                    new_positions[guid] = (ref_pos[0] + self.MIN_X_SPACING, ref_pos[1])
                else:
                    new_positions[guid] = (start_x, current_chain_y)
                    current_chain_y += get_comp_height(guid) + self.MIN_Y_SPACING

                placed.add(guid)

        # =====================================================================
        # 5. 결과 생성
        # =====================================================================

        moves = []
        for guid, comp in comp_map.items():
            old_x = float(comp.get('x') or comp.get('position_x') or 0)
            old_y = float(comp.get('y') or comp.get('position_y') or 0)

            if guid in new_positions:
                new_x, new_y = new_positions[guid]
            else:
                new_x, new_y = old_x, old_y

            if abs(new_x - old_x) > 5 or abs(new_y - old_y) > 5:
                moves.append({
                    "guid": guid,
                    "name": comp.get('name', ''),
                    "old_x": round(old_x, 1),
                    "old_y": round(old_y, 1),
                    "new_x": round(new_x, 1),
                    "new_y": round(new_y, 1)
                })

        return {
            "success": True,
            "moves": moves,
            "version": "v9.5-chain-based",
            "total_components": len(components),
            "components_moved": len(moves),
            "sources_found": len(sources),
            "learned_offsets_applied": total_learned_offsets
        }

    # ================================================================
    # V1 Auto Layout: Layer 0 기본 알고리즘
    # ================================================================
    #
    # 핵심 원칙:
    # 1. 와이어 흐름: 왼쪽 → 오른쪽 (X = depth * DX)
    # 2. 메인 체인 Y 우선: 가장 긴 경로의 노드들이 같은 Y
    # 3. 분기 노드: 메인 체인 아래에 배치
    #
    # 알고리즘 단계:
    # 1) 그래프 구축 (Group 제외)
    # 2) Depth 계산 (순방향)
    # 3) 서브그래프 찾기 (Union-Find)
    # 4) 각 서브그래프에서 메인 체인 찾기
    # 5) X, Y 좌표 할당
    # 6) 겹침 해소
    # 7) 이동 명령 생성
    # ================================================================

    def calculate_auto_layout_v1(
        self,
        components: List[dict],
        wires: List[dict],
        start_x: float = 100.0,
        start_y: float = 100.0,
        mode: str = "full"
    ) -> dict:
        """
        v1 Auto Layout 메인 엔트리 포인트

        Args:
            components: 컴포넌트 목록
            wires: 와이어 목록
            start_x: 시작 X 좌표
            start_y: 시작 Y 좌표
            mode: "full" (전체 재배치) - incremental은 추후 구현

        Returns:
            {"success": bool, "moves": [...], "version": str, ...}
        """
        if len(components) < 2:
            return {"success": False, "error": "Not enough components", "moves": []}

        # 1. 그래프 구축
        comp_map, incoming, outgoing, wire_details = self._build_graph_v1(components, wires)

        if not comp_map:
            return {"success": False, "error": "No valid components", "moves": []}

        # 2. 레이아웃 계산
        positions, debug_log = self._calculate_layout_v1(
            comp_map, incoming, outgoing, wire_details, start_x, start_y
        )

        # 3. 겹침 해소
        positions = self._resolve_overlaps_v1(positions, comp_map)

        # 4. 이동 명령 생성
        moves = self._generate_moves_v1(positions, comp_map)

        return {
            "success": True,
            "moves": moves,
            "version": "v1.9-clean",
            "total_components": len(comp_map),
            "components_moved": len(moves),
            "debug_log": debug_log[:50] if debug_log else []  # 처음 50개만
        }

    def _build_graph_v1(
        self,
        components: List[dict],
        wires: List[dict]
    ) -> Tuple[Dict[str, dict], Dict[str, Set[str]], Dict[str, Set[str]], List[dict]]:
        """
        그래프 구축

        - Group 컴포넌트 제외
        - incoming[guid] = 해당 노드로 들어오는 소스들
        - outgoing[guid] = 해당 노드에서 나가는 타겟들
        - wire_details = 와이어 상세 정보 (인덱스 포함)
        """
        comp_map = {}
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid and comp.get('name') != 'Group':
                comp_map[str(guid)] = comp

        outgoing = defaultdict(set)
        incoming = defaultdict(set)
        wire_details = []

        for wire in wires:
            src = str(wire.get('source_guid', ''))
            tgt = str(wire.get('target_guid', ''))
            if src in comp_map and tgt in comp_map:
                outgoing[src].add(tgt)
                incoming[tgt].add(src)
                wire_details.append({
                    'source_guid': src,
                    'target_guid': tgt,
                    'source_output_idx': wire.get('source_output_idx', 0),
                    'target_input_idx': wire.get('target_input_idx', 0)
                })

        return comp_map, dict(incoming), dict(outgoing), wire_details

    def _calculate_layout_v1(
        self,
        comp_map: Dict[str, dict],
        incoming: Dict[str, Set[str]],
        outgoing: Dict[str, Set[str]],
        wire_details: List[dict],
        start_x: float,
        start_y: float
    ) -> Tuple[Dict[str, Tuple[float, float]], List[str]]:
        """
        레이아웃 계산 (v2.3 - BFS 역방향 배치 + 타겟 입력노드 Y 정렬)

        핵심 원칙:
        1. X = depth * DX (depth 기반, 와이어 꼬임 방지)
        2. 배치 순서: sink부터 BFS로 역방향 (sink → source)
        3. 소스 Y = 타겟 입력 노드 Y (수평 와이어)
        4. 서브그래프별 Y 영역 분리
        """
        positions = {}
        debug_log = []

        # 기본 spacing
        DX = 200  # 수평 간격
        DY = 80   # 수직 간격 (컴포넌트 사이)
        SUBGRAPH_GAP = 150
        NODE_SPACING = 20  # 입력/출력 노드 간격

        def get_height(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('height') or 50)

        def get_width(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('width') or 100)

        def get_input_count(guid: str) -> int:
            comp = comp_map.get(guid, {})
            if 'input_count' in comp:
                return int(comp['input_count'])
            return 1

        def get_output_count(guid: str) -> int:
            comp = comp_map.get(guid, {})
            if 'output_count' in comp:
                return int(comp['output_count'])
            return 1

        # 와이어 정보 인덱싱
        # source → target (소스가 어느 타겟에 연결되는지)
        source_to_wires = defaultdict(list)
        for w in wire_details:
            source_to_wires[w['source_guid']].append({
                'target_guid': w['target_guid'],
                'source_output_idx': w.get('source_output_idx', 0),
                'target_input_idx': w.get('target_input_idx', 0)
            })

        # ========================================
        # 1단계: Depth 계산
        # ========================================
        depth = {}
        processed = set()

        for _ in range(len(comp_map) * 2):
            if len(processed) >= len(comp_map):
                break

            for guid in comp_map:
                if guid in processed:
                    continue

                sources = incoming.get(guid, set())

                if not sources:
                    depth[guid] = 0
                    processed.add(guid)
                elif all(src in processed for src in sources):
                    depth[guid] = max(depth[src] for src in sources) + 1
                    processed.add(guid)

        for guid in comp_map:
            if guid not in depth:
                depth[guid] = 0

        # 2차 패스: incoming이 없는 노드의 depth를 타겟 기준으로 역산
        # Unit Z처럼 incoming 없이 바로 Extrude에 연결되는 경우
        for guid in comp_map:
            sources = incoming.get(guid, set())
            targets = outgoing.get(guid, set())
            comp_name = comp_map.get(guid, {}).get('name', '')

            debug_log.append(f"  CHECK: {comp_name} sources={len(sources)} targets={len(targets)} depth={depth.get(guid, 0)}")

            if not sources:  # incoming이 없는 노드
                if targets:
                    # 타겟들 중 최소 depth - 1
                    target_depths = [depth.get(t, 0) for t in targets]
                    min_target_depth = min(target_depths)
                    new_depth = max(0, min_target_depth - 1)
                    debug_log.append(f"    -> target_depths={target_depths}, min={min_target_depth}, new_depth={new_depth}")
                    if new_depth > depth[guid]:
                        depth[guid] = new_depth
                        debug_log.append(f"  DEPTH-FIX: {comp_name} depth 0 -> {new_depth} (target-based)")

        # ========================================
        # 2단계: 서브그래프 찾기 (Union-Find)
        # ========================================
        parent = {g: g for g in comp_map}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a, b):
            pa, pb = find(a), find(b)
            if pa != pb:
                parent[pa] = pb

        for guid in comp_map:
            for tgt in outgoing.get(guid, set()):
                if tgt in comp_map:
                    union(guid, tgt)

        subgraph_map = defaultdict(list)
        for guid in comp_map:
            subgraph_map[find(guid)].append(guid)

        subgraphs = list(subgraph_map.values())
        subgraphs.sort(key=len, reverse=True)

        # ========================================
        # 3단계: Y 계산 헬퍼
        # ========================================
        def get_input_node_y(target_guid: str, input_idx: int) -> float:
            """타겟 컴포넌트의 특정 입력 노드 Y 좌표 계산"""
            if target_guid not in positions:
                return None

            tgt_y = positions[target_guid][1]
            input_count = get_input_count(target_guid)

            if input_count <= 1:
                return tgt_y

            # 컴포넌트 높이 기반 노드 간격 계산
            comp_height = get_height(target_guid)
            # 입력 노드들은 컴포넌트 높이의 약 80% 영역에 분포
            usable_height = comp_height * 0.8
            node_spacing = usable_height / max(input_count - 1, 1)

            total_input_height = (input_count - 1) * node_spacing
            first_input_y = tgt_y - total_input_height / 2
            return first_input_y + input_idx * node_spacing

        def get_output_node_offset(source_guid: str, output_idx: int) -> float:
            """소스 컴포넌트의 출력 노드 오프셋 (컴포넌트 중심 기준)"""
            output_count = get_output_count(source_guid)

            if output_count <= 1:
                return 0

            # 컴포넌트 높이 기반 노드 간격 계산
            comp_height = get_height(source_guid)
            usable_height = comp_height * 0.8
            node_spacing = usable_height / max(output_count - 1, 1)

            total_output_height = (output_count - 1) * node_spacing
            first_output_offset = -total_output_height / 2
            return first_output_offset + output_idx * node_spacing

        def calculate_source_y(source_guid: str) -> float:
            """
            소스의 Y를 타겟 입력 노드 기준으로 계산
            - 소스 출력 노드가 타겟 입력 노드와 수평이 되도록
            """
            wires_from_source = source_to_wires.get(source_guid, [])

            if not wires_from_source:
                return None

            # 배치된 타겟만 고려
            valid_wires = [w for w in wires_from_source if w['target_guid'] in positions]

            if not valid_wires:
                return None

            # 첫 번째 타겟 기준 (가장 가까운 depth의 타겟)
            w = valid_wires[0]
            target_guid = w['target_guid']
            target_input_idx = w['target_input_idx']
            source_output_idx = w['source_output_idx']

            # 타겟 입력 노드 Y
            target_input_y = get_input_node_y(target_guid, target_input_idx)
            if target_input_y is None:
                return None

            # 소스 출력 노드 오프셋
            source_output_offset = get_output_node_offset(source_guid, source_output_idx)

            # 소스 Y = 타겟 입력 노드 Y - 소스 출력 노드 오프셋
            source_y = target_input_y - source_output_offset

            debug_log.append(
                f"  {comp_map.get(source_guid, {}).get('name', '')}[out {source_output_idx}] -> "
                f"{comp_map.get(target_guid, {}).get('name', '')}[in {target_input_idx}]: "
                f"Y={source_y}"
            )

            return source_y

        # ========================================
        # 4단계: BFS 역방향 배치 (sink → source)
        # ========================================
        current_y = start_y

        for nodes in subgraphs:
            node_set = set(nodes)

            # 싱크 찾기 (서브그래프 내에서 outgoing이 없는 노드)
            sinks = []
            for g in nodes:
                targets_in_subgraph = outgoing.get(g, set()) & node_set
                if not targets_in_subgraph:
                    sinks.append(g)

            if not sinks:
                sinks = [max(nodes, key=lambda g: depth.get(g, 0))]

            # 싱크 배치: 가장 오른쪽 (max depth * DX)
            max_depth = max(depth.get(g, 0) for g in nodes)

            # 싱크들을 depth 역순, 이름순으로 정렬
            sinks.sort(key=lambda g: (-depth.get(g, 0), comp_map.get(g, {}).get('name', '')))

            sink_y = current_y
            for sink in sinks:
                d = depth.get(sink, 0)
                x = start_x + d * DX
                positions[sink] = (x, sink_y)
                debug_log.append(f"  SINK: {comp_map.get(sink, {}).get('name', '')} depth={d} at ({x}, {sink_y})")
                sink_y += get_height(sink) + DY

            # BFS로 역방향 배치 (소스들)
            queue = list(sinks)
            visited = set(sinks)

            while queue:
                current_node = queue.pop(0)

                # 이 노드의 소스들 (서브그래프 내)
                sources = incoming.get(current_node, set()) & node_set

                for src in sources:
                    if src in visited:
                        continue

                    visited.add(src)

                    # X = depth * DX
                    d = depth.get(src, 0)
                    x = start_x + d * DX

                    # Y = 타겟 입력 노드 Y 기준
                    ideal_y = calculate_source_y(src)

                    if ideal_y is not None:
                        y = ideal_y
                    else:
                        y = current_y
                        current_y += get_height(src) + DY

                    positions[src] = (x, y)
                    debug_log.append(
                        f"  {comp_map.get(src, {}).get('name', '')} depth={d} at ({x}, {y})"
                    )

                    queue.append(src)

            # 서브그래프 내 미배치 노드 처리
            for g in nodes:
                if g not in positions:
                    d = depth.get(g, 0)
                    positions[g] = (start_x + d * DX, current_y)
                    current_y += get_height(g) + DY

            # 다음 서브그래프 Y 시작점
            if positions:
                max_y_in_subgraph = max(
                    pos[1] + get_height(guid) for guid, pos in positions.items() if guid in node_set
                )
                current_y = max(current_y, max_y_in_subgraph + SUBGRAPH_GAP)

        # 고립 노드 처리
        for guid in comp_map:
            if guid not in positions:
                positions[guid] = (start_x, current_y)
                current_y += get_height(guid) + 50

        return positions, debug_log

    def _resolve_overlaps_v1(
        self,
        positions: Dict[str, Tuple[float, float]],
        comp_map: Dict[str, dict]
    ) -> Dict[str, Tuple[float, float]]:
        """
        겹침 해소: 같은 X열에서 Y 겹침 방지
        """
        if not positions:
            return positions

        MIN_GAP = 20

        def get_height(guid: str) -> float:
            return float(comp_map.get(guid, {}).get('height') or 50)

        # X 좌표별 그룹화 (50px 단위)
        x_groups = defaultdict(list)
        for guid, (x, y) in positions.items():
            bucket = round(x / 50) * 50
            x_groups[bucket].append((guid, y))

        result = dict(positions)

        for bucket, items in x_groups.items():
            items.sort(key=lambda t: t[1])

            for i in range(1, len(items)):
                prev_guid, prev_y = items[i - 1]
                curr_guid, curr_y = items[i]

                min_y = prev_y + get_height(prev_guid) + MIN_GAP

                if curr_y < min_y:
                    result[curr_guid] = (result[curr_guid][0], min_y)
                    items[i] = (curr_guid, min_y)

        return result

    def _generate_moves_v1(
        self,
        positions: Dict[str, Tuple[float, float]],
        comp_map: Dict[str, dict]
    ) -> List[dict]:
        """
        이동 명령 생성 (5px 이상 차이나는 경우만)
        """
        moves = []

        for guid, comp in comp_map.items():
            if guid not in positions:
                continue

            old_x = float(comp.get('x') or comp.get('position_x') or 0)
            old_y = float(comp.get('y') or comp.get('position_y') or 0)
            new_x, new_y = positions[guid]

            if abs(new_x - old_x) > 5 or abs(new_y - old_y) > 5:
                moves.append({
                    "guid": guid,
                    "name": comp.get('name', ''),
                    "old_x": round(old_x, 1),
                    "old_y": round(old_y, 1),
                    "new_x": round(new_x, 1),
                    "new_y": round(new_y, 1)
                })

        return moves


# ============================================================
# Singleton Instance
# ============================================================

_persistent_learner: Optional[PersistentLayoutLearner] = None


def get_persistent_learner(storage_path: Optional[str] = None) -> PersistentLayoutLearner:
    """싱글톤 인스턴스 반환"""
    global _persistent_learner
    if _persistent_learner is None:
        _persistent_learner = PersistentLayoutLearner(storage_path)
    return _persistent_learner


def reset_persistent_learner():
    """싱글톤 인스턴스 초기화"""
    global _persistent_learner
    _persistent_learner = None
