from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALVE_MACROS = ROOT / "docs" / "klipper_configs" / "valve_macros.cfg"


def _macro_block(name: str) -> str:
    text = VALVE_MACROS.read_text(encoding="utf-8")
    start = text.index(f"[gcode_macro {name}]")
    next_start = text.find("[gcode_macro ", start + 1)
    next_delayed = text.find("[delayed_gcode ", start + 1)
    candidates = [idx for idx in (next_start, next_delayed) if idx != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def test_valve_macros_route_timing_to_arduino_bridge():
    text = VALVE_MACROS.read_text(encoding="utf-8")
    arduino_fire = _macro_block("ARDUINO_VALVE_FIRE")
    bridge_start = _macro_block("START_ARDUINO_VALVE_BRIDGE")
    bridge_restart = _macro_block("RESTART_ARDUINO_VALVE_BRIDGE")
    shoot = _macro_block("SHOOT")

    assert "[output_pin arduino_valve_trigger_0]" in text
    assert "[output_pin arduino_valve_trigger_1]" in text
    assert "pin: rpi:gpio17" in text
    assert "pin: rpi:gpio27" in text
    assert "[gcode_shell_command arduino_valve_fire]" in text
    assert "[gcode_shell_command arduino_valve_configure]" in text
    assert "[gcode_shell_command arduino_valve_bridge_start]" in text
    assert "[gcode_shell_command arduino_valve_bridge_restart]" in text
    assert "RUN_SHELL_COMMAND CMD=arduino_valve_configure" in _macro_block("SET_ARDUINO_VALVE_TIMING")
    assert "RUN_SHELL_COMMAND CMD=arduino_valve_fire" in arduino_fire
    assert 'variable_trigger_mode: "mcu"' in arduino_fire
    assert "variable_trigger_state_0: 0" in arduino_fire
    assert "variable_trigger_state_1: 0" in arduino_fire
    assert "SET_GCODE_VARIABLE MACRO=ARDUINO_VALVE_FIRE VARIABLE=trigger_state_0 VALUE={next_trigger_state}" in arduino_fire
    assert "SET_GCODE_VARIABLE MACRO=ARDUINO_VALVE_FIRE VARIABLE=trigger_state_1 VALUE={next_trigger_state}" in arduino_fire
    assert "SET_PIN PIN=arduino_valve_trigger_0 VALUE={next_trigger_state}" in arduino_fire
    assert "SET_PIN PIN=arduino_valve_trigger_1 VALUE={next_trigger_state}" in arduino_fire
    assert "UPDATE_DELAYED_GCODE" not in arduino_fire
    assert "RUN_SHELL_COMMAND CMD=arduino_valve_bridge_start" in bridge_start
    assert "RUN_SHELL_COMMAND CMD=arduino_valve_bridge_restart" in bridge_restart
    assert "sudo -n /usr/bin/systemctl start spotter-arduino-valve-bridge.service" in text
    assert "sudo -n /usr/bin/systemctl restart spotter-arduino-valve-bridge.service" in text
    assert "Current Arduino bridge pin map supports VALVE=0 and VALVE=1 only" in arduino_fire
    assert "TRIGGER_MODE={trigger_mode}" in shoot
    assert "ARDUINO_VALVE_FIRE VALVE={valve} ON_MS={on_ms} OFF_MS={off_ms} CYCLES={cycles} TRIGGER_MODE={trigger_mode}" in shoot
    assert "SHOOT VALVE=0 X=20 Y={printer.toolhead.position.y} SPEED_MM_S=50 PRE_FIRE_WAIT=0 POST_FIRE_WAIT=0 TRIGGER_MODE=mcu" in text
    assert "SHOOT VALVE=0 X=20 Y={printer.toolhead.position.y} SPEED_MM_S=50 PRE_FIRE_WAIT=20 POST_FIRE_WAIT=20 TRIGGER_MODE=mcu" in text
    assert "M400" not in shoot
    assert "ASYNC is removed; use PRE/POST waits for timing" in shoot
    assert "G1 X{x} Y{y} F{speed_mm_s * 60}" in shoot
    assert "[valve_pulse valve_0]" not in text
    assert "VALVE_PULSE" not in text


def test_valve_macros_do_not_stream_output_pin_edges():
    block = _macro_block("SHOOT")
    text = VALVE_MACROS.read_text(encoding="utf-8")

    assert "UPDATE_DELAYED_GCODE" not in text
    assert "[delayed_gcode ARDUINO_VALVE_FIRE_DISPATCH]" not in text
    assert "[delayed_gcode ARDUINO_VALVE_TRIGGER_0_LOW]" not in text
    assert "[delayed_gcode ARDUINO_VALVE_TRIGGER_1_LOW]" not in text
    assert "[gcode_macro ARDUINO_VALVE_FIRE_REQUEST]" not in text
    assert "RUN_SHELL_COMMAND CMD=arduino_valve_fire" not in block
    assert "SET_PIN" not in block
    assert "G4 P{on_ms}" not in block
    assert "VALVE_BURST_ASYNC" not in VALVE_MACROS.read_text(encoding="utf-8")
    assert "CYCLE_TIME" not in block
    assert "duty_cycle" not in block


def test_valve_off_does_not_send_newer_serial_stop_command():
    text = VALVE_MACROS.read_text(encoding="utf-8")

    assert 'PARAMS="--off"' not in text
    assert "Arduino pulse firmware has no latched off command" in text
