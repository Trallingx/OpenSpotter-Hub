from SpotterFunctions import read_entries_as_dict, create_coordinates, volume_to_mm
from input_configs import GLOBAL_FIELDS, WASHING_FIELDS, CLEANING_FIELDS


def start_gcode(file, z_movement_pos_high, probe_x=75, probe_y=70, speed=5000, decent_speed=500, adcent_speed=5000, acceptance_square=None, mesh_points=3):
    if acceptance_square is None:
        raise ValueError("acceptance_square bounds must be provided")

    file.write('\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
    file.write('\n;Homing sequence\n')
    file.write('M117 Gantry Align\n')
    file.write('G28 Z0 ;Home Z\n')
    file.write('G28 X0 Y0 ;Home X Y\n')

    file.write(f'G0 X{probe_x} Y{probe_y} F{speed} ; Go with Head to probe position\n')
    file.write('SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=0\n')
    file.write('G0 Z110 F300 ; Ram into top\n')
    file.write('G0 Z105 F300 ; Back down\n')
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
    file.write('G1 Z0 F300 \n')
    file.write('M117 ;Calibrate Needle to touch substrate\n')
    file.write('PAUSE\n')
    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')

    return file


def write_anchor_calibration_sequence(file, x_abs, y_abs, z_low, z_high, speed, decent_speed, adcent_speed):
    file.write('; Anchor Calibration Sequence\n')
    file.write(f'G0 X{x_abs} Y{y_abs} F{speed} ; Move to anchor position\n')
    file.write(f'G0 Z{z_low} F{decent_speed} ; Lower needle to calibration height\n')
    file.write('WAIT S=1 ; Wait 1 second at calibration position\n')
    file.write(f'G0 Z{z_high} F{adcent_speed} ; Raise needle to safe height\n')
    file.write('; Calibration complete\n')


def present_build_plate(file):
    file.write('G90 ;absolute positioning\nG0 Y170 F500;present print\n')


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
    priming_vol=3.0,
    syringe_tracker=None,
):
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
        file.write(f'G0 Z{z_movement_pos_low} F{decent_speed}\n')

        if i % cols == 0:
            file.write("WAIT S=0.2\n")

        extrude_mm = volume_to_mm(extrude)
        file.write(f'DISPENSE MM={extrude_mm} SPEED={dispensing_speed} RELATIVE=1\nWAIT S={droplet_wait_time}\n')
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
                priming_vol=priming_vol,
                syringe_tracker=syringe_tracker,
            )
            #file.write(f"G0 X50 Y50 F{speed}") unused?
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
    priming_vol=3.0,
    syringe_tracker=None,
):
    if container is None:
        raise ValueError("Loading container is not configured")

    fill_mm = volume_to_mm(total_fill + priming_vol)
    priming_mm = volume_to_mm(priming_vol)
    
    file.write(f'G0 X{container.x} Y{container.y} F{speed}\n')
    file.write(f'G0 Z{container.z_filling_height}  F{decent_speed}\n')
    file.write(f'ASPIRATE MM={fill_mm} SPEED={refilling_speed}; Filling the syringe\n')
    file.write('WAIT S=2\n')
    file.write('G92 E0\n\n')
    file.write(f'DISPENSE MM={priming_mm} SPEED={refilling_speed/2} RELATIVE=1; Prevent backlash the syringe\n')
    file.write('WAIT S=2\n')
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
    if container is None:
        raise ValueError("Emptying container is not configured")
    file.write(f'\nG0 Z{z_movement_pos_high} F{adcent_speed} ; dispensing leftovers\n')
    file.write(f'G0 X{container.x} Y{container.y} F{speed}\n')
    file.write(f'G0 Z{container.z_filling_height} F{decent_speed}\n')

    leftovers = 0.0 if syringe_tracker is None else max(0.0, syringe_tracker[0])
    if leftovers > 0:
        leftovers_mm = volume_to_mm(leftovers)
        file.write(f'DISPENSE MM={leftovers_mm:.4f} SPEED={dispensing_speed} RELATIVE=1\nWAIT S=1\n')
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
    cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)

    cleaning_rows = int(cleaning_entry_dict['rows_cleaning'])
    cleaning_cols = int(cleaning_entry_dict['cols_cleaning'])
    cleaning_x_shift = float(cleaning_entry_dict['pitch_x_cleaning'])
    cleaning_y_shift = float(cleaning_entry_dict['pitch_y_cleaning'])
    cleaning_x_offset = float(cleaning_entry_dict['grid_offset_x_cleaning'])
    cleaning_y_offset = float(cleaning_entry_dict['grid_offset_y_cleaning'])
    cleaning_dispense_vol = -float(cleaning_entry_dict['dispense_vol_cleaning'])

    file.write("\n\n; Create cleaning sequence\n")

    cleaning_coordinates = create_coordinates(
        cleaning_rows,
        cleaning_cols,
        x_abs,
        cleaning_x_offset,
        cleaning_x_shift,
        y_abs,
        cleaning_y_offset,
        cleaning_y_shift,
    )
    line = 'G0' + f' X{cleaning_x_offset}' + f' Y{cleaning_y_offset}' + f' Z{z_movement_pos_high}' + f' F{speed}' + '\n'
    file.write(line)
    cleaning_dispense_mm = volume_to_mm(cleaning_dispense_vol)
    for i in range(cleaning_rows * cleaning_cols):
        line = 'G0 ' + cleaning_coordinates[i] + f' F{speed}' + '\n'
        file.write(line)
        remainder = i % cleaning_cols
        if remainder == 0:
            file.write("WAIT S=0.2\n")

        file.write(f'DISPENSE MM={cleaning_dispense_mm} SPEED={dispensing_speed} RELATIVE=1\nG92 E0\nWAIT S=0.2\n')
        if syringe_tracker is not None:
            syringe_tracker[0] = max(0.0, syringe_tracker[0] - (-cleaning_dispense_vol))

        file.write(f'G0 Z{z_contact} F{decent_speed} ;position for liquid contact\n')
        file.write(f'G0 Z{z_movement_pos_low} F{adcent_speed}\n')


def auto_washing(self, grid_obj, z_movement_pos_high, file, speed=5000, decent_speed=500, adcent_speed=5000,
                 dispensing_speed=500, refilling_speed=250):
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

    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
    file.write(f'G0 X{x_abs + washing_x_pos} Y{y_abs + washing_y_pos} F{speed}\n')
    file.write(f'G0 Z{washing_depth} F{decent_speed}\n')

    for cycle in range(washing_cycles):
        file.write(f'G0 X{x_abs + washing_x_pos + washing_line_lenght} F{washing_speed}\n')
        file.write(f'G0 X{x_abs + washing_x_pos} F{washing_speed}\n')

    file.write(f'G0 Z{z_movement_pos_high} F{adcent_speed}\n')
    file.write('G0 X50 Y50 F5000\n')
