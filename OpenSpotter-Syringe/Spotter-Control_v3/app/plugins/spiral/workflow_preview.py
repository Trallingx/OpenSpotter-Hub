"""Representative workflow event values owned by the spiral plugin."""

from __future__ import annotations

import math

from ...core.workflow_preview import (
    RINSE_TRIGGERS,
    WorkflowPreviewSample,
    populate_refill_preview,
)
from .workflow import WORKFLOW_CONTRIBUTION


SPIRAL_WORKFLOW_PREVIEW_TRIGGERS = frozenset(
    contribution.name
    for contribution in WORKFLOW_CONTRIBUTION.triggers
)
_SPIRAL_SPOT_TRIGGERS = frozenset(
    ("spiral_drop", "spiral_continuous")
)


def _enrich_spiral_spot(sample: WorkflowPreviewSample) -> None:
    center_x = sample.number("spiral.center_x")
    center_y = sample.number("spiral.center_y")
    start_radius = max(0.0, sample.number("spiral.start_radius"))
    spacing = max(1e-9, sample.number("spiral.spacing_mm", 1.5))
    base_ul = max(0.0, sample.number("spiral.dispense_vol"))
    theta = 0.0
    radius = start_radius
    segment_length = 0.0
    continuous = sample.trigger == "spiral_continuous"
    if continuous:
        theta = max(
            1e-9,
            sample.custom_number("spiral_resolution_radians", 0.08),
        )
        radius = start_radius + spacing * theta / (2.0 * math.pi)
        previous_x = center_x + start_radius
        previous_y = center_y
        current_x = center_x + radius * math.cos(theta)
        current_y = center_y + radius * math.sin(theta)
        segment_length = math.hypot(
            current_x - previous_x,
            current_y - previous_y,
        )
    else:
        current_x = center_x + radius
        current_y = center_y

    volume_ul = (
        max(base_ul, segment_length * base_ul)
        if continuous
        else base_ul
    )
    sample.put("runtime.spot.index", 1 if continuous else 0)
    sample.put("runtime.spot.start_index", 0)
    sample.put("runtime.spot.x", current_x)
    sample.put("runtime.spot.y", current_y)
    sample.put("runtime.spot.dispense_ul", volume_ul)
    sample.put(
        "runtime.spot.dispense_mm",
        volume_ul * sample.custom_number("syringe_mm_per_ul", 1.0),
    )
    sample.put("runtime.spot.segment_length", segment_length)
    sample.put("runtime.spot.theta", theta)
    sample.put("runtime.spot.radius", radius)
    sample.put("runtime.spot.continuous", continuous)


def _enrich_refill(sample: WorkflowPreviewSample) -> None:
    base_ul = max(0.0, sample.number("spiral.dispense_vol"))
    # Preserve the established reserve preview: a staged maintenance droplet
    # may be larger than the spiral's base segment even though spiral jobs do
    # not reserve a complete cleaning grid.
    reserve_basis_ul = max(
        base_ul,
        sample.number("cleaning.dispense_vol_cleaning"),
    )
    populate_refill_preview(
        sample,
        remaining_spots_ul=base_ul,
        cleaning_ul=0.0,
        reserve_basis_ul=reserve_basis_ul,
        container_id=sample.integer("container.id"),
    )


def enrich_spiral_workflow_preview(sample: WorkflowPreviewSample) -> None:
    """Add spiral spot, refill, and emptying-container samples."""

    if sample.trigger in _SPIRAL_SPOT_TRIGGERS:
        _enrich_spiral_spot(sample)
    if sample.trigger == "syringe_reload":
        _enrich_refill(sample)
    if sample.trigger in RINSE_TRIGGERS:
        sample.select_container(
            sample.integer(
                "spiral.leftovers_into",
                sample.integer("container.id"),
            )
        )


__all__ = [
    "SPIRAL_WORKFLOW_PREVIEW_TRIGGERS",
    "enrich_spiral_workflow_preview",
]
