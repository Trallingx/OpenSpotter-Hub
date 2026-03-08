import json
import os
from dataclasses import dataclass


@dataclass
class Container:
    x: float
    y: float
    z_filling_height: float


def volume_to_mm(volume_ul):
    """
    Convert volume in microliters (uL) to stepper motor position in millimeters (mm).
    Conversion: 1 uL = 5 mm
    
    Args:
        volume_ul: Volume in microliters
        
    Returns:
        Position in millimeters for stepper motor
    """
    return volume_ul * 5.0


def read_defaults(file):
    with open(file, "r") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object")
    return data


def save_defaults(file, *section_dicts):
    data = {}

    for section in section_dicts:
        if not isinstance(section, dict):
            raise TypeError(
                f"save_defaults expected dicts, got {type(section).__name__}: {section}"
            )
        data.update(section)

    with open(file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Saved defaults to {file}")


def write_state(state, config_dir=None):
    """Write grid state to JSON file."""
    if config_dir is None:
        filepath = "config_states.json"
    else:
        filepath = os.path.join(config_dir, "config_states.json")
    
    with open(filepath, 'w') as file:
        json.dump({"grid_count": state}, file, indent=2)


def entries_to_dict(entries, fields):
    """
    Convert a list of tk.Entry widgets to a dict keyed by Field.key.
    Assumes same order as fields list.
    """
    result = {}
    for entry, field in zip(entries, fields):
        try:
            raw = entry.get()
            if field.unit == "int":
                value = int(raw)  # enforce integer-only input
            elif field.unit in ("mm", "uL", "s"):
                value = float(raw)
            else:
                value = raw
        except Exception:
            value = field.default
        result[field.key] = value
    return result


def create_coordinates(rows, cols,
                       x_offset, grid_x_offset, x_shift,
                       y_offset, grid_y_offset, y_shift):
    index = 0
    coordinates_grid = ['0' for _ in range(cols * rows)]
    x_offset_abs = x_offset + grid_x_offset
    x_offset = x_offset_abs
    y_offset = y_offset + grid_y_offset
    for j in range(rows):
        for i in range(cols):
            coordinates_grid[index] = f'X{x_offset} Y{y_offset}'
            x_offset = x_offset + x_shift
            index = index + 1
        x_offset = x_offset_abs
        y_offset = y_offset + y_shift
    return coordinates_grid


def count_range(entry):
    count = 0
    while 1:
        try:
            count += 1
            float(entry[count].get())
        except IndexError:
            return count


def read_entries(entry):
    count = count_range(entry)
    return [float(entry[i].get()) for i in range(count)]


def read_entries_as_dict(entries, fields):
    """
    entries: list of Entry widgets
    fields: list of Field objects (or tuples with .key)
    """
    result = {}
    for entry, field in zip(entries, fields):
        try:
            raw = entry.get()
            if field.unit == "int":
                result[field.key] = int(raw)
            elif field.unit in ("mm", "uL", "s"):
                result[field.key] = float(raw)
            else:
                result[field.key] = raw
        except Exception:
            result[field.key] = field.default
    return result


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
