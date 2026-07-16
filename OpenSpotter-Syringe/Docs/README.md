# Engineering Documents

This directory collects component, electronics, and calibration references for OpenSpotter-Syringe. A file's presence does not prove that its revision matches every physical build; confirm part numbers, wiring, dimensions, and ratings before use.

## Build and electronics

- [Bill of materials](BOM.xlsx)
- [Einsy RAMBo 1.1a schematic](<Schematic Prints_Einsy Rambo_1.1a.PDF>)
- [LMD8S12BSS05-060 actuator datasheet](LMD8S12BSS05-060_Full_Datasheet.pdf)

The checked-in Klipper configuration targets the Einsy RAMBo 1.1a. Pin assignments and electrical limits still require comparison with the actual board and connected hardware.

## CAPTRON optical TCP

- [CAPTRON application note](CAPTRON_Application_Note_TCP.pdf)
- [CAPTRON optical-sensor catalog](CAPTRON-Optical-Sensors-Catalog.pdf)
- [OGLW2-40T-2PS6 datasheet](OGLW2-40T-2PS6-DS_V1.1_de_en.pdf)
- [OGLW2-70T4-2PS6 datasheet](OGLW2-70T4-2PS6-DS_V1.0_de_en.pdf)
- [TCP photo 1](TCP_1.jpg), [photo 2](TCP_2.jpg), [photo 3](TCP_3.jpg), [photo 4](TCP_4.jpg)

The active Klipper config names the OGLW2-40T-2PS6 and uses active-low NPN inputs. The 70T4 document remains a design/component reference.

## Calibration and coordinate stack

- [Needle, bed-mesh, TCP, and live-offset stack](needle-bed-mesh-tcp-offset-stack.pdf)
- [TCP calibration algorithm flow](../Spotter-Control_v3/hardware/klipper/config/scripts/tcp_calibration_flow.pdf)
- [Klipper commissioning guide](../Spotter-Control_v3/hardware/klipper/README.md)

## External references

- [Official Klipper documentation](https://www.klipper3d.org/)
- [Einsy RAMBo overview](https://reprap.org/wiki/EinsyRambo)
- [Einsy RAMBo development notes](https://reprap.org/wiki/EinsyRambo_development)

The repository's current host-side configuration is Moonraker/Mainsail-oriented. Use the checked-in configuration and hardware guide as the project source of truth.
