"""
Klipper/Moonraker Service
Interface to Klipper firmware via Moonraker API for motion control and valve firing.
"""

import logging
import threading
import time
from pathlib import PurePosixPath
from typing import Optional, Dict, Any
from urllib.parse import quote, urljoin
import requests
from models import Point3D
from .moonraker_websocket import MoonrakerWebSocketClient
from .valve_macro_commands import build_valve_fire_blocking_command


class MoonrakerClient:
    """
    Client for communicating with Moonraker API (Klipper host interface).
    Handles REST API calls for G-code execution, file management, and status queries.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7125,
        timeout: float = 10.0,
        app_signals=None,
        headers: Optional[Dict[str, str]] = None,
        route_prefix: Optional[str] = None,
        api_base: str = "/api",
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize Moonraker client.

        Args:
            host: Moonraker host address (e.g., "192.168.1.100" or "localhost")
            port: Moonraker API port (default 7125)
            timeout: HTTP request timeout in seconds
            app_signals: Optional AppSignals instance for emitting connection events
        """
        self.host = host
        self.port = port
        # Support optional route prefix (see Moonraker's `route_prefix` option)
        prefix = f"/{route_prefix.strip('/')}" if route_prefix else ""
        self.api_base = api_base
        self.base_url = f"http://{host}:{port}{prefix}{self.api_base}"
        self.timeout = timeout
        self.is_connected = False
        self.current_position = Point3D(0, 0, 0)
        self.printer_state = "disconnected"
        self.app_signals = app_signals
        self.headers = headers or {}
        self.logger = logger or logging.getLogger("dod_system")
        self._connect_lock = threading.Lock()
        self._status_condition = threading.Condition()
        self._cached_homed_axes = ""
        self._cached_toolhead_status_at = 0.0
        self._cached_position_source = ""
        self.ws_client = MoonrakerWebSocketClient(
            host=host,
            port=port,
            timeout=timeout,
            raw_message_callback=self._on_ws_message,
            status_callback=self._on_ws_status_update,
            command_response_callback=self._on_ws_command_response,
            headers=self.headers,
            route_prefix=route_prefix,
            logger=self.logger,
        )

    def connect(self) -> bool:
        """
        Connect to Moonraker and verify API is available.

        Returns:
            True if connection successful, False otherwise
        """
        with self._connect_lock:
            try:
                response = requests.get(
                    urljoin(self.base_url, "server/info"),
                    timeout=self.timeout,
                    headers=self.headers,
                )
                if response.status_code == 200:
                    self.is_connected = True
                    msg = f"Moonraker at {self.host}:{self.port}"
                    self.logger.info(f"Moonraker REST API reachable at {msg}")
                    websocket_ok = self.ws_client.connect(self._on_ws_message)
                    if not websocket_ok:
                        self.logger.warning("Moonraker REST is reachable but WebSocket connect failed")
                    if self.app_signals:
                        self.app_signals.connection_status_changed.emit(True, msg)
                    return True
                else:
                    msg = f"Moonraker returned status {response.status_code}"
                    self.logger.error(msg)
                    self.is_connected = False
                    if self.app_signals:
                        self.app_signals.connection_status_changed.emit(False, msg)
                    return False
            except requests.exceptions.ConnectionError:
                msg = f"Failed to connect to Moonraker at {self.host}:{self.port}"
                self.logger.error(msg)
                self.is_connected = False
                if self.app_signals:
                    self.app_signals.connection_status_changed.emit(False, msg)
                return False
            except Exception as e:
                msg = f"Connection error: {e}"
                self.logger.error(msg)
                self.is_connected = False
                if self.app_signals:
                    self.app_signals.connection_status_changed.emit(False, msg)
                return False

    def get_server_info(self) -> Dict[str, Any]:
        """
        Get server info including available components and versions.
        Useful for debugging API endpoints.

        Returns:
            Server info dict
        """
        try:
            response = requests.get(
                urljoin(self.base_url, "server/info"),
                timeout=self.timeout,
                headers=self.headers,
            )
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.debug(f"Moonraker server/info returned HTTP {response.status_code}")
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            self.logger.debug(f"Failed to fetch Moonraker server/info: {e}")
            return {"error": str(e)}

    def _response_payload(self, response: requests.Response) -> Any:
        """Return Moonraker's JSON result wrapper when present."""
        try:
            payload = response.json()
        except ValueError:
            return response.text
        if isinstance(payload, dict) and "result" in payload:
            return payload.get("result")
        return payload

    def list_file_roots(self) -> Any:
        """Return Moonraker file roots and their permissions."""
        if not self.is_connected:
            self.logger.warning("Pi file editor root request skipped: not connected to Moonraker")
            return {"error": "Not connected to Moonraker"}

        try:
            self.logger.info("Pi file editor requesting Moonraker file roots")
            response = requests.get(
                urljoin(self.base_url, "server/files/roots"),
                timeout=self.timeout,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                payload = self._response_payload(response)
                count = len(payload) if isinstance(payload, list) else "unknown"
                self.logger.info(f"Pi file editor loaded {count} Moonraker file root(s)")
                self.logger.debug(f"Moonraker file roots response: {payload}")
                return payload
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker file roots request failed: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(f"Moonraker file roots request failed: {e}")
            return {"error": str(e)}

    def list_files(self, root: str = "config") -> Any:
        """Return files under a Moonraker root, recursively."""
        if not self.is_connected:
            self.logger.warning(f"Pi file editor list request skipped for {root}: not connected to Moonraker")
            return {"error": "Not connected to Moonraker"}

        try:
            self.logger.info(f"Pi file editor requesting file list for root '{root}'")
            response = requests.get(
                urljoin(self.base_url, "server/files/list"),
                params={"root": root},
                timeout=self.timeout,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                payload = self._response_payload(response)
                count = len(payload) if isinstance(payload, list) else "unknown"
                self.logger.info(f"Pi file editor loaded {count} file(s) from root '{root}'")
                self.logger.debug(f"Moonraker file list response for {root}: {payload}")
                return payload
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker file list request failed for root {root}: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(f"Moonraker file list request failed for root {root}: {e}")
            return {"error": str(e)}

    def download_file(self, root: str, remote_path: str) -> Dict[str, Any]:
        """Download a text file from a Moonraker file root."""
        if not self.is_connected:
            self.logger.warning(
                f"Pi file editor download skipped for {root}/{remote_path}: not connected to Moonraker"
            )
            return {"error": "Not connected to Moonraker"}

        encoded_path = quote(remote_path.strip("/"), safe="/")
        try:
            self.logger.info(f"Pi file editor downloading {root}/{remote_path}")
            response = requests.get(
                urljoin(self.base_url, f"server/files/{root}/{encoded_path}"),
                timeout=self.timeout,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                self.logger.info(
                    f"Pi file editor downloaded {root}/{remote_path} ({len(response.text)} chars)"
                )
                return {"content": response.text}
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker file download failed for {root}/{remote_path}: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(
                f"Moonraker file download failed for {root}/{remote_path}: {e}"
            )
            return {"error": str(e)}

    def upload_file_content(
        self,
        root: str,
        remote_path: str,
        content: str | bytes,
    ) -> Dict[str, Any]:
        """Upload in-memory content to a Moonraker file root."""
        if not self.is_connected:
            self.logger.warning(
                f"Pi file editor upload skipped for {root}/{remote_path}: not connected to Moonraker"
            )
            return {"error": "Not connected to Moonraker"}

        target = PurePosixPath(remote_path.strip("/"))
        if not target.name:
            self.logger.error("Pi file editor upload failed: remote file path is empty")
            return {"error": "Remote file path is empty"}

        data = {"root": root}
        parent = str(target.parent)
        if parent and parent != ".":
            data["path"] = parent

        payload = content.encode("utf-8") if isinstance(content, str) else content
        try:
            self.logger.info(
                f"Pi file editor uploading {root}/{remote_path} ({len(payload)} bytes)"
            )
            files = {"file": (target.name, payload)}
            response = requests.post(
                urljoin(self.base_url, "server/files/upload"),
                data=data,
                files=files,
                timeout=self.timeout * 2,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                payload_response = self._response_payload(response)
                self.logger.info(f"Pi file editor uploaded {root}/{remote_path}")
                self.logger.debug(f"Moonraker file upload response: {payload_response}")
                return {"result": payload_response}
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker file upload failed for {root}/{remote_path}: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(
                f"Moonraker file upload failed for {root}/{remote_path}: {e}"
            )
            return {"error": str(e)}

    def get_machine_system_info(self) -> Dict[str, Any]:
        """Return Moonraker host system info, including allowed services."""
        if not self.is_connected:
            self.logger.warning("Pi file editor system info request skipped: not connected to Moonraker")
            return {"error": "Not connected to Moonraker"}

        try:
            self.logger.info("Pi file editor requesting Moonraker machine system info")
            response = requests.get(
                urljoin(self.base_url, "machine/system_info"),
                timeout=self.timeout,
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                payload = self._response_payload(response)
                if isinstance(payload, dict):
                    system_info = payload.get("system_info", payload)
                    services = system_info.get("available_services", [])
                    self.logger.info(
                        f"Pi file editor loaded machine system info with {len(services)} authorized service(s)"
                    )
                self.logger.debug(f"Moonraker machine system info response: {payload}")
                return payload if isinstance(payload, dict) else {"result": payload}
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker system info request failed: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(f"Moonraker system info request failed: {e}")
            return {"error": str(e)}

    def manage_service(self, service: str, action: str) -> Dict[str, Any]:
        """Start, stop, or restart a Moonraker-authorized system service."""
        if action not in {"start", "stop", "restart"}:
            self.logger.error(f"Pi file editor rejected unsupported service action: {action}")
            return {"error": f"Unsupported service action: {action}"}
        if not self.is_connected:
            self.logger.warning(
                f"Pi file editor service {action} skipped for {service}: not connected to Moonraker"
            )
            return {"error": "Not connected to Moonraker"}

        try:
            self.logger.info(f"Pi file editor requesting service {action}: {service}")
            response = requests.post(
                urljoin(self.base_url, f"machine/services/{action}"),
                json={"service": service},
                timeout=min(self.timeout, 5.0),
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                payload = self._response_payload(response)
                self.logger.info(f"Moonraker service {action} accepted: {service}")
                self.logger.debug(f"Moonraker service {action} response: {payload}")
                return {"result": payload}
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker service {action} failed for {service}: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(f"Moonraker service {action} failed for {service}: {e}")
            return {"error": str(e)}

    def restart_klipper(self) -> Dict[str, Any]:
        """Request a Klipper host restart through Moonraker."""
        if not self.is_connected:
            self.logger.warning("Pi file editor Klipper restart skipped: not connected to Moonraker")
            return {"error": "Not connected to Moonraker"}

        try:
            self.logger.info("Pi file editor requesting Klipper restart")
            response = requests.post(
                urljoin(self.base_url, "printer/restart"),
                timeout=min(self.timeout, 5.0),
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                payload = self._response_payload(response)
                self.logger.info("Moonraker accepted Klipper restart request")
                self.logger.debug(f"Moonraker Klipper restart response: {payload}")
                return {"result": payload}
            error = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"Moonraker Klipper restart failed: {error}")
            return {"error": error}
        except Exception as e:
            self.logger.error(f"Moonraker Klipper restart failed: {e}")
            return {"error": str(e)}

    def _on_ws_message(self, message: str) -> None:
        """Forward raw Moonraker WebSocket messages to the console."""
        if self.app_signals:
            self.app_signals.macro_response_received.emit(message)

    def _on_ws_status_update(self, status: Dict[str, Any]) -> None:
        """Handle subscribed Moonraker toolhead status updates."""
        sample_time = time.monotonic()
        position_source = str(status.get("position_source", "") or "")
        position = status.get("live_position")
        if isinstance(position, list) and len(position) >= 3:
            position_source = "motion_report"
        else:
            position = status.get("position")
            if not position_source:
                position_source = "toolhead"
        if isinstance(position, list) and len(position) >= 3:
            x, y, z = float(position[0]), float(position[1]), float(position[2])
            self.current_position = Point3D(x, y, z)
            self._cached_position_source = position_source
            if self.app_signals:
                self.app_signals.gantry_position_updated.emit(x, y, z)
                if position_source == "motion_report":
                    self.app_signals.gantry_position_sample_updated.emit(x, y, z, sample_time)
        if "homed_axes" in status:
            self._cached_homed_axes = str(status.get("homed_axes", ""))

        with self._status_condition:
            self._cached_toolhead_status_at = sample_time
            self._status_condition.notify_all()

    def _on_ws_command_response(self, response_id: int, ok: bool, response_text: str) -> None:
        """Forward JSON-RPC command completion ids for queued G-code tracking."""
        if self.app_signals:
            self.app_signals.gcode_script_completed.emit(response_id, ok, response_text)

    def get_cached_toolhead_status(self) -> Dict[str, Any]:
        """Return the latest WebSocket toolhead status without a blocking REST query."""
        with self._status_condition:
            return {
                "connected": bool(self.is_connected),
                "position": {
                    "x": self.current_position.x,
                    "y": self.current_position.y,
                    "z": self.current_position.z,
                },
                "homed_axes": self._cached_homed_axes,
                "cached": self._cached_toolhead_status_at > 0,
                "sample_time": self._cached_toolhead_status_at,
                "position_source": self._cached_position_source,
            }

    def wait_for_homed_axes(self, required_axes: set[str], timeout: float) -> Dict[str, Any]:
        """Wait briefly for the WebSocket status cache to contain required homed axes."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        required = {axis.lower() for axis in required_axes}

        with self._status_condition:
            while True:
                homed_axes = set(self._cached_homed_axes.lower())
                if required <= homed_axes or time.monotonic() >= deadline:
                    return {
                        "connected": bool(self.is_connected),
                        "position": {
                            "x": self.current_position.x,
                            "y": self.current_position.y,
                            "z": self.current_position.z,
                        },
                        "homed_axes": self._cached_homed_axes,
                        "cached": self._cached_toolhead_status_at > 0,
                        "sample_time": self._cached_toolhead_status_at,
                        "position_source": self._cached_position_source,
                    }

                remaining = deadline - time.monotonic()
                self._status_condition.wait(timeout=max(0.0, remaining))

    def disconnect(self) -> bool:
        """Disconnect from Moonraker and close the WebSocket client."""
        self.is_connected = False
        with self._status_condition:
            self._status_condition.notify_all()
        try:
            self.ws_client.disconnect()
        except Exception as exc:
            self.logger.debug(f"Moonraker disconnect cleanup failed: {exc}")
        return True

    def get_toolhead_status(self) -> Dict[str, Any]:
        """Return toolhead status, including position and homed axes, when available."""
        if not self.is_connected:
            return {"connected": False, "position": {"x": 0, "y": 0, "z": 0}, "homed_axes": ""}

        try:
            response = requests.get(
                urljoin(self.base_url, "printer/objects/query?toolhead"),
                timeout=self.timeout,
                headers=self.headers,
            )

            if response.status_code != 200:
                return {"connected": False, "error": f"HTTP {response.status_code}"}

            data = response.json().get("result", {}).get("status", {})
            toolhead = data.get("toolhead", {})
            position = toolhead.get("position", [0, 0, 0])
            homed_axes = str(toolhead.get("homed_axes", ""))

            x, y, z = position[0], position[1], position[2]
            self.current_position = Point3D(x, y, z)

            return {
                "connected": True,
                "position": {"x": x, "y": y, "z": z},
                "homed_axes": homed_axes,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def send_gcode(self, script: str) -> Dict[str, Any]:
        """
        Send G-code script to Klipper via Moonraker.

        Args:
            script: G-code script to execute (e.g., "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0 POST_FIRE_WAIT=0 TRIGGER_MODE=mcu")

        Returns:
            Response dict from Moonraker
        """
        try:
            if self.ws_client.is_connected:
                result = self.ws_client.send_gcode(script)
                self.logger.debug(f"Moonraker send_gcode response: {result}")
                return result

            if not self.is_connected:
                self.logger.warning("Attempted to send G-code while disconnected from Moonraker")
                result = {"error": "Not connected to Moonraker"}
                self.logger.debug(f"Moonraker send_gcode response: {result}")
                return result

            payload = {"script": script}
            endpoint = urljoin(self.base_url, "printer/gcode/script")
            self.logger.debug(f"Trying gcode endpoint: {endpoint}")
            self.logger.debug(f"Payload: {payload}")

            response = requests.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
                headers=self.headers,
            )

            self.logger.debug(f"Response status: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                self.logger.debug(f"Moonraker send_gcode response: {result}")
                return result
            error_message = f"HTTP {response.status_code}: {response.text}"
            self.logger.error(f"G-code request failed: {error_message}")
            result = {"error": error_message}
            self.logger.debug(f"Moonraker send_gcode response: {result}")
            return result

        except Exception as e:
            self.logger.error(f"G-code request failed: {e}")
            result = {"error": str(e)}
            self.logger.debug(f"Moonraker send_gcode response: {result}")
            return result

    def fire_valve(self, valve_id: int, duration_ms: float) -> bool:
        """
        Fire a valve by executing the stationary valve macro in Klipper.

        Args:
            valve_id: Valve ID (0-3 typically)
            duration_ms: Pulse duration in milliseconds

        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected:
            self.logger.warning("Cannot fire valve: not connected to Moonraker")
            return False

        try:
            duration = 5.0 if duration_ms is None else float(duration_ms)
            if duration <= 0:
                self.logger.error("Valve fire failed: duration_ms must be greater than 0")
                return False

            script = build_valve_fire_blocking_command(valve_id, duration)
            result = self.send_gcode(script)
            
            if "error" not in result:
                self.logger.info(f"Fired valve {valve_id} with SHOOT for {duration}ms")
                return True
            else:
                self.logger.error(f"Valve fire failed: {result.get('error')}")
                return False
        except Exception as e:
            self.logger.error(f"Exception firing valve: {e}")
            return False

    def move_gantry(
        self, x: float, y: float, z: float, velocity: float = 50.0
    ) -> bool:
        """
        Move gantry to specified position using G-code.

        Args:
            x: Target X position (mm)
            y: Target Y position (mm)
            z: Target Z position (mm)
            velocity: Movement velocity (mm/s)

        Returns:
            True if move initiated, False otherwise
        """
        if not self.is_connected:
            return False

        try:
            # Generate G-code move command
            script = f"G0 X{x:.1f} Y{y:.1f} Z{z:.1f} F{velocity*60:.0f}"
            result = self.send_gcode(script)
            
            if "error" not in result:
                self.logger.info(f"Queued gantry move to X={x:.1f} Y={y:.1f} Z={z:.1f}")
                return True
            else:
                self.logger.error(f"Move failed: {result.get('error')}")
                return False
        except Exception as e:
            self.logger.error(f"Exception moving gantry: {e}")
            return False

    def get_position(self) -> Optional[Point3D]:
        """
        Get current gantry position from Klipper status.

        Returns:
            Point3D with current position or None if unavailable
        """
        if not self.is_connected:
            return None

        try:
            # Query printer objects for toolhead position via HTTP
            # This returns the actual X, Y, Z position
            response = requests.get(
                urljoin(self.base_url, "printer/objects/query?toolhead"),
                timeout=self.timeout,
                headers=self.headers,
            )

            self.logger.debug(f"Position query status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                self.logger.debug(f"Position response: {data}")

                # Navigate: result.status.toolhead.position -> [x, y, z]
                try:
                    result = data.get("result", {})
                    status = result.get("status", {})
                    toolhead = status.get("toolhead", {})
                    position = toolhead.get("position", [0, 0, 0])

                    x, y, z = position[0], position[1], position[2]
                    self.current_position = Point3D(x, y, z)
                    self.logger.debug(f"Got position: X={x:.2f} Y={y:.2f} Z={z:.2f}")
                    return self.current_position
                except (KeyError, IndexError, TypeError) as e:
                    self.logger.debug(f"Failed to parse position: {e}")
                    self.logger.debug(f"Full response: {data}")
                    return None
            else:
                self.logger.debug(f"Position query failed: HTTP {response.status_code}")
                return None
        except Exception as e:
            self.logger.debug(f"Exception querying position: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive Klipper printer status.

        Returns:
            Dictionary with printer state, position, temperatures, etc.
        """
        if not self.is_connected:
            return {
                "connected": False,
                "state": "disconnected",
                "position": {"x": 0, "y": 0, "z": 0},
                "homed_axes": "",
            }

        try:
            response = requests.get(
                urljoin(self.base_url, "printer/info"),
                timeout=self.timeout,
                headers=self.headers,
            )
            if response.status_code == 200:
                info = response.json().get("result", {})
                state = info.get("state", "unknown")
                self.printer_state = state

                toolhead = self.get_toolhead_status()
                pos = toolhead.get(
                    "position",
                    {"x": self.current_position.x, "y": self.current_position.y, "z": self.current_position.z},
                )
                homed_axes = toolhead.get("homed_axes", "")
                
                return {
                    "connected": True,
                    "state": state,
                    "message": info.get("state_message", ""),
                    "position": {
                        "x": pos.get("x", self.current_position.x),
                        "y": pos.get("y", self.current_position.y),
                        "z": pos.get("z", self.current_position.z),
                    },
                    "homed_axes": homed_axes,
                    "uptime": info.get("uptime", 0),
                }
            else:
                return {"connected": False, "error": response.text, "homed_axes": ""}
        except Exception as e:
            return {"connected": False, "error": str(e), "homed_axes": ""}

    def upload_file(self, local_path: str, remote_filename: str) -> bool:
        """
        Upload a G-code file to Moonraker.

        Args:
            local_path: Local file path
            remote_filename: Remote filename (stored on Pi)

        Returns:
            True if upload successful
        """
        if not self.is_connected:
            return False

        try:
            with open(local_path, "rb") as f:
                files = {"file": (remote_filename, f)}
                response = requests.post(
                    urljoin(self.base_url, "files/upload"),
                    files=files,
                    timeout=self.timeout * 2,
                    headers=self.headers,
                )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"File upload failed: {e}")
            return False

    def start_print(self, filename: str) -> bool:
        """
        Start a print job.

        Args:
            filename: Filename to print (from Moonraker file list)

        Returns:
            True if print started
        """
        if not self.is_connected:
            return False

        try:
            script = f"PRINT_START FILE={filename}"
            result = self.send_gcode(script)
            return "error" not in result
        except Exception as e:
            self.logger.error(f"Failed to start print: {e}")
            return False

    def pause_print(self) -> bool:
        """Pause the current print."""
        if not self.is_connected:
            return False
        return self._post_printer_control("printer/print/pause", fallback_gcode="PAUSE")

    def resume_print(self) -> bool:
        """Resume a paused print."""
        if not self.is_connected:
            return False
        return self._post_printer_control("printer/print/resume", fallback_gcode="RESUME")

    def cancel_print(self) -> bool:
        """Cancel the current print."""
        if not self.is_connected:
            return False
        return self._post_printer_control("printer/print/cancel", fallback_gcode="CANCEL_PRINT")

    def _post_printer_control(self, endpoint_path: str, fallback_gcode: Optional[str] = None) -> bool:
        """Call a Moonraker printer-control endpoint, optionally falling back to G-code."""
        try:
            response = requests.post(
                urljoin(self.base_url, endpoint_path),
                timeout=min(self.timeout, 2.0),
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                self.logger.debug(f"Moonraker control request succeeded: {endpoint_path}")
                return True
            self.logger.error(
                f"Moonraker control request failed: {endpoint_path} "
                f"HTTP {response.status_code}: {response.text}"
            )
        except Exception as e:
            self.logger.error(f"Moonraker control request failed: {endpoint_path}: {e}")

        if fallback_gcode:
            result = self.send_gcode(fallback_gcode)
            return "error" not in result
        return False

    def emergency_stop(self) -> bool:
        """Request a Moonraker emergency stop without queueing it behind G-code."""
        if not self.is_connected:
            return False

        endpoint = urljoin(self.base_url, "printer/emergency_stop")
        try:
            response = requests.post(
                endpoint,
                timeout=min(self.timeout, 2.0),
                headers=self.headers,
            )
            if 200 <= response.status_code < 300:
                self.logger.warning("Moonraker emergency stop requested")
                self.is_connected = False
                if self.app_signals:
                    self.app_signals.connection_status_changed.emit(False, "Klipper emergency stop requested")
                return True

            self.logger.error(f"Emergency stop request failed: HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.logger.error(f"Emergency stop request failed: {e}")

        result = self.send_gcode("M112")
        return "error" not in result

    def __repr__(self):
        return (
            f"MoonrakerClient(host={self.host}:{self.port}, "
            f"connected={self.is_connected}, state={self.printer_state})"
        )


# Legacy name for backward compatibility
class KlipperService(MoonrakerClient):
    """Backward-compatible alias for MoonrakerClient."""
    pass
