
G90 ;use absolute coordinates
G21 ;unit mm

;Homing sequence
M117 Gantry Align
G28 Z0 ;Home Z
G28 Y0 ;Home Y
G0 Z35 F5000.0;Move to X Homing position
G28 X0 ;Home X
G0 X75.0 Y70.0 F5000.0 ; Go with Head to probe position
SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=0
G0 Z110.0 F300.0 ; Ram into top
G0 Z105.0 F300.0 ; Back down
SET_TMC_FIELD STEPPER=stepper_z FIELD=SGT VALUE=4
G28 Z0; Home Z again
G28 Z0; Home Z again
M117 Aligned
MESH X_MIN=27.500 X_MAX=192.500 Y_MIN=24.500 Y_MAX=189.500 POINTS=5 ;Home Z with mesh bed leveling inside acceptance square
G0 X75.0 Y70.0 F5000.0; Go with probe above vacuum chuck
HOME_SYRINGE
DISPENSE MM=0
G1 Z0.0 F300.0 
M117 ;Calibrate Needle to touch substrate
PAUSE
G0 Z40.0 F5000.0
