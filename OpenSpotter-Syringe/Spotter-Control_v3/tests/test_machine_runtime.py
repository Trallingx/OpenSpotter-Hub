import asyncio
import hashlib
import json
import socket
import threading
import time
import unittest

import aiohttp

from app.machine import (
    MoonrakerCommandOutcomeUnknown,
    MoonrakerConfig,
    MoonrakerDisconnectedError,
    MoonrakerNotStartedError,
    MoonrakerPreflightError,
    MoonrakerPrintQueuedError,
    MoonrakerRequestTimeout,
    MoonrakerRPCError,
    MoonrakerRuntime,
    RuntimeEvent,
    RuntimeEventQueue,
    StateStore,
    TkEventBridge,
)


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("condition did not become true before timeout")


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = {"result": "ok"} if payload is None else payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def text(self):
        return json.dumps(self.payload)


class FakeWebSocket:
    _STOP = object()

    def __init__(self, available_objects):
        self.available_objects = list(available_objects)
        self.gcode_commands = {
            "ADJUST_NEEDLE_SURFACE_OFFSET": "Adjust live Z",
            "G0": "Move",
            "G28": "Home",
            "NEEDLE_TIP_OFFSETS_DISABLE": "Disable offsets",
            "NEEDLE_TIP_OFFSETS_ENABLE": "Enable offsets",
            "OPENSPOTTER_CONTRACT_V3": "Contract marker",
            "OPENSPOTTER_HOME": "Safe home",
            "OPENSPOTTER_JOB_CLEANUP": "Cleanup",
            "OPENSPOTTER_JOB_HOME": "Job home",
            "OPENSPOTTER_JOB_REHOME_Z": "Job Z rehome",
            "OPENSPOTTER_JOG": "Guarded jog",
            "OPENSPOTTER_SET_PROMPT": "Set prompt",
            "RESET_NEEDLE_SURFACE_OFFSET": "Reset live Z",
        }
        self.sent = []
        self.closed = False
        self._loop = asyncio.get_running_loop()
        self._incoming = asyncio.Queue()

    async def send_json(self, payload):
        self.sent.append(payload)
        method = payload["method"]
        request_id = payload["id"]
        if method == "server.connection.identify":
            result = {"connection_id": 41}
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        elif method == "printer.objects.list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"objects": self.available_objects},
            }
        elif method == "printer.objects.subscribe":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "eventtime": 1.0,
                    "status": {
                        "webhooks": {"state": "ready", "state_message": ""},
                        "toolhead": {
                            "position": [1.0, 2.0, 3.0],
                            "homed_axes": "xyz",
                        },
                        "motion_report": {
                            "live_position": [1.0, 2.0, 3.0],
                            "live_velocity": 0.0,
                        },
                        "print_stats": {"state": "standby"},
                        "pause_resume": {"is_paused": False},
                        "idle_timeout": {"state": "Idle"},
                    },
                },
            }
        elif method == "printer.gcode.help":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": dict(self.gcode_commands),
            }
        elif method == "test.fail":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": 400, "message": "intentional failure"},
            }
        elif method == "test.slow":
            return
        elif method == "test.send_fail":
            raise ConnectionError("simulated send failure")
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"ok": True, "method": method},
            }
        await self._incoming.put(response)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._incoming.get()
        if item is self._STOP:
            raise StopAsyncIteration
        return item

    async def close(self):
        if not self.closed:
            self.closed = True
            await self._incoming.put(self._STOP)

    def exception(self):
        return None

    def push(self, payload):
        self._loop.call_soon_threadsafe(self._incoming.put_nowait, payload)

    def remote_close(self):
        self.closed = True
        self._loop.call_soon_threadsafe(self._incoming.put_nowait, self._STOP)


