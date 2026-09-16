"""
PrintJob Model
Represents a print job with tracking for lines printed and planned.

TODO: Reattach calibration workflow support when the calibration manager
is implemented again.
"""

from dataclasses import dataclass, field
from typing import List, Dict

from .valves import Valve


@dataclass
class PrintJob:
    """
    Represents a complete print job.
    Tracks progress and valve configuration.
    """

    job_id: str = "job_001"
    num_lines: int = 100  # Total lines to print
    valves: List[Valve] = field(default_factory=list)  # List of valve objects
    current_line: int = 0  # Progress: current line being processed
    mode: str = "buildplate"  # "buildplate" or "roll-to-roll"

    @property
    def progress_percent(self) -> float:
        """Calculate progress as percentage (0-100)."""
        if self.num_lines == 0:
            return 0.0
        return (self.current_line / self.num_lines) * 100.0

    @property
    def lines_remaining(self) -> int:
        """Calculate lines remaining to print."""
        return max(0, self.num_lines - self.current_line)

    def advance_line(self) -> bool:
        """
        Advance to the next line.

        Returns:
            True if advanced successfully, False if already at end
        """
        if self.current_line < self.num_lines:
            self.current_line += 1
            return True
        return False

    def get_valve(self, valve_id: int) -> Valve:
        """Get valve by ID."""
        for valve in self.valves:
            if valve.id == valve_id:
                return valve
        raise ValueError(f"Valve {valve_id} not found in print job")

    def add_valve(self, valve: Valve) -> None:
        """Add a valve to the print job."""
        if not any(v.id == valve.id for v in self.valves):
            self.valves.append(valve)

    def reset_progress(self) -> None:
        """Reset progress counters."""
        self.current_line = 0
        for valve in self.valves:
            valve.reset_counters()

    def is_complete(self) -> bool:
        """Check if print job is complete."""
        return self.current_line >= self.num_lines

    def set_mode(self, mode: str) -> None:
        """
        Set print mode.

        Args:
            mode: "buildplate" or "roll-to-roll"
        """
        if mode not in ("buildplate", "roll-to-roll"):
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode

    def get_summary(self) -> Dict:
        """Get summary of print job status."""
        return {
            "job_id": self.job_id,
            "total_lines": self.num_lines,
            "current_line": self.current_line,
            "progress_percent": self.progress_percent,
            "lines_remaining": self.lines_remaining,
            "num_valves": len(self.valves),
            "mode": self.mode,
            "is_complete": self.is_complete(),
        }

    def __repr__(self):
        return (
            f"PrintJob(id={self.job_id}, progress={self.current_line}/{self.num_lines} "
            f"({self.progress_percent:.1f}%), valves={len(self.valves)}, "
            f"mode={self.mode})"
        )
