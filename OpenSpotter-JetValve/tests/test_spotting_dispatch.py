import threading

from controllers.spotting_controller import Spot, SpotSequence, SpottingController, SpottingWorker
from utils import AppSignals
from services.klipper_threads import KlipperPublisher


class FakePublisher:
    def __init__(self):
        self.calls = []

    def enqueue_move(self, x, y, z, velocity):
        self.calls.append(("move", x, y, z, velocity))

    def enqueue_script(self, script, completion_key=None):
        self.calls.append(("script", script, completion_key))


class FakeDispatchWorker:
    def __init__(self):
        self.spots = []

    def _dispatch_spot(self, spot):
        self.spots.append(spot)


class FakeStopWorker:
    def __init__(self):
        self.safe_stop_requested = False
        self.wait_ms = None

    def request_stop_safely(self):
        self.safe_stop_requested = True

    def wait(self, ms):
        self.wait_ms = ms
        return True


class FakeStopService:
    is_connected = True

    def __init__(self):
        self.emergency_stop_count = 0
        self.sent = []
        self.disconnected = False

    def emergency_stop(self):
        self.emergency_stop_count += 1
        return True

    def send_gcode(self, script):
        self.sent.append(script)
        return {"queued": True}

    def disconnect(self):
        self.disconnected = True
        self.is_connected = False
        return True


def make_worker(publisher, valve_config):
    return SpottingWorker(
        sequence=[],
        speed_mm_s=1000.0,
        klipper_service=None,
        klipper_publisher=publisher,
        app_signals=None,
        valve_configs=[valve_config],
        valve_schema=[],
        completion_event=threading.Event(),
    )


def make_spot(speed_mm_s=123.4):
    return Spot(
        x=20.0,
        y=20.0,
        speed_mm_s=speed_mm_s,
        valve_id=0,
        grid_index=0,
        row=0,
        col=0,
    )


def test_spot_dispatch_queues_single_shoot_with_position_and_speed():
    publisher = FakePublisher()
    worker = make_worker(
        publisher,
        {
            "id": 0,
            "hold": False,
            "on_ms": 50.7,
            "off_ms": 50.0,
            "cycles": 1,
        },
    )

    worker._dispatch_spot(make_spot())

    assert len(publisher.calls) == 1
    assert publisher.calls[0] == (
        "script",
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0.0 POST_FIRE_WAIT=0.0 "
        "TRIGGER_MODE=mcu X=20.0 Y=20.0 SPEED_MM_S=123.4",
        "0:0:0:20.000,20.000,0",
    )


def test_spot_dispatch_preserves_waits_in_single_shoot_command():
    publisher = FakePublisher()
    worker = make_worker(
        publisher,
        {
            "id": 0,
            "hold": False,
            "pre_fire_wait": 12.5,
            "post_fire_wait": 7.5,
            "on_ms": 50.7,
            "off_ms": 50.0,
            "cycles": 1,
        },
    )

    worker._dispatch_spot(make_spot())

    assert len(publisher.calls) == 1
    assert publisher.calls[0] == (
        "script",
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=12.5 POST_FIRE_WAIT=7.5 "
        "TRIGGER_MODE=mcu X=20.0 Y=20.0 SPEED_MM_S=123.4",
        "0:0:0:20.000,20.000,0",
    )


def test_build_sequence_carries_per_grid_speed():
    controller = SpottingController(AppSignals(), klipper_service=None)
    controller.speed_mm_s = 999.0

    sequence = controller.build_sequence([
        {
            "name": "Slow",
            "active": True,
            "rows": 1,
            "cols": 1,
            "row_spacing": 10.0,
            "col_spacing": 10.0,
            "origin_x": 20.0,
            "origin_y": 20.0,
            "speed_mm_s": 42.5,
            "valve_id": 0,
        },
        {
            "name": "Fallback",
            "active": True,
            "rows": 1,
            "cols": 1,
            "row_spacing": 10.0,
            "col_spacing": 10.0,
            "origin_x": 30.0,
            "origin_y": 20.0,
            "valve_id": 0,
        },
    ])

    assert [spot.speed_mm_s for spot in sequence] == [42.5, 999.0]


