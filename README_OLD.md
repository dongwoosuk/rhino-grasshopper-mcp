# Grasshopper MCP Server

MCP server for Grasshopper/Rhino integration with AI mentoring capabilities.

## Features

- **Rhino Bridge**: Connect to running Rhino/Grasshopper instances, execute Python remotely
- **GH File Operations**: Read, parse, and analyze .gh/.ghx files
- **Component Library**: Searchable database of Grasshopper components
- **Code Generation**: Generate GHPython and C# scripts from templates
- **AI Mentoring**: Performance prediction, alternative suggestions, auto-grouping, ML layout analysis

## Installation

```bash
cd mcp_servers/grasshopper_mcp
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

This will automatically install all dependencies including:
- `mcp` - Model Context Protocol
- `scikit-learn` - ML clustering and analysis
- `numpy` - Numerical computing

## Usage

### 1. Start the MCP Server (automatic via Claude Desktop)

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "grasshopper": {
      "command": "path/to/grasshopper_mcp/.venv/Scripts/python.exe",
      "args": ["-m", "grasshopper_mcp"],
      "cwd": "path/to/grasshopper_mcp"
    }
  }
}
```

### 2. Start the Rhino Bridge Listener (for live Rhino connection)

To enable live connection to Rhino/Grasshopper:

1. Open Rhino 7 or 8
2. Open the Python editor: `EditPythonScript` command
3. Open the listener script:
   ```
   rhino_listener/rhino_bridge_listener.py
   ```
4. Run the script (F5 or green play button)
5. You should see:
   ```
   ==================================================
   Rhino Bridge Listener started
   Listening on localhost:8080
   ==================================================
   Ready to receive commands from MCP server...
   ```

## Available Tools

### Rhino Bridge (requires listener running in Rhino)

| Tool | Description |
|------|-------------|
| `rhino_status` | Check Rhino/GH connection status |
| `rhino_execute_python` | Execute Python code in Rhino |
| `gh_canvas_state` | Get current Grasshopper canvas state |
| `gh_load_definition` | Load a .gh/.ghx file into Grasshopper |
| `gh_solve` | Trigger a solve/recompute |

### GH File Operations (works without Rhino)

| Tool | Description |
|------|-------------|
| `gh_file_summary` | Get summary of a .gh/.ghx file |
| `gh_list_components` | List all components in a definition |
| `gh_find_components` | Find components by name pattern |
| `gh_get_xml` | Get raw XML content |

### Component Library

| Tool | Description |
|------|-------------|
| `component_search` | Search components by name/keywords |
| `component_categories` | List all categories |
| `component_by_category` | Get components in a category |

### Code Generation

| Tool | Description |
|------|-------------|
| `code_templates` | List available templates |
| `code_get_template` | Get a specific template |
| `code_generate` | Generate code from description |

### AI Mentoring Tools

| Tool | Description |
|------|-------------|
| `predict_performance` | Predict optimization impact (e.g., "15-30% improvement expected") |
| `suggest_alternatives` | Detect inefficient patterns and suggest better approaches |
| `auto_group` | Analyze wire connections and suggest logical groupings |
| `highlight_components` | Highlight specific components on canvas |
| `clear_highlights` | Clear component highlights |
| `ml_layout_analysis` | ML-based clustering analysis (DBSCAN/K-means) |
| `predict_component_position` | Predict optimal position for new components |

## Architecture

```
grasshopper_mcp/
├── grasshopper_mcp/
│   ├── __init__.py
│   ├── __main__.py           # Entry point
│   ├── bridge.py             # Main MCP server & tools
│   ├── rhino_bridge.py       # TCP client to Rhino
│   ├── gh_file_ops.py        # .gh/.ghx file parsing
│   ├── component_library.py  # Component database
│   ├── code_generator.py     # Code templates
│   ├── layout_learner.py     # Statistics-based layout
│   └── mentoring/            # AI Mentoring modules
│       ├── __init__.py       # Shared data types
│       ├── performance_predictor.py   # Optimization prediction
│       ├── alternative_suggester.py   # Pattern detection & alternatives
│       ├── auto_grouper.py            # Wire-based grouping
│       └── ml_layout_learner.py       # ML clustering & prediction
├── rhino_listener/
│   └── rhino_bridge_listener.py  # Run this IN Rhino
├── pyproject.toml
└── README.md
```

## Mentoring Module Details

### Performance Predictor
- Predicts improvement percentage for optimizations
- Supports: Preview Off, Mesh Simplify, Caching, Data Tree optimization
- Returns confidence level for each prediction

### Alternative Suggester
Detects inefficient patterns and suggests better approaches:
- Multiple Move → Transform Matrix
- Flatten + Graft → Path Mapper
- Python loops → Native GH components
- Serial Boolean → Batch Boolean
- Expression for simple math → Native Math components

### Auto Grouper
- BFS-based wire connectivity analysis
- Classifies components: input, transform, calculation, output, geometry, data
- Suggests group names and colors based on function

### ML Layout Learner
- DBSCAN clustering for automatic grouping
- K-means for fixed cluster count
- K-NN based position prediction for new components
- Layout anomaly detection (isolated, overlapping, wrong flow)

## Troubleshooting

### "Connection refused" error
- Make sure Rhino is running
- Make sure the listener script is running in Rhino
- Check that port 8080 is not blocked

### Listener won't start
- Make sure no other application is using port 8080
- Try a different port: `start_listener(port=8081)`

### Grasshopper commands fail
- Make sure Grasshopper is open in Rhino
- Try running `_Grasshopper` command in Rhino first

### Mentoring features not working
- Check that scikit-learn is installed: `pip list | grep scikit`
- Re-install with: `pip install -e .`

## Version History

- **v0.3.0**: Added AI Mentoring module (performance prediction, alternative suggestions, auto-grouping, ML layout analysis)
- **v0.2.0**: Added Rhino Bridge and live connection support
- **v0.1.0**: Initial release with file operations and component library
