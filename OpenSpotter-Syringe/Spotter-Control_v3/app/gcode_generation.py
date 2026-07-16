"""Top-level orchestration for generating pattern output files."""

from .gcode_shared import derive_output_path, prompt_save_base_path
from .grid_gcode import save_grid_gcode
from .runtime_logging import get_logger, log_options
from .spiral_gcode import save_spiral_gcode


logger = get_logger("generation")


def save_file(gui):
    base_filepath = prompt_save_base_path("drop_array.gcode")
    if not base_filepath:
        logger.info("generation.cancelled | reason=no_output_path")
        return None

    grid_count = len(getattr(gui, "grid_tab_dict", {}))
    spiral_count = len(getattr(gui, "spiral_tab_dict", {}))
    log_options(
        logger,
        "generation.requested",
        base_path=base_filepath,
        grid_count=grid_count,
        spiral_count=spiral_count,
    )
    generated_paths = []
    if grid_count:
        generated = save_grid_gcode(gui, derive_output_path(base_filepath, "grid"))
        if generated:
            generated_paths.append(generated)
    if spiral_count:
        generated = save_spiral_gcode(gui, derive_output_path(base_filepath, "spiral"))
        if generated:
            generated_paths.append(generated)
    if not generated_paths:
        logger.warning("generation.skipped | reason=no_patterns")
        return None
    log_options(logger, "generation.completed", output_paths=generated_paths)
    return generated_paths
