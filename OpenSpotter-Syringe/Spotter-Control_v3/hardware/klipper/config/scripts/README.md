# Klipper TCP Calibration Extra

`tcp_calibration.py` is the repository source for the custom `[tcp_calibration]` Klipper extra. It performs continuous optical-cross moves, follows the X beam upward to find the needle tip, centres X and Y in a common plane, verifies both stationary beam states, and persists TCP coordinates and offsets. Its defaults use the machine convention positive X right and positive Y down; the reflected beam normals and Y acquisition direction must stay aligned with `tcp_calibration.cfg`.

The repository intentionally contains no Klipper source checkout. Install this file into the Klipper tree used by the printer.

## Install

After this `scripts` directory has been deployed to `~/printer_data/config/scripts`:

```sh
cp ~/printer_data/config/scripts/tcp_calibration.py ~/klipper/klippy/extras/tcp_calibration.py
sudo systemctl restart klipper
```

The destination may differ for a nonstandard Klipper installation. A service restart is required so Python imports the new extra. Verify the deployment again after Klipper upgrades.

Deploy `tcp_calibration.cfg` and its include only after the module is present; otherwise Klipper cannot load the `[tcp_calibration]` section.

## Guards and commands

`TCPCALIBRATE` requires homed XYZ, TCP power on in `save_variables`, and saved BLTouch state `parked`. `TCPSTART` performs the positioning and power sequence around it.

- `TCPQUERYBEAMS`: report optical input states.
- `TCPQUERYBLTOUCH`: report the saved detachable-probe state.
- `TCPSHOWOFFSETS`: report persisted tip coordinates and offsets.
- `TCPMOVEWITHOFFSET`: move to a nominal XYZ plus saved TCP offsets.
- `TCPABORT`: power down and set `tcp_ready=False`.

See the [hardware guide](../../README.md) for commissioning and safe usage, and the [calibration flow PDF](tcp_calibration_flow.pdf) for the algorithm.

## Remove

First remove `tcp_calibration.cfg` from the active `printer.cfg` include graph and restart Klipper successfully. Then remove `klippy/extras/tcp_calibration.py`. Reversing that order leaves an unloadable configuration on the next restart.
