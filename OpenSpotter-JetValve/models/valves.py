"""
Valve Model
Represents a single liquid dispensing valve configured through the macro layer.
"""


from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any



@dataclass
class Valve:
    id: int  # 0-7 (valve index)
    config: Dict[str, Any] = field(default_factory=dict)
    lines_printed: int = 0  # Count of lines printed
    lines_planned: List[Tuple[float, float]] = field(default_factory=list)

    def fire(self, duration_ms: float = None) -> None:
        if not self.config.get("is_active", True):
            return
        # Hardware firing is routed through the configured macro services.
        pass


    def add_planned_line(self, x: float, y: float) -> None:
        self.lines_planned.append((x, y))


    def clear_planned_lines(self) -> None:
        self.lines_planned.clear()


    def increment_printed(self) -> None:
        self.lines_printed += 1


    def reset_counters(self) -> None:
        self.lines_printed = 0
        self.lines_planned.clear()


    def __repr__(self):
        return f"Valve(id={self.id}, config={self.config}, lines_printed={self.lines_printed})"

    def to_dict(self) -> dict:
        d = {"id": self.id}
        d.update(self.config)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Valve":
        id = data.get("id", 0)
        config = {k: v for k, v in data.items() if k != "id"}
        return cls(id=id, config=config)
