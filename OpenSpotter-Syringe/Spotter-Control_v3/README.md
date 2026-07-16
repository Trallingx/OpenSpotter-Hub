# Spotter-Control_v3

Spotter-Control_v3 is the local desktop recipe editor, G-code generator, and Moonraker machine console for OpenSpotter-Syringe. It uses Tkinter, Pillow, and a persistent aiohttp WebSocket/HTTP client. Saved-file generation remains available without a printer connection.

## Run

From this directory on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

On macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

The equivalent package entry point is `python -m app.main_v3`.

## Validate

```powershell
python -m compileall -q app
python -m unittest discover -s tests -v
```

Launch the GUI after changes to appearance, interaction, paths, images, or workflow editing.

## Runtime logs

Each application run writes to `logs/openspotter-control.log`. The file records startup state, effective global and recipe options, workflow/profile changes, generation choices, output paths, fallback defaults, and failures. Logs rotate at 5 MB with five backups, and credential-like values are redacted.

The default level is `INFO`. Set `OPENSPOTTER_LOG_LEVEL=DEBUG` before launching to include detailed workflow-trigger decisions:

```powershell
$env:OPENSPOTTER_LOG_LEVEL = "DEBUG"
python main.py
```

## Interface

The interface uses a low-saturation graphite scientific palette, restrained steel-blue accents, semantic status colors, Segoe UI text, and Consolas for machine-oriented text. All shared colors, fonts, classic Tk options, and ttk styles live in `app/ui_theme.py`.

The main workspace provides:

- global machine parameters in a persistent maximized editor opened beside **HELP**;
- multiple grid recipes with optional cleaning, washing, and final-rinse behavior;
- multiple spiral recipes;
- a TCP-relative geometry preview;
- JSON profile loading;
- a runtime G-code workflow editor;
- atomic grid and spiral G-code generation;
- Moonraker connection state, virtual-SD Start/Pause/Resume/Cancel, HTTP emergency stop, guarded XYZ jog, safe full home, live needle Z trim, and a read/queued G-code cursor.

## Persisted data

| Data | Location | Behavior |
| --- | --- | --- |
| Global and recipe defaults | `config/config_*.json` | Loaded at startup and updated through **SAVE DEFAULTS**. |
| Grid/spiral counts | `config/config_states.json` | Controls tabs restored at startup. |
| Active workflow | `config/config_gcode_workflow.json` | Validated and saved explicitly in the workflow editor. |
| Preview objects and links | `config/config_visual_objects.json` | Saved independently; geometry never feeds the planner directly. |
| Moonraker example | `config/config_moonraker.example.json` | Key-free connection example. |
| Local Moonraker settings | `config/config_moonraker.json` | Created by **CONFIG**, ignored by Git, and may contain an API key. |
| Job snapshot | `*_settings.json` beside output | Reproducible schema-version 2 generation profile. |

## Generate G-code

Select **GENERATE G-CODE** after adding at least one grid or spiral recipe. The chosen path is a base path:

- grid recipes produce `<base>_grid.gcode`;
- spiral recipes produce `<base>_spiral.gcode`;
- when both exist, both files are created;
- every G-code file receives a matching `<job>_settings.json` sidecar.

Profiles contain global settings, the recipes for that job type, derived runtime values, and the exact effective workflow. Writes are atomic. The dialog starts in `output/gcodes`; this directory is ignored runtime storage and contains no maintained examples.

**LOAD PROFILE** accepts JSON profiles only. Loading a profile:

1. validates the document structure;
2. replaces all current grid and spiral tabs with the saved recipes;
3. restores global values;
4. if `workflow` is present, validates it and overwrites the active `config/config_gcode_workflow.json`.

Treat profile loading as a workflow change, not only a form import.

## Direct Moonraker control

The right-side machine panel starts a background Moonraker runtime without blocking Tk. **CONFIG** edits the host, port, protocol, route prefix, and optional API key; **RETRY** restarts monitoring. The WebSocket is persistent, identified as a desktop client, and subscribes to printer, virtual-SD, position, prompt, saved calibration, and live-Z state. Commands queued before connection or lost before sending fail instead of replaying after reconnect. On a Pi Zero, a fixed IPv4 address can avoid Windows `.local`/mDNS lookup delays.

Deploy the current `hardware/klipper/config/hardware.cfg`, `remote_control.cfg`, and `movement_safety.cfg` together, keep the current `config/config_gcode_workflow.json`, and restart Klipper. The app checks Klipper's advertised commands for the immutable `OPENSPOTTER_CONTRACT_V3` marker and its required manual/job macros, including `OPENSPOTTER_JOB_HOME` and `OPENSPOTTER_JOB_REHOME_Z`. Start, Home, jog, and related machine controls remain disabled when that contract is missing or stale.

