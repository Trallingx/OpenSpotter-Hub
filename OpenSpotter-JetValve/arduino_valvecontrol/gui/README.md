# Arduino Timing GUI

PyQt5 desktop app to control the ON/OFF timings on the Arduino via the serial protocol implemented in `main.cpp`.

## Setup

1. Install Python 3.10+.
2. In this folder, install deps:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python app.py
   ```

## Firmware protocol (implemented in main.cpp)
- `?` or `W` — request current state.
- `S:onMin:onMax:offMin:offMax` — set ranges; step ≈ (max-min)/9.
- `O:<ms>` — set ON time directly.
- `P:<ms>` — set OFF time directly.
- `E` / `R` — ON minus/plus one step.
- `D` / `F` — OFF minus/plus one step.
- `T` — toggle run/stop (output forced LOW when stopped).
- State line format: `STATE on=<ms> off=<ms> onRange=<lo>-<hi> offRange=<lo>-<hi> running=0|1`.

## GUI controls
- Port selector → Connect.
- Checkbox "Running" toggles `T`.
- ON row: min/max fields, slider, value label, buttons "ON - (E)" / "ON + (R)" (keyboard E/R).
- OFF row: same pattern with D/F.
- Sliders and buttons snap to the step implied by current ranges.

## Notes
- The app polls serial every 50 ms and debounces slider/range changes.
- If the port drops, the app will disconnect and show an error in the status label.
