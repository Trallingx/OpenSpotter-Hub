import concurrent.futures
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.machine import CommandTiming, ConsoleEntry, MachineState, MoonrakerConfig
from app.machine_controller import (
    MachineControlController,
    REQUIRED_REMOTE_COMMANDS,
    artifact_bounds_error,
    artifact_hardware_preflight_error,
    machine_view_from_state,
    start_preflight_error,
)
from app.runtime_job import JobArtifact


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeRoot:
    def __init__(self):
        self.global_locked = FakeVariable(True)
        self._next_id = 0
        self.callbacks = {}

    def after(self, delay, callback):
        self._next_id += 1
        self.callbacks[self._next_id] = (int(delay), callback)
        return self._next_id

    def after_cancel(self, after_id):
        self.callbacks.pop(after_id, None)

    def run_short_callbacks(self):
        for _ in range(100):
            available = [
                (after_id, callback)
                for after_id, (delay, callback) in self.callbacks.items()
                if delay <= 100
            ]
            if not available:
                return
            for after_id, callback in available:
                self.callbacks.pop(after_id, None)
                callback()
        raise AssertionError("short callback queue did not settle")


class FakePanel:
    def __init__(self):
        self.actions = {}
        self.operations = []
        self.control_states = []
        self.gcode_contexts = []
        self.manual_parses = []
        self.consoles = []

    def bind_actions(self, **callbacks):
        self.actions = callbacks

    def set_connection(self, *args, **kwargs):
        self.connection = (args, kwargs)

    def set_operation(self, text, **kwargs):
        self.operations.append((text, kwargs))

    def set_job(self, **kwargs):
        self.job = kwargs

    def set_position(self, *args):
        self.position = args

    def set_live_z(self, value):
        self.live_z = value

    def set_control_state(self, **kwargs):
        self.control_states.append(kwargs)

    def show_gcode_context(self, *args):
        self.gcode_contexts.append(args)

    def set_manual_parse(self, *args, **kwargs):
        self.manual_parses.append((args, kwargs))

    def show_console(self, entries):
        self.consoles.append(tuple(entries))


class ImmediateExecutor:
    def submit(self, function, *args, **kwargs):
        future = concurrent.futures.Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future


def completed(value=None, error=None):
    future = concurrent.futures.Future()
    if error is None:
        future.set_result(value)
    else:
        future.set_exception(error)
    return future


def make_state(
    *,
    revision=1,
    print_state="standby",
    filename="",
    file_position=0,
    offsets_enabled=0,
    virtual_sd_active=None,
    homed_axes="xyz",
    bed_mesh_profile="",
    live_position_fresh=True,
):
    if virtual_sd_active is None:
        virtual_sd_active = print_state in {"printing", "paused"}
    return MachineState(
        revision=revision,
        updated_at=1.0,
        connection_state="connected",
        connection_attempt=1,
        last_error=None,
        objects={
            "webhooks": {"state": "ready", "state_message": ""},
            "toolhead": {
                "position": [10.0, 20.0, 30.0],
                "homed_axes": homed_axes,
                "axis_minimum": [0.0, 0.0, 0.0],
                "axis_maximum": [250.0, 220.0, 150.0],
            },
            "gcode_move": {
                "position": [11.0, 21.0, 31.0],
                "gcode_position": [10.0, 20.0, 30.0],
                "homing_origin": [1.0, 1.0, 1.0],
                "absolute_coordinates": True,
            },
            "motion_report": {"live_position": [11.0, 21.0, 31.0]},
            "bed_mesh": {"profile_name": bed_mesh_profile},
            "print_stats": {
                "state": print_state,
                "filename": filename,
            },
            "pause_resume": {"is_paused": print_state == "paused"},
            "virtual_sdcard": {
                "progress": 0.25,
                "file_position": file_position,
                "is_active": bool(virtual_sd_active),
            },
            "display_status": {"message": "Status"},
            "gcode_macro _OPENSPOTTER_RUNTIME": {
                "prompt": 20,
            },
            "gcode_macro _NEEDLE_TIP_OFFSETS": {
                "enabled": offsets_enabled,
                "surface_z": -0.02,
            },
            "save_variables": {
                "variables": {
                    "tcp_offset_x": 1.0,
                    "tcp_offset_y": 2.0,
                    "tcp_offset_z": 3.0,
                    "tcp_ready": True,
                    "tcp_coordinate_version": 2,
                    "bltouch_state": "loaded",
                }
            },
            "_openspotter_capabilities": {
                "gcode_commands": tuple(sorted(REQUIRED_REMOTE_COMMANDS))
            },
            "_openspotter_live_motion": {
                "epoch": 1,
                "fresh": bool(live_position_fresh),
            },
        },
    )


