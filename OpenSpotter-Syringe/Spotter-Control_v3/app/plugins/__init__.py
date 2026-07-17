"""Compatibility facade for OpenSpotter pattern plugin discovery.

New infrastructure lives in :mod:`app.core.plugins`. Existing callers can keep
using ``discover_plugins`` and ``get_plugin`` while built-in and installed
plugins receive the same validation and duplicate protection.
"""

from typing import Optional

from ..core.plugins import (
    API_VERSION,
    ENTRY_POINT_GROUP,
    DuplicatePluginError,
    PatternPlugin,
    PluginCompatibilityError,
    PluginError,
    PluginLoadError,
    PluginManifest,
    PluginManifestError,
    PluginRegistry,
)
from ..runtime_logging import get_logger, log_options


logger = get_logger("plugins")
_REGISTRY = PluginRegistry()

# Kept as a compatibility alias for code that inspected the former module-level
# mapping. New code should use get_registry().plugins.
_PLUGINS = _REGISTRY._plugins


def _log_discovery_error(error: PluginError) -> None:
    logger.error("plugin.discovery_failed | error=%s", error)


def discover_plugins(include_external: bool = True) -> None:
    """Discover built-ins and, optionally, installed entry-point plugins.

    Discovery is safe to call repeatedly. A source that registered successfully
    is not imported or constructed again.
    """

    loaded_ids = list(
        _REGISTRY.discover_builtins(__name__, on_error=_log_discovery_error)
    )
    if include_external:
        loaded_ids.extend(
            _REGISTRY.load_entry_points(on_error=_log_discovery_error)
        )

    for plugin_id in loaded_ids:
        plugin = _REGISTRY.require(plugin_id)
        log_options(
            logger,
            "plugin.loaded",
            plugin_name=plugin_id,
            implementation=type(plugin).__name__,
        )


def get_plugin(name: str) -> Optional[object]:
    """Get a registered plugin by name. Returns ``None`` if it is unknown."""

    return _REGISTRY.get(name)


def get_registry() -> PluginRegistry:
    """Return the process-wide compatibility registry."""

    return _REGISTRY


__all__ = [
    "API_VERSION",
    "ENTRY_POINT_GROUP",
    "DuplicatePluginError",
    "PatternPlugin",
    "PluginCompatibilityError",
    "PluginError",
    "PluginLoadError",
    "PluginManifest",
    "PluginManifestError",
    "PluginRegistry",
    "discover_plugins",
    "get_plugin",
    "get_registry",
]

