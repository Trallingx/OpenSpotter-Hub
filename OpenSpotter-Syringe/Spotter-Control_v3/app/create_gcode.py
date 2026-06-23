"""
Thin wrapper layer for G-code generation that delegates to modular generators.

This file maintains backward compatibility with the GUI while decomposing 
grid, spiral, and shared logic into separate modules:
- grid_gcode.py: Grid-specific G-code generation
- spiral_gcode.py: Spiral-specific G-code generation (via plugins)
- gcode_shared.py: Shared utilities and data collection

Functions exposed to GUI:
- generate_anchor_calibration(self): Generate calibration G-code
- save_file(self): Generate and save grid+spiral G-code in separate files
"""


def generate_anchor_calibration(self):
    from .grid_gcode import generate_anchor_calibration as _generate_anchor_calibration
    return _generate_anchor_calibration(self)


def save_file(self):
    from .gcode_shared import derive_output_path, prompt_save_base_path
    from .grid_gcode import save_grid_gcode
    from .spiral_gcode import save_spiral_gcode

    base_filepath = prompt_save_base_path("drop_array.gcode")
    if not base_filepath:
        return

    generated_paths = []
    if getattr(self, 'grid_tab_dict', {}):
        grid_path = derive_output_path(base_filepath, 'grid')
        generated = save_grid_gcode(self, grid_path)
        if generated:
            generated_paths.append(generated)

    if getattr(self, 'spiral_tab_dict', {}):
        spiral_path = derive_output_path(base_filepath, 'spiral')
        generated = save_spiral_gcode(self, spiral_path)
        if generated:
            generated_paths.append(generated)

    if not generated_paths:
        print('No grids or spirals to save')
        return

    return generated_paths
