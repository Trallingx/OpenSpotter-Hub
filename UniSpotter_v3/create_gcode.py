from tkinter import filedialog
from SpotterFunctions import read_entries_as_dict
from SpotterFunctions import create_coordinates
from SpotterFunctions import build_containers
from input_configs import GLOBAL_FIELDS, GRID_FIELDS, WASHING_FIELDS, CLEANING_FIELDS


def _prompt_save_path(default_filename: str):
    """Ask for a save location with a sensible default name and overwrite existing files."""
    return filedialog.asksaveasfilename(
        defaultextension=".gcode",
        initialfile=default_filename,
        filetypes=[("G-code files", "*.gcode"), ("All files", "*.*")],
        confirmoverwrite=False,
    )


def _compute_acceptance_square(entry_dict):
    """
    Convert acceptance square size + base origin into printer coordinates.
    Keeps canvas orientation (bottom-left is minimum X/Y).
    """
    base_x = float(entry_dict['base_square_x'])
    base_y = float(entry_dict['base_square_y'])
    acceptance_x = float(entry_dict['acceptance_square_x'])
    acceptance_y = float(entry_dict['acceptance_square_y'])
    x_abs = float(entry_dict['x_cord_of_y_line'])
    y_abs = float(entry_dict['y_cord_of_x_line'])

    x_left = x_abs + (base_x - acceptance_x) / 2
    y_bottom = y_abs + (base_y - acceptance_y) / 2

    return {
        'x_left': x_left,
        'x_right': x_left + acceptance_x,
        'y_bottom': y_bottom,
        'y_top': y_bottom + acceptance_y,
    }

def generate_anchor_calibration(self):
    """
    Generate anchor calibration G-code.
    Moves needle to grid_x and grid_y offset position, lowers to z height, then elevates.
    Creates a file named "global_calibration.gcode"
    """
    filepath = _prompt_save_path("global_calibration.gcode")
    if not filepath:
        return

    # Get global inputs
    entry_dict = read_entries_as_dict(self.entry, GLOBAL_FIELDS)
    
    x_abs = float(entry_dict['x_cord_of_y_line'])
    y_abs = float(entry_dict['y_cord_of_x_line'])

    z_high = float(entry_dict['z_movement_pos'])
    z_low = float(entry_dict['z_zero_pos'])

    speed = float(entry_dict['movement_speed'])
    decent_speed = float(entry_dict['decent_speed'])
    adcent_speed = float(entry_dict['adcent_speed'])
    probe_x = float(entry_dict['probe_x'])
    probe_y = float(entry_dict['probe_y'])
    acceptance_square = _compute_acceptance_square(entry_dict)
    
    
    with open(filepath, "w") as file:
        # Write start G-code
        start_gcode(file, z_high, probe_x, probe_y, speed, decent_speed, adcent_speed, acceptance_square)
        
        # Write anchor calibration sequence
        file.write('; Anchor Calibration Sequence\n')
        file.write(f'G0 X{x_abs} Y{y_abs} F{speed} ; Move to anchor position\n')
        file.write(f'G0 Z{z_low} F{decent_speed} ; Lower needle to calibration height\n')
        file.write('G4 S1 ; Wait 1 second at calibration position\n')
        file.write(f'G0 Z{z_high} F{adcent_speed} ; Raise needle to safe height\n')
        file.write('; Calibration complete\n')


