# Arduino Valve Bridge

Use this when the Arduino is connected to the Raspberry Pi over USB and the GUI sends motion through Moonraker/Klipper.

Current working paths:

- MCU trigger mode: preload timing once, then Klipper pulses the Pi host-MCU GPIO at each spot.
- USB bridge mode: Klipper calls the bridge directly and the console shows the JSON response. Use it as an explicit manual fallback, not as the continuous spotting path.
- The Arduino uses interrupt inputs D2 and D3 for GPIO trigger edges only after timing preload arms each trigger. `VALVE=0` fires D7, and `VALVE=1` fires D6.

The older USB-only immediate trigger path remains available with `TRIGGER_MODE=usb`.

## Find The Arduino Port On The Pi

Prefer the stable by-id path:

```bash
ls -l /dev/serial/by-id/
```

Fallback checks:

```bash
dmesg | grep -E "tty(ACM|USB)"
python3 -m serial.tools.list_ports -v
```

Use a path like `/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043...` instead of `/dev/ttyACM0` when possible, because `ttyACM0` can change after reboot.

## Pi Setup

Install the serial dependency from apt:

```bash
sudo apt update
sudo apt install python3-serial
```

Do not use `python3 -m pip install pyserial` against the Pi system Python on Raspberry Pi OS Bookworm; it is externally managed. If the apt package is unavailable, create a venv and run the bridge with that venv's Python.

```bash
python3 -m venv ~/spotter-valve-venv
~/spotter-valve-venv/bin/python -m pip install pyserial
```

If the project is on the Windows PC, create the Pi target folder over SSH and copy the bridge scripts with `scp` from PowerShell:

```powershell
ssh pi@R2R-SPOTTER-PLOTTER.local "mkdir -p /home/pi/printer_data/config/scripts"
scp .\scripts\arduino_valve_bridge.py pi@R2R-SPOTTER-PLOTTER.local:/home/pi/printer_data/config/scripts/
scp .\scripts\arduino_valve_fire.py pi@R2R-SPOTTER-PLOTTER.local:/home/pi/printer_data/config/scripts/
```

Then on the Pi:

```bash
chmod +x /home/pi/printer_data/config/scripts/arduino_valve_*.py
```

If the project is already cloned on the Pi, copy locally instead:

```bash
mkdir -p /home/pi/printer_data/config/scripts
cp scripts/arduino_valve_bridge.py /home/pi/printer_data/config/scripts/
cp scripts/arduino_valve_fire.py /home/pi/printer_data/config/scripts/
chmod +x /home/pi/printer_data/config/scripts/arduino_valve_*.py
```

## Terminal Tests

### 1. Check the bridge service on the Pi

Start the persistent bridge manually if you are not using the systemd service yet:

```bash
python3 /home/pi/printer_data/config/scripts/arduino_valve_bridge.py \
  --serial-port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
  --baud 9600 \
  --valves 0,1
```

Then verify the bridge endpoint:

```bash
curl http://127.0.0.1:8765/status
curl "http://127.0.0.1:8765/configure?valve=0&on_ms=16&off_ms=5&cycles=1"
curl "http://127.0.0.1:8765/fire?valve=0&on_ms=2&off_ms=2&cycles=1"
curl "http://127.0.0.1:8765/configure?valve=1&on_ms=16&off_ms=5&cycles=1"
curl "http://127.0.0.1:8765/fire?valve=1&on_ms=2&off_ms=2&cycles=1"
```

### 2. Fire the valve directly over USB from a Pi shell

This is the fastest end-to-end check when you want the Arduino to actuate immediately:

```bash
curl "http://127.0.0.1:8765/fire?valve=0&on_ms=16&off_ms=5&cycles=1"
curl "http://127.0.0.1:8765/fire?valve=1&on_ms=16&off_ms=5&cycles=1"
```

### 3. Test MCU-trigger mode from the Klipper console

This path tests the Pi host-MCU GPIO edge path. `TEST_ARDUINO_VALVE` preloads timing and then sends the rising trigger pulse in MCU mode:

```text
SET_ARDUINO_VALVE_TIMING VALVE=0 ON_MS=16 OFF_MS=5 CYCLES=1
TEST_ARDUINO_VALVE VALVE=0 ON_MS=16 OFF_MS=5 CYCLES=1
SET_ARDUINO_VALVE_TIMING VALVE=1 ON_MS=16 OFF_MS=5 CYCLES=1
TEST_ARDUINO_VALVE VALVE=1 ON_MS=16 OFF_MS=5 CYCLES=1
```

If you want to test the underlying move-and-fire macro directly, use `TRIGGER_MODE=mcu` explicitly:

```text
SHOOT VALVE=0 PRE_FIRE_WAIT=0 POST_FIRE_WAIT=0 TRIGGER_MODE=mcu
SHOOT VALVE=1 PRE_FIRE_WAIT=0 POST_FIRE_WAIT=0 TRIGGER_MODE=mcu
```

### 4. Test the USB bridge macro from Klipper

Use this when you want the visible bridge JSON in the console:

```text
SHOOT VALVE=0 ON_MS=16 OFF_MS=5 CYCLES=1 TRIGGER_MODE=usb
SHOOT VALVE=1 ON_MS=16 OFF_MS=5 CYCLES=1 TRIGGER_MODE=usb
```

Do not use the USB bridge fallback as the normal continuous spotting path. It runs a shell command through Klipper, while MCU mode keeps per-spot firing inside the Klipper move queue with `SET_PIN`.

For a realtime check on the Pi, query the motion report instead of the queued toolhead target:

```bash
curl http://127.0.0.1:7125/printer/objects/query?motion_report
```

Look for `result.status.motion_report.live_position` in the JSON output. If that value only changes at the end of the move, the issue is below the GUI subscription layer because Mainsail and the GUI read from Moonraker/Klipper status streams.
```

For normal use, run the bridge as a boot service instead of starting it from a terminal or from G-code:

```bash
sudo nano /etc/systemd/system/spotter-arduino-valve-bridge.service
```

Use this service file, replacing `YOUR_ARDUINO_ID` with the stable `/dev/serial/by-id/...` path:

```ini
[Unit]
Description=Spotter Arduino valve bridge
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/printer_data/config/scripts/arduino_valve_bridge.py --serial-port /dev/serial/by-id/YOUR_ARDUINO_ID --baud 9600 --valves 0,1
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

If you installed `pyserial` in `~/spotter-valve-venv` instead of with `apt`, use the venv Python in `ExecStart`:

```ini
ExecStart=/home/pi/spotter-valve-venv/bin/python /home/pi/printer_data/config/scripts/arduino_valve_bridge.py --serial-port /dev/serial/by-id/YOUR_ARDUINO_ID --baud 9600 --valves 0,1
```

Enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now spotter-arduino-valve-bridge.service
sudo systemctl status spotter-arduino-valve-bridge.service
```

View logs:

```bash
journalctl -u spotter-arduino-valve-bridge.service -f
```

If `systemctl status` shows `status=1/FAILURE`, read the real error:

```bash
journalctl -u spotter-arduino-valve-bridge.service -n 80 --no-pager
systemctl cat spotter-arduino-valve-bridge.service
```

Common causes:

- `/usr/bin/python3` cannot import `serial`; use `sudo apt install python3-serial` or change `ExecStart` to `/home/pi/spotter-valve-venv/bin/python`.
- The bridge script is not at `/home/pi/printer_data/config/scripts/arduino_valve_bridge.py`.
- The Arduino by-id path is wrong or missing.

Do not start the persistent bridge from `SHOOT` G-code. Stock Klipper cannot start external commands, and with `gcode_shell_command` the G-code waits for the command to exit or time out. Starting the long-running bridge per shot would also create duplicate bridge processes or port conflicts. G-code should only trigger the already-running bridge.

## Start The Bridge From Mainsail

You can start the systemd service from a Klipper macro so you do not need to open a terminal each time. This starts the service manager unit, not the long-running bridge process directly.

First confirm the systemctl path on the Pi:

```bash
command -v systemctl
```

The provided macro uses `/usr/bin/systemctl`. If your Pi returns a different path, update `docs/klipper_configs/valve_macros.cfg` before copying it to the Pi.

Allow the Klipper user to start and restart only this service without a password:

```bash
sudo visudo -f /etc/sudoers.d/spotter-arduino-valve-bridge
```

Add this line if Klipper runs as user `pi`:

```text
pi ALL=(root) NOPASSWD: /usr/bin/systemctl start spotter-arduino-valve-bridge.service, /usr/bin/systemctl restart spotter-arduino-valve-bridge.service
```

Then copy the updated [docs/klipper_configs/valve_macros.cfg](klipper_configs/valve_macros.cfg) to the Pi config folder, restart Klipper, and run either macro from Mainsail:

```text
START_ARDUINO_VALVE_BRIDGE
RESTART_ARDUINO_VALVE_BRIDGE
```

The GUI also sends `START_ARDUINO_VALVE_BRIDGE` automatically after it connects to Moonraker. This is configured in [config/machine_config.json](../config/machine_config.json) as:

```json
"connect_gcode": "START_ARDUINO_VALVE_BRIDGE"
```

If Klipper runs under a different user, replace `pi` in the sudoers line with that user. Check with:

```bash
ps -o user= -C klippy
```

Do not enter the Raspberry Pi password into Mainsail, the macro, or the GUI. The macro uses `sudo -n`, which refuses to prompt for a password. If Mainsail reports `sudo: a password is required`, the sudoers rule is missing, has the wrong user, or does not exactly match the `/usr/bin/systemctl ... spotter-arduino-valve-bridge.service` command.

After saving the sudoers rule, test it on the Pi as the Klipper user:

```bash
sudo -n /usr/bin/systemctl start spotter-arduino-valve-bridge.service
systemctl status spotter-arduino-valve-bridge.service
curl http://127.0.0.1:8765/status
```

## Pi Host MCU Trigger Setup

[docs/klipper_configs/printer.cfg](klipper_configs/printer.cfg) includes the Pi host MCU:

```ini
[mcu rpi]
serial: /tmp/klipper_host_mcu
```

The macro snippet defines these trigger outputs:

```ini
[output_pin arduino_valve_trigger_0]
pin: rpi:gpio17

