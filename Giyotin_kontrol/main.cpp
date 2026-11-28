/*
 * Giyotin V2 - Nano controller, no-blade servo-cycle prototype.
 *
 * SAFETY BOUNDARY:
 * - The user confirmed the blade is not attached for this prototype.
 * - A valid cycle moves the unloaded servo between two configured angles.
 * - D9 servo output is enabled only after all run conditions and a valid
 *   dual-button press. The two Nano button inputs are process conditions,
 *   not a certified machine-safety device.
 *
 * Hardware inputs: D2 and D3, active-low, using INPUT_PULLUP.
 * Servo signal: D9. Use an appropriate external servo supply and common GND.
 * ESP32 link: Nano D0/RX and D1/TX, 9600 baud, newline-delimited ASCII.
 * D0/D1 are shared with the Nano USB-serial adapter: disconnect USB while
 * the ESP32 UART is attached; disconnect the UART wires while uploading.
 */

#include <Arduino.h>
#include <EEPROM.h>
#include <Servo.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

namespace {

constexpr uint8_t BUTTON_1_PIN = 2;
constexpr uint8_t BUTTON_2_PIN = 3;
constexpr uint32_t SERIAL_BAUD = 9600;
constexpr uint32_t BUTTON_PRESS_DEBOUNCE_MS = 10;
constexpr uint32_t BUTTON_RELEASE_DEBOUNCE_MS = 25;
constexpr uint32_t RELEASE_STABLE_MS = 50;

// Input limits for this no-blade prototype only.
// These are not approved machine operating or safety limits.
constexpr uint32_t MAX_BUTTON_WINDOW_MS = 5000;
constexpr uint32_t MAX_CYCLE_DURATION_MS = 60000;
constexpr uint32_t MAX_CUTS_PER_BOX = 1000;
constexpr uint32_t MIN_CYCLE_DURATION_MS = 1000;
constexpr uint8_t SERVO_PIN = 9;
constexpr uint8_t DEFAULT_HOME_ANGLE = 150;
constexpr uint8_t DEFAULT_CYCLE_ANGLE = 0;
constexpr uint16_t DEFAULT_SERVO_SPEED = 150;
constexpr uint16_t MIN_SERVO_SPEED = 5;
constexpr uint16_t MAX_SERVO_SPEED = 360;
constexpr uint32_t PERMIT_TIMEOUT_MS = 15000;
constexpr uint32_t INITIAL_HOME_MS = 400;
constexpr uint8_t CALIBRATION_MARK = 0xC3;
constexpr uint8_t EVENT_RECORD_MARK = 0xE7;
constexpr uint32_t EVENT_RETRY_MS = 3000;
constexpr int EVENT_JOURNAL_BASE = 64;
constexpr uint8_t EVENT_JOURNAL_SLOTS = 24;

constexpr size_t COMMAND_CAPACITY = 160;
constexpr size_t PERMIT_ID_CAPACITY = 32;
constexpr size_t SESSION_ID_CAPACITY = 17;
constexpr size_t EVENT_ID_CAPACITY = 32;

struct ButtonInput {
  uint8_t pin;
  bool rawHigh;
  bool stableHigh;
  uint32_t rawChangedAt;
  uint32_t pressedAt;
  bool pressEdge;
  bool releaseEdge;
};

struct MachineConfig {
  bool loaded;
  uint32_t revision;
  uint32_t buttonWindowMs;
  uint32_t cycleDurationMs;
  uint32_t cutsPerBox;
  uint8_t homeAngle;
  uint8_t cycleAngle;
};

struct RunPermit {
  bool active;
  uint32_t permitId;
};

enum EventJournalState : uint8_t {
  EVENT_EMPTY = 0,
  EVENT_IN_PROGRESS = 1,
  EVENT_COMPLETED = 2,
  EVENT_ACKNOWLEDGED = 3,
};

struct EventRecord {
  uint8_t marker;
  uint32_t generation;
  uint32_t cycleSequence;
  uint32_t permitId;
  char sessionId[SESSION_ID_CAPACITY];
  uint8_t state;
  uint16_t checksum;
};

struct CalibrationRecord {
  uint16_t generation;
  uint16_t speed;
  uint8_t home;
  uint8_t lower;
  uint16_t checksum;
};

ButtonInput button1 = {BUTTON_1_PIN, true, true, 0, 0, false, false};
ButtonInput button2 = {BUTTON_2_PIN, true, true, 0, 0, false, false};

MachineConfig config = {true, 1, 500, 2000, 2, DEFAULT_HOME_ANGLE, DEFAULT_CYCLE_ANGLE};
RunPermit permit = {false, 0};
char commandSession[SESSION_ID_CAPACITY] = "";
uint32_t lastPermitId = 0;
int8_t lastPermitValue = -1;
EventRecord latestEventRecord = {};
int8_t latestEventSlot = -1;
bool pendingEvent = false;
bool pendingEventUncertain = false;
char pendingEventId[EVENT_ID_CAPACITY] = "";
uint32_t lastEventRetryAt = 0;
Servo cycleServo;
uint16_t servoSpeed = DEFAULT_SERVO_SPEED;
int8_t calibrationSlot = -1;
uint16_t calibrationGeneration = 0;
uint32_t lastPermitAt = 0;

char commandBuffer[COMMAND_CAPACITY];
size_t commandLength = 0;
bool commandOverflow = false;

bool cycleRunning = false;
uint32_t cycleStartedAt = 0;
uint32_t activeCycleDurationMs = 0;
uint32_t activeCycleConfigRevision = 0;
uint8_t activeHomeAngle = DEFAULT_HOME_ANGLE;
uint8_t commandedAngle = DEFAULT_HOME_ANGLE;
bool angleCommanded = false;
uint32_t activeHomeLeadMs = 0;
uint32_t activeTravelMs = 0;
bool returningHome = false;
uint32_t cycleSequence = 0;
char activeCycleId[EVENT_ID_CAPACITY + PERMIT_ID_CAPACITY];
char activeCycleSessionId[SESSION_ID_CAPACITY] = "";
uint32_t activeCyclePermitId = 0;

bool pairArmed = false;
bool bothReleasedTracking = false;
uint32_t bothReleasedSince = 0;
bool pairPending = false;
uint8_t firstPressedButton = 0;
uint32_t firstPressedAt = 0;

static_assert(EVENT_JOURNAL_BASE + EVENT_JOURNAL_SLOTS * sizeof(EventRecord) <= 1024,
              "Event journal exceeds ATmega328P EEPROM");

bool elapsedAtLeast(uint32_t now, uint32_t startedAt, uint32_t duration) {
  return static_cast<uint32_t>(now - startedAt) >= duration;
}

uint16_t calibrationChecksum(const CalibrationRecord &record) {
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&record);
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < offsetof(CalibrationRecord, checksum); ++i) {
    crc ^= bytes[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 1U) ? (crc >> 1) ^ 0xA001U : crc >> 1;
    }
  }
  return crc;
}