def save_file(grid_count, self):
    filepath = _prompt_save_path("drop_array.gcode")
    if not filepath:
        return

    # defining global coordinates
    entry_dict = read_entries_as_dict(self.entry, GLOBAL_FIELDS)
    
    loop_counter = 0
    x_abs = float(entry_dict['x_cord_of_y_line'])
    y_abs = float(entry_dict['y_cord_of_x_line'])
    y_offset = y_abs + float(entry_dict['tuning_offset_y'])
    x_offset = x_abs + float(entry_dict['tuning_offset_x'])
    containers = build_containers(entry_dict)

    probe_x = float(entry_dict['probe_x'])
    probe_y = float(entry_dict['probe_y'])
    acceptance_square = _compute_acceptance_square(entry_dict)
    mesh_points = int(entry_dict['mesh_points'])

    speed = float(entry_dict['movement_speed'])
    decent_speed = float(entry_dict['decent_speed'])
    adcent_speed = float(entry_dict['adcent_speed'])
    
    dispensing_speed = float(entry_dict['dispensing_speed'])
    refilling_speed = float(entry_dict['refilling_speed'])

    max_syringe_vol = float(entry_dict['max_syringe_vol'])

    z_movement_pos_low = float(entry_dict['z_movement_pos_low'])
    z_movement_pos_high = float(entry_dict['z_movement_pos_high'])
    syringe_leftovers = [0.0]  # Track net loaded minus dispensed volume
    
    # code generation
    # creating the coordinates from the intersection between xline and y line which is x and y
    # absolute. From there we start at the initial offset and add the moving step size

    # writing into the file
    # start g-code
    with open(filepath, "w") as file:
        start_gcode(file, z_movement_pos_high, probe_x, probe_y, speed, decent_speed, adcent_speed, acceptance_square, mesh_points)

    # movement loop
        washing_spot_counter = [0]  # Use list to track across grid iterations
        for grid_idx in range(grid_count):
            # Get the correct grid object for this iteration
            grid_attr = f'grid_{grid_idx + 1}'
            grid_obj = getattr(self, grid_attr, None)
            if grid_obj is None:
                continue
            
            grid_entry_dict = read_entries_as_dict(grid_obj.grid_entry, GRID_FIELDS)
            rows = int(grid_entry_dict['rows'])
            cols = int(grid_entry_dict['cols'])
            # step size inside the grid
            x_shift = float(grid_entry_dict['pitch_x'])
            y_shift = float(grid_entry_dict['pitch_y'])
            extrude = -float(grid_entry_dict['dispense_vol'])
            
            # z calibrations
            z_contact = float(grid_entry_dict['z_contact']) 

            # waiting time upon which the droplet forms
            droplet_wait_time = float(grid_entry_dict['droplet_forming_time'])
            grid_x_offset = float(grid_entry_dict['grid_offset_x'])
            grid_y_offset = float(grid_entry_dict['grid_offset_y'])

            # filling the syringe
            loading_container_id = int(grid_entry_dict['loading_from'])
            emptying_container_id = int(grid_entry_dict['leftovers_into'])

            if not (1 <= loading_container_id <= 6):
                raise ValueError("Loading container must be an integer between 1 and 6")
            if not (1 <= emptying_container_id <= 6):
                raise ValueError("Leftovers container must be an integer between 1 and 6")
            loading_container = containers.get(loading_container_id)
            emptying_container = containers.get(emptying_container_id)

            if loading_container is None:
                raise ValueError(f"Container {loading_container_id} is not configured for loading")
            if emptying_container is None:
                raise ValueError(f"Container {emptying_container_id} is not configured for emptying")

            # choosing between container 1 to 2
            # for second grid invert selection
            total_fill = 0
            if (rows * cols * -extrude) >= max_syringe_vol:
                total_fill = max_syringe_vol
            else:
                total_fill = rows * cols * -extrude

            loading_syringe(
                file,
                loading_container,
                z_movement_pos_high,
                speed,
                decent_speed,
                adcent_speed,
                refilling_speed,
                total_fill=total_fill,
                syringe_tracker=syringe_leftovers,
            )

            # Generate and write the normal grid
            generate_grid(
                self,
                rows,
                cols,
                x_shift,
                y_shift,
                extrude,
                grid_x_offset,
                grid_y_offset,
                x_offset,
                y_offset,
                z_contact,
                z_movement_pos_low,
                z_movement_pos_high,
                containers,
                file,
                is_cleaning=False,
                droplet_wait_time=droplet_wait_time,
                grid_obj=grid_obj,
                washing_spot_counter=washing_spot_counter,
                speed=speed,
                decent_speed=decent_speed,
                adcent_speed=adcent_speed,
                dispensing_speed=dispensing_speed,
                refilling_speed=refilling_speed,
                loading_container=loading_container_id,
                max_syringe_vol=max_syringe_vol,
                refill=total_fill,
                syringe_tracker=syringe_leftovers,
            )

            # emptying syringe
            emptying_syringe(
                file,
                emptying_container,
                z_movement_pos_high,
                speed,
                decent_speed,
                adcent_speed,
                dispensing_speed,
                refilling_speed,
                syringe_tracker=syringe_leftovers,
            )

            loop_counter = loop_counter + 1

        # presenting build plate
        file.write('G90 ;absolute positioning\nG0 Y170 F500;present print\n')
    
