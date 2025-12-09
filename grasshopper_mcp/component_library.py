"""
Grasshopper Component Library
Searchable database of Grasshopper components with documentation
"""

import json
from typing import Optional
from dataclasses import dataclass, asdict
from pathlib import Path


# =============================================================================
# PREFERRED COMPONENT MAP
# When a component name has multiple versions (old vs new), specify which to use
# Format: "ComponentName": ("Category", "SubCategory") or None to use default
# =============================================================================
PREFERRED_COMPONENTS = {
    # Curve components - prefer Curve/Primitive over Params/Geometry
    "Rectangle": ("Curve", "Primitive"),
    "Circle": ("Curve", "Primitive"),
    "Line": ("Curve", "Primitive"),
    "Arc": ("Curve", "Primitive"),
    "Polygon": ("Curve", "Primitive"),
    "Polyline": ("Curve", "Primitive"),

    # Transform components - prefer Transform/Euclidean over Vector/Vector
    "Rotate": ("Transform", "Euclidean"),
    "Move": ("Transform", "Euclidean"),
    "Scale": ("Transform", "Euclidean"),
    "Mirror": ("Transform", "Euclidean"),
    "Orient": ("Transform", "Euclidean"),

    # Surface components
    "Extrude": ("Surface", "Freeform"),
    "Loft": ("Surface", "Freeform"),
    "Pipe": ("Surface", "Freeform"),
    "Sweep1": ("Surface", "Freeform"),
    "Sweep2": ("Surface", "Freeform"),

    # Box components - prefer Surface/Primitive
    "Box": ("Surface", "Primitive"),
    "Center Box": ("Surface", "Primitive"),
    "Box 2Pt": ("Surface", "Primitive"),

    # Vector components
    "Unit X": ("Vector", "Vector"),
    "Unit Y": ("Vector", "Vector"),
    "Unit Z": ("Vector", "Vector"),
    "Vector 2Pt": ("Vector", "Vector"),
    "Amplitude": ("Vector", "Vector"),

    # Point components
    "Construct Point": ("Vector", "Point"),
    "Deconstruct Point": ("Vector", "Point"),
    "Distance": ("Vector", "Point"),

    # Sets components
    "Series": ("Sets", "Sequence"),
    "Range": ("Sets", "Sequence"),
    "Random": ("Sets", "Sequence"),
    "Repeat": ("Sets", "Sequence"),

    # List components
    "List Item": ("Sets", "List"),
    "List Length": ("Sets", "List"),
    "Reverse List": ("Sets", "List"),
    "Shift List": ("Sets", "List"),
    "Cross Reference": ("Sets", "List"),

    # Math components
    "Addition": ("Maths", "Operators"),
    "Subtraction": ("Maths", "Operators"),
    "Multiplication": ("Maths", "Operators"),
    "Division": ("Maths", "Operators"),
    "Radians": ("Maths", "Trig"),
    "Degrees": ("Maths", "Trig"),

    # Domain components
    "Construct Domain": ("Maths", "Domain"),
    "Remap Numbers": ("Maths", "Domain"),

    # Curve Division/Analysis
    "Divide Curve": ("Curve", "Division"),
    "Evaluate Curve": ("Curve", "Analysis"),
    "Curve Length": ("Curve", "Analysis"),
}


