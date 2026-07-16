"""
Plugin registry and loader for OpenSpotter-Syringe.

Pattern Generator Plugins:
Plugins extend pattern generation beyond simple grids. Add new plugins by:
1. Create a new module in this directory (e.g., plugins/hexagon.py)
2. Implement a class with a numeric `plan()` method and `name` attribute
3. Implement a `register()` function that returns the plugin instance
4. Plugin is auto-discovered on next startup

Example plugin structure:
```python
class HexagonPlugin:
    name = 'hexagon'
    
    def plan(self, context):
        # Return numeric point-event dictionaries for the workflow renderer.
        return []

def register():
    return HexagonPlugin()
```

Plugin Context Dictionary (passed to plan()):
- params: field values specific to this plugin instance
- resolution and conversion values required by the geometry

Plugin Return Value:
A sequence of numeric point dictionaries. Machine command text belongs only to
the runtime workflow configuration.
"""
import importlib
import pkgutil
import os
from typing import Dict, Optional

_PLUGINS: Dict[str, object] = {}


def discover_plugins():
    """Auto-discover and register all plugins in the plugins package."""
    pkg_dir = os.path.dirname(__file__)
    for _finder, name, _is_package in pkgutil.iter_modules([pkg_dir]):
        if name.startswith('_'):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception as exc:
            print(f"Warning: failed to load plugin '{name}': {exc}")
            continue
        if hasattr(mod, 'register'):
            try:
                plugin = mod.register()
                plugin_name = getattr(plugin, 'name', None) or getattr(mod, 'name', None) or name
                _PLUGINS[plugin_name] = plugin
                print(f"Loaded plugin: {plugin_name}")
            except Exception as exc:
                print(f"Warning: failed to register plugin '{name}': {exc}")
                continue


def get_plugin(name: str) -> Optional[object]:
    """Get a registered plugin by name. Returns None if not found."""
    return _PLUGINS.get(name)

