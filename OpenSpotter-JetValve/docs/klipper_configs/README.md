# Klipper Config Snippets

Reusable Pi/CR6 snippets for the current GUI integration.

## Files

- `printer.cfg`: top-level include template
- `steppers.cfg`: CR6 axes plus `r2r_rewind` manual stepper helpers
- `valve_macros.cfg`: Arduino bridge, valve timing preload, and `SHOOT`
- `moonraker.conf`: Moonraker sample
- `mainsail.cfg`: Mainsail macro sample
- `sonar.conf`: optional network watchdog sample

Legacy LED and safety snippets were removed; keep new setup steps aligned with the files listed above.

## Valve Path

- Continuous spotting uses `SET_ARDUINO_VALVE_TIMING` once per active valve, then per-spot `SHOOT ... TRIGGER_MODE=mcu`.
- Current Arduino firmware is pulse-only. `HOLD`, latched `VALVE_ON`, and latched `VALVE_OFF` are unsupported.
- MCU-mode per-spot `SHOOT` omits `ON_MS`, `OFF_MS`, and `CYCLES`; those values come from the preload.
- USB fallback can still send `ON_MS`, `OFF_MS`, and `CYCLES` for manual testing.

## Start And End G-code

The GUI stores free-form scripts in `config/machine_config.json`:

- `klipper.start_gcode`: runs before spotting homing validation.
- `klipper.end_gcode`: runs after spotting finishes or stops.
- `klipper.connect_gcode`: runs once after Moonraker connects.

Enter one G-code command per line. Blank lines are ignored.
