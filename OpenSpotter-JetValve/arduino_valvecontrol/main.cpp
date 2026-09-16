#include <Arduino.h>

const uint8_t VALVE_COUNT = 2;
const uint8_t VALVE_OUTPUT_PINS[VALVE_COUNT] = {7, 6};   // VALVE=0 -> D7, VALVE=1 -> D6
const uint8_t TRIGGER_PINS[VALVE_COUNT] = {2, 3};        // VALVE=0 -> D2/INT0, VALVE=1 -> D3/INT1
const unsigned long TICK_US = 100;                       // 0.1 ms per unit from GUI

// Timing ranges (0.1 ms units)
unsigned long onMinTicks = 20;
unsigned long onMaxTicks = 20000;
unsigned long offMinTicks = 20;
unsigned long offMaxTicks = 20000;

// Derived step sizes for the legacy serial tuning commands.
unsigned long onStepTicks = 1;
unsigned long offStepTicks = 1;

struct ValveState {
  unsigned long onTicks;
  unsigned long offTicks;
  unsigned long triggerCycles;
  bool triggerArmed;
  bool pulseActive;
  bool pulseHighPhase;
  unsigned long pulsePhaseStartUs;
  unsigned long pulsesRemaining;
};

ValveState valves[VALVE_COUNT];
uint8_t selectedValve = 0;
volatile bool triggerRequested[VALVE_COUNT] = {false, false};
bool acceptedTriggerLevel[VALVE_COUNT] = {false, false};

void requestTrigger0() {
  triggerRequested[0] = true;
}

void requestTrigger1() {
  triggerRequested[1] = true;
}