class FakeRuntime:
    PRIORITY_CONTROL = 0

    def __init__(self, state):
        self.config = MoonrakerConfig(host="printer.local")
        self.state = state
        self.started = True
        self.upload_calls = []
        self.start_calls = []
        self.gcode_calls = []
        self.stop_calls = []
        self.console_entries = []
        self.emergency_calls = 0
        self.cancel_calls = 0
        self._console_sequence = 0

    def state_snapshot(self):
        return self.state

    def console_snapshot(self):
        return tuple(self.console_entries)

    def upload_gcode(self, source, remote_name, **kwargs):
        self.upload_calls.append((source, remote_name, kwargs))
        return completed(SimpleNamespace(elapsed_ms=12.0))

    def start_print(self, remote_name):
        self.start_calls.append(remote_name)
        timing = SimpleNamespace(total_ms=3.0)
        return completed(SimpleNamespace(timing=timing))

    def send_gcode(self, script, **kwargs):
        self.gcode_calls.append((script, kwargs))
        tokens = re.findall(
            r"OPENSPOTTER_MANUAL_(?:BEGIN|END)_[0-9A-F]+",
            script,
        )
        for token in tokens:
            self.append_console(f"openspotter: {token}")
        timing = SimpleNamespace(total_ms=1.0)
        return completed(SimpleNamespace(timing=timing))

    def append_console(self, text, *, level="info"):
        self._console_sequence += 1
        self.console_entries.append(
            ConsoleEntry(
                created_at=1.0,
                text=text,
                level=level,
                sequence=self._console_sequence,
            )
        )

    def pause(self):
        return completed(SimpleNamespace())

    def resume(self):
        return completed(SimpleNamespace())

    def cancel(self):
        self.cancel_calls += 1
        return completed(SimpleNamespace())

    def emergency(self):
        self.emergency_calls += 1
        return completed(SimpleNamespace(elapsed_ms=1.0))

    def stop(self, timeout=0.0):
        self.stop_calls.append(timeout)
        self.started = False
        return True


def make_artifact(directory, text):
    path = Path(directory) / "job.gcode"
    path.write_text(text, encoding="utf-8")
    payload = path.read_bytes()
    offsets = [0]
    for index, value in enumerate(payload):
        if value == 10 and index + 1 < len(payload):
            offsets.append(index + 1)
    digest = hashlib.sha256(payload).hexdigest()
    return JobArtifact(
        kind="grid",
        path=path,
        settings_path=Path(directory) / "job_settings.json",
        sha256=digest,
        size=len(payload),
        remote_path=f"openspotter/grid/{digest}.gcode",
        line_offsets=tuple(offsets),
    )


