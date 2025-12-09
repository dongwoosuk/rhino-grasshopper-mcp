"""
Feature Extractor for ML Layout Learning

Extracts features from Grasshopper canvas for machine learning:
- Connection features (source->target relationships)
- Branching patterns (1->N connections)
- Topology levels
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

# Import component type classification from persistent_layout_learner
try:
    from .persistent_layout_learner import classify_component_type, ComponentType, get_connection_type
except ImportError:
    from persistent_layout_learner import classify_component_type, ComponentType, get_connection_type


@dataclass
class ConnectionFeature:
    """Single connection (wire) feature for ML learning"""
    # Source/Target info
    source_guid: str
    target_guid: str
    source_name: str
    target_name: str
    source_type: str  # ComponentType value
    target_type: str

    # Connection type
    connection_type: str  # param_to_comp, comp_to_comp, etc.

    # Position delta (learning target)
    delta_x: float
    delta_y: float

    # Context features (for KNN)
    sibling_count: int = 1      # Number of connections from same source
    sibling_order: int = 0      # Y-order among siblings (0 = topmost)
    source_level: int = 0       # Topology level (0 = input)
    target_level: int = 0

    # Additional context
    source_output_count: int = 1  # Total outputs of source component
    target_input_count: int = 1   # Total inputs of target component


@dataclass
class BranchingPattern:
    """Pattern for 1->N connections (branching)"""
    source_guid: str
    source_name: str
    source_type: str

    target_count: int           # Number of targets (2, 3, 4, ...)
    y_spacings: List[float]     # Y gaps between consecutive targets
    avg_spacing: float          # Average Y spacing

    # Distribution info
    center_offset: float        # Offset of targets' center from source Y
    distribution: str           # "centered", "below_source", "above_source"

    # Target details
    target_names: List[str] = field(default_factory=list)
    target_ys: List[float] = field(default_factory=list)


class LayoutFeatureExtractor:
    """Extracts ML features from Grasshopper canvas"""

    def __init__(self):
        self._component_cache: Dict[str, dict] = {}
        self._levels_cache: Dict[str, int] = {}

    def extract_all_features(
        self,
        components: List[dict],
        wires: List[dict]
    ) -> dict:
        """Extract all features from canvas

        Returns:
            {
                'connection_features': List[ConnectionFeature],
                'branching_patterns': List[BranchingPattern],
                'statistics': dict
            }
        """
        # Build component map
        comp_map = self._build_component_map(components)

        # Calculate topology levels
        levels = self._calculate_topology_levels(comp_map, wires)

        # Analyze branching (source -> multiple targets)
        branching_info = self._analyze_branching(comp_map, wires)

        # Extract connection features
        connection_features = self._extract_connection_features(
            comp_map, wires, levels, branching_info
        )

        # Extract branching patterns
        branching_patterns = self._extract_branching_patterns(
            comp_map, wires, branching_info
        )

        return {
            'connection_features': connection_features,
            'branching_patterns': branching_patterns,
            'statistics': {
                'total_components': len(components),
                'total_wires': len(wires),
                'total_connections': len(connection_features),
                'branching_sources': len(branching_patterns),
                'max_level': max(levels.values()) if levels else 0
            }
        }

    def _build_component_map(self, components: List[dict]) -> Dict[str, dict]:
        """Build guid -> component mapping"""
        comp_map = {}
        for comp in components:
            guid = comp.get('guid') or comp.get('InstanceGuid')
            if guid:
                comp_map[str(guid)] = comp
        return comp_map

    def _calculate_topology_levels(
        self,
        comp_map: Dict[str, dict],
        wires: List[dict]
    ) -> Dict[str, int]:
        """Calculate topology level for each component (BFS from inputs)"""
        # Build adjacency
        outgoing = defaultdict(set)
        incoming = defaultdict(set)

        for wire in wires:
            src = str(wire.get('source_guid', ''))
            tgt = str(wire.get('target_guid', ''))
            if src in comp_map and tgt in comp_map:
                outgoing[src].add(tgt)
                incoming[tgt].add(src)

        # Find sources (no incoming)
        sources = [g for g in comp_map if len(incoming[g]) == 0]

        # BFS to assign levels
        levels = {}
        queue = [(s, 0) for s in sources]

        while queue:
            guid, level = queue.pop(0)
            if guid in levels:
                levels[guid] = max(levels[guid], level)
            else:
                levels[guid] = level
                for tgt in outgoing[guid]:
                    queue.append((tgt, level + 1))

        # Assign level 0 to unvisited
        for guid in comp_map:
            if guid not in levels:
                levels[guid] = 0

        return levels

    def _analyze_branching(
        self,
        comp_map: Dict[str, dict],
        wires: List[dict]
    ) -> Dict[str, dict]:
        """Analyze branching patterns (which sources connect to multiple targets)

        Returns:
            {
                source_guid: {
                    'count': int,           # Number of targets
                    'targets': [guids],     # Target GUIDs
                    'order': {tgt: idx}     # Y-order of each target
                }
            }
        """
        branching = defaultdict(lambda: {'count': 0, 'targets': [], 'order': {}})

        # Group wires by source
        source_targets = defaultdict(list)
        for wire in wires:
            src = str(wire.get('source_guid', ''))
            tgt = str(wire.get('target_guid', ''))
            if src in comp_map and tgt in comp_map:
                source_targets[src].append(tgt)

        # Analyze each source
        for src_guid, targets in source_targets.items():
            if not targets:
                continue

            branching[src_guid]['count'] = len(targets)
            branching[src_guid]['targets'] = targets

            # Sort targets by Y position to determine order
            target_ys = []
            for tgt in targets:
                tgt_comp = comp_map.get(tgt, {})
                y = float(tgt_comp.get('y') or tgt_comp.get('position_y') or 0)
                target_ys.append((tgt, y))

            target_ys.sort(key=lambda x: x[1])  # Sort by Y

            for idx, (tgt, _) in enumerate(target_ys):
                branching[src_guid]['order'][tgt] = idx

        return dict(branching)

    def _extract_connection_features(
        self,
        comp_map: Dict[str, dict],
        wires: List[dict],
        levels: Dict[str, int],
        branching_info: Dict[str, dict]
    ) -> List[ConnectionFeature]:
        """Extract features for each connection"""
        features = []

        for wire in wires:
            src_guid = str(wire.get('source_guid', ''))
            tgt_guid = str(wire.get('target_guid', ''))

            if src_guid not in comp_map or tgt_guid not in comp_map:
                continue

            src_comp = comp_map[src_guid]
            tgt_comp = comp_map[tgt_guid]

            # Get positions
            src_x = float(src_comp.get('x') or src_comp.get('position_x') or 0)
            src_y = float(src_comp.get('y') or src_comp.get('position_y') or 0)
            tgt_x = float(tgt_comp.get('x') or tgt_comp.get('position_x') or 0)
            tgt_y = float(tgt_comp.get('y') or tgt_comp.get('position_y') or 0)

            # Get component types
            src_type = classify_component_type(
                src_comp.get('name', ''),
                src_comp.get('category', ''),
                src_comp.get('subcategory', '')
            )
            tgt_type = classify_component_type(
                tgt_comp.get('name', ''),
                tgt_comp.get('category', ''),
                tgt_comp.get('subcategory', '')
            )

            # Get connection type
            conn_type = get_connection_type(src_type, tgt_type)

            # Get branching info
            branch = branching_info.get(src_guid, {'count': 1, 'order': {}})
            sibling_count = branch['count']
            sibling_order = branch['order'].get(tgt_guid, 0)

            feature = ConnectionFeature(
                source_guid=src_guid,
                target_guid=tgt_guid,
                source_name=src_comp.get('name', ''),
                target_name=tgt_comp.get('name', ''),
                source_type=src_type.value,
                target_type=tgt_type.value,
                connection_type=conn_type,
                delta_x=tgt_x - src_x,
                delta_y=tgt_y - src_y,
                sibling_count=sibling_count,
                sibling_order=sibling_order,
                source_level=levels.get(src_guid, 0),
                target_level=levels.get(tgt_guid, 0)
            )
            features.append(feature)

        return features

    def _extract_branching_patterns(
        self,
        comp_map: Dict[str, dict],
        wires: List[dict],
        branching_info: Dict[str, dict]
    ) -> List[BranchingPattern]:
        """Extract branching patterns (1->N connections)"""
        patterns = []

        for src_guid, info in branching_info.items():
            if info['count'] < 2:  # Only consider actual branching
                continue

            src_comp = comp_map.get(src_guid, {})
            src_y = float(src_comp.get('y') or src_comp.get('position_y') or 0)

            src_type = classify_component_type(
                src_comp.get('name', ''),
                src_comp.get('category', ''),
                src_comp.get('subcategory', '')
            )

            # Collect target Y positions
            target_ys = []
            target_names = []
            for tgt_guid in info['targets']:
                tgt_comp = comp_map.get(tgt_guid, {})
                tgt_y = float(tgt_comp.get('y') or tgt_comp.get('position_y') or 0)
                target_ys.append(tgt_y)
                target_names.append(tgt_comp.get('name', ''))

            # Sort by Y
            sorted_data = sorted(zip(target_ys, target_names))
            target_ys = [y for y, _ in sorted_data]
            target_names = [n for _, n in sorted_data]

            # Calculate spacings
            y_spacings = [target_ys[i+1] - target_ys[i] for i in range(len(target_ys)-1)]
            avg_spacing = sum(y_spacings) / len(y_spacings) if y_spacings else 0

            # Calculate center offset
            targets_center = sum(target_ys) / len(target_ys)
            center_offset = targets_center - src_y

            # Determine distribution
            if abs(center_offset) < 20:
                distribution = "centered"
            elif center_offset > 0:
                distribution = "below_source"
            else:
                distribution = "above_source"

            pattern = BranchingPattern(
                source_guid=src_guid,
                source_name=src_comp.get('name', ''),
                source_type=src_type.value,
                target_count=info['count'],
                y_spacings=y_spacings,
                avg_spacing=avg_spacing,
                center_offset=center_offset,
                distribution=distribution,
                target_names=target_names,
                target_ys=target_ys
            )
            patterns.append(pattern)

        return patterns

    def feature_to_vector(self, feature: ConnectionFeature) -> List[float]:
        """Convert ConnectionFeature to numeric vector for KNN

        Returns 6-dimensional feature vector:
        [source_type, target_type, connection_type, sibling_count, sibling_order, source_level]
        """
        # Type encoding
        type_values = {t.value: i for i, t in enumerate(ComponentType)}
        conn_type_encoding = {
            'param_to_comp': 0,
            'comp_to_comp': 1,
            'comp_to_param': 2,
            'param_to_param': 3
        }

        return [
            type_values.get(feature.source_type, 0),
            type_values.get(feature.target_type, 0),
            conn_type_encoding.get(feature.connection_type, 1),
            min(feature.sibling_count, 10),  # Cap at 10
            min(feature.sibling_order, 10),
            min(feature.source_level, 20)    # Cap at 20
        ]

    def features_to_matrix(
        self,
        features: List[ConnectionFeature]
    ) -> Tuple[List[List[float]], List[float], List[float]]:
        """Convert features to training data matrices

        Returns:
            (X, y_dx, y_dy) where:
            - X: feature matrix (N x 6)
            - y_dx: delta_x targets
            - y_dy: delta_y targets
        """
        X = []
        y_dx = []
        y_dy = []

        for f in features:
            X.append(self.feature_to_vector(f))
            y_dx.append(f.delta_x)
            y_dy.append(f.delta_y)

        return X, y_dx, y_dy


# Singleton instance
_feature_extractor: Optional[LayoutFeatureExtractor] = None


def get_feature_extractor() -> LayoutFeatureExtractor:
    """Get singleton feature extractor instance"""
    global _feature_extractor
    if _feature_extractor is None:
        _feature_extractor = LayoutFeatureExtractor()
    return _feature_extractor
