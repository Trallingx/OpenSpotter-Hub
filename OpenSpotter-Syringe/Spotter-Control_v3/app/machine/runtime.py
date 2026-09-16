"""Non-blocking Moonraker runtime core for the Tk desktop application."""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import hashlib
import ipaddress
import json
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable, Mapping, Optional, Union

import aiohttp

from ..runtime_logging import get_logger
from .config import MoonrakerConfig
from .events import RuntimeEvent, RuntimeEventQueue, TkEventBridge
from .state import MachineState, StateStore, deep_freeze


class MoonrakerError(RuntimeError):
    """Base class for runtime failures."""


class MoonrakerNotStartedError(MoonrakerError):
    pass


class MoonrakerQueueFullError(MoonrakerError):
    pass


class MoonrakerDisconnectedError(MoonrakerError):
    pass


class MoonrakerCommandOutcomeUnknown(MoonrakerError):
    """A sent request lost confirmation; retrying may duplicate an action."""

    def __init__(
        self,
        method: str,
        request_id: int,
        timing: "CommandTiming",
        reason: str,
    ) -> None:
        super().__init__(
            f"{method} {reason}; the printer-side outcome is unknown"
        )
        self.method = method
        self.request_id = int(request_id)
        self.timing = timing
        self.outcome_unknown = True


class MoonrakerRequestTimeout(MoonrakerCommandOutcomeUnknown):
    def __init__(
        self,
        method: str,
        request_id: int,
        timing: "CommandTiming",
    ) -> None:
        super().__init__(
            method,
            request_id,
            timing,
            f"response timed out after {timing.response_ms:.0f} ms",
        )


class MoonrakerPreflightError(MoonrakerError):
    pass


class MoonrakerPrintQueuedError(MoonrakerError):
    def __init__(self, payload: Any) -> None:
        super().__init__(
            "Moonraker queued the uploaded print instead of starting it; "
            "later motion may still be scheduled"
        )
        self.payload = payload


class MoonrakerHTTPError(MoonrakerError):
    def __init__(self, status: int, message: str, payload: Any = None) -> None:
        super().__init__(f"Moonraker HTTP {status}: {message}")
        self.status = int(status)
        self.payload = payload


class MoonrakerRPCError(MoonrakerError):
    def __init__(
        self,
        method: str,
        code: Any,
        message: str,
        *,
        data: Any = None,
        timing: Optional["CommandTiming"] = None,
    ) -> None:
        super().__init__(f"{method} failed ({code}): {message}")
        self.method = method
        self.code = code
        self.data = data
        self.timing = timing


@dataclass(frozen=True)
class CommandTiming:
    request_id: int
    method: str
    queued_at: float
    sent_at: float
    received_at: float
    queue_ms: float
    response_ms: float
    total_ms: float
    success: bool
    error: Optional[str] = None


@dataclass(frozen=True)
class CommandResult:
    request_id: int
    method: str
    result: Any
    timing: CommandTiming


@dataclass(frozen=True)
class ConsoleEntry:
    created_at: float
    text: str
    source: str = "gcode"
    level: str = "info"
    sequence: int = 0


@dataclass(frozen=True)
class UploadResult:
    remote_name: str
    size: int
    checksum: Optional[str]
    response: Any
    print_started: bool
    print_queued: bool
    elapsed_ms: float

    @property
    def started(self) -> bool:
        return self.print_started


@dataclass(frozen=True)
class EmergencyResult:
    response: Any
    elapsed_ms: float


@dataclass
class _RequestEnvelope:
    method: str
    params: dict[str, Any]
    priority: int
    sequence: int
    queued_at: float
    queued_monotonic: float
    timeout: float
    future: "concurrent.futures.Future[CommandResult]"


@dataclass
class _PendingRequest:
    request_id: int
    method: str
    queued_at: float
    queued_monotonic: float
    sent_at: float
    sent_monotonic: float
    destination: Any
    timeout_handle: Optional[asyncio.Handle]
    outcome_may_change_machine: bool


