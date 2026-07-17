"""Compatibility exports for the built-in grid editor and form builder.

The editor now lives in :mod:`app.plugins.grid.editor`, while the reusable
schema-driven form builder lives in :mod:`app.core.ui.forms`. Existing imports
remain available so downstream integrations do not need to change during the
plugin migration.
"""

from .core.ui.forms import create_labels
from .plugins.grid.editor import Grid

__all__ = ["Grid", "create_labels"]
