"""Backward-compatible exports for the former mixed utility module.

New code should import from the owning core or plugin module.  This facade is
kept so existing profiles, tests, and downstream scripts can migrate without a
flag day.
"""

from .core.configuration import (
    entries_to_dict,
    read_defaults,
    save_defaults,
    write_state,
)
from .core.domain import Container, build_containers, volume_to_mm
from .core.gcode.profiles import write_generation_settings_file
from .core.schema import Field, coerce_field_value, parse_widget_entries
from .plugins.grid.geometry import create_coordinates


__all__ = [
    "Container",
    "Field",
    "build_containers",
    "coerce_field_value",
    "create_coordinates",
    "entries_to_dict",
    "parse_widget_entries",
    "read_defaults",
    "save_defaults",
    "volume_to_mm",
    "write_generation_settings_file",
    "write_state",
]
