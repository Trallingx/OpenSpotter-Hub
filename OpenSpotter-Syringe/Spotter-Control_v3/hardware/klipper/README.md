# OpenSpotter Klipper Configuration

This directory contains the active Klipper configuration template for the OpenSpotter-Syringe build. It targets an Einsy RAMBo 1.1a with TMC2130 drivers, a manual syringe stepper, a detachable BLTouch-compatible probe, and a CAPTRON optical TCP cross.

It is not a universal or automatically safe configuration. Pins, axis directions, sensorless-homing thresholds, travel limits, dock coordinates, optical geometry, and syringe direction must be verified on the physical machine.

## Active files

`config/printer.cfg` is the include root:

| File | Responsibility |
| --- | --- |
| `hardware.cfg` | X/Y/Z pins, ranges, homing, and servo |
| `tmc2130.cfg` | All X/Y/Z/syringe TMC2130 sections |
| `syringe.cfg` | Manual syringe stepper and dispense/aspirate macros |
| `bltouch.cfg` | Probe pins, detachable dock macros, and saved-state initializer |
| `movement_safety.cfg` | G0/G1 wrappers, TCP/live-Z offsets, and persistent dead zones |
| `bed_mesh.cfg` | Bed mesh and `MESH`, `MESH_LOAD`, `MESH_CLEAR` macros |
| `display.cfg` | 20 × 4 LCD content |
| `mainsail.cfg` | Minimal virtual-SD, pause, resume, cancel, display, and respond support |
| `tcp_calibration.cfg` | Optical sensor power, macros, pins, and module settings |

`config/moonraker.conf` configures the separate Moonraker service and is not included by Klipper. `config/saved_vars.cfg` is a repository seed with only the initial syringe position; calibration and runtime values are machine-specific.

The repository does not vendor Klipper. The canonical custom module is `config/scripts/tcp_calibration.py`.

## Deployment

Back up the printer's existing configuration and Klipper source before replacing anything.

1. Copy the contents of `config` into the printer's configuration directory, normally `~/printer_data/config`.
2. Install the custom TCP module as described in [config/scripts/README.md](config/scripts/README.md).
3. Review the MCU serial path in `printer.cfg`, the virtual-SD path in `mainsail.cfg`, and any Moonraker paths for the actual host.
4. Compare every pin and connector with the supplied [Einsy RAMBo 1.1a schematic](../../../Docs/Schematic%20Prints_Einsy%20Rambo_1.1a.PDF).
5. Restart Klipper and resolve configuration errors before energizing motion.
6. Commission one subsystem at a time with the tool clear, low current/speed where practical, and an accessible emergency stop.

Do not copy calibrated `saved_vars.cfg` values from another machine.

## Commissioning checks

Before a job:

- confirm X/Z direction, and confirm positive Y moves from the TCP toward the work area (down in the top view);
- tune and test sensorless homing without fixtures in the travel path;
- verify the syringe endstop, plunger direction, and volume conversion without fluid;
- verify BLTouch pin behavior and dock coordinates at reduced risk;
- test TCP power and both beam inputs;
- calibrate TCP and inspect the saved offsets;
- define and test fixture dead zones;
- run elevated, fluid-free G-code while watching machine coordinates.

The syringe coordinate model is E=0 at empty/fully depressed and E=50 mm at homed/full. `ASPIRATE` increases position toward 50; `DISPENSE` decreases it toward 0. Normal macro motion is clamped to that 0–50 mm working range, while the manual stepper's 70 mm `position_max` provides homing overtravel. Verify the real plunger direction, endstop location, and volume conversion before dispensing.

## Detachable BLTouch state

`LOAD_BLTOUCH` and `PARK_BLTOUCH` reject moves unless the saved state permits the requested transition. On a new `saved_vars.cfg`, state is unknown.

Physically inspect the probe first, then initialize the record:

```gcode
SET_BLTOUCH_DOCK_STATE STATE=parked
```

or:

```gcode
SET_BLTOUCH_DOCK_STATE STATE=loaded
```

This command does not move hardware. Use it only after physical verification. `TCPQUERYBLTOUCH` reports the state used by TCP guards.

The dock macros use raw `G0.1` moves so needle offsets are not applied. Those raw moves also bypass the normal G0 safety wrapper; verify dock coordinates and a clear path before use.

## Optical TCP calibration

The active-low NPN inputs are X on `PH0` and Y on `PK0`; sensor power is switched on `PE5`. The Python extra uses continuous homing-style moves rather than polling.

The active coordinate convention is positive X right and positive Y down in the machine top view. The reflected beam normals and `Y_DIRECTION=-1` keep the TCP scan on the same physical beam paths after the Y stepper direction inversion. Any machine calibrated under the previous Y convention must be homing-tested and TCP-calibrated again before saved needle offsets are enabled.

