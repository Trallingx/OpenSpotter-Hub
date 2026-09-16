from __future__ import annotations

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


def test_toolhead_position_uses_moonraker_api_url(monkeypatch):
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
                            "toolhead": {
                                "position": [10.0, 20.0, 30.0]
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

    position = module._toolhead_position("http://127.0.0.1:7125/api", 1.5)

    assert seen["url"] == "http://127.0.0.1:7125/api/printer/objects/query?toolhead"
    assert seen["timeout"] == 1.5
    assert position == (10.0, 20.0, 30.0)