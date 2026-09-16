"""
Klipper Threads
Background threads for publishing commands to Klipper and listening for status.
"""

from __future__ import annotations

import time
import queue
from typing import Optional, Tuple, Dict, Any

from PyQt6.QtCore import QThread

from services.klipper_service import KlipperService
from utils import AppSignals


class KlipperPublisher(QThread):
    """Publishes move/fire commands to Klipper off the GUI thread."""

    def __init__(self, service: KlipperService, app_signals: AppSignals = None, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.signals = app_signals
        self._queue: "queue.Queue[Tuple[str, Dict[str, Any]]]" = queue.Queue()
        self._running = False

    def enqueue_move(self, x: float, y: float, z: float, velocity: float) -> None:
        self._queue.put(("move", {"x": x, "y": y, "z": z, "velocity": velocity}))

    def enqueue_fire(self, pin: int, duration_ms: float) -> None:
        self._queue.put(("fire", {"pin": pin, "duration_ms": duration_ms}))

    def enqueue_script(self, script: str, completion_key: Optional[str] = None) -> None:
        self._queue.put(("script", {"script": script, "completion_key": completion_key}))

    def stop(self, clear_pending: bool = False) -> None:
        self._running = False
        if clear_pending:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
        # Sentinel to unblock get
        self._queue.put(("__stop__", {}))

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                cmd, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if cmd == "__stop__":
                break
            if not self.service.is_connected:
                if self.signals:
                    self.signals.error_occurred.emit("KlipperPublisher error: Klippy disconnected")
                    self.signals.connection_status_changed.emit(False, "Klippy disconnected")
                self._running = False
                break
            try:
                if cmd == "move":
                    result = self.service.move_gantry(
                        float(payload["x"]),
                        float(payload["y"]),
                        float(payload["z"]),
                        float(payload["velocity"]),
                    )
                    if not result:
                        if self.signals:
                            self.signals.error_occurred.emit("KlipperPublisher error: move command failed")
                        self._running = False
                        break
                    if self.signals:
                        self.signals.gantry_status_changed.emit("moving")
                elif cmd == "fire":
                    result = self.service.fire_valve(int(payload["pin"]), float(payload["duration_ms"]))
                    if not result:
                        if self.signals:
                            self.signals.error_occurred.emit("KlipperPublisher error: fire command failed")
                        self._running = False
                        break
                    if self.signals:
                        self.signals.valve_fired.emit(int(payload["pin"]), float(payload["duration_ms"]))
                elif cmd == "script":
                    result = self.service.send_gcode(str(payload["script"]))
                    if isinstance(result, dict) and "error" in result:
                        if self.signals:
                            self.signals.error_occurred.emit(f"KlipperPublisher error: {result['error']}")
                        self._running = False
                        break
                    if (
                        self.signals
                        and isinstance(result, dict)
                        and isinstance(result.get("id"), int)
                        and payload.get("completion_key") is not None
                    ):
                        self.signals.gcode_script_queued.emit(
                            int(result["id"]),
                            payload["completion_key"],
                        )
            except Exception as e:
                if self.signals:
                    self.signals.error_occurred.emit(f"KlipperPublisher error: {e}")
                self._running = False
                break


class KlipperListener(QThread):
    """Polls Klipper for status and emits updates off the GUI thread."""

    def __init__(self, service: KlipperService, app_signals: AppSignals = None, interval_ms: int = 500, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.signals = app_signals
        self.interval_ms = max(50, interval_ms)
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                if self.service.is_connected:
                    ws_client = getattr(self.service, "ws_client", None)
                    use_cached_status = bool(getattr(ws_client, "is_connected", False)) and hasattr(
                        self.service,
                        "get_cached_toolhead_status",
                    )
                    if use_cached_status:
                        status = self.service.get_cached_toolhead_status()
                    else:
                        status = self.service.get_toolhead_status()

                    if status.get("connected") and (not use_cached_status or status.get("cached")):
                        pos = status.get("position", {})
                        sample_time = float(status.get("sample_time") or time.monotonic())
                        position_source = str(status.get("position_source", "") or "")
                        if self.signals:
                            self.signals.gantry_position_updated.emit(
                                float(pos.get("x", 0.0)),
                                float(pos.get("y", 0.0)),
                                float(pos.get("z", 0.0)),
                            )
                            if position_source == "motion_report":
                                self.signals.gantry_position_sample_updated.emit(
                                    float(pos.get("x", 0.0)),
                                    float(pos.get("y", 0.0)),
                                    float(pos.get("z", 0.0)),
                                    sample_time,
                                )
                            self.signals.gantry_status_changed.emit("idle")
                time.sleep(self.interval_ms / 1000.0)
            except Exception as e:
                if self.signals:
                    self.signals.error_occurred.emit(f"KlipperListener error: {e}")
