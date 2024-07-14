from gui_v2 import *
from SpotterFunctions import *

if __name__ == "__main__":
    Gui = DropletGui()
    Gui.check_grid_state(read_defaults("config_states.txt"))
    global_defaults: list[float] = read_defaults("config_global.txt")
    # global settings
    list_of_inputs = [("1: X cord. of the Y-line", global_defaults[0], "mm"),  # 0
                      ("2: Y cord. of the X-line", global_defaults[1], "mm"),  # 1
                      ("3: First Spot X-offset", global_defaults[2], "mm"),  # 2
                      ("4: First Spot Y-offset", global_defaults[3], "mm"),  # 3
                      ]
    Gui.create_labels(list_of_inputs)
    Gui.mainloop()
