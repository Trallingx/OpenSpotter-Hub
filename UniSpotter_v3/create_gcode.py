from tkinter import filedialog
from SpotterFunctions import read_entries
from SpotterFunctions import read_entries_as_dict
from SpotterFunctions import create_coordinates
from SpotterFunctions import select_loading_container
from SpotterFunctions import select_cleaning_containers
from input_configs import get_global_inputs, get_grid_inputs, get_cleaning_inputs
import input_configs as ic  
from input_configs import GLOBAL_INPUT_LABELS, GRID_INPUT_LABELS, CLEANING_INPUT_LABELS, WASHING_INPUT_LABELS

def generate_anchor_calibration(self):
    """
    Generate anchor calibration G-code.
    Moves needle to grid_x and grid_y offset position, lowers to z height, then elevates.
    Creates a file named "global_calibration.gcode"
    """
    filepath = filedialog.askdirectory()
    if not filepath:
        return
    
    filepath = filepath + str("/global_calibration.gcode")
    file = open(filepath, "w")

    # Get global inputs
    entry_dict = read_entries_as_dict(self.entry, GLOBAL_INPUT_LABELS)
    
    x_abs = float(entry_dict['x_cord._of_the_y-line'])
    y_abs = float(entry_dict['y_cord._of_the_x-line'])

    z_high = 40
    z_low = 4
    
    # Write start G-code
    start_gcode(file, z_high)
    
    # Write anchor calibration sequence
    file.write('; Anchor Calibration Sequence\n')
    file.write(f'G0 X{x_abs} Y{y_abs} F5000 ; Move to anchor position\n')
    file.write(f'G0 Z{z_low} F500 ; Lower needle to calibration height\n')
    file.write('G4 S1 ; Wait 1 second at calibration position\n')
    file.write(f'G0 Z{z_high} F5000 ; Raise needle to safe height\n')
    file.write('; Calibration complete\n')
    
    # End
    file.close()


def save_file(grid_count, self):
    filepath = filedialog.askdirectory()
    filepath = filepath + str("/drop_array.gcode")
    file = open(filepath, "w")

    # defining global coordinates
    entry_dict = read_entries_as_dict(self.entry, GLOBAL_INPUT_LABELS)
    
    loop_counter = 0
    x_abs = float(entry_dict['x_cord_of_y_line'])
    x_loading_calibration = 32.25
    y_abs = float(entry_dict['y_cord_of_x_line'])
    y_loading_calibration = 86
    x_offset = x_abs + float(entry_dict['tuning_offset_x'])
    x_offset_abs = x_offset
    y_offset = y_abs + float(entry_dict['tuning_offset_y'])
    y_offset_abs = y_offset
    container_z_low = float(entry_dict['container_z_height'])
    probe_x = float(entry_dict['probe_x'])
    probe_y = float(entry_dict['probe_y'])


    z_high = 40
    # code generation
    # creating the coordinates from the intersection between xline and y line which is x and y
    # absolute. From there we start at the initial offset and add the moving step size

    # writing into the file
    # start g-code
    start_gcode(file, z_high, probe_x, probe_y)

    # movement loop
    washing_spot_counter = [0]  # Use list to track across grid iterations
    for grid_idx in range(grid_count):
        # Get the correct grid object for this iteration
        grid_attr = f'grid_{grid_idx + 1}'
        grid_obj = getattr(self, grid_attr, None)
        if grid_obj is None:
            continue
        
        grid_entry_dict = read_entries_as_dict(grid_obj.grid_entry, GRID_INPUT_LABELS)
        rows = int(grid_entry_dict['set_rows'])
        cols = int(grid_entry_dict['set_columns'])
        # step size inside the grid
        x_shift = float(grid_entry_dict['x_step_size'])
        y_shift = float(grid_entry_dict['y_step_size'])
        extrude = -float(grid_entry_dict['dispense_volume'])
        emptying_container = int(grid_entry_dict['leftovers_into'])
        # z calibrations
        z_low = 4 - float(grid_entry_dict['z-adjust_down'])  # z_low = 4mm - adjustment
        z = 4
        # waiting time upon which the droplet forms
        droplet_wait_time = float(grid_entry_dict['droplet_forming_time'])
        grid_x_offset = float(grid_entry_dict['grid_offset_x'])
        grid_y_offset = float(grid_entry_dict['grid_offset_y'])

        # filling the syringe
        loading_container = int(grid_entry_dict['loading_from'])
        x_container = x_loading_calibration + 167
        y_container_4 = y_loading_calibration + 29
        y_container_3 = y_loading_calibration + 29 - 25

        # choosing between container 1 to 2
        # for second grid invert selection
        loading_syringe(file,loading_container, y_container_4, x_container, container_z_low, rows,
                    cols, extrude, z_high, x_abs, y_abs)

        # Generate and write the normal grid
        generate_grid(self, rows, cols, x_shift, y_shift, extrude, grid_x_offset, grid_y_offset,
                      x_offset, y_offset, z, z_low, z_high, container_z_low, file,
                      is_cleaning=False, droplet_wait_time=droplet_wait_time,
                      grid_obj=grid_obj, washing_spot_counter=washing_spot_counter)

        # emptying syringe
        emptying_syringe(file, emptying_container, y_container_3, 
                                y_container_4, z_high, x_container, container_z_low)

        e_abs = 0
        loop_counter = loop_counter + 1

    # presenting build plate
    file.write('G90 ;absolute positioning\nG0 Y170 F500;present print\n')
    # end writing

    file.close()
    if file is None:
        return


