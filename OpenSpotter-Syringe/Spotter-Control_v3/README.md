# Spotter-Control_v3

Spotter-Control_v3 is the local desktop recipe editor, G-code generator, and Moonraker machine console for OpenSpotter-Syringe. It uses Tkinter, Pillow, and a persistent aiohttp WebSocket/HTTP client. Saved-file generation remains available without a printer connection.

## Run

From this directory on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
openspotter-control
```

On macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
openspotter-control
```

`python main.py` and `python -m app` remain equivalent source launchers. See
[DEPLOYMENT.md](DEPLOYMENT.md) for wheels, standalone builds, writable runtime
locations, and migration from an older checkout.

## Validate

```powershell
python -m pip install -e ".[test]"
python -m compileall -q app
python -m unittest discover -s tests -v
```

Launch the GUI after changes to appearance, interaction, paths, images, or workflow editing.

## Runtime logs

Each application run writes `openspotter-control.log` under the active runtime
root's `logs` directory. Source checkouts keep the historical local path;
installed and frozen builds use per-user writable storage. The file records
startup state, effective global and recipe options, workflow/profile changes,
generation choices, output paths, fallback defaults, and failures. Logs rotate
at 5 MB with five backups, and credential-like values are redacted.

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
- atomic plugin-driven G-code generation (grid and spiral are built in);
- Moonraker connection state, virtual-SD Start/Pause/Resume/Cancel, HTTP emergency stop, guarded XYZ jog, an operator-owned `HOMING` action, live needle Z trim, and a read/queued G-code cursor.

## Persisted data

| Data | Location | Behavior |
| --- | --- | --- |
| Global and recipe defaults | `config/config_*.json` | Loaded at startup and updated through **SAVE DEFAULTS**. |
| Pattern counts | `config/config_states.json` | Schema-version 2 registered-plugin counts, with legacy built-in keys accepted. |
| Active workflow | `config/config_gcode_workflow.json` | Validated and saved explicitly in the workflow editor. |
| Preview objects and links | `config/config_visual_objects.json` | Saved independently; geometry never feeds the planner directly. |
| Moonraker example | `config/config_moonraker.example.json` | Key-free connection example. |
| Local Moonraker settings | `config/config_moonraker.json` | Created by **CONFIG**, ignored by Git, and may contain an API key. |
| Job snapshot | `*_settings.json` beside output | Reproducible schema-version 3 plugin profile with legacy built-in arrays. |

## Generate G-code

Select **GENERATE G-CODE** after adding at least one pattern recipe. The chosen path is a base path:

- every non-empty application plugin produces `<base>_<plugin-id>.gcode`;
- the built-in examples are `<base>_grid.gcode` and
  `<base>_spiral.gcode`;
- when several plugin workspaces contain recipes, each produces its own file;
- every G-code file receives a matching `<job>_settings.json` sidecar.

Profiles contain global settings, the recipes for that job type, derived runtime values, and the exact effective workflow. Writes are atomic. The dialog starts in `output/gcodes`; this directory is ignored runtime storage and contains no maintained examples.

**LOAD PROFILE** accepts JSON profiles only. Loading a profile:

1. validates the document structure;
2. replaces all registered pattern workspaces with the saved recipes;
3. restores global values;
4. if `workflow` is present, validates it and overwrites the active `config/config_gcode_workflow.json`.

Treat profile loading as a workflow change, not only a form import.

## Direct Moonraker control

The right-side machine panel starts a background Moonraker runtime without blocking Tk. **CONFIG** edits the host, port, protocol, route prefix, and optional API key; **RETRY** restarts monitoring. The WebSocket is persistent, identified as a desktop client, and subscribes to printer, virtual-SD, position, prompt, saved calibration, and live-Z state. Commands queued before connection or lost before sending fail instead of replaying after reconnect. On a Pi Zero, a fixed IPv4 address can avoid Windows `.local`/mDNS lookup delays.

