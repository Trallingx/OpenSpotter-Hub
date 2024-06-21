from Gui import *

if __name__ == "__main__":
    Gui = DropletGui()
    list_of_defaults = Gui.read_defaults()
    print(list_of_defaults)
    list_of_inputs = [("Y off X-line", list_of_defaults[0], "mm"),  # 0
                      ("X off Y-line", list_of_defaults[1], "mm"),  # 1
                      ("First Cantilever X-offset", list_of_defaults[2], "mm"),  # 2
                      ("First Cantilever Y-offset", list_of_defaults[3], "mm"),  # 3
                      ("Set rows", list_of_defaults[4], "int"),  # 4
                      ("Set columns", list_of_defaults[5], "int"),  # 5
                      ("X step size", list_of_defaults[6], "mm"),  # 6
                      ("Y step size", list_of_defaults[7], "mm"),  # 7
                      ("Dispense Volume", list_of_defaults[8], "uL"),  #
                      ("Loading from", list_of_defaults[9], "1 to 4 "),  # 9
                      ("Left-overs into", list_of_defaults[10], "1-4"),  # 10
                      ("Z-Adjust down", list_of_defaults[11], "mm"),  # 11
                      ("droplet forming time", list_of_defaults[12], "s"),  # 12
                      ("number of grids",list_of_defaults[13], "1-2"),  # 13
                      ("grid offset x", list_of_defaults[14], "mm"),  # 14
                      ("grid offset y", list_of_defaults[15], "mm"),  # 15
                      ]
    Gui.create_labels(list_of_inputs)
    Gui.mainloop()
