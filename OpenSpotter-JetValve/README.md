# Klipper OpenSource Spotter

Desktop GUI for drop-on-demand spotting with Klipper and Moonraker.

## Overview

Klipper OpenSource Spotter is a PyQt6 application that provides:
- valve control and macro execution
- 2D spotting canvas, live toolhead marker, and grid workflow
- status/logging and machine configuration panels
- Moonraker connectivity for motion and command execution

## Current Capabilities

- PyQt6 desktop UI with panels for machine status, controls, canvas, grid setup, valve config, and macro execution.
- Moonraker REST and WebSocket communication for connection status, G-code dispatch, subscribed toolhead position updates, and raw console responses.
- Top-bar Pi file editor for Moonraker-exposed config files and scripts, with save-to-Pi, save-and-restart, service status/actions, and a local Windows-to-Pi sync prompt for checked-in Pi-target files.
- Hardware-only spotting through the unified Klipper `SHOOT` macro; the current valve timing path preloads a Pi-connected Arduino over USB and triggers valve 0 or valve 1 with Pi host-MCU GPIO edges.
- Grid-based spotting with per-grid valve selection, per-grid speed, editable grid names, active/inactive grid toggles, and canvas redraws on grid changes.
- The canvas shows the latest toolhead position as a black X using the live gantry position signal.
- Roll-to-roll canvas mode renders two anchored rows per active grid and a compact row-progress legend instead of drawing every configured Y row.
- The spotting backend uses a row-indexed virtual spot sequence, windowed position projection, and bounded R2R progress payloads so large row counts do not allocate a full spot/path cache.
- Grid definitions are edited in the main window grid panel, not in the machine configuration dialog.
- Bounded spotting dispatch with editable Klipper send-ahead and refill-threshold settings, so a run tops the in-flight queue back up to the configured window after the configured number of spots completes.
- Active Stop and app shutdown are soft stops: the GUI stops refilling Klipper and clears pending local dispatch scripts without putting Klipper into shutdown.
- Configurable start and end G-code scripts stored in `config/machine_config.json`.
- User-facing actions and Moonraker traffic logged to `logs/dod_system.log`, trimmed in batches toward the newest 1000 lines so logging does not block high-rate spotting.

## Current Constraints

- Camera service and camera controller are placeholder-level.
- Calibration manager support is removed for now; only calibration data models remain.
- Test coverage is still limited, but includes model, macro command, spotting dispatch, and logging regressions.
- Hardware behavior should be validated against Moonraker/Klipper logs before changing motion or valve timing assumptions.

## Run

1. Create and activate a virtual environment.
2. Install dependencies.
3. Run the app.

```bash
pip install -r requirements.txt
python main.py
```

## Test

```bash
pytest tests/ -v
```

On the checked-in Windows development environment, use the virtualenv directly if `pytest` is not on PATH:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

## Project Layout

- [models](models): data models
- [views](views): UI widgets and panels
- [controllers](controllers): orchestration and feature logic
- [services](services): Moonraker, camera, logging integrations
- [utils](utils): config, helpers, signals
- [docs](docs): hardware and integration documentation

## Documentation

- [DOCS_INDEX.md](DOCS_INDEX.md): documentation map
- [GETTING_STARTED.md](GETTING_STARTED.md): developer onboarding
- [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md): concise project spec
- [AGENTS.md](AGENTS.md): mandatory Codex and contributor workflow rules
- [docs/START_TO_FINISH_FLOW.md](docs/START_TO_FINISH_FLOW.md): simple walk-through of the Start button to job completion
- [docs/PI_CR6_CONNECTION.md](docs/PI_CR6_CONNECTION.md): Pi + CR6 setup
- [docs/ARDUINO_VALVE_BRIDGE.md](docs/ARDUINO_VALVE_BRIDGE.md): Pi USB Arduino valve timing bridge
- [docs/TROUBLESHOOT_CONNECTION.md](docs/TROUBLESHOOT_CONNECTION.md): connection troubleshooting

## Contribution Rule

Read [AGENTS.md](AGENTS.md) before making changes. When behavior, architecture, commands, configuration, or setup steps change, update the relevant documentation and AGENTS change log in the same change.
