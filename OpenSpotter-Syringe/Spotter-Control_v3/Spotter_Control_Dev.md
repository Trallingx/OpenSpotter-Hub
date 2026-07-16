# Spotter-Control_v3 Developer Guide

This guide maps the current implementation and its contracts. Start with
[ARCHITECTURE.md](ARCHITECTURE.md) for dependency and runtime boundaries and
[PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) for extension contracts. User
behavior is documented in [README.md](README.md); firmware commissioning is
documented in [hardware/klipper/README.md](hardware/klipper/README.md).

## Bootstrap and UI

- `main.py` calls `app.main_v3.main()`.
- `app/main_v3.py` creates runtime directories, loads global defaults, restores
  registered plugin counts, and starts Tk.
- `app/gui_v3.py` creates one generic workspace per application plugin and owns
  workspace selection, tabs, controls, defaults, profile loading, and action
  error handling.
- `app/machine_parameters_window.py` owns the persistent maximized global-parameter editor.
- `app/machine_control_panel.py` is presentation-only; it never performs file or network work.
- `app/machine_controller.py` coordinates Tk-safe snapshots, worker generation, preflight, exact upload/start, manual controls, unknown-outcome interlocks, and shutdown.
- `app/moonraker_connection_window.py` owns persistent connection editing.
- `app/machine/` owns immutable connection settings/state/events and the background aiohttp Moonraker runtime.
- `app/plugins/grid/editor.py` and `app/plugins/spiral/editor.py` build recipe
  panels; `app/grid.py` and `app/spiral_grid.py` are compatibility exports.
- `app/input_configs.py` owns `GLOBAL_FIELDS` and compatibility-exports the
  field groups owned by the grid and spiral packages.
- `app/plugin_runtime.py` composes registry plugins that satisfy the richer
  desktop-workspace contract.
- `app/core/ui/forms.py` builds schema-driven Tk entries, readonly comboboxes,
  and tab groups for both global and plugin editors.
- `app/paths.py` is the only central definition of config, asset, output, and log paths.
- `app/runtime_logging.py` configures the rotating runtime log, redacts credential-like values, and serializes effective option snapshots.

The application log is `logs/openspotter-control.log`, rotated at 5 MB with five backups. Important state changes and complete effective generation options are logged at `INFO`; per-trigger workflow rendering decisions are logged at `DEBUG`. `OPENSPOTTER_LOG_LEVEL` controls the level without changing source.

The visual system belongs to `app/ui_theme.py`. Add or change shared palette tokens, fonts, ttk styles, buttons, and entry options there. Use semantic tokens in feature modules; do not introduce another local palette.

Useful UI search targets in `gui_v3.py`:

- `create_buttons`
- `_switch_workspace_mode`
- `instance_pattern` (`instance_grid`/`instance_spiral` are compatibility wrappers)
- `check_saves`
- `_parse_generation_json_file` and `load_generation_config`
- `open_gcode_editor`
- `adding_pictures`

## Preview and visual objects

- `app/core/canvas/` defines `CanvasPreviewContext`, shell-owned preview style,
  immutable primitives/bounds, and optional `CanvasPreviewProvider`.
- `app/plugins/grid/preview.py` and `app/plugins/spiral/preview.py` own the
  built-in renderer-neutral preview planning.
- `app/canvas_drawer.py` combines every preview-capable plugin, draws generic
  primitives by z-order, handles fit/pan/zoom, and checks only
  safety-relevant coordinates against the acceptance boundary.
- `app/visual_objects.py` validates schema-version 2 rectangles/circles/images and their optional geometry bindings, migrates surviving schema-version 1 legacy containers, resolves portable image paths, owns the fresh-install default layout, and persists objects atomically.
- `app/visual_object_editor.py` owns interactive annotation editing plus guarded reverse writes to linked program inputs.
- `config/config_visual_objects.json` is deliberately separate from generation profiles.

Coordinate invariants:

- TCP crossing is preview X0/Y0.
- Preview and machine coordinates use positive X right and positive Y down.
- Static layout geometry, including the build plate, acceptance area, containers, and CAPTRON placeholder, is stored in the editable object list rather than a second hardcoded overlay path.
- The default CAPTRON image spans -30..30 mm on both axes and uses the project-relative `assets/Captron-TCP.png` source.
- Rectangles and images anchor at top-left and extend in positive X/Y; circles anchor at centre.
- Image width/height are converted directly from millimetres to canvas pixels, so independent values intentionally stretch the source to the requested box.
- The image cache is keyed by object ID, resolved path, file metadata, and rendered size. Keep the cached `PhotoImage` alive and invalidate it when the file or target size changes.
- Project-contained images persist relative to the project directory; external image selections persist as absolute paths.
- Both rectangle and circle fills are opaque; do not reintroduce Tk stipple masks for editable surfaces.
- Optional `bindings` map `x`, `y`, `width`, or `height` to a stable numeric program path. Global paths use `global.<field>`; per-pattern paths use an explicit index such as `grid.1.<field>` or `spiral.1.<field>`.
- Binding resolution happens in the canvas snapshot before fitting and drawing. The program value is authoritative; a missing, invalid, or non-positive size source leaves the stored literal as a fallback and records a warning.
- Reverse writes go through `DropletGui._set_visual_binding_variable` and must honor the source widget's current lock/read-only state. Do not use `_set_entry_value` to bypass the global machine-parameter lock for interactive binding edits.
- Persisted object order remains painter order from back to front. The editor deliberately presents `reversed(objects)`, so its first row is the top visual layer; Move Up swaps the stored object with the next index and Move Down swaps it with the previous index.
- Unlinked visual geometry remains annotation-only. Linked geometry also never enters planner calculations directly; only an intentional reverse write to the real program field can affect generation.
- Coordinate axes and the TCP marker remain shell primitives. Built-in
  grid/spiral/cleaning/washing geometry is returned as core preview primitives,
  not editable visual objects.
- Every plugin primitive affects fit-to-content. `safety_relevant=False`
  excludes intentional maintenance geometry from acceptance warnings without
  excluding it from fitting.
- Lower `z_index` values render first. Provider failures are isolated so one
  plugin cannot prevent the remaining preview layers from drawing.

## Generation flow

```text
GUI fields
  -> gcode_generation.save_file
  -> application_plugins
  -> plugin generation adapter
  -> plugin numeric plan and named events
  -> core G-code lifecycle
  -> gcode_workflow template rendering
  -> atomic G-code + schema-version 3 JSON sidecar
```

Key ownership:

- `app/gcode_generation.py`: registry-driven save orchestration and
  plugin-ID-derived output suffixes.
- `app/plugin_runtime.py`: discovery and selection of desktop-capable plugins.
- `app/gcode_shared.py`: common values, acceptance square, output paths, atomic text output, workflow-engine construction.
- `app/core/gcode/`: shared start/refill/empty/rinse/end lifecycle and
  generation sidecars.
- `app/plugins/grid/` and `app/plugins/spiral/`: pattern fields, editor,
  planning, generation, runtime, canvas preview, and workflow
  contribution/preview.
- `app/gcode_planner.py`, `app/grid_gcode.py`, `app/spiral_gcode.py`, and
  `app/SpotterFunctions.py`: legacy compatibility exports; new code imports
  from the owning core or plugin module.
- `app/runtime_job.py`: generic plugin-tagged runtime recipes, shared work and
  artifact caps, hashing/line indexing, deterministic remote names, and local
  runtime retention. Its `grids`/`spirals` properties are compatibility views.

Saving a base path creates one suffixed output for every non-empty registered
desktop plugin. Each schema-version 3 sidecar contains a generic `patterns`
entry with the plugin ID, plugin version, and canonical recipes plus
global/runtime values and the effective workflow. Grid and spiral also retain
their legacy settings arrays for schema-version 2 readers.

Direct execution does not call the file-dialog generation path. The selected
plugin's `capture_runtime_recipes()` strictly validates and detaches its live
editors on the Tk thread; `generate_runtime()` consumes only immutable context
and recipes in a worker. Plugins provide conservative per-recipe
`estimated_work`; core caps total work and rejects artifacts above 50 MiB.
Built-in recipe names reject control characters because workflow interpolation
is executable.

