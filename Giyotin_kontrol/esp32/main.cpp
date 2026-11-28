#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

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

// Classic ESP32 DevKit UART2, linked to Nano SoftwareSerial at 9600 baud.
// Wire Nano D11/TX -> GPIO16/RX through a 5 V-to-3.3 V level shifter;
// wire GPIO17/TX -> Nano D10/RX. Nano D0/D1 stay free for USB programming.
constexpr int NANO_RX_PIN = 16;  // ESP32 RX2 <- Nano D11/TX
constexpr int NANO_TX_PIN = 17;  // ESP32 TX2 -> Nano D10/RX
constexpr uint32_t NANO_BAUD = 9600;

constexpr unsigned long WIFI_RETRY_MS = 10000;
constexpr unsigned long MQTT_RETRY_MS = 5000;
constexpr unsigned long HEARTBEAT_INTERVAL_MS = 5000;
constexpr unsigned long BRIDGE_INTERVAL_MS = 10000;
constexpr unsigned long NANO_TIMEOUT_MS = 15000;
constexpr unsigned long NANO_POLL_INTERVAL_MS = 5000;
constexpr size_t NANO_LINE_MAX = 384;
constexpr size_t MQTT_QUEUE_MAX = 24;
constexpr uint32_t MIN_NANO_CYCLE_MS = 1000;
constexpr uint32_t MAX_NANO_CYCLE_MS = 10000;

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
String currentJobId;
String currentNanoOrderId;
String currentControlState = "idle";
unsigned long lastWifiAttemptAt = 0;
unsigned long lastMqttAttemptAt = 0;
unsigned long lastHeartbeatAt = 0;
unsigned long lastBridgeAt = 0;
unsigned long lastNanoRxAt = 0;
unsigned long lastNanoPollAt = 0;
uint32_t lastCommandId = 0;
bool nanoSeen = false;
bool bridgeStatusDirty = true;

String makeClientId() {
  char id[32];
  snprintf(id, sizeof(id), "giyotin-esp-%08lx",
           static_cast<unsigned long>(ESP.getEfuseMac() & 0xFFFFFFFFULL));
  return String(id);
}

