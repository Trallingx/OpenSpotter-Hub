# AGENT_DOC

Compact machine-oriented context for maintainers and automation.

## Identity

- Project: OpenSpotter-Syringe
- Stack: Python, Tkinter, Pillow, Klipper configuration/G-code, custom Klipper extra
- Target controller in supplied config: Einsy RAMBo 1.1a
- Primary domain: syringe liquid handling and spotting

## Runtime commands

- Install: `cd Spotter-Control_v3 && python -m pip install -r requirements.txt`
- Run: `cd Spotter-Control_v3 && python main.py`
- Compile: `cd Spotter-Control_v3 && python -m compileall -q app`
- Test: `cd Spotter-Control_v3 && python -m unittest discover -s tests -v`

## Active architecture

- Bootstrap and paths: `app/main_v3.py`, `app/paths.py`
- Main UI: `app/gui_v3.py`
- Global parameter window: `app/machine_parameters_window.py`
- Direct-control presentation/coordinator: `app/machine_control_panel.py`, `app/machine_controller.py`
- Moonraker runtime/settings/state/events: `app/machine`, `app/moonraker_connection_window.py`
- Strict direct-run snapshots/artifacts: `app/runtime_job.py`
- Shared dark scientific theme: `app/ui_theme.py`
- Input schemas: `app/input_configs.py`
- Pattern UI: `app/plugins/<plugin>/editor.py`; `app/grid.py` and
  `app/spiral_grid.py` are compatibility exports
- Canvas objects and optional program links: `app/canvas_drawer.py`, `app/visual_objects.py`, `app/visual_object_editor.py`
- Generation orchestration: `app/gcode_generation.py`, `app/grid_gcode.py`, `app/spiral_gcode.py`, `app/gcode_shared.py`
- Shared numeric lifecycle: `app/core/gcode/lifecycle.py`; pattern planning:
  `app/plugins/<plugin>/planner.py`
- Workflow validation/rendering/editor: `app/gcode_workflow.py`, `app/gcode_editor.py`
- Pattern plugins: `app/plugins`
- Canonical workflow: `config/config_gcode_workflow.json`
- Canonical visual objects and bindings: `config/config_visual_objects.json`
- Active hardware include graph: `hardware/klipper/config/printer.cfg`
- Canonical custom Klipper extra: `hardware/klipper/config/scripts/tcp_calibration.py`

## Invariants

- UI colors and fonts come from `ui_theme.py`; do not reintroduce per-window palettes.
- Workflow blocks are event hooks. Python retains lifecycle ordering and numeric syringe state.
- Generated sidecars use schema version 3 generic plugin recipes, retain
  built-in schema-version 2 arrays for migration, and use the suffix
  `_settings.json`; profile loading is JSON-only.
- Loading a profile rebuilds registered plugin workspaces. An embedded workflow is validated and written to the active workflow config.
- Saving with both recipe types creates separate `_grid.gcode` and `_spiral.gcode` jobs and matching profiles.
- `output/gcodes` is ignored runtime output and intentionally contains no examples.
- Canvas rectangles and images use top-left coordinates; circles use centre coordinates. Unlinked geometry is display-only; optional schema-version 2 X/Y/width/height bindings resolve from real program inputs, and guarded reverse writes must honor the global machine-parameter lock.
- Visual-object persistence is painter order from back to front; the editor displays the reverse so higher rows are topmost and layer moves preserve the current appearance until explicitly reordered.
- The canvas origin is the CAPTRON TCP crossing, X0/Y0, with positive X right and positive Y down. The default editable CAPTRON image is 60 × 60 mm and uses `assets/Captron-TCP.png`.
- Build plate, acceptance area, containers, and CAPTRON placeholder all live in the persisted visual-object collection; axes and generated job previews do not.
- Klipper config targets Einsy RAMBo 1.1a. TMC2130 sections live only in `tmc2130.cfg`.
- The include graph has one Mainsail config, one owner for each TMC section, and no firmware source checkout.
- `SET_BLTOUCH_DOCK_STATE` initializes verified state without motion.
- TCP calibration requires homed XYZ, TCP power on, and saved BLTouch state `parked`.
- The Y stepper direction and TCP beam normals are configured for positive Y from the TCP toward the work area; changing that convention requires re-commissioning homing and recalibrating TCP.
- Needle offsets require `tcp_ready=True` and `tcp_coordinate_version=2` by default. Absolute G0/G1 targets add saved TCP offsets; Z also adds the live surface trim. Relative moves remain deltas.
- Raw G0.1/G1.1 bypass the normal correction wrapper and are reserved for reviewed machine macros.
- Direct Start uploads with `print=false`, repeats ready/idle preflight, then calls `printer.print.start`; never replace this with upload auto-start unless queued-job cleanup is proven.
- State-changing commands are not replayed after reconnect. A timeout or disconnect after send is an unknown outcome and normal controls remain interlocked until monitoring reconnects; HTTP Emergency Stop remains available.
- Direct-run recipe names reject CR/LF/control characters. Workflow/profile templates are executable machine code and the final confirmation includes workflow and artifact hashes.
- Direct-run work is bounded before the worker starts, artifacts are capped at 50 MB, identical remote content uses a SHA-256 filename, and only the newest 20 local runtime artifacts per mode are retained.
- Start preflight requires locked globals, ready/idle Klippy, live axis bounds, a loaded saved BLTouch state for `MESH`, and TCP readiness at coordinate version 2 for needle offsets.
- The G-code viewer cursor is virtual-SD read/queued position, never proof of completed physical motion, and is hidden on filename mismatch.
- Direct controls require the immutable advertised `OPENSPOTTER_CONTRACT_V3` plus the reviewed manual/job macro set, including `OPENSPOTTER_JOB_HOME` and `OPENSPOTTER_JOB_REHOME_Z`; missing or stale firmware keeps controls disabled.
- Deploy `hardware.cfg`, `movement_safety.cfg`, `remote_control.cfg`, and the matching `config_gcode_workflow.json` as one motion-control set, then restart Klipper.
- Sensorless X/Y/Z use `homing_retract_dist: 0`. `OPENSPOTTER_HOME` owns the 2-second settle/release Z/Y/physical-clearance/X sequence and requires at least 35 mm plus enabled dead-zone clearances before X home.
- `OPENSPOTTER_JOG` requires homed XYZ, idle/inactive virtual SD, offsets and bed mesh off, physical bounds, and at least 30 mm/min.
- Manual console input is bounded to 16 KiB/100 lines/50 commands and a small query plus `G90`/`G91`/bounded `G0`/`G1` XYZ/F allowlist; raw motion requires explicit mode/feed, live bounds, and at most 60 seconds estimated execution.
- Manual `M112` uses HTTP Emergency Stop. Unsafe/unknown commands are blocked, and partial errors, missing sentinels, timeouts, disconnects, or E-stop latch controls until inspection and reconnect.
- Live Z validates and prechecks motion before coordinate-mode changes, restores state, then commits the offset; desktop changes use `SAVE=0`.
- The sample Moonraker authorization trusts localhost only. Deployment must allow only the exact control host/isolated subnet and firewall port 7125.
- A fixed IPv4 address can avoid `.local`/mDNS connection delay on constrained Pi Zero deployments.

