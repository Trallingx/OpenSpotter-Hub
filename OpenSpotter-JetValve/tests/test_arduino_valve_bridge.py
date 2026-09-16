import sys
import types

import pytest

from scripts.arduino_valve_bridge import ArduinoValveBridge


class FakeSerialPort:
    def __init__(self, *args, **kwargs):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data.decode("ascii"))

    def flush(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture
def fake_serial(monkeypatch):
    port = FakeSerialPort()
    serial_module = types.SimpleNamespace(Serial=lambda *args, **kwargs: port)
    monkeypatch.setitem(sys.modules, "serial", serial_module)
    return port


def test_bridge_sends_full_original_timing_sequence_each_fire(fake_serial):
    bridge = ArduinoValveBridge(
        serial_port="/dev/test",
        baud=9600,
        supported_valves={0, 1},
        min_ms=2.0,
        max_cycles=1000,
        ready_delay_s=0,
    )

    first = bridge.fire(valve=0, on_ms=5.0, off_ms=2.0, cycles=1)
    second = bridge.fire(valve=0, on_ms=5.0, off_ms=2.0, cycles=1)

    assert first["serial_commands"] == ["V:0", "O:50", "P:20", "K:1"]
    assert second["serial_commands"] == ["V:0", "O:50", "P:20", "K:1"]
    assert fake_serial.writes == [
        "V:0\n",
        "O:50\n",
        "P:20\n",
        "K:1\n",
        "V:0\n",
        "O:50\n",
        "P:20\n",
        "K:1\n",
    ]


def test_bridge_off_is_noop_for_original_pulse_firmware(fake_serial):
    bridge = ArduinoValveBridge(
        serial_port="/dev/test",
        baud=9600,
        supported_valves={0, 1},
        min_ms=2.0,
        max_cycles=1000,
        ready_delay_s=0,
    )

    assert bridge.off() == {"ok": True, "command": "noop"}
    assert fake_serial.writes == []


def test_bridge_configure_preloads_mcu_trigger_timing_without_firing(fake_serial):
    bridge = ArduinoValveBridge(
        serial_port="/dev/test",
        baud=9600,
        supported_valves={0, 1},
        min_ms=2.0,
        max_cycles=1000,
        ready_delay_s=0,
    )

    result = bridge.configure_trigger(valve=0, on_ms=5.0, off_ms=2.0, cycles=3)

    assert result["mode"] == "mcu_trigger"
    assert result["serial_commands"] == ["V:0", "O:50", "P:20", "C:3"]
    assert fake_serial.writes == ["V:0\n", "O:50\n", "P:20\n", "C:3\n"]


def test_bridge_selects_valve_one_before_configure_or_fire(fake_serial):
    bridge = ArduinoValveBridge(
        serial_port="/dev/test",
        baud=9600,
        supported_valves={0, 1},
        min_ms=2.0,
        max_cycles=1000,
        ready_delay_s=0,
    )

    configured = bridge.configure_trigger(valve=1, on_ms=6.0, off_ms=3.0, cycles=2)
    fired = bridge.fire(valve=1, on_ms=6.0, off_ms=3.0, cycles=2)

    assert configured["serial_commands"] == ["V:1", "O:60", "P:30", "C:2"]
    assert fired["serial_commands"] == ["V:1", "O:60", "P:30", "K:2"]
    assert fake_serial.writes == [
        "V:1\n",
        "O:60\n",
        "P:30\n",
        "C:2\n",
        "V:1\n",
        "O:60\n",
        "P:30\n",
        "K:2\n",
    ]