def test_build_sequence_is_virtual_for_large_grid():
    controller = SpottingController(AppSignals(), klipper_service=None)

    sequence = controller.build_sequence([
        {
            "name": "Large",
            "active": True,
            "rows": 10000,
            "cols": 1000,
            "row_spacing": 1.0,
            "col_spacing": 1.0,
            "origin_x": 20.0,
            "origin_y": 20.0,
            "speed_mm_s": 1000.0,
            "valve_id": 0,
        },
    ])

    assert isinstance(sequence, SpotSequence)
    assert len(sequence) == 10_000_000
    assert len(sequence._row_segments) == 10000
    assert sequence[0].row == 0
    assert sequence[0].col == 0
    assert sequence[999].row == 0
    assert sequence[999].col == 999
    assert sequence[1000].row == 1
    assert sequence[1000].col == 999

    controller.sequence = sequence
    controller._build_position_completion_path((0.0, 0.0))

    assert controller._position_path_points == [(0.0, 0.0)]
    assert controller._position_spot_distances == []


def test_r2r_progress_keys_are_bounded_to_current_row():
    controller = SpottingController(AppSignals(), klipper_service=None)
    controller._on_mode_changed("roll-to-roll")
    controller.sequence = controller.build_sequence([
        {
            "name": "R2R",
            "active": True,
            "rows": 10000,
            "cols": 10,
            "row_spacing": 1.0,
            "col_spacing": 1.0,
            "origin_x": 20.0,
            "origin_y": 20.0,
            "speed_mm_s": 1000.0,
            "valve_id": 0,
        },
    ])

    for index in range(10):
        controller._current_complete_index = index + 1
        controller._mark_spot_complete(controller.sequence[index])

    assert len(controller.finished_keys) == 10
    assert {
        controller._parse_spot_key_parts(key)[1]
        for key in controller.finished_keys
    } == {0}

    for index in range(10, 20):
        controller._current_complete_index = index + 1
        controller._mark_spot_complete(controller.sequence[index])

    assert len(controller.finished_keys) == 10
    assert {
        controller._parse_spot_key_parts(key)[1]
        for key in controller.finished_keys
    } == {1}


def test_r2r_final_row_keeps_last_two_rows():
    controller = SpottingController(AppSignals(), klipper_service=None)
    controller._on_mode_changed("roll-to-roll")
    controller.sequence = controller.build_sequence([
        {
            "name": "R2R",
            "active": True,
            "rows": 3,
            "cols": 4,
            "row_spacing": 1.0,
            "col_spacing": 1.0,
            "origin_x": 20.0,
            "origin_y": 20.0,
            "speed_mm_s": 1000.0,
            "valve_id": 0,
        },
    ])

    for index in range(12):
        controller._current_complete_index = index + 1
        controller._mark_spot_complete(controller.sequence[index])

    assert len(controller.finished_keys) == 8
    assert {
        controller._parse_spot_key_parts(key)[1]
        for key in controller.finished_keys
    } == {1, 2}


def test_default_dispatch_window_prefills_small_jobs():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(25)
    ]
    controller.worker = worker
    controller.running = True

    controller._pump_dispatch_window()

    assert len(worker.spots) == 25
    assert controller._next_dispatch_index == 25


def test_dispatch_window_caps_large_jobs():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=index // 100,
            col=index % 100,
        )
        for index in range(10000)
    ]
    controller.worker = worker
    controller.running = True
    controller._dispatch_window_cap = 25
    controller._dispatch_window_size = controller._resolve_dispatch_window_size(len(controller.sequence))

    controller._pump_dispatch_window()

    assert controller._dispatch_window_size == 25
    assert len(worker.spots) == 25
    assert controller._next_dispatch_index == 25


