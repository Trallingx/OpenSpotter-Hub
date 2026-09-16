"""Grid job orchestration backed by the editable runtime workflow."""

from __future__ import annotations

from ...core.configuration import entries_to_dict
from ...core.gcode.lifecycle import (
    empty_syringe,
    finish_program,
    load_syringe,
    start_program,
)
from ...core.gcode.profiles import write_generation_settings_file
from ...gcode_shared import (
    atomic_text_output,
    build_workflow_engine,
    collect_common_generation_data,
    prompt_save_base_path,
)
from ...runtime_logging import get_logger, log_options
from .fields import CLEANING_FIELDS, GRID_FIELDS, WASHING_FIELDS
from .manifest import PLUGIN_MANIFEST
from .planner import calculate_grid_refill_ul, clean_grid, generate_grid_events


logger = get_logger("generation.grid")


def _grid_snapshot(grid_number, grid_values, cleaning_values, washing_values, flags):
    return {
        "grid_number": grid_number,
        "grid_name": grid_values["name"],
        "grid_color": grid_values["color"],
        "grid": dict(grid_values),
        "cleaning": dict(cleaning_values),
        "washing": dict(washing_values),
        **dict(flags),
    }


def _collect_grid_job(grid_number, grid_obj):
    grid_values = entries_to_dict(grid_obj.grid_entry, GRID_FIELDS)
    grid_values.update({
        "name": grid_obj.get_grid_name() if hasattr(grid_obj, "get_grid_name") else f"Grid {grid_number}",
        "color": grid_obj.get_grid_color() if hasattr(grid_obj, "get_grid_color") else "green",
    })
    cleaning_values = entries_to_dict(grid_obj.cleaning_entry, CLEANING_FIELDS)
    washing_values = entries_to_dict(grid_obj.washing_entry, WASHING_FIELDS)
    flags = {
        "cleaning_enabled": bool(grid_obj.cleaning_enabled.get()),
        "washing_enabled": bool(grid_obj.washing_enabled.get()),
        "wash_after_loading": bool(grid_obj.wash_after_loading_enabled.get()),
        "final_rinse_enabled": bool(grid_obj.final_rinse_enabled.get()),
        "final_rinse_add_cleaning_grid": bool(grid_obj.final_rinse_add_cleaning_grid.get()),
    }
    return grid_number, grid_values, cleaning_values, washing_values, flags


