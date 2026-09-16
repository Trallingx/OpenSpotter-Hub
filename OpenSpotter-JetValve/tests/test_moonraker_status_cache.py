import threading

from services.klipper_service import KlipperService
from services.moonraker_websocket import MoonrakerWebSocketClient
from utils import AppSignals


def test_websocket_subscription_result_emits_toolhead_status():
    received = []
    client = MoonrakerWebSocketClient(status_callback=received.append)

    client._handle_status_payload(
        {
            "toolhead": {
                "position": [1.0, 2.0, 3.0, 0.0],
                "homed_axes": "xy",
            }
        }
    )

    assert received == [
        {
            "position": [1.0, 2.0, 3.0],
            "position_source": "toolhead",
            "homed_axes": "xy",
        }
    ]


def test_websocket_subscription_result_emits_motion_report_status():
    received = []
    client = MoonrakerWebSocketClient(status_callback=received.append)

    client._handle_status_payload(
        {
            "motion_report": {
                "live_position": [7.0, 8.0, 9.0, 0.0],
                "live_velocity": 1.25,
            }
        }
    )

    assert received == [
        {
            "position": [7.0, 8.0, 9.0],
            "live_position": [7.0, 8.0, 9.0],
            "position_source": "motion_report",
        }
    ]


def test_websocket_response_emits_command_completion_callback():
    received = []
    client = MoonrakerWebSocketClient(command_response_callback=lambda *args: received.append(args))

    client.command_response_callback(42, True, '{"result":"ok"}')

    assert received == [(42, True, '{"result":"ok"}')]


def test_websocket_ignores_stale_spotter_shoot_done_marker():
    received = []
    client = MoonrakerWebSocketClient(raw_message_callback=received.append)

    client._handle_gcode_response("// SPOTTER_SHOOT_DONE")

    assert received == []


def test_websocket_script_summary_counts_batched_gcode():
    summary = MoonrakerWebSocketClient._script_summary("G1 X1\nG1 X2\n")

    assert summary == "2 line script; first=G1 X1"


def test_klipper_service_caches_websocket_toolhead_status():
    service = KlipperService()
    service.is_connected = True

    service._on_ws_status_update({"position": [4.0, 5.0, 6.0], "homed_axes": "xyz"})

    status = service.get_cached_toolhead_status()
    assert status["connected"] is True
    assert status["cached"] is True
    assert status["position"] == {"x": 4.0, "y": 5.0, "z": 6.0}
    assert status["homed_axes"] == "xyz"
    assert status["position_source"] == "toolhead"


def test_klipper_service_caches_motion_report_live_position():
    service = KlipperService()
    service.is_connected = True

    service._on_ws_status_update({"live_position": [11.0, 12.0, 13.0]})

    status = service.get_cached_toolhead_status()
    assert status["connected"] is True
    assert status["cached"] is True
    assert status["position"] == {"x": 11.0, "y": 12.0, "z": 13.0}
    assert status["position_source"] == "motion_report"


def test_klipper_service_emits_completion_samples_only_for_motion_report():
    signals = AppSignals()
    samples = []
    signals.gantry_position_sample_updated.connect(lambda *args: samples.append(args))
    service = KlipperService(app_signals=signals)
    service.is_connected = True

    service._on_ws_status_update({"position": [4.0, 5.0, 6.0]})
    assert samples == []

    service._on_ws_status_update({"live_position": [7.0, 8.0, 9.0]})
    assert len(samples) == 1
    assert samples[0][:3] == (7.0, 8.0, 9.0)


def test_wait_for_homed_axes_uses_websocket_cache():
    service = KlipperService()
    service.is_connected = True

    timer = threading.Timer(0.01, service._on_ws_status_update, args=({"homed_axes": "xy"},))
    timer.start()
    try:
        status = service.wait_for_homed_axes({"x", "y"}, timeout=0.5)
    finally:
        timer.cancel()

    assert status["connected"] is True
    assert status["homed_axes"] == "xy"
