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
- [Spotter-Control_v3/Spotter_Control_Dev.md](Spotter-Control_v3/Spotter_Control_Dev.md)
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

- 2026-07-09: Reworked Klipper TCP calibration for bent/thin needles: fixed X acquisition, local X centering, upward X beam-following with a small sweep after every `Z_STEP`, half-step refinement after the first missed sweep, then matching Y beam-following. XY is solved from the tracked X/Y beam coordinates and final `tcp_tip_z` uses the X-beam tip edge because the laser planes may differ. Removed the old drop/final vertical scan path (`PRE_Y_Z_DROP`, `Z_SCAN_TRAVEL`, `Z_PASSES`, `Z_BEAM`); config exposes `xy_travel: 3`, `z_step: 2`, `z_tolerance: 0.01`, and `z_travel: 20`. `TCPSTART` checks saved BLTouch parked state before movement, and current optical input pins are `PH0`/`PK0`.
- 2026-07-10: Changed TCP cross centering to common-plane diagonal geometry. X tip tracking now sweeps normal to X; at `tip_z - 2 mm`, X is re-centered and Y is centered while following the physical X beam. The solved intersection is accepted only after stationary sequential X/Y queries both report `PRESSED`.
- 2026-06-23: Added standalone Klipper `tcp_calibration.cfg` for active-low NPN optical TCP cross calibration on Einsy inputs, including optical beam sampling, Z edge averaging, and saved TCP offset variables.
- 2026-06-18: Reorganized `Spotter-Control_v3` into app, config, assets, hardware, output, and logs folders. Added central path handling, package-relative imports, launcher, public docs, and compile-check guidance.
- 2026-06-18: Added `Spotter-Control_v3/Spotter_Control_Dev.md` as a developer guide for common edit locations, runtime paths, G-code generation, and validation commands.
