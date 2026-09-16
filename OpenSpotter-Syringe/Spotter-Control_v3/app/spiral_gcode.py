"""Compatibility exports for built-in spiral G-code generation."""

from .plugins.spiral.generation import _collect_spiral_job, save_spiral_gcode

__all__ = ["_collect_spiral_job", "save_spiral_gcode"]