The loader accepts JSON only and requires `global_settings`. It prefers the
schema-version 3 `patterns` array, validates recipes through their registered
plugins, and rebuilds every plugin workspace. Legacy per-plugin profile arrays,
including `grid_settings` and `spiral_settings`, remain accepted. An embedded
validated workflow may overwrite the active workflow after explicit operator
confirmation. Preserve that side effect or introduce an explicit migration if
the contract changes.

## Workflow architecture

- `app/gcode_workflow.py`: schema, safe expression evaluator, template rendering, scope validation, custom-variable dependency resolution, atomic persistence, and runtime engine.
- `app/core/workflow.py`: conflict-checked aggregation of core and plugin field
  groups, triggers, variable scopes, defaults, and planner requirements.
- `app/core/workflow_preview.py`: detached representative event context,
  conflict-checked optional plugin dispatch, and common refill/rinse preview
  calculations.
- `app/plugins/grid/workflow.py` and `app/plugins/spiral/workflow.py`:
  pattern-owned workflow metadata, never command templates.
- `app/plugins/grid/workflow_preview.py` and
  `app/plugins/spiral/workflow_preview.py`: built-in representative event
  values; the generic editor does not know their event semantics.
- `app/gcode_editor.py`: block/section editing, variable catalog, condition/expression tools, validation, preview, and save.
- `config/config_gcode_workflow.json`: only application-owned source of emitted machine-command templates.

`gcode_workflow.DEFAULT_WORKFLOW_PATH` is the writable runtime file.
`SHIPPED_WORKFLOW_PATH` is the immutable resource seed; an engine falls back to
it only when the runtime file is absent.

Workflow blocks do not form a second planner. Plugin planners and
`app/core/gcode/lifecycle.py` emit named events in lifecycle order; matching
enabled sections render in block order and then section order. Add physical
state transitions to the owning planner, contribute or extend a named event,
and keep machine command text in the workflow.

Static expressions, placeholders, variable paths, custom dependencies, and per-trigger section indexes are compiled into bounded caches. Preserve AST immutability and exact-output tests when changing this path; repeated event emission must not reparse the workflow.

## Moonraker runtime and direct execution

```text
Tk inputs
  -> plugin.capture_runtime_recipes (Tk thread)
  -> plugin.generate_runtime + generate_job_artifact (one worker)
  -> manifest/recipe/workflow/artifact confirmation (Tk thread)
  -> HTTP upload, print=false
  -> fresh ready/idle preflight
  -> printer.print.start (persistent WebSocket)
  -> subscribed immutable state -> Tk event bridge -> panel
```

`MoonrakerRuntime` owns one daemon thread and one asyncio loop. Public calls return `concurrent.futures.Future`; no network callback may touch Tk. `MachineControlController` observes futures through Tk `after` polling. State-changing requests fail fast while disconnected and queued unsent requests are never replayed. Sent requests that lose their response are an unknown outcome, not a definite failure; normal controls remain interlocked until monitoring reconnects.

Uploads are intentionally separate from Start. Do not switch the UI path back to `upload_gcode(start=True)`: Moonraker can queue such uploads for later execution. Remote artifact names are content-addressed SHA-256 paths, so identical jobs overwrite/reuse the same remote file.

Connection setup queries `printer.gcode.help`. The required remote-control capability set includes the immutable `OPENSPOTTER_CONTRACT_V3` marker and the reviewed manual/job macros, including `OPENSPOTTER_JOB_HOME` and `OPENSPOTTER_JOB_REHOME_Z`. Missing or stale firmware keeps direct machine controls interlocked. Prefer a fixed IPv4 address on latency-sensitive Pi Zero deployments when `.local`/mDNS resolution is slow.

Start preflight combines:

- connected/ready/idle virtual-SD state;
- locked global parameters;
- live `toolhead.axis_minimum/axis_maximum`;
- rendered absolute motion plus current TCP/live-Z offsets;
- saved `bltouch_state=loaded` when `MESH` is present;
- `tcp_ready=True` and coordinate version 2 when needle offsets are enabled;
- artifact filename matching for the read/queued viewer.

The G-code cursor is based on `virtual_sdcard.file_position`, which is read/queued position. Never describe it as physically executed motion.

