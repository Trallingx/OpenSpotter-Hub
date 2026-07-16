"""Pattern-independent liquid-handling domain helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping


@dataclass(frozen=True)
class Container:
    """One configured loading or emptying location in machine coordinates."""

    x: float
    y: float
    z_filling_height: float


def volume_to_mm(
    volume_ul: float,
    millimeters_per_microliter: float,
) -> float:
    """Convert a liquid volume to syringe-plunger travel."""

    factor = float(millimeters_per_microliter)
    if factor <= 0:
        raise ValueError("millimeters_per_microliter must be positive")
    return float(volume_ul) * factor


def build_containers(
    values: Mapping[str, Any],
    *,
    count: int = 6,
) -> Dict[int, Container]:
    """Build configured container locations from global field values."""

    containers = {}
    for index in range(1, max(0, int(count)) + 1):
        try:
            x = float(values.get("container{}_x".format(index), 0.0))
            y = float(values.get("container{}_y".format(index), 0.0))
            z = float(values.get("container{}_z".format(index), 0.0))
        except (TypeError, ValueError):
            x = y = z = 0.0
        containers[index] = Container(
            x=x,
            y=y,
            z_filling_height=z,
        )
    return containers


__all__ = ["Container", "build_containers", "volume_to_mm"]
