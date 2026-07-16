# Project Description

## Purpose

OpenSpotter-Syringe is a research platform for repeatable syringe-based deposition. Its desktop application turns experiment recipes into Klipper-compatible G-code while keeping machine-command templates editable and the numeric process lifecycle in tested Python code.

## System boundaries

The repository contains:

- a local Tkinter control and planning application;
- grid, cleaning, washing, rinse, and spiral planners;
- an event-driven, runtime-editable G-code workflow;
- JSON defaults, UI state, visual-layout objects, and generation profiles;
- Klipper configuration for an Einsy RAMBo 1.1a syringe platform;
- a custom optical-cross TCP calibration extra;
- CAD generations, manufacturing exports, BOM, schematics, and component references.

It does not contain a machine communication client, a JetValve implementation, computer vision, or automatic lid control.

## Architecture

The desktop stack has four layers:

1. `app/gui_v3.py`, `grid.py`, and `spiral_grid.py` collect experiment inputs.
2. `app/gcode_planner.py` owns numeric lifecycle and syringe state; `app/plugins/spiral.py` supplies spiral geometry.
3. `app/gcode_workflow.py` validates and renders event templates stored in `config/config_gcode_workflow.json`.
4. `app/grid_gcode.py`, `spiral_gcode.py`, and `gcode_generation.py` create atomic outputs and schema-version 2 JSON profiles.

`app/canvas_drawer.py` previews the same recipe inputs around TCP X0/Y0. Unlinked values in `config/config_visual_objects.json` are display annotations only. Optional geometry links resolve from real program inputs; the visual geometry never constrains motion or enters planning directly, while a guarded reverse edit intentionally changes the linked program input.

The firmware side is modular Klipper configuration under `Spotter-Control_v3/hardware/klipper/config`. The custom `tcp_calibration.py` module must be installed into the printer's active Klipper source tree.

## Current maturity

Implemented and covered by repository tests:

- workflow validation/rendering and safe expressions;
- numeric planning edge cases;
- grid/spiral generation integration;
- visual-object validation and persistence;
- static hardware-configuration invariants.

Still requiring physical validation:

- wiring, homing sensitivity, travel limits, docking geometry, and syringe calibration;
- optical TCP repeatability and offset sign conventions on each build;
- bed mesh, live Z trim, dead-zone definitions, and complete hardware-in-the-loop jobs;
- material compatibility and experiment-specific safety.

This repository is a research implementation, not a production-grade laboratory automation system.
