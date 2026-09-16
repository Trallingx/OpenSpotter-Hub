"""Built-in grid plugin and legacy registry entry point."""

from .manifest import PLUGIN_MANIFEST
from .plugin import GRID_WORKSPACE, GridJobSnapshot, GridPlugin, register
from .workflow import WORKFLOW_CONTRIBUTION

__all__ = [
    "GRID_WORKSPACE",
    "GridJobSnapshot",
    "GridPlugin",
    "PLUGIN_MANIFEST",
    "WORKFLOW_CONTRIBUTION",
    "register",
]
