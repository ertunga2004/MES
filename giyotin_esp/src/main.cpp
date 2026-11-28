#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <esp_system.h>

#include "secrets.h"

namespace {
constexpr char MQTT_HOST[] = "broker.emqx.io";
constexpr uint16_t MQTT_PORT = 1883;
constexpr char TOPIC_ROOT[] = "sau/iot/giyotin/";
constexpr char TOPIC_CMD[] = "sau/iot/giyotin/cmd";
constexpr char TOPIC_STATUS[] = "sau/iot/giyotin/status";
constexpr char TOPIC_LOGS[] = "sau/iot/giyotin/logs";
constexpr char TOPIC_HEARTBEAT[] = "sau/iot/giyotin/heartbeat";
constexpr char TOPIC_BRIDGE[] = "sau/iot/giyotin/bridge/status";

// Nano hardware UART, through the level converter.
constexpr int NANO_RX_PIN = 16;  // ESP32 RX2 <- Nano D1/TX
constexpr int NANO_TX_PIN = 17;  // ESP32 TX2 -> Nano D0/RX
constexpr uint32_t NANO_BAUD = 9600;

constexpr unsigned long WIFI_RETRY_MS = 10000;
constexpr unsigned long MQTT_RETRY_MS = 5000;
constexpr unsigned long HEARTBEAT_INTERVAL_MS = 5000;
constexpr unsigned long BRIDGE_INTERVAL_MS = 10000;
constexpr unsigned long NANO_TIMEOUT_MS = 15000;
constexpr unsigned long NANO_POLL_INTERVAL_MS = 5000;
constexpr size_t NANO_LINE_MAX = 512;
constexpr size_t MQTT_QUEUE_MAX = 24;

struct QueuedPublish {
  String topic;
  String payload;
  bool retained;
};

WiFiClient networkClient;
PubSubClient mqttClient(networkClient);
QueuedPublish publishQueue[MQTT_QUEUE_MAX];
size_t queueHead = 0;
size_t queueCount = 0;
uint32_t droppedPublishCount = 0;

String nanoLine;
bool nanoLineOverflow = false;
String requestedPermitId;
char commandSession[17] = "";
unsigned long lastWifiAttemptAt = 0;
unsigned long lastMqttAttemptAt = 0;
unsigned long lastHeartbeatAt = 0;
unsigned long lastBridgeAt = 0;
unsigned long lastNanoRxAt = 0;
unsigned long lastNanoPollAt = 0;
uint32_t lastCommandId = 0;
bool nanoSeen = false;
bool bridgeStatusDirty = true;

void sendNanoCommand(const String &command);

String makeClientId() {
  char id[32];
  snprintf(id, sizeof(id), "giyotin-esp-%08lx",
           static_cast<unsigned long>(ESP.getEfuseMac() & 0xFFFFFFFFULL));
  return String(id);
}

String fieldValue(const String &line, const String &key) {
  const String needle = key + "=";
  int start = line.indexOf('|');
  while (start >= 0 && start < static_cast<int>(line.length())) {
    const int end = line.indexOf('|', start + 1);
    const String field = line.substring(start + 1, end < 0 ? line.length() : end);
    if (field.startsWith(needle)) return field.substring(needle.length());
    start = end;
  }
  return "";
}

bool parseUnsignedField(const String &value, uint32_t &out) {
  if (value.length() == 0) return false;
  uint32_t result = 0;
  for (size_t i = 0; i < value.length(); ++i) {
    const char c = value.charAt(i);
    if (c < '0' || c > '9') return false;
    const uint32_t digit = c - '0';
    if (result > (UINT32_MAX - digit) / 10U) return false;
    result = result * 10U + digit;
  }
  out = result;
  return true;
}

bool isSafeToken(const String &value, size_t maxLength) {
  if (value.length() == 0 || value.length() > maxLength) return false;
  for (size_t i = 0; i < value.length(); ++i) {
    const char c = value.charAt(i);
    const bool allowed = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                         (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.';
    if (!allowed) return false;
  }
  return true;
}

bool nanoConnected() {
  return nanoSeen && millis() - lastNanoRxAt <= NANO_TIMEOUT_MS;
}

bool queuePublish(const char *topic, const String &payload, bool retained) {
  if (mqttClient.connected() && queueCount == 0) {
    if (mqttClient.publish(topic, payload.c_str(), retained)) return true;
  }

  if (queueCount >= MQTT_QUEUE_MAX) {
    ++droppedPublishCount;
    bridgeStatusDirty = true;
    return false;
  }

  const size_t tail = (queueHead + queueCount) % MQTT_QUEUE_MAX;
  publishQueue[tail].topic = topic;
  publishQueue[tail].payload = payload;
  publishQueue[tail].retained = retained;
  ++queueCount;
  bridgeStatusDirty = true;
  return true;
}

void flushPublishQueue() {
  if (!mqttClient.connected()) return;
  uint8_t sent = 0;
  while (queueCount > 0 && sent < 4) {
    QueuedPublish &item = publishQueue[queueHead];
    if (!mqttClient.publish(item.topic.c_str(), item.payload.c_str(), item.retained)) break;
    item.topic = "";
    item.payload = "";
    queueHead = (queueHead + 1) % MQTT_QUEUE_MAX;
    --queueCount;
    ++sent;
  }
}

void publishJson(const char *topic, JsonDocument &document, bool retained = false) {
  String payload;
  serializeJson(document, payload);
  queuePublish(topic, payload, retained);
}

void publishNanoStatus(const String &line) {
  const String nanoState = fieldValue(line, "state");
  const bool isBusy = nanoState == "CYCLE_RUNNING";
  const bool armed = nanoState == "READY" || nanoState == "WAIT_SECOND_BUTTON";
  const bool hasPermit = fieldValue(line, "permit_active") == "1";

  String uiState = "disabled";
  if (isBusy) uiState = "cycle_running";
  else if (nanoState == "READY" || nanoState == "WAIT_SECOND_BUTTON" || nanoState == "WAIT_RELEASE") {
    uiState = "waiting_for_buttons";
  } else if (!nanoConnected()) {
    uiState = "waiting_for_nano";
  }

  StaticJsonDocument<1024> doc;
  doc["device"] = "giyotin_nano";
  doc["state"] = uiState;
  doc["nano_ready"] = nanoSeen;
  doc["nano_armed"] = armed;
  doc["cycle_busy"] = isBusy;
  doc["permit_active"] = hasPermit;
  doc["config_revision"] = fieldValue(line, "config_revision");
  doc["nano_state"] = nanoState;
  doc["phase"] = fieldValue(line, "phase");
  doc["d2_pressed"] = fieldValue(line, "d2_pressed") == "1";
  doc["d3_pressed"] = fieldValue(line, "d3_pressed") == "1";
  doc["calibration_saved"] = fieldValue(line, "calibration_saved") == "1";
  for (const char *key : {"home_angle", "cycle_angle", "servo_speed_dps", "angle_commanded"}) {
    uint32_t value = 0;
    if (parseUnsignedField(fieldValue(line, key), value)) doc[key] = value;
  }
  doc["uptime_ms"] = millis();
  publishJson(TOPIC_STATUS, doc, true);
}

void publishNanoEvent(const String &line) {
  const int firstSep = line.indexOf('|');
  const int secondSep = line.indexOf('|', firstSep + 1);
  if (firstSep < 0) return;

  String event = line.substring(firstSep + 1, secondSep < 0 ? line.length() : secondSep);
  if (event == "CYCLE_STARTED") event = "CUT_START";
  else if (event == "CYCLE_COMPLETED") event = "CUT_DONE";

  StaticJsonDocument<512> doc;
  doc["device"] = "giyotin_nano";
  doc["event"] = event;
  const String eventId = fieldValue(line, "event_id");
  const String cycleId = fieldValue(line, "cycle_id");
  doc["event_id"] = eventId.length() ? eventId : cycleId;
  uint32_t cycleSeq = 0;
  if (parseUnsignedField(fieldValue(line, "cycle_seq"), cycleSeq)) {
    doc["cycle_seq"] = cycleSeq;
  }
  doc["permit_id"] = fieldValue(line, "permit_id");
  doc["config_revision"] = fieldValue(line, "config_revision");
  const String button = fieldValue(line, "pin");
  if (button.length()) doc["button"] = button;
  doc["at_uptime_ms"] = millis();
  publishJson(TOPIC_LOGS, doc, false);
}

void publishNanoLine(const String &line) {
  const bool nanoLinkWasStale = !nanoConnected();
  nanoSeen = true;
  lastNanoRxAt = millis();
  bridgeStatusDirty = true;
  Serial.print("NANO -> ");
  Serial.println(line);

  if (nanoLinkWasStale && commandSession[0] && !line.startsWith("BOOT|")) {
    sendNanoCommand(String("SESSION|") + commandSession);
  }

  if (line.startsWith("STATUS|")) {
    publishNanoStatus(line);
  } else if (line.startsWith("EVENT|")) {
    publishNanoEvent(line);
  } else if (line.startsWith("BOOT|")) {
    requestedPermitId = "";
    if (commandSession[0]) sendNanoCommand(String("SESSION|") + commandSession);
    StaticJsonDocument<256> doc;
    doc["event"] = "NANO_BOOT";
    doc["device"] = "giyotin_nano";
    doc["nano_line"] = line;
    doc["at_uptime_ms"] = millis();
    publishJson(TOPIC_LOGS, doc, false);
  } else if (line.startsWith("NACK|")) {
    requestedPermitId = "";
    StaticJsonDocument<256> doc;
    doc["event"] = "NANO_COMMAND_REJECTED";
    doc["reason"] = line.substring(5);
    doc["nano_line"] = line;
    doc["at_uptime_ms"] = millis();
    publishJson(TOPIC_LOGS, doc, false);
  } else if (line.startsWith("ACK|") || line.startsWith("PONG|")) {
    if (line.startsWith("ACK|PERMIT|")) {
      const String acknowledged = fieldValue(line, "permit_id");
      if (acknowledged.length() && acknowledged == requestedPermitId) {
        requestedPermitId = "";
      }
    }
    StaticJsonDocument<256> doc;
    doc["event"] = line.startsWith("ACK|") ? "NANO_ACK" : "NANO_PONG";
    doc["nano_line"] = line;
    doc["at_uptime_ms"] = millis();
    publishJson(TOPIC_LOGS, doc, false);
  }
}

void readNanoSerial() {
  while (Serial2.available() > 0) {
    const char value = static_cast<char>(Serial2.read());
    if (value == '\r') continue;
    if (value == '\n') {
      nanoLine.trim();
      if (nanoLine.length() > 0) publishNanoLine(nanoLine);
      nanoLine = "";
      nanoLineOverflow = false;
      continue;
    }
    if (nanoLine.length() < NANO_LINE_MAX) nanoLine += value;
    else nanoLineOverflow = true;
  }

  if (nanoLineOverflow && nanoLine.length() == NANO_LINE_MAX) {
    nanoLine = "";
    nanoLineOverflow = false;
    ++droppedPublishCount;
    bridgeStatusDirty = true;
  }
}

void sendNanoCommand(const String &command) {
  Serial2.println(command);
  Serial.print("ESP32 -> NANO: ");
  Serial.println(command);
}

void handleMesCommand(JsonDocument &doc) {
  const String action = String(doc["action"] | "");
  if (action == "STATUS") {
    sendNanoCommand("STATUS");
    return;
  }
  if (action == "PING") {
    sendNanoCommand("PING");
    return;
  }

  const char *sessionId = doc["session_id"] | "";
  if (!commandSession[0] || strcmp(sessionId, commandSession) != 0 || !nanoConnected()) {
    StaticJsonDocument<256> response;
    response["device"] = "giyotin_esp32";
    response["event"] = "COMMAND_REJECTED";
    response["reason"] = "SESSION_SEQUENCE_OR_NANO";
    if (doc.containsKey("permit_id")) response["permit_id"] = doc["permit_id"];
    publishJson(TOPIC_LOGS, response);
    return;
  }

  const bool hasEventAck = doc.containsKey("event_ack_id");
  if (hasEventAck) {
    const String eventAckId = String(doc["event_ack_id"] | "");
    if (!isSafeToken(eventAckId, 96)) return;
    sendNanoCommand(String("EVENT_ACK|") + commandSession + "|" + eventAckId);
  }

  if (hasEventAck && !doc.containsKey("permit")) return;

  if (action == "CALIBRATE") {
    const uint32_t commandId = doc["command_id"] | 0UL;
    if (commandId == 0 || commandId <= lastCommandId) return;
    const uint32_t home = doc["home_angle"] | 181UL;
    const uint32_t lower = doc["cycle_angle"] | 181UL;
    const uint32_t speed = doc["servo_speed_dps"] | 0UL;
    sendNanoCommand(String("CALIBRATE|") + commandId + "|" + home + "|" + lower + "|" + speed);
    lastCommandId = commandId;
    return;
  }

  if (!doc["permit"].is<int>() && !doc["permit"].is<unsigned int>()) {
    StaticJsonDocument<256> response;
    response["device"] = "giyotin_esp32";
    response["event"] = "COMMAND_REJECTED";
    response["reason"] = "PERMIT_FIELD_REQUIRED";
    publishJson(TOPIC_LOGS, response);
    return;
  }
  const int permitValue = doc["permit"].as<int>();
  const uint32_t permitId = doc["permit_id"] | 0UL;
  if ((permitValue != 0 && permitValue != 1) || permitId == 0 || permitId <= lastCommandId) {
    StaticJsonDocument<256> response;
    response["device"] = "giyotin_esp32";
    response["event"] = "COMMAND_REJECTED";
    response["reason"] = "INVALID_OR_OLD_PERMIT";
    response["permit_id"] = permitId;
    publishJson(TOPIC_LOGS, response);
    return;
  }

  lastCommandId = permitId;
  requestedPermitId = String(permitId);
  sendNanoCommand(String("PERMIT|") + commandSession + "|" + permitId + "|" + permitValue);
  Serial.printf("MQTT permit: value=%d permit_id=%lu\n", permitValue,
                static_cast<unsigned long>(permitId));
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  if (String(topic) != TOPIC_CMD) return;

  StaticJsonDocument<768> doc;
  const DeserializationError error = deserializeJson(doc, payload, length);
  if (error || !doc.is<JsonObject>()) {
    Serial.println("Gecersiz giyotin MQTT komutu (JSON bekleniyor)");
    return;
  }
  handleMesCommand(doc);
}

void publishHeartbeat() {
  StaticJsonDocument<320> doc;
  doc["device"] = "giyotin_esp32";
  doc["state"] = "online";
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["mqtt_connected"] = mqttClient.connected();
  doc["nano_connected"] = nanoConnected();
  doc["session_id"] = commandSession;
  doc["protocol"] = 4;
  doc["uptime_ms"] = millis();
  doc["rssi"] = WiFi.RSSI();
  publishJson(TOPIC_HEARTBEAT, doc, true);
}

void publishBridgeStatus(bool force = false) {
  if (!mqttClient.connected()) return;
  if (!force && !bridgeStatusDirty && millis() - lastBridgeAt < BRIDGE_INTERVAL_MS) return;

  StaticJsonDocument<384> doc;
  doc["device"] = "giyotin_esp32";
  doc["state"] = (WiFi.status() == WL_CONNECTED && mqttClient.connected()) ? "online" : "degraded";
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["mqtt_connected"] = mqttClient.connected();
  doc["nano_connected"] = nanoConnected();
  doc["session_id"] = commandSession;
  doc["queue_depth"] = queueCount;
  doc["dropped_publish"] = droppedPublishCount;
  doc["last_nano_rx_ms"] = lastNanoRxAt;
  doc["uptime_ms"] = millis();
  doc["rssi"] = WiFi.RSSI();
  publishJson(TOPIC_BRIDGE, doc, true);
  lastBridgeAt = millis();
  bridgeStatusDirty = false;
}

void startWifi() {
  Serial.printf("Wi-Fi agina baglaniliyor: %s\n", GIYOTIN_WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.begin(GIYOTIN_WIFI_SSID, GIYOTIN_WIFI_PASSWORD);
  lastWifiAttemptAt = millis();
}

bool connectMqtt() {
  const String clientId = makeClientId();
  StaticJsonDocument<128> offlineDoc;
  offlineDoc["device"] = "giyotin_esp32";
  offlineDoc["state"] = "offline";
  String offlinePayload;
  serializeJson(offlineDoc, offlinePayload);

  const bool connected = mqttClient.connect(clientId.c_str(), TOPIC_HEARTBEAT, 0, true,
                                             offlinePayload.c_str());
  if (!connected) {
    Serial.printf("MQTT baglantisi basarisiz, durum kodu: %d\n", mqttClient.state());
    return false;
  }

  Serial.println("MQTT baglandi; giyotin cmd topic'ine abone olunuyor");
  snprintf(commandSession, sizeof(commandSession), "%08lx%08lx",
           static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
  lastCommandId = 0;
  mqttClient.subscribe(TOPIC_CMD);
  sendNanoCommand(String("SESSION|") + commandSession);
  publishHeartbeat();
  sendNanoCommand("STATUS");
  sendNanoCommand("PING");
  publishBridgeStatus(true);
  return true;
}

void endCommandSession() {
  if (commandSession[0]) sendNanoCommand("SESSION|CLOSED");
  requestedPermitId = "";
  commandSession[0] = '\0';
}
}  // namespace

void setup() {
  Serial.begin(115200);  // ESP32 USB debug console
  delay(300);
  Serial.println();
  Serial.println("Giyotin ESP32 Nano-MQTT koprusu basladi | protocol=4");

  Serial2.setRxBufferSize(1024);
  Serial2.begin(NANO_BAUD, SERIAL_8N1, NANO_RX_PIN, NANO_TX_PIN);
  Serial.printf("Nano UART2 hazir: baud=%lu RX=%d TX=%d\n",
                static_cast<unsigned long>(NANO_BAUD), NANO_RX_PIN, NANO_TX_PIN);

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(1536);
  mqttClient.setCallback(mqttCallback);
  startWifi();
}

void loop() {
  readNanoSerial();
  const unsigned long now = millis();
  if (commandSession[0] && (!mqttClient.connected() || WiFi.status() != WL_CONNECTED || !nanoConnected())) {
    if (!mqttClient.connected() || WiFi.status() != WL_CONNECTED) endCommandSession();
    else {
      requestedPermitId = "";
    }
  }
  if (now - lastNanoPollAt >= NANO_POLL_INTERVAL_MS) {
    lastNanoPollAt = now;
    sendNanoCommand("STATUS");
  }

  if (WiFi.status() != WL_CONNECTED) {
    if (mqttClient.connected()) mqttClient.disconnect();
    if (now - lastWifiAttemptAt >= WIFI_RETRY_MS) startWifi();
    delay(2);
    return;
  }

  if (!mqttClient.connected() && now - lastMqttAttemptAt >= MQTT_RETRY_MS) {
    lastMqttAttemptAt = now;
    connectMqtt();
  }

  if (mqttClient.connected()) {
    mqttClient.loop();
    flushPublishQueue();

    if (now - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
      lastHeartbeatAt = now;
      publishHeartbeat();
    }
    publishBridgeStatus(false);
  }

  delay(2);
}