class FakeSession:
    def __init__(self, available_objects):
        self.available_objects = available_objects
        self.websockets = []
        self.posts = []
        self.closed = False
        self.upload_print_started = True
        self.upload_print_queued = False

    async def ws_connect(self, url, **kwargs):
        websocket = FakeWebSocket(self.available_objects)
        self.websockets.append(websocket)
        return websocket

    def post(self, url, *, data=None, timeout=None):
        self.posts.append((url, data, timeout))
        if url.endswith("/printer/emergency_stop"):
            return FakeResponse(payload={"result": "ok"})
        fields = {
            field_options["name"]: value
            for field_options, headers, value in data._fields
        }
        return FakeResponse(
            payload={
                "result": {
                    "item": {"path": "jobs/sample.gcode", "root": "gcodes"},
                    "print_started": (
                        fields.get("print") == "true"
                        and self.upload_print_started
                    ),
                    "print_queued": (
                        fields.get("print") == "true"
                        and self.upload_print_queued
                    ),
                }
            }
        )

    async def close(self):
        self.closed = True


class DelayedIdentifyWebSocket(FakeWebSocket):
    def __init__(self, available_objects):
        super().__init__(available_objects)
        self.held_identify = None

    async def send_json(self, payload):
        if payload["method"] == "server.connection.identify":
            self.sent.append(payload)
            self.held_identify = payload
            return
        await super().send_json(payload)

    def release_identify(self):
        payload = self.held_identify
        if payload is None:
            raise AssertionError("identify request has not been sent")
        response = {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {"connection_id": 41},
        }
        self._loop.call_soon_threadsafe(self._incoming.put_nowait, response)


class DelayedIdentifySession(FakeSession):
    async def ws_connect(self, url, **kwargs):
        websocket = DelayedIdentifyWebSocket(self.available_objects)
        self.websockets.append(websocket)
        return websocket


class DropDuringObjectListWebSocket(FakeWebSocket):
    async def send_json(self, payload):
        if payload["method"] == "printer.objects.list":
            self.sent.append(payload)
            self.remote_close()
            return
        await super().send_json(payload)


class DropDuringObjectListSession(FakeSession):
    async def ws_connect(self, url, **kwargs):
        if not self.websockets:
            websocket = DropDuringObjectListWebSocket(self.available_objects)
        else:
            websocket = FakeWebSocket(self.available_objects)
        self.websockets.append(websocket)
        return websocket


class FakeTkRoot:
    def __init__(self):
        self.callbacks = {}
        self.next_id = 0

    def after(self, interval_ms, callback):
        self.next_id += 1
        self.callbacks[self.next_id] = (interval_ms, callback)
        return self.next_id

    def after_cancel(self, after_id):
        self.callbacks.pop(after_id, None)


