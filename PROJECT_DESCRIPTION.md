# Project Description

## Purpose

OpenSpotter-Syringe is an open source syringe-based liquid handling and spotting platform.
It provides a desktop GUI for configuring droplet grids and spiral patterns, previewing the build plate, and generating Klipper-compatible G-code for automated dispensing.

## Scope

- GUI-first setup for syringe spotting experiments.
- Grid, cleaning, washing, final rinse, and spiral pattern configuration.
- Config-driven defaults for repeatable experiments.
- G-code generation for Klipper-controlled hardware.
- Public repository layout for code, hardware configuration, CAD, and documentation.

## Architecture

- `Spotter-Control_v3/app`: application code.
- `Spotter-Control_v3/app/gui_v3.py`: top-level Tkinter UI and workflow actions.
- `Spotter-Control_v3/app/input_configs.py`: shared field definitions for GUI and config JSON.
- `Spotter-Control_v3/app/canvas_drawer.py`: visual preview of anchors, containers, grids, cleaning paths, washing lines, and spirals.
- `Spotter-Control_v3/app/grid_gcode.py` and `Spotter-Control_v3/app/spiral_gcode.py`: pattern-specific G-code generation.
- `Spotter-Control_v3/app/spotter_gcode.py`: low-level syringe and motion G-code helpers.
- `Spotter-Control_v3/app/plugins`: extension point for pattern generators.
- `Spotter-Control_v3/config`: persistent defaults and UI state.
- `Spotter-Control_v3/hardware`: Klipper and syringe configuration examples.

## Current Status

Implemented:
- Main Tkinter GUI.
- Grid and spiral configuration tabs.
- Build plate preview canvas.
- JSON default loading and saving.
- Grid, cleaning, washing, final rinse, and spiral G-code generation.
- Organized runtime folders for config, assets, output, hardware files, and logs.

In progress / partial:
- Formal automated tests.
- Hardware setup documentation beyond included Klipper config files.
- Clear separation between historical example G-code and generated user output.

## Non-Goals Current Version

- Cloud orchestration or remote fleet control.
- Production-grade laboratory automation validation.
- Automatic vision-based calibration.

## Success Criteria

- `python main.py` launches the control app from `Spotter-Control_v3`.
- Defaults load from `config`.
- Images load from `assets/images`.
- Generated files are saved under a clear output location.
- Hardware configuration and CAD assets are easy to find from the repository root.
