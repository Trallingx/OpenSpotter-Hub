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
        save_button.grid(row=2,column=0)
        save_button = Button(self.main_frame, text="create file", command=self.save_file)
        save_button.grid(row=2,column=1)
        save_button = Button(self.main_frame, text="save defaults", command=self.save_defaults)
        save_button.grid(row=2, column=2)

        info_text = tk.Label(self.main_frame, text="1: Give values to all the text fields\n"
                                                   "Only insert numbers, decimals can be used, except for rows & columns\n"
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

    def check_input(self):
        total_width = float(self.entry[5].get())*float(self.entry[6].get())+float(self.entry[2].get())
        print(total_width)
        total_height = float(self.entry[4].get()) * float(self.entry[7].get()) + float(self.entry[3].get())
        print(total_height)
        if total_width >= 20 or total_height >= 40:
            print("error")
            self.open_secondary_window()

    def open_secondary_window(self):
        # Create secondary (or popup) window.
        secondary_window = tk.Toplevel()
        secondary_window.title("Secondary Window")
        secondary_window.config(width=400, height=200)
        # Create a button to close (destroy) this window.
        button_close = Button(
            secondary_window,
            text="Check the input dimensions, either width or height\nof the array exceeds frame dimensions"
                 ,
            command=secondary_window.destroy
        )
        button_close.place(x=75, y=75)

    def save_defaults(self):
        config = open("config.txt", "w")
        for i in range(16):
            save = self.entry[i].get()
            config.write(save+"\n")
        config.close()

    def read_defaults(self):
        config = open("config.txt", "r")
        lines = config.readlines()
        for i in range(len(lines)):
            lines[i] = lines[i].replace("\n","")
        config.close()
        return lines

    def auto_cleaning(self):
            # create sequence to take Toluol multiple times and dispense for cleaning


    def save_file(self):

        filepath = filedialog.askdirectory()
        filepath = filepath + str("/drop_array.gcode")
        print(filepath)
        file = open(filepath, "w")
        # code generation

        # arrangement of cantilevers
        rows = int(self.entry[4].get())
        cols = int(self.entry[5].get())

        # indexing of cantilevers
        coordinates = ['0' for i in range(cols * rows)]
        coordinates_grid_1 = ['0' for i in range(cols * rows)]
        coordinates_grid_2 = ['0' for i in range(cols * rows)]

        # defining coordinates
        loop_counter = 0
        x_loading_calibration = 32
        y_loading_calibration = 85
        x_abs = float(self.entry[0].get())
        y_abs = float(self.entry[1].get())
        x_offset = x_abs + float(self.entry[2].get())
        x_offset_abs = x_offset
        y_offset = y_abs + float(self.entry[3].get())
        y_offset_abs = y_offset
        x_shift = float(self.entry[6].get())
        y_shift = float(self.entry[7].get())
        z = 4
        z_low = 3-float(self.entry[11].get())
        index = 0
        e_abs = 0
        extrude = -float(self.entry[8].get())

        # reading for possible further grids
        grids = int(self.entry[13].get())
        grid_x_offset = float(self.entry[14].get())
        grid_y_offset = float(self.entry[15].get())

        # creating the coordinates from the intersection between xline and y line which is x and y
        # absolute. From there we take an offset to account for the build type of the cantilevers.
        for j in range(rows):
            for i in range(cols):
                coordinates_grid_1[index] = 'X' + str(x_offset) + ' Y' + str(y_offset) + ' Z' + str(z)
                x_offset = x_offset + x_shift
                index = index + 1
            x_offset = x_offset_abs
            y_offset = y_offset + y_shift
        index = 0
        x_offset = x_offset_abs
        y_offset = y_offset_abs
        # coordinates of second grid
        for j in range(rows):
            for i in range(cols):
                coordinates_grid_2[index] = ('X' + str(x_offset+grid_x_offset) + ' Y'
                                             + str(y_offset+grid_y_offset) + ' Z' + str(z))
                x_offset = x_offset + x_shift
                index = index + 1
            x_offset = x_offset_abs
            y_offset = y_offset + y_shift

        # writing into the file
        # start g-code
        file.write(";TYPE:Custom\nM862.3 P \"MK3S\" ; printer model check")
        file.write('\nM406 ; Filament sensor off\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
        file.write('\n;Homing sequence\n')
        file.write('G0 Z32 F3000 ;Lift Z to prevent scratching and allow leveling\n')
        file.write('\nG28 [X] [Y]\n')
        file.write('G0 X90 Y90 F3000\nG92 [X] [Y]\n')
        file.write('G28 [Z]\n')
        file.write('G92 X100 Y100 Z4 E0\n')  # setting Z to for allows for going below 0 i.e. crash into the metal,
                                            # adjust  carefully
        file.write('G0 Z32 F1000\n\n')

        # movement loop
        for grid in range(grids):
            loop_counter = loop_counter + 1

            # filling the syringe
            loading_container = int(self.entry[9].get())
            x_container = x_loading_calibration + 167
            self.y_container_4 = y_loading_calibration + 29
            container_z = -10
            # choosing between container 1 to 4
            match loading_container:
                case 1:
                    self.y_container_1 = self.y_container_4 - 75
                    y_container_load = self.y_container_1
                case 2:
                    self.y_container_2 = self.y_container_4 - 50
                    y_container_load = self.y_container_2
                case 3:
                    self.y_container_3 = self.y_container_4 - 25
                    y_container_load = self.y_container_3
                case 4:
                    y_container_load = self.y_container_4

            # select loading for second grid
            if loop_counter == 2:
                y_container_load = y_container_load + 25

            file.write('G0 X' + str(x_container) + ' Y' + str(y_container_load) + ' F5000\n')
            file.write('G0 Z' + str(container_z) + ' F500\n')
            total_fill = 0
            total_fill = rows * cols * -extrude
            file.write(('G1 E' + str(total_fill+20) + ' F250; Filling the syringe\n'))
            file.write('G0 Z32 F1000\n')
            file.write('G92 E0\n\n')
            file.write('G1 E-10 F500 ; dispense first drop\nG04 S5; wait 5 seconds for drop to fall\n')
            file.write('G0 X' + str(x_abs) + ' Y' + str(y_abs) + ' F5000\n')
            file.write('G92 E0\n\n')

            # pause for adjusting

            droplet_wait_time = float(self.entry[12].get())  # time printer waits for drop to drop
            file.write(';Coordinates\n')

            if loop_counter == 2:
                coordinates = coordinates_grid_2
            else:
                coordinates = coordinates_grid_1

            # writing the movement sequence
            for i in range(rows * cols):
                line = 'G0 ' + coordinates[i] + ' F3000' + '\n'
                file.write(line)
                # check for beginning of each row
                remainder = i % cols
                if remainder == 0:  # if beginning of row add wait to remove oscillations
                    file.write("G4 S0.5\n")
                file.write("M211 S0 ; disable endstops to allow for lower than 0 calibration movement\n")
                file.write('G1 E' + str(extrude) + ' F500\nG92 E0\nG4 S' + str(droplet_wait_time) + '\n')
                file.write('G0 Z' + str(z_low) + ' F500 ;let the droplet touch the cantilever\n')
                e_abs = e_abs + abs(extrude)
                file.write('G0 Z4 F4000\n')
                file.write("M211 S1 ; enable endstops\n")

            # emptying syringe
            emptying_container = int(self.entry[10].get())
            match emptying_container:
                case 1:
                    y_container_emptying = self.y_container_1
                case 2:
                    y_container_emptying = self.y_container_2
                case 3:
                    y_container_emptying = self.y_container_3
                case 4:
                    y_container_emptying = self.y_container_4

            file.write('\nG0 Z32 F1000 ; dispensing leftovers\n')
            file.write('G0 X' + str(x_container) + ' Y' + str(y_container_emptying) + ' F5000\n')
            file.write('G0 Z-7 F500\n')
            file.write('G1 E-10 F500\nG1 E20 F500\nG1 E-20 F500\n')
            file.write('G0 Z32 F1000\nG04 S10\n')
            e_abs = 0


        # presenting cantilevers
        file.write('G90 ;absolute positioning\nG0 Y170 F500;present print\n')
        # end writing

        file.close()
        if file is None:
            return

