"""
Centralized input configuration schema.
Single source of truth for GUI + JSON.
"""

from dataclasses import dataclass
from typing import Any, List


# ========== Field Definitions ==========
@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str
    default: Any = 0.0
    tab: str = ""
# ------------------------------------------------------------------

GLOBAL_FIELDS: List[Field] = [
    Field("x_cord_of_y_line", "Base origin X from TCP", "mm", tab="Anchors"),
    Field("y_cord_of_x_line", "Base origin Y from TCP", "mm", tab="Anchors"),

    Field("tuning_offset_x", "First Spot X-offset", "mm", tab="Geometry"),
    Field("tuning_offset_y", "First Spot Y-offset", "mm", tab="Geometry"),
    Field("acceptance_square_x", "Acceptance Square X", "mm", tab="Geometry"),
    Field("acceptance_square_y", "Acceptance Square Y", "mm", tab="Geometry"),
    Field("mesh_points", "Mesh Points (3 to 10)", "int", default=3, tab="Geometry"),
    Field("max_grid_count", "Maximum Grid Count", "int", default=6, tab="Geometry"),
    Field("base_square_x", "Base Square X", "mm", tab="Geometry"),
    Field("base_square_y", "Base Square Y", "mm", tab="Geometry"),

    Field("container1_x", "Container 1 X Pos", "mm", tab="Containers"),
    Field("container1_y", "Container 1 Y Pos", "mm", tab="Containers"),
    Field("container1_z", "Container 1 Z Fill", "mm", tab="Containers"),
    Field("container2_x", "Container 2 X Pos", "mm", tab="Containers"),
    Field("container2_y", "Container 2 Y Pos", "mm", tab="Containers"),
    Field("container2_z", "Container 2 Z Fill", "mm", tab="Containers"),
    Field("container3_x", "Container 3 X Pos", "mm", tab="Containers"),
    Field("container3_y", "Container 3 Y Pos", "mm", tab="Containers"),
    Field("container3_z", "Container 3 Z Fill", "mm", tab="Containers"),
    Field("container4_x", "Container 4 X Pos", "mm", tab="Containers"),
    Field("container4_y", "Container 4 Y Pos", "mm", tab="Containers"),
    Field("container4_z", "Container 4 Z Fill", "mm", tab="Containers"),
    Field("container5_x", "Container 5 X Pos", "mm", tab="Containers"),
    Field("container5_y", "Container 5 Y Pos", "mm", tab="Containers"),
    Field("container5_z", "Container 5 Z Fill", "mm", tab="Containers"),
    Field("container6_x", "Container 6 X Pos", "mm", tab="Containers"),
    Field("container6_y", "Container 6 Y Pos", "mm", tab="Containers"),
    Field("container6_z", "Container 6 Z Fill", "mm", tab="Containers"),
    Field("probe_x", "Probe Homing X", "mm", tab="Containers"),
    Field("probe_y", "Probe Homing Y", "mm", tab="Containers"),

    Field("z_movement_pos_low", "Movement Z low", "mm", tab="Motion"),
    Field("z_movement_pos_high", "Movement Z high", "mm", tab="Motion"),
    Field("movement_speed", "Movement Speed", "mm", tab="Motion"),
    Field("decent_speed", "Descent Speed", "mm", tab="Motion"),
    Field("adcent_speed", "Ascent Speed", "mm", tab="Motion"),

    Field("dispensing_speed", "Dispensing Speed", "mm", tab="Fluids"),
    Field("refilling_speed", "Refilling Speed", "mm", tab="Fluids"),
    Field("max_syringe_vol", "Maximum Syringe Volume", "uL", tab="Fluids"),
    Field("priming_vol", "Priming Volume", "uL", default=3.0, tab="Fluids"),
    Field("drop_extra_aspirate", "Drop Extra Aspirate", "x spot vol", default=0.0, tab="Fluids"),

    Field("max_syringe_mm", "Max Syringe MM (Rinse)", "mm", default=50.0, tab="Utility"),
    Field("min_syringe_mm", "Min Syringe MM (Rinse)", "mm", default=0.0, tab="Utility"),
    Field("probe_ram_height", "Probe Ram Height", "mm", default=110.0, tab="Utility"),
    Field("probe_return_height", "Probe Return Height", "mm", default=105.0, tab="Utility"),
    Field("calibration_height", "Calibration Height", "mm", default=0.0, tab="Utility"),
    Field("present_plate_y", "Present Plate Y Position", "mm", default=170.0, tab="Utility"),
    Field("present_plate_speed", "Present Plate Speed", "mm/s", default=2000.0, tab="Utility"),
    Field("row_start_wait", "Row Start Wait", "s", default=0.2, tab="Utility"),
    Field("emptying_wait", "Emptying Wait", "s", default=1.0, tab="Utility"),
    Field("rinse_aspiration_wait", "Rinse Aspiration Wait", "s", default=0.5, tab="Utility"),
    Field("rinse_final_wait", "Rinse Final Wait", "s", default=2.0, tab="Utility"),
    Field("probe_feed_rate", "Probe Feed Rate", "mm/s", default=300.0, tab="Utility"),
    Field("calibration_feed_rate", "Calibration Feed Rate", "mm/s", default=300.0, tab="Utility"),
    Field("syringe_aspirate_wait", "Syringe Aspirate Wait", "s", default=2.0, tab="Utility"),
    Field("syringe_prime_wait", "Syringe Prime Wait", "s", default=2.0, tab="Utility"),
]