bool validCalibration(uint32_t home, uint32_t lower, uint32_t speed) {
  return home <= 180 && lower <= 180 && home != lower &&
         speed >= MIN_SERVO_SPEED && speed <= MAX_SERVO_SPEED;
}

int calibrationAddress(uint8_t slot) {
  return slot * (1 + sizeof(CalibrationRecord));
}

void loadCalibration() {
  for (uint8_t slot = 0; slot < 2; ++slot) {
    const int address = calibrationAddress(slot);
    CalibrationRecord record;
    if (EEPROM.read(address) != CALIBRATION_MARK) continue;
    EEPROM.get(address + 1, record);
    if (!validCalibration(record.home, record.lower, record.speed) ||
        record.checksum != calibrationChecksum(record)) continue;
    if (calibrationSlot >= 0 &&
        static_cast<int16_t>(record.generation - calibrationGeneration) <= 0) continue;
    calibrationSlot = slot;
    calibrationGeneration = record.generation;
    config.homeAngle = record.home;
    config.cycleAngle = record.lower;
    servoSpeed = record.speed;
  }
}

void saveCalibration(uint8_t home, uint8_t lower, uint16_t speed) {
  if (calibrationSlot >= 0 && config.homeAngle == home &&
      config.cycleAngle == lower && servoSpeed == speed) return;
  const uint8_t slot = calibrationSlot == 0 ? 1 : 0;
  const int address = calibrationAddress(slot);
  CalibrationRecord record = {static_cast<uint16_t>(calibrationGeneration + 1U),
                              speed, home, lower, 0};
  record.checksum = calibrationChecksum(record);
  EEPROM.update(address, 0);
  EEPROM.put(address + 1, record);
  EEPROM.update(address, CALIBRATION_MARK);
  calibrationSlot = slot;
  calibrationGeneration = record.generation;
  config.homeAngle = home;
  config.cycleAngle = lower;
  servoSpeed = speed;
}

uint16_t eventChecksum(const EventRecord &record) {
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&record);
  uint16_t crc = 0xFFFF;
  for (size_t i = offsetof(EventRecord, generation); i < offsetof(EventRecord, state); ++i) {
    crc ^= bytes[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 1U) ? (crc >> 1) ^ 0xA001U : crc >> 1;
    }
  }
  return crc;
}

int eventRecordAddress(uint8_t slot) {
  return EVENT_JOURNAL_BASE + slot * sizeof(EventRecord);
}

void formatEventId(char *destination, size_t capacity, const char *sessionId,
                   uint32_t permitId) {
  snprintf(destination, capacity, "%s-%lu", sessionId,
           static_cast<unsigned long>(permitId));
}

