from gui_v3 import *
from SpotterFunctions import *
import logging


class Grid(object):
    def __init__(self, gui, frame_row, frame_col, config, background, config_dir):
        self.gui = gui
        self.config_dir = config_dir
        self.grid_entry = None
        self.input_frame = None
        self.grid_entry = []
        self.cleaning_entry = []
        self.washing_entry = []
        self.cleaning_widgets = []  # Store cleaning widgets for show/hide
        self.washing_widgets = []  # Store washing widgets for show/hide
        self.grid = None
        self.frame_row = frame_row
        self.frame_col = frame_col
        self.create_grid(config, background)

    def _toggle_cleaning_inputs(self):
        """Show/hide cleaning input widgets based on checkbox state."""
        is_enabled = self.cleaning_enabled.get()
        # Hide/show all cleaning input widgets except the checkbox itself
        for widget in self.cleaning_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer._poll()
        except Exception:
            pass

    def _toggle_washing_inputs(self):
        """Show/hide washing input widgets based on checkbox state."""
        is_enabled = self.washing_enabled.get()
        # Hide/show all washing input widgets except the checkbox itself
        for widget in self.washing_widgets[1:]:  # Skip the checkbox
            if is_enabled:
                widget.grid()
            else:
                widget.grid_remove()
        # Trigger canvas update
        try:
            if hasattr(self.gui, 'canvas_drawer') and self.gui.canvas_drawer:
                self.gui.canvas_drawer._poll()
        except Exception:
            pass

    def create_grid(self, config, background):
        self.master_input_frame = tk.Frame(self.gui)
        self.master_input_frame.config(bg=background, border=5)
        self.master_input_frame.grid(row=self.frame_row, column=self.frame_col)

        self.grid_input_frame = tk.Frame(self.master_input_frame)
        self.grid_input_frame.config(bg=background, border=5)
        self.grid_input_frame.grid(row= 0, column= 0)
        Grid_label = tk.Label(self.grid_input_frame, text="Grid Configuration")
        Grid_label.grid(row=0, column=0, columnspan=3, pady =5)

        self.cleaning_input_frame = tk.Frame(self.master_input_frame)
        self.cleaning_input_frame.config(bg=background, border=5)
        self.cleaning_input_frame.grid(row=0, column=1)
        Cleaning_label = tk.Label(self.cleaning_input_frame, text="Cleaning Configuration")
        Cleaning_label.grid(row=0, column=0, columnspan=3, pady=5)

        config_path = os.path.join(self.config_dir, config)
        with open(config_path, "r") as f:
            grid_defaults = json.load(f)
        
        list_of_inputs = [
                          ("5: Set rows", grid_defaults["rows"], "int"),         
                          ("6: Set columns", grid_defaults["cols"], "int"),  
                          ("7: X step size", grid_defaults["pitch_x"], "mm"),   
                          ("8: Y step size", grid_defaults["pitch_y"], "mm"),   
                          ("Dispense Volume", grid_defaults["dispense_vol"], "uL"),
                          ("Loading from", grid_defaults["loading_from"], "1 or 2 "),
                          ("Leftovers into", grid_defaults["loading_to"], "3 or 4"), 
                          ("Z-Adjust down", grid_defaults["Z-Adjust"], "mm"),        
                          ("droplet forming time", grid_defaults["droplet_forming_time"], "s"),
                          ("9: grid offset x", grid_defaults["grid_offset_x"], "mm"),    
                          ("10: grid offset y", grid_defaults["grid_offset_y"], "mm"),   
                  ]
        create_labels(list_of_inputs, self.grid_entry, self.grid_input_frame, self.gui)

        # Add checkbox to enable/disable cleaning grid at row 1
        self.cleaning_enabled = tk.BooleanVar(value=False)
        cleaning_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Cleaning Grid",
            variable=self.cleaning_enabled,
            command=self._toggle_cleaning_inputs
        )
        cleaning_checkbox.grid(row=1, column=0, columnspan=3, pady=5, sticky="WE")
        self.cleaning_widgets.append(cleaning_checkbox)

        list_of_cleaning_inputs = [
                            ("Set rows", grid_defaults["rows_cleaning"], "int"),        
                            ("Set columns", grid_defaults["cols_cleaning"], "int"),     
                            ("X step size", grid_defaults["pitch_x_cleaning"], "mm"),    
                            ("Y step size", grid_defaults["pitch_y_cleaning"], "mm"),      
                            ("Dispense Volume", grid_defaults["dispense_vol_cleaning"], "uL"),
                            ("grid offset x", grid_defaults["grid_offset_x_cleaning"], "mm"),    
                            ("grid offset y", grid_defaults["grid_offset_y_cleaning"], "mm"),  
                            ("spots_before_cleaning", grid_defaults["spots_before_cleaning"], "int"), 
                        ]
        create_labels(list_of_cleaning_inputs, self.cleaning_entry, self.cleaning_input_frame, self.gui,
                     start_row=2, widgets_list=self.cleaning_widgets)
        
        # Add checkbox to enable/disable washing needle at row 10 (after cleaning inputs)
        self.washing_enabled = tk.BooleanVar(value=False)
        washing_checkbox = tk.Checkbutton(
            self.cleaning_input_frame,
            text="Enable Washing Needle",
            variable=self.washing_enabled,
            command=self._toggle_washing_inputs
        )
        washing_checkbox.grid(row=10, column=0, columnspan=3, pady=5, sticky="WE")
        self.washing_widgets.append(washing_checkbox)

        list_of_washing_inputs = [
                            ("Washing Depth", grid_defaults.get("washing_depth", 1.0), "mm"),        
                            ("Washing Speed", grid_defaults.get("washing_speed", 5.0), "mm/s"),     
                            ("Washing Upper Bound", grid_defaults.get("washing_upper_bound", 10.0), "mm"),    
                            ("Washing Lower Bound", grid_defaults.get("washing_lower_bound", 0.0), "mm"),      
                            ("Washing After X Spots", grid_defaults.get("washing_after_x_spots", 5.0), "int"),
                            ("Washing Cycles", grid_defaults.get("washing_cycles", 1.0), "int"),    
                        ]
        create_labels(list_of_washing_inputs, self.washing_entry, self.cleaning_input_frame, self.gui,
                     start_row=11, widgets_list=self.washing_widgets)
        
        # Initially hide washing inputs
        self._toggle_washing_inputs()
        
        # Initially hide cleaning inputs
        self._toggle_cleaning_inputs()


def create_labels(list_of_inputs, entry, input_frame, gui=None, start_row=1, widgets_list=None):
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
        
        # Bind key release to trigger canvas updates
        if gui and hasattr(gui, 'canvas_drawer'):
            def make_on_change(canvas_drawer):
                def on_change(event):
                    try:
                        if canvas_drawer:
                            canvas_drawer._poll()
                    except Exception:
                        pass
                return on_change
            entry[list_of_inputs.index(inputs)].bind('<KeyRelease>', make_on_change(gui.canvas_drawer))
        
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
        
        # place widgets using grid() with proper row offset
        row = start_row + list_of_inputs.index(inputs)
        label[list_of_inputs.index(inputs)].grid(row=row, column=0, sticky="WE", pady=2)
        entry[list_of_inputs.index(inputs)].grid(row=row, column=1)
        labelx[list_of_inputs.index(inputs)].grid(row=row, column=2, sticky="WE", pady=2)
        
        # Track widgets for show/hide if widgets_list is provided
        if widgets_list is not None:
            widgets_list.append(label[list_of_inputs.index(inputs)])
            widgets_list.append(entry[list_of_inputs.index(inputs)])
            widgets_list.append(labelx[list_of_inputs.index(inputs)])


