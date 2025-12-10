"""
Rhino/Grasshopper Bridge Module
Connects to running Rhino instances via TCP socket to the bridge listener
"""

import json
import socket
from typing import Optional, Any
from pathlib import Path


class RhinoBridge:
    """Bridge to communicate with Rhino/Grasshopper via TCP listener"""

    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
        self.timeout = 30.0  # 30 second timeout for operations

    def _send_command(self, command: dict) -> dict:
        """Send a command to the Rhino listener and get response"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))

            # Send command as JSON with double newline terminator
            message = json.dumps(command) + "\n\n"
            sock.sendall(message.encode('utf-8'))

            # Receive response
            data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n\n" in data:
                    break

            sock.close()

            # Parse response
            response_text = data.decode('utf-8').strip()
            if response_text:
                return json.loads(response_text)
            else:
                return {"success": False, "error": "Empty response from Rhino"}

        except socket.timeout:
            return {"success": False, "error": "Connection timed out"}
        except ConnectionRefusedError:
            return {
                "success": False,
                "error": "Connection refused - Rhino listener not running",
                "hint": "Start Rhino and run the rhino_bridge_listener.py script"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_rhino_running(self) -> bool:
        """Check if Rhino is running and listening"""
        result = self._send_command({"command": "ping"})
        return result.get("success", False)

    def get_connection_status(self) -> dict:
        """Get current connection status"""
        result = self._send_command({"command": "status"})
        if result.get("success"):
            return {
                "host": self.host,
                "port": self.port,
                "connected": True,
                **result
            }
        else:
            return {
                "host": self.host,
                "port": self.port,
                "connected": False,
                "error": result.get("error", "Unknown error"),
                "hint": result.get("hint", "")
            }

    async def execute_python(self, code: str) -> dict:
        """
        Execute Python code in Rhino's Python environment.
        Requires Rhino to have the bridge listener running.
        """
        if not code.strip():
            return {"success": False, "error": "No code provided"}

        result = self._send_command({
            "command": "execute",
            "code": code
        })

        return result

    async def get_grasshopper_state(self) -> dict:
        """Get current state of Grasshopper canvas"""
        return self._send_command({"command": "gh_state"})

    async def load_gh_definition(self, file_path: str) -> dict:
        """Load a .gh/.ghx file into Grasshopper"""
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        if path.suffix.lower() not in [".gh", ".ghx"]:
            return {"success": False, "error": "File must be .gh or .ghx"}

        return self._send_command({
            "command": "load_gh",
            "file_path": str(path.resolve())
        })

    async def solve_definition(self) -> dict:
        """Trigger a solve of the current Grasshopper definition"""
        return self._send_command({"command": "solve"})

    async def highlight_components(self, guids: list, color: tuple) -> dict:
        """
        Highlight components on the Grasshopper canvas.

        Args:
            guids: List of component GUIDs to highlight
            color: RGB tuple (r, g, b) for highlight color
        """
        return self._send_command({
            "command": "highlight_components",
            "guids": guids,
            "color": list(color)
        })

    async def clear_highlights(self, guids: list = None) -> dict:
        """
        Clear component highlights.

        Args:
            guids: Optional list of GUIDs to clear. If None, clears all.
        """
        return self._send_command({
            "command": "clear_highlights",
            "guids": guids
        })

    # =========================================================================
    # Component Creation & Manipulation
    # =========================================================================

    async def add_component(
        self,
        name: str,
        x: float,
        y: float,
        nickname: str = None,
        category: str = None,
        subcategory: str = None,
        delay: float = 0
    ) -> dict:
        """
        Add a component to the Grasshopper canvas.

        Args:
            name: Component name (e.g., "Number Slider", "Addition", "Point")
            x: X position on canvas
            y: Y position on canvas
            nickname: Optional nickname for the component
            category: Optional category hint for disambiguation
            subcategory: Optional subcategory hint
            delay: Delay in seconds after creation for visual feedback (default: 0)

        Returns:
            {"success": True, "guid": "...", "name": "..."} or error
        """
        return self._send_command({
            "command": "add_component",
            "name": name,
            "x": x,
            "y": y,
            "nickname": nickname,
            "category": category,
            "subcategory": subcategory,
            "delay": delay
        })

    async def connect_components(
        self,
        source_guid: str,
        source_output: int,
        target_guid: str,
        target_input: int
    ) -> dict:
        """
        Connect two components with a wire.

        Args:
            source_guid: GUID of source component
            source_output: Output parameter index (0-based)
            target_guid: GUID of target component
            target_input: Input parameter index (0-based)

        Returns:
            {"success": True} or error
        """
        return self._send_command({
            "command": "connect_components",
            "source_guid": source_guid,
            "source_output": source_output,
            "target_guid": target_guid,
            "target_input": target_input
        })

    async def disconnect_components(
        self,
        source_guid: str,
        source_output: int,
        target_guid: str,
        target_input: int
    ) -> dict:
        """
        Disconnect a wire between two components.

        Args:
            source_guid: GUID of source component
            source_output: Output parameter index
            target_guid: GUID of target component
            target_input: Input parameter index

        Returns:
            {"success": True} or error
        """
        return self._send_command({
            "command": "disconnect_components",
            "source_guid": source_guid,
            "source_output": source_output,
            "target_guid": target_guid,
            "target_input": target_input
        })

    async def delete_component(self, guid: str) -> dict:
        """
        Delete a component from the canvas.

        Args:
            guid: GUID of component to delete

        Returns:
            {"success": True} or error
        """
        return self._send_command({
            "command": "delete_component",
            "guid": guid
        })

    async def set_component_value(
        self,
        guid: str,
        value: any,
        param_index: int = 0
    ) -> dict:
        """
        Set the value of a component (e.g., Number Slider, Panel, Boolean).

        Args:
            guid: GUID of component
            value: Value to set (number, string, boolean, list)
            param_index: Parameter index for multi-param components

        Returns:
            {"success": True} or error
        """
        return self._send_command({
            "command": "set_value",
            "guid": guid,
            "value": value,
            "param_index": param_index
        })

    async def move_component(self, guid: str, x: float, y: float) -> dict:
        """
        Move a component to a new position.

        Args:
            guid: GUID of component
            x: New X position
            y: New Y position

        Returns:
            {"success": True} or error
        """
        return self._send_command({
            "command": "move_component",
            "guid": guid,
            "x": x,
            "y": y
        })

    async def create_group(
        self,
        guids: list,
        name: str = None,
        color: tuple = None
    ) -> dict:
        """
        Create a group containing the specified components.

        Args:
            guids: List of component GUIDs to group
            name: Optional group name
            color: Optional RGB color tuple

        Returns:
            {"success": True, "group_guid": "..."} or error
        """
        return self._send_command({
            "command": "create_group",
            "guids": guids,
            "name": name,
            "color": list(color) if color else None
        })

    async def get_component_info(self, guid: str) -> dict:
        """
        Get detailed info about a component.

        Args:
            guid: GUID of component

        Returns:
            Component details including inputs, outputs, values
        """
        return self._send_command({
            "command": "get_component_info",
            "guid": guid
        })

    async def new_definition(self) -> dict:
        """
        Create a new empty Grasshopper definition.

        Returns:
            {"success": True} or error
        """
        return self._send_command({
            "command": "new_definition"
        })

    async def save_definition(self, file_path: str) -> dict:
        """
        Save the current Grasshopper definition to a file.

        Args:
            file_path: Path to save the .gh or .ghx file

        Returns:
            {"success": True, "path": "..."} or error
        """
        return self._send_command({
            "command": "save_definition",
            "file_path": file_path
        })


# Singleton instance
_bridge: Optional[RhinoBridge] = None


def get_bridge(host: str = "localhost", port: int = 8080) -> RhinoBridge:
    """Get or create the bridge instance"""
    global _bridge
    if _bridge is None:
        _bridge = RhinoBridge(host, port)
    return _bridge