class MachineConfigAndStateTests(unittest.TestCase):
    def test_config_normalizes_urls_headers_and_subscriptions(self):
        config = MoonrakerConfig(
            host=" printer.local ",
            scheme="https",
            route_prefix="/moonraker/",
            api_key="secret",
            headers={"X-Test": "yes"},
            subscriptions={"toolhead": ["position"]},
        )

        self.assertEqual(
            config.base_url,
            "https://printer.local:7125/moonraker",
        )
        self.assertEqual(
            config.websocket_url,
            "wss://printer.local:7125/moonraker/websocket",
        )
        self.assertEqual(config.request_headers["X-Api-Key"], "secret")
        self.assertEqual(config.subscriptions["toolhead"], ("position",))

    def test_default_config_subscribes_runtime_and_offset_objects(self):
        config = MoonrakerConfig(host="printer.local")

        self.assertIn("display_status", config.subscriptions)
        self.assertIn("save_variables", config.subscriptions)
        self.assertEqual(config.subscriptions["bed_mesh"], ("profile_name",))
        self.assertIsNone(config.subscriptions["gcode_macro _NEEDLE_TIP_OFFSETS"])
        self.assertIsNone(config.subscriptions["gcode_macro _OPENSPOTTER_RUNTIME"])
        self.assertNotIn("status", config.subscriptions["toolhead"])
        self.assertIn("axis_minimum", config.subscriptions["toolhead"])
        self.assertIn("axis_maximum", config.subscriptions["toolhead"])
        self.assertEqual(config.identify_params["type"], "desktop")
        self.assertGreater(config.gcode_timeout, config.request_timeout)
        self.assertGreater(config.upload_timeout, config.gcode_timeout)

        with self.assertRaises(ValueError):
            MoonrakerConfig(host="printer.local", reconnect_initial=0)

    def test_runtime_prefers_ipv4_for_local_mdns_without_breaking_literals(self):
        self.assertEqual(
            MoonrakerRuntime._preferred_address_family("printer.local"),
            socket.AF_INET,
        )
        self.assertEqual(
            MoonrakerRuntime._preferred_address_family("192.168.1.20"),
            socket.AF_INET,
        )
        self.assertEqual(
            MoonrakerRuntime._preferred_address_family("[2001:db8::20]"),
            socket.AF_INET6,
        )
        self.assertEqual(
            MoonrakerRuntime._preferred_address_family("printer.example"),
            socket.AF_UNSPEC,
        )

    def test_state_snapshots_are_deeply_immutable_and_incrementally_merged(self):
        store = StateStore()
        first = store.merge_status(
            {
                "toolhead": {
                    "position": [1.0, 2.0, 3.0],
                    "homed_axes": "xy",
                }
            }
        )
        second = store.merge_status(
            {
                "toolhead": {"position": [4.0, 5.0, 6.0]},
                "print_stats": {"state": "printing"},
            }
        )

        self.assertEqual(first.objects["toolhead"]["position"], (1.0, 2.0, 3.0))
        self.assertEqual(second.objects["toolhead"]["position"], (4.0, 5.0, 6.0))
        self.assertEqual(second.objects["toolhead"]["homed_axes"], "xy")
        self.assertEqual(second.objects["print_stats"]["state"], "printing")
        with self.assertRaises(TypeError):
            second.objects["toolhead"]["homed_axes"] = "xyz"

    def test_event_queue_is_bounded_and_tk_bridge_only_drains_local_events(self):
        events = RuntimeEventQueue(maxsize=2)
        events.publish(RuntimeEvent.create("one"))
        events.publish(RuntimeEvent.create("two"))
        events.publish(RuntimeEvent.create("three"))

        root = FakeTkRoot()
        batches = []
        bridge = TkEventBridge(root, events, batches.append, batch_limit=10)
        batch = bridge.pump_once()

        self.assertEqual([event.kind for event in batch], ["two", "three"])
        self.assertEqual(events.dropped_count, 1)
        self.assertEqual(batches[0], batch)

    def test_state_events_are_coalesced_without_discarding_control_errors(self):
        events = RuntimeEventQueue(maxsize=2)
        events.publish(RuntimeEvent.create("normal-one"))
        events.publish(RuntimeEvent.create("normal-two"))
        events.publish(RuntimeEvent.create("command_error", {"message": "failed"}))
        events.publish(RuntimeEvent.create("state", {"revision": 1}))
        events.publish(RuntimeEvent.create("state", {"revision": 2}))

        batch = events.drain()

        self.assertEqual(
            [event.kind for event in batch],
            ["normal-two", "command_error", "state"],
        )
        self.assertEqual(batch[-1].payload["revision"], 2)
        self.assertEqual(events.dropped_count, 1)
        self.assertEqual(events.coalesced_count, 1)


