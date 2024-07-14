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


def auto_cleaning(clean_y, empty_y, container_x, file, z_high, z_low):
    # create sequence to take Toluol multiple times and dispense for cleaning
    file.write("\n\n: Create cleaning sequence\n")
    for number in range(0, 3):
        file.write('G0 Z' + str(z_high) + ' F2000\n')
        file.write('G0 X' + str(container_x) + ' Y' + str(clean_y) + ' F5000\n')
        file.write('G0 Z' + str(z_low) + ' F2000\n')
        file.write('G1 E20 F500\n')
        file.write('G0 Z' + str(z_high) + ' F2000\n')
        file.write('G0 X' + str(container_x) + ' Y' + str(empty_y) + ' F5000\n')
        file.write('G0 Z' + str(z_low) + ' F2000\n')
        file.write('G1 E-20 F500\n')
    file.write('G0 Z' + str(z_high) + ' F2000\n')


def create_coordinates(self, rows, cols,
                       x_offset, grid_x_offset, x_shift, x_offset_abs,
                       y_offset, grid_y_offset, y_shift,
                       z, loop_counter):
    index = 0
    coordinates_grid = ['0' for _ in range(cols * rows)]
    if loop_counter:
        x_offset = x_offset + grid_x_offset
        y_offset = y_offset + grid_y_offset

    for j in range(rows):
        for i in range(cols):
            coordinates_grid[index] = 'X' + str(x_offset) + ' Y' + str(y_offset) + ' Z' + str(z)
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