def save_grid_gcode(self, filepath=None):
    """Generate all active grid recipes and their versioned settings sidecar."""

    if not getattr(self, "grid_tab_dict", {}):
        return None
    if filepath is None:
        filepath = prompt_save_base_path("drop_array_grid.gcode")
    if not filepath:
        return None

    common = collect_common_generation_data(self)
    engine = build_workflow_engine(common)
    grid_jobs = [
        _collect_grid_job(grid_number, grid_obj)
        for grid_number, grid_obj in sorted(self.grid_tab_dict.items())
    ]
    log_options(
        logger,
        "grid_generation.started",
        output_path=filepath,
        grid_count=len(grid_jobs),
        global_options=common["entry_dict"],
        grid_jobs=[
            _grid_snapshot(
                grid_number,
                grid_values,
                cleaning_values,
                washing_values,
                flags,
            )
            for grid_number, grid_values, cleaning_values, washing_values, flags in grid_jobs
        ],
    )
    first_grid = grid_jobs[0]
    engine.update_context({
        "grid": dict(first_grid[1]),
        "cleaning": dict(first_grid[2]),
        "washing": dict(first_grid[3]),
        "runtime": {"job": {"kind": "grid", "pattern_index": first_grid[0]}},
    })
    grid_settings = []
    settings_snapshot = {
        "schema_version": 3,
        "global_settings": dict(common["entry_dict"]),
        "runtime_values": {
            "x_offset": common["x_offset"],
            "y_offset": common["y_offset"],
            "acceptance_square": dict(common["acceptance_square"]),
            "mesh_points": common["mesh_points"],
        },
        "workflow": engine.workflow,
        "grid_settings": grid_settings,
        "spiral_settings": [],
        "patterns": [
            {
                "plugin_id": PLUGIN_MANIFEST.id,
                "plugin_version": PLUGIN_MANIFEST.version,
                "recipes": grid_settings,
            }
        ],
    }

    with atomic_text_output(filepath) as file:
        start_program(file, engine)
        syringe_tracker = [0.0]

        for grid_number, grid_values, cleaning_values, washing_values, flags in grid_jobs:
            # Cadence belongs to one grid recipe.  A preceding grid with
            # washing disabled must not shift this grid's first wash.
            washing_spot_counter = [0]
            engine.update_context({
                "grid": dict(grid_values),
                "cleaning": dict(cleaning_values),
                "washing": dict(washing_values),
                "runtime": {"job": {"kind": "grid", "pattern_index": grid_number}},
            })
            settings_snapshot["grid_settings"].append(
                _grid_snapshot(
                    grid_number,
                    grid_values,
                    cleaning_values,
                    washing_values,
                    flags,
                )
            )

            loading_container_id = int(grid_values.get("loading_from", 1))
            emptying_container_id = int(grid_values.get("leftovers_into", 1))
            if loading_container_id not in common["containers"]:
                raise ValueError("Loading container must be an integer between 1 and 6")
            if emptying_container_id not in common["containers"]:
                raise ValueError("Leftovers container must be an integer between 1 and 6")

            refill_ul = calculate_grid_refill_ul(
                common,
                grid_values,
                cleaning_values,
                flags,
            )
            log_options(
                logger,
                "grid_generation.recipe_options",
                grid_number=grid_number,
                loading_container_id=loading_container_id,
                leftovers_container_id=emptying_container_id,
                calculated_refill_ul=refill_ul,
                flags=flags,
                grid=grid_values,
                cleaning=cleaning_values,
                washing=washing_values,
            )
            cleaning_cycle_counter = [0]

            generate_grid_events(
                file=file,
                engine=engine,
                common=common,
                grid_values=grid_values,
                cleaning_values=cleaning_values,
                washing_values=washing_values,
                flags=flags,
                containers=common["containers"],
                refill_ul=refill_ul,
                washing_spot_counter=washing_spot_counter,
                syringe_tracker=syringe_tracker,
                cleaning_cycle_counter=cleaning_cycle_counter,
            )

            empty_syringe(
                file=file,
                engine=engine,
                common=common,
                container=common["containers"][emptying_container_id],
                container_id=emptying_container_id,
                final_rinse_enabled=flags["final_rinse_enabled"],
                rinsing_cycles=int(cleaning_values.get("final_rinse_cycles", 1)),
                syringe_tracker=syringe_tracker,
            )

            if flags["final_rinse_enabled"] and flags["final_rinse_add_cleaning_grid"]:
                final_cleaning_ul = (
                    int(cleaning_values.get("rows_cleaning", 0))
                    * int(cleaning_values.get("cols_cleaning", 0))
                    * float(cleaning_values.get("dispense_vol_cleaning", 0.0))
                )
                if final_cleaning_ul > common["max_syringe_vol"] + 1e-9:
                    raise ValueError(
                        "The final rinse cleaning grid exceeds the configured syringe capacity"
                    )
                if final_cleaning_ul > 0:
                    load_syringe(
                        file=file,
                        engine=engine,
                        common=common,
                        container=common["containers"][emptying_container_id],
                        total_fill_ul=final_cleaning_ul,
                        syringe_tracker=syringe_tracker,
                        refill_details={
                            "reason": "final_rinse_cleaning",
                            "dynamic": False,
                            "container_id": emptying_container_id,
                        },
                    )
                clean_grid(
                    file=file,
                    engine=engine,
                    common=common,
                    grid_values=grid_values,
                    cleaning_values=cleaning_values,
                    anchor_x=common["x_offset"],
                    anchor_y=common["y_offset"],
                    syringe_tracker=syringe_tracker,
                    cleaning_cycle_counter=cleaning_cycle_counter,
                )

        finish_program(file, engine)

    settings_path = write_generation_settings_file(filepath, settings_snapshot)
    log_options(
        logger,
        "grid_generation.completed",
        output_path=filepath,
        settings_path=settings_path,
        grid_count=len(grid_jobs),
    )
    return filepath
