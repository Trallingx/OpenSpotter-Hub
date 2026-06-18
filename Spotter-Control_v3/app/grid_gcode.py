from .SpotterFunctions import read_entries_as_dict, write_generation_settings_file, volume_to_mm
from .input_configs import CLEANING_FIELDS, GRID_FIELDS, WASHING_FIELDS
from .gcode_shared import collect_common_generation_data, prompt_save_base_path
from .spotter_gcode import (
    start_gcode,
    write_anchor_calibration_sequence,
    generate_grid,
    loading_syringe,
    emptying_syringe,
    present_build_plate,
    auto_cleaning_grid,
)


def generate_anchor_calibration(self):
    filepath = prompt_save_base_path("global_calibration.gcode")
    if not filepath:
        return

    common = collect_common_generation_data(self)

    with open(filepath, "w") as file:
        start_gcode(
            file,
            common['z_movement_pos_high'],
            common['probe_x'],
            common['probe_y'],
            common['speed'],
            common['decent_speed'],
            common['adcent_speed'],
            common['acceptance_square'],
            common['mesh_points'],
            probe_ram_height=common['probe_ram_height'],
            probe_return_height=common['probe_return_height'],
            calibration_height=common['calibration_height'],
            calibration_wait=common['calibration_wait'],
            probe_feed_rate=common['probe_feed_rate'],
            calibration_feed_rate=common['calibration_feed_rate'],
        )

        write_anchor_calibration_sequence(
            file,
            common['x_abs'],
            common['y_abs'],
            common['z_movement_pos_low'],
            common['z_movement_pos_high'],
            common['speed'],
            common['decent_speed'],
            common['adcent_speed'],
            calibration_wait=common['calibration_wait'],
        )



