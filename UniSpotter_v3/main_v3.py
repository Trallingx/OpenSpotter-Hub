import os
from gui_v3 import DropletGui
from SpotterFunctions import read_defaults, dict_to_list
from grid import create_labels

if __name__ == "__main__":
    config_dir = os.path.dirname(os.path.abspath(__file__))
    Gui = DropletGui(config_dir)
    
    # Read grid state from JSON
    states_data = read_defaults(os.path.join(config_dir, "config_states.json"))
    if isinstance(states_data, dict):
        grid_count = states_data.get("grid_count", 0)
        Gui.check_grid_state([str(grid_count)])
    else:
        Gui.check_grid_state(states_data)
    
    global_defaults = read_defaults(os.path.join(config_dir, "config_global.json"))
    
    # Convert dict to list if necessary
    if isinstance(global_defaults, dict):
        keys_order = ['x_coord_y_line', 'y_coord_x_line', 'first_spot_x_offset', 'first_spot_y_offset']
        global_defaults = dict_to_list(global_defaults, keys_order)
    
    # global settings
    list_of_inputs = [("1: X cord. of the Y-line", global_defaults[0], "mm"),  # 0
                      ("2: Y cord. of the X-line", global_defaults[1], "mm"),  # 1
                      ("3: First Spot X-offset", global_defaults[2], "mm"),  # 2
                      ("4: First Spot Y-offset", global_defaults[3], "mm"),  # 3
                      ]
    create_labels(list_of_inputs, Gui.entry, Gui.global_input_frame)
    Gui.mainloop()
