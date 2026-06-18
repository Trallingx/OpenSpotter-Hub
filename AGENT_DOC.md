# AGENT_DOC

Machine-oriented project tracking context for AI assistants.

## Repo Identity

- Name: OpenSpotter-Syringe
- Stack: Python, Tkinter, Pillow, Klipper G-code/configuration
- Domain: syringe-based open source liquid handling and spotting

## Source Of Truth

- [Spotter-Control_v3/main.py](Spotter-Control_v3/main.py)
- [Spotter-Control_v3/app/main_v3.py](Spotter-Control_v3/app/main_v3.py)
- [Spotter-Control_v3/app/gui_v3.py](Spotter-Control_v3/app/gui_v3.py)
- [Spotter-Control_v3/app/input_configs.py](Spotter-Control_v3/app/input_configs.py)
- [Spotter-Control_v3/app/paths.py](Spotter-Control_v3/app/paths.py)
- [Spotter-Control_v3/config](Spotter-Control_v3/config)

## Runtime Commands

- Install deps: `cd Spotter-Control_v3 && pip install -r requirements.txt`
- Run app: `cd Spotter-Control_v3 && python main.py`
- Compile check: `cd Spotter-Control_v3 && python -m compileall -q app`

## Active Architecture Map

- UI composition and workflow actions: `Spotter-Control_v3/app/gui_v3.py`
- App bootstrap: `Spotter-Control_v3/app/main_v3.py`
- Runtime paths: `Spotter-Control_v3/app/paths.py`
- Field schema and theme: `Spotter-Control_v3/app/input_configs.py`
- Canvas preview: `Spotter-Control_v3/app/canvas_drawer.py`
- Grid UI: `Spotter-Control_v3/app/grid.py`
- Spiral UI: `Spotter-Control_v3/app/spiral_grid.py`
- G-code orchestration: `Spotter-Control_v3/app/create_gcode.py`
- Shared generation data: `Spotter-Control_v3/app/gcode_shared.py`
- Grid G-code generation: `Spotter-Control_v3/app/grid_gcode.py`
- Spiral G-code generation: `Spotter-Control_v3/app/spiral_gcode.py`
- Low-level syringe and motion G-code helpers: `Spotter-Control_v3/app/spotter_gcode.py`
- Pattern plugins: `Spotter-Control_v3/app/plugins`

## Folder Contract

- Source code: `Spotter-Control_v3/app`
- JSON defaults and UI state: `Spotter-Control_v3/config`
- Images and screenshots: `Spotter-Control_v3/assets`
- Klipper and syringe hardware files: `Spotter-Control_v3/hardware`
- Generated/example G-code: `Spotter-Control_v3/output/gcodes`
- Runtime logs: `Spotter-Control_v3/logs`
- CAD assets: `CAD`

## Known Partial Areas

- No formal automated test suite yet.
- Historical generated G-code settings may contain old absolute paths.
- Hardware setup docs are still minimal compared with the included Klipper configs.

## Documentation Policy

When making changes:
1. Update the relevant human docs in the same commit.
2. Add a short note under Change Log below.
3. Remove obsolete docs instead of leaving duplicates.

## Change Log

- 2026-06-18: Reorganized `Spotter-Control_v3` into app, config, assets, hardware, output, and logs folders. Added central path handling, package-relative imports, launcher, public docs, and compile-check guidance.
