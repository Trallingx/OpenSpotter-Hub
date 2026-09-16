from services.klipper_service import KlipperService
from services.valve_macro_commands import build_shoot_command, build_valve_timing_command


def test_mcu_shoot_command_omits_preloaded_timing_fields():
    command = build_shoot_command(
        0,
        {
            "hold": False,
            "pre_fire_wait": 2.5,
            "post_fire_wait": 3.5,
            "on_ms": 0.1,
            "off_ms": 0.0,
            "cycles": 0,
        },
        {
            "on_ms": {"min": 2.0, "default": 5.0},
            "cycles": {"min": 1, "default": 1},
        },
        {
            "valve_trigger_mode": "mcu",
        },
        x=10,
        y=20,
        speed_mm_s=50,
    )

    assert command == (
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=2.5 POST_FIRE_WAIT=3.5 "
        "TRIGGER_MODE=mcu X=10.0 Y=20.0 SPEED_MM_S=50.0"
    )


def test_usb_shoot_command_includes_timing_fields():
    command = build_shoot_command(
        0,
        {
            "hold": False,
            "pre_fire_wait": 2.5,
            "post_fire_wait": 3.5,
            "on_ms": 0.1,
            "off_ms": 0.0,
            "cycles": 0,
        },
        {
            "on_ms": {"min": 2.0, "default": 5.0},
            "cycles": {"min": 1, "default": 1},
        },
        {
            "valve_trigger_mode": "usb",
        },
        x=10,
        y=20,
        speed_mm_s=50,
    )

    assert command == (
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=2.5 POST_FIRE_WAIT=3.5 "
        "ON_MS=2.0 OFF_MS=0.0 CYCLES=1 TRIGGER_MODE=usb X=10.0 Y=20.0 SPEED_MM_S=50.0"
    )


def test_fire_valve_uses_fire_only_shoot_without_legacy_ms_param():
    service = KlipperService()
    service.is_connected = True
    sent = []

    def fake_send_gcode(script):
        sent.append(script)
        return {}

    service.send_gcode = fake_send_gcode

    assert service.fire_valve(0, 16.0)
    assert sent == [
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0.0 POST_FIRE_WAIT=0.0 "
        "ON_MS=16.0 OFF_MS=0.0 CYCLES=1 TRIGGER_MODE=usb"
    ]
    assert " MS=" not in sent[0]


def test_valve_timing_command_preloads_mcu_trigger_values():
    command = build_valve_timing_command(
        0,
        {
            "on_ms": 16.0,
            "off_ms": 5.0,
            "cycles": 1,
        },
        {
            "on_ms": {"min": 2.0, "default": 5.0},
            "off_ms": {"min": 0.0, "default": 0.0},
            "cycles": {"min": 1, "default": 1},
        },
    )

    assert command == "SET_ARDUINO_VALVE_TIMING VALVE=0 ON_MS=16.0 OFF_MS=5.0 CYCLES=1"