void loadEventJournal() {
  latestEventSlot = -1;
  latestEventRecord = {};
  for (uint8_t slot = 0; slot < EVENT_JOURNAL_SLOTS; ++slot) {
    const int address = eventRecordAddress(slot);
    if (EEPROM.read(address) != EVENT_RECORD_MARK) continue;
    EventRecord record;
    EEPROM.get(address, record);
    if (record.marker != EVENT_RECORD_MARK ||
        record.checksum != eventChecksum(record) ||
        record.sessionId[SESSION_ID_CAPACITY - 1] != '\0' ||
        record.state < EVENT_IN_PROGRESS || record.state > EVENT_ACKNOWLEDGED) continue;
    if (latestEventSlot >= 0 &&
        static_cast<int32_t>(record.generation - latestEventRecord.generation) <= 0) continue;
    latestEventRecord = record;
    latestEventSlot = slot;
  }

  if (latestEventSlot < 0) {
    cycleSequence = 0;
    pendingEvent = false;
    return;
  }

  cycleSequence = latestEventRecord.cycleSequence;
  if (latestEventRecord.state == EVENT_IN_PROGRESS ||
      latestEventRecord.state == EVENT_COMPLETED) {
    pendingEvent = true;
    pendingEventUncertain = latestEventRecord.state == EVENT_IN_PROGRESS;
    formatEventId(pendingEventId, sizeof(pendingEventId), latestEventRecord.sessionId,
                  latestEventRecord.permitId);
  }
}

bool writeEventRecord(uint32_t sequence, uint32_t permitId, const char *sessionId,
                      EventJournalState state) {
  if (sessionId == nullptr || strlen(sessionId) >= SESSION_ID_CAPACITY) return false;
  const uint8_t slot = latestEventSlot < 0
                           ? 0
                           : static_cast<uint8_t>((latestEventSlot + 1) % EVENT_JOURNAL_SLOTS);
  const int address = eventRecordAddress(slot);
  EventRecord record = {};
  record.marker = EVENT_RECORD_MARK;
  record.generation = latestEventSlot < 0 ? 1 : latestEventRecord.generation + 1U;
  record.cycleSequence = sequence;
  record.permitId = permitId;
  strncpy(record.sessionId, sessionId, sizeof(record.sessionId) - 1);
  record.state = state;
  record.checksum = eventChecksum(record);

  // Mark invalid first and write the marker last so a reset cannot expose a partial record.
  EEPROM.update(address, 0);
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&record);
  for (size_t i = 1; i < sizeof(record); ++i) EEPROM.update(address + i, bytes[i]);
  EEPROM.update(address, EVENT_RECORD_MARK);
  latestEventRecord = record;
  latestEventSlot = slot;
  cycleSequence = sequence;
  return true;
}

bool setLatestEventState(EventJournalState state) {
  if (latestEventSlot < 0) return false;
  const int address = eventRecordAddress(static_cast<uint8_t>(latestEventSlot));
  EEPROM.update(address + offsetof(EventRecord, state), static_cast<uint8_t>(state));
  latestEventRecord.state = state;
  return true;
}

bool parseUnsigned(const char *text, uint32_t &value) {
  if (text == nullptr || *text == '\0') return false;
  for (const char *cursor = text; *cursor != '\0'; ++cursor) {
    if (*cursor < '0' || *cursor > '9') return false;
  }
  char *end = nullptr;
  const unsigned long parsed = strtoul(text, &end, 10);
  if (end == text || *end != '\0' || parsed > 0xFFFFFFFFUL) return false;
  value = static_cast<uint32_t>(parsed);
  return true;
}

bool parseBoolean01(const char *text, bool &value) {
  if (text == nullptr) return false;
  if (strcmp(text, "0") == 0) {
    value = false;
    return true;
  }
  if (strcmp(text, "1") == 0) {
    value = true;
    return true;
  }
  return false;
}

bool copySafeToken(char *destination, size_t capacity, const char *source) {
  if (destination == nullptr || source == nullptr || capacity == 0) return false;
  const size_t length = strlen(source);
  if (length == 0 || length >= capacity) return false;
  for (size_t i = 0; i < length; ++i) {
    const char c = source[i];
    const bool allowed = (c >= 'a' && c <= 'z') ||
                         (c >= 'A' && c <= 'Z') ||
                         (c >= '0' && c <= '9') ||
                         c == '-' || c == '_' || c == '.';
    if (!allowed) return false;
  }
  memcpy(destination, source, length + 1);
  return true;
}

void printAck(const char *name, uint32_t revision = 0) {
  Serial.print(F("ACK|"));
  Serial.print(name);
  if (revision > 0) {
    Serial.print(F("|revision="));
    Serial.print(revision);
  }
  Serial.println();
}

void printNack(const char *reason) {
  Serial.print(F("NACK|"));
  Serial.println(reason);
}

void printState();
void rejectButtonPair(const char *reason);

