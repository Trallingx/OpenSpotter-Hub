# Flash Klipper to CR6

## Steps

1. Build firmware from your chosen CR6-compatible Klipper source.
2. Copy firmware binary to SD card as firmware.bin.
3. Insert SD into CR6 and power cycle.
4. Confirm file renamed (firmware flashed).
5. Connect CR6 to Pi via USB.
6. Configure [mcu] serial path in printer.cfg.
7. Restart Klipper and verify MCU ready in logs.

## Commands

```bash
ls /dev/serial/by-id/*
sudo systemctl restart klipper
sudo systemctl status klipper
tail -f ~/printer_data/logs/klippy.log
```

## Common Failures

- bad USB cable (power-only)
- wrong serial path in [mcu]
- invalid config include/order
- failed flash due to SD formatting issues
