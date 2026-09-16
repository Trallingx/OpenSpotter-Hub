"""
Moonraker WebSocket Client
Background WebSocket client that forwards raw Moonraker messages to a callback.
"""

import asyncio
import json
import logging
import threading
from typing import Any, Callable, Optional

import websockets


class MoonrakerWebSocketClient:
    """WebSocket client for Moonraker raw message streaming and command sending."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7125,
        timeout: float = 10.0,
        raw_message_callback: Optional[Callable[[str], None]] = None,
        status_callback: Optional[Callable[[dict], None]] = None,
        command_response_callback: Optional[Callable[[int, bool, str], None]] = None,
        headers: Optional[dict] = None,
        route_prefix: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        # Support optional route_prefix for installations that set it in moonraker.conf
        prefix = f"/{route_prefix.strip('/')}" if route_prefix else ""
        self.ws_url = f"ws://{host}:{port}{prefix}/websocket"
        self.raw_message_callback = raw_message_callback
        self.status_callback = status_callback
        self.command_response_callback = command_response_callback
        self.headers = headers or {}
        self.logger = logger or logging.getLogger("dod_system")

        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.msg_id_counter = 1
        self.status_subscription_requested = False

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connect_lock = threading.Lock()
        self._msg_id_lock = threading.Lock()

    def _next_msg_id(self) -> int:
        with self._msg_id_lock:
            msg_id = self.msg_id_counter
            self.msg_id_counter += 1
            return msg_id

    def connect(self, raw_message_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Connect to Moonraker via WebSocket and start the background listener."""
        with self._connect_lock:
            if raw_message_callback is not None:
                self.raw_message_callback = raw_message_callback

            if self.is_connected and self.websocket:
                return True

            try:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()

                future = asyncio.run_coroutine_threadsafe(self._connect_async(), self._loop)
                future.result(timeout=self.timeout)
                self.is_connected = True
                self.logger.info(f"Connected to Moonraker WebSocket at {self.host}:{self.port}")
                return True
            except Exception as exc:
                self.logger.error(f"Failed to connect to Moonraker WebSocket: {exc}")
                self.is_connected = False
                return False

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect_async(self) -> None:
        self.logger.debug(f"Connecting to WebSocket: {self.ws_url}")
        # Pass optional headers (for API keys or auth) to the websocket connect
        self.websocket = await websockets.connect(
            self.ws_url, ping_interval=20, extra_headers=self.headers
        )
        asyncio.create_task(self._listen())
        await self._subscribe_toolhead_status()

    async def _subscribe_toolhead_status(self) -> None:
        """Subscribe to Moonraker's async toolhead and motion report updates."""
        if not self.websocket:
            return

        msg_id = self._next_msg_id()
        message = {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "toolhead": ["position", "homed_axes"],
                    "motion_report": ["live_position", "live_velocity"],
                },
            },
            "id": msg_id,
        }
        await self.websocket.send(json.dumps(message))
        self.status_subscription_requested = True
        self.logger.debug(f"Requested Moonraker toolhead status subscription with id {msg_id}")

    async def _listen(self) -> None:
        try:
            async for message in self.websocket:
                # Try to parse Moonraker JSON-RPC messages and only forward
                # gcode responses (notify_gcode_response) to the callback.
                try:
                    payload = json.loads(message)
                    method = payload.get("method")
                    if method == "notify_gcode_response":
                        params = payload.get("params", [])
                        if params and isinstance(params, list):
                            self._handle_gcode_response(str(params[0]))
                        else:
                            # malformed notify, forward raw message
                            self.logger.debug(f"Moonraker malformed gcode response: {message}")
                            self._emit_raw(message)
                    elif method == "notify_status_update":
                        self._handle_status_update(payload.get("params", []))
                    elif method in {"notify_klippy_disconnected", "notify_klippy_shutdown"}:
                        self.is_connected = False
                        self.logger.warning(f"Moonraker WebSocket received: {method}")
                        self._emit_raw(f"[WS {method}]")
                    elif "id" in payload:
                        response_id = payload.get("id")
                        result = payload.get("result")
                        if isinstance(result, dict):
                            self._handle_status_payload(result.get("status", {}))
                        if isinstance(response_id, int) and self.command_response_callback:
                            ok = "error" not in payload
                            response_text = json.dumps(payload, separators=(",", ":"))
                            self.command_response_callback(response_id, ok, response_text)
                        self.logger.debug(f"Moonraker WebSocket response: {payload}")
                    else:
                        # ignore non-gcode messages to keep console focused
                        pass
                except Exception:
                    # If not JSON, ignore or forward raw as fallback
                    # but per user's request we keep console focused on gcode responses
                    pass
        except Exception as exc:
            self.is_connected = False
            self.logger.error(f"Moonraker WebSocket listener stopped: {exc}")
            self._emit_raw(f"[WS ERROR] {exc}")

    def _handle_status_update(self, params: list) -> None:
        if not params or not isinstance(params[0], dict):
            return

        self._handle_status_payload(params[0])

    def _handle_status_payload(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return

        status = {}
        motion_report = payload.get("motion_report")
        if isinstance(motion_report, dict):
            position = motion_report.get("live_position")
            if isinstance(position, list) and len(position) >= 3:
                status["position"] = position[:3]
                status["live_position"] = position[:3]
                status["position_source"] = "motion_report"

        toolhead = payload.get("toolhead")
        if isinstance(toolhead, dict):
            if "position" not in status:
                position = toolhead.get("position")
                if isinstance(position, list) and len(position) >= 3:
                    status["position"] = position[:3]
                    status["position_source"] = "toolhead"

            if "homed_axes" in toolhead:
                status["homed_axes"] = toolhead.get("homed_axes", "")

        if status and self.status_callback:
            self.status_callback(status)

    def _emit_raw(self, message: str) -> None:
        self.logger.debug(f"Moonraker WS raw: {message}")
        if self.raw_message_callback:
            self.raw_message_callback(message)

    def send_gcode(self, script: str) -> dict[str, Any]:
        """Send a gcode command over the WebSocket and return immediately."""
        if not self.is_connected or not self.websocket or not self._loop:
            return {"error": "Not connected to Moonraker WebSocket"}

        try:
            msg_id = self._next_msg_id()

            message = {
                "jsonrpc": "2.0",
                "method": "printer.gcode.script",
                "params": {"script": script},
                "id": msg_id,
            }

            self.logger.debug(f"Sending gcode via WebSocket: {self._script_summary(script)}")
            future = asyncio.run_coroutine_threadsafe(
                self.websocket.send(json.dumps(message)),
                self._loop,
            )
            future.result(timeout=self.timeout)
            result = {"queued": True, "transport": "websocket", "id": msg_id}
            self.logger.debug(f"Moonraker WebSocket send response: {result}")
            return result
        except Exception as exc:
            result = {"error": str(exc)}
            self.logger.debug(f"Moonraker WebSocket send response: {result}")
            return result

    def disconnect(self) -> bool:
        """Disconnect from Moonraker and stop the background loop."""
        self.is_connected = False

        try:
            if self.websocket and self._loop:
                future = asyncio.run_coroutine_threadsafe(self.websocket.close(), self._loop)
                future.result(timeout=self.timeout)
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=self.timeout)
        except Exception:
            pass

        self.raw_message_callback = None
        self.websocket = None
        self._loop = None
        self._thread = None
        self.status_subscription_requested = False

        self.logger.debug("Moonraker WebSocket disconnected")

        return True

    def _handle_gcode_response(self, gcode_text: str) -> None:
        if self._is_ignored_gcode_response(gcode_text):
            return
        self.logger.debug(f"Moonraker gcode response: {gcode_text}")
        self._emit_raw(gcode_text)

    @staticmethod
    def _is_ignored_gcode_response(gcode_text: str) -> bool:
        normalized = str(gcode_text).strip()
        if normalized.startswith("//"):
            normalized = normalized[2:].strip()
        return normalized == "SPOTTER_SHOOT_DONE"

    @staticmethod
    def _script_summary(script: str) -> str:
        lines = [line.strip() for line in str(script).splitlines() if line.strip()]
        if not lines:
            return "<empty>"
        if len(lines) == 1:
            return lines[0]
        return f"{len(lines)} line script; first={lines[0]}"
