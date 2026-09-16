# Klipper Custom Scripts

`tcp_calibration.py` is a Klipper `extras` module for continuous optical-cross
TCP calibration.

The routine performs one pure-X acquisition, then centers X with diagonal
sweeps normal to the X beam while following the needle upward to its tip edge.
At `tip_z - 2 mm`, it re-centers X, follows the physical X beam to cross and
center Y, solves both beam coordinates in that common Z plane, and accepts the
result only when stationary sequential queries report both beams `PRESSED`.
The fixture convention is a clear start on the right/X+ side: acquisition moves
X-, the X beam rises toward X-, and the Y beam rises toward X+.

For this workspace it is installed here:

```text
../klipper-master/klippy/extras/tcp_calibration.py
```

From this `scripts` folder, refresh that workspace copy with:

```powershell
Copy-Item -LiteralPath .\tcp_calibration.py -Destination ..\klipper-master\klippy\extras\tcp_calibration.py -Force
```

Remove the workspace copy with:

```powershell
Remove-Item -LiteralPath ..\klipper-master\klippy\extras\tcp_calibration.py
```

For a printer deployment, copy the same file to the active Klipper source tree:

```sh
cp ~/printer_data/config/scripts/tcp_calibration.py ~/klipper/klippy/extras/tcp_calibration.py
sudo systemctl restart klipper
```

Remove the printer deployment with:

```sh
rm ~/klipper/klippy/extras/tcp_calibration.py
sudo systemctl restart klipper
```

Then include `tcp_calibration.cfg` when installed, or remove that include when
the Python module has been removed.
