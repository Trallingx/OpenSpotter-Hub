import os
from tkinter import *
from tkinter import filedialog
import tkinter as tk
from tkinter.ttk import *
from PIL import ImageTk, Image


class DropletGui(tk.Tk):
    def __init__(self):
        super(DropletGui, self).__init__()
        self.y_container_1 = None
        self.y_container_2 = None
        self.y_container_3 = None
        self.y_container_4 = None
        self.total_fill = None
        self.entry = None

        # Setting up basic UI structure
        self.title('Droplet-Gcode')

        self.main_frame = tk.Frame(self)
        self.main_frame.grid()

        self.input_frame = tk.Frame(self.main_frame)
        self.input_frame.grid(row=1, column=0)

        self.picture_frame = tk.Frame(self.main_frame)
        self.picture_frame.grid(row=1, column=1)
        picture_label = tk.Label(self.picture_frame, text="Build plate information")
        picture_label.grid()

        image = Image.open("buildplate.png")
        resized_image = image.resize((359, 307))
        photo = ImageTk.PhotoImage(resized_image)

        label_picture = Label(self.picture_frame, image=photo)
        label_picture.image = photo
        label_picture.grid()

        save_button = Button(self.main_frame, text="check input", command=self.check_input)
        save_button.grid(row=2, column=0)
        save_button = Button(self.main_frame, text="create file", command=self.save_file)
        save_button.grid(row=2, column=1)
        save_button = Button(self.main_frame, text="save defaults", command=self.save_defaults)
        save_button.grid(row=2, column=2)

        info_text = tk.Label(self.main_frame, text="1: Give values to all the text fields\n"
                                                   "Only Numbers, decimals can be used, except for rows & columns\n"
                                                   "With rows and columns you create a grid\n"
                                                   "rows extend on the Y line, columns on the X line\n"
                                                   "2: Click check input\n"
                                                   "3: click create files\n")
        info_text.grid(row=0, columnspan=2)

    def create_labels(self, list_of_inputs):
        label = []
        self.entry = []
        labelx = []

        for i in range(0, len(list_of_inputs)):
            label.append('label' + str(i))
            labelx.append('labelx' + str(i))
            self.entry.append('entry' + str(i))

        for inputs in list_of_inputs:
            # create widgets
            label[list_of_inputs.index(inputs)] = tk.Label(self.input_frame, text=inputs[0])
            self.entry[list_of_inputs.index(inputs)] = tk.Entry(self.input_frame, bd=5)
            labelx[list_of_inputs.index(inputs)] = tk.Label(self.input_frame, text=inputs[2])
            # starting values
            self.entry[list_of_inputs.index(inputs)].insert(0, inputs[1])
            # place widgets using grid()
            label[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=0, sticky=W, pady=2)
            self.entry[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=1)
            labelx[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=2, sticky=W, pady=2)

    def open_secondary_window(self):
        secondary_window = tk.Toplevel()
        secondary_window.title("Secondary Window")
        secondary_window.config(width=400, height=200)
        # Create a button to close (destroy) this window.
        button_close = Button(
            secondary_window,
            text="Check the input dimensions, either width or height\nof the array exceeds frame dimensions",
            command=secondary_window.destroy
        )
        button_close.place(x=75, y=75)

    '''class SpotterFunctions:
        def __init__(self) -> None:
            
    
            self.gui = DropletGui()
    '''

    def count_range(self):
        count = 0
        while 1:
            try:
                count += 1
                float(self.entry[count].get())
            except IndexError:
                return count

    def read_entries(self):
        count = self.count_range()
        return [float(self.entry[i].get()) for i in range(count)]

    def check_input(self):
        entry = self.read_entries()
        total_width = float(entry[5]) * float(entry[6]) + float(entry[2])
        total_height = float(entry[4]) * float(entry[7]) + float(entry[3])
        if total_width >= 20 or total_height >= 40:
            self.open_secondary_window()


    def save_defaults(self):
        entry = self.read_entries()
        config = open("config.txt", "w")
        for i in range(self.count_range()):
            save = str(entry[i])
            config.write(save + "\n")
        config.close()

    def read_defaults(self):
        config = open("config.txt", "r")
        lines = config.readlines()
        for i in range(len(lines)):
            lines[i] = lines[i].replace("\n", "")
        config.close()
        return lines

    def auto_cleaning(self, clean_y, empty_y, container_x, file, z_high, z_low):
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

    def select_loading_container(self, loading_container, loop_counter):
        if loop_counter:
            loading_container += 2
        match loading_container:
            case 1:
                return self.y_container_4 - 75
            case 2:
                return self.y_container_4 - 50
            case 3:
                return self.y_container_4 - 50
            case 4:
                return self.y_container_4 - 75

    def select_cleaning_containers(self, emptying_container):
        match emptying_container:
            case 3:
                y_container_emptying = self.y_container_3
            case 4:
                y_container_emptying = self.y_container_4

        match emptying_container:
            case 3:
                y_container_cleaning = self.y_container_3 + 25
            case 4:
                y_container_cleaning = self.y_container_4 - 25

        return y_container_emptying,y_container_cleaning

    def save_file(self):
        filepath = filedialog.askdirectory()
        filepath = filepath + str("/drop_array.gcode")
        file = open(filepath, "w")

        # defining coordinates
        entry = self.read_entries()
        loop_counter = 0
        x_abs = float(entry[0])
        x_loading_calibration = 32.25
        y_abs = float(entry[1])
        y_loading_calibration = 86
        x_offset = x_abs + float(entry[2])
        x_offset_abs = x_offset
        y_offset = y_abs + float(entry[3])
        y_offset_abs = y_offset
        # grid
        rows = int(entry[4])
        cols = int(entry[5])
        # step size inside the grid
        x_shift = float(entry[6])
        y_shift = float(entry[7])
        extrude = -float(entry[8])
        e_abs = 0
        index = 0
        emptying_container = int(entry[10])
        # z calibrations
        z_low = 3 - float(entry[11])
        z = 4
        z_high = 40
        container_z = 11
        # waiting time upon which the droplet forms
        droplet_wait_time = float(entry[12])
        # reading for possible further grids
        grids = int(entry[13])
        grid_x_offset = float(entry[14])
        grid_y_offset = float(entry[15])

        # code generation
        # creating the coordinates from the intersection between xline and y line which is x and y
        # absolute. From there we start at the initial offset and add the moving step size

        # writing into the file
        # start g-code
        file.write(";TYPE:Custom\nM862.3 P \"MK3S\" ; printer model check")
        file.write('\nM406 ; Filament sensor off\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
        file.write('\n;Homing sequence\n')
        file.write('G0 Z' + str(z_high) + ' F3000 ;Lift Z to prevent scratching and allow leveling\n')
        file.write('\nG28 [X] [Y]\n')
        file.write('G0 X90 Y90 F3000\nG92 [X] [Y]\n')
        file.write('G28 [Z]\n')
        file.write('G92 X100 Y100 Z4 E0\n')  # setting Z to for allows for going below 0 i.e. crash into the metal,
        # adjust  carefully
        file.write('G0 Z' + str(z_high) + ' F3000\n\n')
        file.write('G1 E10 F500\nG92 E0\n')
        # movement loop
        for grid in range(grids):

            # filling the syringe
            loading_container = int(entry[9])
            x_container = x_loading_calibration + 167
            self.y_container_4 = y_loading_calibration + 29

            # choosing between container 1 to 2
            # for second grid invert selection
            y_container_load = self.select_loading_container(loading_container, loop_counter)

            file.write('G0 X' + str(x_container) + ' Y' + str(y_container_load) + ' F5000\n')
            file.write('G0 Z' + str(container_z) + ' F500\n')
            total_fill = 0
            total_fill = rows * cols * -extrude
            file.write(('G1 E' + str(total_fill + 30) + ' F250; Filling the syringe\n'))
            file.write('G0 Z' + str(z_high) + ' F3000\n')
            file.write('G92 E0\n\n')
            file.write('G1 E-20 F500 ; dispense first drop\nG04 S5; wait 5 seconds for drop to fall\n')
            file.write('G0 X' + str(x_abs) + ' Y' + str(y_abs) + ' F5000\n')
            file.write('G92 E0\n\n')
            file.write(';Coordinates\n')

            coordinates = self.create_coordinates(rows, cols,
                                                  x_offset, grid_x_offset, x_shift, x_offset_abs,
                                                  y_offset, grid_y_offset, y_shift,
                                                  z, loop_counter)

            # writing the movement sequence
            for i in range(rows * cols):
                line = 'G0 ' + coordinates[i] + ' F3000' + '\n'
                file.write(line)
                # check for beginning of each row
                remainder = i % cols
                if remainder == 0:  # if beginning of row add wait to remove oscillations
                    file.write("G4 S0.2\n")
                file.write("M211 S0 ; disable endstops to allow for lower than 0 calibration movement\n")
                file.write('G1 E' + str(extrude) + ' F500\nG92 E0\nG4 S' + str(droplet_wait_time) + '\n')
                file.write('G0 Z' + str(z_low) + ' F500 ;let the droplet touch the cantilever\n')
                e_abs = e_abs + abs(extrude)
                file.write('G0 Z4 F4000\n')
                file.write("M211 S1 ; enable endstops\n")

            # emptying syringe
            y_container_emptying, y_container_cleaning = self.select_cleaning_containers(emptying_container)
            file.write('\nG0 Z' + str(z_high) + ' F1000 ; dispensing leftovers\n')
            file.write('G0 X' + str(x_container) + ' Y' + str(y_container_emptying) + ' F5000\n')
            file.write('G0 Z' + str(container_z) + ' F500\n')
            file.write('G1 E-10 F500\n')
            file.write('G0 Z' + str(z_high) + ' F1000\n')
            # perform cleaning sequence
            self.auto_cleaning(y_container_cleaning, y_container_emptying, x_container, file, z_high, container_z)
            e_abs = 0
            loop_counter = loop_counter + 1

        # presenting cantilevers
        file.write('G90 ;absolute positioning\nG0 Y170 F500;present print\n')
        # end writing

        file.close()
        if file is None:
            return