String makeSafeToken(const String &value, const char *fallback, size_t maxLength) {
  String result;
  result.reserve(maxLength);
  for (size_t i = 0; i < value.length() && result.length() < maxLength; ++i) {
    const char c = value.charAt(i);
    const bool allowed = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                         (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.';
    result += allowed ? c : '-';
  }
  while (result.endsWith("-")) result.remove(result.length() - 1);
  if (result.length() == 0) result = fallback;
  return result;
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
  for (size_t i = 0; i < value.length(); ++i) {
    if (value.charAt(i) < '0' || value.charAt(i) > '9') return false;
  }
  out = static_cast<uint32_t>(value.toInt());
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
  const String orderId = fieldValue(line, "order");
  const String normalizedNanoState = nanoState;
  const bool isBusy = normalizedNanoState == "CYCLE_RUNNING";
  const bool armed = normalizedNanoState == "READY" || normalizedNanoState == "WAIT_SECOND_BUTTON";
  const bool hasPermit = fieldValue(line, "shift_open") == "1" &&
                         fieldValue(line, "order_active") == "1";

  String uiState = "disabled";
  if (isBusy) uiState = "cycle_running";
  else if (nanoState == "READY" || nanoState == "WAIT_SECOND_BUTTON" || nanoState == "WAIT_RELEASE") {
    uiState = "waiting_for_buttons";
  } else if (!nanoConnected()) {
    uiState = "waiting_for_nano";
  }

  uint32_t completed = 0;
  uint32_t target = 0;
  parseUnsignedField(fieldValue(line, "completed"), completed);
  parseUnsignedField(fieldValue(line, "target"), target);

  StaticJsonDocument<512> doc;
  doc["device"] = "giyotin_nano";
  doc["state"] = uiState;
  doc["nano_ready"] = nanoSeen;
  doc["nano_armed"] = armed;
  doc["cycle_busy"] = isBusy;
  doc["control_state"] = currentControlState;
  doc["job_id"] = (orderId == currentNanoOrderId && currentJobId.length() > 0)
                      ? currentJobId
                      : orderId;
  doc["completed_count"] = completed;
  doc["target_count"] = target;
  doc["config_revision"] = fieldValue(line, "config_revision");
  doc["nano_state"] = nanoState;
  doc["permit_active"] = hasPermit && fieldValue(line, "state") != "TARGET_REACHED";
  doc["uptime_ms"] = millis();
  publishJson(TOPIC_STATUS, doc, true);
}

void publishNanoEvent(const String &line) {
  const int firstSep = line.indexOf('|');
  const int secondSep = line.indexOf('|', firstSep + 1);
  if (firstSep < 0 || secondSep < 0) return;

  String event = line.substring(firstSep + 1, secondSep);
  if (event == "CYCLE_STARTED") event = "CUT_START";
  else if (event == "CYCLE_COMPLETED") event = "CUT_DONE";

  const String orderId = fieldValue(line, "order_id");
  uint32_t completed = 0;
  parseUnsignedField(fieldValue(line, "completed"), completed);

  StaticJsonDocument<512> doc;
  doc["device"] = "giyotin_nano";
  doc["event"] = event;
  doc["cycle_id"] = fieldValue(line, "cycle_id");
  doc["permit_id"] = fieldValue(line, "permit_id");
  doc["job_id"] = (orderId == currentNanoOrderId && currentJobId.length() > 0)
                      ? currentJobId
                      : orderId;
  doc["config_revision"] = fieldValue(line, "config_revision");
  doc["completed_count"] = completed;
  doc["nano_line"] = line;
  doc["at_uptime_ms"] = millis();
  publishJson(TOPIC_LOGS, doc, false);
}

void publishNanoLine(const String &line) {
  nanoSeen = true;
  lastNanoRxAt = millis();
  bridgeStatusDirty = true;
  Serial.print("NANO -> ");
  Serial.println(line);

  if (line.startsWith("STATUS|")) {
    publishNanoStatus(line);
  } else if (line.startsWith("EVENT|")) {
    publishNanoEvent(line);
  } else if (line.startsWith("BOOT|")) {
    StaticJsonDocument<256> doc;
    doc["event"] = "NANO_BOOT";
    doc["device"] = "giyotin_nano";
    doc["nano_line"] = line;
    doc["at_uptime_ms"] = millis();
    publishJson(TOPIC_LOGS, doc, false);
  } else if (line.startsWith("NACK|")) {
    StaticJsonDocument<256> doc;
    doc["event"] = "NANO_COMMAND_REJECTED";
    doc["reason"] = line.substring(5);
    doc["nano_line"] = line;
    doc["at_uptime_ms"] = millis();
    publishJson(TOPIC_LOGS, doc, false);
  } else if (line.startsWith("ACK|") || line.startsWith("PONG|")) {
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
  const bool enabled = doc["enabled"] | false;
  const String action = String(doc["action"] | "SYNC");
  const uint32_t commandId = doc["command_id"] | 0UL;
  const String originalJobId = String(doc["job_id"] | "");
  uint32_t target = doc["target_count"] | 0UL;
  uint32_t completed = doc["completed_count"] | 0UL;
  uint32_t cyclesPerBox = doc["cycles_per_box"] | 2UL;
  uint32_t cycleDuration = doc["cycle_duration_ms"] | 2000UL;

  currentJobId = originalJobId;
  currentNanoOrderId = makeSafeToken(originalJobId, "no-order", 39);
  if (currentJobId.length() == 0) currentJobId = currentNanoOrderId;
  lastCommandId = commandId;

  if (target == 0) target = 1;  // Nano's PERMIT format requires a positive target.
  if (completed > target) completed = target;
  if (cyclesPerBox == 0) cyclesPerBox = 1;
  if (cycleDuration < MIN_NANO_CYCLE_MS) cycleDuration = MIN_NANO_CYCLE_MS;
  if (cycleDuration > MAX_NANO_CYCLE_MS) cycleDuration = MAX_NANO_CYCLE_MS;

  const uint32_t revision = commandId > 0 ? commandId : 1;
  const String configCommand = String("CONFIG|") + revision + "|500|" + cycleDuration + "|" +
                               cyclesPerBox + "|150|0";
  sendNanoCommand(configCommand);

  const String permitId = String("mes-") + (commandId > 0 ? String(commandId) : String(millis()));
  const bool orderActive = enabled && originalJobId.length() > 0;
  const bool shiftOpen = orderActive;
  const String permitCommand = String("PERMIT|") + permitId + "|" + currentNanoOrderId + "|" +
                               (shiftOpen ? "1" : "0") + "|" +
                               (orderActive ? "1" : "0") + "|" + target + "|" + completed;
  sendNanoCommand(permitCommand);

  if (!enabled || action == "PAUSE" || action == "STOP" || action == "DISARM") {
    currentControlState = (action == "PAUSE") ? "paused" : "idle";
  } else if (completed >= target) {
    currentControlState = "complete";
  } else {
    currentControlState = "running";
  }

  Serial.printf("MQTT cmd: action=%s enabled=%d command_id=%lu job=%s\n",
                action.c_str(), enabled ? 1 : 0,
                static_cast<unsigned long>(commandId), currentJobId.c_str());
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
  StaticJsonDocument<256> doc;
  doc["device"] = "giyotin_esp32";
  doc["state"] = "online";
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["mqtt_connected"] = mqttClient.connected();
  doc["nano_connected"] = nanoConnected();
  doc["uptime_ms"] = millis();
  doc["rssi"] = WiFi.RSSI();
  publishJson(TOPIC_HEARTBEAT, doc, true);
}

void publishBridgeStatus(bool force = false) {
  if (!mqttClient.connected()) return;
  if (!force && !bridgeStatusDirty && millis() - lastBridgeAt < BRIDGE_INTERVAL_MS) return;

  StaticJsonDocument<320> doc;
  doc["device"] = "giyotin_esp32";
  doc["state"] = (WiFi.status() == WL_CONNECTED && mqttClient.connected()) ? "online" : "degraded";
  doc["wifi_connected"] = WiFi.status() == WL_CONNECTED;
  doc["mqtt_connected"] = mqttClient.connected();
  doc["nano_connected"] = nanoConnected();
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
  mqttClient.subscribe(TOPIC_CMD);
  publishHeartbeat();
  sendNanoCommand("STATUS");
  sendNanoCommand("PING");
  publishBridgeStatus(true);
  return true;
}
}  // namespace

void setup() {
  Serial.begin(115200);  // ESP32 USB debug console
  delay(300);
  Serial.println();
  Serial.println("Giyotin ESP32 Nano-MQTT koprusu basladi");

  Serial2.setRxBufferSize(1024);
  Serial2.begin(NANO_BAUD, SERIAL_8N1, NANO_RX_PIN, NANO_TX_PIN);
  Serial.printf("Nano UART2 hazir: baud=%lu RX=%d TX=%d\n",
                static_cast<unsigned long>(NANO_BAUD), NANO_RX_PIN, NANO_TX_PIN);

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setBufferSize(1024);
  mqttClient.setCallback(mqttCallback);
  startWifi();
}

void loop() {
  readNanoSerial();
  const unsigned long now = millis();

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

    // Keep the Nano link status fresh even when no operator action occurs.
    if (now - lastNanoPollAt >= NANO_POLL_INTERVAL_MS) {
      lastNanoPollAt = now;
      sendNanoCommand("STATUS");
    }

    if (now - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
      lastHeartbeatAt = now;
      publishHeartbeat();
    }
    publishBridgeStatus(false);
  }

  delay(2);
}
