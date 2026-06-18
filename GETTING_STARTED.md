# Getting Started

This guide is for contributors who want to run and change the syringe control application quickly.

## 1. Setup

```bash
cd Spotter-Control_v3
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## 2. Validate Baseline

There is no formal test suite yet. Use Python compilation as the current smoke check:

```bash
cd Spotter-Control_v3
python -m compileall -q app
```

For GUI validation, launch the app and confirm:
- global defaults load from `config/config_global.json`
- grid and spiral tabs restore from `config/config_states.json`
- build plate images load from `assets/images`
- G-code save dialogs open in `output/gcodes`

## 3. Key Files

- [Spotter-Control_v3/main.py](Spotter-Control_v3/main.py): app launcher.
- [Spotter-Control_v3/app/main_v3.py](Spotter-Control_v3/app/main_v3.py): application bootstrap.
- [Spotter-Control_v3/app/gui_v3.py](Spotter-Control_v3/app/gui_v3.py): main Tkinter UI.
- [Spotter-Control_v3/app/input_configs.py](Spotter-Control_v3/app/input_configs.py): field schema and UI theme.
- [Spotter-Control_v3/app/canvas_drawer.py](Spotter-Control_v3/app/canvas_drawer.py): canvas preview.
- [Spotter-Control_v3/app/grid_gcode.py](Spotter-Control_v3/app/grid_gcode.py): grid G-code generation.
- [Spotter-Control_v3/app/spiral_gcode.py](Spotter-Control_v3/app/spiral_gcode.py): spiral G-code generation.
- [Spotter-Control_v3/app/paths.py](Spotter-Control_v3/app/paths.py): central runtime paths.

## 4. Typical Change Workflow

1. Keep source changes in `Spotter-Control_v3/app`.
2. Keep default values in `Spotter-Control_v3/config`.
3. Put runtime logs in `Spotter-Control_v3/logs`.
4. Keep generated G-code under `Spotter-Control_v3/output/gcodes`.
5. Run `python -m compileall -q app`.
6. Update docs in the same change.

## 5. Hardware Integration Checklist

1. Review Klipper files in `Spotter-Control_v3/hardware/klipper/config`.
2. Confirm syringe-specific settings in `Spotter-Control_v3/hardware/syring.cfg`.
3. Generate a small dry-run G-code file before running fluid experiments.
4. Check physical travel limits before enabling unattended motion.
