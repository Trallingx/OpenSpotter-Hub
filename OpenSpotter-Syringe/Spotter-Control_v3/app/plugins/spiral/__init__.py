"""Built-in spiral plugin and compatibility exports.

Historically ``app.plugins.spiral`` was a single module. It is now a package,
but the geometry class and helpers remain importable from the same path.
"""

from .manifest import PLUGIN_MANIFEST
from .plugin import (
    SPIRAL_WORKSPACE,
    SpiralJobSnapshot,
    SpiralPlugin,
    _as_bool,
    _interleave_point_sets,
    _spiral_points,
    register,
)
from .workflow import WORKFLOW_CONTRIBUTION

__all__ = [
    "PLUGIN_MANIFEST",
    "SPIRAL_WORKSPACE",
    "SpiralJobSnapshot",
    "SpiralPlugin",
    "WORKFLOW_CONTRIBUTION",
    "_as_bool",
    "_interleave_point_sets",
    "_spiral_points",
    "register",
]