def get_find_component_code() -> str:
    """
    Returns Python code that can be executed in Rhino/Grasshopper
    to find the correct component by name, category, and subcategory.

    This code should be prepended to any script that creates GH components.
    """
    return '''
# =============================================================================
# Component Finder Helper - Ensures correct component version is used
# =============================================================================
PREFERRED_COMPONENTS = {
    "Rectangle": ("Curve", "Primitive"),
    "Circle": ("Curve", "Primitive"),
    "Line": ("Curve", "Primitive"),
    "Arc": ("Curve", "Primitive"),
    "Polygon": ("Curve", "Primitive"),
    "Polyline": ("Curve", "Primitive"),
    "Rotate": ("Transform", "Euclidean"),
    "Move": ("Transform", "Euclidean"),
    "Scale": ("Transform", "Euclidean"),
    "Mirror": ("Transform", "Euclidean"),
    "Orient": ("Transform", "Euclidean"),
    "Extrude": ("Surface", "Freeform"),
    "Loft": ("Surface", "Freeform"),
    "Pipe": ("Surface", "Freeform"),
    "Sweep1": ("Surface", "Freeform"),
    "Sweep2": ("Surface", "Freeform"),
    "Box": ("Surface", "Primitive"),
    "Center Box": ("Surface", "Primitive"),
    "Box 2Pt": ("Surface", "Primitive"),
    "Unit X": ("Vector", "Vector"),
    "Unit Y": ("Vector", "Vector"),
    "Unit Z": ("Vector", "Vector"),
    "Vector 2Pt": ("Vector", "Vector"),
    "Amplitude": ("Vector", "Vector"),
    "Construct Point": ("Vector", "Point"),
    "Deconstruct Point": ("Vector", "Point"),
    "Distance": ("Vector", "Point"),
    "Series": ("Sets", "Sequence"),
    "Range": ("Sets", "Sequence"),
    "Random": ("Sets", "Sequence"),
    "Repeat": ("Sets", "Sequence"),
    "List Item": ("Sets", "List"),
    "List Length": ("Sets", "List"),
    "Reverse List": ("Sets", "List"),
    "Shift List": ("Sets", "List"),
    "Cross Reference": ("Sets", "List"),
    "Addition": ("Maths", "Operators"),
    "Subtraction": ("Maths", "Operators"),
    "Multiplication": ("Maths", "Operators"),
    "Division": ("Maths", "Operators"),
    "Radians": ("Maths", "Trig"),
    "Degrees": ("Maths", "Trig"),
    "Construct Domain": ("Maths", "Domain"),
    "Remap Numbers": ("Maths", "Domain"),
    "Divide Curve": ("Curve", "Division"),
    "Evaluate Curve": ("Curve", "Analysis"),
    "Curve Length": ("Curve", "Analysis"),
}

def find_component(server, name, category=None, subcategory=None):
    """
    Find a Grasshopper component by name with preference for specific category/subcategory.

    Args:
        server: Grasshopper.Instances.ComponentServer
        name: Component name (e.g., "Rectangle", "Rotate")
        category: Optional category override (e.g., "Curve", "Transform")
        subcategory: Optional subcategory override (e.g., "Primitive", "Euclidean")

    Returns:
        Component proxy or None
    """
    # Use preference map if no explicit category given
    if category is None and name in PREFERRED_COMPONENTS:
        category, subcategory = PREFERRED_COMPONENTS[name]

    # Search for exact match first
    if category is not None:
        for proxy in server.ObjectProxies:
            if proxy.Desc.Name == name and proxy.Desc.Category == category:
                if subcategory is None or proxy.Desc.SubCategory == subcategory:
                    return proxy

    # Fallback to default search
    return server.FindObjectByName(name, True, True)

def create_component(server, doc, name, x, y, category=None, subcategory=None):
    """
    Create a component and add it to the document at specified position.

    Args:
        server: Grasshopper.Instances.ComponentServer
        doc: Grasshopper document
        name: Component name
        x, y: Canvas position
        category: Optional category override
        subcategory: Optional subcategory override

    Returns:
        Created component instance or None
    """
    import System.Drawing as SD

    proxy = find_component(server, name, category, subcategory)
    if proxy is None:
        print(f"Component not found: {name}")
        return None

    comp = proxy.CreateInstance()
    comp.CreateAttributes()
    comp.Attributes.Pivot = SD.PointF(x, y)
    doc.AddObject(comp, False)
    return comp
'''


@dataclass
class ComponentInfo:
    """Information about a Grasshopper component"""
    name: str
    guid: str
    category: str
    subcategory: str
    description: str
    inputs: list[dict]
    outputs: list[dict]
    keywords: list[str]