def start_gcode(file, z_high, probe_x = 75, probe_y = 70):
    file.write('M110 N0 ; Reset line numbers (VERY IMPORTANT);')
    file.write("\n;TYPE:Custom\nM862.3 P \"MK3\" ; printer model check")
    file.write('\nM406 ; Filament sensor off\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
    file.write('\n;Homing sequence\n')
    file.write(f'G0 Z{z_high} F3000 ;Lift Z to prevent scratching and allow leveling\n')
    file.write('G28 X0 Y0 ;Home X and Y\n')
    file.write(f'G0 X{probe_x} Y{probe_y} ; Go with probe above vacuum chuck\n')
    file.write('G28 Z0 ;Home Z\n')
    #file.write('G92 X100 Y100 Z4 E0 ;Set position to origin (allows negative Z movement)\n')
    file.write(f'G0 Z{z_high} F3000\n')
    #file.write('G1 E10 F500 ;Prime extruder\nG92 E0\n\n')

    return file


def generate_grid(self, rows, cols, x_shift, y_shift, extrude, grid_x_offset, grid_y_offset,
                  x_offset, y_offset, z, z_low, z_high, container_z_low, file,
                  is_cleaning=False, droplet_wait_time=0.5, grid_obj=None, washing_spot_counter=None):
    """
    Generic grid generation function for both normal and cleaning grids.
    
    Args:
        rows, cols: Grid dimensions
        x_shift, y_shift: Step sizes between spots
        extrude: Extrusion amount (negative for dispensing)
        grid_x_offset, grid_y_offset: Grid offsets
        x_offset, y_offset: Base position offsets
        z: Z height for movement
        z_low: Z height for spot touching
        z_high: Z height for safe movement
        container_z_low: Z height for container liquid access
        file: File object to write to
        is_cleaning: Whether this is a cleaning grid (affects some behavior)
        droplet_wait_time: Wait time for droplet formation (normal grid only)
        grid_obj: Grid object for accessing washing checkbox and inputs
        washing_spot_counter: Current spot counter (mutable list to track across calls)
    
    Returns:
        Total number of spots written
    """
    if washing_spot_counter is None:
        washing_spot_counter = [0]
    
    x_offset_start = x_offset
    y_offset_start = y_offset
    
    coordinates = create_coordinates(rows, cols,
                                     x_offset, grid_x_offset, x_shift,
                                     y_offset, grid_y_offset, y_shift,
                                     z)
    
    # Disable endstops once at start of grid
    #file.write("M211 S0 ; disable endstops for grid\n")
    
    # Write movement sequence
    for i in range(rows * cols):
        line = 'G0 ' + coordinates[i] + ' F3000' + '\n'
        file.write(line)
        # check for beginning of each row
        remainder = i % cols
        if remainder == 0:  # if beginning of row add wait to remove oscillations
            file.write("G4 S0.2\n")
        
        file.write(f'G1 E{extrude} F500\nG92 E0\nG4 S{droplet_wait_time}\n')
        
        file.write(f'G0 Z{z_low} F500 ;position for liquid contact\n')
        file.write(f'G0 Z{z} F4000\n')  # Use z variable instead of hardcoded
        
        # Track spots for washing
        washing_spot_counter[0] += 1
        
        # Check if washing should be triggered
        if not is_cleaning and grid_obj and hasattr(grid_obj, 'washing_enabled'):
            
            if grid_obj.washing_enabled.get():
                washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_INPUT_LABELS)
                washing_after_x_spots = int(washing_entry_dict['washing_after_x_spots'])
                if washing_after_x_spots > 0 and washing_spot_counter[0] % washing_after_x_spots == 0:
                    print("washing conditions met")
                    auto_washing(self, grid_obj, coordinates[i], z_high, file)

                    # perform cleaning sequence
                    if grid_obj.cleaning_enabled.get() == True:
                        auto_cleaning(grid_obj, file, x_offset, y_offset, z, z_low)
    
    # Re-enable endstops after grid
    #file.write("M211 S1 ; enable endstops\n")
    
    return rows * cols


