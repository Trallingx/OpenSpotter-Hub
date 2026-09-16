from controllers.main_controller import MainController


class FakeConfig:
    def __init__(self, script):
        self.script = script

    def get(self, dotted_path, default=None):
        if dotted_path == "klipper.connect_gcode":
            return self.script
        return default


class FakeKlipperService:
    def __init__(self, connected=True):
        self.connected = connected
        self.sent = []

    def connect(self):
        return self.connected

    def send_gcode(self, script):
        self.sent.append(script)
        return {"queued": True}


def test_connect_sends_configured_bridge_start_macro():
    controller = MainController(auto_connect=False)
    controller.cm = FakeConfig("START_ARDUINO_VALVE_BRIDGE")
    controller.klipper_service = FakeKlipperService(connected=True)

    controller._connect_to_klipper()

    assert controller.klipper_service.sent == ["START_ARDUINO_VALVE_BRIDGE"]


def test_connect_gcode_supports_multiple_lines():
    controller = MainController(auto_connect=False)
    controller.cm = FakeConfig("START_ARDUINO_VALVE_BRIDGE\nM115")
    controller.klipper_service = FakeKlipperService(connected=True)

    controller._connect_to_klipper()

    assert controller.klipper_service.sent == ["START_ARDUINO_VALVE_BRIDGE", "M115"]


def test_connect_does_not_send_bridge_macro_when_moonraker_connect_fails():
    controller = MainController(auto_connect=False)
    controller.cm = FakeConfig("START_ARDUINO_VALVE_BRIDGE")
    controller.klipper_service = FakeKlipperService(connected=False)

    controller._connect_to_klipper()

    assert controller.klipper_service.sent == []
