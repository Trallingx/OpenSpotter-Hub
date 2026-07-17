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
| `remote_control.cfg` | Guarded desktop jog support, contract marker, structured prompts, and job cleanup |
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

Do not deploy `remote_control.cfg` alone. At minimum, copy the current `hardware.cfg`, `movement_safety.cfg`, and `remote_control.cfg` together, keep the desktop's current `config/config_gcode_workflow.json`, preserve the operator-owned configuration that defines `HOMING`, and restart Klipper before using Start, jog, Home, prompt, or cleanup controls. The desktop requires the immutable `OPENSPOTTER_CONTRACT_V4` marker and the `HOMING` command; machine controls remain disabled if Klipper advertises a missing or stale contract.

In the desktop **CONFIG** window, enter the Moonraker host, port, protocol, optional route prefix, and API key. Local `config/config_moonraker.json` is ignored by Git; keep credentials out of the key-free example. A fixed IPv4 address may connect more quickly and reliably than `.local` on a Pi Zero/Windows mDNS combination.

The shipped `moonraker.conf` trusts localhost only. Add the exact control-PC address, or a dedicated isolated machine subnet, to `trusted_clients`; do not restore blanket `10/8`, `172.16/12`, or `192.168/16` trust on a shared lab LAN. Restrict/firewall TCP port 7125 to intended control hosts. A desktop API key does not protect endpoints reached by a client Moonraker already considers trusted.

Do not copy calibrated `saved_vars.cfg` values from another machine.

## Commissioning checks

Before a job:

- confirm X/Z direction, and confirm positive Y moves from the TCP toward the work area (down in the top view);
- commission the operator-owned `HOMING` macro in both idle and active virtual-SD job-start contexts with fixtures and tools clear, verify each axis/endstop behavior at reduced risk, and make `M400` its final executable command;
- verify the syringe endstop, plunger direction, and volume conversion without fluid;
- verify BLTouch pin behavior and dock coordinates at reduced risk;
- test TCP power and both beam inputs;
- calibrate TCP and inspect the saved offsets;
- define and test fixture dead zones;
- confirm `OPENSPOTTER_CONTRACT_V4`, `HOMING`, `OPENSPOTTER_JOG`, `OPENSPOTTER_RUNTIME_STATUS`, and `NEEDLE_TIP_OFFSETS_STATUS` are recognized;
- confirm Moonraker exposes live toolhead limits, saved variables, the OpenSpotter runtime macro, and the needle-offset macro;
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

For the normal guarded sequence, first disable needle corrections, run the commissioned `HOMING` macro, verify that it completed, and then run:

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

The shipped application workflow disables offsets before `HOMING` and `MESH`, enables them afterward, and disables them at job end. The workflow is editable and profiles embed the effective copy, so verify each job.

The application workflow does not call `TCPSTART` and does not automatically load or park the BLTouch. It assumes calibration and tool state have been prepared by the operator. Start preflight requires saved BLTouch state `loaded` before accepting an artifact that uses `MESH`, and the operator must verify the tool physically before Start; `HOMING` is not relied upon to load or park it.

The desktop direct-run preflight blocks an artifact containing `MESH` unless saved BLTouch state is `loaded`, and blocks needle-offset enablement unless `tcp_ready=True` with coordinate version 2. These are saved-state checks, not physical sensors: inspect the detachable tool and work area yourself.

Artifact preflight is deliberately conservative, but it is not a full Klipper G-code/macro interpreter. It checks rendered direct XYZ targets, current offsets, required saved tool state, and bounded work; custom workflow/profile commands may have additional effects. Review the exact confirmed artifact and run an elevated, fluid-free dry run after workflow, profile, fixture, or firmware changes.

## Desktop remote-control contract

The desktop uses the application-owned support commands below plus one operator-owned homing command:

```gcode
HOMING
OPENSPOTTER_JOG AXIS=X DISTANCE=1 F=600
OPENSPOTTER_RUNTIME_STATUS
OPENSPOTTER_JOB_CLEANUP
```

The UI Home action issues exactly one bare `HOMING` command, and the default workflow also contains exactly one bare `HOMING` command. `remote_control.cfg` intentionally does not define `HOMING`, and the application does not inspect or add to its physical choreography. Define and commission the macro in operator-owned Klipper configuration and keep that file outside `remote_control.cfg`.

The V4 interface requires `HOMING` to be safe in both supported call contexts: an idle UI request and the start of an already-active virtual-SD job. Before its first move the macro must neutralize needle offsets and bed mesh or reject the call, preserve and restore relevant modal G-code state, return with XYZ homed, and use `M400` as its final executable command. Because other authorized Moonraker clients can invoke the public macro without the OpenSpotter UI interlocks, `HOMING` itself must validate every precondition on which its safe execution depends.

`OPENSPOTTER_JOG` requires Klippy idle, inactive virtual SD, all XYZ axes homed, needle offsets disabled, and bed mesh cleared. It rejects non-finite/zero distance, limits XY to 25 mm and Z to 5 mm per command, requires at least 30 mm/min, caps XY feed at 6000 mm/min and Z feed at 1500 mm/min, checks live physical toolhead limits, and runs the dead-zone guard.

`OPENSPOTTER_JOB_CLEANUP` performs no motion. It disables needle offsets, clears bed-mesh compensation, clears the structured prompt/LCD message, and is called by normal completion, cancellation, and virtual-SD error handling.

The live needle-Z setter validates finite range/feed and the physical target, runs movement safety before changing coordinate mode, performs the compensation move, restores state, and only then commits or persists the new offset. Desktop adjustments use `SAVE=0`.

Desktop Emergency Stop bypasses the G-code/WebSocket command queue and sends a short-timeout authenticated HTTP POST directly to Moonraker `/printer/emergency_stop`.

The desktop manual console is intentionally not a general Klipper terminal. It permits a small diagnostic-query allowlist and bounded `G90`/`G91` plus `G0`/`G1` XYZ/F tests with explicit mode/feed, live bounds, homed XYZ, offsets/mesh off, no virtual-SD activity, and a 60-second estimated cap. The operator-owned `HOMING` macro is accepted only as a standalone action; unknown macros and commands that bypass homing, movement safety, offsets, drivers, outputs, or job preflight are blocked. Manual `M112` is routed to the same HTTP Emergency Stop. Partial execution errors or a missing completion response latch controls until the machine is inspected and monitoring is reconnected.

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
- [Official Moonraker file API](https://moonraker.readthedocs.io/en/latest/external_api/file_manager/)
- [Official Moonraker printer API](https://moonraker.readthedocs.io/en/latest/external_api/printer/)
