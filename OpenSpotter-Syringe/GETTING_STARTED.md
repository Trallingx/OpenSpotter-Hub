# Getting Started

This guide covers the desktop application and the minimum safe path to inspect the included Klipper configuration. Run commands from `OpenSpotter-Syringe/Spotter-Control_v3`.

## Install and run

Create a virtual environment and install the Pillow and aiohttp dependencies:

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

The app is a local Tkinter program with optional direct Moonraker control. It still opens and generates saved G-code when no printer is available.

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
- the Visual Objects list is front-to-back, so a higher row appears above a lower row and Move Up/Move Down changes that stack;
- each legacy container circle follows its matching `global.containerN_x/y` values, and reverse editing is blocked until global machine parameters are unlocked;
- **IMPORT IMAGE…** starts in the asset folder, accepts other filesystem paths, and scales the selected image to its entered millimetre width/height;
- **EDIT G-CODE WORKFLOW** validates, previews, and saves workflow changes.
- **MACHINE PARAMETERS** opens the persistent maximized global editor immediately left of **HELP**;
- the right-side Machine Control panel exposes connection state, Start/Pause/Resume/Stop, Emergency Stop, XYZ jog, live Z, and the exact virtual-SD read/queued cursor;
- **CONFIG** opens masked local Moonraker settings and **RETRY** restarts monitoring.

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

An embedded workflow is executable machine-command data. The application asks separately before replacing the active workflow, and direct Start shows both the workflow hash and exact artifact hash before upload.

The save dialog starts in `output/gcodes`, which is an ignored runtime directory. Copy outputs to an experiment record or another durable location when they must be retained.

## Connect and run through Moonraker

1. Deploy the current `hardware.cfg`, `movement_safety.cfg`, and `remote_control.cfg` together, retain the matching application `config/config_gcode_workflow.json`, and restart Klipper.
2. Select **CONFIG** in Machine Control and enter the Moonraker host/IP, port, protocol, optional route prefix, and API key. The created `Spotter-Control_v3/config/config_moonraker.json` is local and ignored by Git.
3. In `moonraker.conf`, trust only the exact control PC or isolated machine subnet and firewall TCP port 7125; do not expose motion endpoints to an entire shared private network.
4. Confirm the panel reports connected and Klippy ready.
5. Confirm Klipper advertises `OPENSPOTTER_CONTRACT_V3`, `OPENSPOTTER_JOB_HOME`, and `OPENSPOTTER_JOB_REHOME_Z`. If the contract is missing or stale, Start/Home/jog controls remain disabled.
6. Physically load and verify the detachable BLTouch before a workflow that uses `MESH`.
7. Confirm saved TCP calibration is ready at coordinate version 2.
8. Keep Global Machine Parameters locked, select Grid or Spiral mode, and choose **START CURRENT RECIPE**.
9. Review the captured mode/count, workflow hash, full artifact SHA-256, byte/line count, remote path, and motion warning. Start only if they describe the intended experiment.

Direct Start captures an immutable snapshot, generates it off the Tk thread, checks resource limits and live machine bounds, uploads without auto-start/queueing, repeats the ready/idle check, and then sends one persistent-WebSocket Start request. Identical content uses the same hash-based remote filename. The newest 20 local runtime artifacts per mode are retained.

The G-code tab maps Moonraker’s virtual-SD file cursor to the exact local artifact. This is a read/queued position and may be ahead of physical execution. If a response is lost after a command was sent, the outcome is treated as unknown and normal controls interlock until monitoring reconnects; Emergency Stop remains available.

If `.local` connection setup is slow on a Pi Zero, enter its fixed IPv4 address in **CONFIG**. XYZ jog requires homed XYZ, no active virtual-SD job, needle offsets and bed mesh off, and at least 30 mm/min. Safe Home requires sensorless `homing_retract_dist: 0` and performs reviewed 2-second settle/release cycles plus a physical Z clearance of at least 35 mm and all enabled dead-zone clearances.

The **MANUAL / CONSOLE** editor is for small tests, not arbitrary Klipper administration. It accepts diagnostic queries and bounded `G90`/`G91` plus `G0`/`G1` XYZ/F motion with explicit mode/feed, live bounds, the same homing/offset/mesh/virtual-SD guards, and a 60-second estimated cap. Unknown or safety-bypassing commands are blocked. `M112` uses Moonraker's HTTP Emergency Stop; partial execution errors, timeouts, disconnects, or E-stop keep controls latched until the printer is inspected and monitoring reconnects.

Preflight is not a complete interpreter for arbitrary custom macros. After any workflow/profile/firmware or fixture change, inspect the exact artifact and perform an elevated, fluid-free dry run.

## Before hardware motion

Read the [Klipper hardware guide](Spotter-Control_v3/hardware/klipper/README.md) in full. In particular:

1. Confirm the machine is actually wired as the Einsy RAMBo 1.1a configuration describes.
2. Install the custom `tcp_calibration.py` extra before enabling `tcp_calibration.cfg`.
3. Verify all pins, axis directions, limits, sensorless homing, syringe travel, and emergency-stop behavior with tools clear of the work area.
4. Physically inspect the detachable BLTouch, then initialize its saved state with `SET_BLTOUCH_DOCK_STATE STATE=parked` or `STATE=loaded`. This command records state and does not move the probe.
5. Commission the TCP optics and obtain `tcp_ready=True` before enabling needle-tip offsets.
6. Run a small, elevated, fluid-free job and compare the preview, generated G-code, and physical motion.

The default workflow homes and meshes, but it does not run TCP calibration or automatically load/park the detachable BLTouch. Saved-state preflight reduces mistakes but does not verify physical attachment. Tool-state preparation and controlled hardware commissioning remain explicit operator steps.
