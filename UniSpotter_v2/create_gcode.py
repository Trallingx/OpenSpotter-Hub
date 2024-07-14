from tkinter import filedialog
from SpotterFunctions import *


def save_file(grid_count, self):
    filepath = filedialog.askdirectory()
    filepath = filepath + str("/drop_array.gcode")
    file = open(filepath, "w")

    # defining global coordinates
    entry = read_entries(self.entry)
    loop_counter = 0
    x_abs = float(entry[0])
    x_loading_calibration = 32.25
    y_abs = float(entry[1])
    y_loading_calibration = 86
    x_offset = x_abs + float(entry[2])
    x_offset_abs = x_offset
    y_offset = y_abs + float(entry[3])
    y_offset_abs = y_offset
    z_high = 40
    # code generation
    # creating the coordinates from the intersection between xline and y line which is x and y
    # absolute. From there we start at the initial offset and add the moving step size

    # writing into the file
    # start g-code
    file = start_gcode(file, z_high)

    # movement loop
    for grid in range(grid_count):
        if grid_count:
            entry = read_entries(self.grid_1.entry)
        else:
            entry = read_entries(self.grid_2.entry)
        rows = int(entry[0])
        cols = int(entry[1])
        # step size inside the grid
        x_shift = float(entry[2])
        y_shift = float(entry[3])
        extrude = -float(entry[4])
        e_abs = 0
        index = 0
        emptying_container = int(entry[6])
        # z calibrations
        z_low = 3 - float(entry[6])
        z = 4
        container_z = 11
        # waiting time upon which the droplet forms
        droplet_wait_time = float(entry[7])
        # reading for possible further grids
        grids = grid_count
        grid_x_offset = float(entry[8])
        grid_y_offset = float(entry[9])

        # filling the syringe
        loading_container = int(entry[5])
        x_container = x_loading_calibration + 167
        y_container_4 = y_loading_calibration + 29
        y_container_3 = y_loading_calibration + 29 - 25

        # choosing between container 1 to 2
        # for second grid invert selection
        y_container_load = select_loading_container(loading_container, y_container_4)

        file.write(f'G0 X{x_container} Y{y_container_load} F5000\n')
        file.write(f'G0 Z{container_z}  F500\n')
        total_fill = 0
        total_fill = rows * cols * -extrude
        file.write(f'G1 E{total_fill + 30} F250; Filling the syringe\n')
        file.write(f'G0 Z{z_high} F3000\n')
        file.write('G92 E0\n\n')
        file.write('G1 E-20 F500 ; dispense first drop\nG04 S5; wait 5 seconds for drop to fall\n')
        file.write(f'G0 X{x_abs} Y{y_abs} F5000\n')
        file.write('G92 E0\n\n')
        file.write(';Coordinates\n')

        coordinates = create_coordinates(rows, cols,
                                         x_offset, grid_x_offset, x_shift, x_offset_abs,
                                         y_offset, grid_y_offset, y_shift,
                                         z)

        # writing the movement sequence
        for i in range(rows * cols):
            line = 'G0 ' + coordinates[i] + ' F3000' + '\n'
            file.write(line)
            # check for beginning of each row
            remainder = i % cols
            if remainder == 0:  # if beginning of row add wait to remove oscillations
                file.write("G4 S0.2\n")
            file.write("M211 S0 ; disable endstops to allow for lower than 0 calibration movement\n")
            file.write(f'G1 E{extrude} F500\nG92 E0\nG4 S{droplet_wait_time}\n')
            file.write(f'G0 Z{z_low} F500 ;let the droplet touch the cantilever\n')
            e_abs = e_abs + abs(extrude)
            file.write('G0 Z4 F4000\n')
            file.write("M211 S1 ; enable endstops\n")

        # emptying syringe
        y_container_emptying, y_container_cleaning = select_cleaning_containers(emptying_container,
                                                                                y_container_3,
                                                                                y_container_4)
        file.write(f'\nG0 Z{z_high} F1000 ; dispensing leftovers\n')
        file.write(f'G0 X{x_container} Y{y_container_emptying} F5000\n')
        file.write(f'G0 Z{container_z} F500\n')
        file.write('G1 E-10 F500\n')
        file.write(f'G0 Z{z_high} F1000\n')
        # perform cleaning sequence
        auto_cleaning(y_container_cleaning, y_container_emptying, x_container, file, z_high, container_z)
        e_abs = 0
        loop_counter = loop_counter + 1

    # presenting build plate
    file.write('G90 ;absolute positioning\nG0 Y170 F500;present print\n')
    # end writing

    file.close()
    if file is None:
        return


def start_gcode(file, z_high):
    file.write(";TYPE:Custom\nM862.3 P \"MK3S\" ; printer model check")
    file.write('\nM406 ; Filament sensor off\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
    file.write('\n;Homing sequence\n')
    file.write(f'G0 Z{z_high} F3000 ;Lift Z to prevent scratching and allow leveling\n')
    file.write('\nG28 [X] [Y]\n')
    file.write('G0 X90 Y90 F3000\nG92 [X] [Y]\n')
    file.write('G28 [Z]\n')
    file.write('G92 X100 Y100 Z4 E0\n')  # setting Z to for allows for going below 0 i.e. crash into the metal,
    # adjust  carefully
    file.write(f'G0 Z{z_high} F3000\n\n')
    file.write('G1 E10 F500\nG92 E0\n')

    return file


def auto_cleaning(clean_y, empty_y, container_x, file, z_high, z_low):
    # create sequence to take Toluol multiple times and dispense for cleaning
    file.write("\n\n: Create cleaning sequence\n")
    for number in range(0, 3):
        file.write(f'G0 Z{z_high} F2000\n')
        file.write(f'G0 X{container_x} Y{clean_y} F5000\n')
        file.write(f'G0 Z{z_low} F2000\n')
        file.write('G1 E20 F500\n')
        file.write(f'G0 Z{z_high} F2000\n')
        file.write(f'G0 X{container_x} Y{empty_y} F5000\n')
        file.write(f'G0 Z{z_low} F2000\n')
        file.write('G1 E-20 F500\n')
    file.write(f'G0 Z{z_high} F2000\n\n')
