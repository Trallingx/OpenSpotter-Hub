"""Shared machine-coordinate geometry that is independent of pattern type."""

from __future__ import annotations

from typing import Any, Dict, Mapping


def acceptance_square(values: Mapping[str, Any]) -> Dict[str, float]:
    """Return the configured acceptance rectangle in machine coordinates.

    The historical ``y_bottom``/``y_top`` names are retained for workflow
    compatibility.  With OpenSpotter's positive-down Y convention they
    correspond to the visual top and bottom edges respectively.
    """

    x_left = float(values["acceptance_square_left"])
    y_top = float(values["acceptance_square_top"])
    acceptance_x = float(values["acceptance_square_width"])
    acceptance_y = float(values["acceptance_square_height"])
    return {
        "x_left": x_left,
        "x_right": x_left + acceptance_x,
        "y_bottom": y_top,
        "y_top": y_top + acceptance_y,
    }


__all__ = ["acceptance_square"]
