"""
Rhino Bridge Listener
Run this script inside Rhino to enable remote Python execution from the MCP server.

Usage in Rhino:
1. Open Rhino
2. Run EditPythonScript or use _RunPythonScript
3. Run this script - it will start listening for commands

The listener creates a simple TCP server that:
- Receives Python code from the MCP server
- Executes it in Rhino's Python environment
- Returns the results
"""

import socket
import threading
import json
import sys
import time
import traceback
from io import StringIO

# Configuration
HOST = 'localhost'
PORT = 8080
BUFFER_SIZE = 65536

# =============================================================================
# PREFERRED COMPONENT MAP
# When a component name has multiple versions (old vs new), specify which to use
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


def find_component(server, name, category=None, subcategory=None):
    """
    Find a Grasshopper component by name with preference for specific category/subcategory.
    Automatically skips obsolete (Old) components.

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

    name_lower = name.lower()

    # Search for matches, preferring non-obsolete components
    candidates = []

    for proxy in server.ObjectProxies:
        # Skip obsolete components entirely
        if proxy.Obsolete:
            continue

        # Check name match (exact or nickname)
        proxy_name = proxy.Desc.Name
        proxy_nickname = proxy.Desc.NickName if hasattr(proxy.Desc, 'NickName') else ''

        if proxy_name.lower() != name_lower and proxy_nickname.lower() != name_lower:
            continue

        # Check category/subcategory if specified
        if category is not None and proxy.Desc.Category != category:
            continue
        if subcategory is not None and proxy.Desc.SubCategory != subcategory:
            continue

        candidates.append(proxy)

    if candidates:
        return candidates[0]

    # Fallback: search again but also check partial matches (still no obsolete)
    for proxy in server.ObjectProxies:
        if proxy.Obsolete:
            continue
        if name_lower in proxy.Desc.Name.lower():
            return proxy

    return None


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
    try:
        import System.Drawing as SD
    except ImportError:
        return None

    proxy = find_component(server, name, category, subcategory)
    if proxy is None:
        print(f"Component not found: {name}")
        return None

    comp = proxy.CreateInstance()
    comp.CreateAttributes()
    comp.Attributes.Pivot = SD.PointF(x, y)
    doc.AddObject(comp, False)
    return comp


def create_component_with_log(server, doc, name, x, y, category=None, subcategory=None, delay=0.5):
    """
    Create a component with logging and delay for real-time visualization.

    Args:
        server: Grasshopper.Instances.ComponentServer
        doc: Grasshopper document
        name: Component name
        x, y: Canvas position
        category: Optional category override
        subcategory: Optional subcategory override
        delay: Delay in seconds after creation (default 0.5)

    Returns:
        Created component instance or None
    """
    print(f"[Creating] {name} at ({x}, {y})...")

    comp = create_component(server, doc, name, x, y, category, subcategory)

    if comp:
        print(f"[Created] {name} - GUID: {comp.InstanceGuid}")
        # Refresh canvas to show the new component
        try:
            import Grasshopper
            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas:
                canvas.Refresh()
        except:
            pass
        # Apply delay for visualization
        time.sleep(delay)
    else:
        print(f"[Failed] {name}")

    return comp


def get_learned_spacing():
    """Get the learned spacing preferences"""
    global _layout_preferences
    return {
        'x': _layout_preferences.get('spacing_x', 200),
        'y': _layout_preferences.get('spacing_y', 80)
    }


def get_next_position(base_x, base_y, direction="right"):
    """
    Calculate next component position based on learned preferences.

    Args:
        base_x, base_y: Reference component position
        direction: "right", "below", "left", "above"

    Returns:
        Tuple of (x, y) coordinates
    """
    spacing = get_learned_spacing()

    if direction == "right":
        return (base_x + spacing['x'], base_y)
    elif direction == "below":
        return (base_x, base_y + spacing['y'])
    elif direction == "left":
        return (base_x - spacing['x'], base_y)
    elif direction == "above":
        return (base_x, base_y - spacing['y'])
    else:
        return (base_x + spacing['x'], base_y)


# Try to import Rhino modules
try:
    import rhinoscriptsyntax as rs
    import Rhino
    import scriptcontext as sc
    IN_RHINO = True
except ImportError:
    IN_RHINO = False
    print("Warning: Not running inside Rhino. Some features will be limited.")


class RhinoBridgeListener:
    """TCP server that listens for Python code execution requests"""

    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.thread = None

    def start(self):
        """Start the listener server"""
        if self.running:
            print(f"Listener already running on {self.host}:{self.port}")
            return

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Allow periodic checking
            self.running = True

            print(f"=" * 50)
            print(f"Rhino Bridge Listener started")
            print(f"Listening on {self.host}:{self.port}")
            print(f"=" * 50)
            print(f"Ready to receive commands from MCP server...")
            print()

            # Start listening in a separate thread
            self.thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.thread.start()

        except Exception as e:
            print(f"Error starting listener: {e}")
            self.stop()

    def stop(self):
        """Stop the listener server"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        print("Listener stopped")

    def _listen_loop(self):
        """Main listening loop"""
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"Connection from {address}")

                # Handle client in a separate thread
                handler = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket,),
                    daemon=True
                )
                handler.start()

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")

    def _handle_client(self, client_socket):
        """Handle a client connection"""
        try:
            # Receive data
            data = b""
            while True:
                chunk = client_socket.recv(BUFFER_SIZE)
                if not chunk:
                    break
                data += chunk
                # Check for end of message (double newline)
                if b"\n\n" in data:
                    break

            if not data:
                return

            # Parse the request
            request = json.loads(data.decode('utf-8').strip())
            command = request.get('command', 'execute')

            if command == 'execute':
                code = request.get('code', '')
                result = self._execute_code(code)
            elif command == 'ping':
                result = {'success': True, 'message': 'pong', 'in_rhino': IN_RHINO}
            elif command == 'status':
                result = self._get_status()
            elif command == 'gh_state':
                result = self._get_grasshopper_state()
            elif command == 'load_gh':
                file_path = request.get('file_path', '')
                result = self._load_gh_definition(file_path)
            elif command == 'solve':
                result = self._solve_definition()
            elif command == 'learn_layout':
                result = self._learn_from_canvas()
            elif command == 'get_layout_prefs':
                result = self._get_layout_preferences()
            elif command == 'highlight_components':
                guids = request.get('guids', [])
                color = request.get('color', [255, 200, 100])
                result = self._highlight_components(guids, color)
            elif command == 'clear_highlights':
                guids = request.get('guids')
                result = self._clear_highlights(guids)
            # Component Creation & Manipulation Commands
            elif command == 'add_component':
                name = request.get('name', '')
                x = request.get('x', 0)
                y = request.get('y', 0)
                nickname = request.get('nickname')
                category = request.get('category')
                subcategory = request.get('subcategory')
                delay = request.get('delay', 0)
                result = self._add_component(name, x, y, nickname, category, subcategory, delay)
            elif command == 'connect_components':
                source_guid = request.get('source_guid', '')
                source_output = request.get('source_output', 0)
                target_guid = request.get('target_guid', '')
                target_input = request.get('target_input', 0)
                result = self._connect_components(source_guid, source_output, target_guid, target_input)
            elif command == 'disconnect_components':
                source_guid = request.get('source_guid', '')
                source_output = request.get('source_output', 0)
                target_guid = request.get('target_guid', '')
                target_input = request.get('target_input', 0)
                result = self._disconnect_components(source_guid, source_output, target_guid, target_input)
            elif command == 'delete_component':
                guid = request.get('guid', '')
                result = self._delete_component(guid)
            elif command == 'set_value':
                guid = request.get('guid', '')
                value = request.get('value')
                param_index = request.get('param_index', 0)
                result = self._set_component_value(guid, value, param_index)
            elif command == 'move_component':
                guid = request.get('guid', '')
                x = request.get('x', 0)
                y = request.get('y', 0)
                result = self._move_component(guid, x, y)
            elif command == 'create_group':
                guids = request.get('guids', [])
                name = request.get('name')
                color = request.get('color')
                result = self._create_group(guids, name, color)
            elif command == 'get_component_info':
                guid = request.get('guid', '')
                result = self._get_component_info(guid)
            elif command == 'new_definition':
                result = self._new_definition()
            elif command == 'save_definition':
                file_path = request.get('file_path', '')
                result = self._save_definition(file_path)
            # Session Management Commands
            elif command == 'mark_session_start':
                mark_existing_components()
                result = {
                    'success': True,
                    'user_components': len(_user_component_guids),
                    'message': 'Session started. Existing components will be preserved.'
                }
            elif command == 'clear_session':
                result = clear_session_components()
            elif command == 'get_session_info':
                result = {
                    'success': True,
                    'user_components': len(_user_component_guids),
                    'session_components': len(_session_created_guids),
                    'user_guids': list(_user_component_guids)[:10],  # First 10 for brevity
                    'session_guids': list(_session_created_guids)[:10]
                }
            else:
                result = {'success': False, 'error': f'Unknown command: {command}'}

            # Send response
            response = json.dumps(result) + "\n\n"
            client_socket.sendall(response.encode('utf-8'))

        except json.JSONDecodeError as e:
            error_response = json.dumps({
                'success': False,
                'error': f'Invalid JSON: {e}'
            }) + "\n\n"
            client_socket.sendall(error_response.encode('utf-8'))
        except Exception as e:
            error_response = json.dumps({
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }) + "\n\n"
            try:
                client_socket.sendall(error_response.encode('utf-8'))
            except:
                pass
        finally:
            try:
                client_socket.close()
            except:
                pass

    def _execute_code(self, code):
        """Execute Python code and capture output"""
        if not code.strip():
            return {'success': False, 'error': 'No code provided'}

        # Capture stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

        result = {'success': True}
        return_value = None

        try:
            # Create execution namespace with Rhino modules
            namespace = {
                '__name__': '__main__',
                '__builtins__': __builtins__,
            }

            if IN_RHINO:
                namespace.update({
                    'rs': rs,
                    'rhinoscriptsyntax': rs,
                    'Rhino': Rhino,
                    'sc': sc,
                    'scriptcontext': sc,
                })

                # Try to add Grasshopper if available
                try:
                    import Grasshopper
                    namespace['Grasshopper'] = Grasshopper
                    namespace['gh'] = Grasshopper

                    # Add component helper functions
                    namespace['PREFERRED_COMPONENTS'] = PREFERRED_COMPONENTS
                    namespace['find_component'] = find_component
                    namespace['create_component'] = create_component
                    namespace['create_component_with_log'] = create_component_with_log
                    namespace['get_learned_spacing'] = get_learned_spacing
                    namespace['get_next_position'] = get_next_position
                except:
                    pass

            # Execute the code
            exec(code, namespace)

            # Check for a 'result' variable in the namespace
            if 'result' in namespace:
                return_value = namespace['result']

            result['output'] = sys.stdout.getvalue()
            result['errors'] = sys.stderr.getvalue()

            if return_value is not None:
                try:
                    result['return_value'] = str(return_value)
                except:
                    result['return_value'] = '<unprintable>'

        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            result['traceback'] = traceback.format_exc()
            result['output'] = sys.stdout.getvalue()
            result['errors'] = sys.stderr.getvalue()

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return result

    def _get_status(self):
        """Get Rhino/Grasshopper status"""
        status = {
            'success': True,
            'in_rhino': IN_RHINO,
            'python_version': sys.version,
        }

        if IN_RHINO:
            try:
                status['rhino_version'] = str(Rhino.RhinoApp.Version)
                status['document_name'] = rs.DocumentName() or 'Untitled'
                status['document_path'] = rs.DocumentPath() or ''

                # Check if Grasshopper is loaded
                try:
                    import Grasshopper
                    status['grasshopper_loaded'] = True

                    # Try to get GH document info
                    gh_doc = Grasshopper.Instances.ActiveCanvas
                    if gh_doc and gh_doc.Document:
                        status['gh_document'] = True
                        status['gh_component_count'] = gh_doc.Document.ObjectCount
                    else:
                        status['gh_document'] = False
                except:
                    status['grasshopper_loaded'] = False

            except Exception as e:
                status['error'] = str(e)

        return status

    def _get_grasshopper_state(self):
        """Get current Grasshopper canvas state with positions and wires for ML analysis"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper

            canvas = Grasshopper.Instances.ActiveCanvas
            if not canvas or not canvas.Document:
                return {'success': False, 'error': 'No active Grasshopper document'}

            doc = canvas.Document

            components = []
            wires = []

            for obj in doc.Objects:
                # Basic component info with position
                comp_info = {
                    'name': obj.Name,
                    'nickname': obj.NickName,
                    'guid': str(obj.InstanceGuid),
                    'category': obj.Category if hasattr(obj, 'Category') else '',
                    'subcategory': obj.SubCategory if hasattr(obj, 'SubCategory') else '',
                    'x': obj.Attributes.Pivot.X,
                    'y': obj.Attributes.Pivot.Y,
                }

                # Get bounds if available
                try:
                    bounds = obj.Attributes.Bounds
                    comp_info['width'] = bounds.Width
                    comp_info['height'] = bounds.Height
                except:
                    pass

                # Classify object type for ML analysis
                type_name = obj.GetType().Name
                if 'Slider' in type_name:
                    comp_info['type'] = 'slider'
                elif 'Panel' in type_name:
                    comp_info['type'] = 'panel'
                elif 'Toggle' in type_name or 'Boolean' in type_name:
                    comp_info['type'] = 'toggle'
                elif 'Param' in type_name or comp_info['category'] == 'Params':
                    comp_info['type'] = 'param'
                elif 'Group' in type_name:
                    comp_info['type'] = 'group'
                elif 'Relay' in type_name:
                    comp_info['type'] = 'relay'
                else:
                    comp_info['type'] = 'component'

                # Get current value for sliders/panels
                try:
                    if comp_info['type'] == 'slider':
                        comp_info['value'] = float(obj.Slider.Value)
                        comp_info['min'] = float(obj.Slider.Minimum)
                        comp_info['max'] = float(obj.Slider.Maximum)
                    elif comp_info['type'] == 'panel':
                        comp_info['value'] = obj.UserText[:100] if obj.UserText else ''
                except:
                    pass

                # 입력/출력 개수 추가 (Y 정렬 계산용)
                try:
                    if hasattr(obj, 'Params'):
                        if hasattr(obj.Params, 'Input'):
                            comp_info['input_count'] = obj.Params.Input.Count
                        if hasattr(obj.Params, 'Output'):
                            comp_info['output_count'] = obj.Params.Output.Count
                    # IGH_Param 직접 구현체 (Panel 등)
                    elif hasattr(obj, 'Sources'):
                        comp_info['input_count'] = 1
                        comp_info['output_count'] = 1
                except:
                    pass

                components.append(comp_info)

                # Extract wire connections (for ML flow analysis)
                # 1. 일반 컴포넌트: Params.Input의 Sources
                if hasattr(obj, 'Params') and hasattr(obj.Params, 'Input'):
                    for input_idx, input_param in enumerate(obj.Params.Input):
                        for source in input_param.Sources:
                            try:
                                source_obj = source.Attributes.GetTopLevel.DocObject
                                # 소스의 출력 인덱스 찾기
                                source_output_idx = 0
                                if hasattr(source_obj, 'Params') and hasattr(source_obj.Params, 'Output'):
                                    for out_idx, out_param in enumerate(source_obj.Params.Output):
                                        if out_param == source:
                                            source_output_idx = out_idx
                                            break

                                wire_info = {
                                    'source_guid': str(source_obj.InstanceGuid),
                                    'target_guid': str(obj.InstanceGuid),
                                    'source_output_idx': source_output_idx,
                                    'target_input_idx': input_idx,
                                }
                                wires.append(wire_info)
                            except:
                                wire_info = {
                                    'source_guid': str(source.Attributes.GetTopLevel.DocObject.InstanceGuid),
                                    'target_guid': str(obj.InstanceGuid),
                                }
                                wires.append(wire_info)

                # 2. Panel 등 IGH_Param 직접 구현체: 자체 Sources 속성
                elif hasattr(obj, 'Sources'):
                    for source in obj.Sources:
                        try:
                            source_obj = source.Attributes.GetTopLevel.DocObject
                            # 소스의 출력 인덱스 찾기
                            source_output_idx = 0
                            if hasattr(source_obj, 'Params') and hasattr(source_obj.Params, 'Output'):
                                for out_idx, out_param in enumerate(source_obj.Params.Output):
                                    if out_param == source:
                                        source_output_idx = out_idx
                                        break

                            wire_info = {
                                'source_guid': str(source_obj.InstanceGuid),
                                'target_guid': str(obj.InstanceGuid),
                                'source_output_idx': source_output_idx,
                                'target_input_idx': 0,  # Panel은 단일 입력
                            }
                            wires.append(wire_info)
                        except:
                            pass

            return {
                'success': True,
                'component_count': doc.ObjectCount,
                'components': components,
                'wires': wires,
                'file_path': doc.FilePath or '',
                'is_modified': doc.IsModified,
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _load_gh_definition(self, file_path):
        """Load a Grasshopper definition"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        if not file_path:
            return {'success': False, 'error': 'No file path provided'}

        try:
            import Grasshopper
            import System.IO

            if not System.IO.File.Exists(file_path):
                return {'success': False, 'error': f'File not found: {file_path}'}

            # Open Grasshopper if not already open
            if not Grasshopper.Instances.ActiveCanvas:
                Rhino.RhinoApp.RunScript("_Grasshopper", False)

            # Load the definition
            io = Grasshopper.Kernel.GH_DocumentIO()
            if io.Open(file_path):
                doc = io.Document
                Grasshopper.Instances.ActiveCanvas.Document = doc
                return {
                    'success': True,
                    'file_path': file_path,
                    'component_count': doc.ObjectCount
                }
            else:
                return {'success': False, 'error': 'Failed to open file'}

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _solve_definition(self):
        """Trigger a solve of the current Grasshopper definition"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper

            canvas = Grasshopper.Instances.ActiveCanvas
            if not canvas or not canvas.Document:
                return {'success': False, 'error': 'No active Grasshopper document'}

            doc = canvas.Document
            doc.NewSolution(True)  # Recompute

            return {
                'success': True,
                'message': 'Solution triggered'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _learn_from_canvas(self):
        """Learn layout patterns from current canvas"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper

            canvas = Grasshopper.Instances.ActiveCanvas
            if not canvas or not canvas.Document:
                return {'success': False, 'error': 'No active Grasshopper document'}

            doc = canvas.Document

            # Extract component positions
            components = []
            for obj in doc.Objects:
                comp_info = {
                    'name': obj.Name,
                    'nickname': obj.NickName,
                    'guid': str(obj.InstanceGuid),
                    'x': obj.Attributes.Pivot.X,
                    'y': obj.Attributes.Pivot.Y,
                }
                components.append(comp_info)

            if len(components) < 2:
                return {
                    'success': False,
                    'error': 'Need at least 2 components to learn patterns'
                }

            # Calculate spacing patterns
            sorted_by_x = sorted(components, key=lambda c: c['x'])
            x_spacings = []
            for i in range(len(sorted_by_x) - 1):
                dx = sorted_by_x[i+1]['x'] - sorted_by_x[i]['x']
                if dx > 10:  # Ignore very small gaps
                    x_spacings.append(dx)

            sorted_by_y = sorted(components, key=lambda c: c['y'])
            y_spacings = []
            for i in range(len(sorted_by_y) - 1):
                dy = sorted_by_y[i+1]['y'] - sorted_by_y[i]['y']
                if dy > 10:
                    y_spacings.append(dy)

            # Calculate averages
            avg_x = sum(x_spacings) / len(x_spacings) if x_spacings else 200
            avg_y = sum(y_spacings) / len(y_spacings) if y_spacings else 80

            # Update global layout preferences
            global _layout_preferences
            if '_layout_preferences' not in globals():
                _layout_preferences = {'spacing_x': 200, 'spacing_y': 80, 'samples': 0}

            # Running average
            samples = _layout_preferences.get('samples', 0)
            if samples > 0:
                _layout_preferences['spacing_x'] = (
                    _layout_preferences['spacing_x'] * samples + avg_x
                ) / (samples + 1)
                _layout_preferences['spacing_y'] = (
                    _layout_preferences['spacing_y'] * samples + avg_y
                ) / (samples + 1)
            else:
                _layout_preferences['spacing_x'] = avg_x
                _layout_preferences['spacing_y'] = avg_y

            _layout_preferences['samples'] = samples + 1

            return {
                'success': True,
                'message': 'Layout patterns learned',
                'components_analyzed': len(components),
                'learned_spacing_x': round(_layout_preferences['spacing_x'], 1),
                'learned_spacing_y': round(_layout_preferences['spacing_y'], 1),
                'total_samples': _layout_preferences['samples']
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _get_layout_preferences(self):
        """Get current learned layout preferences"""
        global _layout_preferences
        if '_layout_preferences' not in globals() or _layout_preferences is None:
            _layout_preferences = {'spacing_x': 200, 'spacing_y': 80, 'samples': 0}

        return {
            'success': True,
            'preferences': {
                'spacing_x': round(_layout_preferences.get('spacing_x', 200), 1),
                'spacing_y': round(_layout_preferences.get('spacing_y', 80), 1),
                'samples': _layout_preferences.get('samples', 0)
            }
        }

    def _highlight_components(self, guids, color):
        """
        Highlight components on the Grasshopper canvas.

        Args:
            guids: List of component GUID strings
            color: RGB list [r, g, b]
        """
        global _highlighted_components

        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System
            import System.Drawing as SD

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            highlighted = []
            r, g, b = color[0], color[1], color[2]
            highlight_color = SD.Color.FromArgb(r, g, b)

            for guid_str in guids:
                try:
                    guid = System.Guid(guid_str)
                    obj = doc.FindObject(guid, True)
                    if obj:
                        # Store original color for restoration
                        if guid_str not in _highlighted_components:
                            # Store original attributes for later restoration
                            _highlighted_components[guid_str] = {
                                'original_selected': obj.Attributes.Selected
                            }

                        # Select and highlight
                        obj.Attributes.Selected = True
                        highlighted.append(guid_str)
                except Exception as e:
                    continue

            # Refresh canvas
            canvas.Refresh()

            return {
                'success': True,
                'highlighted_count': len(highlighted),
                'highlighted_guids': highlighted
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _clear_highlights(self, guids=None):
        """
        Clear component highlights.

        Args:
            guids: Optional list of GUIDs to clear. If None, clears all.
        """
        global _highlighted_components

        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            cleared = []

            if guids is None:
                # Clear all highlights
                guids_to_clear = list(_highlighted_components.keys())
            else:
                guids_to_clear = guids

            for guid_str in guids_to_clear:
                try:
                    guid = System.Guid(guid_str)
                    obj = doc.FindObject(guid, True)
                    if obj:
                        # Deselect
                        obj.Attributes.Selected = False
                        cleared.append(guid_str)

                        # Remove from tracking
                        if guid_str in _highlighted_components:
                            del _highlighted_components[guid_str]
                except:
                    continue

            # Refresh canvas
            canvas.Refresh()

            return {
                'success': True,
                'cleared_count': len(cleared),
                'cleared_guids': cleared
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    # =========================================================================
    # Component Creation & Manipulation Methods
    # =========================================================================

    def _add_component(self, name, x, y, nickname=None, category=None, subcategory=None, delay=0.3):
        """Add a component to the Grasshopper canvas with optional visual delay"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System.Drawing as SD

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            # Auto-start session if not already started (preserves existing components)
            _auto_start_session_if_needed()

            # Log progress
            print(f"[Creating] {name} at ({x}, {y})...")

            # Find the component using the helper function (filters out obsolete components)
            server = Grasshopper.Instances.ComponentServer
            comp_proxy = find_component(server, name, category, subcategory)

            if comp_proxy is None:
                print(f"[Failed] Component not found: {name}")
                return {
                    'success': False,
                    'error': f'Component not found: {name}',
                    'hint': 'Check component name spelling or use component_search tool'
                }

            # Create the component instance
            comp = comp_proxy.CreateInstance()
            if comp is None:
                print(f"[Failed] Could not create instance: {name}")
                return {'success': False, 'error': f'Failed to create instance of {name}'}

            # Create attributes (required before setting position)
            comp.CreateAttributes()

            # Set position
            comp.Attributes.Pivot = SD.PointF(float(x), float(y))

            # Set nickname if provided
            if nickname:
                comp.NickName = nickname

            # Add to document
            doc.AddObject(comp, False)

            # Trigger canvas update
            canvas.Refresh()

            # Log success
            display_name = nickname if nickname else comp.Name
            guid_str = str(comp.InstanceGuid)
            print(f"[Created] {display_name} - GUID: {guid_str}")

            # Track as session-created component
            _session_created_guids.add(guid_str)

            # Apply visual delay if specified
            if delay and delay > 0:
                time.sleep(delay)

            return {
                'success': True,
                'guid': guid_str,
                'name': comp.Name,
                'nickname': comp.NickName,
                'position': {'x': x, 'y': y}
            }

        except Exception as e:
            print(f"[Error] {name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _connect_components(self, source_guid, source_output, target_guid, target_input):
        """Connect two components with a wire"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            # Find source component
            src_guid = System.Guid(source_guid)
            src_obj = doc.FindObject(src_guid, True)
            if src_obj is None:
                return {'success': False, 'error': f'Source component not found: {source_guid}'}

            # Find target component
            tgt_guid = System.Guid(target_guid)
            tgt_obj = doc.FindObject(tgt_guid, True)
            if tgt_obj is None:
                return {'success': False, 'error': f'Target component not found: {target_guid}'}

            # Get output parameter from source
            if hasattr(src_obj, 'Params') and hasattr(src_obj.Params, 'Output'):
                if source_output >= len(src_obj.Params.Output):
                    return {'success': False, 'error': f'Invalid source output index: {source_output}'}
                src_param = src_obj.Params.Output[source_output]
            elif hasattr(src_obj, 'Output'):
                src_param = src_obj
            else:
                return {'success': False, 'error': 'Source has no output parameters'}

            # Get input parameter from target
            if hasattr(tgt_obj, 'Params') and hasattr(tgt_obj.Params, 'Input'):
                if target_input >= len(tgt_obj.Params.Input):
                    return {'success': False, 'error': f'Invalid target input index: {target_input}'}
                tgt_param = tgt_obj.Params.Input[target_input]
            elif hasattr(tgt_obj, 'Input'):
                tgt_param = tgt_obj
            else:
                return {'success': False, 'error': 'Target has no input parameters'}

            # Create connection
            tgt_param.AddSource(src_param)

            # Trigger solve
            doc.NewSolution(False)
            canvas.Refresh()

            return {
                'success': True,
                'source': {'guid': source_guid, 'output': source_output},
                'target': {'guid': target_guid, 'input': target_input}
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _disconnect_components(self, source_guid, source_output, target_guid, target_input):
        """Disconnect a wire between two components"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            # Find source and target
            src_guid = System.Guid(source_guid)
            tgt_guid = System.Guid(target_guid)

            src_obj = doc.FindObject(src_guid, True)
            tgt_obj = doc.FindObject(tgt_guid, True)

            if src_obj is None or tgt_obj is None:
                return {'success': False, 'error': 'Component not found'}

            # Get parameters
            if hasattr(src_obj, 'Params') and hasattr(src_obj.Params, 'Output'):
                src_param = src_obj.Params.Output[source_output]
            else:
                src_param = src_obj

            if hasattr(tgt_obj, 'Params') and hasattr(tgt_obj.Params, 'Input'):
                tgt_param = tgt_obj.Params.Input[target_input]
            else:
                tgt_param = tgt_obj

            # Remove connection
            tgt_param.RemoveSource(src_param)

            doc.NewSolution(False)
            canvas.Refresh()

            return {'success': True, 'message': 'Connection removed'}

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _delete_component(self, guid):
        """Delete a component from the canvas"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            obj_guid = System.Guid(guid)
            obj = doc.FindObject(obj_guid, True)

            if obj is None:
                return {'success': False, 'error': f'Component not found: {guid}'}

            doc.RemoveObject(obj, True)
            canvas.Refresh()

            return {'success': True, 'deleted_guid': guid}

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _set_component_value(self, guid, value, param_index=0):
        """Set the value of a component"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            obj_guid = System.Guid(guid)
            obj = doc.FindObject(obj_guid, True)

            if obj is None:
                return {'success': False, 'error': f'Component not found: {guid}'}

            # Handle different component types
            type_name = obj.GetType().Name

            # Number Slider
            if 'Slider' in type_name or 'GH_NumberSlider' in type_name:
                import System
                decimal_value = System.Decimal(float(value))
                try:
                    obj.SetSliderValue(decimal_value)
                except:
                    obj.Slider.Value = decimal_value

            # Panel
            elif 'Panel' in type_name:
                obj.UserText = str(value)

            # Boolean Toggle
            elif 'Toggle' in type_name or 'Boolean' in type_name:
                obj.Value = bool(value)

            # Generic parameter
            elif hasattr(obj, 'PersistentData'):
                obj.PersistentData.Clear()
                if isinstance(value, list):
                    for v in value:
                        obj.PersistentData.Append(Grasshopper.Kernel.Types.GH_Number(float(v)))
                else:
                    obj.PersistentData.Append(Grasshopper.Kernel.Types.GH_Number(float(value)))

            else:
                return {
                    'success': False,
                    'error': f'Cannot set value for component type: {type_name}'
                }

            obj.ExpireSolution(True)
            doc.NewSolution(False)
            canvas.Refresh()

            return {
                'success': True,
                'guid': guid,
                'value_set': str(value)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _move_component(self, guid, x, y):
        """Move a component to a new position"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System
            import System.Drawing as SD

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            obj_guid = System.Guid(guid)
            obj = doc.FindObject(obj_guid, True)

            if obj is None:
                return {'success': False, 'error': f'Component not found: {guid}'}

            obj.Attributes.Pivot = SD.PointF(float(x), float(y))
            canvas.Refresh()

            return {
                'success': True,
                'guid': guid,
                'position': {'x': x, 'y': y}
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _create_group(self, guids, name=None, color=None):
        """Create a group containing specified components"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System
            import System.Drawing as SD

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            # Find all components
            objects = []
            for guid_str in guids:
                obj_guid = System.Guid(guid_str)
                obj = doc.FindObject(obj_guid, True)
                if obj:
                    objects.append(obj)

            if len(objects) == 0:
                return {'success': False, 'error': 'No valid components found'}

            # Create group
            group = Grasshopper.Kernel.Special.GH_Group()

            # Set name
            if name:
                group.NickName = name

            # Set color
            if color and len(color) >= 3:
                group.Colour = SD.Color.FromArgb(color[0], color[1], color[2])

            # Add objects to group
            for obj in objects:
                group.AddObject(obj.InstanceGuid)

            # Calculate boundary
            group.ExpireBounds()

            # Add group to document
            doc.AddObject(group, False)
            canvas.Refresh()

            return {
                'success': True,
                'group_guid': str(group.InstanceGuid),
                'name': group.NickName,
                'component_count': len(objects)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _get_component_info(self, guid):
        """Get detailed information about a component"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper
            import System

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            obj_guid = System.Guid(guid)
            obj = doc.FindObject(obj_guid, True)

            if obj is None:
                return {'success': False, 'error': f'Component not found: {guid}'}

            info = {
                'success': True,
                'guid': guid,
                'name': obj.Name,
                'nickname': obj.NickName,
                'type': obj.GetType().Name,
                'category': getattr(obj, 'Category', ''),
                'subcategory': getattr(obj, 'SubCategory', ''),
                'position': {
                    'x': obj.Attributes.Pivot.X,
                    'y': obj.Attributes.Pivot.Y
                },
                'inputs': [],
                'outputs': []
            }

            # Get inputs
            if hasattr(obj, 'Params') and hasattr(obj.Params, 'Input'):
                for i, param in enumerate(obj.Params.Input):
                    info['inputs'].append({
                        'index': i,
                        'name': param.Name,
                        'nickname': param.NickName,
                        'type': param.TypeName,
                        'source_count': param.SourceCount
                    })

            # Get outputs
            if hasattr(obj, 'Params') and hasattr(obj.Params, 'Output'):
                for i, param in enumerate(obj.Params.Output):
                    info['outputs'].append({
                        'index': i,
                        'name': param.Name,
                        'nickname': param.NickName,
                        'type': param.TypeName,
                        'recipient_count': param.RecipientCount
                    })

            return info

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _new_definition(self):
        """Create a new empty Grasshopper definition"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                # Open Grasshopper first
                Rhino.RhinoApp.RunScript("_Grasshopper", False)
                canvas = Grasshopper.Instances.ActiveCanvas

            if canvas is None:
                return {'success': False, 'error': 'Could not get Grasshopper canvas'}

            # Create new document
            new_doc = Grasshopper.Kernel.GH_Document()
            canvas.Document = new_doc
            canvas.Refresh()

            return {'success': True, 'message': 'New definition created'}

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _save_definition(self, file_path):
        """Save the current Grasshopper definition to a file"""
        if not IN_RHINO:
            return {'success': False, 'error': 'Not running in Rhino'}

        try:
            import Grasshopper

            canvas = Grasshopper.Instances.ActiveCanvas
            if canvas is None:
                return {'success': False, 'error': 'No active Grasshopper canvas'}

            doc = canvas.Document
            if doc is None:
                return {'success': False, 'error': 'No Grasshopper document'}

            # Save the document
            io = Grasshopper.Kernel.GH_DocumentIO(doc)

            if file_path.lower().endswith('.ghx'):
                success = io.SaveAsXml(file_path)
            else:
                success = io.Save(file_path)

            if success:
                return {'success': True, 'path': file_path}
            else:
                return {'success': False, 'error': 'Failed to save file'}

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            }


# Global layout preferences (in-memory)
_highlighted_components = {}  # Track highlighted components for restoration
_layout_preferences = {'spacing_x': 200, 'spacing_y': 80, 'samples': 0}

# Track components created by the system (for preservation logic)
_session_created_guids = set()  # GUIDs of components created in current session
_user_component_guids = set()  # GUIDs of components that existed before session
_session_started = False  # Flag to track if session has been initialized

# Global listener instance
_listener = None


def mark_existing_components():
    """Mark all current components as user-created (call at session start)"""
    global _user_component_guids, _session_created_guids, _session_started
    _session_created_guids = set()
    _user_component_guids = set()
    _session_started = True

    if not IN_RHINO:
        return

    try:
        import Grasshopper
        canvas = Grasshopper.Instances.ActiveCanvas
        if canvas and canvas.Document:
            for obj in canvas.Document.Objects:
                _user_component_guids.add(str(obj.InstanceGuid))
            print(f"[Session] Marked {len(_user_component_guids)} existing components as user-created")
    except:
        pass


def _auto_start_session_if_needed():
    """Automatically start session if not already started (called before first component creation)"""
    global _session_started
    if not _session_started:
        print("[Session] Auto-starting session (first component creation)")
        mark_existing_components()


def get_user_component_guids():
    """Get GUIDs of user-created components"""
    return _user_component_guids.copy()


def get_session_component_guids():
    """Get GUIDs of components created in this session"""
    return _session_created_guids.copy()


def clear_session_components():
    """Remove only components created in this session, preserve user components"""
    if not IN_RHINO:
        return {'success': False, 'error': 'Not running in Rhino'}

    try:
        import Grasshopper
        import System

        canvas = Grasshopper.Instances.ActiveCanvas
        if not canvas or not canvas.Document:
            return {'success': False, 'error': 'No Grasshopper document'}

        doc = canvas.Document
        removed_count = 0

        for guid_str in list(_session_created_guids):
            try:
                guid = System.Guid(guid_str)
                obj = doc.FindObject(guid, True)
                if obj:
                    doc.RemoveObject(obj, False)
                    removed_count += 1
            except:
                pass

        _session_created_guids.clear()
        canvas.Refresh()

        print(f"[Session] Removed {removed_count} session components, preserved {len(_user_component_guids)} user components")
        return {
            'success': True,
            'removed_count': removed_count,
            'preserved_count': len(_user_component_guids)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def start_listener(host=HOST, port=PORT):
    """Start the bridge listener"""
    global _listener
    if _listener is None:
        _listener = RhinoBridgeListener(host, port)
    _listener.start()
    return _listener


def stop_listener():
    """Stop the bridge listener"""
    global _listener
    if _listener:
        _listener.stop()
        _listener = None


# Auto-start when run as script
if __name__ == '__main__':
    listener = start_listener()

    if IN_RHINO:
        print("Listener is running in background thread.")
        print("Use stop_listener() to stop.")
    else:
        print("Press Ctrl+C to stop...")
        try:
            while listener.running:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            stop_listener()
