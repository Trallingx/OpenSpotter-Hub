# Deployment Guide

OpenSpotter Control supports source checkouts, Python package installation, and
standalone per-operating-system builds. A graphical desktop, Tk 8.6, and network
access to the intended Moonraker host are required for direct machine control.
Source and wheel metadata require Python 3.8 or newer, with CI coverage on
Python 3.8 and 3.12. Frozen builds bundle their interpreter.

## Supported launch methods

### Editable source checkout

From `OpenSpotter-Syringe/Spotter-Control_v3`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
openspotter-control
```

On macOS or Linux, activate with `source .venv/bin/activate` and run the same
pip upgrade/install commands. Editable PEP 621 installs require a current pip.
Linux Python installations may also require the distribution's Tk package,
commonly `python3-tk`. `python main.py` and `python -m app` remain supported.

### Wheel installation

Build and install a wheel:

```powershell
python -m pip install -e ".[test,build]"
python -m build
python -m pip install --force-reinstall dist\openspotter_control-*.whl
openspotter-control
```

Builds must be tested from a directory outside the checkout. This detects
undeclared resources and imports that accidentally rely on the repository
being the current directory.

### Standalone application

PyInstaller builds are operating-system specific. Build each artifact on the
same operating-system family it targets:

```powershell
python -m pip install -e ".[build]"
pyinstaller --clean packaging\openspotter-control.spec
```

The executable is written under `dist/`. The specification bundles application
defaults and image resources but deliberately excludes
`config/config_moonraker.json`.

## Runtime storage

Application resources and operator data are separate. Packaged JSON and images
are immutable seeds. Editable defaults, workflow changes, visual objects,
connection settings, logs, and generated jobs live under a writable runtime
root.

| Mode | Selection | Writable root |
| --- | --- | --- |
| Source | Automatic inside a checkout, or `OPENSPOTTER_MODE=source` | `Spotter-Control_v3` |
| User | Automatic for wheel/frozen installs, or `OPENSPOTTER_MODE=user` | Per-user data directory |
| Portable | `OPENSPOTTER_MODE=portable` | Beside the executable; source checkouts use their project directory |
| Custom | Set `OPENSPOTTER_HOME` | Exact supplied directory |

Default user roots are:

- Windows: `%LOCALAPPDATA%\OpenSpotter\Control`
- macOS: `~/Library/Application Support/OpenSpotter/Control`
- Linux: `$XDG_DATA_HOME/openspotter-control`, or
  `~/.local/share/openspotter-control`

Every runtime root contains:

```text
config/
logs/
output/gcodes/
```

On first run, missing maintained config files are copied from packaged
defaults. Existing files are never overwritten. Local Moonraker credentials
are not a packaged default.

To migrate an earlier checkout on first run:

```powershell
$env:OPENSPOTTER_MIGRATE_FROM = "C:\path\to\old\Spotter-Control_v3"
openspotter-control
```

Migration runs before default seeding and can copy the old local
`config_moonraker.json`. Remove the variable after the first successful start.
Back up the runtime root before upgrades that change schemas or hardware
workflows.

Advanced packaging and tests can set `OPENSPOTTER_RESOURCE_ROOT` to a directory
containing `config/config_global.json` and `assets/`.

## Release build checks

Before distributing an artifact:

1. Install `.[test,build]` into a clean virtual environment.
2. Run `python -m unittest discover -s tests -v`.
3. Build both sdist and wheel with `python -m build`.
4. Inspect archives and confirm `config_moonraker.json`, logs, generated G-code,
   `.venv`, CAD, and vendor PDFs are absent.
5. Install the wheel into a second clean environment and launch it outside the
   checkout.
6. Build and smoke-test the standalone artifact on each target OS.
7. Confirm first-run config seeding and an upgrade using a copy of operator
   data.
8. Verify generated G-code and direct-control interlocks without fluids before
   hardware use.
9. Publish checksums with the release and sign artifacts when release
   infrastructure supports it.

Wheel or executable portability does not validate a machine configuration.
The matching Klipper files, workflow, firmware contract, limits, calibration,
and physical tool state remain part of deployment acceptance.