# Core Grasshopper components database
# This is a subset - the full database would be much larger
COMPONENT_DATABASE: list[dict] = [
    # Params - Geometry
    {
        "name": "Point",
        "guid": "3581f42a-9592-4549-bd6b-1c0fc39d067b",
        "category": "Params",
        "subcategory": "Geometry",
        "description": "Contains a collection of 3D points",
        "inputs": [],
        "outputs": [{"name": "Point", "type": "Point3d", "description": "Point data"}],
        "keywords": ["pt", "vertex", "location"]
    },
    {
        "name": "Curve",
        "guid": "59e0b89a-e487-49f8-bab8-b5bab16be14c",
        "category": "Params",
        "subcategory": "Geometry",
        "description": "Contains a collection of curves",
        "inputs": [],
        "outputs": [{"name": "Curve", "type": "Curve", "description": "Curve data"}],
        "keywords": ["line", "polyline", "arc", "spline"]
    },
    {
        "name": "Surface",
        "guid": "b7e9f4aa-8c7f-4d91-b0c8-8e3a63c77d17",
        "category": "Params",
        "subcategory": "Geometry",
        "description": "Contains a collection of surfaces",
        "inputs": [],
        "outputs": [{"name": "Surface", "type": "Surface", "description": "Surface data"}],
        "keywords": ["srf", "nurbs", "face"]
    },
    {
        "name": "Brep",
        "guid": "2a8b1c3d-4e5f-6789-abcd-ef0123456789",
        "category": "Params",
        "subcategory": "Geometry",
        "description": "Contains a collection of Breps (boundary representations)",
        "inputs": [],
        "outputs": [{"name": "Brep", "type": "Brep", "description": "Brep geometry"}],
        "keywords": ["solid", "polysurface", "boundary"]
    },
    {
        "name": "Mesh",
        "guid": "8d3e4f5a-6b7c-8d9e-0f1a-2b3c4d5e6f7a",
        "category": "Params",
        "subcategory": "Geometry",
        "description": "Contains a collection of meshes",
        "inputs": [],
        "outputs": [{"name": "Mesh", "type": "Mesh", "description": "Mesh geometry"}],
        "keywords": ["polygon", "triangulate", "vertices", "faces"]
    },

    # Params - Primitive
    {
        "name": "Number Slider",
        "guid": "57da07bd-ecab-415d-9d86-af36d7073abc",
        "category": "Params",
        "subcategory": "Input",
        "description": "Numeric slider for input values",
        "inputs": [],
        "outputs": [{"name": "Number", "type": "double", "description": "Slider value"}],
        "keywords": ["slider", "value", "input", "parameter"]
    },
    {
        "name": "Panel",
        "guid": "59e0b89a-e487-49f8-bab8-b5bab16be14c",
        "category": "Params",
        "subcategory": "Input",
        "description": "Text panel for displaying or inputting data",
        "inputs": [{"name": "Input", "type": "any", "description": "Data to display"}],
        "outputs": [{"name": "Output", "type": "string", "description": "Panel content"}],
        "keywords": ["text", "display", "output", "debug"]
    },
    {
        "name": "Boolean Toggle",
        "guid": "2e78987b-9dfb-42a2-8b76-3923ac8bd91a",
        "category": "Params",
        "subcategory": "Input",
        "description": "Boolean true/false toggle",
        "inputs": [],
        "outputs": [{"name": "Boolean", "type": "bool", "description": "True or False"}],
        "keywords": ["true", "false", "switch", "toggle", "on", "off"]
    },

    # Maths - Operators
    {
        "name": "Addition",
        "guid": "a0d62394-a118-422d-abb3-6af115c75b25",
        "category": "Maths",
        "subcategory": "Operators",
        "description": "Mathematical addition",
        "inputs": [
            {"name": "A", "type": "double", "description": "First operand"},
            {"name": "B", "type": "double", "description": "Second operand"}
        ],
        "outputs": [{"name": "Result", "type": "double", "description": "A + B"}],
        "keywords": ["add", "plus", "sum", "+"]
    },
    {
        "name": "Subtraction",
        "guid": "b1e73405-b229-533e-ccc4-7bf226d86b36",
        "category": "Maths",
        "subcategory": "Operators",
        "description": "Mathematical subtraction",
        "inputs": [
            {"name": "A", "type": "double", "description": "First operand"},
            {"name": "B", "type": "double", "description": "Second operand"}
        ],
        "outputs": [{"name": "Result", "type": "double", "description": "A - B"}],
        "keywords": ["subtract", "minus", "difference", "-"]
    },
    {
        "name": "Multiplication",
        "guid": "c2f84516-c33a-644f-ddd5-8cf337e97c47",
        "category": "Maths",
        "subcategory": "Operators",
        "description": "Mathematical multiplication",
        "inputs": [
            {"name": "A", "type": "double", "description": "First operand"},
            {"name": "B", "type": "double", "description": "Second operand"}
        ],
        "outputs": [{"name": "Result", "type": "double", "description": "A * B"}],
        "keywords": ["multiply", "times", "product", "*"]
    },
    {
        "name": "Division",
        "guid": "d3095627-d44b-755g-eee6-9d0448f08d58",
        "category": "Maths",
        "subcategory": "Operators",
        "description": "Mathematical division",
        "inputs": [
            {"name": "A", "type": "double", "description": "Dividend"},
            {"name": "B", "type": "double", "description": "Divisor"}
        ],
        "outputs": [{"name": "Result", "type": "double", "description": "A / B"}],
        "keywords": ["divide", "quotient", "/"]
    },

    # Maths - Domain
    {
        "name": "Construct Domain",
        "guid": "e4106738-e55c-866h-fff7-ae1559019e69",
        "category": "Maths",
        "subcategory": "Domain",
        "description": "Create a numeric domain from two numbers",
        "inputs": [
            {"name": "A", "type": "double", "description": "Domain start"},
            {"name": "B", "type": "double", "description": "Domain end"}
        ],
        "outputs": [{"name": "Domain", "type": "Domain", "description": "Numeric domain"}],
        "keywords": ["range", "interval", "bounds"]
    },
    {
        "name": "Remap Numbers",
        "guid": "f5217849-f66d-977i-000a-bf266a12af7a",
        "category": "Maths",
        "subcategory": "Domain",
        "description": "Remap numbers from one domain to another",
        "inputs": [
            {"name": "Value", "type": "double", "description": "Value to remap"},
            {"name": "Source", "type": "Domain", "description": "Source domain"},
            {"name": "Target", "type": "Domain", "description": "Target domain"}
        ],
        "outputs": [{"name": "Mapped", "type": "double", "description": "Remapped value"}],
        "keywords": ["map", "scale", "normalize", "lerp"]
    },

    # Vector - Point
    {
        "name": "Construct Point",
        "guid": "06328950-077e-088j-111b-c0377b23b08b",
        "category": "Vector",
        "subcategory": "Point",
        "description": "Create a point from X, Y, Z coordinates",
        "inputs": [
            {"name": "X", "type": "double", "description": "X coordinate"},
            {"name": "Y", "type": "double", "description": "Y coordinate"},
            {"name": "Z", "type": "double", "description": "Z coordinate"}
        ],
        "outputs": [{"name": "Point", "type": "Point3d", "description": "Resulting point"}],
        "keywords": ["pt", "xyz", "coordinate", "vertex"]
    },
    {
        "name": "Deconstruct Point",
        "guid": "17439061-188f-199k-222c-d1488c34c19c",
        "category": "Vector",
        "subcategory": "Point",
        "description": "Extract X, Y, Z coordinates from a point",
        "inputs": [{"name": "Point", "type": "Point3d", "description": "Point to deconstruct"}],
        "outputs": [
            {"name": "X", "type": "double", "description": "X coordinate"},
            {"name": "Y", "type": "double", "description": "Y coordinate"},
            {"name": "Z", "type": "double", "description": "Z coordinate"}
        ],
        "keywords": ["pt", "xyz", "extract", "components"]
    },
    {
        "name": "Distance",
        "guid": "2854a172-299g-2aal-333d-e2599d45d2ad",
        "category": "Vector",
        "subcategory": "Point",
        "description": "Calculate distance between two points",
        "inputs": [
            {"name": "A", "type": "Point3d", "description": "First point"},
            {"name": "B", "type": "Point3d", "description": "Second point"}
        ],
        "outputs": [{"name": "Distance", "type": "double", "description": "Distance between points"}],
        "keywords": ["length", "magnitude", "spacing"]
    },

    # Curve - Primitive
    {
        "name": "Line",
        "guid": "3965b283-3aah-3bbm-444e-f36aae56e3be",
        "category": "Curve",
        "subcategory": "Primitive",
        "description": "Create a line between two points",
        "inputs": [
            {"name": "A", "type": "Point3d", "description": "Start point"},
            {"name": "B", "type": "Point3d", "description": "End point"}
        ],
        "outputs": [{"name": "Line", "type": "Line", "description": "Resulting line"}],
        "keywords": ["segment", "straight", "edge"]
    },
    {
        "name": "Circle",
        "guid": "4a76c394-4bbi-4ccn-555f-047bbf67f4cf",
        "category": "Curve",
        "subcategory": "Primitive",
        "description": "Create a circle from plane and radius",
        "inputs": [
            {"name": "Plane", "type": "Plane", "description": "Circle plane"},
            {"name": "Radius", "type": "double", "description": "Circle radius"}
        ],
        "outputs": [{"name": "Circle", "type": "Circle", "description": "Resulting circle"}],
        "keywords": ["round", "arc", "ellipse"]
    },
    {
        "name": "Arc",
        "guid": "5b87d4a5-5ccj-5ddo-666g-158cc078g5dg",
        "category": "Curve",
        "subcategory": "Primitive",
        "description": "Create an arc from three points",
        "inputs": [
            {"name": "A", "type": "Point3d", "description": "Start point"},
            {"name": "B", "type": "Point3d", "description": "Interior point"},
            {"name": "C", "type": "Point3d", "description": "End point"}
        ],
        "outputs": [{"name": "Arc", "type": "Arc", "description": "Resulting arc"}],
        "keywords": ["curve", "segment", "circular"]
    },
    {
        "name": "Polyline",
        "guid": "6c98e5b6-6ddk-6eep-777h-269dd189h6eh",
        "category": "Curve",
        "subcategory": "Primitive",
        "description": "Create a polyline from points",
        "inputs": [
            {"name": "Vertices", "type": "Point3d[]", "description": "Polyline vertices"},
            {"name": "Closed", "type": "bool", "description": "Close polyline"}
        ],
        "outputs": [{"name": "Polyline", "type": "Polyline", "description": "Resulting polyline"}],
        "keywords": ["pline", "polygon", "segments"]
    },
    {
        "name": "Interpolate",
        "guid": "7da9f6c7-7eel-7ffq-888i-37aee29ai7fi",
        "category": "Curve",
        "subcategory": "Spline",
        "description": "Create an interpolated curve through points",
        "inputs": [
            {"name": "Vertices", "type": "Point3d[]", "description": "Interpolation points"},
            {"name": "Degree", "type": "int", "description": "Curve degree"},
            {"name": "Periodic", "type": "bool", "description": "Periodic curve"}
        ],
        "outputs": [{"name": "Curve", "type": "Curve", "description": "Interpolated curve"}],
        "keywords": ["spline", "nurbs", "smooth", "fit"]
    },

    # Curve - Analysis
    {
        "name": "Evaluate Curve",
        "guid": "8eba07d8-8ffm-800r-999j-48bff3abj8gj",
        "category": "Curve",
        "subcategory": "Analysis",
        "description": "Evaluate a curve at a parameter",
        "inputs": [
            {"name": "Curve", "type": "Curve", "description": "Curve to evaluate"},
            {"name": "Parameter", "type": "double", "description": "Parameter on curve"}
        ],
        "outputs": [
            {"name": "Point", "type": "Point3d", "description": "Point on curve"},
            {"name": "Tangent", "type": "Vector3d", "description": "Tangent at point"}
        ],
        "keywords": ["sample", "point on curve", "tangent"]
    },
    {
        "name": "Curve Length",
        "guid": "9fcb18e9-900n-911s-aaak-59c004bck9hk",
        "category": "Curve",
        "subcategory": "Analysis",
        "description": "Measure the length of a curve",
        "inputs": [{"name": "Curve", "type": "Curve", "description": "Curve to measure"}],
        "outputs": [{"name": "Length", "type": "double", "description": "Curve length"}],
        "keywords": ["measure", "distance", "arc length"]
    },
    {
        "name": "Divide Curve",
        "guid": "a0dc29fa-a11o-a22t-bbbl-6ad115cdlail",
        "category": "Curve",
        "subcategory": "Division",
        "description": "Divide a curve into segments",
        "inputs": [
            {"name": "Curve", "type": "Curve", "description": "Curve to divide"},
            {"name": "Count", "type": "int", "description": "Number of segments"}
        ],
        "outputs": [
            {"name": "Points", "type": "Point3d[]", "description": "Division points"},
            {"name": "Tangents", "type": "Vector3d[]", "description": "Tangents at points"},
            {"name": "Parameters", "type": "double[]", "description": "Parameters at points"}
        ],
        "keywords": ["split", "segment", "subdivide"]
    },

    # Surface - Primitive
    {
        "name": "Extrude",
        "guid": "b1ed3a0b-b22p-b33u-cccm-7be226dembjm",
        "category": "Surface",
        "subcategory": "Freeform",
        "description": "Extrude a curve along a vector",
        "inputs": [
            {"name": "Curve", "type": "Curve", "description": "Curve to extrude"},
            {"name": "Direction", "type": "Vector3d", "description": "Extrusion direction"}
        ],
        "outputs": [{"name": "Surface", "type": "Surface", "description": "Extruded surface"}],
        "keywords": ["sweep", "linear", "extend"]
    },
    {
        "name": "Loft",
        "guid": "c2fe4b1c-c33q-c44v-dddn-8cf337fencko",
        "category": "Surface",
        "subcategory": "Freeform",
        "description": "Create a lofted surface through curves",
        "inputs": [
            {"name": "Curves", "type": "Curve[]", "description": "Section curves"},
            {"name": "Options", "type": "int", "description": "Loft options"}
        ],
        "outputs": [{"name": "Surface", "type": "Brep", "description": "Lofted surface"}],
        "keywords": ["skin", "blend", "ruled"]
    },
    {
        "name": "Sweep1",
        "guid": "d30f5c2d-d44r-d55w-eeeo-9d0448gfodlp",
        "category": "Surface",
        "subcategory": "Freeform",
        "description": "Sweep a section curve along a rail",
        "inputs": [
            {"name": "Rail", "type": "Curve", "description": "Rail curve"},
            {"name": "Section", "type": "Curve", "description": "Section curve"}
        ],
        "outputs": [{"name": "Surface", "type": "Brep", "description": "Swept surface"}],
        "keywords": ["extrude along", "pipe", "rail"]
    },

    # Transform
    {
        "name": "Move",
        "guid": "e4106d3e-e55s-e66x-fffp-ae1559hgpemq",
        "category": "Transform",
        "subcategory": "Euclidean",
        "description": "Move geometry along a vector",
        "inputs": [
            {"name": "Geometry", "type": "Geometry", "description": "Geometry to move"},
            {"name": "Motion", "type": "Vector3d", "description": "Translation vector"}
        ],
        "outputs": [{"name": "Geometry", "type": "Geometry", "description": "Moved geometry"}],
        "keywords": ["translate", "shift", "offset"]
    },
    {
        "name": "Rotate",
        "guid": "f5217e4f-f66t-f77y-000q-bf266aihqfnr",
        "category": "Transform",
        "subcategory": "Euclidean",
        "description": "Rotate geometry around an axis",
        "inputs": [
            {"name": "Geometry", "type": "Geometry", "description": "Geometry to rotate"},
            {"name": "Angle", "type": "double", "description": "Rotation angle (radians)"},
            {"name": "Plane", "type": "Plane", "description": "Rotation plane"}
        ],
        "outputs": [{"name": "Geometry", "type": "Geometry", "description": "Rotated geometry"}],
        "keywords": ["spin", "turn", "revolve"]
    },
    {
        "name": "Scale",
        "guid": "06328f50-077u-088z-111r-c0377bjirhos",
        "category": "Transform",
        "subcategory": "Euclidean",
        "description": "Scale geometry uniformly",
        "inputs": [
            {"name": "Geometry", "type": "Geometry", "description": "Geometry to scale"},
            {"name": "Center", "type": "Point3d", "description": "Scale center"},
            {"name": "Factor", "type": "double", "description": "Scale factor"}
        ],
        "outputs": [{"name": "Geometry", "type": "Geometry", "description": "Scaled geometry"}],
        "keywords": ["resize", "enlarge", "shrink"]
    },
    {
        "name": "Mirror",
        "guid": "17439061-188v-199a1-222s-d1488ckjsipt",
        "category": "Transform",
        "subcategory": "Euclidean",
        "description": "Mirror geometry across a plane",
        "inputs": [
            {"name": "Geometry", "type": "Geometry", "description": "Geometry to mirror"},
            {"name": "Plane", "type": "Plane", "description": "Mirror plane"}
        ],
        "outputs": [{"name": "Geometry", "type": "Geometry", "description": "Mirrored geometry"}],
        "keywords": ["reflect", "flip", "symmetry"]
    },

    # Sets - List
    {
        "name": "List Item",
        "guid": "28540172-299w-2ab1-333t-e2599dlktjqu",
        "category": "Sets",
        "subcategory": "List",
        "description": "Get item at index from a list",
        "inputs": [
            {"name": "List", "type": "any[]", "description": "List to index"},
            {"name": "Index", "type": "int", "description": "Item index"},
            {"name": "Wrap", "type": "bool", "description": "Wrap index"}
        ],
        "outputs": [{"name": "Item", "type": "any", "description": "Item at index"}],
        "keywords": ["index", "get", "element", "access"]
    },
    {
        "name": "List Length",
        "guid": "3965b283-3aax-3bc1-444u-f36aaemlukrv",
        "category": "Sets",
        "subcategory": "List",
        "description": "Get the number of items in a list",
        "inputs": [{"name": "List", "type": "any[]", "description": "List to measure"}],
        "outputs": [{"name": "Length", "type": "int", "description": "Number of items"}],
        "keywords": ["count", "size", "number"]
    },
    {
        "name": "Reverse List",
        "guid": "4a76c394-4bby-4cd1-555v-047bbfnmvlsw",
        "category": "Sets",
        "subcategory": "List",
        "description": "Reverse the order of a list",
        "inputs": [{"name": "List", "type": "any[]", "description": "List to reverse"}],
        "outputs": [{"name": "List", "type": "any[]", "description": "Reversed list"}],
        "keywords": ["flip", "invert", "backwards"]
    },

    # Sets - Tree
    {
        "name": "Flatten",
        "guid": "5b87d4a5-5ccz-5de1-666w-158cconwmtx",
        "category": "Sets",
        "subcategory": "Tree",
        "description": "Flatten a data tree to a single list",
        "inputs": [{"name": "Tree", "type": "DataTree", "description": "Tree to flatten"}],
        "outputs": [{"name": "List", "type": "any[]", "description": "Flattened list"}],
        "keywords": ["collapse", "merge", "simplify"]
    },
    {
        "name": "Graft",
        "guid": "6c98e5b6-6dda1-6ef1-777x-269ddpoxnuy",
        "category": "Sets",
        "subcategory": "Tree",
        "description": "Graft each item into its own branch",
        "inputs": [{"name": "Tree", "type": "DataTree", "description": "Tree to graft"}],
        "outputs": [{"name": "Tree", "type": "DataTree", "description": "Grafted tree"}],
        "keywords": ["branch", "separate", "individual"]
    },

    # Script components
    {
        "name": "GhPython Script",
        "guid": "410755b1-224a-4c1e-a407-bf32fb45ea7e",
        "category": "Maths",
        "subcategory": "Script",
        "description": "Python scripting component for custom logic",
        "inputs": [{"name": "x", "type": "any", "description": "Script input"}],
        "outputs": [{"name": "a", "type": "any", "description": "Script output"}],
        "keywords": ["python", "code", "script", "custom", "ghpython"]
    },
    {
        "name": "C# Script",
        "guid": "a9d51e9f-60c1-4c9f-8e34-c5f6a5f5e5e1",
        "category": "Maths",
        "subcategory": "Script",
        "description": "C# scripting component for custom logic",
        "inputs": [{"name": "x", "type": "any", "description": "Script input"}],
        "outputs": [{"name": "A", "type": "any", "description": "Script output"}],
        "keywords": ["csharp", "code", "script", "custom", "dotnet"]
    },

    # Display
    {
        "name": "Custom Preview",
        "guid": "7da9f6c7-7eeb1-7fg1-888y-37aeeqpyovz",
        "category": "Display",
        "subcategory": "Preview",
        "description": "Preview geometry with custom color",
        "inputs": [
            {"name": "Geometry", "type": "Geometry", "description": "Geometry to preview"},
            {"name": "Material", "type": "Material", "description": "Display material"}
        ],
        "outputs": [],
        "keywords": ["color", "render", "visualize"]
    },
    {
        "name": "Colour Swatch",
        "guid": "8eba07d8-8ffc1-8gh1-999z-48bffrqzpwa",
        "category": "Display",
        "subcategory": "Colour",
        "description": "Color picker/swatch",
        "inputs": [],
        "outputs": [{"name": "Colour", "type": "Color", "description": "Selected color"}],
        "keywords": ["color", "rgb", "picker"]
    },
]


