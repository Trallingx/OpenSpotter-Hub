"""
Grid model
Represents a single droplet grid definition for rendering and control.
"""

from dataclasses import dataclass, field


@dataclass
class GridConfig:
    name: str
    valve_id: int = 0
    active: bool = True
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"name": self.name, "valve_id": self.valve_id, "active": self.active}
        d.update(self.config)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GridConfig":
        name = data.get("name", "Grid")
        valve_id = data.get("valve_id", 0)
        active = bool(data.get("active", True))
        config = {k: v for k, v in data.items() if k not in ("name", "valve_id", "active")}
        return cls(name=name, valve_id=valve_id, active=active, config=config)
