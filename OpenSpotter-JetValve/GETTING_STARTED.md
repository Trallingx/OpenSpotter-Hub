# Getting Started

This guide is for contributors who want to make changes quickly without reading long specs.

## 1. Setup

```bash
pip install -r requirements.txt
python main.py
```

On Windows with the local virtualenv:

```powershell
.\.venv\Scripts\python.exe main.py
```

## 2. Validate Baseline

Run tests before editing:

```bash
pytest tests/ -v
```

If `pytest` is not on PATH:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

## 3. Codex Workflow

1. Read [AGENTS.md](AGENTS.md) and check `git status --short`.
2. For runtime bugs, read the latest entries in `logs/dod_system.log` before drawing conclusions.
3. Inspect the relevant source-of-truth files before editing.
4. Keep changes small and scoped to the requested behavior or setup issue.
5. Prefer existing controller, service, view, signal, and config patterns.
6. Do not invent hardware facts; if Moonraker/Klipper behavior is unclear, verify it in logs or ask.
7. Run focused tests after edits and report any command that could not run.
8. Update human docs and the [AGENTS.md](AGENTS.md) change log when behavior, architecture, setup, commands, or configuration change.

## 4. Key Files

- [main.py](main.py): app entrypoint
- [views/main_window.py](views/main_window.py): top-level UI wiring
- [controllers/main_controller.py](controllers/main_controller.py): app orchestration and Moonraker connection
- [services/klipper_service.py](services/klipper_service.py): Moonraker HTTP/WebSocket client
- [utils/signals.py](utils/signals.py): signal bus contract

## 5. Typical Change Workflow

1. Pick one feature area.
2. Update model/service/controller/view as needed.
3. Keep signal names and payloads consistent.
4. Run tests.
5. Update docs in the same change.

## 6. Hardware Integration Checklist

1. Confirm host and port in config/machine_config.json.
2. Verify Moonraker is reachable.
3. Test macro path from GUI.
4. For valve timing, set up and test [docs/ARDUINO_VALVE_BRIDGE.md](docs/ARDUINO_VALVE_BRIDGE.md).
5. Validate CR6 and Pi-side macros with the checked-in snippets under [docs/klipper_configs](docs/klipper_configs) before changing wiring-facing behavior.

## 7. Documentation Rule

Every behavior change must include updates to at least one of:
- [README.md](README.md)
- [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md)
- relevant files in [docs](docs)
- [AGENTS.md](AGENTS.md)
