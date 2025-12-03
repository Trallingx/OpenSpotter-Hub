from gui_v3 import *
from SpotterFunctions import *
import logging


class Grid(object):
    def __init__(self, gui, frame_row, frame_col, config, background, config_dir):
        self.gui = gui
        self.config_dir = config_dir
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

        grid_defaults = read_defaults(config)
        
        # Convert dict to list format if necessary
        if isinstance(grid_defaults, dict):
            keys_order = ['rows', 'columns', 'x_step_size', 'y_step_size', 'dispense_volume', 
                         'loading_from', 'leftovers_into', 'z_adjust_down', 'droplet_forming_time',
                         'grid_offset_x', 'grid_offset_y']
            grid_defaults = dict_to_list(grid_defaults, keys_order)
        
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
        create_labels(list_of_inputs, self.entry, self.input_frame)


def create_labels(list_of_inputs, entry, input_frame):
    label = []
    labelx = []

    for i in enumerate(list_of_inputs):
        label.append('label' + str(i))
        labelx.append('labelx' + str(i))
        entry.append('entry' + str(i))

    for inputs in list_of_inputs:
        # create widgets
        label[list_of_inputs.index(inputs)] = tk.Label(input_frame, text=inputs[0])
        entry[list_of_inputs.index(inputs)] = tk.Entry(input_frame, bd=5)
        labelx[list_of_inputs.index(inputs)] = tk.Label(input_frame, text=inputs[2])
        # starting values (insert before adding validation)
        label_text = inputs[0].lower()
        start_val = inputs[1]
        if ('set rows' in label_text or 'set columns' in label_text) and start_val is not None:
            # ensure initial rows/columns are integer strings (handle floats in config)
            try:
                start_val_int = int(float(start_val))
                entry[list_of_inputs.index(inputs)].insert(0, str(start_val_int))
            except Exception:
                entry[list_of_inputs.index(inputs)].insert(0, str(start_val))
        else:
            entry[list_of_inputs.index(inputs)].insert(0, start_val)

        # Add validation for rows/columns to prevent excessively large inputs
        if 'set rows' in label_text or 'set columns' in label_text:
            def make_validator(max_val=150):
                def validate(new_value):
                    if new_value == '':
                        return True
                    try:
                        v = int(new_value)
                    except Exception:
                        return False
                    return 1 <= v <= max_val
                return validate

            vcmd = input_frame.register(make_validator(150))
            entry[list_of_inputs.index(inputs)].config(validate='key', validatecommand=(vcmd, '%P'))
        # place widgets using grid()
        label[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=0, sticky="WE", pady=2)
        entry[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=1)
        labelx[list_of_inputs.index(inputs)].grid(row=list_of_inputs.index(inputs), column=2, sticky="WE", pady=2)


