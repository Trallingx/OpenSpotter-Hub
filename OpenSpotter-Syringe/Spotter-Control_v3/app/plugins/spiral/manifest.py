"""Manifest for the built-in spiral plugin."""

from ...core.plugins import API_VERSION, PluginManifest


PLUGIN_MANIFEST = PluginManifest(
    id="spiral",
    display_name="Spiral",
    version="1.0.0",
    api_version=API_VERSION,
    description="Archimedean spiral pattern planner.",
    capabilities=("numeric-plan", "editor", "generation", "preview"),
)


__all__ = ["PLUGIN_MANIFEST"]