def test_mcu_position_dispatch_batches_window_as_multiline_script():
    publisher = FakePublisher()
    worker = make_worker(
        publisher,
        {
            "id": 0,
            "hold": False,
            "on_ms": 16.0,
            "off_ms": 27.0,
            "cycles": 1,
        },
    )
    controller = SpottingController(AppSignals(), klipper_service=None)
    controller.sequence = [
        Spot(
            x=20.0 + index,
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(3)
    ]
    controller.worker = worker
    controller.running = True
    controller._dispatch_window_size = 3

    controller._pump_dispatch_window()

    assert len(publisher.calls) == 1
    assert publisher.calls[0][0] == "script"
    assert publisher.calls[0][2] is None
    assert publisher.calls[0][1].splitlines() == [
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0.0 POST_FIRE_WAIT=0.0 TRIGGER_MODE=mcu X=20.0 Y=20.0 SPEED_MM_S=1000.0",
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0.0 POST_FIRE_WAIT=0.0 TRIGGER_MODE=mcu X=21.0 Y=20.0 SPEED_MM_S=1000.0",
        "SHOOT VALVE=0 HOLD=0 PRE_FIRE_WAIT=0.0 POST_FIRE_WAIT=0.0 TRIGGER_MODE=mcu X=22.0 Y=20.0 SPEED_MM_S=1000.0",
    ]
    assert controller._next_dispatch_index == 3


def test_mcu_position_dispatch_batches_refill_without_queueing_entire_job():
    publisher = FakePublisher()
    worker = make_worker(
        publisher,
        {
            "id": 0,
            "hold": False,
            "on_ms": 16.0,
            "off_ms": 27.0,
            "cycles": 1,
        },
    )
    controller = SpottingController(AppSignals(), klipper_service=None)
    controller.sequence = [
        Spot(
            x=20.0 + index,
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=index // 10,
            col=index % 10,
        )
        for index in range(100)
    ]
    controller.worker = worker
    controller.running = True
    controller._dispatch_window_size = 10
    controller._dispatch_refill_threshold = 5
    controller._dispatch_batch_size = 5
    controller._can_batch_dispatch = lambda: True

    controller._pump_dispatch_window()

    assert len(publisher.calls) == 2
    assert all(len(call[1].splitlines()) == 5 for call in publisher.calls)
    assert controller._next_dispatch_index == 10
    assert controller._next_refill_complete_index == 5

    controller._current_complete_index = 4
    controller._pump_dispatch_window()

    assert len(publisher.calls) == 2
    assert controller._next_dispatch_index == 10

    controller._current_complete_index = 5
    controller._pump_dispatch_window()

    assert len(publisher.calls) == 3
    assert len(publisher.calls[-1][1].splitlines()) == 5
    assert controller._next_dispatch_index == 15
    assert controller._next_refill_complete_index == 10

    controller._current_complete_index = 9
    controller._pump_dispatch_window()

    assert len(publisher.calls) == 3
    assert controller._next_dispatch_index == 15

    controller._current_complete_index = 10
    controller._pump_dispatch_window()

    assert len(publisher.calls) == 4
    assert controller._next_dispatch_index == 20
    assert controller._next_refill_complete_index == 15


def test_dispatch_refill_keeps_outstanding_spots_capped_to_window():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(20)
    ]
    controller.worker = worker
    controller.running = True
    controller._dispatch_window_size = 2
    controller._dispatch_refill_threshold = 1

    controller._pump_dispatch_window()
    assert len(worker.spots) == 2
    assert controller._next_dispatch_index - controller._current_complete_index == 2

    controller._current_complete_index = 1
    controller._pump_dispatch_window()

    assert len(worker.spots) == 3
    assert controller._next_dispatch_index == 3
    assert controller._next_dispatch_index - controller._current_complete_index == 2

    controller._current_complete_index = 2
    controller._pump_dispatch_window()

    assert len(worker.spots) == 4
    assert controller._next_dispatch_index == 4
    assert controller._next_dispatch_index - controller._current_complete_index == 2


def test_stop_is_soft_and_does_not_request_moonraker_emergency_stop():
    service = FakeStopService()
    controller = SpottingController(AppSignals(), klipper_service=service, owns_klipper=False)
    worker = FakeStopWorker()
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True

    controller.stop()

    assert controller.stop_requested
    assert worker.safe_stop_requested
    assert service.emergency_stop_count == 0


def test_stop_marks_local_dispatch_not_running_while_worker_exits():
    service = FakeStopService()
    controller = SpottingController(AppSignals(), klipper_service=service, owns_klipper=False)
    worker = FakeStopWorker()
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True

    controller.stop()

    assert not controller.running
    assert controller.stop_requested
    assert worker.safe_stop_requested


def test_safe_stop_unpauses_worker_so_paused_stop_can_finish():
    worker = make_worker(FakePublisher(), {"id": 0})

    worker.request_pause()
    worker.request_stop_safely()

    assert worker._safe_stop
    assert not worker._paused


