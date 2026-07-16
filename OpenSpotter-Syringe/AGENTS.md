# Contributor and Agent Rules

## Change discipline

1. Keep changes scoped and preserve unrelated working-tree edits.
2. Update the matching documentation whenever behavior, setup, architecture, file layout, or hardware configuration changes.
3. Remove superseded code and docs instead of retaining parallel legacy paths.
4. Do not commit runtime G-code, logs, temporary files, screenshots of obsolete interfaces, or a vendored Klipper source tree.
5. Treat physical motion, dispensing, homing, docking, and calibration changes as safety-sensitive.

## Source contracts

- `Spotter-Control_v3/app/ui_theme.py` is the shared UI palette, typography, and widget-style source.
- `Spotter-Control_v3/app/input_configs.py` defines input fields; it is not the theme owner.
- `Spotter-Control_v3/app/gcode_planner.py` owns numeric lifecycle and state transitions.
- `Spotter-Control_v3/config/config_gcode_workflow.json` owns emitted machine-command templates.
- Generation profiles are versioned JSON only.
- `config/config_visual_objects.json` geometry affects the preview only and never enters G-code directly. Interactive bindings may update their real program inputs, subject to the normal machine-parameter lock.
- `Spotter-Control_v3/hardware/klipper/config/printer.cfg` is the active include graph.
- `hardware/klipper/config/scripts/tcp_calibration.py` is the canonical custom module source; no Klipper checkout belongs in this repository.

## Required checks

From `Spotter-Control_v3`:

```powershell
python -m compileall -q app
python -m unittest discover -s tests -v
```

Also launch `python main.py` after visible UI or interactive workflow changes. Hardware changes require config review and controlled commissioning on the target machine; unit tests do not authorize motion.

## Documentation ownership

- User setup and behavior: `README.md`, `GETTING_STARTED.md`, and `Spotter-Control_v3/README.md`.
- Architecture: `PROJECT_DESCRIPTION.md` and `Spotter-Control_v3/Spotter_Control_Dev.md`.
- Hardware: `Spotter-Control_v3/hardware/klipper/README.md` and the relevant config comments.
- Component/design references: `Docs/README.md` and `CAD/README.md`.
- Machine-oriented invariants and change note: `AGENT_DOC.md`.
