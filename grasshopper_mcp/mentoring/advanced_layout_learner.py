"""
Advanced Layout Learner - KNN-based ML Layout Learning

Uses K-Nearest Neighbors to learn and predict component positions
based on user's layout patterns.
"""

import json
import os
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    from sklearn.neighbors import KNeighborsRegressor
    import numpy as np
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    print("Warning: scikit-learn not installed. KNN features disabled.")

try:
    from .feature_extractor import (
        LayoutFeatureExtractor,
        ConnectionFeature,
        BranchingPattern,
        get_feature_extractor
    )
    from .persistent_layout_learner import classify_component_type, ComponentType
except ImportError:
    from feature_extractor import (
        LayoutFeatureExtractor,
        ConnectionFeature,
        BranchingPattern,
        get_feature_extractor
    )
    from persistent_layout_learner import classify_component_type, ComponentType


@dataclass
class ComponentPairPattern:
    """Learning pattern for specific component pair (A -> B)"""
    source_name: str
    target_name: str
    mean_dx: float
    mean_dy: float
    sample_count: int
    samples: List[Dict]  # [{dx, dy, sibling_count, ...}]
    confidence: float = 0.5

    def add_sample(self, dx: float, dy: float, context: dict = None):
        """Add a new sample and update statistics"""
        sample = {'dx': dx, 'dy': dy}
        if context:
            sample.update(context)

        self.samples.append(sample)

        # Keep only last 50 samples
        if len(self.samples) > 50:
            self.samples = self.samples[-50:]

        # Update statistics
        self.sample_count = len(self.samples)
        self.mean_dx = sum(s['dx'] for s in self.samples) / self.sample_count
        self.mean_dy = sum(s['dy'] for s in self.samples) / self.sample_count

        # Update confidence (more samples = higher confidence)
        self.confidence = min(0.95, 0.5 + self.sample_count * 0.03)


@dataclass
class BranchingPatternStats:
    """Statistics for 1->N branching patterns"""
    pattern_key: str  # "1_to_2", "1_to_3", etc.
    avg_spacing: float
    distribution: str  # "centered", "below_source", "above_source"
    sample_count: int
    spacing_samples: List[float]

    def add_sample(self, spacings: List[float], distribution: str):
        """Add branching sample"""
        self.spacing_samples.extend(spacings)

        # Keep only last 100 spacing samples
        if len(self.spacing_samples) > 100:
            self.spacing_samples = self.spacing_samples[-100:]

        self.sample_count = len(self.spacing_samples)
        self.avg_spacing = sum(self.spacing_samples) / self.sample_count if self.spacing_samples else 80.0

        # Update distribution (majority vote)
        # For simplicity, just use latest
        self.distribution = distribution


