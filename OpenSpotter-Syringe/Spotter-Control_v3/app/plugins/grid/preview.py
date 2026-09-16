"""Renderer-neutral live preview construction for grid recipes."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...core.canvas import (
    CanvasPreview,
    CanvasPreviewContext,
    LinePrimitive,
    MarkerPrimitive,
)
from ...core.domain import build_containers
from ...core.geometry import acceptance_square
from ...gcode_workflow import WorkflowEngine, build_runtime_context_defaults
from .planner import calculate_grid_refill_ul, generate_grid_events


class _PreviewSink:
    """File-shaped no-op used while replaying numeric maintenance planning."""

    @staticmethod
    def write(_text):
        return None


class _PreviewEventRecorder:
    """Workflow adapter that records cleaning cycles without rendering text."""

    def __init__(self, workflow_engine):
        self.workflow_engine = workflow_engine
        self.cleaning_cycles = []

    def custom_value(self, name):
        return self.workflow_engine.custom_value(name)

    def emit(self, trigger, overrides):
        if trigger == "cleaning_start":
            self.cleaning_cycles.append(
                int(overrides["cleaning"]["cycle"])
            )
        return ""


def _recipe_flags(recipe: Mapping[str, Any]) -> dict:
    return {
        key: bool(recipe.get(key, False))
        for key in (
            "cleaning_enabled",
            "washing_enabled",
            "wash_after_loading",
            "final_rinse_enabled",
            "final_rinse_add_cleaning_grid",
        )
    }


def _cleaning_cycles(
    engine: WorkflowEngine,
    common: Mapping[str, Any],
    grid_values: Mapping[str, Any],
    cleaning_values: Mapping[str, Any],
    washing_values: Mapping[str, Any],
    flags: Mapping[str, bool],
) -> tuple:
    """Return the same cleaning-cycle indices used by real generation."""

    recorder = _PreviewEventRecorder(engine)
    cleaning_cycle_counter = [0]
    generate_grid_events(
        file=_PreviewSink(),
        engine=recorder,
        common=common,
        grid_values=grid_values,
        cleaning_values=cleaning_values,
        washing_values=washing_values,
        flags=flags,
        containers=build_containers(common["entry_dict"]),
        refill_ul=calculate_grid_refill_ul(
            common,
            grid_values,
            cleaning_values,
            flags,
        ),
        washing_spot_counter=[0],
        syringe_tracker=[0.0],
        cleaning_cycle_counter=cleaning_cycle_counter,
    )
    cycles = list(recorder.cleaning_cycles)
    if (
        flags.get("final_rinse_enabled")
        and flags.get("final_rinse_add_cleaning_grid")
    ):
        cycles.append(cleaning_cycle_counter[0])
    return tuple(cycles)


def build_grid_canvas_preview(
    planner: Any,
    recipes: Sequence[Mapping[str, Any]],
    context: CanvasPreviewContext,
) -> CanvasPreview:
    """Plan all active grid recipes into immutable canvas primitives."""

    global_values = dict(context.global_values)
    base_context = build_runtime_context_defaults()
    base_context["global"].update(global_values)
    base_context["acceptance"].update(acceptance_square(global_values))
    engine = WorkflowEngine(
        context.workflow_source,
        base_context=base_context,
    )
    x_offset = float(global_values.get("x_cord_of_y_line", 0.0)) + float(
        global_values.get("tuning_offset_x", 0.0)
    )
    y_offset = float(global_values.get("y_cord_of_x_line", 0.0)) + float(
        global_values.get("tuning_offset_y", 0.0)
    )
    common = {
        "entry_dict": global_values,
        "x_offset": x_offset,
        "y_offset": y_offset,
        "priming_vol": float(global_values.get("priming_vol", 0.0)),
        "drop_extra_aspirate": float(
            global_values.get("drop_extra_aspirate", 0.0)
        ),
        "max_syringe_vol": float(
            global_values.get("max_syringe_vol", 0.0)
        ),
    }

    markers = []
    lines = []
    warnings = []
    for fallback_index, recipe in enumerate(recipes, start=1):
        index = fallback_index
        try:
            index = int(recipe.get("pattern_number", fallback_index))
            grid_values = dict(recipe.get("grid", {}))
            cleaning_values = dict(recipe.get("cleaning", {}))
            washing_values = dict(recipe.get("washing", {}))
            flags = _recipe_flags(recipe)
            grid_color = str(
                recipe.get(
                    "grid_color",
                    grid_values.get("color", "green"),
                )
            )
            engine.update_context(
                {
                    "grid": grid_values,
                    "cleaning": cleaning_values,
                    "washing": washing_values,
                    "runtime": {
                        "job": {
                            "kind": "grid",
                            "pattern_index": index,
                        }
                    },
                }
            )

            planned = planner.plan(
                {
                    "params": grid_values,
                    "x_offset": x_offset,
                    "y_offset": y_offset,
                }
            )
            dispense_ul = float(grid_values.get("dispense_vol", 0.0))
            markers.extend(
                MarkerPrimitive(
                    x=float(point["x"]),
                    y=float(point["y"]),
                    color=grid_color,
                    volume_ul=dispense_ul,
                    z_index=10,
                )
                for point in planned
            )

            if (
                flags.get("cleaning_enabled")
                or (
                    flags.get("final_rinse_enabled")
                    and flags.get("final_rinse_add_cleaning_grid")
                )
            ):
                rows = max(
                    0,
                    int(float(cleaning_values.get("rows_cleaning", 0))),
                )
                cols = max(
                    0,
                    int(float(cleaning_values.get("cols_cleaning", 0))),
                )
                pitch_x = float(
                    cleaning_values.get("pitch_x_cleaning", 0.0)
                )
                pitch_y = float(
                    cleaning_values.get("pitch_y_cleaning", 0.0)
                )
                base_x = x_offset + float(
                    cleaning_values.get(
                        "grid_offset_x_cleaning",
                        0.0,
                    )
                )
                base_y = y_offset + float(
                    cleaning_values.get(
                        "grid_offset_y_cleaning",
                        0.0,
                    )
                )
                relative_x = float(
                    cleaning_values.get("x_relative_increase", 0.0)
                )
                relative_y = float(
                    cleaning_values.get("y_relative_increase", 0.0)
                )
                for cycle in _cleaning_cycles(
                    engine,
                    common,
                    grid_values,
                    cleaning_values,
                    washing_values,
                    flags,
                ):
                    primary = cycle == 0
                    color = (
                        context.style.maintenance_primary
                        if primary
                        else context.style.maintenance_secondary
                    )
                    outline = (
                        context.style.maintenance_primary_outline
                        if primary
                        else context.style.maintenance_secondary_outline
                    )
                    start_x = base_x + cycle * relative_x
                    start_y = base_y + cycle * relative_y
                    for row in range(rows):
                        for column in range(cols):
                            markers.append(
                                MarkerPrimitive(
                                    x=start_x + column * pitch_x,
                                    y=start_y + row * pitch_y,
                                    color=color,
                                    shape="square",
                                    size_mm=0.16,
                                    outline=outline,
                                    minimum_pixels=2,
                                    z_index=30,
                                )
                            )

            if flags.get("washing_enabled"):
                start_x = float(
                    washing_values.get("washing_x_pos", 0.0)
                )
                y = float(washing_values.get("washing_y_pos", 0.0))
                lines.append(
                    LinePrimitive(
                        start=(start_x, y),
                        end=(
                            start_x
                            + float(
                                washing_values.get(
                                    "washing_line_lenght",
                                    0.0,
                                )
                            ),
                            y,
                        ),
                        color=context.style.washing_line,
                        width=3,
                        dash=(8, 3),
                        z_index=40,
                        safety_relevant=False,
                    )
                )
        except Exception as exc:
            warnings.append(
                "Grid {} preview is unavailable: {}".format(index, exc)
            )

    return CanvasPreview(
        markers=tuple(markers),
        lines=tuple(lines),
        warnings=tuple(warnings),
    )


__all__ = ["build_grid_canvas_preview"]
