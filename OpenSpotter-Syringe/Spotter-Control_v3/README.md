# Spotter-Control_v3

Python control application for OpenSpotter-Syringe.

## Overview

The control app provides:
- a Tkinter GUI for global machine settings, grid patterns, cleaning/washing routines, and spiral patterns
- a canvas preview of anchors, containers, build plate bounds, grids, cleaning points, washing paths, and spirals
- G-code generation for Klipper-controlled syringe dispensing
- JSON defaults for repeatable experiment setup

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Alternative module command:

```bash
python -m app.main_v3
```

## Validate

```bash
python -m compileall -q app
```

## Layout

- [main.py](main.py): launcher.
- [Spotter_Control_Dev.md](Spotter_Control_Dev.md): developer map for common code changes.
- [app](app): Python source code.
- [config](config): JSON defaults and UI state.
- [assets/images](assets/images): images loaded by the GUI.
- [assets/screenshots](assets/screenshots): reference screenshots.
- [hardware](hardware): Klipper and syringe config files.
- [output/gcodes](output/gcodes): generated or example G-code.
- [logs](logs): runtime log folder.

## Notes

Run commands from this directory so relative package imports and file dialogs behave as expected.
