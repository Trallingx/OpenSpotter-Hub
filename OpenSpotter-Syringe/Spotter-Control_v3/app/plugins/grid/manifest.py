"""Manifest for the built-in rectangular-grid plugin."""

from ...core.plugins import API_VERSION, PluginManifest


PLUGIN_MANIFEST = PluginManifest(
    id="grid",
    display_name="Grid",
    version="1.0.0",
    api_version=API_VERSION,
    description="Rectangular spot arrays with cleaning and washing support.",
    capabilities=("numeric-plan", "editor", "generation", "preview"),
)


__all__ = ["PLUGIN_MANIFEST"]
