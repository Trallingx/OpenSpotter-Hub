#!/usr/bin/env python3
"""CLI used by Klipper shell macros to configure or trigger the Arduino valve bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import websockets


MAX_TRACKING_SPEED_MM_S = 50.0
MIN_SAMPLE_INTERVAL_S = 0.0001


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure or trigger an Arduino valve pulse through the local bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--moonraker-host", default="127.0.0.1")
    parser.add_argument("--moonraker-port", type=int, default=7125)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--valve", type=int, default=0)
    parser.add_argument("--on-ms", type=float, default=5.0)
    parser.add_argument("--off-ms", type=float, default=0.0)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--target-x", type=float)
    parser.add_argument("--target-y", type=float)
    parser.add_argument("--position-tolerance-mm", type=float, default=0.05)
    parser.add_argument("--position-timeout-s", type=float, default=5.0)
    parser.add_argument("--poll-interval-ms", type=float, default=1.0)
    parser.add_argument("--pre-fire-wait-ms", type=float, default=0.0)
    parser.add_argument("--post-fire-wait-ms", type=float, default=0.0)
    parser.add_argument(
        "--configure-only",
        action="store_true",
        help="Preload Arduino timing for Pi-MCU edge triggering without firing immediately",
    )
    parser.add_argument("--off", action="store_true", help="Compatibility no-op for pulse-only Arduino firmware")
    return parser.parse_args()


def _motion_report_state(
    base_url: str, timeout_s: float
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    url = f"{base_url}/printer/objects/query?motion_report"
    try:
        with urlopen(Request(url), timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    try:
        result = payload.get("result", {})
        status = result.get("status", {})
        motion_report = status.get("motion_report", {})
        position = motion_report.get("live_position", [0.0, 0.0, 0.0])
        velocity = motion_report.get("live_velocity", [0.0, 0.0, 0.0])
        return (
            float(position[0]),
            float(position[1]),
            float(position[2]),
        ), (
            float(velocity[0]),
            float(velocity[1]),
            float(velocity[2]),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _status_payload_state(
    payload: dict,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if not isinstance(payload, dict):
        return None

    motion_report = payload.get("motion_report")
    if isinstance(motion_report, dict):
        position = motion_report.get("live_position")
        velocity = motion_report.get("live_velocity", [0.0, 0.0, 0.0])
        if isinstance(position, list) and len(position) >= 3:
            return (
                float(position[0]),
                float(position[1]),
                float(position[2]),
            ), (
                float(velocity[0]),
                float(velocity[1]),
                float(velocity[2]),
            )

    toolhead = payload.get("toolhead")
    if isinstance(toolhead, dict):
        position = toolhead.get("position")
        if isinstance(position, list) and len(position) >= 3:
            return (
                float(position[0]),
                float(position[1]),
                float(position[2]),
            ), (0.0, 0.0, 0.0)

    return None


def _project_position(
    position: tuple[float, float, float],
    velocity: tuple[float, float, float],
    elapsed_s: float,
) -> tuple[float, float, float]:
    return (
        position[0] + velocity[0] * elapsed_s,
        position[1] + velocity[1] * elapsed_s,
        position[2] + velocity[2] * elapsed_s,
    )


def _within_target(
    position: tuple[float, float, float],
    target_x: float,
    target_y: float,
    tolerance_mm: float,
) -> bool:
    return abs(position[0] - target_x) <= tolerance_mm and abs(position[1] - target_y) <= tolerance_mm


def _effective_sample_interval_s(tolerance_mm: float, poll_interval_ms: float) -> float:
    poll_interval_s = max(MIN_SAMPLE_INTERVAL_S, poll_interval_ms / 1000.0)
    if tolerance_mm <= 0:
        return poll_interval_s

    tolerance_interval_s = max(MIN_SAMPLE_INTERVAL_S, tolerance_mm / MAX_TRACKING_SPEED_MM_S / 2.0)
    return min(poll_interval_s, tolerance_interval_s)


async def _wait_for_position_ws(
    ws_url: str,
    timeout_s: float,
    target_x: float,
    target_y: float,
    tolerance_mm: float,
    poll_interval_ms: float,
) -> tuple[float, float, float]:
    deadline = time.monotonic() + max(0.0, timeout_s)
    sample_interval_s = _effective_sample_interval_s(tolerance_mm, poll_interval_ms)
    last_state: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    last_state_time = time.monotonic()

    async with websockets.connect(ws_url, ping_interval=20) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "printer.objects.subscribe",
                    "params": {
                        "objects": {
                            "motion_report": ["live_position", "live_velocity"],
                            "toolhead": ["position", "homed_axes"],
                        }
                    },
                    "id": 1,
                }
            )
        )

        while True:
            now = time.monotonic()
            if last_state is not None:
                projected_position = _project_position(last_state[0], last_state[1], now - last_state_time)
                if _within_target(projected_position, target_x, target_y, tolerance_mm):
                    return projected_position

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=min(remaining, sample_interval_s))
            except asyncio.TimeoutError:
                continue

            try:
                payload = json.loads(message)
            except Exception:
                continue

            status = None
            method = payload.get("method")
            if method == "notify_status_update":
                params = payload.get("params", [])
                if params and isinstance(params[0], dict):
                    status = params[0]
            elif "id" in payload:
                result = payload.get("result")
                if isinstance(result, dict):
                    status = result.get("status", {})

            state = _status_payload_state(status or {})
            if state is None:
                continue

            last_state = state
            last_state_time = time.monotonic()
            if _within_target(last_state[0], target_x, target_y, tolerance_mm):
                return last_state[0]

    if last_state is None:
        raise TimeoutError(f"Moonraker did not return realtime motion updates from {ws_url}")

    x, y, z = last_state[0]
    raise TimeoutError(
        f"last seen X={x:g} Y={y:g} Z={z:g}; target X={target_x:g} Y={target_y:g} "
        f"within {tolerance_mm:g} mm"
    )


def _toolhead_position(base_url: str, timeout_s: float) -> tuple[float, float, float] | None:
    url = f"{base_url}/printer/objects/query?toolhead"
    try:
        with urlopen(Request(url), timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    try:
        result = payload.get("result", {})
        status = result.get("status", {})
        toolhead = status.get("toolhead", {})
        position = toolhead.get("position", [0.0, 0.0, 0.0])
        return float(position[0]), float(position[1]), float(position[2])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _wait_for_position(
    base_url: str,
    timeout_s: float,
    target_x: float,
    target_y: float,
    tolerance_mm: float,
    poll_interval_ms: float,
) -> tuple[float, float, float]:
    ws_url = base_url.replace("http://", "ws://", 1) + "/websocket"
    try:
        return asyncio.run(
            _wait_for_position_ws(
                ws_url=ws_url,
                timeout_s=timeout_s,
                target_x=target_x,
                target_y=target_y,
                tolerance_mm=tolerance_mm,
                poll_interval_ms=poll_interval_ms,
            )
        )
    except Exception:
        pass

    deadline = time.monotonic() + max(0.0, timeout_s)
    poll_interval_s = _effective_sample_interval_s(tolerance_mm, poll_interval_ms)
    last_state: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    last_state_time = time.monotonic()

    while True:
        now = time.monotonic()
        if last_state is not None:
            projected_position = _project_position(last_state[0], last_state[1], now - last_state_time)
            if _within_target(projected_position, target_x, target_y, tolerance_mm):
                return projected_position

        state = _motion_report_state(base_url, timeout_s)
        if state is None:
            position = _toolhead_position(base_url, timeout_s)
            if position is not None:
                state = position, (0.0, 0.0, 0.0)
        if state is not None:
            last_state = state
            last_state_time = time.monotonic()
            if _within_target(last_state[0], target_x, target_y, tolerance_mm):
                return last_state[0]

        if time.monotonic() >= deadline:
            if last_state is None:
                raise TimeoutError(f"Moonraker did not return a motion position from {base_url}")

            x, y, z = last_state[0]
            raise TimeoutError(
                f"last seen X={x:g} Y={y:g} Z={z:g}; target X={target_x:g} Y={target_y:g} "
                f"within {tolerance_mm:g} mm"
            )

        time.sleep(poll_interval_s)


def main() -> int:
    args = parse_args()
    bridge_url = f"http://{args.host}:{args.port}"
    moonraker_url = f"http://{args.moonraker_host}:{args.moonraker_port}"
    if args.off:
        url = f"{bridge_url}/off"
    else:
        if args.target_x is not None and args.target_y is not None:
            try:
                _wait_for_position(
                    base_url=moonraker_url,
                    timeout_s=args.position_timeout_s,
                    target_x=args.target_x,
                    target_y=args.target_y,
                    tolerance_mm=max(0.0, float(args.position_tolerance_mm)),
                    poll_interval_ms=args.poll_interval_ms,
                )
            except TimeoutError as exc:
                print(f"ERR arduino valve bridge position wait failed: {exc}", file=sys.stderr)
                return 1

        pre_fire_wait_s = max(0.0, float(args.pre_fire_wait_ms)) / 1000.0
        post_fire_wait_s = max(0.0, float(args.post_fire_wait_ms)) / 1000.0
        if pre_fire_wait_s > 0:
            time.sleep(pre_fire_wait_s)

        query = urlencode(
            {
                "valve": args.valve,
                "on_ms": args.on_ms,
                "off_ms": args.off_ms,
                "cycles": args.cycles,
            }
        )
        path = "configure" if args.configure_only else "fire"
        url = f"{bridge_url}/{path}?{query}"

    try:
        with urlopen(Request(url), timeout=args.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"ERR arduino valve bridge request failed: {exc}", file=sys.stderr)
        return 1

    if post_fire_wait_s > 0:
        time.sleep(post_fire_wait_s)

    if not payload.get("ok"):
        print(f"ERR arduino valve bridge rejected request: {payload}", file=sys.stderr)
        return 1

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())