"""Top-level orchestration for generating pattern output files."""

from .gcode_shared import derive_output_path, prompt_save_base_path
from .grid_gcode import save_grid_gcode
from .spiral_gcode import save_spiral_gcode


def save_file(gui):
    base_filepath = prompt_save_base_path("drop_array.gcode")
    if not base_filepath:
        return None

    generated_paths = []
    if getattr(gui, "grid_tab_dict", {}):
        generated = save_grid_gcode(gui, derive_output_path(base_filepath, "grid"))
        if generated:
            generated_paths.append(generated)
    if getattr(gui, "spiral_tab_dict", {}):
        generated = save_spiral_gcode(gui, derive_output_path(base_filepath, "spiral"))
        if generated:
            generated_paths.append(generated)
    if not generated_paths:
        print("No grids or spirals to save")
        return None
    return generated_paths
