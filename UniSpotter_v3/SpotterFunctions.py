import json
import os


def read_defaults(file):
    """Read configuration from JSON file. Maintains backward compatibility."""
    if file.endswith('.json'):
        with open(file, 'r') as config_file:
            data = json.load(config_file)
            # Convert dict to list format for backward compatibility
            if isinstance(data, dict):
                return data
            return data
    else:
        # Backward compatibility: read old text format
        config = open(f"{file}", "r")
        lines = config.readlines()
        for i, line in enumerate(lines):
            lines[i] = lines[i].replace("\n", "")
        config.close()
        return lines


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


def save_defaults(entry, file):
    """Save configuration to JSON file."""
    data = read_entries(entry)
    if file.endswith('.json'):
        # Determine which keys to use based on filename
        if 'global' in file:
            keys = ['x_coord_y_line', 'y_coord_x_line', 'first_spot_x_offset', 'first_spot_y_offset']
        elif 'grid' in file:
            keys = ['rows', 'columns', 'x_step_size', 'y_step_size', 'dispense_volume', 
                   'loading_from', 'leftovers_into', 'z_adjust_down', 'droplet_forming_time',
                   'grid_offset_x', 'grid_offset_y']
        else:
            keys = [f'param_{i}' for i in range(len(data))]
        
        data_dict = list_to_dict(data, keys)
        with open(file, 'w') as config_file:
            json.dump(data_dict, config_file, indent=2)
    else:
        # Backward compatibility: write old text format
        config = open(f"{file}", "w")
        for i in range(count_range(entry)):
            save = str(data[i])
            config.write(save + "\n")
        config.close()


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


def save_defaults(entry, file):
    """Save configuration to JSON file."""
    data = read_entries(entry)
    if file.endswith('.json'):
        with open(file, 'w') as config_file:
            json.dump(data, config_file, indent=2)
    else:
        # Backward compatibility: write old text format
        config = open(f"{file}", "w")
        for i in range(count_range(entry)):
            save = str(data[i])
            config.write(save + "\n")
        config.close()


def write_state(state, config_dir=None):
    """Write grid state to JSON file."""
    if config_dir is None:
        filepath = "config_states.json"
    else:
        filepath = os.path.join(config_dir, "config_states.json")
    
    with open(filepath, 'w') as file:
        json.dump({"grid_count": state}, file, indent=2)


def select_loading_container(loading_container, y_container_4):
    match loading_container:
        case 1:
            return y_container_4 - 75
        case 2:
            return y_container_4 - 50


