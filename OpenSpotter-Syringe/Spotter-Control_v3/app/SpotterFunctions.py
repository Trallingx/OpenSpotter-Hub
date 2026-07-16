import json
import os
from dataclasses import dataclass
from datetime import datetime

from .runtime_logging import get_logger, log_options


logger = get_logger("configuration")


@dataclass
class Container:
    x: float
    y: float
    z_filling_height: float


def volume_to_mm(volume_ul, millimeters_per_microliter):
    """
    Convert volume in microliters (uL) to stepper motor position in millimeters (mm).
    The conversion factor is supplied by the active runtime workflow.
    
    Args:
        volume_ul: Volume in microliters
        
    Returns:
        Position in millimeters for stepper motor
    """
    factor = float(millimeters_per_microliter)
    if factor <= 0:
        raise ValueError("millimeters_per_microliter must be positive")
    return float(volume_ul) * factor


def read_defaults(file):
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object")
    log_options(logger, "configuration.loaded", path=file, options=data)
    return data


def save_defaults(file, *section_dicts):
    data = {}

    for section in section_dicts:
        if not isinstance(section, dict):
            raise TypeError(
                f"save_defaults expected dicts, got {type(section).__name__}: {section}"
            )
        data.update(section)

    with open(file, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)

    log_options(logger, "configuration.saved", path=file, options=data)


def write_state(state, config_dir=None):
    """Write grid state to JSON file."""
    if config_dir is None:
        filepath = "config_states.json"
    else:
        filepath = os.path.join(config_dir, "config_states.json")
    
    if isinstance(state, dict):
        payload = state
    else:
        payload = {"grid_count": state}

    with open(filepath, 'w', encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, indent=2)
    log_options(logger, "pattern_state.saved", path=filepath, options=payload)


def entries_to_dict(entries, fields):
    """
    Convert a list of tk.Entry widgets to a dict keyed by Field.key.
    Assumes same order as fields list.
    """
    result = {}
    for entry, field in zip(entries, fields):
        raw = "<unavailable>"
        try:
            raw = entry.get()
            unit = str(field.unit).strip().lower()
            if unit == "bool" or isinstance(field.default, bool):
                if isinstance(raw, bool):
                    value = raw
                else:
                    value = str(raw).strip().lower() in ("1", "true", "yes", "on")
            elif unit == "int" or (
                isinstance(field.default, int) and not isinstance(field.default, bool)
            ):
                value = int(float(raw))  # tolerate a JSON/Tk value such as "2.0"
            elif unit == "str" or isinstance(field.default, str):
                value = str(raw)
            else:
                # All remaining field-schema values are numeric, including
                # compound units such as mm/s and descriptive ratio units.
                value = float(raw)
        except Exception as exc:
            value = field.default
            log_options(
                logger,
                "configuration.invalid_value_defaulted",
                field=field.key,
                raw_value=raw,
                default=value,
                error=str(exc),
            )
        result[field.key] = value
    return result


def create_coordinates(rows, cols,
                       x_offset, grid_x_offset, x_shift,
                       y_offset, grid_y_offset, y_shift):
    coordinates_grid = []
    x_offset_abs = x_offset + grid_x_offset
    x_offset = x_offset_abs
    y_offset = y_offset + grid_y_offset
    for j in range(rows):
        for i in range(cols):
            coordinates_grid.append((x_offset, y_offset))
            x_offset = x_offset + x_shift
        x_offset = x_offset_abs
        y_offset = y_offset + y_shift
    return coordinates_grid


def build_containers(entry_dict):
    """Build container objects (1-6) from a global entry dict."""
    containers = {}
    for idx in range(1, 7):
        try:
            x = float(entry_dict.get(f'container{idx}_x', 0.0))
            y = float(entry_dict.get(f'container{idx}_y', 0.0))
            z = float(entry_dict.get(f'container{idx}_z', 0.0))
        except Exception:
            x = y = z = 0.0
        containers[idx] = Container(x=x, y=y, z_filling_height=z)
    return containers


def write_generation_settings_file(gcode_path, settings_snapshot):
    """Write a versioned, reproducible JSON profile beside generated output."""
    base, _ = os.path.splitext(gcode_path)
    settings_path = f"{base}_settings.json"
    payload = dict(settings_snapshot)
    payload.setdefault("schema_version", 2)
    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["gcode_path"] = gcode_path
    temporary_path = f"{settings_path}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")
        os.replace(temporary_path, settings_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        logger.exception(
            "generation.settings_write_failed | gcode_path=%s | settings_path=%s",
            gcode_path,
            settings_path,
        )
        raise
    log_options(
        logger,
        "generation.settings_written",
        gcode_path=gcode_path,
        settings_path=settings_path,
        settings=payload,
    )
    return settings_path