Deploy the current `hardware/klipper/config/hardware.cfg`, `remote_control.cfg`, and `movement_safety.cfg` together, keep the current `config/config_gcode_workflow.json`, preserve the operator-owned Klipper configuration that defines `HOMING`, and restart Klipper. The app checks Klipper's advertised commands for the immutable `OPENSPOTTER_CONTRACT_V4` marker and the single required homing macro `HOMING`. Start, Home, jog, and related machine controls remain disabled when that contract is missing or stale.

**START CURRENT RECIPE** follows this contract:

1. require locked machine parameters and a connected, ready, idle Klippy state;
2. ask the selected plugin to capture immutable recipes on the Tk thread;
3. reject invalid text, unbounded pattern/maintenance work, or non-finite inputs;
4. generate and hash the exact artifact in a worker, using compiled workflow expressions;
5. compare rendered XYZ targets plus saved TCP/live-Z offsets with live axis limits;
6. require a loaded BLTouch when the artifact uses `MESH`, and valid TCP coordinate version 2 when it enables needle offsets;
7. show the artifact hash, workflow hash, size, line count, destination, and physical-action warning for final operator confirmation;
8. upload with `print=false`, run a fresh ready/idle preflight, and send one `printer.print.start` RPC.

The separate upload/start sequence deliberately avoids Moonraker’s optional upload queue, which could otherwise schedule motion for later. Repeated identical artifacts use the same SHA-256 remote filename under `gcodes/openspotter/<kind>/`; local runtime output retains the newest 20 artifacts per kind.

Pause/Resume and Stop control the active virtual-SD job. Stop invokes Klipper cancellation and the non-motion `OPENSPOTTER_JOB_CLEANUP` macro. **EMERGENCY STOP** bypasses the WebSocket command queue and posts directly to Moonraker’s authenticated `/printer/emergency_stop` endpoint with a short timeout.

XYZ jog is available only while connected, ready, idle, inactive in virtual SD, and homed on all axes, with needle offsets disabled and bed mesh cleared. It calls the reviewed `OPENSPOTTER_JOG` firmware macro, which requires at least 30 mm/min and validates finite distance/feed values, axis-specific limits, physical toolhead bounds, and movement dead zones.

The UI Home action issues exactly one bare `HOMING` command, and the default workflow also contains exactly one bare `HOMING` command. The application does not define or inspect that macro's physical choreography. Define and commission it in operator-owned Klipper configuration outside `remote_control.cfg`.

The V4 interface requires `HOMING` to be safe both when called from the idle UI and when called at the start of an active virtual-SD job. Before its first move it must either neutralize needle offsets and bed mesh or reject the call, it must preserve and restore relevant modal G-code state, and it must return with XYZ homed. Make `M400` its final executable command so all queued physical motion completes before the macro returns. `HOMING` is public to every authorized Moonraker client, so the firmware macro itself—not only this application's UI checks—must validate its preconditions.

When a job artifact uses `MESH`, Start preflight already requires the saved BLTouch state to be `loaded`; the operator must also verify the tool physically before Start. `HOMING` is not relied upon to load or park the BLTouch.

Live Z calls the transactional needle-offset macros only during an active job while offsets are enabled. Negative values move closer to the substrate; positive values move away. UI adjustments are live (`SAVE=0`) and are not persisted automatically.

The canvas adds an amber **LIVE REQUESTED TOOLHEAD** cross when Moonraker has supplied fresh position data for homed X/Y axes. It shows Klipper's requested trajectory in raw carriage coordinates rather than encoder feedback, and is intentionally separate from the logical needle-tip path when TCP offsets are enabled. The marker is hidden on disconnect, Klippy restart, stale telemetry, or unhomed X/Y, and it follows pan/zoom without refitting the workspace.

The G-code tab shows Moonraker’s `virtual_sdcard.file_position` mapped onto the exact local artifact. It is explicitly a virtual-SD read/queued cursor, not proof that physical motion has completed. The view is hidden if another filename is active. A response timeout or post-send disconnect is treated as an unknown printer-side outcome; normal controls remain interlocked until monitoring is reconnected, while Emergency Stop stays available.

