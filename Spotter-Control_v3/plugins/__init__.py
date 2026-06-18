"""
Plugin registry and loader for UniSpotter_v3.

Pattern Generator Plugins:
Plugins extend pattern generation beyond simple grids. Add new plugins by:
1. Create a new module in this directory (e.g., plugins/hexagon.py)
2. Implement a class with a `generate()` method and `name` attribute
3. Implement a `register()` function that returns the plugin instance
4. Plugin is auto-discovered on next startup

Example plugin structure:
```python
class HexagonPlugin:
    name = 'hexagon'
    
    def generate(self, file, settings_snapshot, context):
        # Write G-code to file
        # Return dict with metadata
        pass

def register():
    return HexagonPlugin()
```

Plugin Context Dictionary (passed to generate()):
- params: field values specific to this plugin instance
- speed: movement speed (mm/s)
- dispensing_speed: dispensing speed (mm/min)
- z_high, z_low: Z-height values
- helpers: dict of utility functions (volume_to_mm, etc.)

Plugin Return Value:
Dict with execution metadata:
- total_dispense_uL: total volume dispensed
- spots_count: number of dispensing points
- Additional keys: plugin-specific metadata
"""
import importlib
import pkgutil
import os
from typing import Dict, Optional, List

_PLUGINS: Dict[str, object] = {}


def discover_plugins():
    """Auto-discover and register all plugins in the plugins package."""
    pkg_dir = os.path.dirname(__file__)
    for finder, name, ispkg in pkgutil.iter_modules([pkg_dir]):
        if name.startswith('_'):
            continue
        try:
            mod = importlib.import_module(f"plugins.{name}")
        except Exception as e:
            print(f"⚠️ Failed to load plugin '{name}': {e}")
            continue
        if hasattr(mod, 'register'):
            try:
                plugin = mod.register()
                plugin_name = getattr(plugin, 'name', None) or getattr(mod, 'name', None) or name
                _PLUGINS[plugin_name] = plugin
                print(f"✅ Loaded plugin: {plugin_name}")
            except Exception as e:
                print(f"⚠️ Failed to register plugin '{name}': {e}")
                continue


def get_plugin(name: str) -> Optional[object]:
    """Get a registered plugin by name. Returns None if not found."""
    return _PLUGINS.get(name)


def list_plugins() -> List[str]:
    """List all registered plugin names."""
    return list(_PLUGINS.keys())


def register_plugin(name: str, plugin_obj: object):
    """Manually register a plugin (useful for testing or runtime plugins)."""
    _PLUGINS[name] = plugin_obj
    print(f"✅ Registered plugin: {name}")


def get_available_plugin_types() -> Dict[str, str]:
    """
    Get a dict of plugin names for UI display.
    
    Useful for populating dropdown menus or comboboxes.
    Returns: {'spiral': 'Spiral Pattern', 'hexagon': 'Hexagon Pattern', ...}
    
    For now, returns plugin names. In future, could return display labels from metadata.
    """
    if not _PLUGINS:
        discover_plugins()
    return {name: name.capitalize() for name in _PLUGINS.keys()}

