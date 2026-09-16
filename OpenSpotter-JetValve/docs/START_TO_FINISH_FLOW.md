# Start to Finish Flow

This page explains what happens in simple steps after you press **Start** in the GUI and before the spotting job ends.

## What Start Does

1. You click **Start** in [views/controls_panel.py](../views/controls_panel.py).
2. The controls panel sends a `spotting_start_requested` signal with sequence settings; live grid definitions supply per-grid speed.
3. [controllers/spotting_controller.py](../controllers/spotting_controller.py) receives the signal and begins the spotting run.
4. The controller builds a row-indexed virtual spot sequence from the active grids, so large grids can be indexed without storing every spot object.
5. If there are no active grids, the job stops immediately and a warning is logged.
6. The controller reads the Moonraker host and port from config.
7. When the main window connects to Moonraker, it sends the configured `klipper.connect_gcode`; the current default starts the Arduino valve bridge service through `START_ARDUINO_VALVE_BRIDGE`.
8. The app reuses the already-connected Moonraker client from the main window and reads the cached WebSocket toolhead state.
9. The app sends the configured start G-code line by line.
10. The controller waits briefly for the WebSocket homing status cache and verifies that the toolhead is homed on X and Y after the start script runs.
11. In Pi-MCU trigger mode, the app sends `SET_ARDUINO_VALVE_TIMING` once for each active valve before dispatch so USB serial is not used at each spot. That preload arms the selected Arduino trigger path before spotting begins.
12. The app starts the Moonraker publisher and listener threads and uses WebSocket status updates for live toolhead position.
13. The worker thread sends an initial buffer of up to `dispatch_window_spots` planned spots. After `dispatch_refill_threshold_spots` completed spots, it tops the in-flight queue back up to the configured window; for example, window 10 and threshold 5 sends spots 1-10, then 11-15 when 5 are complete, then 16-20 when 10 are complete.
14. Each spot becomes one `SHOOT` command containing `X`, `Y`, `SPEED_MM_S`, wait fields, and `TRIGGER_MODE=mcu`. Timing stays in the earlier `SET_ARDUINO_VALVE_TIMING` preload, so per-spot commands do not repeat `ON_MS`, `OFF_MS`, or `CYCLES`. In MCU position-completion mode `dispatch_batch_spots` limits how many lines are grouped into one Moonraker script request. The Klipper macro queues the speed-controlled `G1` move and the Pi-MCU trigger edge in the same command. Zero `PRE_FIRE_WAIT` and `POST_FIRE_WAIT` keeps the shot immediate after the move reaches the queued point; non-zero waits intentionally add timing delay around the Arduino trigger.
15. Moonraker responses are forwarded back into the GUI console and into `logs/dod_system.log`.
16. In Pi-MCU trigger mode, the progress display updates only from timestamped WebSocket `motion_report.live_position` samples. The GUI projects each fresh sample onto the dispatched, incomplete path window and marks every crossed spot in sequence. This keeps the canvas tied to motion completion without using `M400`, consuming early macro-expansion responses, consuming target `toolhead.position` updates, or caching the full path.
17. In roll-to-roll canvas mode, progress is mapped onto two displayed rows per grid instead of drawing every configured Y row. The backend keeps only the current row's progress keys per grid, except the final row keeps the final two rows visible.
18. When the worker finishes normally, the controller sends the configured end G-code line by line.
19. If Stop is pressed or the app closes during an active or paused run, the controller stops local dispatch/refill, unblocks the paused worker if needed, and clears pending local publisher scripts without requesting Moonraker emergency stop. Already accepted Klipper batches drain normally.
20. The controller emits the finished or stopped signal and the GUI returns to an idle state.

## Logging Rule

All user-facing actions should be logged by default.

If a new feature is added later, it should write a log entry for each important step so the behavior can be traced in `logs/dod_system.log`.

## Where The Logs Come From

- `logs/dod_system.log` records the app lifecycle, the spotting controller steps, and Moonraker WebSocket and REST debug messages. The file is trimmed in batches toward the newest 1000 lines so logging cannot block or crash high-rate motion progress.
- The Moonraker client and websocket client no longer rely on `print`, so their debug output is captured in the same rotating log file.
- The Start flow reuses the existing Moonraker client instead of opening a second connection, and homing preflight uses the WebSocket status cache instead of blocking on repeated REST status queries.
- Moonraker WebSocket `motion_report.live_position` updates feed the live position display and MCU-mode spotting completion. USB fallback can still use Klipper's `arduino_valve_fire` responses.
- Start and end G-code scripts are edited from the top bar and stored in `config/machine_config.json` under `klipper.start_gcode` and `klipper.end_gcode`.
- Connect G-code is stored in `config/machine_config.json` under `klipper.connect_gcode` and runs once after Moonraker connects.
- Start G-code runs before the homing validation so a script can establish the homed state before spotting begins.
- Valve pulse timing is owned by the Arduino. In MCU trigger mode, the bridge preloads timing over USB before the run and per-spot firing is only a queued Pi host-MCU GPIO edge.

## Code Path Summary

- Start button: [views/controls_panel.py](../views/controls_panel.py)
- Spotting orchestration: [controllers/spotting_controller.py](../controllers/spotting_controller.py)
- Moonraker API client: [services/klipper_service.py](../services/klipper_service.py)
- Moonraker WebSocket client: [services/moonraker_websocket.py](../services/moonraker_websocket.py)
- App logger: [services/logger_service.py](../services/logger_service.py)
