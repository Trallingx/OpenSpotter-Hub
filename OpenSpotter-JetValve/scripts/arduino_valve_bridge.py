#!/usr/bin/env python3
"""
Persistent Pi-side HTTP bridge for the Arduino valve controller.

The bridge keeps the Arduino USB serial port open and exposes a localhost
endpoint that Klipper shell macros can call at each shot.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse


TICKS_PER_MS = 10.0  # Arduino sketch uses 0.1 ms timing ticks.


class ArduinoValveBridge:
    """Serial command bridge for the Arduino valve controller firmware."""

    def __init__(
        self,
        serial_port: str,
        baud: int,
        supported_valves: set[int],
        min_ms: float,
        max_cycles: int,
        ready_delay_s: float,
    ) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required. Install Debian package python3-serial for /usr/bin/python3, "
                "or run this bridge with a venv Python that has pyserial installed."
            ) from exc

        self.serial_port = serial_port
        self.baud = baud
        self.supported_valves = supported_valves
        self.min_ms = min_ms
        self.max_cycles = max_cycles
        self._lock = threading.Lock()
        self._serial = serial.Serial(serial_port, baudrate=baud, timeout=0, write_timeout=1.0)
        if ready_delay_s > 0:
            time.sleep(ready_delay_s)

    def _validate_request(self, valve: int, on_ms: float, off_ms: float, cycles: int) -> None:
        if valve not in self.supported_valves:
            raise ValueError(f"VALVE={valve} is not supported by the configured Arduino pin map")
        if on_ms < self.min_ms:
            raise ValueError(f"ON_MS must be at least {self.min_ms:g} ms")
        if off_ms < 0:
            raise ValueError("OFF_MS must be at least 0 ms")
        if cycles < 1 or cycles > self.max_cycles:
            raise ValueError(f"CYCLES must be between 1 and {self.max_cycles}")

    def configure_trigger(self, valve: int, on_ms: float, off_ms: float, cycles: int) -> dict[str, Any]:
        """Preload timing used when the Arduino is triggered by the Pi MCU GPIO edge."""
        self._validate_request(valve, on_ms, off_ms, cycles)
        on_ticks = self._ms_to_ticks(on_ms)
        off_ticks = self._ms_to_ticks(off_ms)
        commands = [f"V:{int(valve)}", f"O:{on_ticks}", f"P:{off_ticks}", f"C:{int(cycles)}"]

        with self._lock:
            for command in commands:
                self._write_line(command)

        return {
            "ok": True,
            "mode": "mcu_trigger",
            "valve": valve,
            "on_ms": on_ms,
            "off_ms": off_ms,
            "cycles": cycles,
            "serial_commands": commands,
        }

    def fire(self, valve: int, on_ms: float, off_ms: float, cycles: int) -> dict[str, Any]:
        """Send timing parameters and an immediate USB serial trigger to the Arduino."""
        self._validate_request(valve, on_ms, off_ms, cycles)
        on_ticks = self._ms_to_ticks(on_ms)
        off_ticks = self._ms_to_ticks(off_ms)
        commands = [f"V:{int(valve)}", f"O:{on_ticks}", f"P:{off_ticks}", f"K:{int(cycles)}"]

        with self._lock:
            for command in commands:
                self._write_line(command)

        return {
            "ok": True,
            "valve": valve,
            "on_ms": on_ms,
            "off_ms": off_ms,
            "cycles": cycles,
            "serial_commands": commands,
        }

    def off(self) -> dict[str, Any]:
        """Keep the endpoint for compatibility."""
        return {"ok": True, "command": "noop"}

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "serial_port": self.serial_port,
            "baud": self.baud,
            "supported_valves": sorted(self.supported_valves),
            "min_ms": self.min_ms,
            "max_cycles": self.max_cycles,
        }

    def close(self) -> None:
        with self._lock:
            self._serial.close()

    def _write_line(self, command: str) -> None:
        line = f"{command}\n".encode("ascii")
        self._serial.write(line)
        self._serial.flush()

    def _ms_to_ticks(self, value_ms: float) -> int:
        return max(1, int(round(float(value_ms) * TICKS_PER_MS)))


def _query_value(params: dict[str, list[str]], name: str, default: str) -> str:
    values = params.get(name)
    if not values:
        return default
    return values[0]


def _handler_factory(bridge: ArduinoValveBridge):
    class ValveBridgeHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            self._handle(parsed.path, params)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length > 0 else b""
            params: dict[str, list[str]] = parse_qs(parsed.query)
            if body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                    for key, value in payload.items():
                        params[key] = [str(value)]
                except json.JSONDecodeError:
                    self._json_response(400, {"ok": False, "error": "invalid JSON body"})
                    return
            self._handle(parsed.path, params)

        def log_message(self, fmt: str, *args: Any) -> None:
            logging.info(fmt, *args)

        def _handle(self, path: str, params: dict[str, list[str]]) -> None:
            try:
                if path == "/fire":
                    result = bridge.fire(
                        valve=int(_query_value(params, "valve", "0")),
                        on_ms=float(_query_value(params, "on_ms", "5")),
                        off_ms=float(_query_value(params, "off_ms", "0")),
                        cycles=int(_query_value(params, "cycles", "1")),
                    )
                    self._json_response(200, result)
                    return
                if path == "/configure":
                    result = bridge.configure_trigger(
                        valve=int(_query_value(params, "valve", "0")),
                        on_ms=float(_query_value(params, "on_ms", "5")),
                        off_ms=float(_query_value(params, "off_ms", "0")),
                        cycles=int(_query_value(params, "cycles", "1")),
                    )
                    self._json_response(200, result)
                    return
                if path == "/off":
                    self._json_response(200, bridge.off())
                    return
                if path == "/status":
                    self._json_response(200, bridge.status())
                    return
                self._json_response(404, {"ok": False, "error": f"unknown path: {path}"})
            except ValueError as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                logging.exception("Arduino valve bridge request failed")
                self._json_response(500, {"ok": False, "error": str(exc)})

        def _json_response(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ValveBridgeHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Arduino valve HTTP bridge on the Pi")
    parser.add_argument("--serial-port", required=True, help="Arduino serial path, preferably /dev/serial/by-id/...")
    parser.add_argument("--baud", type=int, default=9600, help="Arduino serial baud rate")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    parser.add_argument("--valves", default="0,1", help="Comma-separated supported valve ids for current Arduino firmware")
    parser.add_argument("--min-ms", type=float, default=2.0, help="Minimum allowed ON_MS")
    parser.add_argument("--max-cycles", type=int, default=1000, help="Maximum allowed cycles per trigger")
    parser.add_argument("--ready-delay-s", type=float, default=2.0, help="Delay after opening serial to allow Arduino reset")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(message)s")
    valves = {int(part.strip()) for part in args.valves.split(",") if part.strip()}
    bridge = ArduinoValveBridge(
        serial_port=args.serial_port,
        baud=args.baud,
        supported_valves=valves,
        min_ms=args.min_ms,
        max_cycles=args.max_cycles,
        ready_delay_s=args.ready_delay_s,
    )
    server = ThreadingHTTPServer((args.host, args.port), _handler_factory(bridge))
    logging.info("Arduino valve bridge listening on http://%s:%d", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Stopping Arduino valve bridge")
    finally:
        server.server_close()
        bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
