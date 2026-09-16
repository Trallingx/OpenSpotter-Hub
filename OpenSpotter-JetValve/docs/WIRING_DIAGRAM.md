# Wiring Diagram (High Level)

Main path:

```text
Windows Spotter GUI
    -> Moonraker on Raspberry Pi (network)
    -> Klipper on CR6 board plus Raspberry Pi host MCU
    -> Pi host-MCU GPIO triggers into Arduino D2/D3
    -> Arduino valve controller on Raspberry Pi (USB serial for timing preload)
    -> MOSFET drivers
    -> Solenoid valves
```

Current verified control wiring:

```text
Raspberry Pi GPIO17 (Klipper pin rpi:gpio17) -> Arduino D2 trigger input for valve 0
Raspberry Pi GPIO27 (Klipper pin rpi:gpio27) -> Arduino D3 trigger input for valve 1
Raspberry Pi GND -------------------------------- Arduino GND
Arduino D7 -------------------------------------- valve 0 MOSFET driver input
Arduino D6 -------------------------------------- valve 1 MOSFET driver input
```

## Electrical rules

- Do not drive valve coils directly from CR6 MCU pins.
- Use logic-level MOSFET drivers for each valve output.
- Add flyback protection for inductive loads.
- Use a suitable external valve power supply.
- Keep grounds common between Arduino logic, valve driver, and valve supply.
- Keep grounds common between Raspberry Pi and Arduino for the trigger signal.
- Do not connect Arduino 5 V outputs into Raspberry Pi GPIO pins.
- The hardened trigger path accepts stable Arduino D2/D3 trigger edges and ignores short spikes that have returned to the previous level by the time firmware consumes the interrupt. If false triggers remain, add about a 10k pulldown from each trigger input to GND close to the Arduino and route each trigger wire with a nearby ground wire.
- Keep CR6/Klipper on motion control; use the Pi host-MCU trigger only for the verified Arduino trigger input path.

## Safety checklist

- Verify wiring orientation before power-up.
- Confirm Arduino output pin mapping before enabling a valve ID.
- Confirm the Pi GPIOs selected in `valve_macros.cfg` match the wires to Arduino D2 and D3.
- Use gate pull-down resistors to avoid floating gates.
- Run small pulse tests first and monitor logs.
