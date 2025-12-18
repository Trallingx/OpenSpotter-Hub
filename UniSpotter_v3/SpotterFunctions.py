import json
import os

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
            value = entry.get()
            # Convert numeric types if needed
            if field.unit in ("mm", "uL", "int", "s"):
                value = float(value)
                if field.unit == "int":
                    value = int(value)
        except Exception:
            value = field.default
        result[field.key] = value
    return result


def create_coordinates(rows, cols,
                       x_offset, grid_x_offset, x_shift,
                       y_offset, grid_y_offset, y_shift,
                       z):
    index = 0
    coordinates_grid = ['0' for _ in range(cols * rows)]
    x_offset_abs = x_offset + grid_x_offset
    x_offset = x_offset_abs
    y_offset = y_offset + grid_y_offset
    # {y_offset}
    for j in range(rows):
        for i in range(cols):
            coordinates_grid[index] = f'X{x_offset} Y{y_offset} Z{z}'
            x_offset = x_offset + x_shift
            index = index + 1
        x_offset = x_offset_abs
        y_offset = y_offset + y_shift
    #print(coordinates_grid)
    return coordinates_grid


def select_cleaning_containers(emptying_container, y_container_3, y_container_4):
    match emptying_container:
        case 3:
            y_container_emptying = y_container_3
        case 4:
            y_container_emptying = y_container_4

    match emptying_container:
        case 3:
            y_container_cleaning = y_container_3 + 25
        case 4:
            y_container_cleaning = y_container_4 - 25

    return y_container_emptying, y_container_cleaning


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
            result[field.key] = float(entry.get())
        except ValueError:
            result[field.key] = field.default
    return result

def select_loading_container(loading_container, y_container_4):
    match loading_container:
        case 1:
            return y_container_4 - 75
        case 2:
            return y_container_4 - 50


