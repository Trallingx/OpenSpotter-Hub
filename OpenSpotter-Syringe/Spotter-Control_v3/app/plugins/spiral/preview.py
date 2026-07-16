"""Renderer-neutral live preview construction for spiral recipes."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from ...core.canvas import CanvasPreview, CanvasPreviewContext, PolylinePrimitive
from ...core.geometry import acceptance_square
from ...gcode_workflow import WorkflowEngine, build_runtime_context_defaults


def build_spiral_canvas_preview(
    planner: Any,
    recipes: Sequence[Mapping[str, Any]],
    context: CanvasPreviewContext,
) -> CanvasPreview:
    """Plan all active spiral recipes into immutable canvas primitives."""

    base_context = build_runtime_context_defaults()
    base_context["global"].update(dict(context.global_values))
    base_context["acceptance"].update(
        acceptance_square(context.global_values)
    )
    engine = WorkflowEngine(
        context.workflow_source,
        base_context=base_context,
    )

    polylines = []
    warnings = []
    for fallback_index, recipe in enumerate(recipes, start=1):
        index = fallback_index
        try:
            index = int(recipe.get("pattern_number", fallback_index))
            values = dict(recipe.get("spiral", {}))
            color = str(
                recipe.get(
                    "spiral_color",
                    values.get("color", "orange"),
                )
            )
            engine.update_context(
                {
                    "spiral": values,
                    "runtime": {
                        "job": {
                            "kind": "spiral",
                            "pattern_index": index,
                        }
                    },
                }
            )
            planned = planner.plan(
                {
                    "params": values,
                    "resolution_radians": float(
                        engine.custom_value(
                            "spiral_resolution_radians"
                        )
                    ),
                    "millimeters_per_microliter": float(
                        engine.custom_value("syringe_mm_per_ul")
                    ),
                }
            )
            paths = defaultdict(list)
            for point in planned:
                paths[int(point["start_index"])].append(
                    (float(point["x"]), float(point["y"]))
                )
            drop_mode = (
                str(values.get("spiral_mode", "drop")).strip().lower()
                == "drop"
            )
            dispense_ul = float(values.get("dispense_vol", 0.003))
            for start_index in sorted(paths):
                polylines.append(
                    PolylinePrimitive(
                        points=tuple(paths[start_index]),
                        color=color,
                        width=2,
                        show_markers=drop_mode,
                        marker_volume_ul=(
                            dispense_ul if drop_mode else None
                        ),
                        marker_minimum_pixels=2,
                        z_index=20,
                    )
                )
        except Exception as exc:
            warnings.append(
                "Spiral {} preview is unavailable: {}".format(index, exc)
            )

    return CanvasPreview(
        polylines=tuple(polylines),
        warnings=tuple(warnings),
    )


__all__ = ["build_spiral_canvas_preview"]