bool permitAllowsCycle() {
  return config.loaded && commandSession[0] != '\0' && permit.active && !pendingEvent &&
         !elapsedAtLeast(millis(), lastPermitAt, PERMIT_TIMEOUT_MS);
}

const char *stateName() {
  if (cycleRunning) return "CYCLE_RUNNING";
  if (!config.loaded) return "CONFIG_REQUIRED";
  if (!commandSession[0]) return "SESSION_REQUIRED";
  if (pendingEvent) return pendingEventUncertain ? "CYCLE_UNCERTAIN" : "EVENT_PENDING";
  if (!permit.active) return "PERMIT_REQUIRED";
  if (pairPending) return "WAIT_SECOND_BUTTON";
  if (!pairArmed) return "WAIT_RELEASE";
  return "READY";
}

void printState() {
  Serial.print(F("STATUS|mode=SERVO_TEST_NO_BLADE|protocol=4|state="));
  Serial.print(stateName());
  Serial.print(F("|session_id="));
  Serial.print(commandSession);
  Serial.print(F("|permit_id="));
  Serial.print(permit.permitId);
  Serial.print(F("|permit_active="));
  Serial.print(permitAllowsCycle() ? 1 : 0);
  Serial.print(F("|cycle_busy="));
  Serial.print(cycleRunning ? 1 : 0);
  Serial.print(F("|cycle_seq="));
  Serial.print(cycleSequence);
  Serial.print(F("|event_pending="));
  Serial.print(pendingEvent ? 1 : 0);
  Serial.print(F("|event_id="));
  Serial.print(pendingEventId);
  Serial.print(F("|event_state="));
  Serial.print(pendingEventUncertain ? "uncertain" : (pendingEvent ? "completed" : "none"));
  Serial.print(F("|config_revision="));
  Serial.print(config.revision);
  Serial.print(F("|button_window_ms="));
  Serial.print(config.buttonWindowMs);
  Serial.print(F("|cycle_duration_ms="));
  Serial.print(config.cycleDurationMs);
  Serial.print(F("|cuts_per_box="));
  Serial.print(config.cutsPerBox);
  Serial.print(F("|home_angle="));
  Serial.print(config.homeAngle);
  Serial.print(F("|cycle_angle="));
  Serial.print(config.cycleAngle);
  Serial.print(F("|servo_speed_dps="));
  Serial.print(servoSpeed);
  Serial.print(F("|calibration_saved="));
  Serial.print(calibrationSlot >= 0);
  Serial.print(F("|angle_commanded="));
  if (angleCommanded) Serial.print(commandedAngle);
  Serial.print(F("|d2_pressed="));
  Serial.print(!button1.stableHigh);
  Serial.print(F("|d3_pressed="));
  Serial.print(!button2.stableHigh);
  Serial.print(F("|phase="));
  if (!cycleRunning) Serial.print(F("IDLE"));
  else if (returningHome) Serial.print(F("RAISING"));
  else {
    const uint32_t elapsed = millis() - cycleStartedAt;
    if (elapsed < activeHomeLeadMs) Serial.print(F("HOMING"));
    else if (elapsed < activeHomeLeadMs + activeTravelMs) Serial.print(F("LOWERING"));
    else Serial.print(F("HOLD"));
  }
  Serial.print(F("|permit_active="));
  Serial.println(permitAllowsCycle());
}

void printEvent(const char *eventName, const char *cycleId) {
  Serial.print(F("EVENT|"));
  Serial.print(eventName);
  Serial.print(F("|cycle_id="));
  Serial.print(cycleId);
  if (strcmp(eventName, "CYCLE_COMPLETED") == 0) {
    char eventId[EVENT_ID_CAPACITY];
    formatEventId(eventId, sizeof(eventId), activeCycleSessionId, activeCyclePermitId);
    Serial.print(F("|event_id="));
    Serial.print(eventId);
  }
  Serial.print(F("|session_id="));
  Serial.print(activeCycleSessionId);
  Serial.print(F("|cycle_seq="));
  Serial.print(cycleSequence);
  Serial.print(F("|permit_id="));
  Serial.print(activeCyclePermitId);
  Serial.print(F("|config_revision="));
  Serial.print(activeCycleConfigRevision);
  Serial.println();
}

void printPendingEvent() {
  if (!pendingEvent) return;
  Serial.print(F("EVENT|"));
  Serial.print(pendingEventUncertain ? "CYCLE_UNCERTAIN" : "CYCLE_COMPLETED");
  Serial.print(F("|event_id="));
  Serial.print(pendingEventId);
  Serial.print(F("|session_id="));
  Serial.print(latestEventRecord.sessionId);
  Serial.print(F("|cycle_seq="));
  Serial.print(latestEventRecord.cycleSequence);
  Serial.print(F("|permit_id="));
  Serial.print(latestEventRecord.permitId);
  Serial.print(F("|config_revision="));
  Serial.println(config.revision);
}