class MachineViewAndPreflightTests(unittest.TestCase):
    def test_state_projection_and_start_preflight(self):
        view = machine_view_from_state(make_state())

        self.assertEqual(view.position, (11.0, 21.0, 31.0))
        self.assertEqual(view.live_position, (11.0, 21.0, 31.0))
        self.assertTrue(view.live_position_fresh)
        self.assertEqual(view.axis_maximum, (250.0, 220.0, 150.0))
        self.assertEqual(view.tcp_offset, (1.0, 2.0, 3.0))
        self.assertEqual(view.bltouch_state, "loaded")
        self.assertTrue(view.tcp_ready)
        self.assertEqual(view.gcode_position, (10.0, 20.0, 30.0))
        self.assertEqual(view.homing_origin, (1.0, 1.0, 1.0))
        self.assertEqual(view.bed_mesh_profile, "")
        self.assertIn("OPENSPOTTER_CONTRACT_V3", view.gcode_commands)
        self.assertIn("OPENSPOTTER_HOME", view.gcode_commands)
        self.assertIsNone(
            start_preflight_error(view, parameters_locked=True)
        )
        self.assertIn(
            "Lock Global",
            start_preflight_error(view, parameters_locked=False),
        )

    def test_artifact_bounds_include_live_tcp_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(
                directory,
                "G90\nNEEDLE_TIP_OFFSETS_ENABLE\nG0 X250 Y10 Z10\n",
            )
            view = machine_view_from_state(make_state())

            error = artifact_bounds_error(artifact, view)

        self.assertIn("physical 251.0000", error)

    def test_artifact_requires_loaded_probe_and_valid_tcp(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(
                directory,
                "G90\nMESH X_MIN=1 X_MAX=2 Y_MIN=1 Y_MAX=2\n"
                "NEEDLE_TIP_OFFSETS_ENABLE\nG0 X10\n",
            )
            state = make_state()
            state.objects["save_variables"]["variables"]["bltouch_state"] = "parked"
            view = machine_view_from_state(state)

            error = artifact_hardware_preflight_error(artifact, view)

        self.assertIn("BLTouch", error)

    def test_artifact_rejects_ambiguous_traditional_gcode_numbers(self):
        view = machine_view_from_state(make_state())
        with tempfile.TemporaryDirectory() as directory:
            exponent = make_artifact(
                directory,
                "G90\nG0 X1e-6 F600\n",
            )
            exponent_error = artifact_bounds_error(exponent, view)
            equals = make_artifact(
                directory,
                "G90\nG0 X=10 F600\n",
            )
            equals_error = artifact_bounds_error(equals, view)
            plain = make_artifact(
                directory,
                "G90\nG0 X0.000001 F600\n",
            )
            plain_error = artifact_bounds_error(plain, view)

        self.assertIn("unsupported raw G0/G1 parameter 'E'", exponent_error)
        self.assertIn("malformed or ambiguous", equals_error)
        self.assertIsNone(plain_error)


class MachineControllerTests(unittest.TestCase):
    def make_controller(self, runtime, artifact, *, position_sink=None):
        root = FakeRoot()
        panel = FakePanel()
        controller = MachineControlController(
            root,
            panel,
            lambda: runtime.config,
            artifact_executor=ImmediateExecutor(),
            artifact_generator=lambda _snapshot: artifact,
            position_sink=position_sink,
        )
        controller.runtime = runtime
        return controller, root, panel

    def test_canvas_position_sink_uses_only_fresh_homed_live_motion(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            updates = []
            controller, _root, _panel = self.make_controller(
                runtime,
                artifact,
                position_sink=lambda position, axes: updates.append(
                    (position, axes)
                ),
            )

            controller._refresh_state()
            self.assertEqual(updates[-1], ((11.0, 21.0, 31.0), "xyz"))

            runtime.state = make_state(homed_axes="z")
            controller._refresh_state()
            self.assertEqual(updates[-1], (None, "z"))

            runtime.state = make_state(live_position_fresh=False)
            controller._refresh_state()
            self.assertEqual(updates[-1], (None, "xyz"))

    def test_reconnect_clears_canvas_before_waiting_for_runtime_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            runtime.stop = mock.Mock(return_value=False)
            updates = []
            controller, _root, _panel = self.make_controller(
                runtime,
                artifact,
                position_sink=lambda position, axes: updates.append(
                    (position, axes)
                ),
            )
            controller._refresh_state()
            self.assertIsNotNone(updates[-1][0])

            controller.reconnect(runtime.config)

            self.assertEqual(updates[-1], (None, ""))
            runtime.stop.assert_called_once_with(timeout=0.0)

    def test_start_uses_detached_artifact_upload_then_fresh_rpc_start(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(
                directory,
                "G90\nNEEDLE_TIP_OFFSETS_DISABLE\nG0 X10 Y10 Z10\n"
                "NEEDLE_TIP_OFFSETS_ENABLE\nG0 X20 Y20 Z20\n",
            )
            runtime = FakeRuntime(make_state())
            controller, root, panel = self.make_controller(runtime, artifact)
            snapshot = SimpleNamespace(
                kind="grid",
                grids=(object(),),
                spirals=(),
                workflow_json='{"name":"test"}',
            )

            with mock.patch(
                "app.machine_controller.capture_generation_snapshot",
                return_value=snapshot,
            ), mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ):
                controller.start_current_job()
                root.run_short_callbacks()

            self.assertEqual(len(runtime.upload_calls), 1)
            source, remote_name, options = runtime.upload_calls[0]
            self.assertEqual(Path(source), artifact.path)
            self.assertEqual(remote_name, artifact.remote_path)
            self.assertEqual(options["checksum"], artifact.sha256)
            self.assertFalse(options["start"])
            self.assertEqual(runtime.start_calls, [artifact.remote_path])
            self.assertTrue(controller._launch_pending)

            runtime.state = make_state(
                revision=2,
                print_state="printing",
                filename=artifact.remote_path,
                file_position=5,
                offsets_enabled=1,
            )
            controller._refresh_state()
            self.assertFalse(controller._launch_pending)
            self.assertFalse(controller._outcome_unknown)

    def test_launch_confirmation_handles_early_status_and_rejects_stale_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(
                directory,
                "G90\nNEEDLE_TIP_OFFSETS_DISABLE\nG0 X10\n",
            )
            snapshot = SimpleNamespace(
                kind="grid",
                grids=(object(),),
                spirals=(),
                workflow_json='{"name":"test"}',
            )

            runtime = FakeRuntime(make_state())

            def start_with_early_status(remote_name):
                runtime.start_calls.append(remote_name)
                runtime.state = make_state(
                    revision=2,
                    print_state="printing",
                    filename=artifact.remote_path,
                )
                return completed(
                    SimpleNamespace(
                        timing=SimpleNamespace(total_ms=2.0)
                    )
                )

            runtime.start_print = start_with_early_status
            controller, root, _panel = self.make_controller(runtime, artifact)
            with mock.patch(
                "app.machine_controller.capture_generation_snapshot",
                return_value=snapshot,
            ), mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ):
                controller.start_current_job()
                root.run_short_callbacks()
            self.assertFalse(controller._launch_pending)

            stale_runtime = FakeRuntime(
                make_state(
                    revision=5,
                    print_state="complete",
                    filename=artifact.remote_path,
                )
            )
            stale_controller, stale_root, _ = self.make_controller(
                stale_runtime,
                artifact,
            )
            with mock.patch(
                "app.machine_controller.capture_generation_snapshot",
                return_value=snapshot,
            ), mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ):
                stale_controller.start_current_job()
                stale_root.run_short_callbacks()
            self.assertTrue(stale_controller._launch_pending)

    def test_unknown_active_job_reconnect_reuses_current_runtime_config(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(print_state="paused", filename=artifact.remote_path)
            )
            controller, _root, _panel = self.make_controller(runtime, artifact)
            controller._outcome_unknown = True

            with mock.patch.object(controller, "_start_runtime") as start_runtime:
                controller.reconnect(
                    MoonrakerConfig(host="different-printer.local")
                )

            self.assertEqual(start_runtime.call_args.args[0], runtime.config)
            self.assertFalse(controller._outcome_unknown)

    def test_post_upload_hardware_change_blocks_start_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(
                directory,
                "G90\nMESH X_MIN=1 X_MAX=2 Y_MIN=1 Y_MAX=2\nG0 X10\n",
            )
            runtime = FakeRuntime(make_state())

            def upload_then_park_probe(source, remote_name, **kwargs):
                runtime.upload_calls.append((source, remote_name, kwargs))
                changed = make_state(revision=2)
                changed.objects["save_variables"]["variables"][
                    "bltouch_state"
                ] = "parked"
                runtime.state = changed
                return completed(SimpleNamespace(elapsed_ms=10.0))

            runtime.upload_gcode = upload_then_park_probe
            controller, root, panel = self.make_controller(runtime, artifact)
            snapshot = SimpleNamespace(
                kind="grid",
                grids=(object(),),
                spirals=(),
                workflow_json='{"name":"test"}',
            )

            with mock.patch(
                "app.machine_controller.capture_generation_snapshot",
                return_value=snapshot,
            ), mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ), mock.patch(
                "app.machine_controller.messagebox.showerror"
            ):
                controller.start_current_job()
                root.run_short_callbacks()

            self.assertEqual(runtime.start_calls, [])
            self.assertIn("Fresh hardware preflight", panel.operations[-1][0])

    def test_external_filename_hides_local_artifact_context(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(
                    revision=2,
                    print_state="printing",
                    filename="external/job.gcode",
                    file_position=5,
                )
            )
            controller, _root, panel = self.make_controller(runtime, artifact)
            controller.artifact = artifact

            controller._refresh_state()

            self.assertIsNone(panel.gcode_contexts[-1][0])
            self.assertIn("external virtual-SD job", panel.operations[-1][0])

    def test_live_z_uses_guarded_macro_and_timeout_interlocks_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(
                    print_state="printing",
                    filename=artifact.remote_path,
                    offsets_enabled=1,
                )
            )
            controller, root, _panel = self.make_controller(runtime, artifact)

            controller.adjust_live_z(-0.01)
            root.run_short_callbacks()

            self.assertIn(
                "ADJUST_NEEDLE_SURFACE_OFFSET Z_ADJUST=-0.0100 "
                "MOVE=1 SAVE=0 F=300",
                runtime.gcode_calls[0][0],
            )

            timing = CommandTiming(
                request_id=7,
                method="printer.gcode.script",
                queued_at=1.0,
                sent_at=1.0,
                received_at=2.0,
                queue_ms=0.0,
                response_ms=1000.0,
                total_ms=1000.0,
                success=False,
                error="request timeout",
            )
            runtime.state = make_state()
            runtime.send_gcode = mock.Mock(
                return_value=completed(
                    error=__import__(
                        "app.machine",
                        fromlist=["MoonrakerRequestTimeout"],
                    ).MoonrakerRequestTimeout(
                        "printer.gcode.script",
                        7,
                        timing,
                    )
                )
            )
            controller.jog("X", 1.0, 600.0)
            root.run_short_callbacks()
            controller.jog("X", 1.0, 600.0)

            self.assertTrue(controller._outcome_unknown)
            self.assertEqual(runtime.send_gcode.call_count, 1)

    def test_home_rpc_rejection_interlocks_possible_partial_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            runtime.send_gcode = mock.Mock(
                return_value=completed(error=RuntimeError("home failed"))
            )
            controller, root, panel = self.make_controller(runtime, artifact)

            with mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ), mock.patch(
                "app.machine_controller.messagebox.showerror"
            ):
                controller.home()
                root.run_short_callbacks()

            self.assertTrue(controller._outcome_unknown)
            self.assertIn("may have executed partially", panel.operations[-1][0])

    def test_live_z_requires_active_virtual_sd_and_homed_z(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(
                    print_state="printing",
                    virtual_sd_active=False,
                    offsets_enabled=1,
                )
            )
            controller, _root, panel = self.make_controller(runtime, artifact)

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.adjust_live_z(-0.01)
            self.assertEqual(runtime.gcode_calls, [])
            self.assertIn("active virtual-SD", panel.operations[-1][0])

            runtime.state = make_state(
                print_state="printing",
                virtual_sd_active=True,
                offsets_enabled=1,
                homed_axes="xy",
            )
            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.adjust_live_z(-0.01)
            self.assertEqual(runtime.gcode_calls, [])
            self.assertIn("Z must be homed", panel.operations[-1][0])

    def test_missing_remote_macro_and_enabled_offsets_block_jog(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            state = make_state()
            state.objects["_openspotter_capabilities"]["gcode_commands"] = ()
            runtime = FakeRuntime(state)
            controller, _root, panel = self.make_controller(runtime, artifact)

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.jog("X", 1.0, 600.0)

            self.assertEqual(runtime.gcode_calls, [])
            self.assertIn("OPENSPOTTER_JOG", panel.operations[-1][0])

            runtime.state = make_state(offsets_enabled=1)
            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.jog("X", 1.0, 600.0)

            self.assertEqual(runtime.gcode_calls, [])
            self.assertIn("Disable needle tip offsets", panel.operations[-1][0])

    def test_missing_immutable_contract_marker_blocks_home_and_jog(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            state = make_state()
            commands = set(
                state.objects["_openspotter_capabilities"]["gcode_commands"]
            )
            commands.remove("OPENSPOTTER_CONTRACT_V3")
            state.objects["_openspotter_capabilities"][
                "gcode_commands"
            ] = tuple(sorted(commands))
            runtime = FakeRuntime(state)
            controller, _root, panel = self.make_controller(runtime, artifact)

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.jog("X", 1.0, 600.0)
                controller.home()

            self.assertEqual(runtime.gcode_calls, [])
            self.assertTrue(
                any(
                    "OPENSPOTTER_CONTRACT_V3" in operation[0]
                    for operation in panel.operations
                )
            )

    def test_manual_gcode_parses_wraps_and_confirms_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            controller, root, panel = self.make_controller(runtime, artifact)
            script = "; test\nG91\r\nG0 X1 F300\r\nG90\r\n"

            with mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ):
                controller.send_manual_gcode(script)
                root.run_short_callbacks()

            wire_script = runtime.gcode_calls[-1][0]
            self.assertIn("; test\nG91\nG0 X1 F300\nG90", wire_script)
            self.assertRegex(
                wire_script,
                r"OPENSPOTTER_MANUAL_BEGIN_[0-9A-F]+",
            )
            self.assertRegex(
                wire_script,
                r"OPENSPOTTER_MANUAL_END_[0-9A-F]+",
            )
            self.assertIn("\nM400\n", wire_script)
            self.assertTrue(panel.manual_parses)
            self.assertIn("Manual G-code completed", panel.operations[-1][0])

    def test_manual_gcode_is_blocked_during_virtual_sd_job(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(
                    print_state="printing",
                    filename=artifact.remote_path,
                )
            )
            controller, _root, panel = self.make_controller(runtime, artifact)

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("M105")

            self.assertEqual(runtime.gcode_calls, [])
            self.assertIn("virtual-SD job is active", panel.operations[-1][0])

    def test_manual_m112_uses_http_emergency_and_never_gcode_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            controller, root, _panel = self.make_controller(runtime, artifact)

            controller.send_manual_gcode("N7M112*9")
            root.run_short_callbacks()

            self.assertEqual(runtime.gcode_calls, [])
            self.assertEqual(runtime.emergency_calls, 1)
            self.assertTrue(controller._outcome_unknown)

    def test_manual_raw_motion_requires_mode_feed_bounds_and_clean_transforms(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            controller, _root, panel = self.make_controller(runtime, artifact)

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("G0 X12 F300")
            self.assertIn("explicit G90 or G91", panel.operations[-1][0])

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("G90\nG0 X12")
            self.assertIn("explicit F feed", panel.operations[-1][0])

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("G90\nG0 X999 F300")
            self.assertIn("outside live limits", panel.operations[-1][0])

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("G90\nG0 X=nan F=nan")
            self.assertIn("malformed parameter", panel.operations[-1][0])

            for mismatched in (
                "G90\nG0 X1e2 F600",
                "G90\nG0 X12 F6e2",
                "G90\nG0 X=12 F600",
            ):
                with self.subTest(mismatched=mismatched), mock.patch(
                    "app.machine_controller.messagebox.showerror"
                ):
                    controller.send_manual_gcode(mismatched)
                self.assertTrue(
                    "blocked E" in panel.operations[-1][0]
                    or "malformed parameter" in panel.operations[-1][0]
                )

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("G90\nG0 X12 X13 F300")
            self.assertIn("duplicate X", panel.operations[-1][0])

            runtime.state = make_state(bed_mesh_profile="default")
            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.send_manual_gcode("G90\nG0 X12 F300")
            self.assertIn("active bed mesh", panel.operations[-1][0])
            self.assertEqual(runtime.gcode_calls, [])

    def test_standby_virtual_sd_cursor_blocks_home_and_jog(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(
                    print_state="standby",
                    virtual_sd_active=True,
                )
            )
            controller, _root, panel = self.make_controller(runtime, artifact)

            with mock.patch("app.machine_controller.messagebox.showerror"):
                controller.home()
                controller.jog("X", 1.0, 600.0)

            self.assertEqual(runtime.gcode_calls, [])
            self.assertIn("ready and idle", panel.operations[-1][0])

    def test_standby_virtual_sd_cursor_still_allows_cancel_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(
                make_state(
                    print_state="standby",
                    virtual_sd_active=True,
                )
            )
            controller, root, _panel = self.make_controller(runtime, artifact)

            with mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ):
                controller.cancel_job()
                root.run_short_callbacks()

            self.assertEqual(runtime.cancel_calls, 1)

    def test_emergency_keeps_prior_unknown_interlock_latched(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            controller, root, panel = self.make_controller(runtime, artifact)
            controller._outcome_unknown = True

            controller.emergency_stop()
            root.run_short_callbacks()

            self.assertTrue(controller._outcome_unknown)
            self.assertEqual(runtime.emergency_calls, 1)
            self.assertIn("remain interlocked", panel.operations[-1][0])

    def test_manual_console_error_after_begin_interlocks_partial_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())

            def reject_after_begin(script, **kwargs):
                runtime.gcode_calls.append((script, kwargs))
                begin = re.search(
                    r"OPENSPOTTER_MANUAL_BEGIN_[0-9A-F]+",
                    script,
                )
                runtime.append_console(f"openspotter: {begin.group(0)}")
                runtime.append_console(
                    "!! simulated move rejection",
                    level="error",
                )
                return completed(
                    SimpleNamespace(timing=SimpleNamespace(total_ms=1.0))
                )

            runtime.send_gcode = reject_after_begin
            controller, root, panel = self.make_controller(runtime, artifact)
            with mock.patch(
                "app.machine_controller.messagebox.askyesno",
                return_value=True,
            ), mock.patch(
                "app.machine_controller.messagebox.showerror"
            ):
                controller.send_manual_gcode("G90\nG0 X12 F300")
                root.run_short_callbacks()

            self.assertTrue(controller._outcome_unknown)
            self.assertIn("partial execution", panel.operations[-1][0].lower())
            self.assertNotIn("completed", panel.operations[-1][0].lower())

    def test_success_callback_failure_releases_normal_busy_state(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(directory, "G90\nG0 X10\n")
            runtime = FakeRuntime(make_state())
            controller, root, panel = self.make_controller(runtime, artifact)
            token = controller._begin_operation("testing")

            controller._watch_future(
                completed("ok"),
                token=token,
                on_success=lambda _result: (_ for _ in ()).throw(
                    RuntimeError("callback failed")
                ),
                title="Callback",
            )
            with mock.patch("app.machine_controller.messagebox.showerror"):
                root.run_short_callbacks()

            self.assertFalse(controller._operation_busy)
            self.assertIn("callback failed", panel.operations[-1][0])


if __name__ == "__main__":
    unittest.main()
