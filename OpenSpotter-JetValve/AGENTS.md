# AGENTS

Compact rules and current project facts for AI agents and contributors.

## Mandatory Workflow

1. Read this file and run `git status --short` before editing.
2. For runtime bugs, read the latest `logs/dod_system.log` entries first.
3. Inspect source-of-truth files before changing behavior.
4. Keep changes small, scoped, and aligned with existing patterns.
5. Do not invent hardware, Klipper, Moonraker, wiring, or timing facts. Verify in code, config, logs, or ask.
6. Keep generated files, caches, virtualenvs, and runtime logs out of source changes.
7. Run focused validation after edits and report commands that could not run.
8. If behavior, architecture, setup, commands, or configuration changes, update human docs and the Change Log below in the same change.

## Source Of Truth

- App entry: `main.py`
- UI shell and mode menu: `views/main_window.py`
- Canvas and R2R display: `views/canvas_view.py`
- Grid editor: `views/grid_panel.py`
- Spotting orchestration: `controllers/spotting_controller.py`
- Moonraker client: `services/klipper_service.py`
- Signal contract: `utils/signals.py`
- Config loader/cache: `utils/config_manager.py`, `utils/json_loader.py`
- Config files: `config/*.json`
- Klipper snippets: `docs/klipper_configs/*.cfg`

## Current Behavior Facts

- Stack: Python, PyQt6, requests, pytest.
- Domain: drop-on-demand spotting GUI with Moonraker/Klipper integration.
- Camera service and camera controller are placeholder-level.
- Calibration workflow is not active; only calibration data models remain.
- Grids are owned by the main-window grid panel, not the machine config dialog.
- Grid tabs support names, active toggles, active-valve selection, per-grid speed, and empty state.
- Buildplate canvas renders every active grid spot.
- Roll-to-roll canvas renders only two anchored rows per active grid plus a top-right `current/total` row legend per grid; it does not allocate spot items for every Y row.
- Spotting sequence planning is row-indexed and virtual; code should index/slice the plan and avoid iterating whole large R2R jobs unless explicitly bounded.
- Spotting dispatch sends an initial burst of up to `dispatch_window_spots`; after each `dispatch_refill_threshold_spots` completions, it tops the in-flight queue back up to the configured window instead of stacking full extra bursts.
- MCU completion follows timestamped realtime `motion_report.live_position` projected onto the dispatched, incomplete path window. Klipper macro responses and Moonraker JSON-RPC ids are not physical completion signals for queued lookahead.
- In R2R mode, progress payloads are bounded to the current row per grid, except the final row keeps the last two rows visible.
- Active Stop and app shutdown are soft stops: stop local dispatch/refill, unblock paused workers, clear pending local publisher scripts, and do not call Moonraker `/printer/emergency_stop`. Already accepted Klipper batches drain normally.
- Spotting start preflight and the listener use cached Moonraker WebSocket toolhead status; do not reintroduce blocking REST status queries on the hot path.
- Valve timing preloads through the Pi-side Arduino bridge. Continuous spotting must preload timing once and then use Pi host-MCU GPIO trigger edges.
- Verified valve path: Pi GPIO17 -> Arduino D2 -> `VALVE=0` on D7; Pi GPIO27 -> Arduino D3 -> `VALVE=1` on D6.
- Arduino bridge supports USB `O:<ticks>`, `P:<ticks>`, `K:<cycles>` and MCU preload `O:<ticks>`, `P:<ticks>`, `C:<cycles>`. No `B`/`X` serial dependency.
- Current Arduino firmware is pulse-only. Hold, latched `VALVE_ON`, and latched `VALVE_OFF` are unsupported.
- `klipper.connect_gcode` runs after Moonraker connects; current default is `START_ARDUINO_VALVE_BRIDGE`.
- Bridge systemd macros use `sudo -n`; exact NOPASSWD sudoers rules are required. Do not add password prompts to G-code.

## Runtime Commands

- Install deps: `pip install -r requirements.txt`
- Run app: `python main.py`
- Run tests: `pytest tests/ -v`
- Windows venv tests: `.\.venv\Scripts\python.exe -m pytest tests/ -v`

## Documentation Policy

- Human docs stay concise and task-focused.
- `AGENTS.md` stays compact and optimized for agent context.
- Remove stale docs when replaced; do not keep duplicate old versions.
- Use `changelog.md` for longer historical notes when needed.

## Change Log

- 2026-06-11: Fixed MCU progress completion to ignore target `toolhead.position` samples and use only `motion_report.live_position`.
- 2026-06-11: Optimized spotting backend for large R2R jobs with virtual row-indexed spot sequences, capped in-flight dispatch top-ups, windowed position completion, and bounded R2R progress keys.
- 2026-06-11: Optimized AGENTS/docs for compact agent use, removed stale CanvasController and generated artifacts, and added R2R two-row canvas rendering with row legends.
- 2026-06-11: Fixed soft Stop after Pause by clearing the worker paused state and marking local spotting dispatch not running while the worker exits.
