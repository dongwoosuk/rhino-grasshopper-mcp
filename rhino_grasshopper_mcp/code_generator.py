"""
Code Generation Module
Generate GHPython and C# script component code
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class ScriptTemplate:
    """Template for generated scripts"""
    language: str
    code: str
    inputs: list[dict]
    outputs: list[dict]
    description: str


# Common GHPython templates
GHPYTHON_TEMPLATES = {
    "basic": '''"""
{description}
"""
import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import ghpythonlib.components as ghcomp

# Inputs: {input_names}
# Outputs: {output_names}

{code}
''',

    "geometry_processing": '''"""
{description}
Process geometry with Rhino.Geometry
"""
import Rhino.Geometry as rg
from Rhino.Geometry import Point3d, Vector3d, Curve, Surface, Brep

# Input: geometry (Geometry)
# Output: result (Geometry)

def process_geometry(geo):
    """Process a single geometry object"""
    # TODO: Add processing logic
    return geo

if isinstance(geometry, list):
    result = [process_geometry(g) for g in geometry]
else:
    result = process_geometry(geometry)
''',

    "data_tree": '''"""
{description}
Work with data trees
"""
import ghpythonlib.treehelpers as th
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# Convert tree to nested lists
nested_list = th.tree_to_list(x)

# Process data
processed = []
for branch in nested_list:
    processed.append([item * 2 for item in branch])  # Example operation

# Convert back to tree
result = th.list_to_tree(processed)
''',

    "point_grid": '''"""
{description}
Generate a grid of points
"""
import Rhino.Geometry as rg

# Inputs:
#   x_count (int) - Number of points in X
#   y_count (int) - Number of points in Y
#   spacing (float) - Distance between points

points = []
for i in range(x_count):
    for j in range(y_count):
        pt = rg.Point3d(i * spacing, j * spacing, 0)
        points.append(pt)

a = points
''',

    "attractor": '''"""
{description}
Attractor point influence on geometry
"""
import Rhino.Geometry as rg
import math

# Inputs:
#   points (Point3d[]) - Points to affect
#   attractor (Point3d) - Attractor point
#   max_distance (float) - Maximum influence distance
#   strength (float) - Effect strength (0-1)

result = []
for pt in points:
    dist = pt.DistanceTo(attractor)
    if dist < max_distance:
        # Calculate influence (inverse distance)
        influence = 1.0 - (dist / max_distance)
        influence = influence ** 2  # Quadratic falloff

        # Apply transformation based on influence
        direction = rg.Vector3d(pt - attractor)
        direction.Unitize()

        # Move point away from attractor based on influence
        new_pt = pt + direction * influence * strength
        result.append(new_pt)
    else:
        result.append(pt)

a = result
''',

    "mesh_analysis": '''"""
{description}
Analyze mesh properties
"""
import Rhino.Geometry as rg

# Input: mesh (Mesh)
# Outputs: vertices, faces, normals, area

vertices = [mesh.Vertices[i] for i in range(mesh.Vertices.Count)]
faces = mesh.Faces
normals = [mesh.Normals[i] for i in range(mesh.Normals.Count)]

# Calculate total area
area = 0
for i in range(mesh.Faces.Count):
    face = mesh.Faces[i]
    if face.IsQuad:
        # Quad face - split into two triangles
        tri1 = rg.Mesh()
        tri1.Vertices.Add(mesh.Vertices[face.A])
        tri1.Vertices.Add(mesh.Vertices[face.B])
        tri1.Vertices.Add(mesh.Vertices[face.C])
        tri1.Faces.AddFace(0, 1, 2)

        tri2 = rg.Mesh()
        tri2.Vertices.Add(mesh.Vertices[face.A])
        tri2.Vertices.Add(mesh.Vertices[face.C])
        tri2.Vertices.Add(mesh.Vertices[face.D])
        tri2.Faces.AddFace(0, 1, 2)

        area += rg.AreaMassProperties.Compute(tri1).Area
        area += rg.AreaMassProperties.Compute(tri2).Area
    else:
        # Triangle face
        tri = rg.Mesh()
        tri.Vertices.Add(mesh.Vertices[face.A])
        tri.Vertices.Add(mesh.Vertices[face.B])
        tri.Vertices.Add(mesh.Vertices[face.C])
        tri.Faces.AddFace(0, 1, 2)
        area += rg.AreaMassProperties.Compute(tri).Area

a = vertices
b = faces
c = normals
d = area
''',
}

# Common C# templates
CSHARP_TEMPLATES = {
    "basic": '''/*
{description}
*/
using System;
using System.Collections.Generic;
using Rhino;
using Rhino.Geometry;
using Grasshopper;
using Grasshopper.Kernel;

// Inputs: {input_names}
// Outputs: {output_names}

{code}
''',

    "geometry_processing": '''/*
{description}
Process geometry with RhinoCommon
*/
using System;
using System.Collections.Generic;
using Rhino.Geometry;

// Input: x (Geometry)
// Output: A (Geometry)

private void RunScript(object x, ref object A)
{{
    if (x is Point3d pt)
    {{
        A = pt;
    }}
    else if (x is Curve crv)
    {{
        A = crv;
    }}
    else if (x is Brep brep)
    {{
        A = brep;
    }}
}}
''',

    "point_grid": '''/*
{description}
Generate a grid of points
*/
using System;
using System.Collections.Generic;
using Rhino.Geometry;

// Inputs: xCount, yCount, spacing
// Output: A (List<Point3d>)

private void RunScript(int xCount, int yCount, double spacing, ref object A)
{{
    var points = new List<Point3d>();

    for (int i = 0; i < xCount; i++)
    {{
        for (int j = 0; j < yCount; j++)
        {{
            points.Add(new Point3d(i * spacing, j * spacing, 0));
        }}
    }}

    A = points;
}}
''',
}


class CodeGenerator:
    """Generate GHPython and C# code for Grasshopper"""

    def __init__(self):
        self.ghpython_templates = GHPYTHON_TEMPLATES
        self.csharp_templates = CSHARP_TEMPLATES

    def list_templates(self, language: str = "python") -> list[str]:
        """List available templates"""
        if language.lower() in ["python", "ghpython"]:
            return list(self.ghpython_templates.keys())
        elif language.lower() in ["csharp", "c#"]:
            return list(self.csharp_templates.keys())
        return []

    def get_template(self, template_name: str, language: str = "python") -> Optional[str]:
        """Get a specific template"""
        if language.lower() in ["python", "ghpython"]:
            return self.ghpython_templates.get(template_name)
        elif language.lower() in ["csharp", "c#"]:
            return self.csharp_templates.get(template_name)
        return None

    def generate_ghpython(
        self,
        description: str,
        inputs: list[dict],
        outputs: list[dict],
        code_body: str
    ) -> str:
        """Generate a GHPython script"""
        input_names = ", ".join(i.get("name", "x") for i in inputs) if inputs else "None"
        output_names = ", ".join(o.get("name", "a") for o in outputs) if outputs else "None"

        # Build input comments
        input_comments = ""
        for inp in inputs:
            name = inp.get("name", "x")
            typ = inp.get("type", "any")
            desc = inp.get("description", "")
            input_comments += f"# Input: {name} ({typ}) - {desc}\n"

        # Build output comments
        output_comments = ""
        for out in outputs:
            name = out.get("name", "a")
            typ = out.get("type", "any")
            desc = out.get("description", "")
            output_comments += f"# Output: {name} ({typ}) - {desc}\n"

        return f'''"""
{description}
"""
import rhinoscriptsyntax as rs
import Rhino.Geometry as rg

{input_comments}{output_comments}
{code_body}
'''

    def generate_csharp(
        self,
        description: str,
        inputs: list[dict],
        outputs: list[dict],
        code_body: str
    ) -> str:
        """Generate a C# script"""
        # Build method signature
        params = []
        for inp in inputs:
            name = inp.get("name", "x")
            typ = self._python_to_csharp_type(inp.get("type", "object"))
            params.append(f"{typ} {name}")

        for out in outputs:
            name = out.get("name", "A")
            params.append(f"ref object {name}")

        param_str = ", ".join(params)

        return f'''/*
{description}
*/
using System;
using System.Collections.Generic;
using Rhino.Geometry;

private void RunScript({param_str})
{{
{self._indent_code(code_body, 4)}
}}
'''

    def _python_to_csharp_type(self, python_type: str) -> str:
        """Convert Python type hint to C# type"""
        type_map = {
            "int": "int",
            "float": "double",
            "double": "double",
            "str": "string",
            "string": "string",
            "bool": "bool",
            "Point3d": "Point3d",
            "Vector3d": "Vector3d",
            "Curve": "Curve",
            "Surface": "Surface",
            "Brep": "Brep",
            "Mesh": "Mesh",
            "Plane": "Plane",
            "Line": "Line",
            "any": "object",
        }
        return type_map.get(python_type, "object")

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by given spaces"""
        indent = " " * spaces
        lines = code.split("\n")
        return "\n".join(indent + line if line.strip() else line for line in lines)

    def generate_from_description(self, description: str, language: str = "python") -> dict:
        """
        Generate code from a natural language description.
        Returns a dict with generated code and suggestions.
        """
        description_lower = description.lower()

        # Match description to templates
        suggestions = []

        if "grid" in description_lower or "point" in description_lower:
            suggestions.append({
                "template": "point_grid",
                "reason": "Description mentions grid or points"
            })

        if "attractor" in description_lower or "influence" in description_lower:
            suggestions.append({
                "template": "attractor",
                "reason": "Description mentions attractor or influence"
            })

        if "mesh" in description_lower:
            suggestions.append({
                "template": "mesh_analysis",
                "reason": "Description mentions mesh"
            })

        if "tree" in description_lower or "branch" in description_lower:
            suggestions.append({
                "template": "data_tree",
                "reason": "Description mentions data tree or branches"
            })

        # Default to basic if no matches
        if not suggestions:
            suggestions.append({
                "template": "basic",
                "reason": "Default template"
            })

        # Get the first suggested template
        template_name = suggestions[0]["template"]
        template = self.get_template(template_name, language)

        return {
            "description": description,
            "language": language,
            "suggested_template": template_name,
            "suggestions": suggestions,
            "code": template.format(description=description) if template else None
        }


# Singleton instance
_generator: Optional[CodeGenerator] = None


def get_generator() -> CodeGenerator:
    """Get or create the code generator"""
    global _generator
    if _generator is None:
        _generator = CodeGenerator()
    return _generator
