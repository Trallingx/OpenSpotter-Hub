"""
Centralized configuration for all input field definitions.
Each configuration is a list of tuples: (label, default_value, unit)
"""

def get_global_inputs(global_defaults):
    """Global coordinate inputs"""
    return [
        ("1: X cord. of the Y-line", global_defaults["X_cord_of_Y_Line"], "mm"),  # 0
        ("2: Y cord. of the X-line", global_defaults["Y_cord_of_X_Line"], "mm"),  # 1
        ("3: First Spot X-offset",   global_defaults["tuning_offset_x"], "mm"),   # 2
        ("4: First Spot Y-offset",   global_defaults["tuning_offset_y"], "mm"),   # 3
        ("5: Acceptance Square X",   global_defaults["acceptance_square_x"], "mm"), # 4
        ("6: Acceptance Square Y",   global_defaults["acceptance_square_y"], "mm"), # 
        ("7: Base Square X",         global_defaults["base_square_x"], "mm"), # 7
        ("8: Base Square Y",         global_defaults["base_square_y"], "mm"), # 8
        ("9: Grey Square X",         global_defaults["grey_square_x"], "mm"), # 9
        ("10: Grey Square Y",        global_defaults["grey_square_y"], "mm"), # 10
    ]


def get_grid_inputs(grid_defaults):
    """Grid configuration inputs"""
    return [
        ("5: Set rows",             grid_defaults["rows"], "int"),         
        ("6: Set columns",          grid_defaults["cols"], "int"),  
        ("7: X step size",          grid_defaults["pitch_x"], "mm"),   
        ("8: Y step size",          grid_defaults["pitch_y"], "mm"),   
        ("Dispense Volume",         grid_defaults["dispense_vol"], "uL"),
        ("Loading from",            grid_defaults["loading_from"], "1 or 2 "),
        ("Leftovers into",          grid_defaults["loading_to"], "3 or 4"), 
        ("Z-Adjust down",           grid_defaults["Z-Adjust"], "mm"),        
        ("droplet forming time",    grid_defaults["droplet_forming_time"], "s"),
        ("9: grid offset x",        grid_defaults["grid_offset_x"], "mm"),    
        ("10: grid offset y",       grid_defaults["grid_offset_y"], "mm"),   
    ]


def get_cleaning_inputs(grid_defaults):
    """Cleaning grid configuration inputs"""
    return [
        ("Set rows",                grid_defaults["rows_cleaning"], "int"),        
        ("Set columns",             grid_defaults["cols_cleaning"], "int"),     
        ("X step size",             grid_defaults["pitch_x_cleaning"], "mm"),    
        ("Y step size",             grid_defaults["pitch_y_cleaning"], "mm"),      
        ("Dispense Volume",         grid_defaults["dispense_vol_cleaning"], "uL"),
        ("grid offset x",           grid_defaults["grid_offset_x_cleaning"], "mm"),    
        ("grid offset y",           grid_defaults["grid_offset_y_cleaning"], "mm"),  
        ("spots_before_cleaning",   grid_defaults["spots_before_cleaning"], "int"), 
    ]


def get_washing_inputs(grid_defaults):
    """Washing needle configuration inputs"""
    return [
        ("Washing Depth",           grid_defaults["washing_depth"],         "mm"),        
        ("Washing Speed",           grid_defaults["washing_speed"],         "mm/s"),     
        ("Washing Upper Bound",     grid_defaults["washing_upper_bound"],   "mm"),    
        ("Washing Lower Bound",     grid_defaults["washing_lower_bound"],   "mm"),  
        ("Washing Column Offset",   grid_defaults["washing_column_offset"], "mm"),   
        ("Washing After X Spots",   grid_defaults["washing_after_x_spots"], "int"),
        ("Washing Cycles",          grid_defaults["washing_cycles"],        "int"),    
    ]