void beginCycle(uint32_t now) {
  if (cycleRunning || !permitAllowsCycle()) return;

  activeHomeLeadMs = !angleCommanded || commandedAngle != config.homeAngle ? INITIAL_HOME_MS : 0;
  if (!cycleServo.attached()) {
    cycleServo.write(config.homeAngle);
    cycleServo.attach(SERVO_PIN);
  }
  if (!cycleServo.attached()) {
    rejectButtonPair("SERVO_ATTACH_FAILED");
    return;
  }

  const uint32_t nextCycleSequence = cycleSequence + 1U;
  if (!writeEventRecord(nextCycleSequence, permit.permitId, commandSession,
                        EVENT_IN_PROGRESS)) {
    rejectButtonPair("EVENT_JOURNAL_WRITE_FAILED");
    return;
  }

  cycleRunning = true;
  permit.active = false;  // One MES grant authorizes one cycle only.
  cycleStartedAt = now;
  const uint32_t travelDegrees = abs(static_cast<int>(config.homeAngle) - config.cycleAngle);
  activeTravelMs = (travelDegrees * 1000UL + servoSpeed - 1) / servoSpeed;
  const uint32_t minimumCycleMs = activeTravelMs * 2UL;
  activeCycleDurationMs = max(config.cycleDurationMs, minimumCycleMs);
  activeCycleConfigRevision = config.revision;
  activeCyclePermitId = permit.permitId;
  strncpy(activeCycleSessionId, commandSession, sizeof(activeCycleSessionId) - 1);
  activeCycleSessionId[sizeof(activeCycleSessionId) - 1] = '\0';
  activeHomeAngle = config.homeAngle;
  returningHome = false;
  commandedAngle = activeHomeAngle;
  angleCommanded = true;
  cycleServo.write(commandedAngle);
  snprintf(activeCycleId, sizeof(activeCycleId), "%s-%lu-%lu", activeCycleSessionId,
           static_cast<unsigned long>(activeCyclePermitId),
           static_cast<unsigned long>(cycleSequence));
  printEvent("CYCLE_STARTED", activeCycleId);
  printEvent("CUT_DOWN", activeCycleId);
}

void moveToward(uint8_t from, uint8_t to, uint32_t elapsed) {
  const int distance = static_cast<int>(to) - from;
  const uint32_t degrees = min(abs(distance) * 1UL, elapsed * servoSpeed / 1000UL);
  const uint8_t angle = distance < 0 ? from - degrees : from + degrees;
  if (angle == commandedAngle) return;
  commandedAngle = angle;
  cycleServo.write(angle);
}

void completeCycle() {
  if (!cycleRunning) return;

  cycleRunning = false;
  setLatestEventState(EVENT_COMPLETED);
  pendingEvent = true;
  pendingEventUncertain = false;
  formatEventId(pendingEventId, sizeof(pendingEventId), activeCycleSessionId,
                activeCyclePermitId);
  lastEventRetryAt = millis();
  printEvent("CYCLE_COMPLETED", activeCycleId);
  activeCycleId[0] = '\0';
  printState();
}

void updateButton(ButtonInput &button, uint32_t now) {
  button.pressEdge = false;
  button.releaseEdge = false;
  const bool rawHigh = digitalRead(button.pin) == HIGH;
  if (rawHigh != button.rawHigh) {
    button.rawHigh = rawHigh;
    button.rawChangedAt = now;
  }

  const uint32_t debounceMs = button.rawHigh ? BUTTON_RELEASE_DEBOUNCE_MS : BUTTON_PRESS_DEBOUNCE_MS;
  if (button.stableHigh != button.rawHigh && elapsedAtLeast(now, button.rawChangedAt, debounceMs)) {
    button.stableHigh = button.rawHigh;
    if (!button.stableHigh) {
      button.pressedAt = now;
      button.pressEdge = true;
    } else button.releaseEdge = true;
  }
}

void updateReleaseArming(uint32_t now) {
  if (button1.stableHigh && button2.stableHigh) {
    if (!bothReleasedTracking) {
      bothReleasedTracking = true;
      bothReleasedSince = now;
    } else if (elapsedAtLeast(now, bothReleasedSince, RELEASE_STABLE_MS)) {
      const bool wasArmed = pairArmed;
      pairArmed = true;
      pairPending = false;
      firstPressedButton = 0;
      if (!wasArmed) printState();
    }
  } else {
    bothReleasedTracking = false;
  }
}

void rejectButtonPair(const char *reason) {
  pairArmed = false;
  pairPending = false;
  firstPressedButton = 0;
  Serial.print(F("EVENT|BUTTON_PAIR_REJECTED|reason="));
  Serial.println(reason);
}