Calibration requires:

- all XYZ axes homed;
- saved BLTouch state `parked`;
- TCP power recorded on;
- a clear start position on the right/X+ side of the optical cross.

Test the inputs before motion:

```gcode
TCPON
TCPQUERYBEAMS
TCPOFF
```

With power on, query once clear and once while interrupting each beam by hand. `PRESSED` means that beam is disrupted.

For the normal guarded sequence, first disable needle corrections, home safely, and run:

```gcode
TCPSTART X=<clear_start_x> Y=<clear_start_y> Z=<clear_start_z> HEIGHT=<beam_height> CALX=<nominal_cross_x> CALY=<nominal_cross_y> CALZ=<nominal_tip_z>
```

`X/Y/Z` position the clear start. `CALX/CALY/CALZ` are the expected final coordinates used to calculate offsets; if omitted they default to X/Y/Z. `TCPSTART` raises to `LIFTZ`, positions the tool, powers the sensor, calls the calibration module, then powers it off.

The module:

1. acquires the X beam with a pure-X move;
2. centres and follows that beam upward to the needle tip edge;
3. re-centres X at `tip_z - 2 mm`;
4. follows the physical X beam to centre Y in the same plane;
5. accepts the result only if stationary X and Y queries both report `PRESSED`.

Success saves `tcp_tip_x/y/z`, `tcp_offset_x/y/z`, `tcp_coordinate_version=2`, and `tcp_ready=True`. Needle-offset motion rejects older or unversioned calibrations. Inspect them with:

```gcode
TCPSHOWOFFSETS
NEEDLE_TIP_OFFSETS_STATUS
```

On a calibration fault, assume the TCP output may still need explicit cleanup and run `TCPABORT`; use `TCPABORT EMERGENCY=1` only when an emergency shutdown is required. The [TCP calibration flow diagram](config/scripts/tcp_calibration_flow.pdf) documents the routine.

## Needle offsets and bed mesh

Normal `G0` and `G1` are wrapped. With needle offsets enabled, absolute targets become:

```text
X machine target = X command + tcp_offset_x
Y machine target = Y command + tcp_offset_y
Z machine target = Z command + tcp_offset_z + needle_surface_z_offset
```

Relative moves remain unmodified deltas. Klipper applies the active bed mesh separately after the corrected target is sent.

Common commands:

```gcode
NEEDLE_TIP_OFFSETS_ENABLE
NEEDLE_TIP_OFFSETS_DISABLE
NEEDLE_TIP_OFFSETS_STATUS
SET_NEEDLE_SURFACE_OFFSET Z=-0.030 MOVE=1 SAVE=1
ADJUST_NEEDLE_SURFACE_OFFSET Z_ADJUST=0.005 MOVE=1
RESET_NEEDLE_SURFACE_OFFSET MOVE=1 SAVE=1
```

Enabling requires `tcp_ready=True` by default. `REQUIRE_TCP=0` exists for a controlled dry run and must not be used to imply a valid calibration.

The live surface trim defaults to a permitted range of -2 to +2 mm. Negative moves the needle closer to the substrate; positive moves it higher. `MOVE=1` applies the delta physically only while offsets are enabled, and `SAVE=1` persists it.

The shipped application workflow disables offsets before homing and `MESH`, enables them afterward, and disables them at job end. The workflow is editable and profiles embed the effective copy, so verify each job.

The application workflow does not call `TCPSTART` and does not automatically load or park the BLTouch. It assumes calibration and tool state have been prepared by the operator.

## Dead-zone guard

Movement safety is disabled by default unless a saved state enables it. Zones are persistent XY rectangles with a Z clearance and independent allowances for travel above the fixture, exit, pure Z lift/lower, or XY motion inside. The guard conservatively treats a move's XY bounding box as its swept area.

```gcode
SET_DEAD_ZONE NAME=fixture X_MIN=80 X_MAX=170 Y_MIN=60 Y_MAX=160 Z_CLEARANCE=20 ALLOW_WHEN_ABOVE=1 ALLOW_EXIT=1 ALLOW_Z_LIFT=1
MOVEMENT_SAFETY_ENABLE
MOVEMENT_SAFETY_STATUS
REMOVE_DEAD_ZONE NAME=fixture
CLEAR_DEAD_ZONES
```

Test every zone with controlled moves. `G0.1` and `G1.1` are the renamed raw Klipper moves; they bypass both correction and the normal guard and should remain limited to reviewed machine macros.

## References

- [Engineering document index](../../../Docs/README.md)
- [Needle, bed-mesh, TCP, and live-offset stack](../../../Docs/needle-bed-mesh-tcp-offset-stack.pdf)
- [Custom TCP module](config/scripts/README.md)
- [Official Klipper documentation](https://www.klipper3d.org/)