unsigned long clampUnsignedLong(unsigned long v, unsigned long lo, unsigned long hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

unsigned long computeStep(unsigned long lo, unsigned long hi) {
  if (hi <= lo) return 1;
  unsigned long span = hi - lo;
  unsigned long step = span / 9;
  if (step == 0) step = 1;
  return step;
}

unsigned long subtractStep(unsigned long value, unsigned long step, unsigned long floorValue) {
  if (value <= floorValue || step >= value - floorValue) {
    return floorValue;
  }
  return value - step;
}

void applyRangeAndClamp() {
  onStepTicks = computeStep(onMinTicks, onMaxTicks);
  offStepTicks = computeStep(offMinTicks, offMaxTicks);
  for (uint8_t valve = 0; valve < VALVE_COUNT; valve++) {
    valves[valve].onTicks = clampUnsignedLong(valves[valve].onTicks, onMinTicks, onMaxTicks);
    valves[valve].offTicks = clampUnsignedLong(valves[valve].offTicks, offMinTicks, offMaxTicks);
  }
}

bool isValidValve(int valve) {
  return valve >= 0 && valve < VALVE_COUNT;
}

String commandPayload(const String &line) {
  if (line.length() > 2 && line.charAt(1) == ':') {
    return line.substring(2);
  }
  if (line.length() > 1) {
    return line.substring(1);
  }
  return "";
}

void handleRangeCommand(const String &payload) {
  int p1 = payload.indexOf(':');
  int p2 = payload.indexOf(':', p1 + 1);
  int p3 = payload.indexOf(':', p2 + 1);
  if (p1 < 0 || p2 < 0 || p3 < 0) {
    Serial.println("ERR bad range format");
    return;
  }

  unsigned long onLo = payload.substring(0, p1).toInt();
  unsigned long onHi = payload.substring(p1 + 1, p2).toInt();
  unsigned long offLo = payload.substring(p2 + 1, p3).toInt();
  unsigned long offHi = payload.substring(p3 + 1).toInt();
  if (onHi <= onLo || offHi <= offLo) {
    Serial.println("ERR range order");
    return;
  }

  onMinTicks = onLo;
  onMaxTicks = onHi;
  offMinTicks = offLo;
  offMaxTicks = offHi;
  applyRangeAndClamp();
}

void startPulses(uint8_t valve, unsigned long count) {
  if (count == 0) {
    Serial.println("ERR pulse count");
    return;
  }

  if (valves[valve].pulseActive) {
    Serial.println("ERR busy");
    return;
  }

  valves[valve].pulsesRemaining = count;
  valves[valve].pulseActive = true;
  valves[valve].pulseHighPhase = true;
  valves[valve].pulsePhaseStartUs = micros();
  digitalWrite(VALVE_OUTPUT_PINS[valve], HIGH);
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  char cmd = line.charAt(0);
  ValveState &valve = valves[selectedValve];

  switch (cmd) {
    case 'V': {
      int requested = commandPayload(line).toInt();
      if (!isValidValve(requested)) {
        Serial.println("ERR valve");
        break;
      }
      selectedValve = static_cast<uint8_t>(requested);
      break;
    }
    case 'E':
      valve.onTicks = subtractStep(valve.onTicks, onStepTicks, onMinTicks);
      break;
    case 'R':
      valve.onTicks = clampUnsignedLong(valve.onTicks + onStepTicks, onMinTicks, onMaxTicks);
      break;
    case 'D':
      valve.offTicks = subtractStep(valve.offTicks, offStepTicks, offMinTicks);
      break;
    case 'F':
      valve.offTicks = clampUnsignedLong(valve.offTicks + offStepTicks, offMinTicks, offMaxTicks);
      break;
    case 'S':
      handleRangeCommand(commandPayload(line));
      break;
    case 'O':
      valve.onTicks = clampUnsignedLong(commandPayload(line).toInt(), onMinTicks, onMaxTicks);
      break;
    case 'P':
      valve.offTicks = clampUnsignedLong(commandPayload(line).toInt(), offMinTicks, offMaxTicks);
      break;
    case 'K': {
      unsigned long count = commandPayload(line).toInt();
      if (count == 0) {
        count = 1;
      }
      startPulses(selectedValve, count);
      break;
    }
    case 'C': {
      unsigned long requested = commandPayload(line).toInt();
      if (requested == 0) {
        Serial.println("ERR trigger cycles");
        break;
      }
      valve.triggerCycles = requested;
      valve.triggerArmed = true;
      acceptedTriggerLevel[selectedValve] = digitalRead(TRIGGER_PINS[selectedValve]) == HIGH;
      break;
    }
    case '?':
      break;
    default:
      Serial.println("ERR unknown");
      break;
  }
}

void consumeTriggerRequests() {
  for (uint8_t valve = 0; valve < VALVE_COUNT; valve++) {
    noInterrupts();
    bool requested = triggerRequested[valve];
    triggerRequested[valve] = false;
    interrupts();

    if (requested && valves[valve].triggerArmed) {
      bool currentLevel = digitalRead(TRIGGER_PINS[valve]) == HIGH;
      if (currentLevel == acceptedTriggerLevel[valve]) {
        continue;
      }
      acceptedTriggerLevel[valve] = currentLevel;
      startPulses(valve, valves[valve].triggerCycles);
    }
  }
}

void updatePulse(uint8_t valve) {
  ValveState &state = valves[valve];
  if (!state.pulseActive) {
    return;
  }

  unsigned long nowUs = micros();
  if (state.pulseHighPhase) {
    if (nowUs - state.pulsePhaseStartUs >= state.onTicks * TICK_US) {
      state.pulseHighPhase = false;
      state.pulsePhaseStartUs = nowUs;
      digitalWrite(VALVE_OUTPUT_PINS[valve], LOW);
    }
    return;
  }

  if (nowUs - state.pulsePhaseStartUs >= state.offTicks * TICK_US) {
    if (state.pulsesRemaining > 1) {
      state.pulsesRemaining--;
      state.pulseHighPhase = true;
      state.pulsePhaseStartUs = nowUs;
      digitalWrite(VALVE_OUTPUT_PINS[valve], HIGH);
    } else {
      state.pulsesRemaining = 0;
      state.pulseActive = false;
      digitalWrite(VALVE_OUTPUT_PINS[valve], LOW);
    }
  }
}

void setup() {
  for (uint8_t valve = 0; valve < VALVE_COUNT; valve++) {
    pinMode(VALVE_OUTPUT_PINS[valve], OUTPUT);
    digitalWrite(VALVE_OUTPUT_PINS[valve], LOW);
    pinMode(TRIGGER_PINS[valve], INPUT);
    acceptedTriggerLevel[valve] = digitalRead(TRIGGER_PINS[valve]) == HIGH;

    valves[valve].onTicks = 100;
    valves[valve].offTicks = 900;
    valves[valve].triggerCycles = 1;
    valves[valve].triggerArmed = false;
    valves[valve].pulseActive = false;
    valves[valve].pulseHighPhase = false;
    valves[valve].pulsePhaseStartUs = 0;
    valves[valve].pulsesRemaining = 0;
  }

  Serial.begin(9600);
  while (!Serial) { }

  applyRangeAndClamp();
  attachInterrupt(digitalPinToInterrupt(TRIGGER_PINS[0]), requestTrigger0, CHANGE);
  attachInterrupt(digitalPinToInterrupt(TRIGGER_PINS[1]), requestTrigger1, CHANGE);
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    handleCommand(line);
  }

  consumeTriggerRequests();

  for (uint8_t valve = 0; valve < VALVE_COUNT; valve++) {
    updatePulse(valve);
  }
}