void handleButtonPress(uint8_t buttonNumber, uint32_t pressedAt) {
  if (cycleRunning) {
    rejectButtonPair("CYCLE_BUSY");
    return;
  }
  if (!permitAllowsCycle()) {
    rejectButtonPair("NO_VALID_MES_PERMIT");
    return;
  }
  if (!pairArmed && !pairPending) return;

  if (!pairPending) {
    pairPending = true;
    firstPressedButton = buttonNumber;
    firstPressedAt = pressedAt;
    pairArmed = false;
    return;
  }

  if (buttonNumber == firstPressedButton) {
    rejectButtonPair("SAME_BUTTON_TWICE");
    return;
  }

  const uint32_t difference = static_cast<uint32_t>(pressedAt - firstPressedAt);
  const bool bothCurrentlyPressed = !button1.rawHigh && !button2.rawHigh &&
                                    !button1.stableHigh && !button2.stableHigh;
  if (!bothCurrentlyPressed || difference > config.buttonWindowMs) {
    rejectButtonPair("OUTSIDE_SYNC_WINDOW");
    return;
  }

  pairPending = false;
  beginCycle(millis());
}

bool nextField(char *&cursor, char *&field) {
  if (cursor == nullptr) return false;
  field = strtok_r(cursor, "|", &cursor);
  return field != nullptr;
}

bool noMoreFields(char *cursor) {
  if (cursor == nullptr) return true;
  char *save = cursor;
  return strtok_r(cursor, "|", &save) == nullptr;
}

void handleCalibration(char *cursor) {
  char *revisionText = nullptr, *homeText = nullptr, *lowerText = nullptr, *speedText = nullptr;
  uint32_t revision = 0, home = 0, lower = 0, speed = 0;
  if (!nextField(cursor, revisionText) || !nextField(cursor, homeText) ||
      !nextField(cursor, lowerText) || !nextField(cursor, speedText) || !noMoreFields(cursor) ||
      !parseUnsigned(revisionText, revision) || revision == 0 ||
      !parseUnsigned(homeText, home) || !parseUnsigned(lowerText, lower) ||
      !parseUnsigned(speedText, speed) || !validCalibration(home, lower, speed)) {
    printNack("CALIBRATION_RANGE");
    return;
  }
  if (cycleRunning || permitAllowsCycle() || pendingEvent) {
    printNack("STATION_ACTIVE");
    return;
  }
  saveCalibration(home, lower, speed);
  printAck("CALIBRATE", revision);
  printState();
}

void handleConfig(char *cursor) {
  char *revisionText = nullptr;
  char *windowText = nullptr;
  char *durationText = nullptr;
  char *cutsText = nullptr;
  char *homeAngleText = nullptr;
  char *cycleAngleText = nullptr;
  if (!nextField(cursor, revisionText) || !nextField(cursor, windowText) ||
      !nextField(cursor, durationText) || !nextField(cursor, cutsText)) {
    printNack("CONFIG_FORMAT");
    return;
  }

  uint32_t revision = 0;
  uint32_t windowMs = 0;
  uint32_t durationMs = 0;
  uint32_t cutsPerBox = 0;
  uint32_t homeAngle = config.homeAngle;
  uint32_t cycleAngle = config.cycleAngle;
  if (cursor != nullptr) {
    if (!nextField(cursor, homeAngleText) || !nextField(cursor, cycleAngleText) ||
        !noMoreFields(cursor) || !parseUnsigned(homeAngleText, homeAngle) ||
        !parseUnsigned(cycleAngleText, cycleAngle) || homeAngle > 180 || cycleAngle > 180) {
      printNack("CONFIG_ANGLE");
      return;
    }
    if (homeAngle != config.homeAngle || cycleAngle != config.cycleAngle) {
      printNack("USE_CALIBRATE");
      return;
    }
  }
  if (!parseUnsigned(revisionText, revision) || revision == 0 ||
      !parseUnsigned(windowText, windowMs) || windowMs == 0 || windowMs > MAX_BUTTON_WINDOW_MS ||
      !parseUnsigned(durationText, durationMs) || durationMs < MIN_CYCLE_DURATION_MS || durationMs > MAX_CYCLE_DURATION_MS ||
      !parseUnsigned(cutsText, cutsPerBox) || cutsPerBox == 0 || cutsPerBox > MAX_CUTS_PER_BOX) {
    printNack("CONFIG_RANGE");
    return;
  }
  if (homeAngle == cycleAngle) {
    printNack("CONFIG_ANGLE");
    return;
  }

  if (cycleRunning) {
    printNack("CYCLE_BUSY");
    return;
  }

  if (config.loaded && revision < config.revision) {
    printNack("CONFIG_OLD_REVISION");
    return;
  }
  if (config.loaded && revision == config.revision) {
    if (windowMs != config.buttonWindowMs || durationMs != config.cycleDurationMs ||
        cutsPerBox != config.cutsPerBox || homeAngle != config.homeAngle || cycleAngle != config.cycleAngle) {
      printNack("CONFIG_REVISION_CONFLICT");
      return;
    }
    printAck("CONFIG", revision);
    return;
  }

  config.loaded = true;
  config.revision = revision;
  config.buttonWindowMs = windowMs;
  config.cycleDurationMs = durationMs;
  config.cutsPerBox = cutsPerBox;
  config.homeAngle = static_cast<uint8_t>(homeAngle);
  config.cycleAngle = static_cast<uint8_t>(cycleAngle);
  printAck("CONFIG", revision);
  printState();
}

