import os
from gui_v3 import DropletGui
from SpotterFunctions import read_defaults
from grid import create_labels
import json
from input_configs import GLOBAL_FIELDS

if __name__ == "__main__":
    config_dir = os.path.dirname(os.path.abspath(__file__))
    Gui = DropletGui(config_dir)

    # Load global defaults and create global inputs first.
    config_path = os.path.join(config_dir, "config_global.json")
    with open(config_path, "r") as f:
        global_defaults = json.load(f)

    create_labels(GLOBAL_FIELDS, global_defaults, Gui.entry, Gui.global_input_frame)
    max_grid_count = max(1, int(global_defaults.get("max_grid_count", 6)))
    
    # Read grid state from JSON and create grids accordingly
    states_data = read_defaults(os.path.join(config_dir, "config_states.json"))
    if isinstance(states_data, dict):
        grid_count = states_data.get("grid_count", 0)
        spiral_count = states_data.get("spiral_count", 0)
    else:
        grid_count = int(states_data[0]) if states_data else 0
        spiral_count = 0

    grid_count = max(0, min(int(grid_count), max_grid_count))
    
    # Create grids based on stored state
    for _ in range(grid_count):
        Gui.instance_grid()

    for _ in range(spiral_count):
        Gui.instance_spiral()

    Gui._switch_workspace_mode()
    
    # Set global fields to locked state by default
    Gui._update_global_fields_state()
    
    Gui.mainloop()