[output_pin arduino_valve_trigger_1]
pin: rpi:gpio27
```

Verify the pins against your actual wiring before enabling the macro. The required wiring is:

- Raspberry Pi GPIO17 (`rpi:gpio17`) -> Arduino D2 trigger for `VALVE=0`
- Raspberry Pi GPIO27 (`rpi:gpio27`) -> Arduino D3 trigger for `VALVE=1`
- Arduino D7 -> valve 0 MOSFET control signal
- Arduino D6 -> valve 1 MOSFET control signal
- Pi GND connected to Arduino GND

The Arduino inputs use normal digital inputs and hardware interrupts on `CHANGE`, but the firmware only fires if the pin level is still changed when the main loop consumes the interrupt. Klipper toggles the matching Pi GPIO once for each spot. This keeps one queued edge per spot while ignoring short coupled spikes that have already returned to the previous level. If false triggers remain, add about a 10k pulldown from each Arduino trigger input to GND close to the Arduino. Do not connect any Arduino 5 V output back into a Raspberry Pi GPIO.

The `SET_ARDUINO_VALVE_TIMING` preload also arms the selected valve trigger, which keeps the Arduino from firing on boot-time pin noise or startup edges before the run is configured.

## Klipper Setup

The macro snippet in [docs/klipper_configs/valve_macros.cfg](klipper_configs/valve_macros.cfg) uses both the local bridge and the Pi host MCU trigger.

Requirements:

- Arduino connected to the Pi over USB.
- Pi host MCU configured and connected to Klipper.
- Pi trigger GPIO17 wired to Arduino D2 and GPIO27 wired to Arduino D3 with common ground.
- `arduino_valve_bridge.py` running on the Pi.
- `arduino_valve_fire.py` copied to the path used by the macro.
- Klipper `gcode_shell_command` extension installed, because stock Klipper does not provide `RUN_SHELL_COMMAND`.

If Mainsail reports this error:

```text
Section 'gcode_shell_command arduino_valve_fire' is not a valid config section
```

then the Klipper shell-command extension is missing. Install or reinstall it with KIAUH:

```bash
cd ~
git clone https://github.com/dw-0/kiauh.git
./kiauh/kiauh.sh
```

In KIAUH, install **G-Code Shell Command** from the advanced/extensions menu, then restart Klipper. If KIAUH is already installed, run `~/kiauh/kiauh.sh` instead of cloning again.

Confirm the extension file exists:

```bash
ls ~/klipper/klippy/extras/gcode_shell_command.py
```

After installation, restart Klipper from Mainsail or run:

```bash
sudo systemctl restart klipper
```

After setup, the GUI sends `SET_ARDUINO_VALVE_TIMING ...` before the run for each active valve when `klipper.valve_trigger_mode` is `mcu`, then sends `SHOOT VALVE=... X=... Y=... SPEED_MM_S=... PRE_FIRE_WAIT=... POST_FIRE_WAIT=... TRIGGER_MODE=mcu` for each spot. The per-spot MCU `SHOOT` command intentionally omits `ON_MS`, `OFF_MS`, and `CYCLES`; the preload is the only timing source. The Klipper macro places the `G1` move and one queued Pi-MCU GPIO edge in one macro call. Zero pre/post waits leave motion continuous; non-zero waits intentionally add timing delay around the shot. The Arduino owns valve pulse timing after it receives the GPIO edge.

## Arduino Firmware

The current Arduino sketch can fire valve 0 on D7 and valve 1 on D6. The bridge selects the valve with `V:<id>`, then uses the legacy timing commands `O:<ticks>`, `P:<ticks>`, and either `K:<cycles>` for immediate USB fire or `C:<cycles>` for MCU-trigger preload. The `C` preload arms the selected trigger path so startup edges are ignored until the run has been configured. The sketch uses 0.1 ms ticks and clamps both ON and OFF timing to a minimum of 2 ms.

For MCU trigger mode, flash the checked-in Arduino sketch because it adds the D2/D3 interrupt trigger inputs. The Pi bridge sends `V/O/P/C` before spotting starts; each stable Pi-MCU GPIO edge then starts the selected valve's preloaded burst. The USB-only fallback still sends `V/O/P/K` for every shot.

If a manual `SHOOT` command seems to do nothing in MCU mode, make sure the Pi host MCU trigger is enabled and use `TRIGGER_MODE=mcu` explicitly or `TEST_ARDUINO_VALVE`.

Current verified pin map:

- `VALVE=0`: Arduino D7 output, Arduino D2 interrupt trigger from Pi GPIO17
- `VALVE=1`: Arduino D6 output, Arduino D3 interrupt trigger from Pi GPIO27

Do not enable additional valve IDs until the Arduino output pin map and driver wiring are verified.

## Timing Boundary

MCU trigger mode removes the per-shot USB serial shell call from the timing path. It still depends on the Raspberry Pi host MCU timing path, not the CR6 motion MCU. If host-MCU jitter is still too high for the required dot placement, move the trigger output to a verified CR6/Klipper MCU pin.
