from .SpotterFunctions import read_entries_as_dict, create_coordinates, volume_to_mm
from .input_configs import WASHING_FIELDS, CLEANING_FIELDS


def start_gcode(file, z_movement_pos_high, probe_x=75, probe_y=70, speed=5000, decent_speed=500, adcent_speed=5000, acceptance_square=None, mesh_points=3, probe_ram_height=110.0, probe_return_height=105.0, calibration_height=0.0, calibration_wait=1.0, probe_feed_rate=300.0, calibration_feed_rate=300.0):
    if acceptance_square is None:
        raise ValueError("acceptance_square bounds must be provided")

    file.write('\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
    file.write('\n;Homing sequence\n')
    file.write('M117 Gantry Align\n')
    file.write('G28 Z0 ;Home Z\n')
    file.write('G28 Y0 ;Home Y\n')
    file.write(f'G0 Z35 F{adcent_speed};Move to X Homing position\n')
    file.write('G28 X0 ;Home X\n')

    file.write(f'G0 X{probe_x} Y{probe_y} F{speed} ; Go with Head to probe position\n')
    file.write('SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=0\n')
    file.write(f'G0 Z{probe_ram_height} F{probe_feed_rate} ; Ram into top\n')
    file.write(f'G0 Z{probe_return_height} F{probe_feed_rate} ; Back down\n')
    file.write('SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=4\n')
    file.write('G28 Z0; Home Z again\n')
    file.write('G28 Z0; Home Z again\n')
    file.write('M117 Aligned\n')

    file.write(
        f"MESH X_MIN={acceptance_square['x_left']:.3f} X_MAX={acceptance_square['x_right']:.3f} "
        f"Y_MIN={acceptance_square['y_bottom']:.3f} Y_MAX={acceptance_square['y_top']:.3f} POINTS={mesh_points} ;Home Z with mesh bed leveling inside acceptance square\n"
    )

    file.write(f'G0 X{probe_x} Y{probe_y} F{speed}; Go with probe above vacuum chuck\n')
    file.write('HOME_SYRINGE\n')
    file.write('DISPENSE MM=0\n')
    file.write(f'G1 Z{calibration_height} F{calibration_feed_rate} \n')
    file.write('M117 ;Calibrate Needle to touch substrate\n')
    file.write('PAUSE\n')
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')

    return file


def write_anchor_calibration_sequence(file, x_abs, y_abs, z_low, z_high, speed, decent_speed, adcent_speed, calibration_wait=1.0):
    file.write('; Anchor Calibration Sequence\n')
    file.write(f'G0 X{x_abs} Y{y_abs} F{speed} ; Move to anchor position\n')
    file.write(f'G0 Z{z_low} F{decent_speed} ; Lower needle to calibration height\n')
    file.write(f'WAIT S={calibration_wait} ; Wait at calibration position\n')
    file.write(f'G0 Z{z_high} F{adcent_speed} ; Raise needle to safe height\n')
    file.write('; Calibration complete\n')


def present_build_plate(file, present_plate_y=170.0, present_plate_speed=2000.0):
    file.write(f'G90 ;absolute positioning\nG0 Y{present_plate_y} F{present_plate_speed};present print\n')


def generate_grid(
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
    priming_vol=3.0,
    syringe_tracker=None,
    row_start_wait=0.2,
    syringe_aspirate_wait=2.0,
    syringe_prime_wait=2.0,
    cleaning_anchor_x=None,
    cleaning_anchor_y=None,
    cleaning_cycle_counter=None,
):
    if washing_spot_counter is None:
        washing_spot_counter = [0]
    if syringe_tracker is None:
        syringe_tracker = [0.0]
    if cleaning_anchor_x is None:
        cleaning_anchor_x = x_offset
    if cleaning_anchor_y is None:
        cleaning_anchor_y = y_offset
    if cleaning_cycle_counter is None:
        cleaning_cycle_counter = [0]

    def reset_washing_counter():
        washing_spot_counter[0] = 0

    coordinates = create_coordinates(
        rows,
        cols,
        x_offset,
        grid_x_offset,
        x_shift,
        y_offset,
        grid_y_offset,
        y_shift,
    )

    loading_container_obj = containers.get(loading_container)
    if loading_container_obj is None:
        raise ValueError(f"Missing configuration for container {loading_container}")

    refill_mm_cap = volume_to_mm(refill)
    mm_per_ul = volume_to_mm(1.0)
    if mm_per_ul <= 0:
        raise ValueError("volume_to_mm(1.0) must be positive")

    # Pre-compute cleaning grid volume per reload (will run after each reload if cleaning is enabled).
    cleaning_grid_volume_per_reload_mm = 0.0
    if grid_obj and hasattr(grid_obj, 'cleaning_enabled') and grid_obj.cleaning_enabled.get():
        cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
        cleaning_rows = int(cleaning_entry_dict.get('rows_cleaning', 0))
        cleaning_cols = int(cleaning_entry_dict.get('cols_cleaning', 0))
        cleaning_dispense_vol = float(cleaning_entry_dict.get('dispense_vol_cleaning', 0.0))
        cleaning_grid_volume_per_reload_mm = volume_to_mm(cleaning_rows * cleaning_cols * cleaning_dispense_vol)

    # Pre-compute spot volumes for all remaining spots calculation.
    spot_volumes_mm = []
    base_spot_mm = volume_to_mm(extrude)
    for spot_idx in range(rows * cols):
        spot_extrude = extrude
        if cols > 0 and spot_idx % cols == 0 and spot_idx != 0:
            spot_extrude += row_add_volume
        spot_volumes_mm.append(volume_to_mm(spot_extrude))
    
    # Reserve: always keep buffer for 1 base spot to avoid edge-case reloads.
    reserve_volume_mm = base_spot_mm

    def ensure_loaded(required_mm=0.0, current_spot_index=None):
        """Reload syringe when remaining plunger travel is insufficient.
        Dynamically calculates refill as min(remaining_spots + cleaning + reserve, refill_cap).
        """
        did_reload = False
        eps = 1e-6
        if syringe_tracker[0] <= eps or (syringe_tracker[0] + eps) < required_mm:
            did_reload = True
            # Calculate remaining volume needed from current spot to grid end.
            remaining_spots_mm = 0.0
            if current_spot_index is not None and 0 <= current_spot_index < len(spot_volumes_mm):
                remaining_spots_mm = sum(spot_volumes_mm[current_spot_index:])
            
            # Total: remaining spots + cleaning volume (runs after reload) + reserve buffer.
            total_needed_mm = remaining_spots_mm + cleaning_grid_volume_per_reload_mm + reserve_volume_mm
            
            # Use min(needed, cap) to avoid waste but fill to cap if needed.
            target_fill_mm = min(total_needed_mm, refill_mm_cap) if total_needed_mm > 0 else refill_mm_cap

            file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
            file.write(
                f'; Dynamic refill: {target_fill_mm:.3f} mm ({target_fill_mm / mm_per_ul:.3f} uL) '
                f'[spots={remaining_spots_mm:.3f} mm + cleaning={cleaning_grid_volume_per_reload_mm:.3f} mm + '
                f'reserve={reserve_volume_mm:.3f} mm = {total_needed_mm:.3f} mm, cap={refill_mm_cap:.3f} mm]\n'
            )
            loading_syringe(
                file,
                loading_container_obj,
                z_movement_pos_high,
                speed,
                decent_speed,
                adcent_speed,
                refilling_speed,
                dispensing_speed,
                total_fill=(target_fill_mm / mm_per_ul),
                priming_vol=priming_vol,
                syringe_tracker=syringe_tracker,
                syringe_aspirate_wait=syringe_aspirate_wait,
                syringe_prime_wait=syringe_prime_wait,
            )

            if should_wash_after_loading():
                    auto_washing(self, grid_obj, z_movement_pos_high, file)
                    reset_washing_counter()

            if grid_obj.cleaning_enabled.get():
                auto_cleaning_grid(
                    grid_obj,
                    file,
                    cleaning_anchor_x,
                    cleaning_anchor_y,
                    z_contact,
                    z_movement_pos_low,
                    z_movement_pos_high,
                    syringe_tracker=syringe_tracker,
                    row_start_wait=row_start_wait,
                    cleaning_cycle_counter=cleaning_cycle_counter,
                )
        return did_reload

    def should_wash_after_loading():
        if is_cleaning or not grid_obj:
            return False
        if not hasattr(grid_obj, 'washing_enabled') or not grid_obj.washing_enabled.get():
            return False
        if not hasattr(grid_obj, 'wash_after_loading_enabled'):
            return False
        return bool(grid_obj.wash_after_loading_enabled.get())


    if grid_obj.cleaning_enabled.get():
        ensure_loaded(current_spot_index=0)
        reset_washing_counter()

    file.write(f'M117; Main Grid {grid_obj.get_grid_name()}\n')

    for i in range(rows * cols):
        current_extrude = extrude
        if cols > 0 and i % cols == 0 and i != 0:
            current_extrude += row_add_volume
        extrude_mm = volume_to_mm(current_extrude)
        ensure_loaded(required_mm=extrude_mm, current_spot_index=i)

        line = 'G0 ' + coordinates[i] + f' F{speed}' + '\n'
        file.write(line)
        file.write(f'G0 Z{z_movement_pos_low} F{decent_speed}\n')

        if i % cols == 0:
            file.write(f"WAIT S={row_start_wait}\n") # against oscillations at the start of rows

        file.write(f'DISPENSE MM={extrude_mm} SPEED={dispensing_speed} RELATIVE=1\nWAIT S={droplet_wait_time}\n')
        syringe_tracker[0] = max(0.0, syringe_tracker[0] - extrude_mm)

        file.write(f'G0 Z{z_contact} F{decent_speed} ;position for liquid contact\n')
        file.write(f'G0 Z{z_movement_pos_low} F{adcent_speed}\n')

        washing_spot_counter[0] += 1

        if not is_cleaning and grid_obj and hasattr(grid_obj, 'washing_enabled'):
            if grid_obj.washing_enabled.get():
                washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
                washing_after_x_spots = int(washing_entry_dict['washing_after_x_spots'])
                if washing_after_x_spots > 0 and washing_spot_counter[0] % washing_after_x_spots == 0:
                    auto_washing(self, grid_obj, z_movement_pos_high, file)
                    reset_washing_counter()

                    if grid_obj.cleaning_enabled.get():
                        auto_cleaning_grid(
                            grid_obj,
                            file,
                            cleaning_anchor_x,
                            cleaning_anchor_y,
                            z_contact,
                            z_movement_pos_low,
                            z_movement_pos_high,
                            syringe_tracker=syringe_tracker,
                            row_start_wait=row_start_wait,
                            cleaning_cycle_counter=cleaning_cycle_counter,
                        )

    if grid_obj.washing_enabled.get():
        auto_washing(self, grid_obj, z_movement_pos_high, file)

    return rows * cols


def loading_syringe(
    file,
    container,
    z_movement_pos_high,
    speed=5000,
    decent_speed=500,
    adcent_speed=5000,
    refilling_speed=250,
    dispensing_speed=500,
    total_fill=10,
    priming_vol=3.0,
    syringe_tracker=None,
    syringe_aspirate_wait=2.0,
    syringe_prime_wait=2.0,
):
    if container is None:
        raise ValueError("Loading container is not configured")
        
    fill_mm = volume_to_mm(total_fill) + volume_to_mm(priming_vol)
    priming_mm = volume_to_mm(priming_vol)
    
    file.write(f'G0 X{container.x} Y{container.y} F{speed}\n')

    file.write('M117; Open Container\n')
    file.write('PAUSE\n')

    file.write(f'G0 Z{container.z_filling_height}  F{decent_speed}\n')
    file.write(f'ASPIRATE MM={fill_mm} SPEED={refilling_speed}; Filling the syringe\n')
    file.write(f'WAIT S={syringe_aspirate_wait}\n')
    file.write(f'DISPENSE MM={priming_mm} SPEED={dispensing_speed/2} RELATIVE=1; Prevent backlash the syringe\n')
    file.write(f'WAIT S={syringe_prime_wait}\n')
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')

    if syringe_tracker is not None:
        # Track remaining plunger travel in mm after priming.
        syringe_tracker[0] = max(0.0, fill_mm - priming_mm)


def emptying_syringe(
    file,
    container,
    z_movement_pos_high,
    speed=5000,
    decent_speed=500,
    adcent_speed=5000,
    dispensing_speed=500,
    refilling_speed=250,
    final_rinse_enabled=False,
    rinsing_cycles=1,
    max_syringe_mm=50.0,
    min_syringe_mm=0.0,
    emptying_wait=1.0,
    rinse_aspiration_wait=0.5,
    rinse_final_wait=2.0,
    syringe_tracker=None,
):
    if container is None:
        raise ValueError("Emptying container is not configured")
    file.write('M117; Emptying Syringe\n')

    file.write(f'\nG0 Z{z_movement_pos_high} F{adcent_speed} ; dispensing leftovers\n')
    file.write(f'G0 X{container.x} Y{container.y} F{speed}\n')
    file.write(f'G0 Z{container.z_filling_height} F{decent_speed}\n')

    file.write(f'DISPENSE MM={min_syringe_mm} SPEED={dispensing_speed}\nWAIT S={emptying_wait}\n')

    if syringe_tracker is not None:
        syringe_tracker[0] = 0
    
    if final_rinse_enabled:
        cycles = max(0, int(rinsing_cycles))
        for _ in range(cycles):
            file.write(f'ASPIRATE MM={max_syringe_mm} SPEED={dispensing_speed} ; rinse aspiration\n')
            file.write(f'WAIT S={rinse_aspiration_wait}\n')
            file.write(f'DISPENSE MM={min_syringe_mm} SPEED={dispensing_speed} ; rinse dispense\n')
        file.write(f'WAIT S={rinse_final_wait}\n')
        file.write(f'\nG0 Z{z_movement_pos_high} F{adcent_speed} ; dispensing leftovers\n')
        for _ in range(cycles):
            file.write(f'ASPIRATE MM={max_syringe_mm} SPEED={dispensing_speed} ; rinse aspiration\n')
            file.write(f'WAIT S={rinse_aspiration_wait}\n')
            file.write(f'DISPENSE MM={min_syringe_mm} SPEED={dispensing_speed} ; rinse dispense\n')
        file.write(f'WAIT S={rinse_final_wait}\n')

    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')




def auto_cleaning_grid(
    grid_obj,
    file,
    anchor_x,
    anchor_y,
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
    row_start_wait=0.2,
    cleaning_cycle_counter=None,
):
    cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)

    cleaning_rows = int(cleaning_entry_dict['rows_cleaning'])
    cleaning_cols = int(cleaning_entry_dict['cols_cleaning'])
    cleaning_x_shift = float(cleaning_entry_dict['pitch_x_cleaning'])
    cleaning_y_shift = float(cleaning_entry_dict['pitch_y_cleaning'])
    cleaning_x_offset = float(cleaning_entry_dict['grid_offset_x_cleaning'])
    cleaning_y_offset = float(cleaning_entry_dict['grid_offset_y_cleaning'])
    x_relative_increase = float(cleaning_entry_dict.get('x_relative_increase', 0.0))
    y_relative_increase = float(cleaning_entry_dict.get('y_relative_increase', 0.0))
    cleaning_dispense_vol = float(cleaning_entry_dict['dispense_vol_cleaning'])
    cleaning_droplet_wait_time = float(cleaning_entry_dict.get('droplet_forming_time_cleaning', 0.5))

    cycle_index = cleaning_cycle_counter[0] if cleaning_cycle_counter is not None else 0
    anchor_x_shifted = anchor_x + (cycle_index * x_relative_increase)
    anchor_y_shifted = anchor_y + (cycle_index * y_relative_increase)

    file.write("\n\n; Create cleaning sequence\n")
    file.write('M117; Auto Cleaning\n')
    cleaning_coordinates = create_coordinates(
        cleaning_rows,
        cleaning_cols,
        anchor_x_shifted,
        cleaning_x_offset,
        cleaning_x_shift,
        anchor_y_shifted,
        cleaning_y_offset,
        cleaning_y_shift,
    )
    cleaning_dispense_mm = volume_to_mm(cleaning_dispense_vol)
    for i in range(cleaning_rows * cleaning_cols):
        line = 'G0 ' + cleaning_coordinates[i] + f' F{speed}' + '\n'
        file.write(line)
        remainder = i % cleaning_cols
        if remainder == 0:
            file.write(f"WAIT S={row_start_wait}\n")

        file.write(f'DISPENSE MM={cleaning_dispense_mm} SPEED={dispensing_speed} RELATIVE=1\nWAIT S={cleaning_droplet_wait_time}\n')
        if syringe_tracker is not None:
            syringe_tracker[0] = max(0.0, syringe_tracker[0] - cleaning_dispense_mm)

        file.write(f'G0 Z{z_contact} F{decent_speed} ;position for liquid contact\n')
        file.write(f'G0 Z{z_movement_pos_low} F{adcent_speed}\n')

    file.write('\n\n\n')

    if cleaning_cycle_counter is not None:
        cleaning_cycle_counter[0] += 1

def auto_washing(self, grid_obj, z_movement_pos_high, file, speed=5000, decent_speed=500, adcent_speed=5000,
                 dispensing_speed=500, refilling_speed=250):
    washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)

    washing_depth = float(washing_entry_dict['washing_depth'])
    washing_speed = float(washing_entry_dict['washing_speed'])
    washing_x_pos = float(washing_entry_dict['washing_x_pos'])
    washing_y_pos = float(washing_entry_dict['washing_y_pos'])
    washing_line_lenght = float(washing_entry_dict['washing_line_lenght'])
    washing_cycles = int(washing_entry_dict['washing_cycles'])

    # Washing coordinates are absolute machine coordinates, same as container positions.
    x_abs = washing_x_pos
    y_abs = washing_y_pos
    file.write("\n; Washing sequence\n")
    file.write('M117; Auto Washing\n')

    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
    file.write(f'G0 X{x_abs} Y{y_abs} F{speed}\n')
    file.write(f'G0 Z{washing_depth} F{decent_speed}\n')

    for cycle in range(washing_cycles):
        file.write(f'G0 X{x_abs + washing_line_lenght} F{washing_speed}\n')
        file.write(f'G0 X{x_abs} F{washing_speed}\n')

    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