class AdvancedLayoutLearner:
    """KNN-based ML layout learner"""

    VERSION = "4.0"

    def __init__(self, storage_path: str = None):
        self.feature_extractor = get_feature_extractor()

        # Learning data
        self.component_pair_patterns: Dict[str, ComponentPairPattern] = {}
        self.branching_patterns: Dict[str, BranchingPatternStats] = {}

        # KNN training data
        self.training_features: List[List[float]] = []
        self.training_dx: List[float] = []
        self.training_dy: List[float] = []

        # KNN models
        self.knn_dx = None
        self.knn_dy = None
        self.knn_ready = False

        # Metadata
        self.total_sessions = 0
        self.total_connections_learned = 0
        self.last_updated = None

        # Storage
        if storage_path:
            self.storage_path = storage_path
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.storage_path = os.path.join(current_dir, "advanced_learning_data.json")

        # Load existing data
        self.load()

    def learn_from_canvas(
        self,
        components: List[dict],
        wires: List[dict],
        source_name: str = "manual"
    ) -> dict:
        """Learn patterns from current canvas layout

        Args:
            components: List of component dicts from canvas
            wires: List of wire dicts from canvas
            source_name: Name of source file/session

        Returns:
            Learning summary
        """
        # Extract features
        extracted = self.feature_extractor.extract_all_features(components, wires)
        connection_features = extracted['connection_features']
        branching_list = extracted['branching_patterns']

        # Learn component pair patterns
        pairs_learned = 0
        for feature in connection_features:
            pair_key = f"{feature.source_name} -> {feature.target_name}"

            if pair_key not in self.component_pair_patterns:
                self.component_pair_patterns[pair_key] = ComponentPairPattern(
                    source_name=feature.source_name,
                    target_name=feature.target_name,
                    mean_dx=feature.delta_x,
                    mean_dy=feature.delta_y,
                    sample_count=0,
                    samples=[]
                )

            self.component_pair_patterns[pair_key].add_sample(
                dx=feature.delta_x,
                dy=feature.delta_y,
                context={
                    'sibling_count': feature.sibling_count,
                    'sibling_order': feature.sibling_order,
                    'source_level': feature.source_level
                }
            )
            pairs_learned += 1

        # Learn branching patterns
        branches_learned = 0
        for bp in branching_list:
            pattern_key = f"1_to_{bp.target_count}"

            if pattern_key not in self.branching_patterns:
                self.branching_patterns[pattern_key] = BranchingPatternStats(
                    pattern_key=pattern_key,
                    avg_spacing=bp.avg_spacing,
                    distribution=bp.distribution,
                    sample_count=0,
                    spacing_samples=[]
                )

            self.branching_patterns[pattern_key].add_sample(
                spacings=bp.y_spacings,
                distribution=bp.distribution
            )
            branches_learned += 1

        # Update KNN training data
        X, y_dx, y_dy = self.feature_extractor.features_to_matrix(connection_features)
        self.training_features.extend(X)
        self.training_dx.extend(y_dx)
        self.training_dy.extend(y_dy)

        # Keep training data bounded
        max_samples = 2000
        if len(self.training_features) > max_samples:
            self.training_features = self.training_features[-max_samples:]
            self.training_dx = self.training_dx[-max_samples:]
            self.training_dy = self.training_dy[-max_samples:]

        # Retrain KNN if enough samples
        if len(self.training_features) >= 30:
            self._train_knn()

        # Update metadata
        self.total_sessions += 1
        self.total_connections_learned += len(connection_features)
        self.last_updated = datetime.now().isoformat()

        # Save
        self.save()

        return {
            'success': True,
            'pairs_learned': pairs_learned,
            'branches_learned': branches_learned,
            'total_pair_patterns': len(self.component_pair_patterns),
            'total_branching_patterns': len(self.branching_patterns),
            'knn_ready': self.knn_ready,
            'knn_samples': len(self.training_features),
            'source': source_name
        }

    def _train_knn(self):
        """Train KNN models for dx and dy prediction"""
        if not HAS_SKLEARN:
            return

        if len(self.training_features) < 5:
            return

        try:
            X = np.array(self.training_features)
            y_dx = np.array(self.training_dx)
            y_dy = np.array(self.training_dy)

            k = min(5, len(X))

            self.knn_dx = KNeighborsRegressor(n_neighbors=k, weights='distance')
            self.knn_dy = KNeighborsRegressor(n_neighbors=k, weights='distance')

            self.knn_dx.fit(X, y_dx)
            self.knn_dy.fit(X, y_dy)

            self.knn_ready = True
        except Exception as e:
            print(f"KNN training error: {e}")
            self.knn_ready = False

    def predict_position(
        self,
        source_comp: dict,
        target_name: str,
        context: dict = None
    ) -> dict:
        """Predict optimal position for target component

        Priority:
        1. Component pair pattern (if enough samples)
        2. KNN prediction (if model ready)
        3. Fallback to default spacing

        Args:
            source_comp: Source component dict
            target_name: Name of target component
            context: Additional context (sibling_count, sibling_order, etc.)

        Returns:
            {x, y, confidence, method, details}
        """
        source_name = source_comp.get('name', '')
        source_x = float(source_comp.get('x') or source_comp.get('position_x') or 0)
        source_y = float(source_comp.get('y') or source_comp.get('position_y') or 0)

        context = context or {}

        # Method 1: Component pair pattern
        pair_key = f"{source_name} -> {target_name}"
        if pair_key in self.component_pair_patterns:
            pattern = self.component_pair_patterns[pair_key]
            if pattern.sample_count >= 3:
                return {
                    'x': source_x + pattern.mean_dx,
                    'y': source_y + pattern.mean_dy,
                    'confidence': pattern.confidence,
                    'method': 'component_pair',
                    'details': {
                        'pair': pair_key,
                        'samples': pattern.sample_count,
                        'mean_dx': pattern.mean_dx,
                        'mean_dy': pattern.mean_dy
                    }
                }

        # Method 2: KNN prediction
        if self.knn_ready and HAS_SKLEARN:
            try:
                # Build feature vector
                source_type = classify_component_type(
                    source_name,
                    source_comp.get('category', ''),
                    source_comp.get('subcategory', '')
                )
                target_type = classify_component_type(target_name, '', '')

                from .persistent_layout_learner import get_connection_type
                conn_type = get_connection_type(source_type, target_type)

                # Encode
                type_values = {t.value: i for i, t in enumerate(ComponentType)}
                conn_encoding = {
                    'param_to_comp': 0, 'comp_to_comp': 1,
                    'comp_to_param': 2, 'param_to_param': 3
                }

                feature = [
                    type_values.get(source_type.value, 0),
                    type_values.get(target_type.value, 0),
                    conn_encoding.get(conn_type, 1),
                    context.get('sibling_count', 1),
                    context.get('sibling_order', 0),
                    context.get('source_level', 0)
                ]

                X = np.array([feature])
                dx = self.knn_dx.predict(X)[0]
                dy = self.knn_dy.predict(X)[0]

                # Calculate confidence from neighbor distances
                distances, _ = self.knn_dx.kneighbors(X)
                confidence = 1 / (1 + np.mean(distances))
                confidence = min(0.85, max(0.3, confidence))

                return {
                    'x': source_x + dx,
                    'y': source_y + dy,
                    'confidence': confidence,
                    'method': 'knn',
                    'details': {
                        'predicted_dx': dx,
                        'predicted_dy': dy,
                        'feature_vector': feature
                    }
                }
            except Exception as e:
                pass  # Fall through to default

        # Method 3: Fallback
        default_dx = 200.0
        default_dy = 0.0

        return {
            'x': source_x + default_dx,
            'y': source_y + default_dy,
            'confidence': 0.3,
            'method': 'fallback',
            'details': {'reason': 'no_learned_pattern'}
        }

    def predict_branching_positions(
        self,
        source_comp: dict,
        target_count: int
    ) -> dict:
        """Predict Y positions for branching (1->N connection)

        Args:
            source_comp: Source component dict
            target_count: Number of targets

        Returns:
            {y_positions: List[float], spacing, distribution, confidence}
        """
        source_y = float(source_comp.get('y') or source_comp.get('position_y') or 0)

        pattern_key = f"1_to_{target_count}"

        if pattern_key in self.branching_patterns:
            pattern = self.branching_patterns[pattern_key]
            spacing = pattern.avg_spacing
            distribution = pattern.distribution

            # Calculate Y positions based on distribution
            total_height = spacing * (target_count - 1)

            if distribution == "centered":
                start_y = source_y - total_height / 2
            elif distribution == "below_source":
                start_y = source_y
            else:  # above_source
                start_y = source_y - total_height

            y_positions = [start_y + i * spacing for i in range(target_count)]

            confidence = min(0.9, 0.5 + pattern.sample_count * 0.02)

            return {
                'y_positions': y_positions,
                'spacing': spacing,
                'distribution': distribution,
                'confidence': confidence,
                'method': 'learned_pattern',
                'samples': pattern.sample_count
            }

        # Default: centered distribution with 80px spacing
        spacing = 80.0
        total_height = spacing * (target_count - 1)
        start_y = source_y - total_height / 2
        y_positions = [start_y + i * spacing for i in range(target_count)]

        return {
            'y_positions': y_positions,
            'spacing': spacing,
            'distribution': 'centered',
            'confidence': 0.3,
            'method': 'default'
        }

    def get_learned_spacing(
        self,
        source_name: str,
        target_name: str,
        connection_type: str = None
    ) -> Optional[Tuple[float, float, float]]:
        """Get learned spacing for component pair

        Returns:
            (dx, dy, confidence) or None if no pattern
        """
        pair_key = f"{source_name} -> {target_name}"

        if pair_key in self.component_pair_patterns:
            pattern = self.component_pair_patterns[pair_key]
            if pattern.sample_count >= 2:
                return (pattern.mean_dx, pattern.mean_dy, pattern.confidence)

        return None

    def save(self):
        """Save learning data to JSON"""
        data = {
            'version': self.VERSION,
            'meta': {
                'total_sessions': self.total_sessions,
                'total_connections_learned': self.total_connections_learned,
                'last_updated': self.last_updated,
                'knn_ready': self.knn_ready,
                'knn_samples': len(self.training_features)
            },
            'component_pair_patterns': {},
            'branching_patterns': {},
            'knn_training_data': {
                'features': self.training_features[-500:],  # Save last 500
                'dx': self.training_dx[-500:],
                'dy': self.training_dy[-500:]
            }
        }

        # Serialize component pair patterns
        for key, pattern in self.component_pair_patterns.items():
            data['component_pair_patterns'][key] = {
                'source_name': pattern.source_name,
                'target_name': pattern.target_name,
                'mean_dx': pattern.mean_dx,
                'mean_dy': pattern.mean_dy,
                'sample_count': pattern.sample_count,
                'samples': pattern.samples[-20:],  # Keep last 20
                'confidence': pattern.confidence
            }

        # Serialize branching patterns
        for key, pattern in self.branching_patterns.items():
            data['branching_patterns'][key] = {
                'pattern_key': pattern.pattern_key,
                'avg_spacing': pattern.avg_spacing,
                'distribution': pattern.distribution,
                'sample_count': pattern.sample_count,
                'spacing_samples': pattern.spacing_samples[-50:]  # Keep last 50
            }

        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving advanced learning data: {e}")

    def load(self):
        """Load learning data from JSON"""
        if not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load metadata
            meta = data.get('meta', {})
            self.total_sessions = meta.get('total_sessions', 0)
            self.total_connections_learned = meta.get('total_connections_learned', 0)
            self.last_updated = meta.get('last_updated')

            # Load component pair patterns
            for key, pdata in data.get('component_pair_patterns', {}).items():
                self.component_pair_patterns[key] = ComponentPairPattern(
                    source_name=pdata['source_name'],
                    target_name=pdata['target_name'],
                    mean_dx=pdata['mean_dx'],
                    mean_dy=pdata['mean_dy'],
                    sample_count=pdata['sample_count'],
                    samples=pdata.get('samples', []),
                    confidence=pdata.get('confidence', 0.5)
                )

            # Load branching patterns
            for key, pdata in data.get('branching_patterns', {}).items():
                self.branching_patterns[key] = BranchingPatternStats(
                    pattern_key=pdata['pattern_key'],
                    avg_spacing=pdata['avg_spacing'],
                    distribution=pdata['distribution'],
                    sample_count=pdata['sample_count'],
                    spacing_samples=pdata.get('spacing_samples', [])
                )

            # Load KNN training data
            knn_data = data.get('knn_training_data', {})
            self.training_features = knn_data.get('features', [])
            self.training_dx = knn_data.get('dx', [])
            self.training_dy = knn_data.get('dy', [])

            # Retrain KNN if we have data
            if len(self.training_features) >= 30:
                self._train_knn()

        except Exception as e:
            print(f"Error loading advanced learning data: {e}")

    def get_summary(self) -> dict:
        """Get learning summary"""
        return {
            'version': self.VERSION,
            'total_sessions': self.total_sessions,
            'total_connections_learned': self.total_connections_learned,
            'component_pair_patterns': len(self.component_pair_patterns),
            'branching_patterns': len(self.branching_patterns),
            'knn_ready': self.knn_ready,
            'knn_samples': len(self.training_features),
            'last_updated': self.last_updated,
            'top_patterns': self._get_top_patterns(5)
        }

    def _get_top_patterns(self, n: int = 5) -> List[dict]:
        """Get top N most used patterns"""
        patterns = [
            {
                'pair': key,
                'samples': p.sample_count,
                'dx': round(p.mean_dx, 1),
                'dy': round(p.mean_dy, 1)
            }
            for key, p in self.component_pair_patterns.items()
        ]
        patterns.sort(key=lambda x: x['samples'], reverse=True)
        return patterns[:n]

    def clear(self) -> dict:
        """Clear all learning data"""
        self.component_pair_patterns.clear()
        self.branching_patterns.clear()
        self.training_features.clear()
        self.training_dx.clear()
        self.training_dy.clear()
        self.knn_dx = None
        self.knn_dy = None
        self.knn_ready = False
        self.total_sessions = 0
        self.total_connections_learned = 0
        self.last_updated = None

        # Delete storage file
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)

        return {
            "success": True,
            "message": "Advanced learning data cleared"
        }


# Singleton
_advanced_learner: Optional[AdvancedLayoutLearner] = None


def get_advanced_learner(storage_path: str = None) -> AdvancedLayoutLearner:
    """Get singleton advanced learner instance"""
    global _advanced_learner
    if _advanced_learner is None:
        _advanced_learner = AdvancedLayoutLearner(storage_path)
    return _advanced_learner


def reset_advanced_learner():
    """Reset singleton"""
    global _advanced_learner
    _advanced_learner = None