**START CURRENT RECIPE** follows this contract:

1. require locked machine parameters and a connected, ready, idle Klippy state;
2. capture an immutable grid or spiral snapshot on the Tk thread;
3. reject invalid text, unbounded pattern/maintenance work, or non-finite inputs;
4. generate and hash the exact artifact in a worker, using compiled workflow expressions;
5. compare rendered XYZ targets plus saved TCP/live-Z offsets with live axis limits;
6. require a loaded BLTouch when the artifact uses `MESH`, and valid TCP coordinate version 2 when it enables needle offsets;
7. show the artifact hash, workflow hash, size, line count, destination, and physical-action warning for final operator confirmation;
8. upload with `print=false`, run a fresh ready/idle preflight, and send one `printer.print.start` RPC.

The separate upload/start sequence deliberately avoids Moonraker’s optional upload queue, which could otherwise schedule motion for later. Repeated identical artifacts use the same SHA-256 remote filename under `gcodes/openspotter/<kind>/`; local runtime output retains the newest 20 artifacts per kind.

Pause/Resume and Stop control the active virtual-SD job. Stop invokes Klipper cancellation and the non-motion `OPENSPOTTER_JOB_CLEANUP` macro. **EMERGENCY STOP** bypasses the WebSocket command queue and posts directly to Moonraker’s authenticated `/printer/emergency_stop` endpoint with a short timeout.

XYZ jog is available only while connected, ready, idle, inactive in virtual SD, and homed on all axes, with needle offsets disabled and bed mesh cleared. It calls the reviewed `OPENSPOTTER_JOG` firmware macro, which requires at least 30 mm/min and validates finite distance/feed values, axis-specific limits, physical toolhead bounds, and movement dead zones. Safe Home uses `OPENSPOTTER_HOME`: sensorless X/Y/Z must have `homing_retract_dist: 0`; each homing contact receives a 2-second StallGuard settle and a release move; X homing occurs only after physical Z reaches at least the commissioned 35 mm clearance and every enabled dead-zone clearance.

Live Z calls the transactional needle-offset macros only during an active job while offsets are enabled. Negative values move closer to the substrate; positive values move away. UI adjustments are live (`SAVE=0`) and are not persisted automatically.

The canvas adds an amber **LIVE REQUESTED TOOLHEAD** cross when Moonraker has supplied fresh position data for homed X/Y axes. It shows Klipper's requested trajectory in raw carriage coordinates rather than encoder feedback, and is intentionally separate from the logical needle-tip path when TCP offsets are enabled. The marker is hidden on disconnect, Klippy restart, stale telemetry, or unhomed X/Y, and it follows pan/zoom without refitting the workspace.

The G-code tab shows Moonraker’s `virtual_sdcard.file_position` mapped onto the exact local artifact. It is explicitly a virtual-SD read/queued cursor, not proof that physical motion has completed. The view is hidden if another filename is active. A response timeout or post-send disconnect is treated as an unknown printer-side outcome; normal controls remain interlocked until monitoring is reconnected, while Emergency Stop stays available.

**MANUAL / CONSOLE** parses text before it can be sent. It accepts a small diagnostic allowlist plus `G90`, `G91`, and bounded `G0`/`G1` XYZ/F moves. Raw motion requires an explicit coordinate mode and feed in the same script, Klipper-native plain decimal words (no `=` or scientific notation), live bounds, homed XYZ, offsets and bed mesh off, no virtual-SD activity, a 30–6000 mm/min feed, and an estimated total duration no longer than 60 seconds. Unknown macros, raw homing, arcs, output/driver changes, safety mutations, and other bypass commands are blocked. `M112`/`EMERGENCY_STOP` is routed through Moonraker's HTTP emergency-stop endpoint rather than the queued G-code path. A partial script error, missing completion sentinel, E-stop, timeout, or disconnect latches the machine controls until the operator inspects the printer and reconnects monitoring.

Preflight is not a complete interpreter for arbitrary custom macros or raw G-code. Review the exact artifact and perform an elevated, fluid-free dry run after changing workflows, profiles, fixtures, or firmware. The supplied Moonraker sample trusts localhost only; explicitly allow just the control PC/isolated subnet and firewall port 7125.

## Runtime G-code workflow

**EDIT G-CODE WORKFLOW** opens the editor for ordered Start, Loading, Printing, Cleaning, and End blocks. Sections attach templates and optional conditions to planner events. The editor supports validation, rendered previews, searchable scoped variables, and custom-variable expressions.

The editor opens maximized in normal windowed mode. Its workspace and preview area share a vertical page scrollbar, while the header, status, and Save/Cancel controls remain visible.

