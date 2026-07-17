"""Spiral-specific workflow-event planning."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, MutableSequence, Optional

from ...core.domain import volume_to_mm
from ...core.gcode.lifecycle import (
    _millimeters_per_microliter,
    emit_event,
    load_syringe,
)


def generate_spiral_events(
    file,
    engine,
    common: Mapping[str, Any],
    spiral_values: Mapping[str, Any],
    points: Iterable[Mapping[str, Any]],
    loading_container,
    loading_container_id: int,
    syringe_tracker: Optional[MutableSequence[float]] = None,
) -> Dict[str, Any]:
    """Emit a planned spiral with capacity-aware automatic reloads."""

    syringe_tracker = syringe_tracker or [0.0]
    mode = str(spiral_values.get("spiral_mode", "drop")).strip().lower()
    planned_points = [dict(point) for point in points]
    cap_mm = volume_to_mm(
        float(common["max_syringe_vol"]),
        _millimeters_per_microliter(engine),
    )
    if cap_mm <= 0:
        raise ValueError(
            "Maximum syringe volume must be positive for spiral generation"
        )
    dispense_amounts = [
        float(point.get("dispense_mm", 0.0))
        for point in planned_points
    ]
    if any(amount < 0 for amount in dispense_amounts):
        raise ValueError("Spiral dispense amounts cannot be negative")
    remaining_mm = sum(dispense_amounts)
    emit_event(file, engine, "spiral_start", {"spiral": dict(spiral_values)})
    spots = 0
    total_ul = 0.0
    for spot in planned_points:
        required_mm = float(spot.get("dispense_mm", 0.0))
        if required_mm > cap_mm + 1e-6:
            raise ValueError(
                "A spiral segment requires more liquid than the configured "
                "syringe capacity"
            )
        reloaded = False
        if syringe_tracker[0] + 1e-6 < required_mm:
            reserve_mm = required_mm * (
                1.0
                + max(
                    0.0,
                    float(common["drop_extra_aspirate"]),
                )
            )
            total_needed_mm = remaining_mm + reserve_mm
            target_fill_mm = min(total_needed_mm, cap_mm)
            load_syringe(
                file=file,
                engine=engine,
                common=common,
                container=loading_container,
                total_fill_ul=(
                    target_fill_mm
                    / _millimeters_per_microliter(engine)
                ),
                syringe_tracker=syringe_tracker,
                refill_details={
                    "reason": (
                        "spiral_start"
                        if spots == 0
                        else "automatic_refill"
                    ),
                    "dynamic": spots > 0,
                    "container_id": loading_container_id,
                    "target_fill_mm": target_fill_mm,
                    "target_fill_ul": (
                        target_fill_mm
                        / _millimeters_per_microliter(engine)
                    ),
                    "remaining_spots_mm": remaining_mm,
                    "cleaning_mm": 0.0,
                    "reserve_mm": reserve_mm,
                    "total_needed_mm": total_needed_mm,
                    "cap_mm": cap_mm,
                },
            )
            reloaded = True
        event_spot = dict(spot)
        # Reloading leaves the tool at the container/safe height. Re-enter a
        # continuous path through the configured drop/reposition event before
        # later continuous segments resume.
        if reloaded and event_spot.get("continuous"):
            event_spot["continuous"] = False
        overrides = {
            "spiral": dict(spiral_values),
            "runtime": {"spot": event_spot},
        }
        emit_event(
            file,
            engine,
            (
                "spiral_continuous"
                if event_spot.get("continuous")
                else "spiral_drop"
            ),
            overrides,
        )
        syringe_tracker[0] = max(
            0.0,
            syringe_tracker[0] - required_mm,
        )
        remaining_mm = max(0.0, remaining_mm - required_mm)
        spots += 1
        total_ul += float(spot.get("dispense_ul", 0.0))
    return {
        "total_dispense_uL": total_ul,
        "spots_count": spots,
        "mode": mode,
    }


__all__ = ["generate_spiral_events"]
