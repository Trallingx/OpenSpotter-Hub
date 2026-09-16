"""Pattern-independent workflow lifecycle and syringe operations.

Pattern plugins plan their own geometry and maintenance cadence. This module
owns the shared workflow writer plus loading, emptying, and rinsing behavior so
all plugins use the same fluidic lifecycle.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableSequence, Optional

from ..domain import volume_to_mm


def emit_event(
    file,
    engine,
    trigger: str,
    overrides: Optional[Mapping[str, Any]] = None,
) -> None:
    """Render one workflow trigger and append it to an open output stream."""

    rendered = engine.emit(trigger, dict(overrides or {}))
    if rendered:
        file.write(rendered)


def start_program(file, engine) -> None:
    """Emit the shared job-start workflow event."""

    emit_event(file, engine, "job_start")


def finish_program(file, engine) -> None:
    """Emit the shared job-end workflow event."""

    emit_event(file, engine, "job_end")


def _millimeters_per_microliter(engine) -> float:
    """Resolve and validate the workflow-owned syringe conversion factor."""

    try:
        if hasattr(engine, "custom_value"):
            factor = float(engine.custom_value("syringe_mm_per_ul"))
        else:
            factor = float(engine.custom_values["syringe_mm_per_ul"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Workflow variable custom.syringe_mm_per_ul must be a positive number"
        ) from exc
    if factor <= 0:
        raise ValueError(
            "Workflow variable custom.syringe_mm_per_ul must be positive"
        )
    return factor


def load_syringe(
    file,
    engine,
    common: Mapping[str, Any],
    container,
    total_fill_ul: float,
    syringe_tracker: Optional[MutableSequence[float]] = None,
    refill_details: Optional[Mapping[str, Any]] = None,
) -> None:
    """Emit one configured loading block and update remaining plunger travel."""

    if container is None:
        raise ValueError("Loading container is not configured")
    if float(total_fill_ul) < 0:
        raise ValueError("Syringe fill volume cannot be negative")
    if float(common["priming_vol"]) < 0:
        raise ValueError("Priming volume cannot be negative")

    mm_per_ul = _millimeters_per_microliter(engine)
    target_fill_mm = volume_to_mm(total_fill_ul, mm_per_ul)
    priming_mm = volume_to_mm(common["priming_vol"], mm_per_ul)
    fill_mm = target_fill_mm + priming_mm
    details: Dict[str, Any] = {
        "reason": "initial",
        "dynamic": False,
        "fill_mm": fill_mm,
        "priming_mm": priming_mm,
        "target_fill_mm": target_fill_mm,
        "target_fill_ul": float(total_fill_ul),
        "remaining_spots_mm": target_fill_mm,
        "cleaning_mm": 0.0,
        "reserve_mm": 0.0,
        "total_needed_mm": target_fill_mm,
        "cap_mm": target_fill_mm,
    }
    details.update(dict(refill_details or {}))

    emit_event(
        file,
        engine,
        "syringe_reload",
        {
            "container": {
                "id": details.get("container_id", 0),
                "x": container.x,
                "y": container.y,
                "z": container.z_filling_height,
            },
            "runtime": {"refill": details},
        },
    )
    if syringe_tracker is not None:
        syringe_tracker[0] = max(0.0, target_fill_mm)


def empty_syringe(
    file,
    engine,
    common: Mapping[str, Any],
    container,
    container_id: int,
    final_rinse_enabled: bool,
    rinsing_cycles: int,
    syringe_tracker: Optional[MutableSequence[float]] = None,
) -> None:
    """Emit emptying and optional two-pass rinse operations."""

    if container is None:
        raise ValueError("Emptying container is not configured")
    container_context = {
        "id": container_id,
        "x": container.x,
        "y": container.y,
        "z": container.z_filling_height,
    }
    base = {
        "container": container_context,
        "runtime": {
            "rinse": {
                "cycle": 0,
                "phase": 0,
                "max_mm": common["max_syringe_mm"],
                "min_mm": common["min_syringe_mm"],
            }
        },
    }
    emit_event(file, engine, "syringe_empty_start", base)
    if syringe_tracker is not None:
        syringe_tracker[0] = 0.0

    if final_rinse_enabled:
        cycles = max(0, int(rinsing_cycles))
        for phase in (1, 2):
            if phase == 2:
                emit_event(file, engine, "rinse_midpoint", base)
            for cycle in range(cycles):
                emit_event(
                    file,
                    engine,
                    "rinse_cycle",
                    {
                        "container": container_context,
                        "runtime": {
                            "rinse": {
                                "cycle": cycle,
                                "phase": phase,
                                "max_mm": common["max_syringe_mm"],
                                "min_mm": common["min_syringe_mm"],
                            }
                        },
                    },
                )
    end_context = {
        "container": container_context,
        "runtime": {
            "rinse": {
                "cycle": (
                    max(0, int(rinsing_cycles))
                    if final_rinse_enabled
                    else 0
                ),
                "phase": 2 if final_rinse_enabled else 0,
                "max_mm": common["max_syringe_mm"],
                "min_mm": common["min_syringe_mm"],
            }
        },
    }
    emit_event(file, engine, "syringe_empty_end", end_context)


__all__ = [
    "_millimeters_per_microliter",
    "emit_event",
    "empty_syringe",
    "finish_program",
    "load_syringe",
    "start_program",
]
