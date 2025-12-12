import json
import os


def read_defaults(file):
    with open(file, 'r') as config_file:
        data = json.load(config_file)
        # Convert dict to list format for backward compatibility
        if isinstance(data, dict):
            return data
        return data

def dict_to_list(data_dict, keys_order):
    """Convert dict config to list format (for backward compatibility with existing code)."""
    if isinstance(data_dict, dict):
        return [data_dict.get(key, 0) for key in keys_order]
    return data_dict


def list_to_dict(data_list, keys):
    """Convert list config to dict format."""
    if isinstance(data_list, list):
        return {key: value for key, value in zip(keys, data_list)}
    return data_list

def save_defaults(grid_entry, cleaning_entry, washing_entry, file):
    """Save configuration to JSON file (key-value pairs)."""
    data = read_entries(grid_entry)
    if cleaning_entry:
        cleaning_data = read_entries(cleaning_entry)
        data = data + cleaning_data   # ← this merges both lists
    if washing_entry:
        washing_data = read_entries(washing_entry)
        data = data + washing_data   # ← this merges washing data
    
    print(data)
    # Decide which keys to use based on filename
    if 'global' in file:
        keys = ['X_cord_of_Y_Line', 'Y_cord_of_X_Line', 'tuning_offset_x', 'tuning_offset_y']
    elif 'grid' in file:
        keys = ['rows', 'cols', 'pitch_x', 'pitch_y', 'dispense_vol',
                'loading_from', 'loading_to', 'Z-Adjust', 'droplet_forming_time',
                'grid_offset_x', 'grid_offset_y','rows_cleaning', 'cols_cleaning',
                'pitch_x_cleaning', 'pitch_y_cleaning', 'dispense_vol_cleaning',
                'grid_offset_x_cleaning', 'grid_offset_y_cleaning', 'spots_before_cleaning',
                'washing_depth', 'washing_speed', 'washing_upper_bound', 
                'washing_lower_bound','washing_column_offset', 'washing_after_x_spots', 'washing_cycles']
    else:
        keys = [f'param_{i}' for i in range(len(data))]

    # Convert list of tuples → dict {key: value}
    data_dict = {}
    for key, item in zip(keys, data):
        # Each item is likely (label, value, unit)
        if isinstance(item, (list, tuple)) and len(item) > 1:
            data_dict[key] = float(item[1])
        else:
            data_dict[key] = float(item) if isinstance(item, (int, float, str)) else None

    # Save to JSON
    with open(file, 'w') as config_file:
        json.dump(data_dict, config_file, indent=2)
        print(f"✅ Saved defaults to {file}")


def write_state(state, config_dir=None):
    """Write grid state to JSON file."""
    if config_dir is None:
        filepath = "config_states.json"
    else:
        filepath = os.path.join(config_dir, "config_states.json")
    
    with open(filepath, 'w') as file:
        json.dump({"grid_count": state}, file, indent=2)


def create_coordinates(rows, cols,
                       x_offset, grid_x_offset, x_shift, x_offset_abs,
                       y_offset, grid_y_offset, y_shift,
                       z):
    index = 0
    coordinates_grid = ['0' for _ in range(cols * rows)]
    x_offset = x_offset + grid_x_offset
    y_offset = y_offset + grid_y_offset
    # {y_offset}
    for j in range(rows):
        for i in range(cols):
            coordinates_grid[index] = f'X{x_offset} Y{y_offset} Z{z}'
            x_offset = x_offset + x_shift
            index = index + 1
        x_offset = x_offset_abs
        y_offset = y_offset + y_shift
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

def read_entries_as_dict(entry, list_of_inputs):
    """
    Convert entry list to dictionary using labels from list_of_inputs.
    
    Args:
        entry: List of tkinter Entry widgets
        list_of_inputs: List of tuples (label, default_value, unit)
    
    Returns:
        Dictionary mapping simplified labels to float values
    """
    values = read_entries(entry)
    result = {}
    
    for i, (label, _, _) in enumerate(list_of_inputs):
        if i < len(values):
            # Simplify label: remove numbers, colons, convert to lowercase, replace spaces with underscores
            simplified_label = label.lower().strip().rstrip(':').split(':')[-1].strip()
            simplified_label = simplified_label.replace(' ', '_')
            result[simplified_label] = values[i]
    
    return result

def select_loading_container(loading_container, y_container_4):
    match loading_container:
        case 1:
            return y_container_4 - 75
        case 2:
            return y_container_4 - 50