def start_gcode(file, z_movement_pos_high, probe_x = 75, probe_y = 70, speed = 5000, decent_speed = 500, adcent_speed = 5000, acceptance_square = None, mesh_points = 3):
    if acceptance_square is None:
        raise ValueError("acceptance_square bounds must be provided")
    
    # Start G-code with homing
    file.write('\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
    file.write('\n;Homing sequence\n')
    file.write('M117 Gantry Align\n')
    file.write('G28 Z0 ;Home Z\n')
    file.write('G28 X0 Y0 ;Home X Y\n')


    # Manual Z tilt compensation with ramming
    file.write(f'G0 X{probe_x} Y{probe_y} F{speed} ; Go with Head to probe position\n')
    # Disable stall detection temporarily (prevents retrigger)
    file.write('SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=0\n')
    file.write('G91 ;use relative coordinates\n')
    file.write('G0 Z10 F300 ; Ram into top\n')
    file.write('G90 ;use absolute coordinates\n')
    # Enable stall detection 
    file.write('SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=4\n')
    file.write('G28 Z0; Home Z again\n')
    file.write('M117 Aligned\n')

    #Mesh bed leveling within acceptance square to compensate for any remaining tilt and ensure proper Z=0 calibration across the print area. Uses the computed acceptance square bounds and mesh points from global inputs.
    file.write(
        f"MESH X_MIN={acceptance_square['x_left']:.3f} X_MAX={acceptance_square['x_right']:.3f} "
        f"Y_MIN={acceptance_square['y_bottom']:.3f} Y_MAX={acceptance_square['y_top']:.3f} POINTS={mesh_points} ;Home Z with mesh bed leveling inside acceptance square\n"
    )

    # Homing Syringe
    file.write(f'G0 X{probe_x} Y{probe_y} F{speed}; Go with probe above vacuum chuck\n')
    file.write('HOME_SYRINGE\n')
    file.write('DISPENSE VOLUME=1 \n')
    file.write('G1 Z0 F300 \n')
    file.write('M117 ;Calibrate Needle to touch substrate\n')
    file.write('PAUSE\n')
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
   
    return file


def generate_grid(
    self,
    rows,
    cols,
    x_shift,
    y_shift,
    extrude,
    grid_x_offset,
    grid_y_offset,
    x_offset,
    y_offset,
    z_contact,
    z_movement_pos_low,
    z_movement_pos_high,
    containers,
    file,
    loading_container,
    refill,
    is_cleaning=False,
    droplet_wait_time=0.5,
    grid_obj=None,
    washing_spot_counter=None,
    speed=5000,
    decent_speed=500,
    adcent_speed=5000,
    dispensing_speed=500,
    refilling_speed=250,
    max_syringe_vol=10,
    syringe_tracker=None,
):
    """Generate grid G-code and track syringe volume usage."""
    if washing_spot_counter is None:
        washing_spot_counter = [0]
    if syringe_tracker is None:
        syringe_tracker = [0.0]

    coordinates = create_coordinates(
        rows,
        cols,
        x_offset,
        grid_x_offset,
        x_shift,
        y_offset,
        grid_y_offset,
        y_shift,
        z_movement_pos_low,
    )

    spot_counter = 0

    loading_container_obj = containers.get(loading_container)
    if loading_container_obj is None:
        raise ValueError(f"Missing configuration for container {loading_container}")

    if grid_obj.cleaning_enabled.get():
        auto_cleaning(
            grid_obj,
            file,
            x_offset,
            y_offset,
            z_contact,
            z_movement_pos_low,
            z_movement_pos_high,
            syringe_tracker=syringe_tracker,
        )

    for i in range(rows * cols):
        line = 'G0 ' + coordinates[i] + f' F{speed}' + '\n'
        file.write(line)

        if i % cols == 0:
            file.write("G4 S0.2\n")

        file.write(f'DISPENSE VOLUME={extrude} F{dispensing_speed}\nG4 S{droplet_wait_time}\n')
        syringe_tracker[0] = max(0.0, syringe_tracker[0] - (-extrude))

        file.write(f'G0 Z{z_contact} F{decent_speed} ;position for liquid contact\n')
        file.write(f'G0 Z{z_movement_pos_low} F{adcent_speed}\n')

        washing_spot_counter[0] += 1
        spot_counter += 1

        if float(spot_counter) * (-extrude) >= max_syringe_vol:
            file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
            loading_syringe(
                file,
                loading_container_obj,
                z_movement_pos_high,
                speed,
                decent_speed,
                adcent_speed,
                refilling_speed,
                total_fill=refill,
                syringe_tracker=syringe_tracker,
            )
            file.write(f"G0 X50 Y50 F{speed}")
            if grid_obj.cleaning_enabled.get():
                auto_cleaning(
                    grid_obj,
                    file,
                    x_offset,
                    y_offset,
                    z_contact,
                    z_movement_pos_low,
                    z_movement_pos_high,
                    syringe_tracker=syringe_tracker,
                )
            spot_counter = 0

        if not is_cleaning and grid_obj and hasattr(grid_obj, 'washing_enabled'):
            if grid_obj.washing_enabled.get():
                washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
                washing_after_x_spots = int(washing_entry_dict['washing_after_x_spots'])
                if washing_after_x_spots > 0 and washing_spot_counter[0] % washing_after_x_spots == 0:
                    auto_washing(self, grid_obj, z_movement_pos_high, file)

                    if grid_obj.cleaning_enabled.get():
                        auto_cleaning(
                            grid_obj,
                            file,
                            x_offset,
                            y_offset,
                            z_contact,
                            z_movement_pos_low,
                            z_movement_pos_high,
                            syringe_tracker=syringe_tracker,
                        )

    return rows * cols


def loading_syringe(
    file,
    container,
    z_movement_pos_high,
    speed=5000,
    decent_speed=500,
    adcent_speed=5000,
    refilling_speed=250,
    total_fill=10,
    syringe_tracker=None,
):
    """
    loading syringe from chosen container

    """
    if container is None:
        raise ValueError("Loading container is not configured")

    file.write(f'G0 X{container.x} Y{container.y} F{speed}\n')
    file.write(f'G0 Z{container.z_filling_height}  F{decent_speed}\n')
    file.write(f'DISPENSE VOLUME={total_fill+3} F{refilling_speed}; Filling the syringe\n')
    file.write('G4 S2\n')
    file.write('G92 E0\n\n')
    file.write(f'DISPENSE VOLUME={-3} F{refilling_speed/2}; Prevent backlash the syringe\n')
    file.write('G4 S2\n')
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
    file.write('G92 E0\n\n')

    if syringe_tracker is not None:
        syringe_tracker[0] += total_fill



def emptying_syringe(
    file,
    container,
    z_movement_pos_high,
    speed=5000,
    decent_speed=500,
    adcent_speed=5000,
    dispensing_speed=500,
    refilling_speed=250,
    syringe_tracker=None,
):
    """
    Select container and emptying sequence
    """
    if container is None:
        raise ValueError("Emptying container is not configured")
    file.write(f'\nG0 Z{z_movement_pos_high} F{adcent_speed} ; dispensing leftovers\n')
    file.write(f'G0 X{container.x} Y{container.y} F{speed}\n')
    file.write(f'G0 Z{container.z_filling_height} F{decent_speed}\n')

    leftovers = 0.0 if syringe_tracker is None else max(0.0, syringe_tracker[0])
    if leftovers > 0:
        file.write(f'DISPENSE VOLUME={-leftovers:.4f} F{dispensing_speed}\nG4 S1\n')
        syringe_tracker[0] = 0.0
    else:
        file.write('; No syringe leftovers to purge\n')

    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')

def auto_cleaning(
    grid_obj,
    file,
    x_abs,
    y_abs,
    z_contact,
    z_movement_pos_low,
    z_movement_pos_high,
    speed=5000,
    decent_speed=500,
    adcent_speed=5000,
    dispensing_speed=500,
    refilling_speed=250,
    z_high=40,
    syringe_tracker=None,
):
    """
    Generate cleaning grid based on cleaning inputs.
    Uses the same logic as the normal grid generation.
    """
    # Get cleaning grid inputs
    cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
    
    cleaning_rows = int(cleaning_entry_dict['rows_cleaning'])
    cleaning_cols = int(cleaning_entry_dict['cols_cleaning'])
    cleaning_x_shift = float(cleaning_entry_dict['pitch_x_cleaning'])
    cleaning_y_shift = float(cleaning_entry_dict['pitch_y_cleaning'])
    cleaning_x_offset = float(cleaning_entry_dict['grid_offset_x_cleaning'])
    cleaning_y_offset = float(cleaning_entry_dict['grid_offset_y_cleaning'])
    cleaning_dispense_vol = -float(cleaning_entry_dict['dispense_vol_cleaning'])
        
    file.write("\n\n; Create cleaning sequence\n")

    cleaning_coordinates = create_coordinates(cleaning_rows, cleaning_cols,
                                     x_abs, cleaning_x_offset, cleaning_x_shift,
                                     y_abs, cleaning_y_offset, cleaning_y_shift,
                                     z_movement_pos_low)
    line = 'G0' +f' X{cleaning_x_offset}' + f' Y{cleaning_y_offset}' +f' Z{z_movement_pos_high}'+ f' F{speed}' + '\n'
    file.write(line)
    for i in range(cleaning_rows * cleaning_cols):
        line = 'G0 ' + cleaning_coordinates[i] + f' F{speed}' + '\n'
        file.write(line)
        # check for beginning of each row
        remainder = i % cleaning_cols
        if remainder == 0:  # if beginning of row add wait to remove oscillations
            file.write("G4 S0.2\n")
        
        file.write(f'DISPENSE VOLUME={cleaning_dispense_vol} F{dispensing_speed}\nG92 E0\nG4 S0.2\n')
        if syringe_tracker is not None:
            syringe_tracker[0] = max(0.0, syringe_tracker[0] - (-cleaning_dispense_vol))
        
        file.write(f'G0 Z{z_contact} F{decent_speed} ;position for liquid contact\n')
        file.write(f'G0 Z{z_movement_pos_low} F{adcent_speed}\n')  


def auto_washing(self,grid_obj, z_movement_pos_high, file, speed = 5000, decent_speed = 500, adcent_speed = 5000,
                     dispensing_speed= 500, refilling_speed = 250):
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
    washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
    global_entry_dict = read_entries_as_dict(self.entry, GLOBAL_FIELDS)
    
    washing_depth = float(washing_entry_dict['washing_depth'])
    washing_speed = float(washing_entry_dict['washing_speed'])
    washing_x_pos = float(washing_entry_dict['washing_x_pos'])
    washing_y_pos = float(washing_entry_dict['washing_y_pos'])
    washing_line_lenght = float(washing_entry_dict['washing_line_lenght'])
    washing_cycles = int(washing_entry_dict['washing_cycles'])
    
    x_abs = float(global_entry_dict['x_cord_of_y_line'])
    y_abs = float(global_entry_dict['y_cord_of_x_line'])
    file.write("\n; Washing sequence\n")
    
    # Move to safe height
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
    
    # Move to washing column position with offset
    file.write(f'G0 X{x_abs+washing_x_pos} Y{y_abs+washing_y_pos} F{speed}\n')
    
    # Move down to upper bound
    file.write(f'G0 Z{washing_depth} F{decent_speed}\n')
    
    # forward and backward between bounds
    for cycle in range(washing_cycles):
        # Move down to lower bound
        file.write(f'G0 X{x_abs+washing_x_pos+washing_line_lenght} F{washing_speed}\n')        
        # Move back up to upper bound
        file.write(f'G0 X{x_abs+washing_x_pos} F{washing_speed}\n')

    # Return to safe height
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
    file.write('G0 X50 Y50 F5000\n')
