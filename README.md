# 🚀 Rhino Grasshopper MCP - AI-Powered Computational Design Assistant

An MCP (Model Context Protocol) server that brings AI capabilities directly into Rhino/Grasshopper workflows, featuring **ML-based automatic layout optimization** - a capability not found in any other publicly available tool.

![Version](https://img.shields.io/badge/version-0.1.0--beta-orange)
![Status](https://img.shields.io/badge/status-beta-yellow)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## 🎯 What Makes This Different?

Unlike basic Grasshopper-to-LLM connectors that only generate code, this tool includes:

### 🧠 ML-Based Auto Layout (Industry First)
- **DBSCAN clustering** for automatic component grouping
- **K-means clustering** for fixed group counts
- **User pattern learning** with persistent preferences
- **K-NN position prediction** for optimal new component placement
- **Wire crossing minimization** algorithm

### 🎓 AI Mentoring System
- **Performance prediction**: Estimates optimization impact (e.g., "15-30% improvement expected")
- **Pattern detection**: Identifies inefficient patterns and suggests better alternatives
- **Auto-grouping**: Analyzes wire connectivity to suggest logical component groups
- **Layout anomaly detection**: Finds isolated, overlapping, or misaligned components

### 🔌 Live Rhino Integration
- Real-time connection to running Rhino/Grasshopper instances
- Execute Python code remotely in Rhino
- Get canvas state and trigger solves
- No file-based workflow required

## 📋 Features Overview

| Category | Features |
|----------|----------|
| **Rhino Bridge** | Live connection, remote Python execution, canvas state |
| **GH File Ops** | Parse .gh/.ghx files, analyze structure, extract components |
| **Component Library** | Searchable database of 500+ GH components |
| **Code Generation** | GHPython and C# script templates |
| **AI Mentoring** | Performance prediction, alternatives, auto-grouping |
| **ML Layout** | Clustering, position prediction, crossing minimization |

## 🛠️ Installation

```bash
git clone https://github.com/dongwoosuk/rhino-grasshopper-mcp.git
cd rhino-grasshopper-mcp
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e .
```

## ⚙️ Configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "grasshopper": {
      "command": "path/to/rhino_grasshopper_mcp/.venv/Scripts/python.exe",
      "args": ["-m", "rhino_grasshopper_mcp"]
    }
  }
}
```

## 🔌 Live Rhino Connection (Optional)

To enable real-time Rhino/Grasshopper control:

1. Open Rhino 7 or 8
2. Run `ScriptEditor` in Rhino 8 and select **Python 3**
3. Open and run `rhino_listener/rhino_bridge_listener.py` with Python 3.
   Keep the cloned repository structure: the listener also needs its sibling
   `graph_operations.py` and `rhino_grasshopper_mcp/port_layout.py`.
   New batch graphs use Elefront **EF Data Description (R6)**; install Elefront
   before using `gh_apply_graph`. Do not launch this listener with the legacy
   `EditPythonScript` / IronPython editor.
4. You'll see: `Rhino Bridge Listener started on localhost:8080`

## 📚 Available Tools

### Rhino Bridge (requires listener)
| Tool | Description |
|------|-------------|
| `rhino_status` | Check connection status |
| `rhino_execute_python` | Execute Python in Rhino |
| `gh_canvas_state` | Get current canvas state |
| `gh_load_definition` | Load a .gh file |
| `gh_solve` | Trigger recompute |

### AI Mentoring Tools
| Tool | Description |
|------|-------------|
| `predict_performance` | Predict optimization impact |
| `suggest_alternatives` | Detect patterns, suggest better approaches |
| `auto_group` | Analyze connectivity, suggest groupings |
| `ml_layout_analysis` | ML clustering analysis |
| `predict_component_position` | K-NN based position prediction |

### Pattern Detection Examples

The `suggest_alternatives` tool detects these inefficient patterns:

| Pattern | Better Alternative |
|---------|-------------------|
| Multiple Move components | Single Transform Matrix |
| Flatten + Graft sequence | Path Mapper |
| Python loops for geometry | Native GH components |
| Serial Boolean operations | Batch Boolean |
| Expression for simple math | Native Math components |

## 🏗️ Architecture

```
rhino_grasshopper_mcp/
├── rhino_grasshopper_mcp/
│   ├── bridge.py              # Main MCP server
│   ├── rhino_bridge.py        # TCP client to Rhino
│   ├── gh_file_ops.py         # .gh/.ghx parsing
│   ├── component_library.py   # Component database
│   ├── code_generator.py      # Code templates
│   └── mentoring/
│       ├── ml_layout_learner.py        # DBSCAN/K-means
│       ├── advanced_layout_learner.py  # Advanced learning
│       ├── persistent_layout_learner.py # User patterns
│       ├── performance_predictor.py    # Optimization prediction
│       ├── alternative_suggester.py    # Pattern detection
│       ├── auto_grouper.py             # Wire-based grouping
│       ├── wire_crossing_detector.py   # Crossing detection
│       └── crossing_minimizer.py       # Layout optimization
├── rhino_listener/
│   └── rhino_bridge_listener.py  # Run IN Rhino
└── pyproject.toml
```

## 🤖 ML Layout System Details

### How It Works

1. **Feature Extraction**: Analyzes component positions, types, and connections
2. **Clustering**: Groups components using DBSCAN or K-means
3. **Pattern Learning**: Stores user preferences in `layout_preferences.json`
4. **Position Prediction**: Uses K-NN to suggest optimal positions for new components
5. **Anomaly Detection**: Identifies layout issues (isolated nodes, overlaps, wrong flow direction)

### Supported Analyses

```python
# Example: ML clustering analysis
result = ml_layout_analysis(gh_file_path, method="dbscan")
# Returns: clusters, anomalies, optimization suggestions

# Example: Position prediction
result = predict_component_position(gh_file_path, "Panel", near_component="Slider")
# Returns: predicted X, Y coordinates based on learned patterns
```

## 🎯 Use Cases

- **Design Automation**: Let AI handle repetitive Grasshopper tasks
- **Code Review**: Get suggestions for optimizing definitions
- **Learning**: AI mentoring for Grasshopper best practices
- **Layout Cleanup**: Automatic organization of messy definitions
- **Team Standards**: Consistent component arrangement across projects

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

- Built on the [Model Context Protocol](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/model_context_protocol) by Anthropic
- Grasshopper by David Rutten / McNeel
- scikit-learn for ML algorithms

## 📬 Contact

Dongwoo Suk - Computational Design Specialist

- GitHub: [dongwoosuk](https://github.com/dongwoosuk)
- LinkedIn: [dongwoosuk](https://www.linkedin.com/in/dongwoosuk/)

## Graph and layout update

See [upgrade notes and validation](UPGRADE_NOTES.md) for measured-port layout,
batch graph tools, Rhino 8 Python 3 defaults and Elefront Name View descriptions.
Keep the repository folder structure when updating the listener.
