"""
Gantry Model
Represents the CNC gantry position, velocity, and motion limits.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Point3D:
    """3D coordinate point in mm."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __iter__(self):
        """Allow unpacking: x, y, z = point"""
        return iter([self.x, self.y, self.z])

    def __repr__(self):
        return f"Point3D(x={self.x:.2f}, y={self.y:.2f}, z={self.z:.2f})"


class Gantry:
    """
    Represents the CNC gantry system.
    Tracks current position, velocity, and motion limits.
    """

    def __init__(
        self,
        max_position: Point3D = None,
        min_position: Point3D = None,
    ):
        """
        Initialize gantry.

        Args:
            max_position: Maximum position limits (mm)
            min_position: Minimum position limits (mm)
        """
        self.position = Point3D(0.0, 0.0, 0.0)
        self.velocity = 0.0  # mm/s
        self.max_position = max_position or Point3D(200.0, 200.0, 10.0)
        self.min_position = min_position or Point3D(0.0, 0.0, 0.0)
        self.is_moving = False

    def set_position(self, x: float, y: float, z: float) -> None:
        """Update gantry position."""
        self.position = Point3D(x, y, z)

    def set_velocity(self, velocity: float) -> None:
        """Set motion velocity in mm/s."""
        self.velocity = max(0.0, velocity)

    def is_within_limits(self, point: Point3D) -> bool:
        """Check if point is within gantry limits."""
        return (
            self.min_position.x <= point.x <= self.max_position.x
            and self.min_position.y <= point.y <= self.max_position.y
            and self.min_position.z <= point.z <= self.max_position.z
        )

    def __repr__(self):
        return (
            f"Gantry(pos={self.position}, vel={self.velocity:.2f}mm/s, "
            f"moving={self.is_moving})"
        )
