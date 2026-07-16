"""Numeric job planning and workflow-event emission.

This module owns liquid/state calculations and iteration.  Machine commands live
in ``config/config_gcode_workflow.json`` and are rendered by ``WorkflowEngine``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, MutableSequence, Optional

from .SpotterFunctions import create_coordinates, volume_to_mm


def emit_event(file, engine, trigger: str, overrides: Optional[Mapping[str, Any]] = None) -> None:
    """Render one workflow trigger and append it to an open output stream."""
    rendered = engine.emit(trigger, dict(overrides or {}))
    if rendered:
        file.write(rendered)


def start_program(file, engine) -> None:
    emit_event(file, engine, "job_start")


def write_anchor_calibration(file, engine, common: Mapping[str, Any]) -> None:
    emit_event(
        file,
        engine,
        "anchor_calibration",
        {
            "runtime": {
                "anchor": {
                    "x": common["x_abs"],
                    "y": common["y_abs"],
                }
            }
        },
    )


def finish_program(file, engine) -> None:
    emit_event(file, engine, "job_end")


def _millimeters_per_microliter(engine) -> float:
    try:
        if hasattr(engine, "custom_value"):
            factor = float(engine.custom_value("syringe_mm_per_ul"))
        else:
            factor = float(engine.custom_values["syringe_mm_per_ul"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Workflow variable custom.syringe_mm_per_ul must be a positive number") from exc
    if factor <= 0:
        raise ValueError("Workflow variable custom.syringe_mm_per_ul must be positive")
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


def clean_grid(
    file,
    engine,
    common: Mapping[str, Any],
    grid_values: Mapping[str, Any],
    cleaning_values: Mapping[str, Any],
    anchor_x: float,
    anchor_y: float,
    syringe_tracker: Optional[MutableSequence[float]] = None,
    cleaning_cycle_counter: Optional[MutableSequence[int]] = None,
) -> None:
    """Plan one cleaning grid and emit its configured workflow sections."""
    rows = int(cleaning_values["rows_cleaning"])
    cols = int(cleaning_values["cols_cleaning"])
    if rows < 0 or cols < 0:
        raise ValueError("Cleaning grid dimensions cannot be negative")
    if rows == 0 or cols == 0:
        return

    cycle_index = int(cleaning_cycle_counter[0]) if cleaning_cycle_counter is not None else 0
    origin_x = anchor_x + cycle_index * float(cleaning_values.get("x_relative_increase", 0.0))
    origin_y = anchor_y + cycle_index * float(cleaning_values.get("y_relative_increase", 0.0))
    coordinates = create_coordinates(
        rows,
        cols,
        origin_x,
        float(cleaning_values["grid_offset_x_cleaning"]),
        float(cleaning_values["pitch_x_cleaning"]),
        origin_y,
        float(cleaning_values["grid_offset_y_cleaning"]),
        float(cleaning_values["pitch_y_cleaning"]),
    )
    cleaning_volume_ul = float(cleaning_values["dispense_vol_cleaning"])
    if cleaning_volume_ul < 0:
        raise ValueError("Cleaning dispense volume cannot be negative")
    dispense_mm = volume_to_mm(
        cleaning_volume_ul,
        _millimeters_per_microliter(engine),
    )
    required_mm = rows * cols * dispense_mm
    if syringe_tracker is not None and syringe_tracker[0] + 1e-6 < required_mm:
        raise ValueError(
            "Cleaning grid requires more liquid than is currently loaded"
        )
    cleaning_context = dict(cleaning_values)
    cleaning_context["cycle"] = cycle_index
    emit_event(
        file,
        engine,
        "cleaning_start",
        {"grid": dict(grid_values), "cleaning": cleaning_context},
    )

    for index, (x_pos, y_pos) in enumerate(coordinates):
        row, column = divmod(index, cols)
        spot = {
            "index": index,
            "row": row,
            "column": column,
            "x": x_pos,
            "y": y_pos,
            "dispense_mm": dispense_mm,
            "is_row_start": column == 0,
        }
        overrides = {
            "grid": dict(grid_values),
            "cleaning": cleaning_context,
            "runtime": {"spot": spot},
        }
        emit_event(file, engine, "cleaning_spot_move", overrides)
        if column == 0:
            emit_event(file, engine, "cleaning_row_start", overrides)
        emit_event(file, engine, "cleaning_spot_dispense", overrides)
        if syringe_tracker is not None:
            syringe_tracker[0] = max(0.0, syringe_tracker[0] - dispense_mm)

    if cleaning_cycle_counter is not None:
        cleaning_cycle_counter[0] += 1


def wash_needle(
    file,
    engine,
    grid_values: Mapping[str, Any],
    washing_values: Mapping[str, Any],
) -> None:
    """Emit one washing operation using a configured repeated cycle section."""
    washing = dict(washing_values)
    x_start = float(washing["washing_x_pos"])
    x_end = x_start + float(washing["washing_line_lenght"])
    base = {
        "grid": dict(grid_values),
        "washing": washing,
        "runtime": {"washing": {"cycle": 0, "x_start": x_start, "x_end": x_end}},
    }
    emit_event(file, engine, "washing_start", base)
    for cycle in range(max(0, int(washing["washing_cycles"]))):
        event_context = {
            **base,
            "runtime": {"washing": {"cycle": cycle, "x_start": x_start, "x_end": x_end}},
        }
        emit_event(file, engine, "washing_cycle", event_context)
    emit_event(file, engine, "washing_end", base)


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
                "cycle": max(0, int(rinsing_cycles)) if final_rinse_enabled else 0,
                "phase": 2 if final_rinse_enabled else 0,
                "max_mm": common["max_syringe_mm"],
                "min_mm": common["min_syringe_mm"],
            }
        },
    }
    emit_event(file, engine, "syringe_empty_end", end_context)


def calculate_grid_refill_ul(
    common: Mapping[str, Any],
    grid_values: Mapping[str, Any],
    cleaning_values: Mapping[str, Any],
    flags: Mapping[str, bool],
) -> float:
    """Calculate the useful refill cap shared by generation and preview."""
    rows = int(grid_values["rows"])
    cols = int(grid_values["cols"])
    base_volume = float(grid_values["dispense_vol"])
    row_add_volume = float(grid_values.get("row_add_volume", 0.0))
    main_grid_fill = (
        rows * cols * base_volume
        + max(0, rows - 1) * row_add_volume
    )
    cleaning_grid_fill = 0.0
    largest_spot_volume = max(base_volume, base_volume + row_add_volume)
    if flags.get("cleaning_enabled"):
        cleaning_spot_volume = float(
            cleaning_values.get("dispense_vol_cleaning", 0.0)
        )
        cleaning_grid_fill = (
            int(cleaning_values.get("rows_cleaning", 0))
            * int(cleaning_values.get("cols_cleaning", 0))
            * cleaning_spot_volume
        )
        largest_spot_volume = max(largest_spot_volume, cleaning_spot_volume)
    reserve_fill = largest_spot_volume * (
        1.0 + max(0.0, float(common.get("drop_extra_aspirate", 0.0)))
    )
    return min(
        float(common["max_syringe_vol"]),
        main_grid_fill + cleaning_grid_fill + reserve_fill,
    )


def generate_grid_events(
    file,
    engine,
    common: Mapping[str, Any],
    grid_values: Mapping[str, Any],
    cleaning_values: Mapping[str, Any],
    washing_values: Mapping[str, Any],
    flags: Mapping[str, bool],
    containers: Mapping[int, Any],
    refill_ul: float,
    washing_spot_counter: Optional[MutableSequence[int]] = None,
    syringe_tracker: Optional[MutableSequence[float]] = None,
    cleaning_cycle_counter: Optional[MutableSequence[int]] = None,
) -> int:
    """Plan a grid, including refills and maintenance, and emit workflow events."""
    washing_spot_counter = washing_spot_counter or [0]
    syringe_tracker = syringe_tracker or [0.0]
    cleaning_cycle_counter = cleaning_cycle_counter or [0]

    rows = int(grid_values["rows"])
    cols = int(grid_values["cols"])
    if rows <= 0 or cols <= 0:
        return 0
    loading_container_id = int(grid_values.get("loading_from", 1))
    loading_container = containers.get(loading_container_id)
    if loading_container is None:
        raise ValueError(f"Container {loading_container_id} is not configured for loading")

    coordinates = create_coordinates(
        rows,
        cols,
        common["x_offset"],
        float(grid_values["grid_offset_x"]),
        float(grid_values["pitch_x"]),
        common["y_offset"],
        float(grid_values["grid_offset_y"]),
        float(grid_values["pitch_y"]),
    )
    mm_per_ul = _millimeters_per_microliter(engine)
    base_volume_ul = float(grid_values["dispense_vol"])
    row_add_ul = float(grid_values.get("row_add_volume", 0.0))
    if base_volume_ul < 0:
        raise ValueError("Grid dispense volume cannot be negative")
    spot_volumes_mm = []
    for index in range(rows * cols):
        volume_ul = base_volume_ul + (row_add_ul if index and index % cols == 0 else 0.0)
        if volume_ul < 0:
            raise ValueError("Grid row-add volume produces a negative spot volume")
        spot_volumes_mm.append(volume_to_mm(volume_ul, mm_per_ul))
    remaining_spots_mm = sum(spot_volumes_mm)
    if float(refill_ul) <= 0:
        raise ValueError("Refill capacity must be positive")
    refill_cap_mm = volume_to_mm(refill_ul, mm_per_ul)
    cleaning_mm = 0.0
    largest_required_ul = max(
        [base_volume_ul, base_volume_ul + row_add_ul],
    )
    if flags.get("cleaning_enabled"):
        cleaning_rows = int(cleaning_values["rows_cleaning"])
        cleaning_cols = int(cleaning_values["cols_cleaning"])
        if cleaning_rows < 0 or cleaning_cols < 0:
            raise ValueError("Cleaning grid dimensions cannot be negative")
        cleaning_spot_ul = float(cleaning_values["dispense_vol_cleaning"])
        if cleaning_spot_ul < 0:
            raise ValueError("Cleaning dispense volume cannot be negative")
        cleaning_mm = volume_to_mm(
            cleaning_rows
            * cleaning_cols
            * cleaning_spot_ul,
            mm_per_ul,
        )
        largest_required_ul = max(largest_required_ul, cleaning_spot_ul)
    reserve_mm = volume_to_mm(
        largest_required_ul
        * (1.0 + max(0.0, float(common.get("drop_extra_aspirate", 0.0)))),
        mm_per_ul,
    )

    largest_spot_mm = max(spot_volumes_mm, default=0.0)
    if largest_spot_mm > refill_cap_mm + 1e-6:
        raise ValueError("A print spot exceeds the configured refill capacity")
    if flags.get("cleaning_enabled"):
        if cleaning_mm + largest_spot_mm > refill_cap_mm + 1e-6:
            raise ValueError(
                "Cleaning grid plus one print spot exceeds the refill capacity"
            )

    def run_cleaning() -> None:
        if syringe_tracker[0] + 1e-6 < cleaning_mm:
            if ensure_loaded(cleaning_mm, remaining_spots_mm):
                return
        clean_grid(
            file,
            engine,
            common,
            grid_values,
            cleaning_values,
            common["x_offset"],
            common["y_offset"],
            syringe_tracker,
            cleaning_cycle_counter,
        )

    def run_washing() -> None:
        wash_needle(file, engine, grid_values, washing_values)
        washing_spot_counter[0] = 0

    def ensure_loaded(required_mm: float, remaining_mm: float) -> bool:
        epsilon = 1e-6
        if syringe_tracker[0] > epsilon and syringe_tracker[0] + epsilon >= required_mm:
            return False
        total_needed_mm = remaining_mm + cleaning_mm + reserve_mm
        target_fill_mm = min(total_needed_mm, refill_cap_mm) if total_needed_mm > 0 else refill_cap_mm
        load_syringe(
            file,
            engine,
            common,
            loading_container,
            target_fill_mm / mm_per_ul,
            syringe_tracker,
            {
                "reason": "automatic_refill",
                "dynamic": True,
                "container_id": loading_container_id,
                "target_fill_mm": target_fill_mm,
                "target_fill_ul": target_fill_mm / mm_per_ul,
                "remaining_spots_mm": remaining_mm,
                "cleaning_mm": cleaning_mm,
                "reserve_mm": reserve_mm,
                "total_needed_mm": total_needed_mm,
                "cap_mm": refill_cap_mm,
            },
        )
        if flags.get("washing_enabled") and flags.get("wash_after_loading"):
            run_washing()
        if flags.get("cleaning_enabled"):
            run_cleaning()
        return True

    if flags.get("cleaning_enabled"):
        ensure_loaded(0.0, remaining_spots_mm)
        washing_spot_counter[0] = 0

    emit_event(file, engine, "grid_start", {"grid": dict(grid_values)})
    cleaning_interval = max(0, int(cleaning_values.get("spots_before_cleaning", 0)))
    washing_interval = max(0, int(washing_values.get("washing_after_x_spots", 0)))

    for index, ((x_pos, y_pos), dispense_mm) in enumerate(zip(coordinates, spot_volumes_mm)):
        ensure_loaded(dispense_mm, remaining_spots_mm)
        row, column = divmod(index, cols)
        spot = {
            "index": index,
            "row": row,
            "column": column,
            "x": x_pos,
            "y": y_pos,
            "dispense_mm": dispense_mm,
            "is_row_start": column == 0,
        }
        overrides = {"grid": dict(grid_values), "runtime": {"spot": spot}}
        emit_event(file, engine, "grid_spot_move", overrides)
        if column == 0:
            emit_event(file, engine, "grid_row_start", overrides)
        emit_event(file, engine, "grid_spot_dispense", overrides)
        syringe_tracker[0] = max(0.0, syringe_tracker[0] - dispense_mm)
        remaining_spots_mm = max(0.0, remaining_spots_mm - dispense_mm)
        washing_spot_counter[0] += 1

        cleaned = False
        if flags.get("washing_enabled") and washing_interval:
            if washing_spot_counter[0] >= washing_interval:
                run_washing()
                if flags.get("cleaning_enabled"):
                    run_cleaning()
                    cleaned = True
        if flags.get("cleaning_enabled") and cleaning_interval:
            if (index + 1) % cleaning_interval == 0 and not cleaned:
                run_cleaning()

    if flags.get("washing_enabled"):
        run_washing()
    return rows * cols


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
    cap_mm = volume_to_mm(float(common["max_syringe_vol"]), _millimeters_per_microliter(engine))
    if cap_mm <= 0:
        raise ValueError("Maximum syringe volume must be positive for spiral generation")
    dispense_amounts = [float(point.get("dispense_mm", 0.0)) for point in planned_points]
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
                "A spiral segment requires more liquid than the configured syringe capacity"
            )
        reloaded = False
        if syringe_tracker[0] + 1e-6 < required_mm:
            reserve_mm = required_mm * (1.0 + max(0.0, float(common["drop_extra_aspirate"])))
            total_needed_mm = remaining_mm + reserve_mm
            target_fill_mm = min(total_needed_mm, cap_mm)
            load_syringe(
                file=file,
                engine=engine,
                common=common,
                container=loading_container,
                total_fill_ul=target_fill_mm / _millimeters_per_microliter(engine),
                syringe_tracker=syringe_tracker,
                refill_details={
                    "reason": "spiral_start" if spots == 0 else "automatic_refill",
                    "dynamic": spots > 0,
                    "container_id": loading_container_id,
                    "target_fill_mm": target_fill_mm,
                    "target_fill_ul": target_fill_mm / _millimeters_per_microliter(engine),
                    "remaining_spots_mm": remaining_mm,
                    "cleaning_mm": 0.0,
                    "reserve_mm": reserve_mm,
                    "total_needed_mm": total_needed_mm,
                    "cap_mm": cap_mm,
                },
            )
            reloaded = True
        event_spot = dict(spot)
        # Reloading leaves the tool at the container/safe height.  Re-enter a
        # continuous path through the configured drop/reposition event before
        # later continuous segments resume; otherwise the next segment would
        # execute from the container position.
        if reloaded and event_spot.get("continuous"):
            event_spot["continuous"] = False
        overrides = {
            "spiral": dict(spiral_values),
            "runtime": {"spot": event_spot},
        }
        emit_event(
            file,
            engine,
            "spiral_continuous" if event_spot.get("continuous") else "spiral_drop",
            overrides,
        )
        syringe_tracker[0] = max(0.0, syringe_tracker[0] - required_mm)
        remaining_mm = max(0.0, remaining_mm - required_mm)
        spots += 1
        total_ul += float(spot.get("dispense_ul", 0.0))
    return {"total_dispense_uL": total_ul, "spots_count": spots, "mode": mode}
