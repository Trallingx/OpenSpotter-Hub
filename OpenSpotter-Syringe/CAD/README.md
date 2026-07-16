# OpenSpotter-Syringe CAD

The CAD directory contains two design generations:

- `Syringe_Spotter_V1`: 77 native `.prt` files.
- `Syringe_Spotter_V2`: 121 native `.prt` files plus selected manufacturing exports.

V2 exports include:

- `3D-Printing`: STL parts and one assembled 3MF package;
- `CNC-Mill`: machine-specific G-code exports;
- `Waterjetting`: DXF geometry with OMX, PDF, and log companions.

The folder names indicate design generations, not a formal released-build status. There is no authoritative release manifest identifying which duplicate or suffixed file is approved for a particular machine.

## Before manufacturing

1. Confirm the intended physical revision against the [BOM](../Docs/BOM.xlsx), drawings, and existing machine.
2. Open the native assembly and check dependencies, units, coordinate systems, clearances, and hardware.
3. Verify material, thickness, tolerances, orientation, and process parameters independently.
4. Regenerate CNC or waterjet toolpaths for the actual machine, stock, tooling, and controller. Checked-in G-code/OMX files are references, not universally safe jobs.
5. Inspect printable exports for scale, manifold geometry, supports, and fit before producing a full set.

For the TCP sensor and detachable-probe context, see the [engineering document index](../Docs/README.md) and [Klipper hardware guide](../Spotter-Control_v3/hardware/klipper/README.md).
