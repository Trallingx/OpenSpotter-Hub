"""Representative workflow event values owned by the grid plugin."""

from __future__ import annotations

from ...core.workflow_preview import (
    RINSE_TRIGGERS,
    WorkflowPreviewSample,
    populate_refill_preview,
)
from .workflow import WORKFLOW_CONTRIBUTION


GRID_WORKFLOW_PREVIEW_TRIGGERS = frozenset(
    contribution.name
    for contribution in WORKFLOW_CONTRIBUTION.triggers
)

_GRID_SPOT_TRIGGERS = frozenset(
    ("grid_spot_move", "grid_row_start", "grid_spot_dispense")
)
_CLEANING_SPOT_TRIGGERS = frozenset(
    (
        "cleaning_spot_move",
        "cleaning_row_start",
        "cleaning_spot_dispense",
    )
)
_WASHING_TRIGGERS = frozenset(
    ("washing_start", "washing_cycle", "washing_end")
)


def _enrich_grid_spot(sample: WorkflowPreviewSample) -> None:
    anchor_x = (
        sample.number("global.x_cord_of_y_line")
        + sample.number("global.tuning_offset_x")
    )
    anchor_y = (
        sample.number("global.y_cord_of_x_line")
        + sample.number("global.tuning_offset_y")
    )
    volume_ul = sample.number("grid.dispense_vol")
    sample.put("runtime.spot.index", 0)
    sample.put("runtime.spot.row", 0)
    sample.put("runtime.spot.column", 0)
    sample.put(
        "runtime.spot.x",
        anchor_x + sample.number("grid.grid_offset_x"),
    )
    sample.put(
        "runtime.spot.y",
        anchor_y + sample.number("grid.grid_offset_y"),
    )
    sample.put(
        "runtime.spot.dispense_mm",
        volume_ul * sample.custom_number("syringe_mm_per_ul", 1.0),
    )
    sample.put("runtime.spot.is_row_start", True)


def _enrich_cleaning_spot(sample: WorkflowPreviewSample) -> None:
    anchor_x = (
        sample.number("global.x_cord_of_y_line")
        + sample.number("global.tuning_offset_x")
    )
    anchor_y = (
        sample.number("global.y_cord_of_x_line")
        + sample.number("global.tuning_offset_y")
    )
    volume_ul = sample.number("cleaning.dispense_vol_cleaning")
    sample.put("runtime.spot.index", 0)
    sample.put("runtime.spot.row", 0)
    sample.put("runtime.spot.column", 0)
    sample.put(
        "runtime.spot.x",
        anchor_x + sample.number("cleaning.grid_offset_x_cleaning"),
    )
    sample.put(
        "runtime.spot.y",
        anchor_y + sample.number("cleaning.grid_offset_y_cleaning"),
    )
    sample.put(
        "runtime.spot.dispense_mm",
        volume_ul * sample.custom_number("syringe_mm_per_ul", 1.0),
    )
    sample.put("runtime.spot.is_row_start", True)
    sample.put("cleaning.cycle", 0)


def _enrich_refill(sample: WorkflowPreviewSample) -> None:
    base_ul = max(0.0, sample.number("grid.dispense_vol"))
    row_add_ul = max(0.0, sample.number("grid.row_add_volume"))
    rows = max(0, sample.integer("grid.rows", 1))
    columns = max(0, sample.integer("grid.cols", 1))
    remaining_spots_ul = (
        rows * columns * base_ul
        + max(0, rows - 1) * row_add_ul
    )
    cleaning_dispense_ul = max(
        0.0,
        sample.number("cleaning.dispense_vol_cleaning"),
    )
    cleaning_ul = (
        max(0, sample.integer("cleaning.rows_cleaning"))
        * max(0, sample.integer("cleaning.cols_cleaning"))
        * cleaning_dispense_ul
    )
    populate_refill_preview(
        sample,
        remaining_spots_ul=remaining_spots_ul,
        cleaning_ul=cleaning_ul,
        reserve_basis_ul=max(
            base_ul + row_add_ul,
            cleaning_dispense_ul,
        ),
        container_id=sample.integer("container.id"),
    )


def enrich_grid_workflow_preview(sample: WorkflowPreviewSample) -> None:
    """Add grid, cleaning, washing, refill, and emptying samples."""

    if sample.trigger in _GRID_SPOT_TRIGGERS:
        _enrich_grid_spot(sample)
    elif sample.trigger in _CLEANING_SPOT_TRIGGERS:
        _enrich_cleaning_spot(sample)

    if sample.trigger == "syringe_reload":
        _enrich_refill(sample)

    if sample.trigger in _WASHING_TRIGGERS:
        wash_x = sample.number("washing.washing_x_pos")
        sample.put("runtime.washing.cycle", 0)
        sample.put("runtime.washing.x_start", wash_x)
        sample.put(
            "runtime.washing.x_end",
            wash_x + sample.number("washing.washing_line_lenght"),
        )

    if sample.trigger in RINSE_TRIGGERS:
        sample.select_container(
            sample.integer(
                "grid.leftovers_into",
                sample.integer("container.id"),
            )
        )


__all__ = [
    "GRID_WORKFLOW_PREVIEW_TRIGGERS",
    "enrich_grid_workflow_preview",
]
