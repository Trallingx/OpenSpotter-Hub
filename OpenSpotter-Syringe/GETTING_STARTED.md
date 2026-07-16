# Getting Started

This guide covers the desktop application and the minimum safe path to inspect the included Klipper configuration. Run commands from `OpenSpotter-Syringe/Spotter-Control_v3`.

## Install and run

Create a virtual environment and install the Pillow dependency:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

On macOS or Linux, activation is:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

The app is a local Tkinter program; it does not connect to Klipper directly.

## Validate the checkout

```powershell
python -m compileall -q app
python -m unittest discover -s tests -v
```

For a visual smoke test, confirm that:

- the window uses the graphite/grey theme;
- global defaults load locked from `config/config_global.json`;
- saved grid and spiral counts restore from `config/config_states.json`;
- the canvas shows the editable 60 × 60 mm CAPTRON image centred at TCP X0/Y0;
- scroll zoom, drag pan, and **FIT VIEW** work;
- **VISUAL OBJECTS** edits persisted rectangles, circles, and imported images; unlinked geometry remains display-only;
- each legacy container circle follows its matching `global.containerN_x/y` values, and reverse editing is blocked until global machine parameters are unlocked;
- **IMPORT IMAGE…** starts in the asset folder, accepts other filesystem paths, and scales the selected image to its entered millimetre width/height;
- **EDIT G-CODE WORKFLOW** validates, previews, and saves workflow changes.

## Generate and reload a job

1. Select Grid or Spiral mode and add at least one recipe.
2. Review global settings, recipe coordinates, volumes, containers, maintenance options, and the workflow.
3. Select **GENERATE G-CODE** and choose a base path.
4. Inspect every generated command before sending it to a machine.

If both grid and spiral recipes exist, choosing `experiment.gcode` produces:

```text
experiment_grid.gcode
experiment_grid_settings.json
experiment_spiral.gcode
experiment_spiral_settings.json
```

Each schema-version 2 settings profile records the global values, pattern recipes, derived runtime values, and effective workflow. **LOAD PROFILE** accepts JSON only. Loading replaces the current grid and spiral tabs; if the profile contains `workflow`, the validated embedded workflow is also saved over `config/config_gcode_workflow.json`.

The save dialog starts in `output/gcodes`, which is an ignored runtime directory. Copy outputs to an experiment record or another durable location when they must be retained.

## Before hardware motion

Read the [Klipper hardware guide](Spotter-Control_v3/hardware/klipper/README.md) in full. In particular:

1. Confirm the machine is actually wired as the Einsy RAMBo 1.1a configuration describes.
2. Install the custom `tcp_calibration.py` extra before enabling `tcp_calibration.cfg`.
3. Verify all pins, axis directions, limits, sensorless homing, syringe travel, and emergency-stop behavior with tools clear of the work area.
4. Physically inspect the detachable BLTouch, then initialize its saved state with `SET_BLTOUCH_DOCK_STATE STATE=parked` or `STATE=loaded`. This command records state and does not move the probe.
5. Commission the TCP optics and obtain `tcp_ready=True` before enabling needle-tip offsets.
6. Run a small, elevated, fluid-free job and compare the preview, generated G-code, and physical motion.

The default workflow homes and meshes, but it does not run TCP calibration or automatically load/park the detachable BLTouch. Tool-state preparation remains an explicit operator step.
