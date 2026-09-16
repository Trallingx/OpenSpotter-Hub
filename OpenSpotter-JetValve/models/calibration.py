"""
Calibration Model
Stores per-valve and per-spot calibration offsets.

TODO: Reintroduce a calibration manager when the calibration workflow is
ready again.
"""

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class CalibrationOffset:
    """
    Represents a calibration offset for a specific valve at a specific spot.
    """

    valve_id: int  # 0-7
    spot_id: int  # Unique spot identifier
    offset_x_um: float = 0.0  # X offset in micrometers
    offset_y_um: float = 0.0  # Y offset in micrometers
    timestamp: datetime = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def __repr__(self):
        return (
            f"CalibrationOffset(valve={self.valve_id}, spot={self.spot_id}, "
            f"offset_x={self.offset_x_um:.1f}µm, offset_y={self.offset_y_um:.1f}µm)"
        )
