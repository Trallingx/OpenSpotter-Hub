"""Immutable, recursively merged Moonraker state snapshots."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional


def deep_merge(target: dict[str, Any], update: Mapping[str, Any]) -> None:
    """Recursively merge a Moonraker status delta into mutable storage."""
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        elif isinstance(value, Mapping):
            target[key] = copy.deepcopy(dict(value))
        else:
            target[key] = copy.deepcopy(value)


def deep_freeze(value: Any) -> Any:
    """Return an immutable recursive representation suitable for UI readers."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class MachineState:
    """One immutable view of merged Moonraker printer objects."""

    revision: int
    updated_at: float
    connection_state: str
    connection_attempt: int
    last_error: Optional[str]
    objects: Mapping[str, Any]

    @property
    def connected(self) -> bool:
        return self.connection_state == "connected"

    @property
    def klippy_state(self) -> str:
        webhooks = self.objects.get("webhooks", {})
        if isinstance(webhooks, Mapping):
            return str(webhooks.get("state", "unknown"))
        return "unknown"


class StateStore:
    """Thread-safe mutable store that only exposes immutable snapshots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._revision = 0
        self._updated_at = time.time()
        self._connection_state = "stopped"
        self._connection_attempt = 0
        self._last_error: Optional[str] = None
        self._objects: dict[str, Any] = {}

    def snapshot(self) -> MachineState:
        with self._lock:
            return self._snapshot_locked()

    def set_connection(
        self,
        connection_state: str,
        *,
        attempt: Optional[int] = None,
        error: Optional[str] = None,
    ) -> MachineState:
        with self._lock:
            self._connection_state = str(connection_state)
            if attempt is not None:
                self._connection_attempt = int(attempt)
            self._last_error = None if error is None else str(error)
            self._touch_locked()
            return self._snapshot_locked()

    def merge_status(self, status: Mapping[str, Any]) -> MachineState:
        with self._lock:
            deep_merge(self._objects, status)
            self._touch_locked()
            return self._snapshot_locked()

    def _touch_locked(self) -> None:
        self._revision += 1
        self._updated_at = time.time()

    def _snapshot_locked(self) -> MachineState:
        return MachineState(
            revision=self._revision,
            updated_at=self._updated_at,
            connection_state=self._connection_state,
            connection_attempt=self._connection_attempt,
            last_error=self._last_error,
            objects=deep_freeze(self._objects),
        )