def test_shutdown_is_soft_and_does_not_request_moonraker_emergency_stop():
    service = FakeStopService()
    controller = SpottingController(AppSignals(), klipper_service=service, owns_klipper=False)
    worker = FakeStopWorker()
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True

    controller.shutdown()

    assert worker.safe_stop_requested
    assert worker.wait_ms == 3000
    assert service.emergency_stop_count == 0
    assert not controller.running


def test_macro_response_completion_uses_usb_fire_completion_only():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(10)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "macro_response"
    controller._dispatch_window_size = 3
    controller._dispatch_refill_threshold = 2

    controller._pump_dispatch_window()
    controller._on_macro_response_received("// Command {arduino_valve_fire} finished")

    assert len(controller.finished_keys) == 1
    assert controller._current_complete_index == 1
    assert len(worker.spots) == 3
    assert controller._next_dispatch_index == 3

    controller._on_macro_response_received("// Command {arduino_valve_fire} finished")

    assert len(controller.finished_keys) == 2
    assert controller._current_complete_index == 2
    assert len(worker.spots) == 5
    assert controller._next_dispatch_index == 5


def test_dispatch_window_refills_from_position_in_mcu_trigger_mode():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(10)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "position"
    controller._dispatch_window_size = 4
    controller._dispatch_refill_threshold = 2
    controller._build_position_completion_path((-1.0, 20.0))

    controller._pump_dispatch_window()
    controller._on_gantry_position_updated(-1.0, 20.0, 0.0)
    controller._on_gantry_position_updated(0.0, 20.0, 0.0)

    assert len(controller.finished_keys) == 1
    assert controller._current_complete_index == 1
    assert len(worker.spots) == 4
    assert controller._next_dispatch_index == 4

    controller._on_gantry_position_updated(1.0, 20.0, 0.0)

    assert len(controller.finished_keys) == 2
    assert controller._current_complete_index == 2
    assert len(worker.spots) == 6
    assert controller._next_dispatch_index == 6


def test_position_completion_ignores_stale_sample_at_later_spot():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(5)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "position"
    controller._dispatch_window_size = 5
    controller._position_completion_started_at = 100.0
    controller._build_position_completion_path((-1.0, 20.0))

    controller._pump_dispatch_window()
    controller._on_gantry_position_updated(4.0, 20.0, 0.0, sample_time=99.0)

    assert len(controller.finished_keys) == 0
    assert controller._current_complete_index == 0


def test_position_completion_batches_sparse_fresh_sample_along_planned_path():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(5)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "position"
    controller._dispatch_window_size = 5
    controller._position_completion_started_at = 100.0
    controller._build_position_completion_path((-1.0, 20.0))

    controller._pump_dispatch_window()
    controller._on_gantry_position_updated(4.0, 20.0, 0.0, sample_time=101.0)

    assert len(controller.finished_keys) == 5
    assert controller._current_complete_index == 5


def test_dispatch_window_refills_from_command_response_in_mcu_trigger_mode():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(10)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "command_response"
    controller._dispatch_window_size = 3
    controller._dispatch_refill_threshold = 2

    controller._pump_dispatch_window()
    controller._on_gcode_script_queued(101, controller._spot_key(controller.sequence[0]))
    controller._on_gcode_script_queued(102, controller._spot_key(controller.sequence[1]))
    controller._on_gcode_script_completed(101, True, '{"result":"ok"}')

    assert len(controller.finished_keys) == 1
    assert controller._current_complete_index == 1
    assert len(worker.spots) == 3
    assert controller._next_dispatch_index == 3

    controller._on_gcode_script_completed(102, True, '{"result":"ok"}')

    assert len(controller.finished_keys) == 2
    assert controller._current_complete_index == 2
    assert len(worker.spots) == 5
    assert controller._next_dispatch_index == 5


def test_command_response_completion_handles_response_before_queue_signal():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(3)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "command_response"
    controller._dispatch_window_size = 1
    controller._dispatch_refill_threshold = 1

    controller._pump_dispatch_window()
    controller._on_gcode_script_completed(101, True, '{"result":"ok"}')
    controller._on_gcode_script_queued(101, controller._spot_key(controller.sequence[0]))

    assert len(controller.finished_keys) == 1
    assert controller._current_complete_index == 1
    assert len(worker.spots) == 2
    assert controller._next_dispatch_index == 2


