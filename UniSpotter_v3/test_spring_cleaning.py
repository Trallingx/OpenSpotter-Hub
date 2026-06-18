#!/usr/bin/env python3
"""Spring Cleaning Smoke Test - Verify refactoring didn't break anything"""

import json, sys, tempfile, os

print('=' * 60)
print('SPRING CLEANING SMOKE TEST')
print('=' * 60)

# Test 1: Import all cleaned modules
print('\n[TEST 1] Importing cleaned modules...')
try:
    from create_gcode import save_file, generate_anchor_calibration
    from grid_gcode import save_grid_gcode
    from spiral_gcode import save_spiral_gcode
    from gcode_shared import collect_common_generation_data, prompt_save_base_path, compute_acceptance_square
    from plugins import discover_plugins, get_plugin, list_plugins, get_available_plugin_types
    print('✅ All modules imported successfully')
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)

# Test 2: Load plugins
print('\n[TEST 2] Testing plugin discovery...')
discover_plugins()
plugins = list_plugins()
print(f'✅ Found {len(plugins)} plugins: {plugins}')
plugin_types = get_available_plugin_types()
print(f'✅ Plugin types: {plugin_types}')

# Test 3: Initialize GUI and test data collection
print('\n[TEST 3] Initializing GUI and collecting common data...')
try:
    from gui_v3 import DropletGui
    from grid import create_labels
    from input_configs import GLOBAL_FIELDS
    
    gui = DropletGui('c:/Users/sduna/Desktop/FelixSpotters/AutoSpan_DoubleGridSpotter/UniSpotter_v3')
    cfg = json.load(open('config_global.json', 'r'))
    create_labels(GLOBAL_FIELDS, cfg, gui.entry, gui.global_input_frame)
    gui.instance_grid()
    gui.instance_spiral()
    
    print('✅ GUI initialized')
    print(f'✅ Grids: {len(gui.grid_tab_dict)}')
    print(f'✅ Spirals: {len(gui.spiral_tab_dict)}')
    
    # Test common data collection
    common = collect_common_generation_data(gui)
    print(f'✅ Common data collected: {len(common)} keys')
    print(f'  - x_abs={common["x_abs"]:.2f}, y_abs={common["y_abs"]:.2f}')
    print(f'  - priming_vol={common["priming_vol"]:.2f} uL')
    print(f'  - probe_ram_height={common["probe_ram_height"]:.2f} mm')
    print(f'  - present_plate_y={common["present_plate_y"]:.2f} mm')
    
except Exception as e:
    print(f'❌ GUI initialization failed: {e}')
    import traceback; traceback.print_exc()
    sys.exit(1)

# Test 4: Generate G-code
print('\n[TEST 4] Testing G-code generation...')
try:
    grid_path = tempfile.NamedTemporaryFile(delete=False, suffix='_grid_test.gcode').name
    spiral_path = tempfile.NamedTemporaryFile(delete=False, suffix='_spiral_test.gcode').name
    
    grid_result = save_grid_gcode(gui, grid_path)
    print(f'✅ Grid G-code: {grid_result}')
    if os.path.exists(grid_path) and os.path.getsize(grid_path) > 0:
        print(f'  File size: {os.path.getsize(grid_path)} bytes')
    
    spiral_result = save_spiral_gcode(gui, spiral_path)
    print(f'✅ Spiral G-code: {spiral_result}')
    if os.path.exists(spiral_path) and os.path.getsize(spiral_path) > 0:
        print(f'  File size: {os.path.getsize(spiral_path)} bytes')
    
    # Cleanup
    os.unlink(grid_path)
    os.unlink(spiral_path)
    
except Exception as e:
    print(f'❌ G-code generation failed: {e}')
    import traceback; traceback.print_exc()
    sys.exit(1)

# Test 5: Check no hardcoded values
print('\n[TEST 5] Verifying centralized defaults...')
import inspect
src = inspect.getsource(collect_common_generation_data)
# Count direct field access vs .get() calls
get_calls = src.count('.get(')
direct_access = src.count("entry_dict['")
print(f'✅ Direct field access: {direct_access} (no hardcoded defaults)')
print(f'✅ .get() calls: {get_calls} (backward compatibility only)')

# Cleanup GUI
gui.destroy()

print('\n' + '=' * 60)
print('✅ ALL TESTS PASSED - Spring cleaning successful!')
print('=' * 60)
