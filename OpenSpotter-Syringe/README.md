# OpenSpotter-Syringe

OpenSpotter-Syringe is an open-source, syringe-driven liquid-handling and spotting platform. It combines a Python/Tkinter experiment editor, reproducible G-code generation, Klipper configuration for an Einsy RAMBo 1.1a, and two generations of mechanical design files.

![OpenSpotter-Syringe hardware](Spotter.JPEG)

## Current capabilities

- Configure multiple droplet grids, cleaning and washing cycles, final rinses, and spiral paths.
- Preview geometry in millimetres around the CAPTRON TCP beam crossing at X0/Y0.
- Edit Start, Loading, Printing, Cleaning, and End G-code event blocks at runtime.
- Save versioned JSON profiles beside generated G-code and load those profiles back into the application.
- Connect directly to Moonraker for exact virtual-SD upload/start, monitored Pause/Resume/Cancel, independent Emergency Stop, guarded XYZ motion, and live needle Z trim.
- Calibrate a needle TCP with the retained Klipper optical-cross module.
- Apply saved TCP offsets, bed mesh compensation, and a live needle-to-surface Z trim.
- Use a neutral graphite scientific UI defined centrally in `app/ui_theme.py`.

## Start here

- [GETTING_STARTED.md](GETTING_STARTED.md): install, validate, generate a job, and prepare hardware.
- [Spotter-Control_v3/README.md](Spotter-Control_v3/README.md): application behavior and profile contract.
- [Spotter-Control_v3/hardware/klipper/README.md](Spotter-Control_v3/hardware/klipper/README.md): configuration, commissioning, TCP calibration, and movement safety.
- [CAD/README.md](CAD/README.md): mechanical-file inventory and manufacturing cautions.
- [Docs/README.md](Docs/README.md): BOM, schematics, datasheets, calibration references, and photos.
- [DOCS_INDEX.md](DOCS_INDEX.md): complete documentation map.

Generated files default to `Spotter-Control_v3/output/gcodes`. That directory is intentionally ignored except for `.gitkeep`; it contains runtime output, not maintained examples.

## Repository layout

- `Spotter-Control_v3/app`: desktop UI, planners, compiled workflow renderer, direct-run artifacts, Moonraker runtime/controller, and pattern code.
- `Spotter-Control_v3/config`: editable JSON defaults, workflow, visual layout, and UI state.
- `Spotter-Control_v3/hardware/klipper`: active Klipper configuration and custom TCP module.
- `Spotter-Control_v3/tests`: standard-library unit and integration tests.
- `CAD`: native design files and manufacturing exports.
- `Docs`: component and calibration references.

## Project status

Software generation and fake-Moonraker control paths have unit/integration coverage. Physical commissioning, hardware-in-the-loop validation, and experiment-specific risk assessment remain operator responsibilities. Computer vision, automatic lid handling, and a JetValve controller are not implemented in this repository.

Related publication: [ACS Sensors, DOI 10.1021/acssensors.5c02007](https://pubs.acs.org/doi/10.1021/acssensors.5c02007).
