# Spotter-Control_v3 Developer Guide

This guide maps the current implementation and its contracts. User behavior is documented in [README.md](README.md); firmware commissioning is documented in [hardware/klipper/README.md](hardware/klipper/README.md).

## Bootstrap and UI

- `main.py` calls `app.main_v3.main()`.
- `app/main_v3.py` creates runtime directories, loads global defaults, restores pattern counts, and starts Tk.
- `app/gui_v3.py` owns the main window, workspace mode, tabs, controls, defaults, profile loading, and action error handling.
- `app/grid.py` and `app/spiral_grid.py` build recipe panels.
- `app/input_configs.py` defines `GLOBAL_FIELDS`, `GRID_FIELDS`, `CLEANING_FIELDS`, `WASHING_FIELDS`, and `SPIRAL_FIELDS`.
- `app/paths.py` is the only central definition of config, asset, output, and log paths.
- `app/runtime_logging.py` configures the rotating runtime log, redacts credential-like values, and serializes effective option snapshots.

The application log is `logs/openspotter-control.log`, rotated at 5 MB with five backups. Important state changes and complete effective generation options are logged at `INFO`; per-trigger workflow rendering decisions are logged at `DEBUG`. `OPENSPOTTER_LOG_LEVEL` controls the level without changing source.

The visual system belongs to `app/ui_theme.py`. Add or change shared palette tokens, fonts, ttk styles, buttons, and entry options there. Use semantic tokens in feature modules; do not introduce another local palette.

Useful UI search targets in `gui_v3.py`:

- `create_buttons`
- `_switch_workspace_mode`
- `instance_grid` and `instance_spiral`
- `check_saves`
- `_parse_generation_json_file` and `load_generation_config`
- `open_gcode_editor`
- `adding_pictures`

## Preview and visual objects

- `app/canvas_drawer.py` snapshots GUI values, plans preview geometry, draws TCP axes and patterns, and handles polling, zoom, pan, fit, and acceptance warnings.
- `app/visual_objects.py` validates schema-version 2 rectangles/circles/images and their optional geometry bindings, migrates surviving schema-version 1 legacy containers, resolves portable image paths, owns the fresh-install default layout, and persists objects atomically.
- `app/visual_object_editor.py` owns interactive annotation editing plus guarded reverse writes to linked program inputs.
- `config/config_visual_objects.json` is deliberately separate from generation profiles.

Coordinate invariants:

- TCP crossing is preview X0/Y0.
- Preview and machine coordinates use positive X right and positive Y down.
- Static layout geometry, including the build plate, acceptance area, containers, and CAPTRON placeholder, is stored in the editable object list rather than a second hardcoded overlay path.
- The default CAPTRON image spans -30..30 mm on both axes and uses the project-relative `assets/Captron-TCP.png` source.
- Rectangles and images anchor at top-left and extend in positive X/Y; circles anchor at centre.
- Image width/height are converted directly from millimetres to canvas pixels, so independent values intentionally stretch the source to the requested box.
- The image cache is keyed by object ID, resolved path, file metadata, and rendered size. Keep the cached `PhotoImage` alive and invalidate it when the file or target size changes.
- Project-contained images persist relative to the project directory; external image selections persist as absolute paths.
- Both rectangle and circle fills are opaque; do not reintroduce Tk stipple masks for editable surfaces.
- Optional `bindings` map `x`, `y`, `width`, or `height` to a stable numeric program path. Global paths use `global.<field>`; per-pattern paths use an explicit index such as `grid.1.<field>` or `spiral.1.<field>`.
- Binding resolution happens in the canvas snapshot before fitting and drawing. The program value is authoritative; a missing, invalid, or non-positive size source leaves the stored literal as a fallback and records a warning.
- Reverse writes go through `DropletGui._set_visual_binding_variable` and must honor the source widget's current lock/read-only state. Do not use `_set_entry_value` to bypass the global machine-parameter lock for interactive binding edits.
- Persisted object order remains painter order from back to front. The editor deliberately presents `reversed(objects)`, so its first row is the top visual layer; Move Up swaps the stored object with the next index and Move Down swaps it with the previous index.
- Unlinked visual geometry remains annotation-only. Linked geometry also never enters planner calculations directly; only an intentional reverse write to the real program field can affect generation.
- Coordinate axes, the TCP marker, and generated grid/spiral/cleaning/washing previews remain renderer primitives and are not editor objects.

