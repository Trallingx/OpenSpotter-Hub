from tkinter import filedialog
from SpotterFunctions import read_entries_as_dict
from SpotterFunctions import build_containers
from SpotterFunctions import write_generation_settings_file
from input_configs import GLOBAL_FIELDS, GRID_FIELDS, CLEANING_FIELDS, WASHING_FIELDS
from spotter_gcode import (
    start_gcode,
    write_anchor_calibration_sequence,
    generate_grid,
    emptying_syringe,
    present_build_plate,
    auto_cleaning_grid,
)


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
    
    # Utility parameters for probe and timing
    probe_ram_height = float(entry_dict.get('probe_ram_height', 110.0))
    probe_return_height = float(entry_dict.get('probe_return_height', 105.0))
    calibration_height = float(entry_dict.get('calibration_height', 0.0))
    calibration_wait = float(entry_dict.get('calibration_wait', 1.0))
    probe_feed_rate = float(entry_dict.get('probe_feed_rate', 300.0))
    calibration_feed_rate = float(entry_dict.get('calibration_feed_rate', 300.0))
    
    
    with open(filepath, "w") as file:
        # Write start G-code
        start_gcode(
            file, z_high, probe_x, probe_y, speed, decent_speed, adcent_speed, acceptance_square,
            probe_ram_height=probe_ram_height,
            probe_return_height=probe_return_height,
            calibration_height=calibration_height,
            calibration_wait=calibration_wait,
            probe_feed_rate=probe_feed_rate,
            calibration_feed_rate=calibration_feed_rate,
        )
        
        write_anchor_calibration_sequence(
            file,
            x_abs,
            y_abs,
            z_low,
            z_high,
            speed,
            decent_speed,
            adcent_speed,
            calibration_wait=calibration_wait,
        )


