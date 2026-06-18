from .SpotterFunctions import read_entries_as_dict, write_generation_settings_file, volume_to_mm
from .input_configs import SPIRAL_FIELDS
from .gcode_shared import collect_common_generation_data, prompt_save_base_path
from .plugins import discover_plugins, get_plugin
from .spotter_gcode import (
    start_gcode,
    loading_syringe,
    emptying_syringe,
    present_build_plate,
)


def save_spiral_gcode(self, filepath=None):
    if not getattr(self, 'spiral_tab_dict', {}):
        return None

    if filepath is None:
        filepath = prompt_save_base_path("drop_array_spiral.gcode")
    if not filepath:
        return None

    common = collect_common_generation_data(self)
    entry_dict = common['entry_dict']
    containers = common['containers']
    speed = common['speed']
    decent_speed = common['decent_speed']
    adcent_speed = common['adcent_speed']
    dispensing_speed = common['dispensing_speed']
    refilling_speed = common['refilling_speed']
    max_syringe_vol = common['max_syringe_vol']
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

    settings_snapshot = {
        "global_settings": dict(entry_dict),
        "runtime_values": {
            "x_offset": common['x_offset'],
            "y_offset": common['y_offset'],
            "acceptance_square_x_left": common['acceptance_square']['x_left'],
            "acceptance_square_x_right": common['acceptance_square']['x_right'],
            "acceptance_square_y_bottom": common['acceptance_square']['y_bottom'],
            "acceptance_square_y_top": common['acceptance_square']['y_top'],
            "mesh_points": common['mesh_points'],
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
            common['acceptance_square'],
            common['mesh_points'],
            probe_ram_height=probe_ram_height,
            probe_return_height=probe_return_height,
            calibration_height=calibration_height,
            calibration_wait=calibration_wait,
            probe_feed_rate=probe_feed_rate,
            calibration_feed_rate=calibration_feed_rate,
        )

        syringe_tracker = [0.0]
        for _, spiral_obj in sorted(getattr(self, 'spiral_tab_dict', {}).items()):
            spiral_entry_dict = read_entries_as_dict(spiral_obj.spiral_entry, SPIRAL_FIELDS)
            spiral_number = len(settings_snapshot["spiral_settings"]) + 1
            settings_snapshot["spiral_settings"].append({
                "spiral_number": spiral_number,
                "spiral_name": spiral_obj.get_grid_name() if hasattr(spiral_obj, 'get_grid_name') else f"Spiral {spiral_number}",
                "spiral_color": spiral_obj.get_grid_color() if hasattr(spiral_obj, 'get_grid_color') else "orange",
                "spiral": dict(spiral_entry_dict),
            })

            loading_container_id = int(spiral_entry_dict.get('loading_from', 1))
            emptying_container_id = int(spiral_entry_dict.get('leftovers_into', 1))
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

            loading_syringe(
                file,
                loading_container,
                z_movement_pos_high,
                speed,
                decent_speed,
                adcent_speed,
                refilling_speed,
                dispensing_speed,
                total_fill=max_syringe_vol,
                priming_vol=priming_vol,
                syringe_tracker=syringe_tracker,
                syringe_aspirate_wait=syringe_aspirate_wait,
                syringe_prime_wait=syringe_prime_wait,
            )

            plugin = get_plugin('spiral')
            if plugin is None:
                discover_plugins()
                plugin = get_plugin('spiral')
            if plugin is None:
                raise ValueError("Spiral plugin is not available")

            context = {
                'params': spiral_entry_dict,
                'speed': speed,
                'dispensing_speed': dispensing_speed,
                'z_high': z_movement_pos_high,
                'z_low': z_movement_pos_low,
                'helpers': {
                    'volume_to_mm': volume_to_mm,
                },
            }
            plugin.generate(file, settings_snapshot, context)

            emptying_syringe(
                file,
                emptying_container,
                z_movement_pos_high,
                speed,
                decent_speed,
                adcent_speed,
                dispensing_speed,
                refilling_speed,
                final_rinse_enabled=False,
                rinsing_cycles=0,
                max_syringe_mm=max_syringe_mm,
                min_syringe_mm=min_syringe_mm,
                emptying_wait=emptying_wait,
                rinse_aspiration_wait=rinse_aspiration_wait,
                rinse_final_wait=rinse_final_wait,
                syringe_tracker=syringe_tracker,
            )

        present_build_plate(file, present_plate_y=present_plate_y, present_plate_speed=present_plate_speed)

    settings_path = write_generation_settings_file(filepath, settings_snapshot)
    print(f"✅ Saved generation settings to {settings_path}")
    return filepath