GRID_FIELDS: List[Field] = [
    Field("rows", "Set rows", "int"),
    Field("cols", "Set columns", "int"),
    Field("pitch_x", "X step size", "mm"),
    Field("pitch_y", "Y step size", "mm"),
    Field("dispense_vol", "Dispense Volume", "uL"),
    Field("row_add_volume", "Row Add Volume", "uL"),
    Field("loading_from", "Loading from (1-6)", "int", default=1),
    Field("leftovers_into", "Leftovers into (1-6)", "int"),
    Field("z_contact", "Needle-Substrate Distance", "mm"),
    Field("droplet_forming_time", "Droplet forming time", "s"),
    Field("grid_offset_x", "Grid offset X", "mm"),
    Field("grid_offset_y", "Grid offset Y", "mm"),
]

# Fields specific to spiral plugin; keys must match plugin expected params
SPIRAL_FIELDS = [
    Field('center_x', 'Center X (mm)', unit='mm', default=0.0),
    Field('center_y', 'Center Y (mm)', unit='mm', default=0.0),
    Field('start_radius', 'Start Radius (mm)', unit='mm', default=0.0),
    Field('turns', 'Turns', unit='float', default=5.0),
    Field('num_starts', 'Starts', unit='int', default=1),
    Field('spacing_mm', 'Spacing (mm)', unit='mm', default=1.5),
    Field('dispense_vol', 'Dispense uL', unit='uL', default=0.003),
    Field('spiral_mode', 'Spiral Mode', unit='str', default='drop'),
    Field('interleave', 'Interleave Starts', unit='bool', default=False),
    Field('loading_from', 'Loading from (1-6)', unit='int', default=1),
    Field('leftovers_into', 'Leftovers into (1-6)', unit='int', default=1),
    Field('z_contact', 'Needle-Substrate Distance', unit='mm', default=0.01),
    Field('droplet_forming_time', 'Droplet forming time', unit='s', default=0.5),
]


CLEANING_FIELDS: List[Field] = [
    Field("rows_cleaning", "Set rows", "int"),
    Field("cols_cleaning", "Set columns", "int"),
    Field("pitch_x_cleaning", "X step size", "mm"),
    Field("pitch_y_cleaning", "Y step size", "mm"),
    Field("dispense_vol_cleaning", "Dispense volume cleaning", "uL"),
    Field("droplet_forming_time_cleaning", "Droplet forming time", "s", default=0.5),
    Field("grid_offset_x_cleaning", "Grid offset X", "mm"),
    Field("grid_offset_y_cleaning", "Grid offset Y", "mm"),
    Field("x_relative_increase", "X Relative Increase", "mm", default=0.0),
    Field("y_relative_increase", "Y Relative Increase", "mm", default=0.0),
    Field("spots_before_cleaning", "Spots before cleaning", "int"),
    Field("final_rinse_cycles", "Final Rinse Cycles", "int", default=1),
]


WASHING_FIELDS: List[Field] = [
    Field("washing_depth", "Washing Depth", "mm"),
    Field("washing_speed", "Washing Speed", "mm/s"),
    Field("washing_x_pos", "Washing X position", "mm"),
    Field("washing_y_pos", "Washing Y position", "mm"),
    Field("washing_line_lenght", "Washing line lenght", "mm"),
    Field("washing_after_x_spots", "Washing After X Spots", "int"),
    Field("washing_cycles", "Washing Cycles", "int"),
]
