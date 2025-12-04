import os
from gui_v3 import DropletGui
from SpotterFunctions import read_defaults, dict_to_list
from grid import create_labels
import json

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
    
    # Load the JSON file
    config_path = os.path.join(config_dir, "config_global.json")
    with open(config_path, "r") as f:
        global_defaults = json.load(f)

    # Access directly as a dictionary
    list_of_inputs = [
        ("1: X cord. of the Y-line", global_defaults["X_cord_of_Y_Line"], "mm"),  # 0
        ("2: Y cord. of the X-line", global_defaults["Y_cord_of_X_Line"], "mm"),  # 1
        ("3: First Spot X-offset",   global_defaults["tuning_offset_x"], "mm"),   # 2
        ("4: First Spot Y-offset",   global_defaults["tuning_offset_y"], "mm"),   # 3
    ]

    create_labels(list_of_inputs, Gui.entry, Gui.global_input_frame)
    Gui.mainloop()
