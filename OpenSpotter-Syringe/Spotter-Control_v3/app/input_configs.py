"""
Centralized input configuration schema.
Single source of truth for GUI + JSON.
"""

from typing import List

from .core.schema import Field
from .plugins.grid.fields import (
    CLEANING_FIELDS,
    GRID_FIELDS,
    WASHING_FIELDS,
)
from .plugins.spiral.fields import SPIRAL_FIELDS


# ========== Field Definitions ==========
# ------------------------------------------------------------------

GLOBAL_FIELDS: List[Field] = [
    Field("x_cord_of_y_line", "Base origin X from TCP", "mm", tab="Anchors"),
    Field("y_cord_of_x_line", "Base origin Y from TCP", "mm", tab="Anchors"),

    Field("tuning_offset_x", "First Spot X-offset", "mm", tab="Geometry"),
    Field("tuning_offset_y", "First Spot Y-offset", "mm", tab="Geometry"),
    Field("acceptance_square_x", "Acceptance Square X", "mm", tab="Geometry"),
    Field("acceptance_square_y", "Acceptance Square Y", "mm", tab="Geometry"),
    Field("mesh_points", "Mesh Points (3 to 10)", "int", default=3, tab="Geometry"),
    # The persisted key predates the plugin architecture; the operator-facing
    # label reflects that the limit now applies to every pattern workspace.
    Field("max_grid_count", "Maximum Pattern Count", "int", default=6, tab="Geometry"),
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
    Field("calibration_height", "Calibration Height", "mm", default=0.0, tab="Utility"),
    Field("present_plate_y", "Present Plate Y Position", "mm", default=170.0, tab="Utility"),
    Field("present_plate_speed", "Present Plate Speed", "mm/s", default=2000.0, tab="Utility"),
    Field("row_start_wait", "Row Start Wait", "s", default=0.2, tab="Utility"),
    Field("emptying_wait", "Emptying Wait", "s", default=1.0, tab="Utility"),
    Field("rinse_aspiration_wait", "Rinse Aspiration Wait", "s", default=0.5, tab="Utility"),
    Field("rinse_final_wait", "Rinse Final Wait", "s", default=2.0, tab="Utility"),
    Field("calibration_feed_rate", "Calibration Feed Rate", "mm/s", default=300.0, tab="Utility"),
    Field("syringe_aspirate_wait", "Syringe Aspirate Wait", "s", default=2.0, tab="Utility"),
    Field("syringe_prime_wait", "Syringe Prime Wait", "s", default=2.0, tab="Utility"),
]


__all__ = [
    "CLEANING_FIELDS",
    "Field",
    "GLOBAL_FIELDS",
    "GRID_FIELDS",
    "SPIRAL_FIELDS",
    "WASHING_FIELDS",
]
