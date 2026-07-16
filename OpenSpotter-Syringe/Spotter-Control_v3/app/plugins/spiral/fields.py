"""Field schema owned by the built-in spiral plugin."""

from typing import List

from ...core.schema import Field


SPIRAL_FIELDS: List[Field] = [
    Field("center_x", "Center X (mm)", unit="mm", default=0.0),
    Field("center_y", "Center Y (mm)", unit="mm", default=0.0),
    Field("start_radius", "Start Radius (mm)", unit="mm", default=0.0),
    Field("turns", "Turns", unit="float", default=5.0),
    Field("num_starts", "Starts", unit="int", default=1),
    Field("spacing_mm", "Spacing (mm)", unit="mm", default=1.5),
    Field("dispense_vol", "Dispense uL", unit="uL", default=0.003),
    Field(
        "spiral_mode",
        "Spiral Mode",
        unit="str",
        default="drop",
        widget="combobox",
        choices=("drop", "continuous"),
    ),
    Field(
        "interleave",
        "Interleave Starts",
        unit="bool",
        default=False,
        widget="combobox",
        choices=(False, True),
    ),
    Field("loading_from", "Loading from (1-6)", unit="int", default=1),
    Field("leftovers_into", "Leftovers into (1-6)", unit="int", default=1),
    Field(
        "z_contact",
        "Needle-Substrate Distance",
        unit="mm",
        default=0.01,
    ),
    Field(
        "droplet_forming_time",
        "Droplet forming time",
        unit="s",
        default=0.5,
    ),
]


__all__ = ["SPIRAL_FIELDS"]
