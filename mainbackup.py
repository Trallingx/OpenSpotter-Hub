file = open("C:/Users/felih/Downloads/TEST/Rwtest.gcode", "w")

# arrangement of cantilevers
rows, cols = (4, 3)

# indexing of cantilevers
arr = [[0 for i in range(cols)] for j in range(rows)]

coordinates = ['0' for i in range(cols*rows)]


l = 0

# writing and printing index
for i in range(rows):
    for j in range(cols):
        arr[i][j] = l
        l = l + 1

for i in range(rows):
    line = ';' + str(arr[i]) + '\n'
    file.write(line)

# X inside square left at exactly 30
# Y inside square down at 82 88okoj

# defining coordinates
x_abs = 32
y_abs = 83
x = x_abs
y = y_abs
z = 5
z_low = 1
index = 0
e_abs = 0
extrude = -1
for j in range(rows):
    for i in range(cols):
        coordinates[index] = 'X' + str(x) + ' Y' + str(y) + ' Z' + str(z)
        x = x + 5
        z = z
        index = index + 1
    x = x_abs
    y = y + 5
# writing into the file
file.write('\nM406 ; Filament sensor of\nG90 ;use absolute coordinates\nG21 ;unit mm\n')
file.write('\n;Homing sequence\n')
file.write('G0 Z10 F3000 ;Lift Z to prevent scratching and allow leveling\n')
file.write('\nG28 [X] [Y]\n')
file.write('G0 X90 Y90 F3000\nG92 [X] [Y] [Z]\nG4 S1\n')
file.write('G28 [Z]\nG4 S1\n')
file.write('G92 X100 Y100 E0\n')
file.write('G0 Z5 F1000\n\n')

# pause for adjusting
# file.write('M601 ;add pause\n')
file.write(';Coordinates\n')
for i in range(rows*cols):
    line = 'G1 ' + coordinates[i] + ' F500' + '\n'
    file.write(line)
    file.write('G1 Z' + str(z_low) + ' F500\n')
    file.write('G1 E' + str(extrude) + ' F250\nG92 E0\nG4 S1\n')  ##Extrude water and wait for drop
    e_abs = e_abs + abs(extrude)
    file.write('G1 Z5 F500\n')
# presenting cantilevers
file.write('\nG1 E' + str(e_abs) + ' F500\n')
file.write('G90 ;absolute positioning\nG0 Y170 Z10 F500;present print\n')
file.close()

list = [("X-line", "mm"), ("Y-line", "mm"), ("First Cantilever X-offset", "mm"),
        ("First Cantilever Y-offset", "mm"), ("Set rows", "int"), ("Set columns", "int"),
        ("X step size", "mm"), ("Y step size", "mm"), ("Dispense Volume", "uL")
        ]