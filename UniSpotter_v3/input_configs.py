"""
Centralized input configuration schema.
Single source of truth for GUI + JSON.
"""

from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str
    default: Any = 0.0


# ------------------------------------------------------------------
# Field definitions
# ------------------------------------------------------------------

GLOBAL_FIELDS: List[Field] = [
    Field("x_cord_of_y_line", "X coord. of Y-line", "mm"),
    Field("y_cord_of_x_line", "Y coord. of X-line", "mm"),
    Field("tuning_offset_x", "First Spot X-offset", "mm"),
    Field("tuning_offset_y", "First Spot Y-offset", "mm"),
    Field("container_z_height", "Container Z Height", "mm"),
    Field("acceptance_square_x", "Acceptance Square X", "mm"),
    Field("acceptance_square_y", "Acceptance Square Y", "mm"),
    Field("base_square_x", "Base Square X", "mm"),
    Field("base_square_y", "Base Square Y", "mm"),
    Field("grey_square_x", "Grey Square X", "mm"),
    Field("grey_square_y", "Grey Square Y", "mm"),
    Field("probe_x", "Probe Homing X", "mm"),
    Field("probe_y", "Probe Homing Y", "mm"),
]


GRID_FIELDS: List[Field] = [
    Field("rows", "Set rows", "int"),
    Field("cols", "Set columns", "int"),
    Field("pitch_x", "X step size", "mm"),
    Field("pitch_y", "Y step size", "mm"),
    Field("dispense_vol", "Dispense Volume", "uL"),
    Field("loading_from", "Loading from", "1 or 2"),
    Field("leftovers_into", "Leftovers into", "3 or 4"),
    Field("z_adjust", "Z-Adjust down", "mm"),
    Field("droplet_forming_time", "Droplet forming time", "s"),
    Field("grid_offset_x", "Grid offset X", "mm"),
    Field("grid_offset_y", "Grid offset Y", "mm"),
]


CLEANING_FIELDS: List[Field] = [
    Field("rows_cleaning", "Set rows", "int"),
    Field("cols_cleaning", "Set columns", "int"),
    Field("pitch_x_cleaning", "X step size", "mm"),
    Field("pitch_y_cleaning", "Y step size", "mm"),
    Field("dispense_vol_cleaning", "Dispense volume cleaning", "uL"),
    Field("grid_offset_x_cleaning", "Grid offset X", "mm"),
    Field("grid_offset_y_cleaning", "Grid offset Y", "mm"),
    Field("spots_before_cleaning", "Spots before cleaning", "int"),
]


WASHING_FIELDS: List[Field] = [
    Field("washing_depth", "Washing Depth", "mm"),
    Field("washing_speed", "Washing Speed", "mm/s"),
    Field("washing_upper_bound", "Washing Upper Bound", "mm"),
    Field("washing_lower_bound", "Washing Lower Bound", "mm"),
    Field("washing_column_offset", "Washing Column Offset", "mm"),
    Field("washing_after_x_spots", "Washing After X Spots", "int"),
    Field("washing_cycles", "Washing Cycles", "int"),
]
