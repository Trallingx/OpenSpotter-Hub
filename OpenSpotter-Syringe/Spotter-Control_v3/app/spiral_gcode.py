"""Spiral job orchestration backed by the editable runtime workflow."""

from __future__ import annotations

from .SpotterFunctions import entries_to_dict, write_generation_settings_file
from .gcode_planner import (
    empty_syringe,
    finish_program,
    generate_spiral_events,
    start_program,
)
from .gcode_shared import (
    atomic_text_output,
    build_workflow_engine,
    collect_common_generation_data,
    prompt_save_base_path,
)
from .input_configs import SPIRAL_FIELDS
from .plugins import discover_plugins, get_plugin
from .runtime_logging import get_logger, log_options


logger = get_logger("generation.spiral")


def _collect_spiral_job(spiral_number, spiral_obj):
    spiral_values = entries_to_dict(spiral_obj.spiral_entry, SPIRAL_FIELDS)
    spiral_values.update({
        "name": spiral_obj.get_grid_name() if hasattr(spiral_obj, "get_grid_name") else f"Spiral {spiral_number}",
        "color": spiral_obj.get_grid_color() if hasattr(spiral_obj, "get_grid_color") else "orange",
    })
    return spiral_number, spiral_values


def save_spiral_gcode(self, filepath=None):
    if not getattr(self, "spiral_tab_dict", {}):
        return None
    if filepath is None:
        filepath = prompt_save_base_path("drop_array_spiral.gcode")
    if not filepath:
        return None

    common = collect_common_generation_data(self)
    engine = build_workflow_engine(common)
    spiral_jobs = [
        _collect_spiral_job(spiral_number, spiral_obj)
        for spiral_number, spiral_obj in sorted(self.spiral_tab_dict.items())
    ]
    log_options(
        logger,
        "spiral_generation.started",
        output_path=filepath,
        spiral_count=len(spiral_jobs),
        global_options=common["entry_dict"],
        spiral_jobs=[
            {
                "spiral_number": spiral_number,
                "spiral": spiral_values,
            }
            for spiral_number, spiral_values in spiral_jobs
        ],
    )
    engine.update_context({
        "spiral": dict(spiral_jobs[0][1]),
        "runtime": {
            "job": {"kind": "spiral", "pattern_index": spiral_jobs[0][0]}
        },
    })
    settings_snapshot = {
        "schema_version": 2,
        "global_settings": dict(common["entry_dict"]),
        "runtime_values": {
            "x_offset": common["x_offset"],
            "y_offset": common["y_offset"],
            "acceptance_square": dict(common["acceptance_square"]),
            "mesh_points": common["mesh_points"],
        },
        "workflow": engine.workflow,
        "grid_settings": [],
        "spiral_settings": [],
    }

    plugin = get_plugin("spiral")
    if plugin is None:
        discover_plugins()
        plugin = get_plugin("spiral")
    if plugin is None or not hasattr(plugin, "plan"):
        raise ValueError("Spiral planning plugin is not available")

    with atomic_text_output(filepath) as file:
        start_program(file, engine)
        syringe_tracker = [0.0]
        for spiral_number, spiral_values in spiral_jobs:
            engine.update_context({
                "spiral": dict(spiral_values),
                "runtime": {
                    "job": {"kind": "spiral", "pattern_index": spiral_number}
                },
            })
            settings_snapshot["spiral_settings"].append({
                "spiral_number": spiral_number,
                "spiral_name": spiral_values["name"],
                "spiral_color": spiral_values["color"],
                "spiral": dict(spiral_values),
            })

            loading_container_id = int(spiral_values.get("loading_from", 1))
            emptying_container_id = int(spiral_values.get("leftovers_into", 1))
            if loading_container_id not in common["containers"]:
                raise ValueError("Loading container must be an integer between 1 and 6")
            if emptying_container_id not in common["containers"]:
                raise ValueError("Leftovers container must be an integer between 1 and 6")

            points = plugin.plan({
                "params": spiral_values,
                "resolution_radians": float(engine.custom_value("spiral_resolution_radians")),
                "millimeters_per_microliter": float(engine.custom_value("syringe_mm_per_ul")),
            })
            log_options(
                logger,
                "spiral_generation.recipe_options",
                spiral_number=spiral_number,
                loading_container_id=loading_container_id,
                leftovers_container_id=emptying_container_id,
                point_count=len(points),
                plugin=getattr(plugin, "name", type(plugin).__name__),
                spiral=spiral_values,
            )
            generate_spiral_events(
                file=file,
                engine=engine,
                common=common,
                spiral_values=spiral_values,
                points=points,
                loading_container=common["containers"][loading_container_id],
                loading_container_id=loading_container_id,
                syringe_tracker=syringe_tracker,
            )

            empty_syringe(
                file=file,
                engine=engine,
                common=common,
                container=common["containers"][emptying_container_id],
                container_id=emptying_container_id,
                final_rinse_enabled=False,
                rinsing_cycles=0,
                syringe_tracker=syringe_tracker,
            )

        finish_program(file, engine)

    settings_path = write_generation_settings_file(filepath, settings_snapshot)
    log_options(
        logger,
        "spiral_generation.completed",
        output_path=filepath,
        settings_path=settings_path,
        spiral_count=len(spiral_jobs),
    )
    return filepath
