"""
Grasshopper File Operations Module
Read, parse, and modify .gh/.ghx Grasshopper definition files

.ghx files are XML-based and can be parsed directly
.gh files are gzip-compressed .ghx files
"""

import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class GHComponent:
    """Represents a component in a Grasshopper definition"""
    guid: str
    name: str
    nickname: str
    category: str
    subcategory: str
    position_x: float
    position_y: float
    instance_guid: str


@dataclass
class GHWire:
    """Represents a wire connection between components"""
    source_component: str
    source_param: str
    target_component: str
    target_param: str


@dataclass
class GHDefinition:
    """Represents a parsed Grasshopper definition"""
    file_path: str
    components: list[GHComponent]
    wires: list[GHWire]
    metadata: dict


def read_gh_file(file_path: str) -> str:
    """Read a .gh or .ghx file and return XML content"""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = path.suffix.lower()

    if suffix == ".ghx":
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    elif suffix == ".gh":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def parse_gh_definition(file_path: str) -> GHDefinition:
    """Parse a Grasshopper definition file"""
    xml_content = read_gh_file(file_path)
    root = ET.fromstring(xml_content)

    components = []
    wires = []
    metadata = {}

    # Extract document metadata
    doc_header = root.find(".//DocumentHeader")
    if doc_header is not None:
        metadata["document_id"] = doc_header.get("DocumentID", "")

    # Parse components (Objects in GH XML)
    for obj in root.findall(".//Object"):
        try:
            name = obj.get("Name", "Unknown")
            guid = obj.get("Id", "")

            # Get component container
            container = obj.find("Container")
            if container is not None:
                nickname = container.get("NickName", name)

                # Get position from Attributes
                attrs = container.find("Attributes")
                pos_x, pos_y = 0.0, 0.0
                if attrs is not None:
                    bounds = attrs.get("Bounds", "")
                    if bounds:
                        parts = bounds.split(",")
                        if len(parts) >= 2:
                            pos_x = float(parts[0])
                            pos_y = float(parts[1])

                components.append(GHComponent(
                    guid=guid,
                    name=name,
                    nickname=nickname,
                    category="",
                    subcategory="",
                    position_x=pos_x,
                    position_y=pos_y,
                    instance_guid=container.get("InstanceGuid", "")
                ))
        except Exception:
            continue

    # Parse wires/connections
    for wire in root.findall(".//Wire"):
        try:
            source = wire.get("Source", "")
            target = wire.get("Target", "")
            if source and target:
                # Format is typically "ComponentGuid/ParamIndex"
                src_parts = source.split("/")
                tgt_parts = target.split("/")

                wires.append(GHWire(
                    source_component=src_parts[0] if src_parts else "",
                    source_param=src_parts[1] if len(src_parts) > 1 else "0",
                    target_component=tgt_parts[0] if tgt_parts else "",
                    target_param=tgt_parts[1] if len(tgt_parts) > 1 else "0"
                ))
        except Exception:
            continue

    return GHDefinition(
        file_path=str(file_path),
        components=components,
        wires=wires,
        metadata=metadata
    )


def get_definition_summary(file_path: str) -> dict:
    """Get a summary of a Grasshopper definition"""
    try:
        definition = parse_gh_definition(file_path)

        # Count components by type
        component_counts = {}
        for comp in definition.components:
            name = comp.name
            component_counts[name] = component_counts.get(name, 0) + 1

        return {
            "file": file_path,
            "total_components": len(definition.components),
            "total_wires": len(definition.wires),
            "component_types": component_counts,
            "metadata": definition.metadata
        }
    except Exception as e:
        return {
            "file": file_path,
            "error": str(e)
        }


def list_components(file_path: str) -> list[dict]:
    """List all components in a definition"""
    definition = parse_gh_definition(file_path)
    return [asdict(c) for c in definition.components]


def get_xml_content(file_path: str) -> str:
    """Get raw XML content of a GH file"""
    return read_gh_file(file_path)


def find_components_by_name(file_path: str, name_pattern: str) -> list[dict]:
    """Find components matching a name pattern"""
    definition = parse_gh_definition(file_path)
    pattern_lower = name_pattern.lower()

    matches = []
    for comp in definition.components:
        if pattern_lower in comp.name.lower() or pattern_lower in comp.nickname.lower():
            matches.append(asdict(comp))

    return matches
