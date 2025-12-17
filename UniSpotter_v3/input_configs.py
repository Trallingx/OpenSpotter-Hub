"""
Centralized configuration for all input field definitions.
Each configuration is a list of tuples: (label, default_value, unit)
"""

# Define simplified input label lists (without defaults, just labels)
GLOBAL_INPUT_LABELS = [
    ("x_cord_of_y_line", None, "mm"),
    ("y_cord_of_x_line", None, "mm"),
    ("tuning_offset_x", None, "mm"),
    ("tuning_offset_y", None, "mm"),
    ("container_z_height", None, "mm"),
    ("acceptance_square_x",None, "mm"),
    ("acceptance_square_y",None, "mm"),
    ("base_square_x",None, "mm"),
    ("base_square_y",None, "mm"),
    ("grey_square_x",None, "mm"),
    ("grey_square_y",None, "mm"),
    ("probe_x",None, "mm"),
    ("probe_y",None, "mm")
]

GRID_INPUT_LABELS = [
    ("5: Set rows", None, "int"),
    ("6: Set columns", None, "int"),
    ("7: X step size", None, "mm"),
    ("8: Y step size", None, "mm"),
    ("Dispense Volume", None, "uL"),
    ("Loading from", None, "1 or 2 "),
    ("Leftovers into", None, "3 or 4"),
    ("Z-Adjust down", None, "mm"),
    ("droplet forming time", None, "s"),
    ("9: grid offset x", None, "mm"),
    ("10: grid offset y", None, "mm"),
]

CLEANING_INPUT_LABELS = [
    ("Set rows", None, "int"),
    ("Set columns", None, "int"),
    ("X step size", None, "mm"),
    ("Y step size", None, "mm"),
    ("Dispense Volume", None, "uL"),
    ("grid offset x", None, "mm"),
    ("grid offset y", None, "mm"),
    ("spots_before_cleaning", None, "int"),
]

WASHING_INPUT_LABELS = [
    ("Washing Depth", None, "mm"),
    ("Washing Speed", None, "mm/s"),
    ("Washing Upper Bound", None, "mm"),
    ("Washing Lower Bound", None, "mm"),
    ("Washing Column Offset", None, "mm"),
    ("Washing After X Spots", None, "int"),
    ("Washing Cycles", None, "int"),
]

def get_keys(file,data):
    if 'global' in file:
        keys = ['x_cord_of_y_line', 'y_cord_of_x_line', 'tuning_offset_x', 'tuning_offset_y','container_z_height', 'acceptance_square_x','acceptance_square_y','base_square_x',
                'base_square_y','grey_square_x','grey_square_y','probe_x', 'probe_y']
    elif 'grid' in file:
        keys = ['rows', 'cols', 'pitch_x', 'pitch_y', 'dispense_vol',
                'loading_from', 'loading_to', 'Z-Adjust', 'droplet_forming_time',
                'grid_offset_x', 'grid_offset_y','rows_cleaning', 'cols_cleaning',
                'pitch_x_cleaning', 'pitch_y_cleaning', 'dispense_vol_cleaning',
                'grid_offset_x_cleaning', 'grid_offset_y_cleaning', 'spots_before_cleaning',
                'washing_depth', 'washing_speed', 'washing_upper_bound', 
                'washing_lower_bound','washing_column_offset', 'washing_after_x_spots', 'washing_cycles']
    else:
        keys = [f'param_{i}' for i in range(len(data))]

    return keys

def get_global_inputs(global_defaults):
    """Global coordinate inputs"""
    return [
        ("1: X cord. of the Y-line",   global_defaults["x_cord_of_y_line"], "mm"),  # 0
        ("2: Y cord. of the X-line",   global_defaults["y_cord_of_x_line"], "mm"),  # 1
        ("3: First Spot X-offset",     global_defaults["tuning_offset_x"], "mm"),   # 2
        ("4: First Spot Y-offset",     global_defaults["tuning_offset_y"], "mm"),   # 3
        ("Container Z_Height",         global_defaults["container_z_height"], "mm"), # 4
        ("5: Acceptance Square X",     global_defaults["acceptance_square_x"], "mm"), # 4
        ("6: Acceptance Square Y",     global_defaults["acceptance_square_y"], "mm"), # 
        ("7: Base Square X",           global_defaults["base_square_x"], "mm"), # 7
        ("8: Base Square Y",           global_defaults["base_square_y"], "mm"), # 8
        ("9: Grey Square X",           global_defaults["grey_square_x"], "mm"), # 9
        ("10: Grey Square Y",          global_defaults["grey_square_y"], "mm"), # 10
        ("11: Probe Homing Position X",global_defaults["probe_x"], "mm"),
        ("12: Probe Homing Position Y",global_defaults["probe_y"], "mm")
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
