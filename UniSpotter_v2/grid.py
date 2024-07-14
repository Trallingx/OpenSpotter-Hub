from gui_v2 import *
from SpotterFunctions import *
import logging


class Grid(object):
    def __init__(self, gui, frame_row, frame_col, config, background):
        self.gui = gui
        self.grid_entry = None
        self.input_frame = None
        self.entry = []
        self.grid = None
        self.frame_row = frame_row
        self.frame_col = frame_col
        self.create_grid(config, background)

    def create_grid(self, config, background):
        self.input_frame = tk.Frame(self.gui)
        self.input_frame.config(bg=background, border=5)
        self.input_frame.grid(row=self.frame_row, column=self.frame_col)

        grid_defaults: list[float] = read_defaults(config)
        list_of_inputs = [
                          ("5: Set rows", grid_defaults[0], "int"),         # 4 old
                          ("6: Set columns", grid_defaults[1], "int"),      # 5
                          ("7: X step size", grid_defaults[2], "mm"),       # 6
                          ("8: Y step size", grid_defaults[3], "mm"),       # 7
                          ("Dispense Volume", grid_defaults[4], "uL"),      # 8
                          ("Loading from", grid_defaults[5], "1 or 2 "),    # 9
                          ("Leftovers into", grid_defaults[6], "3 or 4"),   # 10
                          ("Z-Adjust down", grid_defaults[7], "mm"),        # 11
                          ("droplet forming time", grid_defaults[8], "s"),  # 12
                          ("9: grid offset x", grid_defaults[9], "mm"),     # 14
                          ("10: grid offset y", grid_defaults[10], "mm"),   # 15
                          ]
        self.create_labels(list_of_inputs)

    def create_labels(self, list_of_inputs):
        label = []
        labelx = []

        for i in enumerate(list_of_inputs):
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
            label[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=0, sticky="WE", pady=2)
            self.entry[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=1)
            labelx[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=2, sticky="WE", pady=2)