class MoonrakerRuntimeTests(unittest.TestCase):
    def make_runtime(self):
        subscriptions = {
            "webhooks": ["state", "state_message"],
            "toolhead": ["position", "homed_axes"],
            "motion_report": ["live_position", "live_velocity"],
            "print_stats": ["state"],
            "pause_resume": ["is_paused"],
            "idle_timeout": ["state"],
        }
        config = MoonrakerConfig(
            host="fake.local",
            request_timeout=1.0,
            connect_timeout=1.0,
            reconnect_initial=0.01,
            reconnect_max=0.02,
            subscriptions=subscriptions,
            console_limit=2,
        )
        session = FakeSession(subscriptions)
        runtime = MoonrakerRuntime(
            config,
            session_factory=lambda **kwargs: session,
        )
        return runtime, session

    def test_request_before_start_returns_failed_future(self):
        runtime, _ = self.make_runtime()

        with self.assertRaises(MoonrakerNotStartedError):
            runtime.send_gcode("G28").result(timeout=0.1)

    def test_identify_subscribe_commands_state_console_and_timing(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            websocket = session.websockets[0]
            methods = [payload["method"] for payload in websocket.sent]
            self.assertEqual(
                methods[:3],
                [
                    "server.connection.identify",
                    "printer.objects.list",
                    "printer.objects.subscribe",
                ],
            )
            self.assertEqual(methods[3], "printer.gcode.help")
            capabilities = runtime.state_snapshot().objects[
                "_openspotter_capabilities"
            ]["gcode_commands"]
            self.assertIn("OPENSPOTTER_JOG", capabilities)
            self.assertTrue(
                runtime.state_snapshot().objects[
                    "_openspotter_live_motion"
                ]["fresh"]
            )

            command = runtime.send_gcode("G28").result(timeout=1.0)
            self.assertEqual(command.method, "printer.gcode.script")
            self.assertTrue(command.timing.success)
            self.assertGreaterEqual(command.timing.total_ms, 0.0)

            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_status_update",
                    "params": [
                        {
                            "toolhead": {"position": [9.0, 8.0, 7.0]},
                            "motion_report": {
                                "live_position": [9.0, 8.0, 7.0],
                                "live_velocity": 0.0,
                            },
                        },
                        2.0,
                    ],
                }
            )
            wait_for(
                lambda: runtime.state_snapshot()
                .objects.get("toolhead", {})
                .get("position")
                == (9.0, 8.0, 7.0)
            )
            state = runtime.state_snapshot()
            self.assertEqual(state.objects["toolhead"]["homed_axes"], "xyz")
            self.assertEqual(state.objects["motion_report"]["live_velocity"], 0.0)

            for text in ("first", "second", "third"):
                websocket.push(
                    {
                        "jsonrpc": "2.0",
                        "method": "notify_gcode_response",
                        "params": [text],
                    }
                )
            wait_for(
                lambda: len(runtime.console_snapshot()) == 2
                and runtime.console_snapshot()[-1].text == "third"
            )
            self.assertEqual(
                [entry.text for entry in runtime.console_snapshot()],
                ["second", "third"],
            )
            self.assertEqual(
                [entry.sequence for entry in runtime.console_snapshot()],
                [2, 3],
            )
            self.assertTrue(runtime.timings_snapshot())
        finally:
            self.assertTrue(runtime.stop())
            self.assertTrue(session.closed)

    def test_unknown_gcode_response_is_exposed_as_console_error(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            websocket = session.websockets[0]
            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_gcode_response",
                    "params": ['Unknown command:"OPENSPOTTER_JOG"'],
                }
            )
            entry = wait_for(
                lambda: runtime.console_snapshot()[-1]
                if runtime.console_snapshot()
                else None
            )
            self.assertEqual(entry.level, "error")
        finally:
            runtime.stop()

    def test_klippy_restart_invalidates_and_reloads_gcode_capabilities(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            websocket = session.websockets[0]
            self.assertIn(
                "OPENSPOTTER_CONTRACT_V3",
                runtime.state_snapshot().objects[
                    "_openspotter_capabilities"
                ]["gcode_commands"],
            )

            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_klippy_shutdown",
                    "params": [],
                }
            )
            wait_for(
                lambda: runtime.state_snapshot().objects[
                    "_openspotter_capabilities"
                ]["gcode_commands"]
                == ()
            )
            self.assertFalse(
                runtime.state_snapshot().objects[
                    "_openspotter_live_motion"
                ]["fresh"]
            )
            self.assertEqual(
                runtime.state_snapshot().objects["toolhead"]["homed_axes"],
                "",
            )

            websocket.gcode_commands = {"M105": "Temperature report"}
            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_klippy_ready",
                    "params": [],
                }
            )
            wait_for(
                lambda: runtime.state_snapshot().objects[
                    "_openspotter_capabilities"
                ]["gcode_commands"]
                == ("M105",)
            )
            self.assertFalse(
                runtime.state_snapshot().objects[
                    "_openspotter_live_motion"
                ]["fresh"]
            )
            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_status_update",
                    "params": [
                        {
                            "motion_report": {
                                "live_position": [4.0, 5.0, 6.0],
                            }
                        },
                        3.0,
                    ],
                }
            )
            wait_for(
                lambda: runtime.state_snapshot().objects[
                    "_openspotter_live_motion"
                ]["fresh"]
                is True
            )
            self.assertEqual(
                runtime.state_snapshot().objects["toolhead"]["homed_axes"],
                "",
            )
            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_status_update",
                    "params": [
                        {"toolhead": {"homed_axes": "xyz"}},
                        3.1,
                    ],
                }
            )
            wait_for(
                lambda: runtime.state_snapshot().objects["toolhead"][
                    "homed_axes"
                ]
                == "xyz"
            )
            self.assertGreaterEqual(
                sum(
                    payload["method"] == "printer.gcode.help"
                    for payload in websocket.sent
                ),
                2,
            )
        finally:
            runtime.stop()

    def test_control_helpers_and_rpc_errors_use_json_rpc_ids(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            results = [
                runtime.pause().result(timeout=1.0),
                runtime.resume().result(timeout=1.0),
                runtime.cancel().result(timeout=1.0),
            ]
            self.assertEqual(
                [result.method for result in results],
                [
                    "printer.print.pause",
                    "printer.print.resume",
                    "printer.print.cancel",
                ],
            )
            request_ids = [result.request_id for result in results]
            self.assertEqual(request_ids, sorted(set(request_ids)))

            emergency = runtime.emergency().result(timeout=1.0)
            self.assertEqual(emergency.response["result"], "ok")
            self.assertTrue(
                any(
                    url.endswith("/printer/emergency_stop")
                    for url, data, timeout in session.posts
                )
            )

            with self.assertRaises(MoonrakerRPCError) as raised:
                runtime.request("test.fail").result(timeout=1.0)
            self.assertEqual(raised.exception.code, 400)
            self.assertFalse(raised.exception.timing.success)
        finally:
            runtime.stop()

    def test_commands_fail_fast_while_connecting_and_are_not_replayed(self):
        subscriptions = {"webhooks": ["state"], "toolhead": ["position"]}
        config = MoonrakerConfig(
            host="fake.local",
            request_timeout=1.0,
            connect_timeout=1.0,
            subscriptions=subscriptions,
        )
        session = DelayedIdentifySession(subscriptions)
        runtime = MoonrakerRuntime(
            config,
            session_factory=lambda **kwargs: session,
        )
        runtime.start()
        try:
            websocket = wait_for(
                lambda: session.websockets[0]
                if session.websockets
                and session.websockets[0].held_identify is not None
                else None
            )
            offline = runtime.request("test.normal", priority=100)
            with self.assertRaises(MoonrakerDisconnectedError):
                offline.result(timeout=0.1)
            emergency = runtime.emergency().result(timeout=1.0)
            self.assertEqual(emergency.response["result"], "ok")
            websocket.release_identify()

            wait_for(lambda: runtime.connected)
            user_methods = [
                payload["method"]
                for payload in websocket.sent
                if payload["method"].startswith("test.")
            ]
            self.assertEqual(user_methods, [])
        finally:
            runtime.stop()

    def test_response_timeout_is_reported_as_unknown_not_cancelled(self):
        runtime, _ = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            pending = runtime.request("test.slow", timeout=0.02)
            with self.assertRaises(MoonrakerRequestTimeout) as raised:
                pending.result(timeout=1.0)
            self.assertTrue(raised.exception.outcome_unknown)
            self.assertEqual(raised.exception.method, "test.slow")
            self.assertTrue(
                any(
                    event.kind == "command_outcome_unknown"
                    for event in runtime.drain_events()
                )
            )
        finally:
            runtime.stop()

    def test_upload_bytes_adds_checksum_and_can_start_print(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            payload = b"G28\nM400\n"
            result = runtime.upload_gcode(
                payload,
                "jobs/sample.gcode",
                checksum=True,
                start=True,
            ).result(timeout=1.0)

            self.assertEqual(result.remote_name, "jobs/sample.gcode")
            self.assertEqual(result.size, len(payload))
            self.assertEqual(result.checksum, hashlib.sha256(payload).hexdigest())
            self.assertTrue(result.started)
            self.assertEqual(
                session.posts[0][0],
                "http://fake.local:7125/server/files/upload",
            )
            fields = {
                field_options["name"]: value
                for field_options, headers, value in session.posts[0][1]._fields
            }
            self.assertEqual(fields["root"], "gcodes")
            self.assertEqual(fields["path"], "jobs")
            self.assertEqual(fields["checksum"], result.checksum)
            self.assertEqual(fields["print"], "true")
            self.assertEqual(fields["file"], payload)
            self.assertTrue(result.print_started)
            self.assertFalse(result.print_queued)
        finally:
            runtime.stop()

    def test_upload_start_requires_ready_idle_monitored_state(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            websocket = session.websockets[0]
            websocket.push(
                {
                    "jsonrpc": "2.0",
                    "method": "notify_status_update",
                    "params": [{"print_stats": {"state": "printing"}}, 2.0],
                }
            )
            wait_for(
                lambda: runtime.state_snapshot()
                .objects.get("print_stats", {})
                .get("state")
                == "printing"
            )

            with self.assertRaises(MoonrakerPreflightError):
                runtime.upload_gcode(
                    b"G28\n",
                    "busy.gcode",
                    start=True,
                ).result(timeout=1.0)
            self.assertFalse(
                any(
                    url.endswith("/server/files/upload")
                    for url, data, timeout in session.posts
                )
            )
        finally:
            runtime.stop()

    def test_upload_queue_response_is_a_distinct_error(self):
        runtime, session = self.make_runtime()
        session.upload_print_started = False
        session.upload_print_queued = True
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            with self.assertRaises(MoonrakerPrintQueuedError):
                runtime.upload_gcode(
                    b"G28\n",
                    "queued.gcode",
                    start=True,
                ).result(timeout=1.0)
        finally:
            runtime.stop()

    def test_websocket_close_reconnects_and_resubscribes(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            first = session.websockets[0]
            first.remote_close()
            wait_for(lambda: len(session.websockets) >= 2)
            wait_for(lambda: runtime.connected)

            second = session.websockets[1]
            methods = [payload["method"] for payload in second.sent]
            self.assertEqual(
                methods[:3],
                [
                    "server.connection.identify",
                    "printer.objects.list",
                    "printer.objects.subscribe",
                ],
            )
            self.assertGreaterEqual(runtime.state_snapshot().connection_attempt, 2)
        finally:
            runtime.stop()

    def test_internal_handshake_disconnect_does_not_report_motion_unknown(self):
        subscriptions = {
            "webhooks": ["state"],
            "toolhead": ["position"],
        }
        config = MoonrakerConfig(
            host="fake.local",
            request_timeout=1.0,
            connect_timeout=1.0,
            reconnect_initial=0.01,
            reconnect_max=0.02,
            subscriptions=subscriptions,
        )
        session = DropDuringObjectListSession(subscriptions)
        runtime = MoonrakerRuntime(
            config,
            session_factory=lambda **kwargs: session,
        )
        runtime.start()
        try:
            wait_for(lambda: len(session.websockets) >= 2)
            wait_for(lambda: runtime.connected)
            self.assertFalse(
                any(
                    event.kind == "command_outcome_unknown"
                    for event in runtime.drain_events()
                )
            )
        finally:
            runtime.stop()

    def test_disconnect_marks_sent_pending_request_outcome_unknown(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            websocket = session.websockets[0]
            pending = runtime.request("test.slow")
            wait_for(
                lambda: any(
                    payload["method"] == "test.slow" for payload in websocket.sent
                )
            )
            websocket.remote_close()

            with self.assertRaises(MoonrakerCommandOutcomeUnknown):
                pending.result(timeout=1.0)
            wait_for(
                lambda: any(
                    timing.method == "test.slow" and not timing.success
                    for timing in runtime.timings_snapshot()
                )
            )
            self.assertTrue(
                any(
                    event.kind == "command_outcome_unknown"
                    for event in runtime.drain_events()
                )
            )
        finally:
            runtime.stop()

    def test_send_failure_does_not_kill_command_worker(self):
        runtime, session = self.make_runtime()
        runtime.start()
        try:
            wait_for(lambda: runtime.connected)
            failed = runtime.request("test.send_fail")
            with self.assertRaises(MoonrakerCommandOutcomeUnknown):
                failed.result(timeout=1.0)
            self.assertTrue(
                any(
                    event.kind == "command_outcome_unknown"
                    for event in runtime.drain_events()
                )
            )

            wait_for(lambda: len(session.websockets) >= 2)
            wait_for(lambda: runtime.connected)
            recovered = runtime.request("test.recovered").result(timeout=1.0)
            self.assertEqual(recovered.method, "test.recovered")
        finally:
            runtime.stop()


if __name__ == "__main__":
    unittest.main()
