"""
Layout Learner Module
Learns and applies user's preferred Grasshopper canvas layout patterns.
"""

import json
import os
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path


class LayoutLearner:
    """
    Learns layout patterns from GH files and live canvas,
    then applies them when creating new components.
    """

    DEFAULT_PREFERENCES = {
        "user_id": "default",
        "last_updated": None,
        "samples_count": 0,
        "preferences": {
            "spacing_x": 200,
            "spacing_y": 80,
            "flow_direction": "left_to_right",
            "grid_aligned": True,
            "input_position": "left",
            "wire_style": "horizontal"
        },
        "component_patterns": {},
        "spacing_samples": {
            "x": [],
            "y": []
        }
    }

    def __init__(self, preferences_path: Optional[str] = None):
        if preferences_path is None:
            # Default path next to this file
            self.preferences_path = Path(__file__).parent / "layout_preferences.json"
        else:
            self.preferences_path = Path(preferences_path)

        self.preferences = self.load_preferences()

    def load_preferences(self) -> dict:
        """Load preferences from JSON file"""
        if self.preferences_path.exists():
            try:
                with open(self.preferences_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return self.DEFAULT_PREFERENCES.copy()

    def save_preferences(self):
        """Save preferences to JSON file"""
        self.preferences["last_updated"] = datetime.now().isoformat()
        with open(self.preferences_path, 'w', encoding='utf-8') as f:
            json.dump(self.preferences, f, indent=2, ensure_ascii=False)

    def analyze_gh_file(self, file_path: str) -> dict:
        """
        Analyze a GH file and extract layout patterns.

        Args:
            file_path: Path to .gh or .ghx file

        Returns:
            Dictionary with extracted patterns
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            # Read file content (GH files are gzipped XML)
            if file_path.suffix.lower() == '.gh':
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    content = f.read()
            else:  # .ghx is plain XML
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

            root = ET.fromstring(content)

            # Extract component positions and connections
            components = self._extract_components(root)
            wires = self._extract_wires(root)

            # Calculate patterns
            patterns = self._calculate_patterns(components, wires)

            # Update preferences with new data
            self._update_from_patterns(patterns)

            return {
                "success": True,
                "file": str(file_path),
                "components_found": len(components),
                "wires_found": len(wires),
                "patterns": patterns
            }

        except Exception as e:
            return {"error": str(e)}

    def _extract_components(self, root: ET.Element) -> List[dict]:
        """Extract component positions from XML"""
        components = []

        # Find all objects with pivot points
        for obj in root.iter():
            if obj.tag == "Object":
                comp_data = {
                    "guid": obj.get("Id", ""),
                    "name": obj.get("Name", ""),
                }

                # Find pivot position
                pivot = obj.find(".//Pivot")
                if pivot is not None:
                    x = pivot.get("X") or pivot.find("X")
                    y = pivot.get("Y") or pivot.find("Y")

                    if x is not None and y is not None:
                        try:
                            comp_data["x"] = float(x.text if hasattr(x, 'text') else x)
                            comp_data["y"] = float(y.text if hasattr(y, 'text') else y)
                            components.append(comp_data)
                        except (ValueError, TypeError):
                            pass

        return components

    def _extract_wires(self, root: ET.Element) -> List[dict]:
        """Extract wire connections from XML"""
        wires = []

        for wire in root.iter("Wire"):
            source = wire.find("Source")
            target = wire.find("Target")

            if source is not None and target is not None:
                wires.append({
                    "source_guid": source.get("Id", ""),
                    "target_guid": target.get("Id", "")
                })

        return wires

    def _calculate_patterns(self, components: List[dict], wires: List[dict]) -> dict:
        """Calculate layout patterns from components and wires"""
        if len(components) < 2:
            return {}

        # Build GUID to component map
        guid_map = {c["guid"]: c for c in components if "guid" in c}

        # Calculate spacing between connected components
        x_spacings = []
        y_spacings = []
        flow_directions = {"left_to_right": 0, "right_to_left": 0, "top_to_bottom": 0}

        for wire in wires:
            source = guid_map.get(wire["source_guid"])
            target = guid_map.get(wire["target_guid"])

            if source and target and "x" in source and "x" in target:
                dx = target["x"] - source["x"]
                dy = target["y"] - source["y"]

                x_spacings.append(abs(dx))
                y_spacings.append(abs(dy))

                # Determine flow direction
                if abs(dx) > abs(dy):
                    if dx > 0:
                        flow_directions["left_to_right"] += 1
                    else:
                        flow_directions["right_to_left"] += 1
                else:
                    flow_directions["top_to_bottom"] += 1

        # Calculate averages
        patterns = {}

        if x_spacings:
            patterns["avg_spacing_x"] = sum(x_spacings) / len(x_spacings)
        if y_spacings:
            patterns["avg_spacing_y"] = sum(y_spacings) / len(y_spacings)

        # Determine dominant flow direction
        if flow_directions:
            patterns["flow_direction"] = max(flow_directions, key=flow_directions.get)

        # Check grid alignment
        if components:
            x_coords = [c["x"] for c in components if "x" in c]
            y_coords = [c["y"] for c in components if "y" in c]

            # Check if coordinates cluster around regular intervals
            patterns["grid_aligned"] = self._check_grid_alignment(x_coords, y_coords)

        return patterns

    def _check_grid_alignment(self, x_coords: List[float], y_coords: List[float]) -> bool:
        """Check if coordinates suggest grid-like alignment"""
        if len(x_coords) < 3:
            return True  # Assume grid for small sets

        # Check variance in spacing
        x_sorted = sorted(x_coords)
        spacings = [x_sorted[i+1] - x_sorted[i] for i in range(len(x_sorted)-1)]

        if not spacings:
            return True

        avg_spacing = sum(spacings) / len(spacings)
        if avg_spacing == 0:
            return True

        # Calculate coefficient of variation
        variance = sum((s - avg_spacing) ** 2 for s in spacings) / len(spacings)
        std_dev = variance ** 0.5
        cv = std_dev / avg_spacing if avg_spacing else 0

        # If CV is low, spacing is consistent (grid-like)
        return cv < 0.5

    def _update_from_patterns(self, patterns: dict):
        """Update preferences based on extracted patterns"""
        if not patterns:
            return

        prefs = self.preferences["preferences"]
        samples = self.preferences.get("spacing_samples", {"x": [], "y": []})

        # Add new spacing samples
        if "avg_spacing_x" in patterns:
            samples["x"].append(patterns["avg_spacing_x"])
            # Keep last 50 samples
            samples["x"] = samples["x"][-50:]
            prefs["spacing_x"] = sum(samples["x"]) / len(samples["x"])

        if "avg_spacing_y" in patterns:
            samples["y"].append(patterns["avg_spacing_y"])
            samples["y"] = samples["y"][-50:]
            prefs["spacing_y"] = sum(samples["y"]) / len(samples["y"])

        if "flow_direction" in patterns:
            prefs["flow_direction"] = patterns["flow_direction"]

        if "grid_aligned" in patterns:
            prefs["grid_aligned"] = patterns["grid_aligned"]

        self.preferences["spacing_samples"] = samples
        self.preferences["samples_count"] += 1
        self.save_preferences()

    def analyze_canvas(self, components: List[dict]) -> dict:
        """
        Analyze current canvas state and extract patterns.

        Args:
            components: List of component dicts with name, x, y, guid, etc.

        Returns:
            Extracted patterns
        """
        if len(components) < 2:
            return {}

        # Calculate spacing between adjacent components (by x position)
        sorted_by_x = sorted(components, key=lambda c: c.get("x", 0))

        x_spacings = []
        for i in range(len(sorted_by_x) - 1):
            dx = sorted_by_x[i+1].get("x", 0) - sorted_by_x[i].get("x", 0)
            if dx > 0:
                x_spacings.append(dx)

        # Calculate y spacing for vertically adjacent components
        sorted_by_y = sorted(components, key=lambda c: c.get("y", 0))
        y_spacings = []
        for i in range(len(sorted_by_y) - 1):
            dy = sorted_by_y[i+1].get("y", 0) - sorted_by_y[i].get("y", 0)
            if dy > 0:
                y_spacings.append(dy)

        patterns = {}
        if x_spacings:
            patterns["avg_spacing_x"] = sum(x_spacings) / len(x_spacings)
        if y_spacings:
            patterns["avg_spacing_y"] = sum(y_spacings) / len(y_spacings)

        # Update preferences
        self._update_from_patterns(patterns)

        return patterns

    def get_next_position(
        self,
        component_name: str,
        connected_to: Optional[dict] = None,
        direction: str = "right"
    ) -> Tuple[float, float]:
        """
        Calculate the next component position based on learned patterns.

        Args:
            component_name: Name of the component to place
            connected_to: Component dict this will connect to (with x, y)
            direction: Direction relative to connected component ("right", "below", "left", "above")

        Returns:
            Tuple of (x, y) coordinates
        """
        prefs = self.preferences["preferences"]
        spacing_x = prefs.get("spacing_x", 200)
        spacing_y = prefs.get("spacing_y", 80)

        # Check for component-specific patterns
        comp_patterns = self.preferences.get("component_patterns", {})
        if component_name in comp_patterns:
            offset = comp_patterns[component_name]
            if connected_to and "x" in connected_to and "y" in connected_to:
                return (
                    connected_to["x"] + offset.get("offset_x", spacing_x),
                    connected_to["y"] + offset.get("offset_y", 0)
                )

        # Default positioning based on direction
        if connected_to and "x" in connected_to and "y" in connected_to:
            base_x = connected_to["x"]
            base_y = connected_to["y"]

            if direction == "right":
                return (base_x + spacing_x, base_y)
            elif direction == "below":
                return (base_x, base_y + spacing_y)
            elif direction == "left":
                return (base_x - spacing_x, base_y)
            elif direction == "above":
                return (base_x, base_y - spacing_y)

        # No reference component, start at origin
        return (0, 0)

    def learn_component_pattern(
        self,
        component_name: str,
        offset_x: float,
        offset_y: float
    ):
        """
        Learn a specific offset pattern for a component type.

        Args:
            component_name: Name of the component
            offset_x: X offset from connected component
            offset_y: Y offset from connected component
        """
        if "component_patterns" not in self.preferences:
            self.preferences["component_patterns"] = {}

        # Running average for the component
        existing = self.preferences["component_patterns"].get(component_name, {})
        count = existing.get("count", 0)

        if count > 0:
            # Update running average
            old_x = existing.get("offset_x", 0)
            old_y = existing.get("offset_y", 0)
            new_x = (old_x * count + offset_x) / (count + 1)
            new_y = (old_y * count + offset_y) / (count + 1)
        else:
            new_x = offset_x
            new_y = offset_y

        self.preferences["component_patterns"][component_name] = {
            "offset_x": new_x,
            "offset_y": new_y,
            "count": count + 1
        }

        self.save_preferences()

    def get_preferences_summary(self) -> dict:
        """Get a summary of current learned preferences"""
        prefs = self.preferences["preferences"]
        return {
            "spacing_x": round(prefs.get("spacing_x", 200), 1),
            "spacing_y": round(prefs.get("spacing_y", 80), 1),
            "flow_direction": prefs.get("flow_direction", "left_to_right"),
            "grid_aligned": prefs.get("grid_aligned", True),
            "samples_count": self.preferences.get("samples_count", 0),
            "component_patterns_count": len(self.preferences.get("component_patterns", {}))
        }


# Singleton instance
_learner: Optional[LayoutLearner] = None


def get_learner(preferences_path: Optional[str] = None) -> LayoutLearner:
    """Get or create the layout learner instance"""
    global _learner
    if _learner is None:
        _learner = LayoutLearner(preferences_path)
    return _learner
