"""Application composition helpers for registered pattern plugins.

The core registry intentionally does not import built-ins.  This module is the
desktop application's composition boundary: it performs discovery and selects
plugins that implement the richer workspace contract.
"""

from __future__ import annotations

from typing import Tuple

from .core.application_patterns import ApplicationPatternPlugin
from .plugins import discover_plugins, get_registry


def application_plugins(
    *,
    include_external: bool = True,
) -> Tuple[ApplicationPatternPlugin, ...]:
    """Discover and return plugins that can participate in the desktop shell."""

    discover_plugins(include_external=include_external)
    return tuple(
        plugin
        for plugin in get_registry().values()
        if isinstance(plugin, ApplicationPatternPlugin)
    )


def require_application_plugin(plugin_id: str) -> ApplicationPatternPlugin:
    """Return one desktop-capable plugin or raise an actionable error."""

    for plugin in application_plugins():
        if plugin.manifest.id == plugin_id:
            return plugin
    raise KeyError(
        "No desktop-capable pattern plugin is registered as {!r}".format(
            plugin_id
        )
    )


__all__ = ["application_plugins", "require_application_plugin"]
