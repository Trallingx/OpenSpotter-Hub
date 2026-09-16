"""Pure rectangular-grid geometry owned by the grid plugin."""

from __future__ import annotations

from typing import List, Tuple


Point = Tuple[float, float]


def create_coordinates(
    rows: int,
    cols: int,
    x_offset: float,
    grid_x_offset: float,
    x_shift: float,
    y_offset: float,
    grid_y_offset: float,
    y_shift: float,
) -> List[Point]:
    """Return row-major coordinates using numeric machine-space offsets."""

    row_count = max(0, int(rows))
    column_count = max(0, int(cols))
    start_x = float(x_offset) + float(grid_x_offset)
    start_y = float(y_offset) + float(grid_y_offset)
    step_x = float(x_shift)
    step_y = float(y_shift)
    return [
        (start_x + column * step_x, start_y + row * step_y)
        for row in range(row_count)
        for column in range(column_count)
    ]


__all__ = ["create_coordinates"]