**MANUAL / CONSOLE** parses text before it can be sent. It accepts a small diagnostic allowlist plus `G90`, `G91`, and bounded `G0`/`G1` XYZ/F moves. Raw motion requires an explicit coordinate mode and feed in the same script, Klipper-native plain decimal words (no `=` or scientific notation), live bounds, homed XYZ, offsets and bed mesh off, no virtual-SD activity, a 30–6000 mm/min feed, and an estimated total duration no longer than 60 seconds. The operator-owned `HOMING` macro is accepted only as a standalone action; unknown macros, raw `G28` homing, arcs, output/driver changes, safety mutations, and other bypass commands are blocked. `M112`/`EMERGENCY_STOP` is routed through Moonraker's HTTP emergency-stop endpoint rather than the queued G-code path. A partial script error, missing completion sentinel, E-stop, timeout, or disconnect latches the machine controls until the operator inspects the printer and reconnects monitoring.

Preflight is not a complete interpreter for arbitrary custom macros or raw G-code. Review the exact artifact and perform an elevated, fluid-free dry run after changing workflows, profiles, fixtures, or firmware. The supplied Moonraker sample trusts localhost only; explicitly allow just the control PC/isolated subnet and firewall port 7125.

## Runtime G-code workflow

**EDIT G-CODE WORKFLOW** opens the editor for ordered Start, Loading, Printing, Cleaning, and End blocks. Sections attach templates and optional conditions to planner events. The editor supports validation, rendered previews, searchable scoped variables, and custom-variable expressions.

The editor opens maximized in normal windowed mode. Its workspace and preview area share a vertical page scrollbar, while the header, status, and Save/Cancel controls remain visible.

The Python planner retains numeric state and the physical lifecycle: start, refill, pattern motion, maintenance, emptying, and end. Workflow blocks are event hooks; reordering them changes template order for a matching event but does not replace the planner.

Variables are namespaced by global, grid, cleaning, washing, spiral, container, runtime, or custom scope. Grid-only and spiral-only values on shared events should be guarded with a condition such as `runtime.job.kind == 'grid'`. `custom.syringe_mm_per_ul` and `custom.spiral_resolution_radians` are required planner inputs and must remain positive.

Grid and spiral are the shipped pattern plugins. Compatible installed plugins
may add workspaces, workflow events, canvas previews, saved generation, and
direct-run capture/generation through plugin API 1. Startup needle calibration
and hardware TCP calibration remain separate safety workflows.

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

The supplied application workflow disables needle offsets before `HOMING` and `MESH`, then enables them after `MESH`, and disables them at job end. When enabled, the Klipper wrapper applies:

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
- `app/core`: reusable contracts and services for plugins, schemas, storage,
  canvas previews, workflow composition, and shared G-code lifecycle.
- `app/plugins`: built-in grid and spiral pattern packages.
- `app`: generic Tk shell, compiled workflow renderer, runtime artifacts, and
  Moonraker runtime/controller.
- `config`: defaults and persisted application state.
- `assets/images`: current static GUI images.
- `tests`: planner, workflow, generation, visual-object, and hardware-config checks.
- `hardware/klipper`: active printer configuration and custom TCP module.
- `output/gcodes`: ignored runtime output.
- [DEPLOYMENT.md](DEPLOYMENT.md): source, wheel, standalone, and runtime-data deployment.
- [VERSIONING.md](VERSIONING.md): application, schema, and firmware compatibility versions.
- [CHANGELOG.md](CHANGELOG.md): user-visible release history.
- [ARCHITECTURE.md](ARCHITECTURE.md): core/plugin boundaries, runtime layers,
  dependency rules, and migration status.
- [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md): installed entry points and
  desktop plugin hooks.
- [Spotter_Control_Dev.md](Spotter_Control_Dev.md): source-level developer map.