def loading_syringe(file,loading_container, y_container_4, x_container, container_z_low, rows,
                    cols, extrude, z_high, x_abs, y_abs):
    """
    loading syringe from choosen container

    """
    y_container_load = select_loading_container(loading_container, y_container_4)

    file.write(f'G0 X{x_container} Y{y_container_load} F5000\n')
    file.write(f'G0 Z{container_z_low}  F500\n')
    total_fill = 0
    total_fill = rows * cols * -extrude
    file.write(f'G1 E{total_fill + 30} F250; Filling the syringe\n')
    file.write(f'G0 Z{z_high} F5000\n')
    file.write('G92 E0\n\n')
    file.write(f'G0 X{x_container} Y{y_container_4} F5000\n')
    file.write(f'G0 Z{container_z_low} F500\n')
    file.write('G1 E-20 F500 ; dispense first drop\nG4 S0.5\n')
    file.write(f'G0 Z{z_high} F5000\n')
    file.write(f'G0 X{x_abs} Y{y_abs} F5000\n')
    file.write('G92 E0\n\n')
    file.write(';Coordinates\n')


def emptying_syringe(file, emptying_container, y_container_3, y_container_4, z_high, x_container, container_z_low):
    """
    Select container and emptying sequence
    """
    y_container_emptying, y_container_cleaning = select_cleaning_containers(emptying_container,
                                                                            y_container_3,
                                                                            y_container_4)
    file.write(f'\nG0 Z{z_high} F1000 ; dispensing leftovers\n')
    file.write(f'G0 X{x_container} Y{y_container_emptying} F5000\n')
    file.write(f'G0 Z{container_z_low} F500\n')
    file.write('G1 E-10 F500\nG4 S1\n')
    file.write(f'G0 Z{z_high} F1000\n')

def auto_cleaning(grid_obj, file, x_abs, y_abs, z, z_low):
    """
    Generate cleaning grid based on cleaning inputs.
    Uses the same logic as the normal grid generation.
    """
    # Get cleaning grid inputs
    cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_INPUT_LABELS)
    
    cleaning_rows = int(cleaning_entry_dict['set_rows'])
    cleaning_cols = int(cleaning_entry_dict['set_columns'])
    cleaning_x_shift = float(cleaning_entry_dict['x_step_size'])
    cleaning_y_shift = float(cleaning_entry_dict['y_step_size'])
    cleaning_x_offset = float(cleaning_entry_dict['grid_offset_x'])
    cleaning_y_offset = float(cleaning_entry_dict['grid_offset_y'])
    cleaning_dispense_vol = float(cleaning_entry_dict['dispense_vol_cleaning'])
        
    file.write("\n\n; Create cleaning sequence\n")

    cleaning_coordinates = create_coordinates(cleaning_rows, cleaning_cols,
                                     x_abs, cleaning_x_offset, cleaning_x_shift,
                                     y_abs, cleaning_y_offset, cleaning_y_shift,
                                     z)
    for i in range(cleaning_rows * cleaning_cols):
        line = 'G0 ' + cleaning_coordinates[i] + ' F3000' + '\n'
        file.write(line)
        # check for beginning of each row
        remainder = i % cleaning_cols
        if remainder == 0:  # if beginning of row add wait to remove oscillations
            file.write("G4 S0.2\n")
        
        file.write(f'G1 E{cleaning_dispense_vol} F500\nG92 E0\nG4 S0.2\n')
        
        file.write(f'G0 Z{z_low} F500 ;position for liquid contact\n')
        file.write(f'G0 Z{z} F4000\n')  # Use z variable instead of hardcoded


def auto_washing(self,grid_obj, current_position, z_high, file):
    """
    Generate washing sequence with up/down needle movement.
    Called when washing checkbox is enabled and spot counter reaches washing_after_x_spots.
    
    Args:
        grid_obj: Grid object containing washing inputs and checkbox
        current_position: Current X,Y,Z position string (e.g., "X100.5 Y200.3 Z4")
        z_high: Safe Z height for movement
        file: File object to write to
    """
    # Get washing grid inputs
    washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_INPUT_LABELS)
    global_entry_dict = read_entries_as_dict(self.entry, GLOBAL_INPUT_LABELS)
    
    washing_depth = float(washing_entry_dict['washing_depth'])
    washing_speed = float(washing_entry_dict['washing_speed'])
    washing_upper_bound = float(washing_entry_dict['washing_upper_bound'])
    washing_lower_bound = float(washing_entry_dict['washing_lower_bound'])
    washing_column_offset = float(washing_entry_dict['washing_column_offset'])
    washing_cycles = int(washing_entry_dict['washing_cycles'])
    
    x_abs = float(global_entry_dict['x_cord_of_y_line'])
    y_abs = float(global_entry_dict['y_cord_of_x_line'])
    file.write("\n; Washing sequence\n")
    
    # Move to safe height
    file.write(f'G0 Z{z_high} F5000\n')
    
    # Move to washing column position with offset
    file.write(f'G0 X{x_abs+washing_column_offset} Y{y_abs+washing_upper_bound} F5000\n')
    
    # Move down to upper bound
    file.write(f'G0 Z{washing_depth} F{washing_speed}\n')
    
    # forward and backward between bounds
    for cycle in range(washing_cycles):
        # Move down to lower bound
        file.write(f'G0 Y{y_abs+washing_lower_bound} F{washing_speed}\n')        
        # Move back up to upper bound
        file.write(f'G0 Y{y_abs+washing_upper_bound} F{washing_speed}\n')

    # Return to safe height
    file.write(f'G0 Z{z_high} F5000\n')
