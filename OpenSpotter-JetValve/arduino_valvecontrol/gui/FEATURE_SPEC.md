# Spotter Solenoid Control - Feature Specification

## Purpose
Desktop UI owns all settings and sends pulse commands to an Arduino-controlled solenoid output.
The Arduino only executes pulses and reports errors or pulse-activation messages.

## Architecture
- GUI: PyQt5 app in `app.py`
- Serial transport: `serial_client.py`
- Firmware protocol: `src/main.cpp`

## Serial Protocol
- `S:onMin:onMax:offMin:offMax`: set timing ranges
- `O:<ms>`: set ON time directly
- `P:<ms>`: set OFF time directly
- `E` / `R`: ON minus/plus one step
- `D` / `F`: OFF minus/plus one step
- `K:<count>`: trigger a burst of `count` cycles using the current ON/OFF values

## Firmware Responses
- `ERR ...`: invalid command or invalid parameter
- `ACT pulse=<n> phase=HIGH|LOW`: pulse activation updates

## UI Functional Requirements
- Auto-detect/select the most likely COM port.
- Connect/disconnect serial session.
- Show status text for connection and protocol errors.
- Show and control:
  - ON min/max, slider, current value label
  - OFF min/max, slider, current value label
  - cycle count
- Keyboard shortcuts:
  - `E`/`R` for ON down/up
  - `D`/`F` for OFF down/up
  - `K` for sending pulses
- Keep sliders clamped to current range.
- Prevent invalid range send (`min >= max`).
- Prevent transient typing values from being transmitted (example: typing 900 should not send 9).

## Behavioral Rules
- The GUI is authoritative for settings.
- The Arduino must not overwrite UI state with a separate state model.
- On connect:
  - open port
  - allow command entry
- On disconnect/read failure:
  - close serial
  - stop timers
  - show disconnected state
- On range change:
  - commit text edits first
  - validate ranges
  - sync sliders
  - send range plus current values
- On shot:
  - commit edits
  - validate ranges
  - push current range plus current values
  - send burst command

## Non-Goals
- No running mode.
- No persistent device state synchronization.
- No plotting/history views.