`app/manual_gcode.py` performs bounded, immutable parsing before the controller may send console text: 16 KiB, 100 physical lines, and 50 executable commands. The normal console allowlist is diagnostic queries plus explicit `G90`/`G91` and `G0`/`G1` XYZ/F motion. The controller requires homed XYZ, no active virtual-SD job, offsets and bed mesh disabled, live physical/logical coordinates and bounds, explicit mode/feed, 30–6000 mm/min, and at most 60 seconds estimated motion/dwell. Unknown or safety-bypassing commands are blocked. Emergency input is accepted only as a standalone action and is routed to HTTP Emergency Stop. Normal scripts are wrapped in nonce response sentinels plus `M400`; an RPC error, printer error between sentinels, absent completion sentinel, timeout, disconnect, or E-stop latches the unknown-outcome interlock until inspection and reconnect.

Variable metadata distinguishes event availability from job kind. Event-scoped values may only be used where supplied. Mode-specific values on shared events need a `runtime.job.kind` condition. The editor uses representative GUI values for preview; generation supplies planned runtime values.

Grid and spiral are the shipped pattern plugins. Installed application plugins
can contribute their own fields, events, representative previews, canvas
geometry, saved generation, and direct-run recipes without a shell/controller
branch. Startup needle calibration and hardware TCP calibration remain
separate safety workflows rather than pattern plugins.

`custom.syringe_mm_per_ul` and `custom.spiral_resolution_radians` are required positive planner inputs. Other default custom variables currently include priming speed and X-homing clearance.

## Configuration and defaults

- `config/config_global.json`: global defaults.
- `config/config_grid_*.json`: indexed grid defaults.
- `config/config_spiral_1.json`: spiral defaults.
- `config/config_states.json`: workspace-state schema 2 generic plugin counts,
  with legacy built-in count keys accepted.
- `config/config_gcode_workflow.json`: workflow schema version 1.
- `config/config_visual_objects.json`: visual-object and binding schema version 2.
- `config/config_moonraker.example.json`: key-free example.
- ignored `config/config_moonraker.json`: local host/proxy/API-key settings.

`max_grid_count` is a retained persisted key whose label and current meaning are
**Maximum Pattern Count** for each plugin workspace. Keep plugin field keys
aligned between the owning `fields.py`, JSON defaults, profile parsing,
planner/runtime context, and workflow metadata.

## Hardware files

`hardware/klipper/config/printer.cfg` includes:

- `hardware.cfg`
- `tmc2130.cfg`
- `syringe.cfg`
- `bltouch.cfg`
- `movement_safety.cfg`
- `bed_mesh.cfg`
- `display.cfg`
- `mainsail.cfg`
- `remote_control.cfg`
- `tcp_calibration.cfg`

The custom Klipper source of truth is `hardware/klipper/config/scripts/tcp_calibration.py`. It is deployed into the printer's `klippy/extras` directory; no Klipper source checkout is maintained here. `moonraker.conf` is a separate service config and is not included by `printer.cfg`.

When changing generated motion, review axis/syringe limits, the G0/G1 wrappers, raw G0.1/G1.1 uses, mesh assumptions, detachable-probe state, TCP readiness, and the effective workflow together.

Treat `hardware.cfg`, `movement_safety.cfg`, `remote_control.cfg`, and `config/config_gcode_workflow.json` as one versioned motion-control set. The firmware contract v3 expects sensorless `homing_retract_dist: 0`, 2-second settle/release cycles, physical-Z clearance of at least 35 mm plus enabled dead-zone requirements, and job-only home/rehome macros used by the shipped workflow. Restart Klipper after deploying the Klipper files.

## Tests

From this directory:

```powershell
python -m compileall -q app
python -c "import app.main_v3; import app.gui_v3; import app.gcode_shared; import app.plugins; print('imports ok')"
python -m unittest discover -s tests -v
```

Run `python main.py` for visible or interactive changes. The controller/runtime tests use fake Moonraker, state, Tk scheduling, and exact artifacts; hardware config tests are static checks, not hardware-in-the-loop validation.

`tests/test_architecture_boundaries.py` statically rejects concrete/shell/legacy
imports from core, outward imports from pure plugin layers, and executable
implementations in legacy facades.

## Repository hygiene

Keep one generation architecture, JSON-only profiles, current static images, and the project-owned Klipper configuration/custom extra. Do not add parallel retired implementations, generated output, UI captures used only as stale documentation, or a firmware source checkout.
