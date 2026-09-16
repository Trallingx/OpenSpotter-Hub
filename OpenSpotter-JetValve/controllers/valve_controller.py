"""
Valve Controller
Handles valve-specific control logic and firing.
"""

from typing import Optional, List
from models import Valve


class ValveController:
    """
    Controller for valve management.
    Handles valve registration, pulse timing, and valve state.
    """

    def __init__(self):
        """Initialize valve controller."""
        self.valves: List[Valve] = []

    def register_valve(self, valve: Valve) -> None:
        """Register a valve for control."""
        if not any(v.id == valve.id for v in self.valves):
            self.valves.append(valve)

    def enable_valve(self, valve_id: int) -> bool:
        """Enable a valve."""
        valve = self._get_valve(valve_id)
        if valve is None:
            return False
        valve.is_active = True
        return True

    def disable_valve(self, valve_id: int) -> bool:
        """Disable a valve."""
        valve = self._get_valve(valve_id)
        if valve is None:
            return False
        valve.is_active = False
        return True

    def fire_valve(self, valve_id: int, duration_ms: float = None) -> bool:
        """
        Fire a specific valve.

        Args:
            valve_id: Valve ID
            duration_ms: Optional override duration

        Returns:
            True if successful, False if valve not found
        """
        valve = self._get_valve(valve_id)
        if valve is None:
            return False

        valve.fire(duration_ms)
        return True

    def _get_valve(self, valve_id: int) -> Optional[Valve]:
        """Internal helper to get valve by ID."""
        for valve in self.valves:
            if valve.id == valve_id:
                return valve
        return None

    def __repr__(self):
        return f"ValveController(valves={len(self.valves)})"