void closePermit() {
  permit.active = false;
  pairArmed = false;
  pairPending = false;
  bothReleasedTracking = false;
  firstPressedButton = 0;
}

void handleSession(char *cursor) {
  char *sessionText = nullptr;
  if (!nextField(cursor, sessionText) || !noMoreFields(cursor)) {
    printNack("SESSION_FORMAT");
    return;
  }
  if (strcmp(sessionText, "CLOSED") == 0) {
    closePermit();
    commandSession[0] = '\0';
    lastPermitId = 0;
    lastPermitValue = -1;
    printAck("SESSION_CLOSED");
    printState();
    return;
  }

  char newSession[SESSION_ID_CAPACITY];
  if (!copySafeToken(newSession, sizeof(newSession), sessionText)) {
    printNack("SESSION_VALUE");
    return;
  }
  if (strcmp(commandSession, newSession) != 0) {
    closePermit();
    strcpy(commandSession, newSession);
    lastPermitId = 0;
    lastPermitValue = -1;
    if (latestEventSlot >= 0 &&
        strcmp(latestEventRecord.sessionId, commandSession) == 0) {
      // Restore the last cycle grant from the journal to reject a replay after reboot.
      lastPermitId = latestEventRecord.permitId;
      lastPermitValue = 1;
    }
  }
  Serial.print(F("ACK|SESSION|session_id="));
  Serial.println(commandSession);
  printState();
}

void handlePermit(char *cursor) {
  char *sessionText = nullptr;
  char *permitIdText = nullptr;
  char *permitValueText = nullptr;
  uint32_t permitId = 0;
  bool permitValue = false;
  if (!nextField(cursor, sessionText) || !nextField(cursor, permitIdText) ||
      !nextField(cursor, permitValueText) || !noMoreFields(cursor) ||
      !parseUnsigned(permitIdText, permitId) || permitId == 0 ||
      !parseBoolean01(permitValueText, permitValue)) {
    printNack("PERMIT_FORMAT");
    return;
  }
  if (!commandSession[0] || strcmp(sessionText, commandSession) != 0) {
    printNack("PERMIT_SESSION");
    return;
  }
  if (permitId < lastPermitId ||
      (permitId == lastPermitId && static_cast<int8_t>(permitValue) != lastPermitValue)) {
    printNack("PERMIT_STALE_OR_CONFLICT");
    return;
  }
  if (permitId == lastPermitId) {
    Serial.print(F("ACK|PERMIT|permit_id="));
    Serial.print(permitId);
    Serial.print(F("|permit="));
    Serial.println(permitValue ? 1 : 0);
    printState();
    return;
  }
  if (permitValue && (cycleRunning || pendingEvent)) {
    printNack(pendingEvent ? "EVENT_PENDING" : "CYCLE_BUSY");
    return;
  }
  if (permitValue && !config.loaded) {
    printNack("CONFIG_REQUIRED");
    return;
  }

  lastPermitId = permitId;
  lastPermitValue = permitValue ? 1 : 0;
  permit.permitId = permitId;
  permit.active = permitValue;
  if (permitValue) lastPermitAt = millis();
  else closePermit();
  pairArmed = false;
  pairPending = false;
  bothReleasedTracking = false;

  Serial.print(F("ACK|PERMIT|permit_id="));
  Serial.print(permitId);
  Serial.print(F("|permit="));
  Serial.println(permitValue ? 1 : 0);
  printState();
}

void handleEventAck(char *cursor) {
  char *sessionText = nullptr;
  char *eventIdText = nullptr;
  if (!nextField(cursor, sessionText) || !nextField(cursor, eventIdText) ||
      !noMoreFields(cursor) || !commandSession[0] ||
      strcmp(sessionText, commandSession) != 0) {
    printNack("EVENT_ACK_SESSION_OR_FORMAT");
    return;
  }

  if (!pendingEvent && latestEventSlot >= 0 &&
      latestEventRecord.state == EVENT_ACKNOWLEDGED) {
    char lastEventId[EVENT_ID_CAPACITY];
    formatEventId(lastEventId, sizeof(lastEventId), latestEventRecord.sessionId,
                  latestEventRecord.permitId);
    if (strcmp(eventIdText, lastEventId) == 0) {
      Serial.print(F("ACK|EVENT|event_id="));
      Serial.println(eventIdText);
      return;
    }
  }
  if (!pendingEvent || strcmp(eventIdText, pendingEventId) != 0) {
    printNack("EVENT_ACK_MISMATCH");
    return;
  }

  if (!setLatestEventState(EVENT_ACKNOWLEDGED)) {
    printNack("EVENT_ACK_STORAGE_FAILED");
    return;
  }
  pendingEvent = false;
  pendingEventUncertain = false;
  pendingEventId[0] = '\0';
  Serial.print(F("ACK|EVENT|event_id="));
  Serial.println(eventIdText);
  printState();
}

