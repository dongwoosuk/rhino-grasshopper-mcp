"""
Grasshopper MCP Server - Main Entry Point
Run with: python -m grasshopper_mcp.bridge

Includes AI Mentoring features:
- Performance Prediction
- Alternative Logic Suggestion
- Auto Grouping
- Component Highlighting
"""

import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .rhino_bridge import get_bridge
from .gh_file_ops import (
    get_definition_summary,
    list_components,
    get_xml_content,
    find_components_by_name,
)
from .component_library import get_library
from .code_generator import get_generator

# Mentoring module imports
_mentoring_available = False
_ml_layout_available = False
_persistent_learner_available = False
_advanced_learner_available = False
try:
    from .mentoring.performance_predictor import PerformancePredictor, create_predictor_from_canvas_data
    from .mentoring.alternative_suggester import AlternativeSuggester, create_suggester_from_canvas_data
    from .mentoring.auto_grouper import AutoGrouper, create_grouper_from_canvas_data
    _mentoring_available = True

    # ML Layout Learner (optional sklearn dependency)
    from .mentoring.ml_layout_learner import MLLayoutLearner, create_ml_learner_from_canvas_data
    _ml_layout_available = True

    # Persistent Layout Learner (누적 학습 시스템)
    from .mentoring.persistent_layout_learner import get_persistent_learner, PersistentLayoutLearner
    _persistent_learner_available = True

    # Advanced Layout Learner (KNN 기반 진정한 ML 학습)
    from .mentoring.advanced_layout_learner import get_advanced_learner
    _advanced_learner_available = True
except ImportError:
    pass

