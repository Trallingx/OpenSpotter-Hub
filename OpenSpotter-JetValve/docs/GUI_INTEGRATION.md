# GUI Integration with Moonraker

## Data Flow

1. User action in UI
2. Signal emitted via AppSignals
3. Controller receives signal
4. Service sends request to Moonraker
5. Toolhead status updates arrive over Moonraker WebSocket subscriptions
6. Result is logged and reflected in UI

## Main Integration Points

- Signal definitions: [utils/signals.py](../utils/signals.py)
- Controller handling: [controllers/main_controller.py](../controllers/main_controller.py)
- Moonraker client: [services/klipper_service.py](../services/klipper_service.py)

## API Endpoints

- GET /api/server/info
- POST /api/gcode/script
- GET /api/printer/info
- GET /api/printer/objects/query?toolhead
- POST /printer/print/pause and POST /printer/print/cancel for Mainsail-style print controls
- POST /printer/emergency_stop only for true emergency-stop behavior
- GET /server/files/roots, GET /server/files/list, GET /server/files/{root}/{path}, and POST /server/files/upload for the Pi file editor
- GET /machine/system_info and POST /machine/services/{start|stop|restart} for Moonraker-authorized service status/actions
- POST /printer/restart for the Pi file editor's save-and-restart path
- WebSocket `printer.objects.subscribe` for `toolhead.position` and `toolhead.homed_axes`

**Auth & Routing**

- If Moonraker is configured to require API keys or authorization, the GUI's Moonraker client supports passing HTTP headers (e.g. `Authorization`/Bearer tokens). Configure `services.MoonrakerClient(headers={...})` accordingly.
- If Moonraker uses a `route_prefix` (see Moonraker docs), include it when constructing the client so endpoints resolve correctly.

## Minimum Manual Test

1. Start app.
2. Confirm status panel changes to connected.
3. Send a simple macro.
4. Verify success in Moonraker/Klipper logs.

## Notes

- Keep macro format and parameter naming aligned with [docs/klipper_configs/valve_macros.cfg](klipper_configs/valve_macros.cfg).
- Grid spots in MCU trigger mode preload timing once with `SET_ARDUINO_VALVE_TIMING`, then send one `SHOOT` command with `X`, `Y`, `SPEED_MM_S`, `HOLD`, `PRE_FIRE_WAIT`, `POST_FIRE_WAIT`, and `TRIGGER_MODE=mcu`. USB fallback `SHOOT` commands include `ON_MS`, `OFF_MS`, and `CYCLES`.
- Buildplate canvas mode renders every active grid spot. Roll-to-roll canvas mode renders two anchored rows per active grid and a stacked `current/total` row legend so large row counts do not allocate thousands of visual rows.
- After Moonraker connects, the main controller sends `klipper.connect_gcode`; the current default is `START_ARDUINO_VALVE_BRIDGE`.
- Spotting dispatch must not block each move on a REST position query. Live position display can use cached toolhead status, but MCU-mode spotting completion is driven only by WebSocket `motion_report.live_position` samples. At run start, the GUI clears prior completed spots, records a timestamped run boundary, and projects fresh live-position samples only onto the dispatched, incomplete spot window so sparse updates can still complete crossed spots in sequence without caching the full path. Klipper macro responses, Moonraker JSON-RPC responses, and `toolhead.position` target updates are not physical completion signals. `dispatch_window_spots` is the maximum in-flight send-ahead window, and `dispatch_refill_threshold_spots` is the completed-spot count that triggers a top-up. For example, window 10 and threshold 5 sends spots 1-10, then 11-15 when 5 are complete, then 16-20 when 10 are complete. `dispatch_batch_spots` still limits how many lines are grouped into one Moonraker script request.
- Pressing Stop or closing the app during an active spotting run does not request Moonraker `/printer/emergency_stop`. It stops local dispatch/refill and clears pending local publisher scripts; already accepted Klipper batches are allowed to drain. The emergency endpoint remains reserved for actual emergency-stop UI because Moonraker documents it as a shutdown path.
- Stale `SPOTTER_SHOOT_DONE` macro messages from older Pi-side configs are ignored by the GUI to avoid log and console flooding. The current checked-in `valve_macros.cfg` should still be copied to the Pi because Klipper itself can be slowed by excessive g-code response output.
- The `Pi_Files` top-bar action is disabled until Moonraker connects, then opens a Moonraker-backed file editor. The Pi is treated as the source of truth. File editor Moonraker calls run in background worker threads and return UI updates through Qt signals; do not run blocking file API calls on the GUI thread. From the editor reload/upload controls, the GUI compares local Pi-target files from `docs/klipper_configs/*` and `scripts/arduino_valve_*.py` against the Pi `config` root and asks before uploading Windows copies. The per-file `Copy To Local` action downloads the current Pi file and overwrites the mapped local copy only after confirmation.
- Pi file editor open, reload, root listing, file listing, download, upload, sync prompt, Klipper restart, service actions, and caught exceptions are logged to `logs/dod_system.log`.
- The service tab only shows and controls services that Moonraker reports in `machine.system_info.available_services`; add project-specific services such as the Arduino bridge to Moonraker's allowed services if they should be controllable there.
- Spotting start preflight uses cached WebSocket `toolhead` status and waits only briefly for homing status after start G-code; repeated blocking REST status queries should not be added back to the start path.
- Valve timing is preloaded through the Pi-side Arduino bridge in the provided macro snippet; the per-spot trigger is a Pi host-MCU GPIO edge when `klipper.valve_trigger_mode` is `mcu`.
- `SHOOT` has no async flag. Zero `PRE_FIRE_WAIT` and `POST_FIRE_WAIT` leaves motion continuous after the embedded `G1`; non-zero waits intentionally add timing delay around the Arduino trigger. Live position display should follow the `motion_report.live_position` WebSocket updates, not the queued `toolhead.position` target. Do not add an unconditional `M400` unless stationary stop-at-each-spot behavior is intended.
- The current verified Arduino pin map supports `VALVE=0` on Arduino D7 triggered through D2 from Pi GPIO17, and `VALVE=1` on Arduino D6 triggered through D3 from Pi GPIO27. Additional valve IDs require verified Arduino wiring and firmware changes.
- Burst timing with `CYCLES>1` is handled by the Arduino after the Pi-MCU trigger edge instead of streaming valve output edges through Klipper.
- Update this file if signal names or endpoint usage changes.
