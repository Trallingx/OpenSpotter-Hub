# Documentation Index

This project keeps a compact, task-focused documentation set.

## Start Here

1. [README.md](README.md)
Purpose: run the app and get high-level context.

2. [GETTING_STARTED.md](GETTING_STARTED.md)
Purpose: practical contributor workflow.

3. [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md)
Purpose: architecture and project scope.

4. [AGENTS.md](AGENTS.md)
Purpose: mandatory Codex workflow, contribution rules, and change log.

## Human Setup Docs

- [docs/PI_CR6_CONNECTION.md](docs/PI_CR6_CONNECTION.md): end-to-end Pi + CR6 setup flow.
- [docs/START_TO_FINISH_FLOW.md](docs/START_TO_FINISH_FLOW.md): plain-language walk-through of what happens after pressing Start.
- [docs/FLASH_KLIPPER_CR6.md](docs/FLASH_KLIPPER_CR6.md): firmware flash notes.
- [docs/WIRING_DIAGRAM.md](docs/WIRING_DIAGRAM.md): high-level wiring safety notes.
- [docs/ARDUINO_VALVE_BRIDGE.md](docs/ARDUINO_VALVE_BRIDGE.md): Pi USB Arduino valve timing bridge setup.
- [docs/GUI_INTEGRATION.md](docs/GUI_INTEGRATION.md): GUI to Moonraker integration contract.
- [docs/TROUBLESHOOT_CONNECTION.md](docs/TROUBLESHOOT_CONNECTION.md): connection diagnostics.
- [docs/klipper_configs/README.md](docs/klipper_configs/README.md): reusable Klipper snippets and GUI-edited start/end G-code notes.

## AI Maintenance Docs

- [AGENTS.md](AGENTS.md): mandatory Codex workflow, contribution rules, doc-update rules, and compact project context.

## Code Entry Points

- [main.py](main.py)
- [views/main_window.py](views/main_window.py)
- [controllers/main_controller.py](controllers/main_controller.py)
- [services/klipper_service.py](services/klipper_service.py)
- [utils/signals.py](utils/signals.py)

## Maintenance Policy

Whenever behavior, architecture, setup, commands, or configuration changes, update code and documentation in the same change and add an AGENTS change-log note.