# Create MCP server
app = Server("grasshopper-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        # Rhino Bridge Tools
        Tool(
            name="rhino_status",
            description="Check if Rhino/Grasshopper is running and connection status",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="rhino_execute_python",
            description="Execute Python code in Rhino's environment (requires bridge listener)",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute"
                    }
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="gh_canvas_state",
            description="Get current state of the Grasshopper canvas (components, connections)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="gh_load_definition",
            description="Load a .gh/.ghx file into Grasshopper",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .gh or .ghx file"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="gh_solve",
            description="Trigger a solve/recompute of the current Grasshopper definition",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        # GH File Operations
        Tool(
            name="gh_file_summary",
            description="Get summary of a .gh or .ghx Grasshopper definition file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .gh or .ghx file"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="gh_list_components",
            description="List all components in a Grasshopper definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .gh or .ghx file"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="gh_find_components",
            description="Find components by name in a Grasshopper definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .gh or .ghx file"
                    },
                    "name_pattern": {
                        "type": "string",
                        "description": "Name pattern to search for"
                    }
                },
                "required": ["file_path", "name_pattern"]
            }
        ),
        Tool(
            name="gh_get_xml",
            description="Get raw XML content of a .gh or .ghx file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to .gh or .ghx file"
                    }
                },
                "required": ["file_path"]
            }
        ),

        # Component Library
        Tool(
            name="component_search",
            description="Search for Grasshopper components by name, description, or keywords",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 20)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="component_categories",
            description="List all component categories and subcategories",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="component_by_category",
            description="Get all components in a category",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name (e.g., 'Curve', 'Surface', 'Transform')"
                    },
                    "subcategory": {
                        "type": "string",
                        "description": "Optional subcategory name"
                    }
                },
                "required": ["category"]
            }
        ),

        # Code Generation
        Tool(
            name="code_templates",
            description="List available code templates for GHPython or C#",
            inputSchema={
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Language: 'python' or 'csharp'"
                    }
                }
            }
        ),
        Tool(
            name="code_get_template",
            description="Get a specific code template",
            inputSchema={
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "Template name (e.g., 'point_grid', 'attractor')"
                    },
                    "language": {
                        "type": "string",
                        "description": "Language: 'python' or 'csharp'"
                    }
                },
                "required": ["template_name"]
            }
        ),
        Tool(
            name="code_generate",
            description="Generate GHPython or C# code from description",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of what the code should do"
                    },
                    "language": {
                        "type": "string",
                        "description": "Language: 'python' or 'csharp'"
                    },
                    "inputs": {
                        "type": "array",
                        "description": "Input parameters [{name, type, description}]",
                        "items": {"type": "object"}
                    },
                    "outputs": {
                        "type": "array",
                        "description": "Output parameters [{name, type, description}]",
                        "items": {"type": "object"}
                    }
                },
                "required": ["description"]
            }
        ),

        # ============================================================
        # AI Mentoring Tools
        # ============================================================
        Tool(
            name="predict_performance",
            description="Predict performance improvement before applying optimizations. Shows expected improvement percentage, confidence level, and effort required. Use this to guide users on which optimizations are most effective.",
            inputSchema={
                "type": "object",
                "properties": {
                    "optimization_type": {
                        "type": "string",
                        "description": "Type of optimization to predict. Options: 'disable_heavy_preview', 'add_data_dam', 'simplify_tree_operations', 'cache_expensive_geometry', 'use_native_components', 'reduce_list_operations', 'batch_boolean_operations', 'reduce_mesh_resolution', or 'all' for all optimizations",
                        "enum": ["disable_heavy_preview", "add_data_dam", "simplify_tree_operations", "cache_expensive_geometry", "use_native_components", "reduce_list_operations", "batch_boolean_operations", "reduce_mesh_resolution", "all"]
                    },
                    "target_guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: specific component GUIDs to analyze. If not provided, auto-detects applicable components."
                    }
                }
            }
        ),
        Tool(
            name="suggest_alternatives",
            description="Suggest better alternative approaches for current Grasshopper logic. Detects inefficient patterns and recommends optimized solutions with implementation steps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern_type": {
                        "type": "string",
                        "description": "Optional: specific pattern to check. Options: 'multiple_move', 'flatten_then_graft', 'python_loop_geometry', 'serial_boolean', 'expression_math', 'excessive_list_item'. If not provided, checks all patterns.",
                        "enum": ["multiple_move", "flatten_then_graft", "python_loop_geometry", "serial_boolean", "expression_math", "excessive_list_item", "all"]
                    }
                }
            }
        ),
        Tool(
            name="auto_group",
            description="Automatically detect logical groups in a Grasshopper definition based on wire connectivity. Returns suggested group names, colors, and layout recommendations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_cluster_size": {
                        "type": "integer",
                        "description": "Minimum number of components per group (default: 2)",
                        "default": 2
                    },
                    "max_clusters": {
                        "type": "integer",
                        "description": "Maximum number of groups to detect (default: 10)",
                        "default": 10
                    },
                    "color_scheme": {
                        "type": "string",
                        "description": "Color scheme for groups: 'default', 'vibrant', 'monochrome'",
                        "enum": ["default", "vibrant", "monochrome"],
                        "default": "default"
                    }
                }
            }
        ),
        Tool(
            name="highlight_components",
            description="Highlight specific components on the Grasshopper canvas with colors. Use this when explaining or referencing components to help users visually identify them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Component GUIDs to highlight"
                    },
                    "context": {
                        "type": "string",
                        "description": "Context for coloring: 'problem' (red), 'suggestion' (blue), 'optimized' (green), 'reference' (orange)",
                        "enum": ["problem", "suggestion", "optimized", "reference"]
                    }
                },
                "required": ["guids"]
            }
        ),
        Tool(
            name="clear_highlights",
            description="Clear component highlights from the canvas",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: specific GUIDs to clear. If not provided, clears all highlights."
                    }
                }
            }
        ),
        Tool(
            name="ml_layout_analysis",
            description="ML-based layout analysis using DBSCAN/K-means clustering. Detects component clusters, classifies data flow patterns, and identifies layout anomalies. Requires scikit-learn for full functionality.",
            inputSchema={
                "type": "object",
                "properties": {
                    "clustering_method": {
                        "type": "string",
                        "description": "Clustering algorithm: 'dbscan' (density-based) or 'kmeans' (fixed clusters)",
                        "enum": ["dbscan", "kmeans"],
                        "default": "dbscan"
                    },
                    "eps": {
                        "type": "number",
                        "description": "DBSCAN: neighborhood distance threshold in pixels (default: 150)",
                        "default": 150
                    },
                    "n_clusters": {
                        "type": "integer",
                        "description": "K-means: number of clusters (default: auto)",
                    },
                    "include_anomalies": {
                        "type": "boolean",
                        "description": "Include layout anomaly detection (default: true)",
                        "default": True
                    }
                }
            }
        ),
        Tool(
            name="predict_component_position",
            description="Predict optimal position for a new component based on learned layout patterns and context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_name": {
                        "type": "string",
                        "description": "Name of the component to add"
                    },
                    "connected_to": {
                        "type": "string",
                        "description": "GUID of the component it will connect to"
                    },
                    "direction": {
                        "type": "string",
                        "description": "Placement direction: 'right', 'down', 'left', 'up'",
                        "enum": ["right", "down", "left", "up"],
                        "default": "right"
                    }
                },
                "required": ["component_name"]
            }
        ),

        # ============================================================
        # Component Creation & Manipulation Tools
        # ============================================================
        Tool(
            name="gh_add_component",
            description="Add a component to the Grasshopper canvas. Returns the GUID of the created component.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Component name (e.g., 'Number Slider', 'Addition', 'Point', 'Circle')"
                    },
                    "x": {
                        "type": "number",
                        "description": "X position on canvas"
                    },
                    "y": {
                        "type": "number",
                        "description": "Y position on canvas"
                    },
                    "nickname": {
                        "type": "string",
                        "description": "Optional nickname for the component"
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category hint (e.g., 'Params', 'Maths', 'Curve')"
                    },
                    "subcategory": {
                        "type": "string",
                        "description": "Optional subcategory hint (e.g., 'Primitive', 'Operators')"
                    },
                    "delay": {
                        "type": "number",
                        "description": "Delay in seconds after creation for visual feedback (default: 0.3)",
                        "default": 0.3
                    }
                },
                "required": ["name", "x", "y"]
            }
        ),
        Tool(
            name="gh_connect",
            description="Connect two components with a wire. Use output/input indices (0-based).",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_guid": {
                        "type": "string",
                        "description": "GUID of the source component"
                    },
                    "source_output": {
                        "type": "integer",
                        "description": "Output parameter index (0-based)",
                        "default": 0
                    },
                    "target_guid": {
                        "type": "string",
                        "description": "GUID of the target component"
                    },
                    "target_input": {
                        "type": "integer",
                        "description": "Input parameter index (0-based)",
                        "default": 0
                    }
                },
                "required": ["source_guid", "target_guid"]
            }
        ),
        Tool(
            name="gh_disconnect",
            description="Disconnect a wire between two components.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_guid": {
                        "type": "string",
                        "description": "GUID of the source component"
                    },
                    "source_output": {
                        "type": "integer",
                        "description": "Output parameter index",
                        "default": 0
                    },
                    "target_guid": {
                        "type": "string",
                        "description": "GUID of the target component"
                    },
                    "target_input": {
                        "type": "integer",
                        "description": "Input parameter index",
                        "default": 0
                    }
                },
                "required": ["source_guid", "target_guid"]
            }
        ),
        Tool(
            name="gh_set_value",
            description="Set the value of a component (Number Slider, Panel, Boolean Toggle, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "GUID of the component"
                    },
                    "value": {
                        "description": "Value to set (number, string, boolean, or list)"
                    },
                    "param_index": {
                        "type": "integer",
                        "description": "Parameter index for multi-param components",
                        "default": 0
                    }
                },
                "required": ["guid", "value"]
            }
        ),
        Tool(
            name="gh_delete_component",
            description="Delete a component from the canvas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "GUID of the component to delete"
                    }
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_move_component",
            description="Move a component to a new position on the canvas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "GUID of the component"
                    },
                    "x": {
                        "type": "number",
                        "description": "New X position"
                    },
                    "y": {
                        "type": "number",
                        "description": "New Y position"
                    }
                },
                "required": ["guid", "x", "y"]
            }
        ),
        Tool(
            name="gh_create_group",
            description="Create a group containing specified components.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of component GUIDs to group"
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional group name"
                    },
                    "color": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional RGB color [r, g, b]"
                    }
                },
                "required": ["guids"]
            }
        ),
        Tool(
            name="gh_get_component_info",
            description="Get detailed information about a component including inputs, outputs, and current values.",
            inputSchema={
                "type": "object",
                "properties": {
                    "guid": {
                        "type": "string",
                        "description": "GUID of the component"
                    }
                },
                "required": ["guid"]
            }
        ),
        Tool(
            name="gh_new_definition",
            description="Create a new empty Grasshopper definition (clears the canvas).",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="gh_save_definition",
            description="Save the current Grasshopper definition to a file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to save the .gh or .ghx file"
                    }
                },
                "required": ["file_path"]
            }
        ),

        # ============================================================
        # Persistent Layout Learning Tools (영속 학습 시스템)
        # ============================================================
        Tool(
            name="ml_learn_layout",
            description="Learn layout patterns from the current canvas. Patterns are accumulated across sessions and saved to disk. Use this after manually adjusting layouts to teach the system your preferences.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_name": {
                        "type": "string",
                        "description": "Optional name to identify this learning session (e.g., file name)"
                    }
                }
            }
        ),
        Tool(
            name="ml_get_position",
            description="Get optimal position for a new component based on accumulated learning. Uses patterns learned from previous sessions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_name": {
                        "type": "string",
                        "description": "Name of the component to position"
                    },
                    "connected_to_guid": {
                        "type": "string",
                        "description": "GUID of the component it will connect to"
                    },
                    "direction": {
                        "type": "string",
                        "description": "Placement direction: 'right', 'down', 'left', 'up'",
                        "enum": ["right", "down", "left", "up"],
                        "default": "right"
                    }
                },
                "required": ["component_name"]
            }
        ),
        Tool(
            name="ml_learning_summary",
            description="Get summary of accumulated learning data including total sessions, component patterns, and spacing statistics.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="ml_clear_learning",
            description="Clear all accumulated learning data and start fresh. Use with caution - this deletes all learned patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to confirm deletion"
                    }
                },
                "required": ["confirm"]
            }
        ),
        Tool(
            name="ml_auto_layout",
            description="Automatically arrange all components on the canvas using learned layout patterns. Uses topological sorting and connection-type-specific spacing to create clean, organized layouts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_x": {
                        "type": "number",
                        "description": "Starting X position for layout (default: 100)",
                        "default": 100
                    },
                    "start_y": {
                        "type": "number",
                        "description": "Starting Y position for layout (default: 100)",
                        "default": 100
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, only calculate positions without moving components (default: false)",
                        "default": False
                    },
                    "use_v9": {
                        "type": "boolean",
                        "description": "If true, use v9 algorithm with pattern-based layout (Sequence, Branching, Merging patterns). Default: true",
                        "default": True
                    }
                }
            }
        ),
        Tool(
            name="ml_learn_from_files",
            description="Learn layout patterns from GH/GHX files. Use this to build initial pattern database from your existing well-organized Grasshopper definitions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of .gh or .ghx file paths to learn from"
                    }
                },
                "required": ["file_paths"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    try:
        # Rhino Bridge Tools
        if name == "rhino_status":
            bridge = get_bridge()
            status = bridge.get_connection_status()
            return [TextContent(type="text", text=json.dumps(status, indent=2))]

        elif name == "rhino_execute_python":
            code = arguments.get("code", "")
            bridge = get_bridge()
            result = await bridge.execute_python(code)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_canvas_state":
            bridge = get_bridge()
            result = await bridge.get_grasshopper_state()
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_load_definition":
            file_path = arguments.get("file_path")
            if not file_path:
                raise ValueError("Missing 'file_path' parameter")
            bridge = get_bridge()
            result = await bridge.load_gh_definition(file_path)

            # Auto-learn from loaded definition (after short delay for canvas to update)
            if result.get("success") and _advanced_learner_available:
                try:
                    import asyncio
                    await asyncio.sleep(0.5)  # Wait for canvas to fully load

                    canvas_state = await bridge.get_grasshopper_state()
                    if canvas_state.get("success"):
                        components = canvas_state.get("components", [])
                        wires = canvas_state.get("wires", [])

                        if components and wires:
                            # Extract filename for source tracking
                            import os
                            source_name = os.path.basename(file_path)

                            # Learn with advanced learner
                            advanced_learner = get_advanced_learner()
                            learn_result = advanced_learner.learn_from_canvas(
                                components=components,
                                wires=wires,
                                source_name=source_name
                            )
                            result["auto_learning"] = {
                                "success": True,
                                "source": source_name,
                                "pair_patterns": learn_result.get("pair_patterns_learned", 0),
                                "branching_patterns": learn_result.get("branching_patterns_learned", 0),
                                "knn_samples": learn_result.get("knn_samples", 0)
                            }
                except Exception as e:
                    result["auto_learning"] = {
                        "success": False,
                        "error": str(e)
                    }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_solve":
            bridge = get_bridge()
            result = await bridge.solve_definition()
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # GH File Operations
        elif name == "gh_file_summary":
            file_path = arguments.get("file_path")
            if not file_path:
                raise ValueError("Missing 'file_path' parameter")
            result = get_definition_summary(file_path)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_list_components":
            file_path = arguments.get("file_path")
            if not file_path:
                raise ValueError("Missing 'file_path' parameter")
            result = list_components(file_path)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_find_components":
            file_path = arguments.get("file_path")
            name_pattern = arguments.get("name_pattern", "")
            if not file_path:
                raise ValueError("Missing 'file_path' parameter")
            result = find_components_by_name(file_path, name_pattern)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_get_xml":
            file_path = arguments.get("file_path")
            if not file_path:
                raise ValueError("Missing 'file_path' parameter")
            xml_content = get_xml_content(file_path)
            # Truncate if too long
            if len(xml_content) > 50000:
                xml_content = xml_content[:50000] + "\n... [truncated]"
            return [TextContent(type="text", text=xml_content)]

        # Component Library
        elif name == "component_search":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 20)
            library = get_library()
            results = library.search(query, limit)
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "component_categories":
            library = get_library()
            categories = library.get_categories()
            return [TextContent(type="text", text=json.dumps(categories, indent=2))]

        elif name == "component_by_category":
            category = arguments.get("category", "")
            subcategory = arguments.get("subcategory")
            library = get_library()
            if subcategory:
                results = library.get_by_subcategory(category, subcategory)
            else:
                results = library.get_by_category(category)
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        # Code Generation
        elif name == "code_templates":
            language = arguments.get("language", "python")
            generator = get_generator()
            templates = generator.list_templates(language)
            return [TextContent(type="text", text=json.dumps(templates, indent=2))]

        elif name == "code_get_template":
            template_name = arguments.get("template_name", "")
            language = arguments.get("language", "python")
            generator = get_generator()
            template = generator.get_template(template_name, language)
            if template:
                return [TextContent(type="text", text=template)]
            else:
                return [TextContent(type="text", text=f"Template not found: {template_name}")]

        elif name == "code_generate":
            description = arguments.get("description", "")
            language = arguments.get("language", "python")
            inputs = arguments.get("inputs", [])
            outputs = arguments.get("outputs", [])
            generator = get_generator()

            if inputs or outputs:
                # Generate custom code with specified inputs/outputs
                if language.lower() in ["python", "ghpython"]:
                    code = generator.generate_ghpython(description, inputs, outputs, "# TODO: Add implementation")
                else:
                    code = generator.generate_csharp(description, inputs, outputs, "// TODO: Add implementation")
                result = {"description": description, "language": language, "code": code}
            else:
                # Generate from description using templates
                result = generator.generate_from_description(description, language)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ============================================================
        # AI Mentoring Tools
        # ============================================================
        elif name == "predict_performance":
            if not _mentoring_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Mentoring module not available",
                    "hint": "Check that gh_analyzer is properly installed"
                }, indent=2))]

            optimization_type = arguments.get("optimization_type", "all")
            target_guids = arguments.get("target_guids")

            # Get canvas state for component data
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])

            # Get performance data if available
            perf_data = {}
            if "performance" in canvas_state:
                for comp in canvas_state.get("performance", []):
                    guid = comp.get("guid")
                    time_ms = comp.get("execution_time_ms", 0)
                    if guid:
                        perf_data[guid] = time_ms

            # Create predictor
            predictor = create_predictor_from_canvas_data(components, perf_data)

            if optimization_type == "all":
                # Get summary of all optimizations
                summary = predictor.get_optimization_summary()
                result = {
                    "success": True,
                    "mode": "summary",
                    "data": summary
                }
            else:
                # Get specific optimization prediction
                try:
                    prediction = predictor.predict_optimization_impact(
                        optimization_type,
                        target_guids
                    )
                    result = {
                        "success": True,
                        "mode": "single",
                        "prediction": {
                            "optimization_type": prediction.optimization_type,
                            "target_components": prediction.target_components,
                            "current_time_ms": prediction.current_time_ms,
                            "predicted_time_ms": prediction.predicted_time_ms,
                            "improvement_percent": round(prediction.improvement_percent, 1),
                            "confidence": round(prediction.confidence, 2),
                            "effort_level": prediction.effort_level,
                            "description": prediction.description,
                            "steps": prediction.steps
                        }
                    }
                except ValueError as e:
                    result = {"success": False, "error": str(e)}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "suggest_alternatives":
            if not _mentoring_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Mentoring module not available",
                    "hint": "Check that gh_analyzer is properly installed"
                }, indent=2))]

            pattern_type = arguments.get("pattern_type")
            if pattern_type == "all":
                pattern_type = None

            # Get canvas state for component data
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])
            wires = canvas_state.get("wires", [])

            # Create suggester
            suggester = create_suggester_from_canvas_data(components, wires)

            if pattern_type:
                # Get specific pattern suggestions
                suggestions = suggester.suggest_alternatives(pattern_type)
                result = {
                    "success": True,
                    "mode": "single_pattern",
                    "pattern_type": pattern_type,
                    "suggestions": [
                        {
                            "current_pattern": s.current_pattern,
                            "alternative": s.alternative_pattern,
                            "improvement": s.expected_improvement,
                            "explanation": s.explanation,
                            "affected_guids": s.components_affected,
                            "steps": s.implementation_steps
                        }
                        for s in suggestions
                    ]
                }
            else:
                # Get all suggestions summary
                summary = suggester.get_all_suggestions_summary()
                result = {
                    "success": True,
                    "mode": "summary",
                    "data": summary
                }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "auto_group":
            if not _mentoring_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Mentoring module not available",
                    "hint": "Check that gh_analyzer is properly installed"
                }, indent=2))]

            min_cluster_size = arguments.get("min_cluster_size", 2)
            max_clusters = arguments.get("max_clusters", 10)
            color_scheme = arguments.get("color_scheme", "default")

            # Get canvas state for component data
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])
            wires = canvas_state.get("wires", [])

            # Create grouper
            grouper = create_grouper_from_canvas_data(components, wires)

            # Get grouping recommendation
            recommendation = grouper.get_grouping_recommendation(
                min_size=min_cluster_size,
                max_clusters=max_clusters,
                color_scheme=color_scheme
            )

            # Convert to serializable format
            result = {
                "success": True,
                "total_clusters": len(recommendation.clusters),
                "ungrouped_count": recommendation.ungrouped_count,
                "clusters": [
                    {
                        "name": c.suggested_name,
                        "function_type": c.function_type,
                        "color": c.suggested_color,
                        "component_count": len(c.component_guids),
                        "component_guids": c.component_guids,
                        "confidence": c.confidence,
                        "boundary": c.boundary_rect
                    }
                    for c in recommendation.clusters
                ],
                "layout_suggestions": recommendation.layout_suggestions,
                "color_scheme": {
                    k: list(v) for k, v in recommendation.color_scheme.items()
                }
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "highlight_components":
            guids = arguments.get("guids", [])
            context = arguments.get("context", "reference")

            if not guids:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "No GUIDs provided"
                }, indent=2))]

            # Color mapping
            colors = {
                "problem": (255, 100, 100),
                "suggestion": (100, 200, 255),
                "optimized": (100, 255, 100),
                "reference": (255, 200, 100)
            }
            color = colors.get(context, colors["reference"])

            bridge = get_bridge()
            result = await bridge.highlight_components(guids, color)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "clear_highlights":
            guids = arguments.get("guids")
            bridge = get_bridge()
            result = await bridge.clear_highlights(guids)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ml_layout_analysis":
            if not _ml_layout_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "ML Layout module not available",
                    "hint": "Install scikit-learn: pip install scikit-learn numpy"
                }, indent=2))]

            clustering_method = arguments.get("clustering_method", "dbscan")
            eps = arguments.get("eps", 150)
            n_clusters = arguments.get("n_clusters")
            include_anomalies = arguments.get("include_anomalies", True)

            # Get canvas state
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])
            wires = canvas_state.get("wires", [])

            # Create ML learner
            learner = create_ml_learner_from_canvas_data(components, wires)

            # Run clustering
            if clustering_method == "kmeans":
                clusters = learner.detect_clusters_kmeans(n_clusters=n_clusters)
            else:
                clusters = learner.detect_clusters_dbscan(eps=eps)

            # Get data flow classification
            data_flow = learner.classify_data_flow()

            # Helper to convert numpy types to Python native types
            def to_native(obj):
                if obj is None:
                    return None
                if hasattr(obj, 'item'):  # numpy scalar
                    return obj.item()
                elif isinstance(obj, (list, tuple)):
                    return [to_native(x) for x in obj]
                elif isinstance(obj, dict):
                    return {k: to_native(v) for k, v in obj.items()}
                elif isinstance(obj, float):
                    return float(obj)
                elif isinstance(obj, int):
                    return int(obj)
                return obj

            # Get anomalies if requested
            anomalies = []
            if include_anomalies:
                anomaly_results = learner.detect_layout_anomalies()
                anomalies = [
                    {
                        "guid": str(a.component_guid),
                        "type": str(a.anomaly_type),
                        "severity": float(a.severity),
                        "suggestion": str(a.suggestion),
                        "expected_position": to_native(a.expected_position)
                    }
                    for a in anomaly_results
                ]

            # Learn patterns
            learned = learner.learn_from_canvas()

            result = {
                "success": True,
                "ml_available": learner.ml_available,
                "clustering_method": clustering_method,
                "clusters": [
                    {
                        "id": int(c.cluster_id),
                        "name": c.suggested_name,
                        "pattern_type": c.pattern_type,
                        "component_count": len(c.component_guids),
                        "component_guids": c.component_guids,
                        "centroid": to_native(c.centroid),
                        "confidence": float(c.confidence),
                        "color": to_native(c.suggested_color),
                        "bounding_box": to_native(c.bounding_box) if c.bounding_box else None
                    }
                    for c in clusters
                ],
                "data_flow": {
                    "input_count": len(data_flow.get("input", [])),
                    "processing_count": len(data_flow.get("processing", [])),
                    "output_count": len(data_flow.get("output", [])),
                    "input_guids": data_flow.get("input", [])[:10],
                    "output_guids": data_flow.get("output", [])[:10]
                },
                "anomalies": anomalies,
                "learned_patterns": to_native(learned)
            }

            # Recursively convert all numpy types to native Python types
            def convert_to_native(obj):
                if obj is None:
                    return None
                if hasattr(obj, 'item'):  # numpy scalar (int64, float64, etc.)
                    return obj.item()
                if hasattr(obj, 'tolist'):  # numpy array
                    return obj.tolist()
                if isinstance(obj, dict):
                    return {str(k): convert_to_native(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [convert_to_native(x) for x in obj]
                if isinstance(obj, (int, float, str, bool)):
                    return obj
                # Fallback: try to convert to string
                try:
                    return str(obj)
                except:
                    return None

            result = convert_to_native(result)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "predict_component_position":
            if not _ml_layout_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "ML Layout module not available",
                    "hint": "Install scikit-learn: pip install scikit-learn numpy"
                }, indent=2))]

            component_name = arguments.get("component_name", "")
            connected_to = arguments.get("connected_to")
            direction = arguments.get("direction", "right")

            # Get canvas state
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])
            wires = canvas_state.get("wires", [])

            # Create ML learner
            learner = create_ml_learner_from_canvas_data(components, wires)

            # Learn from current canvas
            learner.learn_from_canvas()

            # Predict position
            prediction = learner.predict_next_position(
                component_name=component_name,
                connected_to=connected_to,
                direction=direction
            )

            result = {
                "success": True,
                "component_name": component_name,
                "predicted_position": {
                    "x": prediction.x,
                    "y": prediction.y
                },
                "confidence": prediction.confidence,
                "reasoning": prediction.reasoning,
                "alternatives": prediction.alternatives
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ============================================================
        # Component Creation & Manipulation Tools
        # ============================================================
        elif name == "gh_add_component":
            comp_name = arguments.get("name", "")
            x = arguments.get("x", 0)
            y = arguments.get("y", 0)
            nickname = arguments.get("nickname")
            category = arguments.get("category")
            subcategory = arguments.get("subcategory")
            delay = arguments.get("delay", 0.3)

            if not comp_name:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Component name is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.add_component(
                name=comp_name,
                x=x,
                y=y,
                nickname=nickname,
                category=category,
                subcategory=subcategory,
                delay=delay
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_connect":
            source_guid = arguments.get("source_guid", "")
            source_output = arguments.get("source_output", 0)
            target_guid = arguments.get("target_guid", "")
            target_input = arguments.get("target_input", 0)

            if not source_guid or not target_guid:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "source_guid and target_guid are required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.connect_components(
                source_guid=source_guid,
                source_output=source_output,
                target_guid=target_guid,
                target_input=target_input
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_disconnect":
            source_guid = arguments.get("source_guid", "")
            source_output = arguments.get("source_output", 0)
            target_guid = arguments.get("target_guid", "")
            target_input = arguments.get("target_input", 0)

            if not source_guid or not target_guid:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "source_guid and target_guid are required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.disconnect_components(
                source_guid=source_guid,
                source_output=source_output,
                target_guid=target_guid,
                target_input=target_input
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_set_value":
            guid = arguments.get("guid", "")
            value = arguments.get("value")
            param_index = arguments.get("param_index", 0)

            if not guid:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "guid is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.set_component_value(
                guid=guid,
                value=value,
                param_index=param_index
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_delete_component":
            guid = arguments.get("guid", "")

            if not guid:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "guid is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.delete_component(guid)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_move_component":
            guid = arguments.get("guid", "")
            x = arguments.get("x", 0)
            y = arguments.get("y", 0)

            if not guid:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "guid is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.move_component(guid, x, y)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_create_group":
            guids = arguments.get("guids", [])
            group_name = arguments.get("name")
            color = arguments.get("color")

            if not guids:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "guids list is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.create_group(
                guids=guids,
                name=group_name,
                color=tuple(color) if color else None
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_get_component_info":
            guid = arguments.get("guid", "")

            if not guid:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "guid is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.get_component_info(guid)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_new_definition":
            bridge = get_bridge()
            result = await bridge.new_definition()
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "gh_save_definition":
            file_path = arguments.get("file_path", "")

            if not file_path:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "file_path is required"
                }, indent=2))]

            bridge = get_bridge()
            result = await bridge.save_definition(file_path)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # ============================================================
        # Persistent Layout Learning Tools
        # ============================================================
        elif name == "ml_learn_layout":
            if not _persistent_learner_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Persistent learner module not available"
                }, indent=2))]

            source_name = arguments.get("source_name", "manual_session")

            # Get canvas state
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])
            wires = canvas_state.get("wires", [])

            # Learn from canvas (persistent learner - statistics based)
            learner = get_persistent_learner()
            result = learner.learn_from_canvas(
                components=components,
                wires=wires,
                source_file=source_name
            )

            # Also learn with advanced learner (KNN/ML based)
            advanced_result = None
            if _advanced_learner_available:
                try:
                    advanced_learner = get_advanced_learner()
                    advanced_result = advanced_learner.learn_from_canvas(
                        components=components,
                        wires=wires,
                        source_name=source_name
                    )
                    result["advanced_learning"] = {
                        "success": True,
                        "pair_patterns_learned": advanced_result.get("pair_patterns_learned", 0),
                        "branching_patterns_learned": advanced_result.get("branching_patterns_learned", 0),
                        "knn_samples": advanced_result.get("knn_samples", 0)
                    }
                except Exception as e:
                    result["advanced_learning"] = {
                        "success": False,
                        "error": str(e)
                    }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ml_get_position":
            if not _persistent_learner_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Persistent learner module not available"
                }, indent=2))]

            component_name = arguments.get("component_name", "")
            connected_to_guid = arguments.get("connected_to_guid")
            direction = arguments.get("direction", "right")

            if not component_name:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "component_name is required"
                }, indent=2))]

            learner = get_persistent_learner()

            # Get connected component info if provided
            connected_to = None
            if connected_to_guid:
                bridge = get_bridge()
                canvas_state = await bridge.get_grasshopper_state()
                if canvas_state.get("success"):
                    for comp in canvas_state.get("components", []):
                        if comp.get("guid") == connected_to_guid:
                            connected_to = comp
                            break

            result = learner.get_optimal_position(
                component_name=component_name,
                connected_to=connected_to,
                direction=direction
            )

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ml_learning_summary":
            if not _persistent_learner_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Persistent learner module not available"
                }, indent=2))]

            learner = get_persistent_learner()
            result = learner.get_learning_summary()

            # Add advanced learner summary
            if _advanced_learner_available:
                try:
                    advanced_learner = get_advanced_learner()
                    advanced_summary = advanced_learner.get_summary()
                    result["advanced_learning"] = advanced_summary
                except Exception as e:
                    result["advanced_learning"] = {"error": str(e)}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ml_clear_learning":
            if not _persistent_learner_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Persistent learner module not available"
                }, indent=2))]

            confirm = arguments.get("confirm", False)
            if not confirm:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Must set confirm=true to clear learning data"
                }, indent=2))]

            learner = get_persistent_learner()
            result = learner.clear()

            # Also clear advanced learner data
            if _advanced_learner_available:
                try:
                    advanced_learner = get_advanced_learner()
                    advanced_learner.clear()
                    result["advanced_learning_cleared"] = True
                except Exception as e:
                    result["advanced_learning_cleared"] = False
                    result["advanced_learning_error"] = str(e)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ml_auto_layout":
            if not _persistent_learner_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Persistent learner module not available"
                }, indent=2))]

            start_x = arguments.get("start_x", 100)
            start_y = arguments.get("start_y", 100)
            dry_run = arguments.get("dry_run", False)
            use_v9 = arguments.get("use_v9", True)  # Legacy parameter for backwards compatibility

            # Get canvas state
            bridge = get_bridge()
            canvas_state = await bridge.get_grasshopper_state()

            if not canvas_state.get("success"):
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Could not get canvas state",
                    "hint": "Make sure Rhino is running with the bridge listener"
                }, indent=2))]

            components = canvas_state.get("components", [])
            wires = canvas_state.get("wires", [])

            # Calculate layout
            learner = get_persistent_learner()

            # v1: New hierarchical pattern-based layout (Main Chain + Fan-In/Out)
            # This is now the default algorithm
            layout_result = learner.calculate_auto_layout_v1(
                components=components,
                wires=wires,
                start_x=start_x,
                start_y=start_y,
                mode="full"
            )

            if not layout_result.get("success"):
                return [TextContent(type="text", text=json.dumps(layout_result, indent=2))]

            # If dry_run, just return the calculated positions with debug info
            if dry_run:
                layout_result["dry_run"] = True
                layout_result["message"] = "Dry run - no components were moved. Set dry_run=false to apply layout."
                # Include debug_log if available
                if "debug_log" in layout_result:
                    layout_result["debug_log"] = layout_result["debug_log"][:30]  # Limit
                return [TextContent(type="text", text=json.dumps(layout_result, indent=2))]

            # Apply moves
            moves = layout_result.get("moves", [])
            successful_moves = 0
            failed_moves = []

            for move in moves:
                guid = move["guid"]
                new_x = move["new_x"]
                new_y = move["new_y"]

                try:
                    move_result = await bridge.move_component(guid, new_x, new_y)
                    if move_result.get("success"):
                        successful_moves += 1
                    else:
                        failed_moves.append({
                            "guid": guid,
                            "name": move.get("name", ""),
                            "error": move_result.get("error", "Unknown error")
                        })
                except Exception as e:
                    failed_moves.append({
                        "guid": guid,
                        "name": move.get("name", ""),
                        "error": str(e)
                    })

            result = {
                "success": True,
                "total_components": layout_result.get("total_components", 0),
                "components_moved": successful_moves,
                "failed_moves": len(failed_moves),
                "levels_created": layout_result.get("levels_created", 0),
                "spacing_used": layout_result.get("spacing_used", {}),
            }

            if failed_moves:
                result["failed_details"] = failed_moves[:10]  # Limit to first 10 failures

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "ml_learn_from_files":
            if not _persistent_learner_available:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "Persistent learner module not available"
                }, indent=2))]

            file_paths = arguments.get("file_paths", [])

            if not file_paths:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": "No file paths provided"
                }, indent=2))]

            learner = get_persistent_learner()
            result = learner.learn_from_gh_files(file_paths)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