The Python planner retains numeric state and the physical lifecycle: start, refill, pattern motion, maintenance, emptying, and end. Workflow blocks are event hooks; reordering them changes template order for a matching event but does not replace the planner.

Variables are namespaced by global, grid, cleaning, washing, spiral, container, runtime, or custom scope. Grid-only and spiral-only values on shared events should be guarded with a condition such as `runtime.job.kind == 'grid'`. `custom.syringe_mm_per_ul` and `custom.spiral_resolution_radians` are required planner inputs and must remain positive.

Application generation and workflow events cover grid and spiral jobs only. Startup needle calibration and hardware TCP calibration remain separate safety workflows.

## TCP coordinate preview

The CAPTRON beam crossing is visual X0/Y0. Positive X is right and positive Y is down, matching the configured machine motion from the TCP toward the work area. Scroll zooms, dragging pans, and **FIT VIEW** restores the useful extent.

**VISUAL OBJECTS** manages rectangles, circles, and images:

- rectangle X/Y identifies its top-left corner;
- circle X/Y identifies its centre;
- image X/Y identifies its top-left corner;
- width and height may differ, producing an oval;
- images are stretched to the exact width and height entered in millimetres;
- **IMPORT IMAGE…** starts in the project asset folder and can browse to any image path; select **APPLY CHANGES** to persist the draft;
- project-contained images are stored with portable relative paths, while external files use absolute paths;
- text size, descriptive text, and color are editable; image color controls its centred description text;
- rectangle and circle fills are solid;
- X, Y, width, and height can each be linked to a numeric program input by using the dropdown beside the value;
- the object list is a layer stack: higher rows draw above lower rows, and **MOVE UP** / **MOVE DOWN** persist adjacent layer changes immediately.

The program input is authoritative while a property is linked. Changing that input moves or resizes every linked object on the next canvas refresh. Changing a linked value in **VISUAL OBJECTS** and selecting **APPLY CHANGES** writes the value back to the program input, so every other object using the same link follows it. Locked global machine parameters cannot be changed through the visual editor; unlock them through the normal safety control first. Visual links are saved immediately, while changed program values use the existing **SAVE DEFAULTS** action for persistence.

The editable layout starts with the former canvas overlays: build plate, acceptance area, six containers, and the CAPTRON TCP image. Legacy container circles automatically link X/Y to `global.containerN_x/y`, including existing schema-version 1 layouts, so the visual container and loading coordinate remain coupled. Other stable choices include indexed grid, cleaning, washing, and spiral inputs such as `grid.1.grid_offset_x`. The CAPTRON object uses `assets/Captron-TCP.png` and defaults to exactly 60 × 60 mm at X=-30..30 and Y=-30..30.

Unlinked object values remain annotations and never enter generated commands, homing, firmware limits, acceptance checks, or Klipper configuration. A linked visual edit can affect generation only by updating its real program input; visual-object geometry itself is still excluded from the planner. Missing or temporarily invalid link sources use the object's stored fallback value. The coordinate grid, TCP origin marker, generated grid/spiral points, cleaning previews, and washing lines remain live preview primitives rather than editable layout objects. The preview and its acceptance warning are planning aids, not collision protection.

## Hardware boundary

The supplied application workflow disables needle offsets for homing/mesh, then enables them after `MESH`, and disables them at job end. When enabled, the Klipper wrapper applies:

```text
machine X = commanded X + tcp_offset_x
machine Y = commanded Y + tcp_offset_y
machine Z = commanded Z + tcp_offset_z + needle_surface_z_offset
```

Relative moves remain deltas and Klipper bed mesh remains active independently. This behavior is editable through the workflow, so inspect the effective profile rather than assuming the shipped defaults.

TCP calibration now records coordinate version 2. Saved offsets from the former positive-up Y convention are rejected until calibration is run again.

The workflow does not run `TCPSTART` and does not automatically load or park the detachable BLTouch. Direct Start checks the saved readiness state but cannot verify physical tool attachment. Deploy the complete matching hardware/remote-control/safety configuration, restart Klipper, and follow the [Klipper hardware guide](hardware/klipper/README.md) before any machine run.

## Layout

- `main.py`: stable launcher.
- `app`: UI, planner, compiled workflow renderer, generation, preview, Moonraker runtime/controller, and plugins.
- `config`: defaults and persisted application state.
- `assets/images`: current static GUI images.
- `tests`: planner, workflow, generation, visual-object, and hardware-config checks.
- `hardware/klipper`: active printer configuration and custom TCP module.
- `output/gcodes`: ignored runtime output.
- [Spotter_Control_Dev.md](Spotter_Control_Dev.md): source-level developer map.
