"""Detached direct-run support owned by the grid plugin.

The capture path reads live editor values on the GUI thread. Generation later
uses immutable snapshots and widget-shaped value sources, so worker threads
never touch Tk objects.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Tuple

from ...core.application_patterns import (
    FrozenDict,
    PatternRecipeSnapshot,
    RuntimeBooleanSource,
    RuntimeGenerationContext,
    capture_runtime_fields as _strict_entries_to_dict,
    require_runtime_range as _require_range,
    runtime_entries,
    validate_runtime_container_ids as _validate_container_ids,
    validated_runtime_text as _validated_recipe_text,
)
from .fields import CLEANING_FIELDS, GRID_FIELDS, WASHING_FIELDS
from .manifest import PLUGIN_MANIFEST


MAX_GRID_AXIS_POINTS = 500
MAX_GRID_POINTS_PER_PATTERN = 25_000
MAX_MAINTENANCE_CYCLES = 100
MAX_PATTERN_WORK = 100_000


@dataclass(frozen=True)
class GridJobSnapshot:
    """Immutable values for one grid recipe."""

    number: int
    grid: Mapping[str, Any]
    cleaning: Mapping[str, Any]
    washing: Mapping[str, Any]
    flags: Mapping[str, bool]


def _validate_grid(
    grid: Mapping[str, Any],
    cleaning: Mapping[str, Any],
    washing: Mapping[str, Any],
    flags: Mapping[str, bool],
    context: str,
) -> None:
    _require_range(grid, "rows", minimum=1, label="{} rows".format(context))
    _require_range(grid, "cols", minimum=1, label="{} columns".format(context))
    _require_range(
        grid,
        "rows",
        maximum=MAX_GRID_AXIS_POINTS,
        label="{} rows".format(context),
    )
    _require_range(
        grid,
        "cols",
        maximum=MAX_GRID_AXIS_POINTS,
        label="{} columns".format(context),
    )
    grid_points = int(grid["rows"]) * int(grid["cols"])
    if grid_points > MAX_GRID_POINTS_PER_PATTERN:
        raise ValueError(
            "{} has {:,} spots; the direct-run limit is {:,}".format(
                context,
                grid_points,
                MAX_GRID_POINTS_PER_PATTERN,
            )
        )
    _require_range(
        grid,
        "pitch_x",
        nonzero=True,
        label="{} X pitch".format(context),
    )
    _require_range(
        grid,
        "pitch_y",
        nonzero=True,
        label="{} Y pitch".format(context),
    )
    _require_range(grid, "dispense_vol", minimum=0.000000001)
    _require_range(grid, "row_add_volume", minimum=0)
    _require_range(grid, "droplet_forming_time", minimum=0)
    _validate_container_ids(grid, context)

    cleaning_required = bool(
        flags.get("cleaning_enabled")
        or flags.get("final_rinse_add_cleaning_grid")
    )
    if cleaning_required:
        _require_range(cleaning, "rows_cleaning", minimum=1)
        _require_range(cleaning, "cols_cleaning", minimum=1)
        _require_range(
            cleaning,
            "rows_cleaning",
            maximum=MAX_GRID_AXIS_POINTS,
        )
        _require_range(
            cleaning,
            "cols_cleaning",
            maximum=MAX_GRID_AXIS_POINTS,
        )
        cleaning_points = int(cleaning["rows_cleaning"]) * int(
            cleaning["cols_cleaning"]
        )
        if cleaning_points > MAX_GRID_POINTS_PER_PATTERN:
            raise ValueError(
                "{} cleaning grid has {:,} spots; the direct-run limit is "
                "{:,}".format(
                    context,
                    cleaning_points,
                    MAX_GRID_POINTS_PER_PATTERN,
                )
            )
        _require_range(cleaning, "pitch_x_cleaning", nonzero=True)
        _require_range(cleaning, "pitch_y_cleaning", nonzero=True)
        _require_range(
            cleaning,
            "dispense_vol_cleaning",
            minimum=0.000000001,
        )
        _require_range(
            cleaning,
            "droplet_forming_time_cleaning",
            minimum=0,
        )
    _require_range(cleaning, "spots_before_cleaning", minimum=0)
    _require_range(
        cleaning,
        "final_rinse_cycles",
        minimum=0,
        maximum=MAX_MAINTENANCE_CYCLES,
    )

    if flags.get("washing_enabled"):
        _require_range(washing, "washing_speed", minimum=0.000001)
        _require_range(washing, "washing_line_lenght", minimum=0.000001)
        _require_range(
            washing,
            "washing_cycles",
            minimum=1,
            maximum=MAX_MAINTENANCE_CYCLES,
        )
    _require_range(washing, "washing_after_x_spots", minimum=0)


def _estimate_grid_work(
    global_values: Mapping[str, Any],
    grid: Mapping[str, Any],
    cleaning: Mapping[str, Any],
    washing: Mapping[str, Any],
    flags: Mapping[str, bool],
) -> int:
    """Conservatively bound repeated maintenance before generation."""

    rows = int(grid["rows"])
    cols = int(grid["cols"])
    main_points = rows * cols
    cleaning_points = int(cleaning["rows_cleaning"]) * int(
        cleaning["cols_cleaning"]
    )
    cleaning_interval = int(cleaning["spots_before_cleaning"])
    washing_interval = int(washing["washing_after_x_spots"])

    washing_triggers = (
        int(math.ceil(float(main_points) / washing_interval))
        if flags.get("washing_enabled") and washing_interval > 0
        else 0
    )
    scheduled_cleaning_runs = 0
    if flags.get("cleaning_enabled"):
        if cleaning_interval > 0:
            scheduled_cleaning_runs += int(
                math.ceil(float(main_points) / cleaning_interval)
            )
        scheduled_cleaning_runs += washing_triggers
    if flags.get("final_rinse_add_cleaning_grid"):
        scheduled_cleaning_runs += 1

    base_ul = (
        main_points * float(grid["dispense_vol"])
        + max(0, rows - 1) * float(grid["row_add_volume"])
    )
    cleaning_ul = cleaning_points * float(cleaning["dispense_vol_cleaning"])
    capacity_ul = float(global_values["max_syringe_vol"])
    fixed_ul = base_ul + scheduled_cleaning_runs * cleaning_ul
    refill_count = max(1, int(math.ceil(fixed_ul / capacity_ul)))
    if flags.get("cleaning_enabled") and cleaning_ul > 0:
        effective_capacity = capacity_ul - cleaning_ul
        if effective_capacity <= 0:
            refill_count = main_points + 1
        else:
            refill_count = min(
                main_points + 1,
                max(1, int(math.ceil(fixed_ul / effective_capacity))),
            )

    cleaning_runs = scheduled_cleaning_runs
    if flags.get("cleaning_enabled"):
        cleaning_runs += refill_count

    washing_runs = 0
    if flags.get("washing_enabled"):
        washing_runs = washing_triggers + 1
        if flags.get("wash_after_loading"):
            washing_runs += refill_count
    washing_work = washing_runs * (int(washing["washing_cycles"]) + 2)
    rinse_work = (
        2 * int(cleaning["final_rinse_cycles"])
        if flags.get("final_rinse_enabled")
        else 0
    )
    return (
        main_points
        + cleaning_runs * cleaning_points
        + washing_work
        + rinse_work
    )


def capture_runtime_recipes(
    instances: Mapping[int, Any],
    global_values: Mapping[str, Any],
    _workflow: Mapping[str, Any],
) -> Tuple[PatternRecipeSnapshot[GridJobSnapshot], ...]:
    """Capture and validate every active grid editor."""

    recipes = []
    for number, grid_obj in sorted(instances.items()):
        context = "Grid {}".format(number)
        grid_values = _strict_entries_to_dict(
            grid_obj.grid_entry,
            GRID_FIELDS,
            context,
        )
        grid_values.update(
            {
                "name": _validated_recipe_text(
                    grid_obj.get_grid_name()
                    if hasattr(grid_obj, "get_grid_name")
                    else context,
                    "{} name".format(context),
                ),
                "color": _validated_recipe_text(
                    grid_obj.get_grid_color()
                    if hasattr(grid_obj, "get_grid_color")
                    else "green",
                    "{} color".format(context),
                ),
            }
        )
        cleaning_values = _strict_entries_to_dict(
            grid_obj.cleaning_entry,
            CLEANING_FIELDS,
            "{} cleaning".format(context),
        )
        washing_values = _strict_entries_to_dict(
            grid_obj.washing_entry,
            WASHING_FIELDS,
            "{} washing".format(context),
        )
        flags = {
            "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
            "washing_enabled": bool(grid_obj.washing_enabled.get()),
            "wash_after_loading": bool(
                grid_obj.wash_after_loading_enabled.get()
            ),
            "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
            "final_rinse_add_cleaning_grid": bool(
                grid_obj.final_rinse_add_cleaning_grid.get()
            ),
        }
        _validate_grid(
            grid_values,
            cleaning_values,
            washing_values,
            flags,
            context,
        )
        estimated_work = _estimate_grid_work(
            global_values,
            grid_values,
            cleaning_values,
            washing_values,
            flags,
        )
        if estimated_work > MAX_PATTERN_WORK:
            raise ValueError(
                "{} estimates {:,} pattern and maintenance operations; the "
                "direct-run limit is {:,}".format(
                    context,
                    estimated_work,
                    MAX_PATTERN_WORK,
                )
            )

        payload = GridJobSnapshot(
            number=int(number),
            grid=FrozenDict(grid_values),
            cleaning=FrozenDict(cleaning_values),
            washing=FrozenDict(washing_values),
            flags=FrozenDict(flags),
        )
        recipes.append(
            PatternRecipeSnapshot(
                plugin_id=PLUGIN_MANIFEST.id,
                number=int(number),
                payload=payload,
                estimated_work=estimated_work,
            )
        )

    if not recipes:
        raise ValueError("Add at least one grid before starting a grid job")
    if len(recipes) > int(global_values["max_grid_count"]):
        raise ValueError(
            "Active grid count exceeds the configured Maximum Pattern Count"
        )
    return tuple(recipes)


class _GridAdapter:
    """Legacy generation shape for one detached grid recipe."""

    def __init__(self, snapshot: GridJobSnapshot):
        self.grid_entry = runtime_entries(GRID_FIELDS, snapshot.grid)
        self.cleaning_entry = runtime_entries(
            CLEANING_FIELDS,
            snapshot.cleaning,
        )
        self.washing_entry = runtime_entries(WASHING_FIELDS, snapshot.washing)
        self.cleaning_enabled = RuntimeBooleanSource(
            snapshot.flags.get("cleaning_enabled")
        )
        self.washing_enabled = RuntimeBooleanSource(
            snapshot.flags.get("washing_enabled")
        )
        self.wash_after_loading_enabled = RuntimeBooleanSource(
            snapshot.flags.get("wash_after_loading")
        )
        self.final_rinse_enabled = RuntimeBooleanSource(
            snapshot.flags.get("final_rinse_enabled")
        )
        self.final_rinse_add_cleaning_grid = RuntimeBooleanSource(
            snapshot.flags.get("final_rinse_add_cleaning_grid")
        )
        self._name = str(
            snapshot.grid.get("name", "Grid {}".format(snapshot.number))
        )
        self._color = str(snapshot.grid.get("color", "green"))

    def get_grid_name(self) -> str:
        return self._name

    def get_grid_color(self) -> str:
        return self._color


class GridGenerationAdapter:
    """Detached application shape consumed by the existing grid generator."""

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
                    "Grid runtime received a {!r} recipe".format(
                        recipe.plugin_id
                    )
                )
            if not isinstance(recipe.payload, GridJobSnapshot):
                raise TypeError(
                    "Grid runtime recipe {} has an incompatible payload".format(
                        recipe.number
                    )
                )
            if recipe.number != recipe.payload.number:
                raise ValueError(
                    "Grid runtime recipe number does not match its payload"
                )
            self.grid_tab_dict[recipe.number] = _GridAdapter(recipe.payload)


def build_generation_adapter(
    context: RuntimeGenerationContext,
    recipes: Sequence[PatternRecipeSnapshot[Any]],
) -> GridGenerationAdapter:
    """Return the detached GUI-shaped adapter used for G-code generation."""

    return GridGenerationAdapter(context, recipes)


__all__ = [
    "GridGenerationAdapter",
    "GridJobSnapshot",
    "build_generation_adapter",
    "capture_runtime_recipes",
]