def save_file(self):
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
    max_syringe_mm = float(entry_dict.get('max_syringe_mm', 50.0))
    min_syringe_mm = float(entry_dict.get('min_syringe_mm', 0.0))

    # Utility parameters for probe and timing
    probe_ram_height = float(entry_dict.get('probe_ram_height', 110.0))
    probe_return_height = float(entry_dict.get('probe_return_height', 105.0))
    calibration_height = float(entry_dict.get('calibration_height', 0.0))
    present_plate_y = float(entry_dict.get('present_plate_y', 170.0))
    present_plate_speed = float(entry_dict.get('present_plate_speed', 2000.0))
    row_start_wait = float(entry_dict.get('row_start_wait', 0.2))
    calibration_wait = float(entry_dict.get('calibration_wait', 1.0))
    emptying_wait = float(entry_dict.get('emptying_wait', 1.0))
    rinse_aspiration_wait = float(entry_dict.get('rinse_aspiration_wait', 0.5))
    rinse_final_wait = float(entry_dict.get('rinse_final_wait', 2.0))
    probe_feed_rate = float(entry_dict.get('probe_feed_rate', 300.0))
    calibration_feed_rate = float(entry_dict.get('calibration_feed_rate', 300.0))
    syringe_aspirate_wait = float(entry_dict.get('syringe_aspirate_wait', 2.0))
    syringe_prime_wait = float(entry_dict.get('syringe_prime_wait', 2.0))

    z_movement_pos_low = float(entry_dict['z_movement_pos_low'])
    z_movement_pos_high = float(entry_dict['z_movement_pos_high'])
    syringe_leftovers = [0.0]  # Track remaining syringe travel in mm

    settings_snapshot = {
        "global_settings": dict(entry_dict),
        "runtime_values": {
            "x_offset": x_offset,
            "y_offset": y_offset,
            "acceptance_square_x_left": acceptance_square['x_left'],
            "acceptance_square_x_right": acceptance_square['x_right'],
            "acceptance_square_y_bottom": acceptance_square['y_bottom'],
            "acceptance_square_y_top": acceptance_square['y_top'],
            "mesh_points": mesh_points,
        },
        "grid_settings": [],
    }
    
    # code generation
    # creating the coordinates from the intersection between xline and y line which is x and y
    # absolute. From there we start at the initial offset and add the moving step size

    # writing into the file
    # start g-code
    with open(filepath, "w") as file:
        start_gcode(
            file, z_movement_pos_high, probe_x, probe_y, speed, decent_speed, adcent_speed, 
            acceptance_square, mesh_points,
            probe_ram_height=probe_ram_height,
            probe_return_height=probe_return_height,
            calibration_height=calibration_height,
            calibration_wait=calibration_wait,
            probe_feed_rate=probe_feed_rate,
            calibration_feed_rate=calibration_feed_rate,
        )

    # movement loop
        washing_spot_counter = [0]  # Use list to track across grid iterations
        for _, grid_obj in sorted(self.grid_tab_dict.items()):
            
            grid_entry_dict = read_entries_as_dict(grid_obj.grid_entry, GRID_FIELDS)
            cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
            washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
            grid_number = len(settings_snapshot["grid_settings"]) + 1

            settings_snapshot["grid_settings"].append({
                "grid_number": grid_number,
                "grid": dict(grid_entry_dict),
                "cleaning": dict(cleaning_entry_dict),
                "washing": dict(washing_entry_dict),
                "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
                "washing_enabled": bool(grid_obj.washing_enabled.get()),
                "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
            })

            rows = int(grid_entry_dict['rows'])
            cols = int(grid_entry_dict['cols'])
            # step size inside the grid
            x_shift = float(grid_entry_dict['pitch_x'])
            y_shift = float(grid_entry_dict['pitch_y'])
            extrude = float(grid_entry_dict['dispense_vol'])
            row_add_volume = float(grid_entry_dict.get('row_add_volume', 0.0))
            
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

            
            # for second grid invert selection
            total_fill = 0
            if (rows * cols * extrude) >= max_syringe_vol:
                total_fill = max_syringe_vol
            else:
                total_fill = rows * cols * extrude

            priming_vol = float(entry_dict['priming_vol'])

            # Generate and write the normal grid
            generate_grid(
                self,
                rows,
                cols,
                x_shift,
                y_shift,
                extrude,
                row_add_volume,
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
                priming_vol=priming_vol,
                refill=total_fill,
                syringe_tracker=syringe_leftovers,
                row_start_wait=row_start_wait,
                syringe_aspirate_wait=syringe_aspirate_wait,
                syringe_prime_wait=syringe_prime_wait,
                cleaning_anchor_x=x_abs,
                cleaning_anchor_y=y_abs,
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
                final_rinse_enabled=bool(grid_obj.final_rinse_enabled.get()),
                rinsing_cycles=int(cleaning_entry_dict.get('final_rinse_cycles', 1)),
                max_syringe_mm=max_syringe_mm,
                min_syringe_mm=min_syringe_mm,
                emptying_wait=emptying_wait,
                rinse_aspiration_wait=rinse_aspiration_wait,
                rinse_final_wait=rinse_final_wait,
                syringe_tracker=syringe_leftovers,
            )

            # Add final cleaning grid if enabled
            if (bool(grid_obj.final_rinse_enabled.get()) and 
                bool(grid_obj.final_rinse_add_cleaning_grid.get())):
                auto_cleaning_grid(
                    grid_obj,
                    file,
                    x_abs,
                    y_abs,
                    z_contact,
                    z_movement_pos_low,
                    z_movement_pos_high,
                    speed=speed,
                    decent_speed=decent_speed,
                    adcent_speed=adcent_speed,
                    dispensing_speed=dispensing_speed,
                    refilling_speed=refilling_speed,
                    syringe_tracker=syringe_leftovers,
                    row_start_wait=row_start_wait,
                )

            loop_counter = loop_counter + 1

        # presenting build plate
        present_build_plate(file, present_plate_y=present_plate_y, present_plate_speed=present_plate_speed)

    settings_path = write_generation_settings_file(filepath, settings_snapshot)
    print(f"✅ Saved generation settings to {settings_path}")
