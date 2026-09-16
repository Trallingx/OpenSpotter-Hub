from services.klipper_service import MoonrakerClient


class FakeJsonResponse:
    def __init__(self, status_code=200, payload=None, text="ok"):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"result": "ok"}
        self.text = text

    def json(self):
        return self._payload


def test_list_files_uses_moonraker_config_root(monkeypatch):
    calls = []

    def fake_get(url, params, timeout, headers):
        calls.append((url, params, timeout, headers))
        return FakeJsonResponse(payload={"result": [{"path": "printer.cfg"}]})

    monkeypatch.setattr("services.klipper_service.requests.get", fake_get)
    client = MoonrakerClient(
        host="moonraker.local",
        port=7125,
        timeout=10.0,
        route_prefix="proxy",
    )
    client.is_connected = True

    assert client.list_files("config") == [{"path": "printer.cfg"}]
    assert calls == [
        (
            "http://moonraker.local:7125/proxy/server/files/list",
            {"root": "config"},
            10.0,
            {},
        )
    ]


def test_download_file_quotes_path_segments(monkeypatch):
    calls = []

    def fake_get(url, timeout, headers):
        calls.append((url, timeout, headers))
        return FakeJsonResponse(payload={}, text="file content")

    monkeypatch.setattr("services.klipper_service.requests.get", fake_get)
    client = MoonrakerClient(host="moonraker.local", port=7125)
    client.is_connected = True

    assert client.download_file("config", "scripts/my file.py") == {"content": "file content"}
    assert calls == [
        (
            "http://moonraker.local:7125/server/files/config/scripts/my%20file.py",
            10.0,
            {},
        )
    ]


def test_upload_file_content_posts_to_config_subdirectory(monkeypatch):
    calls = []

    def fake_post(url, data, files, timeout, headers):
        file_name, payload = files["file"]
        calls.append((url, data, file_name, payload, timeout, headers))
        return FakeJsonResponse(status_code=201, payload={"result": {"action": "modify_file"}})

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(host="moonraker.local", port=7125, timeout=10.0)
    client.is_connected = True

    assert client.upload_file_content("config", "scripts/bridge.py", "print('ok')") == {
        "result": {"action": "modify_file"}
    }
    assert calls == [
        (
            "http://moonraker.local:7125/server/files/upload",
            {"root": "config", "path": "scripts"},
            "bridge.py",
            b"print('ok')",
            20.0,
            {},
        )
    ]


def test_manage_service_uses_moonraker_machine_endpoint(monkeypatch):
    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append((url, json, timeout, headers))
        return FakeJsonResponse(payload={"result": "ok"})

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(host="moonraker.local", port=7125, timeout=10.0)
    client.is_connected = True

    assert client.manage_service("klipper", "restart") == {"result": "ok"}
    assert calls == [
        (
            "http://moonraker.local:7125/machine/services/restart",
            {"service": "klipper"},
            5.0,
            {},
        )
    ]


def test_restart_klipper_uses_printer_restart_endpoint(monkeypatch):
    calls = []

    def fake_post(url, timeout, headers):
        calls.append((url, timeout, headers))
        return FakeJsonResponse(payload={"result": "ok"})

    monkeypatch.setattr("services.klipper_service.requests.post", fake_post)
    client = MoonrakerClient(host="moonraker.local", port=7125, timeout=10.0)
    client.is_connected = True

    assert client.restart_klipper() == {"result": "ok"}
    assert calls == [
        (
            "http://moonraker.local:7125/printer/restart",
            5.0,
            {},
        )
    ]
