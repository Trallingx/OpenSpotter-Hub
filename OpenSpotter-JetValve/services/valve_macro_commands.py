"""
Klipper valve macro command builders.

Keep these helpers aligned with docs/klipper_configs/valve_macros.cfg.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


ValveSchema = Optional[Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]]


def _normalize_schema(valve_schema: ValveSchema) -> dict:
    if isinstance(valve_schema, Mapping):
        return dict(valve_schema)

    schema: dict[str, Mapping[str, Any]] = {}
    for field in valve_schema or []:
        if isinstance(field, Mapping) and field.get("name"):
            schema[str(field["name"])] = field
    return schema


def _schema_field(schema: Mapping[str, Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    field = schema.get(name, {})
    return field if isinstance(field, Mapping) else {}


def _value(
    valve_config: Mapping[str, Any],
    schema: Mapping[str, Mapping[str, Any]],
    name: str,
    default: Any,
) -> Any:
    if name in valve_config:
        return valve_config[name]
    return _schema_field(schema, name).get("default", default)


def _bool_value(
    valve_config: Mapping[str, Any],
    schema: Mapping[str, Mapping[str, Any]],
    name: str,
    default: bool,
) -> bool:
    value = _value(valve_config, schema, name, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_value(
    valve_config: Mapping[str, Any],
    schema: Mapping[str, Mapping[str, Any]],
    name: str,
    default: float,
) -> float:
    value = float(_value(valve_config, schema, name, default))
    field = _schema_field(schema, name)
    if field.get("min") is not None:
        value = max(value, float(field["min"]))
    if field.get("max") is not None:
        value = min(value, float(field["max"]))
    return value


def _int_value(
    valve_config: Mapping[str, Any],
    schema: Mapping[str, Mapping[str, Any]],
    name: str,
    default: int,
) -> int:
    value = int(_value(valve_config, schema, name, default))
    field = _schema_field(schema, name)
    if field.get("min") is not None:
        value = max(value, int(field["min"]))
    if field.get("max") is not None:
        value = min(value, int(field["max"]))
    return value


def build_shoot_command(
    valve_id: int,
    valve_config: Optional[Mapping[str, Any]] = None,
    valve_schema: ValveSchema = None,
    klipper_config: Optional[Mapping[str, Any]] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    speed_mm_s: Optional[float] = None,
) -> str:
    """Build the unified move-and-fire SHOOT macro command used by spotting."""
    schema = _normalize_schema(valve_schema)
    valve = valve_config or {}
    klipper = klipper_config or {}

    parts = [
        "SHOOT",
        f"VALVE={int(valve_id)}",
        f"HOLD={int(_bool_value(valve, schema, 'hold', False))}",
        f"PRE_FIRE_WAIT={_float_value(valve, schema, 'pre_fire_wait', 0.0)}",
        f"POST_FIRE_WAIT={_float_value(valve, schema, 'post_fire_wait', 0.0)}",
    ]

    trigger_mode = str(klipper.get("valve_trigger_mode", "") or "").strip().lower()
    if trigger_mode != "mcu":
        parts.extend(
            [
                f"ON_MS={_float_value(valve, schema, 'on_ms', 5.0)}",
                f"OFF_MS={_float_value(valve, schema, 'off_ms', 0.0)}",
                f"CYCLES={_int_value(valve, schema, 'cycles', 1)}",
            ]
        )

    if trigger_mode:
        parts.append(f"TRIGGER_MODE={trigger_mode}")

    if x is not None:
        parts.append(f"X={float(x)}")
    if y is not None:
        parts.append(f"Y={float(y)}")
    if speed_mm_s is not None:
        parts.append(f"SPEED_MM_S={float(speed_mm_s)}")

    return " ".join(parts)


def build_valve_timing_command(
    valve_id: int,
    valve_config: Optional[Mapping[str, Any]] = None,
    valve_schema: ValveSchema = None,
) -> str:
    """Build the timing preload command used by Pi-MCU edge-triggered shots."""
    schema = _normalize_schema(valve_schema)
    valve = valve_config or {}
    return (
        f"SET_ARDUINO_VALVE_TIMING VALVE={int(valve_id)} "
        f"ON_MS={_float_value(valve, schema, 'on_ms', 5.0)} "
        f"OFF_MS={_float_value(valve, schema, 'off_ms', 0.0)} "
        f"CYCLES={_int_value(valve, schema, 'cycles', 1)}"
    )


def build_valve_fire_blocking_command(
    valve_id: int,
    on_ms: float,
    off_ms: float = 0.0,
    cycles: int = 1,
) -> str:
    """Build a manual SHOOT command without embedded movement."""
    return (
        f"SHOOT VALVE={int(valve_id)} HOLD=0 PRE_FIRE_WAIT=0.0 POST_FIRE_WAIT=0.0 "
        f"ON_MS={float(on_ms)} OFF_MS={float(off_ms)} CYCLES={int(cycles)} TRIGGER_MODE=usb"
    )
