"""Field schemas owned by the built-in grid plugin."""

from typing import List

from ...core.schema import Field


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

CLEANING_FIELDS: List[Field] = [
    Field("rows_cleaning", "Set rows", "int"),
    Field("cols_cleaning", "Set columns", "int"),
    Field("pitch_x_cleaning", "X step size", "mm"),
    Field("pitch_y_cleaning", "Y step size", "mm"),
    Field("dispense_vol_cleaning", "Dispense volume cleaning", "uL"),
    Field(
        "droplet_forming_time_cleaning",
        "Droplet forming time",
        "s",
        default=0.5,
    ),
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


__all__ = ["CLEANING_FIELDS", "GRID_FIELDS", "WASHING_FIELDS"]
