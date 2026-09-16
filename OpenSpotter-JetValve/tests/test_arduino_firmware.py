from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARDUINO_MAIN = ROOT / "arduino_valvecontrol" / "main.cpp"


def test_two_valve_firmware_uses_interrupt_trigger_pins():
    text = ARDUINO_MAIN.read_text(encoding="utf-8")

    assert "VALVE_OUTPUT_PINS[VALVE_COUNT] = {7, 6}" in text
    assert "TRIGGER_PINS[VALVE_COUNT] = {2, 3}" in text
    assert "pinMode(TRIGGER_PINS[valve], INPUT)" in text
    assert "INPUT_PULLUP" not in text
    assert "acceptedTriggerLevel[VALVE_COUNT]" in text
    assert "currentLevel == acceptedTriggerLevel[valve]" in text
    assert "attachInterrupt(digitalPinToInterrupt(TRIGGER_PINS[0]), requestTrigger0, CHANGE)" in text
    assert "attachInterrupt(digitalPinToInterrupt(TRIGGER_PINS[1]), requestTrigger1, CHANGE)" in text
    assert "pollTriggerInputs" not in text
