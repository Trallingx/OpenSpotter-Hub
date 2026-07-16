"""Thread-safe events and a small Tk ``after`` bridge."""

from __future__ import annotations

from collections import deque
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple


@dataclass(frozen=True)
class RuntimeEvent:
    """One immutable runtime-to-UI event."""

    kind: str
    payload: Any
    created_at: float

    @classmethod
    def create(cls, kind: str, payload: Any = None) -> "RuntimeEvent":
        return cls(kind=str(kind), payload=payload, created_at=time.time())


class RuntimeEventQueue:
    """Bounded queue with state coalescing and protected control events."""

    DEFAULT_COALESCED_KINDS = frozenset({"state"})
    DEFAULT_CRITICAL_KINDS = frozenset(
        {
            "command_error",
            "command_outcome_unknown",
            "disconnected",
            "emergency_result",
            "stopped",
            "upload_error",
        }
    )

    def __init__(
        self,
        maxsize: int = 2000,
        *,
        coalesced_kinds=None,
        critical_kinds=None,
    ) -> None:
        self._maxsize = max(1, int(maxsize))
        self._queue = deque()
        self._coalesced = {}
        self._coalesced_kinds = frozenset(
            coalesced_kinds or self.DEFAULT_COALESCED_KINDS
        )
        self._critical_kinds = frozenset(
            critical_kinds or self.DEFAULT_CRITICAL_KINDS
        )
        self._dropped = 0
        self._coalesced_count = 0
        self._lock = threading.Lock()

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def coalesced_count(self) -> int:
        with self._lock:
            return self._coalesced_count

    def publish(self, event: RuntimeEvent) -> None:
        with self._lock:
            if event.kind in self._coalesced_kinds:
                if event.kind in self._coalesced:
                    self._coalesced_count += 1
                self._coalesced[event.kind] = event
                return

            if len(self._queue) >= self._maxsize:
                removable_index = next(
                    (
                        index
                        for index, queued in enumerate(self._queue)
                        if queued.kind not in self._critical_kinds
                    ),
                    None,
                )
                if removable_index is None:
                    if event.kind not in self._critical_kinds:
                        self._dropped += 1
                        return
                    self._queue.popleft()
                    self._dropped += 1
                else:
                    del self._queue[removable_index]
                    self._dropped += 1
            self._queue.append(event)

    def drain(self, limit: Optional[int] = None) -> Tuple[RuntimeEvent, ...]:
        maximum = None if limit is None else max(0, int(limit))
        with self._lock:
            events = []
            while self._queue and (maximum is None or len(events) < maximum):
                events.append(self._queue.popleft())
            if maximum is None or len(events) < maximum:
                for kind in tuple(self._coalesced):
                    if maximum is not None and len(events) >= maximum:
                        break
                    events.append(self._coalesced.pop(kind))
            return tuple(events)


class TkEventBridge:
    """Drain local runtime events through Tk's ``after`` scheduler.

    The bridge performs no network work. ``start`` and ``stop`` should be called
    from the Tk thread, and the callback receives a tuple of events per tick.
    """

    def __init__(
        self,
        root: Any,
        events: RuntimeEventQueue,
        callback: Callable[[Tuple[RuntimeEvent, ...]], None],
        *,
        interval_ms: int = 50,
        batch_limit: int = 200,
    ) -> None:
        self.root = root
        self.events = events
        self.callback = callback
        self.interval_ms = max(1, int(interval_ms))
        self.batch_limit = max(1, int(batch_limit))
        self._after_id = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> "TkEventBridge":
        if not self._running:
            self._running = True
            self._schedule()
        return self

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def pump_once(self) -> Tuple[RuntimeEvent, ...]:
        batch = self.events.drain(self.batch_limit)
        if batch:
            self.callback(batch)
        return batch

    def _schedule(self) -> None:
        if self._running:
            self._after_id = self.root.after(self.interval_ms, self._tick)

    def _tick(self) -> None:
        self._after_id = None
        if not self._running:
            return
        try:
            self.pump_once()
        finally:
            self._schedule()