def test_command_response_completion_waits_for_in_order_spot():
    controller = SpottingController(AppSignals(), klipper_service=None)
    worker = FakeDispatchWorker()
    controller.sequence = [
        Spot(
            x=float(index),
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=0,
            grid_index=0,
            row=0,
            col=index,
        )
        for index in range(3)
    ]
    controller.worker = worker
    controller.running = True
    controller._spotting_session_active = True
    controller._spotting_completion_source = "command_response"
    controller._dispatch_window_size = 3

    controller._pump_dispatch_window()
    controller._on_gcode_script_queued(101, controller._spot_key(controller.sequence[0]))
    controller._on_gcode_script_queued(102, controller._spot_key(controller.sequence[1]))
    controller._on_gcode_script_completed(102, True, '{"result":"ok"}')

    assert len(controller.finished_keys) == 0
    assert controller._current_complete_index == 0

    controller._on_gcode_script_completed(101, True, '{"result":"ok"}')

    assert len(controller.finished_keys) == 2
    assert controller._current_complete_index == 2


class FakeMcuConfig:
    def get(self, dotted_path, default=None):
        values = {
            "klipper.valve_trigger_mode": "mcu",
            "klipper.spotting_completion_source": "",
        }
        return values.get(dotted_path, default)

    def available_valves(self):
        return [
            {"id": 0, "on_ms": 16.0, "off_ms": 5.0, "cycles": 1},
            {"id": 1, "on_ms": 6.0, "off_ms": 3.0, "cycles": 2},
        ]

    def valve_fields(self):
        return []


class FakeTimingService:
    def __init__(self):
        self.sent = []

    def send_gcode(self, script):
        self.sent.append(script)
        return {"queued": True}


def test_mcu_trigger_mode_preloads_valve_timing_before_spotting():
    service = FakeTimingService()
    controller = SpottingController(AppSignals(), klipper_service=service)
    controller.cm = FakeMcuConfig()
    controller.sequence = [make_spot()]

    assert controller._prepare_valve_timing()
    assert service.sent == ["SET_ARDUINO_VALVE_TIMING VALVE=0 ON_MS=16.0 OFF_MS=5.0 CYCLES=1"]


def test_mcu_trigger_mode_preloads_valve_one_timing_before_spotting():
    service = FakeTimingService()
    controller = SpottingController(AppSignals(), klipper_service=service)
    controller.cm = FakeMcuConfig()
    controller.sequence = [
        make_spot(),
        Spot(
            x=21.0,
            y=20.0,
            speed_mm_s=1000.0,
            valve_id=1,
            grid_index=0,
            row=0,
            col=1,
        ),
    ]

    assert controller._prepare_valve_timing()
    assert service.sent == [
        "SET_ARDUINO_VALVE_TIMING VALVE=0 ON_MS=16.0 OFF_MS=5.0 CYCLES=1",
        "SET_ARDUINO_VALVE_TIMING VALVE=1 ON_MS=6.0 OFF_MS=3.0 CYCLES=2",
    ]


def test_mcu_trigger_mode_defaults_to_position_completion():
    controller = SpottingController(AppSignals(), klipper_service=None)
    controller.cm = FakeMcuConfig()

    assert controller._resolve_spotting_completion_source() == "position"


class FakeMoveService:
    is_connected = True

    def __init__(self):
        self.moves = []
        self.position_polled = False

    def move_gantry(self, x, y, z, velocity):
        self.moves.append((x, y, z, velocity))
        return True

    def get_position(self):
        self.position_polled = True
        return None


def test_publisher_does_not_poll_position_after_move():
    service = FakeMoveService()
    publisher = KlipperPublisher(service)

    publisher.enqueue_move(20.0, 20.0, 0.0, 1000.0)
    publisher.stop()
    publisher.run()

    assert service.moves == [(20.0, 20.0, 0.0, 1000.0)]
    assert not service.position_polled


class FakeScriptService:
    is_connected = True

    def __init__(self):
        self.scripts = []

    def send_gcode(self, script):
        self.scripts.append(script)
        return {"queued": True}


def test_publisher_stop_can_clear_pending_scripts():
    service = FakeScriptService()
    publisher = KlipperPublisher(service)

    publisher.enqueue_script("SHOOT X=1 Y=1")
    publisher.stop(clear_pending=True)
    publisher.run()

    assert service.scripts == []
