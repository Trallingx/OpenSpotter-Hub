import json
import os
from dataclasses import dataclass
from datetime import datetime


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
    
    if isinstance(state, dict):
        payload = state
    else:
        payload = {"grid_count": state}

    with open(filepath, 'w') as file:
        json.dump(payload, file, indent=2)


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


# NOTE: read_entries_as_dict consolidated into entries_to_dict (above)
# This alias is kept for backwards compatibility during transition
read_entries_as_dict = entries_to_dict


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
    """Write a human-readable settings snapshot next to a generated G-code file."""
    base, _ = os.path.splitext(gcode_path)
    settings_path = f"{base}_settings.txt"

    lines = []
    lines.append("AutoSpan Generation Settings")
    lines.append("=" * 30)
    lines.append(f"generated_at={datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"gcode_path={gcode_path}")
    lines.append("")

    global_settings = settings_snapshot.get("global_settings", {})
    lines.append("[global_settings]")
    for key in sorted(global_settings.keys()):
        lines.append(f"{key}={global_settings[key]}")
    lines.append("")

    runtime_values = settings_snapshot.get("runtime_values", {})
    if runtime_values:
        lines.append("[runtime_values]")
        for key in sorted(runtime_values.keys()):
            lines.append(f"{key}={runtime_values[key]}")
        lines.append("")

    grid_settings = settings_snapshot.get("grid_settings", [])
    for grid_data in grid_settings:
        grid_number = grid_data.get("grid_number", "?")
        lines.append(f"[grid_{grid_number}]")
        lines.append(f"grid_name={grid_data.get('grid_name', f'Grid {grid_number}')}")
        lines.append(f"grid_color={grid_data.get('grid_color', 'green')}")

        for section_name in ("grid", "cleaning", "washing"):
            section = grid_data.get(section_name, {})
            if section:
                lines.append(f"{section_name}:")
                for key in sorted(section.keys()):
                    lines.append(f"  {key}={section[key]}")

        lines.append(f"cleaning_enabled={grid_data.get('cleaning_enabled', False)}")
        lines.append(f"washing_enabled={grid_data.get('washing_enabled', False)}")
        lines.append(f"wash_after_loading={grid_data.get('wash_after_loading', False)}")
        lines.append(f"final_rinse_enabled={grid_data.get('final_rinse_enabled', False)}")
        lines.append(f"final_rinse_add_cleaning_grid={grid_data.get('final_rinse_add_cleaning_grid', False)}")
        lines.append("")

    spiral_settings = settings_snapshot.get("spiral_settings", [])
    for spiral_data in spiral_settings:
        spiral_number = spiral_data.get("spiral_number", "?")
        lines.append(f"[spiral_{spiral_number}]")
        lines.append(f"spiral_name={spiral_data.get('spiral_name', f'Spiral {spiral_number}')}" )
        lines.append(f"spiral_color={spiral_data.get('spiral_color', 'orange')}")

        spiral_section = spiral_data.get("spiral", {})
        if spiral_section:
            lines.append("spiral:")
            for key in sorted(spiral_section.keys()):
                lines.append(f"  {key}={spiral_section[key]}")

        lines.append("")

    with open(settings_path, "w") as file:
        file.write("\n".join(lines).rstrip() + "\n")

    return settings_path