class ComponentLibrary:
    """Searchable component library"""

    def __init__(self):
        self.components = [ComponentInfo(**c) for c in COMPONENT_DATABASE]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search components by name, description, or keywords"""
        query_lower = query.lower()
        results = []

        for comp in self.components:
            score = 0

            # Exact name match
            if query_lower == comp.name.lower():
                score = 100
            # Name contains query
            elif query_lower in comp.name.lower():
                score = 50
            # Description contains query
            elif query_lower in comp.description.lower():
                score = 30
            # Keyword match
            elif any(query_lower in kw.lower() for kw in comp.keywords):
                score = 40
            # Category/subcategory match
            elif query_lower in comp.category.lower() or query_lower in comp.subcategory.lower():
                score = 20

            if score > 0:
                results.append((score, asdict(comp)))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def get_by_category(self, category: str) -> list[dict]:
        """Get all components in a category"""
        return [
            asdict(c) for c in self.components
            if c.category.lower() == category.lower()
        ]

    def get_by_subcategory(self, category: str, subcategory: str) -> list[dict]:
        """Get components in a specific subcategory"""
        return [
            asdict(c) for c in self.components
            if c.category.lower() == category.lower()
            and c.subcategory.lower() == subcategory.lower()
        ]

    def get_categories(self) -> dict:
        """Get all categories and their subcategories"""
        categories = {}
        for comp in self.components:
            if comp.category not in categories:
                categories[comp.category] = set()
            categories[comp.category].add(comp.subcategory)

        return {k: sorted(list(v)) for k, v in sorted(categories.items())}

    def get_by_guid(self, guid: str) -> Optional[dict]:
        """Get component by GUID"""
        for comp in self.components:
            if comp.guid == guid:
                return asdict(comp)
        return None

    def list_all(self) -> list[dict]:
        """List all components"""
        return [asdict(c) for c in self.components]


# Singleton instance
_library: Optional[ComponentLibrary] = None


def get_library() -> ComponentLibrary:
    """Get or create the component library"""
    global _library
    if _library is None:
        _library = ComponentLibrary()
    return _library
