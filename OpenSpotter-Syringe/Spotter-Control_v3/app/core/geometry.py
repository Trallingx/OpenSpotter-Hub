"""Shared machine-coordinate geometry that is independent of pattern type."""

from __future__ import annotations

from typing import Any, Dict, Mapping


def acceptance_square(values: Mapping[str, Any]) -> Dict[str, float]:
    """Return the configured acceptance rectangle in machine coordinates.

    The historical ``y_bottom``/``y_top`` names are retained for workflow
    compatibility.  With OpenSpotter's positive-down Y convention they
    correspond to the visual top and bottom edges respectively.
    """

    base_x = float(values["base_square_x"])
    base_y = float(values["base_square_y"])
    acceptance_x = float(values["acceptance_square_x"])
    acceptance_y = float(values["acceptance_square_y"])
    origin_x = float(values["x_cord_of_y_line"])
    origin_y = float(values["y_cord_of_x_line"])
    x_left = origin_x + (base_x - acceptance_x) / 2.0
    y_bottom = origin_y + (base_y - acceptance_y) / 2.0
    return {
        "x_left": x_left,
        "x_right": x_left + acceptance_x,
        "y_bottom": y_bottom,
        "y_top": y_bottom + acceptance_y,
    }


__all__ = ["acceptance_square"]
