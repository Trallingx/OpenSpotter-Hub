"""Detached direct-run support owned by the spiral plugin."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ...core.application_patterns import (
    FrozenDict,
    PatternRecipeSnapshot,
    RuntimeGenerationContext,
    capture_runtime_fields as _strict_entries_to_dict,
    require_runtime_range as _require_range,
    runtime_entries,
    validate_runtime_container_ids as _validate_container_ids,
    validated_runtime_text as _validated_recipe_text,
)
from .fields import SPIRAL_FIELDS
from .manifest import PLUGIN_MANIFEST


MAX_SPIRAL_POINTS = 100_000


@dataclass(frozen=True)
class SpiralJobSnapshot:
    """Immutable values for one spiral recipe."""

    number: int
    spiral: Mapping[str, Any]


def _validate_spiral(values: Mapping[str, Any], context: str) -> None:
    _require_range(values, "turns", minimum=0, maximum=1000)
    _require_range(values, "num_starts", minimum=1, maximum=64)
    _require_range(values, "spacing_mm", minimum=0.000001)
    _require_range(values, "dispense_vol", minimum=0.000000001)
    _require_range(values, "droplet_forming_time", minimum=0)
    if str(values["spiral_mode"]) not in {"drop", "continuous"}:
        raise ValueError(
            "{} spiral mode must be 'drop' or 'continuous'".format(context)
        )
    _validate_container_ids(values, context)


def _workflow_custom_number(
    workflow: Mapping[str, Any],
    name: str,
) -> float:
    for item in workflow.get("custom_variables", []):
        if isinstance(item, Mapping) and str(item.get("name", "")) == name:
            value = float(item.get("value"))
            if math.isfinite(value):
                return value
    raise ValueError(
        "Workflow custom variable {!r} is missing or invalid".format(name)
    )


def capture_runtime_recipes(
    instances: Mapping[int, Any],
    global_values: Mapping[str, Any],
    workflow: Mapping[str, Any],
) -> Tuple[PatternRecipeSnapshot[SpiralJobSnapshot], ...]:
    """Capture and validate every active spiral editor."""

    resolution = _workflow_custom_number(
        workflow,
        "spiral_resolution_radians",
    )
    if resolution <= 0:
        raise ValueError("Spiral resolution must be positive")

    recipes = []
    for number, spiral_obj in sorted(instances.items()):
        context = "Spiral {}".format(number)
        spiral_values = _strict_entries_to_dict(
            spiral_obj.spiral_entry,
            SPIRAL_FIELDS,
            context,
        )
        spiral_values.update(
            {
                "name": _validated_recipe_text(
                    spiral_obj.get_grid_name()
                    if hasattr(spiral_obj, "get_grid_name")
                    else context,
                    "{} name".format(context),
                ),
                "color": _validated_recipe_text(
                    spiral_obj.get_grid_color()
                    if hasattr(spiral_obj, "get_grid_color")
                    else "orange",
                    "{} color".format(context),
                ),
            }
        )
        _validate_spiral(spiral_values, context)
        estimated_points = (
            int(
                math.floor(
                    (2.0 * math.pi * float(spiral_values["turns"]))
                    / resolution
                )
            )
            + 1
        ) * int(spiral_values["num_starts"])
        if estimated_points > MAX_SPIRAL_POINTS:
            raise ValueError(
                "{} estimates {:,} points; the direct-run limit is {:,}".format(
                    context,
                    estimated_points,
                    MAX_SPIRAL_POINTS,
                )
            )

        payload = SpiralJobSnapshot(
            number=int(number),
            spiral=FrozenDict(spiral_values),
        )
        recipes.append(
            PatternRecipeSnapshot(
                plugin_id=PLUGIN_MANIFEST.id,
                number=int(number),
                payload=payload,
                estimated_work=estimated_points,
            )
        )

    if not recipes:
        raise ValueError(
            "Add at least one spiral before starting a spiral job"
        )
    if len(recipes) > int(global_values["max_grid_count"]):
        raise ValueError(
            "Active spiral count exceeds the configured Maximum Pattern Count"
        )
    return tuple(recipes)


class _SpiralAdapter:
    """Legacy generation shape for one detached spiral recipe."""

    def __init__(self, snapshot: SpiralJobSnapshot):
        self.spiral_entry = runtime_entries(SPIRAL_FIELDS, snapshot.spiral)
        self._name = str(
            snapshot.spiral.get(
                "name",
                "Spiral {}".format(snapshot.number),
            )
        )
        self._color = str(snapshot.spiral.get("color", "orange"))

    def get_grid_name(self) -> str:
        return self._name

    def get_grid_color(self) -> str:
        return self._color


class SpiralGenerationAdapter:
    """Detached application shape consumed by the existing spiral generator."""

    def __init__(
        self,
        context: RuntimeGenerationContext,
        recipes: Sequence[PatternRecipeSnapshot[Any]],
    ):
        from ...input_configs import GLOBAL_FIELDS

        self.config_dir = context.config_dir
        self.workflow_data = json.loads(context.workflow_json)
        self.entry = runtime_entries(GLOBAL_FIELDS, context.global_values)
        self.grid_tab_dict = {}
        self.spiral_tab_dict = {}

        for recipe in recipes:
            if recipe.plugin_id != PLUGIN_MANIFEST.id:
                raise ValueError(
                    "Spiral runtime received a {!r} recipe".format(
                        recipe.plugin_id
                    )
                )
            if not isinstance(recipe.payload, SpiralJobSnapshot):
                raise TypeError(
                    "Spiral runtime recipe {} has an incompatible payload".format(
                        recipe.number
                    )
                )
            if recipe.number != recipe.payload.number:
                raise ValueError(
                    "Spiral runtime recipe number does not match its payload"
                )
            self.spiral_tab_dict[recipe.number] = _SpiralAdapter(
                recipe.payload
            )


def build_generation_adapter(
    context: RuntimeGenerationContext,
    recipes: Sequence[PatternRecipeSnapshot[Any]],
) -> SpiralGenerationAdapter:
    """Return the detached GUI-shaped adapter used for G-code generation."""

    return SpiralGenerationAdapter(context, recipes)


__all__ = [
    "SpiralGenerationAdapter",
    "SpiralJobSnapshot",
    "build_generation_adapter",
    "capture_runtime_recipes",
]
