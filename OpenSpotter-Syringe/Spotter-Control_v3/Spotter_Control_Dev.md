# Spotter-Control_v3 Developer Guide

This guide is an extra map for the next developer. It does not replace `README.md`, the repository root docs, or the files in `config/` and `hardware/`.

## Quick Orientation

- The active app is a Python/Tkinter desktop GUI.
- `main.py` is the simple launcher. It imports `app.main_v3.main()`.
- `app/main_v3.py` bootstraps runtime folders, loads global defaults, restores grid/spiral state, and starts the Tkinter main loop.
- `app/gui_v3.py` is the main window: workspace mode, global inputs, grid/spiral tab management, build plate controls, load/save actions, and validation popups.
- `app/input_configs.py` is the shared field schema for global, grid, cleaning, washing, and spiral settings.
- `app/canvas_drawer.py` renders the preview canvas for anchors, containers, grids, cleaning points, washing lines, and spirals.
- `app/grid.py` and `app/spiral_grid.py` build the per-pattern configuration panels.
- `app/create_gcode.py` is the GUI-facing wrapper for G-code creation.
- `app/grid_gcode.py`, `app/spiral_gcode.py`, `app/gcode_shared.py`, and `app/spotter_gcode.py` contain G-code generation logic.
- `app/plugins/` contains pattern generator plugins. The current plugin is `spiral`.
- `config/` stores JSON defaults and UI state.
- `assets/images/` stores images loaded by the GUI.
- `output/gcodes/` stores generated or example G-code.
- `hardware/` stores Klipper and syringe configuration files.
- `logs/` is the runtime log folder.

## Where To Edit Common Things

Global machine settings:

- Field definitions, labels, defaults, and tabs: `GLOBAL_FIELDS` in `app/input_configs.py`.
- Loading global defaults at startup: `main()` in `app/main_v3.py`.
- Global save behavior: `check_saves()` in `app/gui_v3.py`.
- Global lock/unlock behavior: `_toggle_global_lock()` and `_update_global_fields_state()` in `app/gui_v3.py`.
- Persistent values: `config/config_global.json`.

Grid configuration:

- Grid field definitions: `GRID_FIELDS` in `app/input_configs.py`.
- Cleaning field definitions: `CLEANING_FIELDS` in `app/input_configs.py`.
- Washing field definitions: `WASHING_FIELDS` in `app/input_configs.py`.
- Grid panel UI: `Grid.create_grid()` in `app/grid.py`.
- Shared label/input construction: `create_labels()` in `app/grid.py`.
- Adding/removing grid tabs: `instance_grid()` and related tab methods in `app/gui_v3.py`.
- Grid defaults: `config/config_grid_*.json`.

Spiral configuration:

- Spiral field definitions: `SPIRAL_FIELDS` in `app/input_configs.py`.
- Spiral panel UI: `SpiralGrid.create_spiral()` in `app/spiral_grid.py`.
- Spiral tab creation/removal: `instance_spiral()` and related tab methods in `app/gui_v3.py`.
- Spiral G-code output: `save_spiral_gcode()` in `app/spiral_gcode.py`.
- Spiral path math: `app/plugins/spiral.py`.
- Spiral defaults: `config/config_spiral_1.json`.

Canvas preview:

- Polling and refresh loop: `CanvasDrawer.start()`, `_poll()`, and `refresh()` in `app/canvas_drawer.py`.
- Reading GUI values for preview: `_collect_data()` in `app/canvas_drawer.py`.
- Build plate, anchors, containers, grids, cleaning preview, washing line, and spiral drawing: `draw()` in `app/canvas_drawer.py`.
- Zoom and pan behavior: `_on_mousewheel()`, `_apply_zoom()`, `_on_pan_start()`, and `_on_pan_move()` in `app/canvas_drawer.py`.
- Acceptance warning popup: `_show_exceed_popup()` in `app/canvas_drawer.py`.

G-code generation:

- Save button entrypoint: `DropletGui.save_file()` in `app/gui_v3.py`.
- GUI-facing wrapper: `save_file()` in `app/create_gcode.py`.
- Output path dialog and suffix handling: `prompt_save_base_path()` and `derive_output_path()` in `app/gcode_shared.py`.
- Common global/runtime values: `collect_common_generation_data()` in `app/gcode_shared.py`.
- Anchor calibration G-code: `generate_anchor_calibration()` in `app/grid_gcode.py`.
- Grid G-code: `save_grid_gcode()` in `app/grid_gcode.py`.
- Spiral G-code: `save_spiral_gcode()` in `app/spiral_gcode.py`.
- Low-level motion, syringe, cleaning, washing, and presentation helpers: `app/spotter_gcode.py`.
- Settings snapshots next to generated G-code: `write_generation_settings_file()` in `app/SpotterFunctions.py`.

Runtime paths and folders:

- Central folder definitions: `app/paths.py`.
- Runtime folder creation: `ensure_runtime_dirs()` in `app/paths.py`.
- Config path passed into the GUI: `main()` in `app/main_v3.py`.
- Image loading paths: `adding_pictures()` in `app/gui_v3.py`.
- Output dialog starting folder: `prompt_save_base_path()` in `app/gcode_shared.py`.

Hardware and machine configuration:

- Klipper config examples: `hardware/klipper/config/`.
- Syringe config: `hardware/syring.cfg`.
- Before changing generated motion, check the matching Klipper limits and physical travel assumptions.

## File Sections To Search First

`app/gui_v3.py` is the largest file. Good first search targets:

- `create_buttons`: main control buttons.
- `instance_grid`: add grid tab.
- `instance_spiral`: add spiral tab.
- `_switch_workspace_mode`: grid/spiral UI switching.
- `check_saves`: save current defaults.
- `load_generation_config`: load a generated settings snapshot.
- `check_inputs`: acceptance-area validation.
- `adding_pictures`: build plate and spot images.

`app/spotter_gcode.py` is the low-level generation file. Good first search targets:

- `start_gcode`: initial homing/probing sequence.
- `generate_grid`: main spot generation loop.
- `loading_syringe`: aspirate/refill sequence.
- `emptying_syringe`: empty/rinse sequence.
- `auto_cleaning_grid`: cleaning grid generation.
- `auto_washing`: washing motion.
- `present_build_plate`: final presentation motion.

## Tests To Run

Run the compile smoke check after changing Python code:

```powershell
python -m compileall -q app
```

Run an import smoke check after changing imports, packaging, paths, or dependencies:

```powershell
python -c "import app.main_v3; import app.gui_v3; import app.gcode_shared; import app.plugins; print('imports ok')"
```

Run the app after visible UI, config, path, image, or G-code workflow changes:

```powershell
python main.py
```

There is no formal automated test suite yet. Add focused tests before large generation-logic changes.

## Cleanup Notes From 2026-06-18

- The old flat `Spotter-Control_v3` layout was reorganized into `app/`, `config/`, `assets/`, `hardware/`, `output/`, and `logs/`.
- Python imports were converted to package-relative imports under `app/`.
- `app/paths.py` now owns runtime folder locations.
- `main.py` was added as the stable launcher from the `Spotter-Control_v3` root.
- `requirements.txt` was added with `Pillow` as the GUI image dependency.
