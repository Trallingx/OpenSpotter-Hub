# Raspberry Pi + CR6 Connection

This is the shortest path to bring up Pi, CR6, Klipper, the Arduino valve bridge, and Spotter.

## Steps

1. Flash Pi with MainsailOS.
2. Flash Klipper to CR6 (see [FLASH_KLIPPER_CR6.md](FLASH_KLIPPER_CR6.md)).
3. Copy config snippets from [klipper_configs](klipper_configs) to the Pi config folder.
4. Connect the Arduino valve controller to the Pi over USB, wire Pi GPIO17 to Arduino D2 for valve 0, wire Pi GPIO27 to Arduino D3 for valve 1, and set up [ARDUINO_VALVE_BRIDGE.md](ARDUINO_VALVE_BRIDGE.md).
5. Restart services:

```bash
sudo systemctl restart klipper
sudo systemctl restart moonraker
```

6. Set [config/machine_config.json](../config/machine_config.json) host to the Pi IP.
7. Run Spotter on Windows:

```bash
python main.py
```

## Validate

- Moonraker API returns 200 from /api/server/info
- Arduino bridge returns 200 from http://127.0.0.1:8765/status on the Pi
- `curl "http://127.0.0.1:8765/configure?valve=0&on_ms=16&off_ms=5&cycles=1"` returns `ok`
- `curl "http://127.0.0.1:8765/configure?valve=1&on_ms=16&off_ms=5&cycles=1"` returns `ok`
- `TEST_ARDUINO_VALVE VALVE=0` pulses Pi GPIO17 and fires Arduino D7
- `TEST_ARDUINO_VALVE VALVE=1` pulses Pi GPIO27 and fires Arduino D6
- GUI status shows connected
- Macro execution from GUI works

## Related docs

- [FLASH_KLIPPER_CR6.md](FLASH_KLIPPER_CR6.md)
- [ARDUINO_VALVE_BRIDGE.md](ARDUINO_VALVE_BRIDGE.md)
- [GUI_INTEGRATION.md](GUI_INTEGRATION.md)
- [TROUBLESHOOT_CONNECTION.md](TROUBLESHOOT_CONNECTION.md)
