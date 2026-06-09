"""
Shared utilities for grid and spiral G-code generation.

Provides:
- File dialogs and path derivation
- Configuration acceptance square computation
- Common data collection for both grid and spiral generators
"""
import os
from tkinter import filedialog

from SpotterFunctions import build_containers, read_entries_as_dict
from input_configs import GLOBAL_FIELDS


def prompt_save_base_path(default_filename: str):
    """
    Prompt user to select a base filename and location for G-code output.
    Returns the full filepath, or None if cancelled.
    """
    return filedialog.asksaveasfilename(
        defaultextension=".gcode",
        initialfile=default_filename,
        filetypes=[("G-code files", "*.gcode"), ("All files", "*.*")],
        confirmoverwrite=False,
    )


def derive_output_path(base_path: str, suffix: str) -> str:
    """
    Derive output path from base filename by inserting suffix before extension.
    
    Example: derive_output_path("drop_array.gcode", "grid") -> "drop_array_grid.gcode"
    """
    root, ext = os.path.splitext(base_path)
    if not ext:
        ext = ".gcode"
    return f"{root}_{suffix}{ext}"


def compute_acceptance_square(entry_dict):
    """
    Convert acceptance square size + base origin into printer coordinates.
    
    Keeps canvas orientation (bottom-left is minimum X/Y).
    Returns dict with keys: x_left, x_right, y_bottom, y_top
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


def collect_common_generation_data(self):
    """
    Single source of truth for runtime values shared by grid and spiral generators.
    
    Collects all global configuration from GLOBAL_FIELDS and builds containers dict.
    All numeric defaults are sourced from input_configs.py GLOBAL_FIELDS definitions.
    
    Returns dict with keys:
    - entry_dict: all raw global field values
    - spatial: x_abs, y_abs, x_offset, y_offset
    - containers: dict of container 1-6 with x, y, z positions
    - probe: probe_x, probe_y
    - acceptance_square: computed square bounds
    - mesh_points: mesh calibration point count
    - speeds: movement_speed, decent_speed, adcent_speed, dispensing_speed, refilling_speed
    - syringe: max_syringe_vol, drop_extra_aspirate, max_syringe_mm, min_syringe_mm, priming_vol
    - z_heights: z_movement_pos_low, z_movement_pos_high
    - probe_params: probe_ram_height, probe_return_height, calibration_height, probe_feed_rate, calibration_feed_rate
    - timing: row_start_wait, calibration_wait, emptying_wait, rinse_aspiration_wait, rinse_final_wait, syringe_aspirate_wait, syringe_prime_wait
    - plate: present_plate_y, present_plate_speed
    """
    entry_dict = read_entries_as_dict(self.entry, GLOBAL_FIELDS)
    x_abs = float(entry_dict['x_cord_of_y_line'])
    y_abs = float(entry_dict['y_cord_of_x_line'])
    x_offset = x_abs + float(entry_dict['tuning_offset_x'])
    y_offset = y_abs + float(entry_dict['tuning_offset_y'])
    containers = build_containers(entry_dict)

    return {
        # Raw config
        'entry_dict': entry_dict,
        # Spatial coords
        'x_abs': x_abs,
        'y_abs': y_abs,
        'x_offset': x_offset,
        'y_offset': y_offset,
        # Containers and probe
        'containers': containers,
        'probe_x': float(entry_dict['probe_x']),
        'probe_y': float(entry_dict['probe_y']),
        'acceptance_square': compute_acceptance_square(entry_dict),
        'mesh_points': int(entry_dict['mesh_points']),
        # Movement speeds
        'speed': float(entry_dict['movement_speed']),
        'decent_speed': float(entry_dict['decent_speed']),
        'adcent_speed': float(entry_dict['adcent_speed']),
        'dispensing_speed': float(entry_dict['dispensing_speed']),
        'refilling_speed': float(entry_dict['refilling_speed']),
        # Syringe parameters (all defaults from input_configs.py GLOBAL_FIELDS)
        'max_syringe_vol': float(entry_dict['max_syringe_vol']),
        'drop_extra_aspirate': float(entry_dict['drop_extra_aspirate']),
        'max_syringe_mm': float(entry_dict['max_syringe_mm']),
        'min_syringe_mm': float(entry_dict['min_syringe_mm']),
        'priming_vol': float(entry_dict['priming_vol']),
        # Z positions
        'z_movement_pos_low': float(entry_dict['z_movement_pos_low']),
        'z_movement_pos_high': float(entry_dict['z_movement_pos_high']),
        # Probe parameters (all defaults from input_configs.py GLOBAL_FIELDS)
        'probe_ram_height': float(entry_dict['probe_ram_height']),
        'probe_return_height': float(entry_dict['probe_return_height']),
        'calibration_height': float(entry_dict['calibration_height']),
        'probe_feed_rate': float(entry_dict['probe_feed_rate']),
        'calibration_feed_rate': float(entry_dict['calibration_feed_rate']),
        # Timing parameters (all defaults from input_configs.py GLOBAL_FIELDS)
        'row_start_wait': float(entry_dict['row_start_wait']),
        'calibration_wait': float(entry_dict['calibration_wait']),
        'emptying_wait': float(entry_dict['emptying_wait']),
        'rinse_aspiration_wait': float(entry_dict['rinse_aspiration_wait']),
        'rinse_final_wait': float(entry_dict['rinse_final_wait']),
        'syringe_aspirate_wait': float(entry_dict['syringe_aspirate_wait']),
        'syringe_prime_wait': float(entry_dict['syringe_prime_wait']),
        # Plate presentation
        'present_plate_y': float(entry_dict['present_plate_y']),
        'present_plate_speed': float(entry_dict['present_plate_speed']),
    }

