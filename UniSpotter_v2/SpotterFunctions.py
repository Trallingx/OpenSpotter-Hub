import gui_v2
import grid
import main_v2


def read_defaults(file):
    config = open(f"{file}", "r")
    lines = config.readlines()
    for i, line in enumerate(lines):
        lines[i] = lines[i].replace("\n", "")
    config.close()
    return lines


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
    data = read_entries(entry)
    config = open(f"{file}", "w")
    for i in range(count_range(entry)):
        save = str(data[i])
        config.write(save + "\n")
    config.close()


def write_state(state):
    file = open("config_states.txt", "w")
    file.write(str(state))
    file.close()


def select_loading_container(loading_container, y_container_4):
    match loading_container:
        case 1:
            return y_container_4 - 75
        case 2:
            return y_container_4 - 50


