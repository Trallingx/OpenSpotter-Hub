"""Top-level orchestration for generating pattern output files."""

from .gcode_shared import derive_output_path, prompt_save_base_path
from .plugin_runtime import application_plugins
from .runtime_logging import get_logger, log_options


logger = get_logger("generation")


def save_file(gui):
    """Generate one artifact for every registered plugin with active recipes."""

    base_filepath = prompt_save_base_path("drop_array.gcode")
    if not base_filepath:
        logger.info("generation.cancelled | reason=no_output_path")
        return None

    active_plugins = []
    pattern_counts = {}
    for plugin in application_plugins():
        instances = plugin.instance_map(gui)
        pattern_counts[plugin.manifest.id] = len(instances)
        if instances:
            active_plugins.append(plugin)
    log_options(
        logger,
        "generation.requested",
        base_path=base_filepath,
        pattern_counts=pattern_counts,
    )
    generated_paths = []
    for plugin in active_plugins:
        plugin_id = plugin.manifest.id
        generated = plugin.generate(
            gui,
            derive_output_path(base_filepath, plugin_id),
        )
        if generated:
            generated_paths.append(generated)
    if not generated_paths:
        logger.warning("generation.skipped | reason=no_patterns")
        return None
    log_options(logger, "generation.completed", output_paths=generated_paths)
    return generated_paths
