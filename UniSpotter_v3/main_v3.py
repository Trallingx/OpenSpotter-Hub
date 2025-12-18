import os
from gui_v3 import DropletGui
from SpotterFunctions import read_defaults
from grid import create_labels
import json
from input_configs import GLOBAL_FIELDS

if __name__ == "__main__":
    config_dir = os.path.dirname(os.path.abspath(__file__))
    Gui = DropletGui(config_dir)
    
    # Read grid state from JSON and create grids accordingly
    states_data = read_defaults(os.path.join(config_dir, "config_states.json"))
    if isinstance(states_data, dict):
        grid_count = states_data.get("grid_count", 0)
    else:
        grid_count = int(states_data[0]) if states_data else 0
    
    # Create grids based on stored state
    for _ in range(grid_count):
        Gui.instance_grid()
    
    # Load the JSON file
    config_path = os.path.join(config_dir, "config_global.json")
    with open(config_path, "r") as f:
        global_defaults = json.load(f)

    # Get input configuration
    

    create_labels(GLOBAL_FIELDS, global_defaults, Gui.entry, Gui.global_input_frame)
    
    # Set global fields to locked state by default
    Gui._update_global_fields_state()
    
    Gui.mainloop()
