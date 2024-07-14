import os
from tkinter import *
from tkinter import filedialog
import tkinter as tk
from tkinter.ttk import *
from PIL import ImageTk, Image
from grid import *
from create_gcode import *


class DropletGui(tk.Tk):
    def __init__(self):
        super(DropletGui, self).__init__()
        self.global_input_frame = None
        self.grid_1 = None
        self.grid_2 = None

        self.entry = []
        self.grid_count = 0

        # Setting up basic UI structure
        self.title('SDU-Spotter')

        self.main_frame = tk.Frame(self)
        self.main_frame.grid()

        self.global_frame = tk.Frame(self.main_frame)
        self.global_frame.grid(row=1, column=0)

        self.global_input_frame = tk.Frame(self.global_frame)
        self.global_input_frame.config(bg="lightblue", border=5)
        self.global_input_frame.grid(row=1, column=0)

        info_text = tk.Label(self.main_frame, text="Lorem ipsum dolor sit amet")
        info_text.grid(row=0, columnspan=2)

        # Adding Pictures, that define inputs
        self.picture_frame = tk.Frame(self.main_frame)
        self.picture_frame.grid(row=1, column=1)
        self.adding_pictures()

        # Adding buttons
        self.button_frame = tk.Frame(self.main_frame)
        self.button_frame.grid(row=2, columnspan=2)
        self.create_buttons()

    def create_buttons(self):
        add_grid_button = Button(self.button_frame, text="create grid", command=self.instance_grid)
        add_grid_button.grid(row=3, column=1)

        remove_grid_button = Button(self.button_frame, text="remove grid", command=self.subtract_grid)
        remove_grid_button.grid(row=3, column=2)

        check_input_button = Button(self.button_frame, text="check input", command="check_input")
        check_input_button.grid(row=5, column=0)

        create_gcode_button = Button(self.button_frame, text="create G-code", command=self.save_file)
        create_gcode_button.grid(row=5, column=1)

        check_save_button = Button(self.button_frame, text="save defaults", command=self.check_saves)
        check_save_button.grid(row=5, column=2)

    def instance_grid(self):
        match self.grid_count:
            case 0:
                self.grid_count += 1
                self.grid_1 = Grid(self.main_frame, 4, 0, "config_grid_1.txt", "lightgreen")

            case 1:
                self.grid_count += 1
                self.grid_2 = Grid(self.main_frame, 4, 1, "config_grid_2.txt", "orange")
            case 2:
                open_secondary_window("Cannot add more grids")

    def check_grid_state(self, states):
        match states:
            case ['0']:
                pass  # no grid
            case ['1']:
                self.instance_grid()
            case ['2']:
                self.instance_grid()
                self.instance_grid()

    def subtract_grid(self):
        match self.grid_count:
            case 0:
                open_secondary_window("No more grids available")
            case 1:
                open_secondary_window("One grid required")
                '''self.grid_count -= 1
                self.grid_1.input_frame.destroy()'''
            case 2:
                self.grid_count -= 1
                self.grid_2.input_frame.destroy()

    def check_saves(self):
        match self.grid_count:
            case 0:
                write_state(self.grid_count)
                save_defaults(self.entry, "config_global.txt")
            case 1:
                write_state(self.grid_count)
                save_defaults(self.entry, "config_global.txt")
                save_defaults(self.grid_1.entry, "config_grid_1.txt")
            case 2:
                write_state(self.grid_count)
                save_defaults(self.entry, "config_global.txt")
                save_defaults(self.grid_1.entry, "config_grid_1.txt")
                save_defaults(self.grid_2.entry, "config_grid_2.txt")

    def create_labels(self, list_of_inputs):
        label = []
        labelx = []

        for i in enumerate(list_of_inputs):
            label.append('label' + str(i))
            labelx.append('labelx' + str(i))
            self.entry.append('entry' + str(i))

        for inputs in list_of_inputs:
            # create widgets
            label[list_of_inputs.index(inputs)] = tk.Label(self.global_input_frame, text=inputs[0])
            self.entry[list_of_inputs.index(inputs)] = tk.Entry(self.global_input_frame, bd=5)
            labelx[list_of_inputs.index(inputs)] = tk.Label(self.global_input_frame, text=inputs[2])
            # starting values
            self.entry[list_of_inputs.index(inputs)].insert(0, inputs[1])
            # place widgets using grid()
            label[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=0, sticky="WE", pady=2)
            self.entry[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=1)
            labelx[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=2, sticky="WE", pady=2)

    def adding_pictures(self):
        picture_label = tk.Label(self.picture_frame, text="Build plate information")
        picture_label.grid()

        image = Image.open("buildplate.png")
        resized_image = image.resize((359+20, 307+20))
        photo = ImageTk.PhotoImage(resized_image)

        label_picture = Label(self.picture_frame, image=photo)
        label_picture.image = photo
        label_picture.grid(padx=20, pady=5)

        image = Image.open("spots.png")
        photo = ImageTk.PhotoImage(image)

        spots_picture = Label(self.global_frame, image=photo)
        spots_picture.image = photo
        spots_picture.grid(row=0, column=0)

    def save_file(self):
        save_file(self.grid_count, self)


def open_secondary_window(text):
    secondary_window = tk.Toplevel()
    secondary_window.title("Secondary Window")
    secondary_window.config(width=400, height=200)
    # Create a button to close (destroy) this window.
    button_close = Button(
        secondary_window,
        text=text,
        command=secondary_window.destroy
    )
    button_close.place(x=75, y=75)





