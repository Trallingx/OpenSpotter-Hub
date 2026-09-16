"""Pure preview-scene objects.

Pattern plugins describe their geometry with these immutable objects.  They do
not import Tkinter or draw directly on a canvas.  This keeps planning reusable
for validation, tests, future renderers, and the desktop preview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional, Tuple


Point = Tuple[float, float]


@dataclass(frozen=True)
class CanvasPreviewStyle:
    """Renderer colors supplied to plugin preview builders.

    Plugins describe geometry, while the application shell remains the owner
    of its visual theme. Passing the small palette needed by pattern previews
    avoids importing Tk-specific theme modules from numeric plugin code.
    """

    maintenance_primary: str
    maintenance_secondary: str
    maintenance_primary_outline: str
    maintenance_secondary_outline: str
    washing_line: str


@dataclass(frozen=True)
class CanvasPreviewContext:
    """Read-only application values needed to build a pattern preview."""

    global_values: Mapping[str, Any]
    config_dir: Path
    workflow_source: Any
    style: CanvasPreviewStyle

    def __post_init__(self) -> None:
        """Detach global inputs so one plugin cannot affect another's preview."""

        object.__setattr__(
            self,
            "global_values",
            MappingProxyType(dict(self.global_values)),
        )


@dataclass(frozen=True)
class PreviewBounds:
    """Axis-aligned machine-coordinate boundary used for safety previews."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def contains(self, point: Point, *, tolerance: float = 1e-9) -> bool:
        """Return whether ``point`` falls inside the boundary."""
        x, y = point
        return (
            self.x_min - tolerance <= x <= self.x_max + tolerance
            and self.y_min - tolerance <= y <= self.y_max + tolerance
        )


@dataclass(frozen=True)
class MarkerPrimitive:
    """One spot or maintenance marker in machine coordinates."""

    x: float
    y: float
    color: str
    shape: str = "circle"
    volume_ul: Optional[float] = None
    size_mm: float = 0.16
    outline: Optional[str] = None
    minimum_pixels: int = 1
    z_index: int = 20
    safety_relevant: bool = True

    @property
    def point(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class PolylinePrimitive:
    """A connected path, optionally with volume-scaled markers at its points."""

    points: Tuple[Point, ...]
    color: str
    width: int = 2
    show_markers: bool = False
    marker_volume_ul: Optional[float] = None
    outline: Optional[str] = None
    marker_minimum_pixels: int = 1
    z_index: int = 20
    safety_relevant: bool = True


@dataclass(frozen=True)
class LinePrimitive:
    """A standalone line such as a washing stroke."""

    start: Point
    end: Point
    color: str
    width: int = 3
    dash: Tuple[int, ...] = ()
    z_index: int = 20
    safety_relevant: bool = True


@dataclass(frozen=True)
class CanvasPreview:
    """Complete plugin-owned preview layer.

    ``safety_points`` may include points that are not visibly marked but still
    need to participate in acceptance-boundary checks.
    """

    markers: Tuple[MarkerPrimitive, ...] = ()
    polylines: Tuple[PolylinePrimitive, ...] = ()
    lines: Tuple[LinePrimitive, ...] = ()
    safety_points: Tuple[Point, ...] = ()
    warnings: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        """Detach metadata and make its top-level mapping read-only."""

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    @classmethod
    def empty(cls) -> "CanvasPreview":
        return cls()

    def all_points(self) -> Tuple[Point, ...]:
        """Return every coordinate needed to fit the rendered scene."""
        points = list(self.safety_points)
        points.extend(marker.point for marker in self.markers)
        for polyline in self.polylines:
            points.extend(polyline.points)
        for line in self.lines:
            points.extend((line.start, line.end))
        return tuple(points)

    def safety_check_points(self) -> Tuple[Point, ...]:
        """Return only coordinates that belong inside the acceptance area."""
        points = list(self.safety_points)
        points.extend(
            marker.point
            for marker in self.markers
            if marker.safety_relevant
        )
        for polyline in self.polylines:
            if polyline.safety_relevant:
                points.extend(polyline.points)
        for line in self.lines:
            if line.safety_relevant:
                points.extend((line.start, line.end))
        return tuple(points)

    def extends_outside(self, bounds: PreviewBounds) -> bool:
        """Return whether any plugin coordinate exceeds ``bounds``."""
        return any(
            not bounds.contains(point)
            for point in self.safety_check_points()
        )

    @staticmethod
    def combine(previews: Iterable["CanvasPreview"]) -> "CanvasPreview":
        """Merge plugin layers without losing their warnings or metadata."""
        markers = []
        polylines = []
        lines = []
        safety_points = []
        warnings = []
        metadata = {}
        for preview in previews:
            markers.extend(preview.markers)
            polylines.extend(preview.polylines)
            lines.extend(preview.lines)
            safety_points.extend(preview.safety_points)
            warnings.extend(preview.warnings)
            metadata.update(preview.metadata)
        return CanvasPreview(
            markers=tuple(markers),
            polylines=tuple(polylines),
            lines=tuple(lines),
            safety_points=tuple(safety_points),
            warnings=tuple(warnings),
            metadata=metadata,
        )