void handleCommand(char *line) {
  char *cursor = nullptr;
  char *command = strtok_r(line, "|", &cursor);
  if (command == nullptr) return;

  if (strcmp(command, "CONFIG") == 0) {
    handleConfig(cursor);
  } else if (strcmp(command, "CALIBRATE") == 0) {
    handleCalibration(cursor);
  } else if (strcmp(command, "SESSION") == 0) {
    handleSession(cursor);
  } else if (strcmp(command, "PERMIT") == 0) {
    handlePermit(cursor);
  } else if (strcmp(command, "EVENT_ACK") == 0) {
    handleEventAck(cursor);
  } else if (strcmp(command, "STATUS") == 0 && noMoreFields(cursor)) {
    printState();
  } else if (strcmp(command, "PING") == 0 && noMoreFields(cursor)) {
    Serial.println(F("PONG|mode=SERVO_TEST_NO_BLADE"));
  } else {
    printNack("UNKNOWN_COMMAND");
  }
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    const char value = static_cast<char>(Serial.read());
    if (value == '\r') continue;
    if (value == '\n') {
      if (commandOverflow) {
        printNack("COMMAND_TOO_LONG");
      } else if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        handleCommand(commandBuffer);
      }
      commandLength = 0;
      commandOverflow = false;
      continue;
    }
    if (!commandOverflow) {
      if (commandLength + 1 < sizeof(commandBuffer)) {
        commandBuffer[commandLength++] = value;
      } else {
        commandOverflow = true;
      }
    }
  }
}

}  // namespace

void setup() {
  loadCalibration();
  loadEventJournal();
  pinMode(BUTTON_1_PIN, INPUT_PULLUP);
  pinMode(BUTTON_2_PIN, INPUT_PULLUP);

  const uint32_t now = millis();
  button1.rawHigh = digitalRead(BUTTON_1_PIN) == HIGH;
  button1.stableHigh = button1.rawHigh;
  button1.rawChangedAt = now;
  button2.rawHigh = digitalRead(BUTTON_2_PIN) == HIGH;
  button2.stableHigh = button2.rawHigh;
  button2.rawChangedAt = now;

  Serial.begin(SERIAL_BAUD);
  Serial.print(F("BOOT|mode=SERVO_TEST_NO_BLADE|state=DISARMED|servo_pin=D9|protocol=4|cycle_seq="));
  Serial.println(cycleSequence);
  printState();
  if (pendingEvent) {
    printPendingEvent();
    lastEventRetryAt = millis();
  }
}

void loop() {
  readSerialCommands();
  const uint32_t now = millis();
  if (permit.active && elapsedAtLeast(now, lastPermitAt, PERMIT_TIMEOUT_MS)) {
    const uint32_t expiredPermitId = permit.permitId;
    closePermit();
    Serial.print(F("EVENT|PERMIT_EXPIRED|permit_id="));
    Serial.println(expiredPermitId);
    printState();
  }

  if (pendingEvent && elapsedAtLeast(now, lastEventRetryAt, EVENT_RETRY_MS)) {
    printPendingEvent();
    lastEventRetryAt = now;
  }

  updateButton(button1, now);
  updateButton(button2, now);
  updateReleaseArming(now);

  if (button1.pressEdge) handleButtonPress(1, button1.pressedAt);
  if (button2.pressEdge) handleButtonPress(2, button2.pressedAt);

  if (cycleRunning && elapsedAtLeast(now, cycleStartedAt, activeHomeLeadMs)) {
    const uint32_t elapsed = now - cycleStartedAt - activeHomeLeadMs;
    const uint32_t returnAt = activeCycleDurationMs - activeTravelMs;
    if (elapsed < returnAt) moveToward(activeHomeAngle, config.cycleAngle, elapsed);
    else {
      if (!returningHome) {
        returningHome = true;
        printEvent("CUT_UP", activeCycleId);
      }
      moveToward(config.cycleAngle, activeHomeAngle, min(elapsed - returnAt, activeTravelMs));
      if (elapsed >= activeCycleDurationMs) completeCycle();
    }
  }

  if (button1.pressEdge) Serial.println(F("EVENT|BUTTON_PRESSED|pin=D2"));
  if (button2.pressEdge) Serial.println(F("EVENT|BUTTON_PRESSED|pin=D3"));
  if (button1.releaseEdge) Serial.println(F("EVENT|BUTTON_RELEASED|pin=D2"));
  if (button2.releaseEdge) Serial.println(F("EVENT|BUTTON_RELEASED|pin=D3"));
}