## Folder contract

- Source: `Spotter-Control_v3/app`
- Defaults/state: `Spotter-Control_v3/config`
- Canvas-import assets: `Spotter-Control_v3/assets`
- Static GUI images: `Spotter-Control_v3/assets/images`
- Runtime output: `Spotter-Control_v3/output/gcodes`
- Tests: `Spotter-Control_v3/tests`
- Klipper files: `Spotter-Control_v3/hardware/klipper`
- Mechanical design: `CAD`
- Engineering references: `Docs`

## Known limits

- Hardware-in-the-loop coverage is manual.
- Moonraker/controller tests use fakes; they do not authorize physical motion or prove network/hardware timing.
- The supplied workflow does not run TCP calibration or automatically load/park the detachable BLTouch.
- CAD folders do not provide a formal released-build manifest; verify files against the intended physical revision.
- JetValve, computer vision, and automatic lid handling are not implemented.

## Change log

- 2026-07-16: Added the immutable OpenSpotter contract v3 capability gate, safe sensorless job/manual homing, physical-frame jog/dead-zone checks, and the bounded parsed manual console with HTTP E-stop and partial-outcome interlocks.
- 2026-07-16: Added persistent Moonraker HTTP/WebSocket control, immutable exact virtual-SD artifacts, guarded Start/Pause/Resume/Cancel/E-stop, XYZ jog/home, live Z, read/queued G-code context, connection settings, unknown-outcome interlocks, live bounds/tool readiness, deterministic remote files, retention, and compiled workflow performance caches.
- 2026-07-16: Moved global machine parameters into a persistent maximized editor beside Help and replaced the former reference-imagery space with responsive Machine Control tabs.
- 2026-07-16: Limited application generation to grid and spiral jobs by removing the obsolete standalone calibration UI/event path and its dedicated wait setting; startup needle calibration and hardware TCP calibration remain separate.
- 2026-07-16: Added persistent Move Up/Move Down visual layering with a front-to-back editor list while preserving existing canvas appearance and stored painter order.
- 2026-07-16: Added persistent visual-property bindings to stable numeric program inputs, automatic legacy-container X/Y migration, live canvas resolution with safe fallbacks, and lock-aware reverse editing.
- 2026-07-16: Reflected the machine Y convention to positive-down, including the canvas transform, Y stepper direction, and TCP beam geometry/acquisition defaults.
- 2026-07-16: Added imported image objects with exact millimetre scaling, portable project paths, external-file selection, and cached Tk rendering; migrated CAPTRON to the editable image type.
- 2026-07-16: Moved all former static canvas overlays into the runtime visual-object editor, retained the scalable CAPTRON placeholder, and changed rectangle rendering from stippled mesh to solid fill.
- 2026-07-15: Centralized a graphite/grey scientific UI in `ui_theme.py`; updated all project documentation to the current source and hardware layout; removed stale screenshots, legacy deployment material, generated examples, and the vendored Klipper checkout.
- 2026-07-15: Consolidated hardware configuration around `printer.cfg`, singular `mainsail.cfg`, `syringe.cfg`, and `tmc2130.cfg`; added the non-moving BLTouch state initializer while retaining optical TCP calibration and movement-offset safety.
- 2026-07-15: Consolidated generation around numeric planning plus a runtime-editable workflow, schema-version 2 JSON profiles, atomic output, and focused tests; profile loading is now JSON-only.
- 2026-07-15: Rebased the preview on TCP X0/Y0 and added separately persisted, display-only rectangles and circles.
- 2026-07-09: Reworked TCP calibration for X acquisition, upward X-beam tip tracking, same-plane X/Y centring, stationary beam verification, and persisted TCP offsets.
