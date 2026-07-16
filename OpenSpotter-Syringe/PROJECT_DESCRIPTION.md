# Project Description

## Purpose

OpenSpotter-Syringe is a research platform for repeatable syringe-based deposition. Its desktop application turns experiment recipes into Klipper-compatible G-code while keeping machine-command templates editable and the numeric process lifecycle in tested Python code.

## System boundaries

The repository contains:

- a local Tkinter control and planning application;
- a persistent Moonraker WebSocket/HTTP runtime for monitored virtual-SD execution and guarded manual control;
- grid, cleaning, washing, rinse, and spiral planners;
- an event-driven, runtime-editable G-code workflow;
- JSON defaults, UI state, visual-layout objects, and generation profiles;
- Klipper configuration for an Einsy RAMBo 1.1a syringe platform;
- a custom optical-cross TCP calibration extra;
- CAD generations, manufacturing exports, BOM, schematics, and component references.

It does not contain a JetValve implementation, computer vision, or automatic lid control.

## Architecture

The desktop stack has five layers:

1. `app/gui_v3.py`, `grid.py`, and `spiral_grid.py` collect experiment inputs.
2. `app/gcode_planner.py` owns numeric lifecycle and syringe state; `app/plugins/spiral.py` supplies spiral geometry.
3. `app/gcode_workflow.py` validates and renders event templates stored in `config/config_gcode_workflow.json`.
4. `app/grid_gcode.py`, `spiral_gcode.py`, and `gcode_generation.py` create atomic outputs and schema-version 2 JSON profiles.
5. `app/runtime_job.py`, `machine_controller.py`, `machine_control_panel.py`, and `app/machine/` capture bounded immutable jobs, generate exact artifacts, validate live machine readiness/bounds, and coordinate Moonraker without blocking Tk.

`app/canvas_drawer.py` previews the same recipe inputs around TCP X0/Y0. Unlinked values in `config/config_visual_objects.json` are display annotations only. Optional geometry links resolve from real program inputs; the visual geometry never constrains motion or enters planning directly, while a guarded reverse edit intentionally changes the linked program input.

The firmware side is modular Klipper configuration under `Spotter-Control_v3/hardware/klipper/config`. The custom `tcp_calibration.py` module must be installed into the printer's active Klipper source tree.

Direct execution uses content-addressed virtual-SD files. It uploads without Moonraker auto-start queueing, repeats ready/idle preflight, and starts through one persistent JSON-RPC connection. Subscribed state drives Pause/Resume/Cancel, guarded XYZ motion, live needle Z, prompts, positions, and the virtual-SD read/queued cursor. HTTP Emergency Stop remains independent of the WebSocket command queue.

## Current maturity

Implemented and covered by repository tests:

- workflow validation/rendering and safe expressions;
- numeric planning edge cases;
- grid/spiral generation integration;
- compiled workflow output equivalence and cache reuse;
- Moonraker reconnect/no-replay behavior, command timing, unknown outcomes, upload/start preflight, emergency HTTP, and Tk event bridging;
- controller snapshot-to-upload/start ordering, live bounds/tool readiness, filename matching, and interlocks;
- visual-object validation and persistence;
- static hardware-configuration invariants.

Still requiring physical validation:

- wiring, homing sensitivity, travel limits, docking geometry, and syringe calibration;
- optical TCP repeatability and offset sign conventions on each build;
- bed mesh, live Z trim, dead-zone definitions, and complete hardware-in-the-loop jobs;
- material compatibility and experiment-specific safety.

This repository is a research implementation, not a production-grade laboratory automation system.
