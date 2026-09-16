# Connection Troubleshooting

Use this order to debug connection issues.

## 1. Verify Config

Check [config/machine_config.json](../config/machine_config.json):
- host must be the Pi IP (not localhost)
- port should be 7125 unless customized

## 2. Verify Services On Pi

```bash
sudo systemctl status moonraker
sudo systemctl status klipper
```

## 3. Verify Network Reachability

```powershell
ping <PI_IP>
Invoke-WebRequest -Uri "http://<PI_IP>:7125/api/server/info"
```

## 4. Verify USB MCU Readiness

```bash
tail -f ~/printer_data/logs/klippy.log
```

Look for: `MCU 'mcu' is ready`

## 5. Verify Macro Path

From GUI, send a known macro and observe logs.

## Common Causes

- wrong Pi IP in config
- Moonraker not running
- Klipper not running
- firewall blocking 7125
- invalid printer.cfg macro definitions