## Generation flow

```text
GUI fields
  -> gcode_generation.save_file
  -> grid_gcode / spiral_gcode
  -> gcode_planner numeric events
  -> gcode_workflow template rendering
  -> atomic G-code + schema-version 2 JSON sidecar
```

Key ownership:

- `app/gcode_generation.py`: GUI-facing save orchestration and per-type suffixes.
- `app/gcode_shared.py`: common values, acceptance square, output paths, atomic text output, workflow-engine construction.
- `app/gcode_planner.py`: lifecycle ordering, refill calculations, syringe state, and numeric event payloads.
- `app/grid_gcode.py`: grid job collection and orchestration.
- `app/spiral_gcode.py`: spiral job collection and orchestration.
- `app/plugins/spiral.py`: numeric spiral points only.
- `app/SpotterFunctions.py`: field conversion, containers, and atomic JSON profile sidecars.

Saving a base path with both recipe types creates separate `_grid.gcode` and `_spiral.gcode` files. Each sidecar contains only the recipes for its job type plus global/runtime values and the effective workflow.

The loader accepts JSON only. It requires `global_settings`, `grid_settings`, and `spiral_settings`, rebuilds tabs, and writes an embedded validated workflow to the active workflow file. Preserve that side effect or introduce an explicit migration if the contract changes.

## Workflow architecture

- `app/gcode_workflow.py`: schema, safe expression evaluator, template rendering, scope validation, custom-variable dependency resolution, atomic persistence, and runtime engine.
- `app/gcode_editor.py`: block/section editing, variable catalog, condition/expression tools, validation, preview, and save.
- `config/config_gcode_workflow.json`: only application-owned source of emitted machine-command templates.

Workflow blocks do not form a second planner. `gcode_planner.py` emits named events in lifecycle order; matching enabled sections render in block order and then section order. Add physical state transitions to the planner, add or extend a named event, and keep machine command text in the workflow.

Variable metadata distinguishes event availability from job kind. Event-scoped values may only be used where supplied. Mode-specific values on shared events need a `runtime.job.kind` condition. The editor uses representative GUI values for preview; generation supplies planned runtime values.

The application planner supports grid and spiral jobs only; no separate calibration-generation event or runtime namespace is exposed.

`custom.syringe_mm_per_ul` and `custom.spiral_resolution_radians` are required positive planner inputs. Other default custom variables currently include priming speed and X-homing clearance.

## Configuration and defaults

- `config/config_global.json`: global defaults.
- `config/config_grid_*.json`: indexed grid defaults.
- `config/config_spiral_1.json`: spiral defaults.
- `config/config_states.json`: restored tab counts.
- `config/config_gcode_workflow.json`: workflow schema version 1.
- `config/config_visual_objects.json`: visual-object and binding schema version 2.

Keep field keys aligned between `input_configs.py`, JSON defaults, profile parsing, planner context, and workflow variable metadata.

## Hardware files

`hardware/klipper/config/printer.cfg` includes:

- `hardware.cfg`
- `tmc2130.cfg`
- `syringe.cfg`
- `bltouch.cfg`
- `movement_safety.cfg`
- `bed_mesh.cfg`
- `display.cfg`
- `mainsail.cfg`
- `tcp_calibration.cfg`

The custom Klipper source of truth is `hardware/klipper/config/scripts/tcp_calibration.py`. It is deployed into the printer's `klippy/extras` directory; no Klipper source checkout is maintained here. `moonraker.conf` is a separate service config and is not included by `printer.cfg`.

When changing generated motion, review axis/syringe limits, the G0/G1 wrappers, raw G0.1/G1.1 uses, mesh assumptions, detachable-probe state, TCP readiness, and the effective workflow together.

## Tests

From this directory:

```powershell
python -m compileall -q app
python -c "import app.main_v3; import app.gui_v3; import app.gcode_shared; import app.plugins; print('imports ok')"
python -m unittest discover -s tests -v
```

Run `python main.py` for visible or interactive changes. Hardware config tests are static checks, not hardware-in-the-loop validation.

## Repository hygiene

Keep one generation architecture, JSON-only profiles, current static images, and the project-owned Klipper configuration/custom extra. Do not add parallel retired implementations, generated output, UI captures used only as stale documentation, or a firmware source checkout.
