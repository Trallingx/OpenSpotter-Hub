from services.klipper_service import MoonrakerClient


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


def test_emergency_stop_uses_direct_moonraker_endpoint(monkeypatch):
    calls = []

    def fake_post(url, timeout, headers):
        calls.append((url, timeout, headers))
        return FakeResponse(204)

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(
        host="moonraker.local",
        port=7125,
        timeout=10.0,
        headers={"Authorization": "Bearer token"},
        route_prefix="proxy",
    )
    client.is_connected = True

    assert client.emergency_stop()
    assert calls == [
        (
            "http://moonraker.local:7125/proxy/printer/emergency_stop",
            2.0,
            {"Authorization": "Bearer token"},
        )
    ]
    assert client.is_connected is False


def test_emergency_stop_falls_back_to_m112_when_endpoint_fails(monkeypatch):
    calls = []

    def fake_post(url, timeout, headers):
        return FakeResponse(404, "not found")

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(host="moonraker.local", port=7125)
    client.is_connected = True

    def fake_send_gcode(script):
        calls.append(script)
        return {"result": "ok"}

    client.send_gcode = fake_send_gcode

    assert client.emergency_stop()
    assert calls == ["M112"]


def test_cancel_print_uses_moonraker_print_cancel_endpoint(monkeypatch):
    calls = []

    def fake_post(url, timeout, headers):
        calls.append((url, timeout, headers))
        return FakeResponse(200)

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(host="moonraker.local", port=7125, timeout=10.0)
    client.is_connected = True

    assert client.cancel_print()
    assert calls == [("http://moonraker.local:7125/printer/print/cancel", 2.0, {})]


def test_pause_print_uses_moonraker_print_pause_endpoint(monkeypatch):
    calls = []

    def fake_post(url, timeout, headers):
        calls.append((url, timeout, headers))
        return FakeResponse(200)

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(host="moonraker.local", port=7125, timeout=10.0)
    client.is_connected = True

    assert client.pause_print()
    assert calls == [("http://moonraker.local:7125/printer/print/pause", 2.0, {})]
