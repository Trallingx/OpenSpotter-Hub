"""Optional capabilities implemented by plugins that support live previews."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import CanvasPreview, CanvasPreviewContext


@runtime_checkable
class CanvasPreviewProvider(Protocol):
    """Pattern plugin capable of describing renderer-neutral live geometry."""

    def build_canvas_preview(
        self,
        gui: Any,
        context: CanvasPreviewContext,
    ) -> CanvasPreview:
        """Build the combined preview for this plugin's active editors."""


__all__ = ["CanvasPreviewProvider"]
