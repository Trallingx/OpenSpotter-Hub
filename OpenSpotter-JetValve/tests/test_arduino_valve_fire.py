from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "arduino_valve_fire.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("arduino_valve_fire_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_motion_report_state_uses_moonraker_api_url(monkeypatch):
    module = _load_module()
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "result": {
                        "status": {
                            "motion_report": {
                                "live_position": [10.0, 20.0, 30.0],
                                "live_velocity": [4.0, 5.0, 6.0],
                            }
                        }
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    state = module._motion_report_state("http://127.0.0.1:7125", 1.5)

    assert seen["url"] == "http://127.0.0.1:7125/printer/objects/query?motion_report"
    assert seen["timeout"] == 1.5
    assert state == ((10.0, 20.0, 30.0), (4.0, 5.0, 6.0))


def test_effective_sample_interval_scales_to_tolerance():
    module = _load_module()

    assert module._effective_sample_interval_s(0.5, 1.0) == 0.001
    assert module._effective_sample_interval_s(0.01, 1.0) == 0.0001


def test_wait_for_position_prefers_websocket_updates(monkeypatch):
    module = _load_module()
    seen = {}

    class FakeWebSocket:
        def __init__(self, messages):
            self.messages = list(messages)
            self.sent = []

        async def send(self, message):
            self.sent.append(message)

        async def recv(self):
            return self.messages.pop(0)

    class FakeConnect:
        def __init__(self, messages):
            self.websocket = FakeWebSocket(messages)

        async def __aenter__(self):
            return self.websocket

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_connect(*args, **kwargs):
        seen["url"] = args[0]
        return FakeConnect(
            [
                json.dumps(
                    {
                        "result": {
                            "status": {
                                "motion_report": {
                                    "live_position": [1.0, 2.0, 3.0],
                                    "live_velocity": [10.0, 0.0, 0.0],
                                }
                            }
                        }
                    }
                ),
                json.dumps(
                    {
                        "method": "notify_status_update",
                        "params": [
                            {
                                "motion_report": {
                                    "live_position": [20.0, 30.0, 40.0],
                                    "live_velocity": [0.0, 0.0, 0.0],
                                }
                            }
                        ],
                    }
                ),
            ]
        )

    monkeypatch.setattr(module.websockets, "connect", fake_connect)

    position = asyncio.run(
        module._wait_for_position_ws(
            ws_url="ws://127.0.0.1:7125/websocket",
            timeout_s=1.0,
            target_x=20.0,
            target_y=30.0,
            tolerance_mm=0.05,
            poll_interval_ms=1.0,
        )
    )

    assert seen["url"] == "ws://127.0.0.1:7125/websocket"
    assert position == (20.0, 30.0, 40.0)