def save_grid_gcode(self, filepath=None):
    if not getattr(self, 'grid_tab_dict', {}):
        return None

    if filepath is None:
        filepath = prompt_save_base_path("drop_array_grid.gcode")
    if not filepath:
        return None

    common = collect_common_generation_data(self)
    entry_dict = common['entry_dict']
    containers = common['containers']
    x_offset = common['x_offset']
    y_offset = common['y_offset']
    speed = common['speed']
    decent_speed = common['decent_speed']
    adcent_speed = common['adcent_speed']
    dispensing_speed = common['dispensing_speed']
    refilling_speed = common['refilling_speed']
    max_syringe_vol = common['max_syringe_vol']
    drop_extra_aspirate = common['drop_extra_aspirate']
    max_syringe_mm = common['max_syringe_mm']
    min_syringe_mm = common['min_syringe_mm']
    probe_ram_height = common['probe_ram_height']
    probe_return_height = common['probe_return_height']
    calibration_height = common['calibration_height']
    present_plate_y = common['present_plate_y']
    present_plate_speed = common['present_plate_speed']
    row_start_wait = common['row_start_wait']
    calibration_wait = common['calibration_wait']
    emptying_wait = common['emptying_wait']
    rinse_aspiration_wait = common['rinse_aspiration_wait']
    rinse_final_wait = common['rinse_final_wait']
    probe_feed_rate = common['probe_feed_rate']
    calibration_feed_rate = common['calibration_feed_rate']
    syringe_aspirate_wait = common['syringe_aspirate_wait']
    syringe_prime_wait = common['syringe_prime_wait']
    z_movement_pos_low = common['z_movement_pos_low']
    z_movement_pos_high = common['z_movement_pos_high']
    priming_vol = common['priming_vol']
    acceptance_square = common['acceptance_square']
    mesh_points = common['mesh_points']
    x_abs = common['x_abs']
    y_abs = common['y_abs']
    x_offset = common['x_offset']
    y_offset = common['y_offset']

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
        "spiral_settings": [],
    }

    with open(filepath, "w") as file:
        start_gcode(
            file,
            z_movement_pos_high,
            common['probe_x'],
            common['probe_y'],
            speed,
            decent_speed,
            adcent_speed,
            acceptance_square,
            mesh_points,
            probe_ram_height=probe_ram_height,
            probe_return_height=probe_return_height,
            calibration_height=calibration_height,
            calibration_wait=calibration_wait,
            probe_feed_rate=probe_feed_rate,
            calibration_feed_rate=calibration_feed_rate,
        )

        washing_spot_counter = [0]
        syringe_tracker = [0.0]
        for _, grid_obj in sorted(self.grid_tab_dict.items()):
            grid_entry_dict = read_entries_as_dict(grid_obj.grid_entry, GRID_FIELDS)
            cleaning_entry_dict = read_entries_as_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
            washing_entry_dict = read_entries_as_dict(grid_obj.washing_entry, WASHING_FIELDS)
            grid_number = len(settings_snapshot["grid_settings"]) + 1

            settings_snapshot["grid_settings"].append({
                "grid_number": grid_number,
                "grid_name": grid_obj.get_grid_name() if hasattr(grid_obj, 'get_grid_name') else f"Grid {grid_number}",
                "grid_color": grid_obj.get_grid_color() if hasattr(grid_obj, 'get_grid_color') else "green",
                "grid": dict(grid_entry_dict),
                "cleaning": dict(cleaning_entry_dict),
                "washing": dict(washing_entry_dict),
                "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
                "washing_enabled": bool(grid_obj.washing_enabled.get()),
                "wash_after_loading": bool(grid_obj.wash_after_loading_enabled.get()),
                "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
                "final_rinse_add_cleaning_grid": bool(grid_obj.final_rinse_add_cleaning_grid.get()),
            })

            rows = int(grid_entry_dict['rows'])
            cols = int(grid_entry_dict['cols'])
            x_shift = float(grid_entry_dict['pitch_x'])
            y_shift = float(grid_entry_dict['pitch_y'])
            extrude = float(grid_entry_dict['dispense_vol'])
            row_add_volume = float(grid_entry_dict.get('row_add_volume', 0.0))
            z_contact = float(grid_entry_dict['z_contact'])
            droplet_wait_time = float(grid_entry_dict['droplet_forming_time'])
            grid_x_offset = float(grid_entry_dict['grid_offset_x'])
            grid_y_offset = float(grid_entry_dict['grid_offset_y'])
            loading_container_id = int(grid_entry_dict.get('loading_from', 1))
            emptying_container_id = int(grid_entry_dict.get('leftovers_into', 1))

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

            main_grid_fill = rows * cols * extrude
            cleaning_grid_fill = 0.0
            base_spot_volume = extrude + max(0.0, row_add_volume)
            if bool(grid_obj.cleaning_enabled.get()):
                cleaning_rows = int(cleaning_entry_dict.get('rows_cleaning', 0))
                cleaning_cols = int(cleaning_entry_dict.get('cols_cleaning', 0))
                cleaning_dispense_vol = float(cleaning_entry_dict.get('dispense_vol_cleaning', 0.0))
                cleaning_grid_fill = cleaning_rows * cleaning_cols * cleaning_dispense_vol
                base_spot_volume = max(base_spot_volume, cleaning_dispense_vol)

            reserve_multiplier = 1.0 + max(0.0, drop_extra_aspirate)
            reserve_fill = base_spot_volume * reserve_multiplier
            total_fill = min(max_syringe_vol, main_grid_fill + cleaning_grid_fill + reserve_fill)
            cleaning_cycle_counter = [0]

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
                loading_container_id,
                refill=total_fill,
                is_cleaning=False,
                droplet_wait_time=droplet_wait_time,
                grid_obj=grid_obj,
                washing_spot_counter=washing_spot_counter,
                speed=speed,
                decent_speed=decent_speed,
                adcent_speed=adcent_speed,
                dispensing_speed=dispensing_speed,
                refilling_speed=refilling_speed,
                max_syringe_vol=max_syringe_vol,
                priming_vol=priming_vol,
                syringe_tracker=syringe_tracker,
                row_start_wait=row_start_wait,
                syringe_aspirate_wait=syringe_aspirate_wait,
                syringe_prime_wait=syringe_prime_wait,
                cleaning_anchor_x=x_offset,
                cleaning_anchor_y=y_offset,
                cleaning_cycle_counter=cleaning_cycle_counter,
            )

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
                syringe_tracker=syringe_tracker,
            )

            if bool(grid_obj.final_rinse_enabled.get()) and bool(grid_obj.final_rinse_add_cleaning_grid.get()):
                auto_cleaning_grid(
                    grid_obj,
                    file,
                    x_offset,
                    y_offset,
                    z_contact,
                    z_movement_pos_low,
                    z_movement_pos_high,
                    speed=speed,
                    decent_speed=decent_speed,
                    adcent_speed=adcent_speed,
                    dispensing_speed=dispensing_speed,
                    refilling_speed=refilling_speed,
                    syringe_tracker=syringe_tracker,
                    row_start_wait=row_start_wait,
                    cleaning_cycle_counter=cleaning_cycle_counter,
                )

        present_build_plate(file, present_plate_y=present_plate_y, present_plate_speed=present_plate_speed)

    settings_path = write_generation_settings_file(filepath, settings_snapshot)
    print(f"✅ Saved generation settings to {settings_path}")
    return filepath