class MoonrakerRuntime:
    """Own a single asyncio thread, HTTP session, and persistent WebSocket.

    Public methods are safe to call from Tk callbacks. Network work is queued to
    the background loop and returned as ``concurrent.futures.Future`` objects.
    """

    PRIORITY_EMERGENCY = -100
    PRIORITY_CONTROL = 0
    PRIORITY_NORMAL = 100
    PRIORITY_BACKGROUND = 200

    def __init__(
        self,
        config: MoonrakerConfig,
        *,
        session_factory: Optional[Callable[..., Any]] = None,
        reconnect_sleep: Optional[Callable[[float], Awaitable[None]]] = None,
    ) -> None:
        self.config = config
        self.events = RuntimeEventQueue(config.event_queue_limit)
        self._state = StateStore()
        self._console = deque(maxlen=config.console_limit)
        self._timings = deque(maxlen=config.timing_limit)
        self._console_sequence = 0
        self._console_lock = threading.RLock()
        self._timing_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._sequence_lock = threading.Lock()
        self._request_sequence = 0
        self._uses_default_session_factory = session_factory is None
        self._session_factory = session_factory or aiohttp.ClientSession
        self._reconnect_sleep = reconnect_sleep or asyncio.sleep
        self._logger = get_logger("machine.moonraker")

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()
        self._request_queue: Optional[asyncio.PriorityQueue] = None
        self._connected_async: Optional[asyncio.Event] = None
        self._shutdown_async: Optional[asyncio.Event] = None
        self._session_ready_async: Optional[asyncio.Event] = None
        self._send_lock: Optional[asyncio.Lock] = None
        self._session: Any = None
        self._ws: Any = None
        self._pending: dict[int, _PendingRequest] = {}
        self._next_request_id = 1
        self._capability_epoch = 0
        self._motion_epoch = 0

    @property
    def started(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    @property
    def connected(self) -> bool:
        return self.state_snapshot().connected

    def start(self) -> "MoonrakerRuntime":
        """Start the background loop without waiting for network connection."""
        with self._lifecycle_lock:
            if self.started:
                return self
            self._loop_ready = threading.Event()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="MoonrakerRuntime",
                daemon=True,
            )
            self._thread.start()

        if not self._loop_ready.wait(timeout=2.0):
            raise MoonrakerError("Moonraker runtime loop did not start")
        return self

    def stop(self, timeout: float = 5.0) -> bool:
        """Request shutdown and optionally wait for the runtime thread."""
        with self._lifecycle_lock:
            thread = self._thread
            loop = self._loop
            shutdown = self._shutdown_async
            if not thread:
                return True
            if loop and shutdown:
                loop.call_soon_threadsafe(shutdown.set)

        if thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        stopped = not thread.is_alive()
        if stopped:
            with self._lifecycle_lock:
                self._thread = None
        return stopped

    def request(
        self,
        method: str,
        params: Optional[Mapping[str, Any]] = None,
        priority: int = PRIORITY_NORMAL,
        *,
        timeout: Optional[float] = None,
    ) -> "concurrent.futures.Future[CommandResult]":
        """Queue one JSON-RPC request and return immediately."""
        result_future: "concurrent.futures.Future[CommandResult]" = (
            concurrent.futures.Future()
        )
        loop = self._loop
        if not self.started or loop is None:
            result_future.set_exception(
                MoonrakerNotStartedError("Call start() before queueing requests")
            )
            return result_future
        if not self.connected:
            result_future.set_exception(
                MoonrakerDisconnectedError(
                    "Moonraker is not connected; command was not queued"
                )
            )
            return result_future

        cleaned_method = str(method).strip()
        if not cleaned_method:
            result_future.set_exception(ValueError("JSON-RPC method must not be empty"))
            return result_future

        with self._sequence_lock:
            self._request_sequence += 1
            sequence = self._request_sequence

        envelope = _RequestEnvelope(
            method=cleaned_method,
            params=copy.deepcopy(dict(params or {})),
            priority=int(priority),
            sequence=sequence,
            queued_at=time.time(),
            queued_monotonic=time.monotonic(),
            timeout=float(
                self.config.request_timeout if timeout is None else timeout
            ),
            future=result_future,
        )
        if envelope.timeout <= 0:
            result_future.set_exception(ValueError("request timeout must be positive"))
            return result_future
        loop.call_soon_threadsafe(self._enqueue_request, envelope)
        return result_future

    def send_gcode(
        self,
        script: str,
        *,
        priority: int = PRIORITY_NORMAL,
        timeout: Optional[float] = None,
    ) -> "concurrent.futures.Future[CommandResult]":
        cleaned_script = str(script).strip()
        if not cleaned_script:
            future: "concurrent.futures.Future[CommandResult]" = (
                concurrent.futures.Future()
            )
            future.set_exception(ValueError("G-code script must not be empty"))
            return future
        return self.request(
            "printer.gcode.script",
            {"script": cleaned_script},
            priority,
            timeout=self.config.gcode_timeout if timeout is None else timeout,
        )

    def pause(self) -> "concurrent.futures.Future[CommandResult]":
        return self.request(
            "printer.print.pause",
            priority=self.PRIORITY_CONTROL,
            timeout=self.config.control_timeout,
        )

    def resume(self) -> "concurrent.futures.Future[CommandResult]":
        return self.request(
            "printer.print.resume",
            priority=self.PRIORITY_CONTROL,
            timeout=self.config.control_timeout,
        )

    def cancel(self) -> "concurrent.futures.Future[CommandResult]":
        return self.request(
            "printer.print.cancel",
            priority=self.PRIORITY_CONTROL,
            timeout=self.config.control_timeout,
        )

    def emergency(self) -> "concurrent.futures.Future[EmergencyResult]":
        """Attempt Moonraker's independent HTTP emergency-stop endpoint."""
        loop = self._loop
        if not self.started or loop is None:
            future: "concurrent.futures.Future[EmergencyResult]" = (
                concurrent.futures.Future()
            )
            future.set_exception(
                MoonrakerNotStartedError("Call start() before requesting E-stop")
            )
            return future
        return asyncio.run_coroutine_threadsafe(
            self._emergency_http(),
            loop,
        )

    def start_print(
        self,
        filename: str,
        *,
        priority: int = PRIORITY_CONTROL,
    ) -> "concurrent.futures.Future[CommandResult]":
        try:
            self._validate_print_start_preflight()
        except MoonrakerError as exc:
            future: "concurrent.futures.Future[CommandResult]" = (
                concurrent.futures.Future()
            )
            future.set_exception(exc)
            return future
        return self.request(
            "printer.print.start",
            {"filename": str(filename)},
            priority,
            timeout=self.config.control_timeout,
        )

    def upload_gcode(
        self,
        source: Union[str, Path, bytes, bytearray, memoryview],
        remote_name: Optional[str] = None,
        *,
        checksum: Union[bool, str, None] = True,
        start: bool = False,
    ) -> "concurrent.futures.Future[UploadResult]":
        """Upload G-code over HTTP and optionally start it after upload."""
        loop = self._loop
        if not self.started or loop is None:
            future: "concurrent.futures.Future[UploadResult]" = (
                concurrent.futures.Future()
            )
            future.set_exception(
                MoonrakerNotStartedError("Call start() before uploading G-code")
            )
            return future
        return asyncio.run_coroutine_threadsafe(
            self._upload_gcode(
                source,
                remote_name,
                checksum=checksum,
                start=start,
            ),
            loop,
        )

    def state_snapshot(self) -> MachineState:
        return self._state.snapshot()

    def console_snapshot(self) -> tuple[ConsoleEntry, ...]:
        with self._console_lock:
            return tuple(self._console)

    def timings_snapshot(self) -> tuple[CommandTiming, ...]:
        with self._timing_lock:
            return tuple(self._timings)

    def drain_events(self, limit: Optional[int] = None) -> tuple[RuntimeEvent, ...]:
        return self.events.drain(limit)

    def tk_bridge(
        self,
        root: Any,
        callback: Callable[[tuple[RuntimeEvent, ...]], None],
        *,
        interval_ms: int = 50,
        batch_limit: int = 200,
    ) -> TkEventBridge:
        return TkEventBridge(
            root,
            self.events,
            callback,
            interval_ms=interval_ms,
            batch_limit=batch_limit,
        )

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._request_queue = asyncio.PriorityQueue(
            maxsize=self.config.request_queue_limit
        )
        self._connected_async = asyncio.Event()
        self._shutdown_async = asyncio.Event()
        self._session_ready_async = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._loop_ready.set()
        try:
            loop.run_until_complete(self._async_main())
        except Exception:
            self._logger.exception("moonraker.runtime_loop_failed")
        finally:
            try:
                pending_tasks = asyncio.all_tasks(loop)
                for task in pending_tasks:
                    task.cancel()
                if pending_tasks:
                    loop.run_until_complete(
                        asyncio.gather(*pending_tasks, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()
                self._loop = None

    async def _async_main(self) -> None:
        state = self._state.set_connection("starting")
        self._publish("state", state)
        timeout = aiohttp.ClientTimeout(
            total=self.config.request_timeout,
            connect=self.config.connect_timeout,
        )
        session_options = {
            "timeout": timeout,
            "headers": self.config.request_headers,
        }
        if self._uses_default_session_factory:
            session_options["connector"] = aiohttp.TCPConnector(
                family=self._preferred_address_family(self.config.host),
                ttl_dns_cache=300,
            )
        self._session = self._session_factory(**session_options)
        assert self._session_ready_async is not None
        self._session_ready_async.set()

        connection_task = asyncio.create_task(self._connection_manager())
        command_task = asyncio.create_task(self._command_worker())
        assert self._shutdown_async is not None
        await self._shutdown_async.wait()

        for task in (command_task, connection_task):
            task.cancel()
        await asyncio.gather(command_task, connection_task, return_exceptions=True)
        await self._close_websocket()
        self._fail_pending(MoonrakerDisconnectedError("Moonraker runtime stopped"))
        self._fail_queued(MoonrakerDisconnectedError("Moonraker runtime stopped"))
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                self._logger.debug("moonraker.session_close_failed", exc_info=True)
        self._session = None
        state = self._state.set_connection("stopped")
        self._publish("state", state)
        self._publish("stopped", state)

    async def _connection_manager(self) -> None:
        assert self._shutdown_async is not None
        assert self._connected_async is not None
        backoff = self.config.reconnect_initial
        attempt = 0
        while not self._shutdown_async.is_set():
            attempt += 1
            state_name = "connecting" if attempt == 1 else "reconnecting"
            state = self._state.set_connection(state_name, attempt=attempt)
            self._publish("state", state)
            self._publish("connection", state)
            receiver_task: Optional[asyncio.Task] = None
            try:
                self._ws = await self._session.ws_connect(
                    self.config.websocket_url,
                    heartbeat=self.config.heartbeat,
                    autoping=True,
                )
                capability_epoch = self._invalidate_gcode_capabilities()
                subscription_epoch = self._invalidate_live_motion()
                receiver_task = asyncio.create_task(self._receive_loop(self._ws))
                await self._rpc_internal(
                    "server.connection.identify",
                    self.config.identify_params,
                )
                await self._refresh_object_subscriptions(subscription_epoch)
                await self._refresh_gcode_capabilities(capability_epoch)

                self._connected_async.set()
                state = self._state.set_connection("connected", attempt=attempt)
                self._publish("state", state)
                self._publish("connected", state)
                backoff = self.config.reconnect_initial

                await receiver_task
                if not self._shutdown_async.is_set():
                    raise MoonrakerDisconnectedError("Moonraker WebSocket closed")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._shutdown_async.is_set():
                    message = str(exc) or exc.__class__.__name__
                    self._logger.warning("moonraker.connection_failed: %s", message)
                    state = self._state.set_connection(
                        "disconnected",
                        attempt=attempt,
                        error=message,
                    )
                    self._publish("state", state)
                    self._publish("disconnected", state)
            finally:
                self._connected_async.clear()
                self._invalidate_gcode_capabilities()
                self._invalidate_live_motion()
                disconnect_error = MoonrakerDisconnectedError(
                    "Moonraker connection was lost"
                )
                self._fail_pending(disconnect_error)
                self._fail_queued(disconnect_error)
                if receiver_task and not receiver_task.done():
                    receiver_task.cancel()
                    await asyncio.gather(receiver_task, return_exceptions=True)
                await self._close_websocket()

            if self._shutdown_async.is_set():
                break
            self._publish("reconnect_scheduled", {"delay": backoff, "attempt": attempt + 1})
            await self._reconnect_sleep(backoff)
            backoff = min(
                self.config.reconnect_max,
                max(
                    self.config.reconnect_initial,
                    backoff * self.config.reconnect_multiplier,
                ),
            )

    async def _command_worker(self) -> None:
        assert self._request_queue is not None
        assert self._connected_async is not None
        assert self._shutdown_async is not None
        while not self._shutdown_async.is_set():
            priority, sequence, envelope = await self._request_queue.get()
            try:
                if not self._connected_async.is_set():
                    self._set_exception(
                        envelope.future,
                        MoonrakerDisconnectedError(
                            "Moonraker disconnected before the command was sent"
                        ),
                    )
                    continue
                try:
                    await self._send_request(envelope)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    public_error = self._detached_exception(exc)
                    self._set_exception(envelope.future, public_error)
                    self._publish(
                        "command_error",
                        {"method": envelope.method, "error": str(exc)},
                    )
                    self._connected_async.clear()
                    state = self._state.set_connection(
                        "disconnected",
                        error=str(exc),
                    )
                    self._publish("state", state)
                    self._publish("disconnected", state)
                    await self._close_websocket()
            finally:
                self._request_queue.task_done()

    def _enqueue_request(self, envelope: _RequestEnvelope) -> None:
        assert self._request_queue is not None
        assert self._shutdown_async is not None
        assert self._connected_async is not None
        if self._shutdown_async.is_set():
            self._set_exception(
                envelope.future,
                MoonrakerDisconnectedError("Moonraker runtime is stopping"),
            )
            return
        if not self._connected_async.is_set():
            self._set_exception(
                envelope.future,
                MoonrakerDisconnectedError(
                    "Moonraker disconnected before the command could be queued"
                ),
            )
            return
        try:
            self._request_queue.put_nowait(
                (envelope.priority, envelope.sequence, envelope)
            )
            self._publish(
                "command_queued",
                {
                    "method": envelope.method,
                    "priority": envelope.priority,
                    "sequence": envelope.sequence,
                },
            )
        except asyncio.QueueFull:
            error = MoonrakerQueueFullError("Moonraker request queue is full")
            self._set_exception(envelope.future, error)
            self._publish("command_error", {"method": envelope.method, "error": str(error)})

    async def _send_request(self, envelope: _RequestEnvelope) -> None:
        await self._send_rpc(
            method=envelope.method,
            params=envelope.params,
            queued_at=envelope.queued_at,
            queued_monotonic=envelope.queued_monotonic,
            timeout=envelope.timeout,
            destination=envelope.future,
            outcome_may_change_machine=True,
        )

    async def _rpc_internal(
        self,
        method: str,
        params: Mapping[str, Any],
    ) -> CommandResult:
        loop = asyncio.get_running_loop()
        destination = loop.create_future()
        now = time.time()
        try:
            await self._send_rpc(
                method=method,
                params=dict(params),
                queued_at=now,
                queued_monotonic=time.monotonic(),
                timeout=self.config.request_timeout,
                destination=destination,
                outcome_may_change_machine=False,
            )
            return await destination
        except Exception:
            if destination.done():
                try:
                    destination.exception()
                except Exception:
                    pass
            raise

    async def _send_rpc(
        self,
        *,
        method: str,
        params: Mapping[str, Any],
        queued_at: float,
        queued_monotonic: float,
        timeout: float,
        destination: Any,
        outcome_may_change_machine: bool,
    ) -> int:
        if self._ws is None or getattr(self._ws, "closed", False):
            error = MoonrakerDisconnectedError("Moonraker WebSocket is not connected")
            self._set_exception(destination, error)
            raise error
        assert self._send_lock is not None

        request_id = self._next_request_id
        self._next_request_id += 1
        sent_at = time.time()
        sent_monotonic = time.monotonic()
        loop = asyncio.get_running_loop()
        timeout_handle = loop.call_later(
            max(0.001, float(timeout)),
            self._expire_request,
            request_id,
        )
        pending = _PendingRequest(
            request_id=request_id,
            method=method,
            queued_at=queued_at,
            queued_monotonic=queued_monotonic,
            sent_at=sent_at,
            sent_monotonic=sent_monotonic,
            destination=destination,
            timeout_handle=timeout_handle,
            outcome_may_change_machine=bool(outcome_may_change_machine),
        )
        self._pending[request_id] = pending
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": dict(params),
            "id": request_id,
        }
        try:
            async with self._send_lock:
                await self._ws.send_json(payload)
        except Exception as exc:
            removed = self._pending.pop(request_id, None)
            if removed and removed.timeout_handle:
                removed.timeout_handle.cancel()
            received_at = time.time()
            received_monotonic = time.monotonic()
            timing = CommandTiming(
                request_id=request_id,
                method=method,
                queued_at=queued_at,
                sent_at=sent_at,
                received_at=received_at,
                queue_ms=max(
                    0.0,
                    (sent_monotonic - queued_monotonic) * 1000.0,
                ),
                response_ms=max(
                    0.0,
                    (received_monotonic - sent_monotonic) * 1000.0,
                ),
                total_ms=max(
                    0.0,
                    (received_monotonic - queued_monotonic) * 1000.0,
                ),
                success=False,
                error=str(exc),
            )
            self._record_timing(timing)
            if outcome_may_change_machine:
                unknown = MoonrakerCommandOutcomeUnknown(
                    method,
                    request_id,
                    timing,
                    "encountered a transport error after send began",
                )
                self._set_exception(destination, unknown)
                self._publish(
                    "command_outcome_unknown",
                    {
                        "request_id": request_id,
                        "method": method,
                        "timing": timing,
                        "reason": str(exc),
                    },
                )
            else:
                self._set_exception(
                    destination,
                    self._detached_exception(exc),
                )
            raise
        self._publish(
            "command_sent",
            {"request_id": request_id, "method": method},
        )
        return request_id

    async def _receive_loop(self, websocket: Any) -> None:
        async for message in websocket:
            message_type = getattr(message, "type", None)
            if isinstance(message, Mapping):
                payload = dict(message)
            elif isinstance(message, str):
                payload = json.loads(message)
            elif message_type == aiohttp.WSMsgType.TEXT:
                payload = json.loads(message.data)
            elif message_type in {
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.CLOSING,
            }:
                break
            elif message_type == aiohttp.WSMsgType.ERROR:
                error = websocket.exception()
                raise MoonrakerDisconnectedError(str(error or "WebSocket error"))
            else:
                continue
            self._handle_payload(payload)

    def _handle_payload(self, payload: Mapping[str, Any]) -> None:
        method = payload.get("method")
        if method:
            params = payload.get("params", [])
            if method == "notify_status_update":
                if isinstance(params, list) and params and isinstance(params[0], Mapping):
                    self._merge_status(params[0])
                return
            if method == "notify_gcode_response":
                if isinstance(params, list) and params:
                    response_text = str(params[0])
                    response_level = self._gcode_response_level(response_text)
                    self._append_console(
                        response_text,
                        level=response_level,
                    )
                    if response_level == "error":
                        self._logger.warning(
                            "moonraker.gcode_response_error: %s",
                            response_text,
                        )
                return
            if method in {"notify_klippy_disconnected", "notify_klippy_shutdown"}:
                self._invalidate_gcode_capabilities()
                self._invalidate_live_motion()
                self._merge_status(
                    {
                        "webhooks": {
                            "state": "shutdown",
                            "state_message": method,
                        }
                    }
                )
            elif method == "notify_klippy_ready":
                capability_epoch = self._invalidate_gcode_capabilities()
                subscription_epoch = self._invalidate_live_motion()
                self._merge_status(
                    {
                        "webhooks": {
                            "state": "ready",
                            "state_message": "",
                        }
                    }
                )
                self._spawn_background_task(
                    self._refresh_gcode_capabilities(capability_epoch)
                )
                self._spawn_background_task(
                    self._refresh_object_subscriptions(subscription_epoch)
                )
            self._publish(
                "notification",
                {"method": method, "params": deep_freeze(params)},
            )
            return

        request_id = payload.get("id")
        if not isinstance(request_id, int):
            return
        pending = self._pending.pop(request_id, None)
        if pending is None:
            self._publish("orphan_response", deep_freeze(payload))
            return
        if pending.timeout_handle:
            pending.timeout_handle.cancel()

        received_at = time.time()
        received_monotonic = time.monotonic()
        error_payload = payload.get("error")
        success = error_payload is None
        error_text = None
        if isinstance(error_payload, Mapping):
            error_text = str(error_payload.get("message", "Moonraker RPC error"))
        timing = CommandTiming(
            request_id=request_id,
            method=pending.method,
            queued_at=pending.queued_at,
            sent_at=pending.sent_at,
            received_at=received_at,
            queue_ms=max(
                0.0,
                (pending.sent_monotonic - pending.queued_monotonic) * 1000.0,
            ),
            response_ms=max(
                0.0,
                (received_monotonic - pending.sent_monotonic) * 1000.0,
            ),
            total_ms=max(
                0.0,
                (received_monotonic - pending.queued_monotonic) * 1000.0,
            ),
            success=success,
            error=error_text,
        )
        self._record_timing(timing)

        result = payload.get("result")
        if isinstance(result, Mapping) and pending.method != "printer.objects.subscribe":
            status = result.get("status")
            if isinstance(status, Mapping):
                self._merge_status(status)

        if error_payload is not None:
            if isinstance(error_payload, Mapping):
                error = MoonrakerRPCError(
                    pending.method,
                    error_payload.get("code"),
                    str(error_payload.get("message", "Moonraker RPC error")),
                    data=error_payload.get("data"),
                    timing=timing,
                )
            else:
                error = MoonrakerRPCError(
                    pending.method,
                    None,
                    str(error_payload),
                    timing=timing,
                )
            self._set_exception(pending.destination, error)
            self._publish(
                "command_error",
                {"request_id": request_id, "method": pending.method, "timing": timing},
            )
            return

        command_result = CommandResult(
            request_id=request_id,
            method=pending.method,
            result=deep_freeze(result),
            timing=timing,
        )
        self._set_result(pending.destination, command_result)
        self._publish("command_result", command_result)

    def _expire_request(self, request_id: int) -> None:
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        now = time.time()
        now_monotonic = time.monotonic()
        timing = CommandTiming(
            request_id=request_id,
            method=pending.method,
            queued_at=pending.queued_at,
            sent_at=pending.sent_at,
            received_at=now,
            queue_ms=max(
                0.0,
                (pending.sent_monotonic - pending.queued_monotonic) * 1000.0,
            ),
            response_ms=max(
                0.0,
                (now_monotonic - pending.sent_monotonic) * 1000.0,
            ),
            total_ms=max(
                0.0,
                (now_monotonic - pending.queued_monotonic) * 1000.0,
            ),
            success=False,
            error="request timeout",
        )
        self._record_timing(timing)
        if pending.outcome_may_change_machine:
            error = MoonrakerRequestTimeout(
                pending.method,
                request_id,
                timing,
            )
        else:
            error = MoonrakerDisconnectedError(
                f"{pending.method} response timed out during connection setup"
            )
        self._set_exception(pending.destination, error)
        if pending.outcome_may_change_machine:
            self._publish(
                "command_outcome_unknown",
                {"request_id": request_id, "method": pending.method, "timing": timing},
            )
        else:
            self._publish(
                "command_error",
                {"request_id": request_id, "method": pending.method, "timing": timing},
            )

    async def _upload_gcode(
        self,
        source: Union[str, Path, bytes, bytearray, memoryview],
        remote_name: Optional[str],
        *,
        checksum: Union[bool, str, None],
        start: bool,
    ) -> UploadResult:
        assert self._session_ready_async is not None
        await self._session_ready_async.wait()
        started_at = time.monotonic()
        data, inferred_name = await self._read_upload_source(source)
        normalized_name = self._normalize_remote_name(remote_name or inferred_name)

        digest: Optional[str]
        if checksum is True:
            digest = hashlib.sha256(data).hexdigest()
        elif isinstance(checksum, str) and checksum.strip():
            digest = checksum.strip()
        else:
            digest = None

        if start:
            self._validate_print_start_preflight()

        remote_path = PurePosixPath(normalized_name)
        form = aiohttp.FormData()
        form.add_field("root", "gcodes")
        parent = str(remote_path.parent)
        if parent and parent != ".":
            form.add_field("path", parent)
        if digest:
            form.add_field("checksum", digest)
        if start:
            form.add_field("print", "true")
        form.add_field(
            "file",
            data,
            filename=remote_path.name,
            content_type="text/x-gcode",
        )

        url = f"{self.config.base_url}/server/files/upload"
        upload_timeout = aiohttp.ClientTimeout(
            total=self.config.upload_timeout,
            connect=self.config.connect_timeout,
        )
        async with self._session.post(
            url,
            data=form,
            timeout=upload_timeout,
        ) as response:
            response_text = await response.text()
            try:
                response_payload = json.loads(response_text)
            except (TypeError, ValueError):
                response_payload = response_text
            if int(response.status) >= 400:
                raise MoonrakerHTTPError(
                    int(response.status),
                    response_text,
                    response_payload,
                )
            response_status = int(response.status)

        response_result = (
            response_payload.get("result", response_payload)
            if isinstance(response_payload, Mapping)
            else {}
        )
        print_started = bool(
            response_result.get("print_started", False)
            if isinstance(response_result, Mapping)
            else False
        )
        print_queued = bool(
            response_result.get("print_queued", False)
            if isinstance(response_result, Mapping)
            else False
        )
        if start and print_queued:
            error = MoonrakerPrintQueuedError(deep_freeze(response_payload))
            self._publish(
                "upload_error",
                {"error": str(error), "response": deep_freeze(response_payload)},
            )
            raise error
        if start and not print_started:
            raise MoonrakerHTTPError(
                response_status,
                "upload succeeded but Moonraker did not start the print",
                response_payload,
            )

        result = UploadResult(
            remote_name=normalized_name,
            size=len(data),
            checksum=digest,
            response=deep_freeze(response_payload),
            print_started=print_started,
            print_queued=print_queued,
            elapsed_ms=max(0.0, (time.monotonic() - started_at) * 1000.0),
        )
        self._publish("upload_complete", result)
        return result

    async def _emergency_http(self) -> EmergencyResult:
        assert self._session_ready_async is not None
        await self._session_ready_async.wait()
        started_at = time.monotonic()
        timeout = aiohttp.ClientTimeout(
            total=self.config.emergency_timeout,
            connect=min(self.config.emergency_timeout, self.config.connect_timeout),
        )
        url = f"{self.config.base_url}/printer/emergency_stop"
        async with self._session.post(url, timeout=timeout) as response:
            response_text = await response.text()
            try:
                response_payload = json.loads(response_text)
            except (TypeError, ValueError):
                response_payload = response_text
            if int(response.status) >= 400:
                raise MoonrakerHTTPError(
                    int(response.status),
                    response_text,
                    response_payload,
                )
        result = EmergencyResult(
            response=deep_freeze(response_payload),
            elapsed_ms=max(0.0, (time.monotonic() - started_at) * 1000.0),
        )
        self._publish("emergency_result", result)
        return result

    async def _read_upload_source(
        self,
        source: Union[str, Path, bytes, bytearray, memoryview],
    ) -> tuple[bytes, Optional[str]]:
        if isinstance(source, (bytes, bytearray, memoryview)):
            return bytes(source), None
        path = Path(source)
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, path.read_bytes)
        return data, path.name

    @staticmethod
    def _normalize_remote_name(name: Optional[str]) -> str:
        if not name:
            raise ValueError("remote_name is required when uploading bytes")
        cleaned = str(name).replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(cleaned)
        if not path.name or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("remote_name must be a safe relative G-code path")
        return str(path)

    def _validate_print_start_preflight(self) -> None:
        state = self.state_snapshot()
        if not state.connected:
            raise MoonrakerPreflightError(
                "Cannot start a print without a live Moonraker WebSocket"
            )
        if state.klippy_state.strip().lower() != "ready":
            raise MoonrakerPreflightError(
                f"Klippy is not ready (state={state.klippy_state})"
            )

        pause_resume = state.objects.get("pause_resume", {})
        if isinstance(pause_resume, Mapping) and bool(
            pause_resume.get("is_paused", False)
        ):
            raise MoonrakerPreflightError("Cannot start a new print while paused")

        print_stats = state.objects.get("print_stats", {})
        idle_timeout = state.objects.get("idle_timeout", {})
        print_state = (
            str(print_stats.get("state", "")).strip().lower()
            if isinstance(print_stats, Mapping)
            else ""
        )
        idle_state = (
            str(idle_timeout.get("state", "")).strip().lower()
            if isinstance(idle_timeout, Mapping)
            else ""
        )
        print_idle = print_state in {"standby", "complete", "cancelled"}
        machine_idle = idle_state in {"idle", "ready"}
        is_idle = print_idle if print_state else machine_idle
        if not is_idle:
            shown_state = print_state or idle_state or "unavailable"
            raise MoonrakerPreflightError(
                f"Machine is not in an idle start state (state={shown_state})"
            )

    @staticmethod
    def _available_objects(result: Any) -> set[str]:
        if isinstance(result, Mapping):
            objects = result.get("objects", [])
        else:
            objects = result
        if not isinstance(objects, (list, tuple, set, frozenset)):
            return set()
        return {str(name) for name in objects}

    @staticmethod
    def _thaw_status(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): MoonrakerRuntime._thaw_status(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [MoonrakerRuntime._thaw_status(item) for item in value]
        if isinstance(value, tuple):
            return tuple(MoonrakerRuntime._thaw_status(item) for item in value)
        if isinstance(value, set):
            return {MoonrakerRuntime._thaw_status(item) for item in value}
        return value

    def _spawn_background_task(self, awaitable: Awaitable[Any]) -> None:
        task = asyncio.create_task(awaitable)

        def _consume(task: asyncio.Task) -> None:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                self._logger.debug(
                    "moonraker.background_task_failed",
                    exc_info=True,
                )

        task.add_done_callback(_consume)

    async def _refresh_object_subscriptions(self, epoch: int) -> bool:
        """Refresh printer-object subscriptions after Klippy becomes ready."""
        assert epoch > 0
        delay = max(0.05, float(self.config.reconnect_initial))
        attempts = 0
        while attempts < 5:
            attempts += 1
            if epoch != self._motion_epoch or self._shutdown_async is None:
                return False
            try:
                object_result = await self._rpc_internal("printer.objects.list", {})
                available_objects = self._available_objects(object_result.result)
                if not available_objects:
                    raise MoonrakerDisconnectedError(
                        "printer.objects.list returned no available objects"
                    )
                subscription_objects = {
                    name: fields
                    for name, fields in self.config.subscriptions.items()
                    if name in available_objects
                }
                unavailable = tuple(
                    sorted(set(self.config.subscriptions) - set(subscription_objects))
                )
                if subscription_objects:
                    subscribe_result = await self._rpc_internal(
                        "printer.objects.subscribe",
                        {"objects": subscription_objects},
                    )
                    if epoch != self._motion_epoch:
                        return False
                    status = subscribe_result.result.get("status")
                    if not isinstance(status, Mapping) or not status:
                        raise MoonrakerDisconnectedError(
                            "printer.objects.subscribe returned no status snapshot"
                        )
                    self._merge_status(self._thaw_status(status))
                    if unavailable:
                        self._publish("subscription_unavailable", unavailable)
                    return True
                raise MoonrakerDisconnectedError(
                    "printer.objects.subscribe had no matching objects"
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if epoch != self._motion_epoch:
                    return False
                if attempts >= 5:
                    self._logger.warning(
                        "moonraker.subscription_refresh_failed: %s",
                        str(exc) or exc.__class__.__name__,
                    )
                    self._publish(
                        "subscription_unavailable",
                        tuple(sorted(self.config.subscriptions)),
                    )
                    return False
                await asyncio.sleep(delay)
                delay = min(
                    self.config.reconnect_max,
                    max(
                        self.config.reconnect_initial,
                        delay * self.config.reconnect_multiplier,
                    ),
                )
        return False

    @staticmethod
    def _available_gcode_commands(result: Any) -> set[str]:
        if not isinstance(result, Mapping):
            return set()
        return {
            str(name).strip().upper()
            for name in result
            if str(name).strip()
        }

    def _invalidate_gcode_capabilities(self) -> int:
        """Clear cached macros and return the generation for the next refresh."""
        self._capability_epoch += 1
        self._merge_status(
            {
                "_openspotter_capabilities": {
                    "gcode_commands": (),
                }
            }
        )
        return self._capability_epoch

    async def _refresh_gcode_capabilities(self, epoch: int) -> None:
        """Read the currently loaded command set without reviving stale data."""
        try:
            help_result = await self._rpc_internal(
                "printer.gcode.help",
                {},
            )
            gcode_commands = self._available_gcode_commands(
                help_result.result
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if epoch != self._capability_epoch:
                return
            self._logger.warning(
                "moonraker.gcode_capabilities_failed: %s",
                str(exc) or exc.__class__.__name__,
            )
            self._publish(
                "gcode_capabilities_unavailable",
                str(exc) or exc.__class__.__name__,
            )
            return
        if epoch != self._capability_epoch:
            return
        self._merge_status(
            {
                "_openspotter_capabilities": {
                    "gcode_commands": sorted(gcode_commands),
                }
            }
        )

    @staticmethod
    def _preferred_address_family(host: str) -> int:
        """Prefer IPv4 for mDNS names with unusable link-local IPv6 routes.

        Windows commonly resolves ``.local`` printer names to link-local IPv6
        before their reachable IPv4 address.  aiohttp may consume the complete
        connect timeout on that first address.  Restricting mDNS names to IPv4
        avoids that delay while preserving explicit IPv6 literals and normal
        dual-stack behavior for other DNS names.
        """
        candidate = str(host or "").strip()
        unbracketed = (
            candidate[1:-1]
            if candidate.startswith("[") and candidate.endswith("]")
            else candidate
        )
        try:
            address = ipaddress.ip_address(unbracketed)
        except ValueError:
            return (
                socket.AF_INET
                if unbracketed.lower().endswith(".local")
                else socket.AF_UNSPEC
            )
        return socket.AF_INET6 if address.version == 6 else socket.AF_INET

    @staticmethod
    def _gcode_response_level(text: str) -> str:
        normalized = str(text or "").strip().lower()
        if (
            normalized.startswith("!!")
            or normalized.startswith("error")
            or "unknown command:" in normalized
            or "must home axis first" in normalized
            or "move out of range" in normalized
            or "blocked unsafe move" in normalized
            or "printer is not ready" in normalized
        ):
            return "error"
        return "info"

    def _merge_status(self, status: Mapping[str, Any]) -> None:
        merged_status = dict(status)
        motion_report = merged_status.get("motion_report")
        if (
            isinstance(motion_report, Mapping)
            and "live_position" in motion_report
        ):
            merged_status["_openspotter_live_motion"] = {
                "epoch": self._motion_epoch,
                "fresh": True,
            }
        state = self._state.merge_status(merged_status)
        self._publish("state", state)

    def _invalidate_live_motion(self) -> int:
        """Hide retained motion data until this Klippy epoch reports it again."""
        self._motion_epoch += 1
        state = self._state.merge_status(
            {
                "_openspotter_live_motion": {
                    "epoch": self._motion_epoch,
                    "fresh": False,
                },
                "toolhead": {
                    "homed_axes": "",
                },
            }
        )
        self._publish("state", state)
        return self._motion_epoch

    def _append_console(self, text: str, *, source: str = "gcode", level: str = "info") -> None:
        with self._console_lock:
            self._console_sequence += 1
            entry = ConsoleEntry(
                created_at=time.time(),
                text=str(text),
                source=str(source),
                level=str(level),
                sequence=self._console_sequence,
            )
            self._console.append(entry)
        self._publish("console", entry)

    def _record_timing(self, timing: CommandTiming) -> None:
        with self._timing_lock:
            self._timings.append(timing)
        self._publish("command_timing", timing)

    def _publish(self, kind: str, payload: Any = None) -> None:
        self.events.publish(RuntimeEvent.create(kind, payload))

    async def _close_websocket(self) -> None:
        websocket = self._ws
        self._ws = None
        if websocket is not None and not getattr(websocket, "closed", False):
            try:
                await websocket.close()
            except Exception:
                self._logger.debug("moonraker.websocket_close_failed", exc_info=True)

    def _fail_pending(self, error: BaseException) -> None:
        pending_items = list(self._pending.values())
        self._pending.clear()
        for pending in pending_items:
            if pending.timeout_handle:
                pending.timeout_handle.cancel()
            now = time.time()
            now_monotonic = time.monotonic()
            timing = CommandTiming(
                request_id=pending.request_id,
                method=pending.method,
                queued_at=pending.queued_at,
                sent_at=pending.sent_at,
                received_at=now,
                queue_ms=max(
                    0.0,
                    (pending.sent_monotonic - pending.queued_monotonic) * 1000.0,
                ),
                response_ms=max(
                    0.0,
                    (now_monotonic - pending.sent_monotonic) * 1000.0,
                ),
                total_ms=max(
                    0.0,
                    (now_monotonic - pending.queued_monotonic) * 1000.0,
                ),
                success=False,
                error=str(error),
            )
            self._record_timing(timing)
            if pending.outcome_may_change_machine:
                unknown = MoonrakerCommandOutcomeUnknown(
                    pending.method,
                    pending.request_id,
                    timing,
                    "lost its connection after being sent",
                )
                self._set_exception(pending.destination, unknown)
                self._publish(
                    "command_outcome_unknown",
                    {
                        "request_id": pending.request_id,
                        "method": pending.method,
                        "timing": timing,
                        "reason": str(error),
                    },
                )
            else:
                self._set_exception(
                    pending.destination,
                    MoonrakerDisconnectedError(str(error)),
                )
                self._publish(
                    "command_error",
                    {
                        "request_id": pending.request_id,
                        "method": pending.method,
                        "timing": timing,
                        "reason": str(error),
                    },
                )

    def _fail_queued(self, error: BaseException) -> None:
        if self._request_queue is None:
            return
        while True:
            try:
                _, _, envelope = self._request_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._set_exception(
                envelope.future,
                MoonrakerDisconnectedError(str(error)),
            )
            self._request_queue.task_done()

    @staticmethod
    def _set_result(destination: Any, value: Any) -> None:
        if not destination.done():
            destination.set_result(value)

    @staticmethod
    def _set_exception(destination: Any, error: BaseException) -> None:
        if not destination.done():
            destination.set_exception(error)

    @staticmethod
    def _detached_exception(error: BaseException) -> BaseException:
        """Copy an error without sharing the runtime coroutine's traceback.

        ``unittest.assertRaises`` clears traceback frames after consuming an
        exception. Sharing the exact exception raised inside this coroutine
        would therefore clear (and terminate) the long-lived command worker.
        """
        try:
            detached = type(error)(*getattr(error, "args", ()))
        except Exception:
            detached = MoonrakerError(str(error) or error.__class__.__name__)
        return detached
