#include <WiFi.h>
#include <PubSubClient.h>

// =====================
// Wi-Fi
// =====================
const char* ssid     = "TOMRIS_IoT";
const char* password = "Kataturk1881.";

// =====================
// MQTT
// =====================
const char* mqtt_host = "broker.emqx.io";
const uint16_t mqtt_port = 1883;

// =====================
// Topicler
// =====================
const char* TOPIC_ROOT      = "sau/iot/mega/konveyor/";
const char* TOPIC_CMD       = "sau/iot/mega/konveyor/cmd";
const char* TOPIC_STATUS    = "sau/iot/mega/konveyor/status";
const char* TOPIC_LOGS      = "sau/iot/mega/konveyor/logs";
const char* TOPIC_HEARTBEAT = "sau/iot/mega/konveyor/heartbeat";
const char* TOPIC_LWT       = "sau/iot/mega/konveyor/heartbeat";
const char* TOPIC_BRIDGE    = "sau/iot/mega/konveyor/bridge/status";

// =====================
// MEGA <-> ESP32 UART2
// ESP32 RX2=16, TX2=17
// =====================
constexpr int MEGA_RX_PIN = 16;   // ESP32 RX2 <- MEGA TX1
constexpr int MEGA_TX_PIN = 17;   // ESP32 TX2 -> MEGA RX1
constexpr uint32_t MEGA_BAUD = 57600;

constexpr size_t MEGA_LINE_MAX = 896;
constexpr size_t MQTT_QUEUE_MAX = 48;
constexpr uint8_t MQTT_FLUSH_BURST = 6;

WiFiClient espClient;
PubSubClient client(espClient);

String clientId;
String megaLineBuffer;
bool megaLineOverflow = false;
String megaPublishQueue[MQTT_QUEUE_MAX];
size_t megaQueueHead = 0;
size_t megaQueueCount = 0;
uint32_t droppedUartLines = 0;
uint32_t droppedPublishLines = 0;
bool bridgeStatusDirty = true;
unsigned long lastBridgeStatusMs = 0;

size_t mqttQueueTail();
void markBridgeStatusDirty();
bool enqueueMegaLineForPublish(const String& line);
void dropQueuedLine();
void flushMegaPublishQueue();
void publishBridgeStatus(bool force);
bool connectWiFi();
bool connectMQTT();
void ensureMQTTConnected();
void readMegaSerialAndQueue();

// =====================
// MQTT callback
// =====================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  msg.reserve(length + 1);

  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  msg.trim();

  Serial.print("MQTT [");
  Serial.print(topic);
  Serial.print("] -> ");
  Serial.println(msg);

  if (String(topic) == TOPIC_CMD) {
    Serial2.println(msg);
    Serial.print("ESP32 -> MEGA: ");
    Serial.println(msg);
  }
}

size_t mqttQueueTail() {
  return (megaQueueHead + megaQueueCount) % MQTT_QUEUE_MAX;
}

void markBridgeStatusDirty() {
  bridgeStatusDirty = true;
}

bool enqueueMegaLineForPublish(const String& line) {
  if (line.length() == 0) return true;

  if (megaQueueCount >= MQTT_QUEUE_MAX) {
    droppedUartLines++;
    markBridgeStatusDirty();
    return false;
  }

  megaPublishQueue[mqttQueueTail()] = line;
  megaQueueCount++;
  markBridgeStatusDirty();
  return true;
}

void dropQueuedLine() {
  if (megaQueueCount == 0) return;

  megaPublishQueue[megaQueueHead] = "";
  megaQueueHead = (megaQueueHead + 1) % MQTT_QUEUE_MAX;
  megaQueueCount--;
  markBridgeStatusDirty();
}

void flushMegaPublishQueue() {
  if (!client.connected()) return;

  uint8_t sent = 0;
  while (megaQueueCount > 0 && sent < MQTT_FLUSH_BURST) {
    String line = megaPublishQueue[megaQueueHead];
    const bool retained = line.startsWith("MEGA|STATUS|");
    const char* topic = retained ? TOPIC_STATUS : TOPIC_LOGS;

    if (!client.publish(topic, line.c_str(), retained)) {
      if (!client.connected()) break;
      droppedPublishLines++;
      dropQueuedLine();
      continue;
    }

    dropQueuedLine();
    sent++;
  }
}

void publishBridgeStatus(bool force) {
  if (!client.connected()) return;
  if (!force && !bridgeStatusDirty && millis() - lastBridgeStatusMs < 10000) return;

  String payload;
  payload.reserve(120);
  payload += "ESP32|BRIDGE|QUEUE=";
  payload += megaQueueCount;
  payload += "|DROP_UART=";
  payload += droppedUartLines;
  payload += "|DROP_PUB=";
  payload += droppedPublishLines;
  payload += "|WIFI=";
  payload += (WiFi.status() == WL_CONNECTED) ? "1" : "0";
  payload += "|MQTT=";
  payload += client.connected() ? "1" : "0";

  client.publish(TOPIC_BRIDGE, payload.c_str(), true);
  lastBridgeStatusMs = millis();
  bridgeStatusDirty = false;
}

// =====================
// Wi-Fi bağlan
// =====================
bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.setSleep(false);

  const int MAX_TRIES = 6;
  const unsigned long TRY_MS = 15000;

  for (int attempt = 1; attempt <= MAX_TRIES; attempt++) {
    Serial.printf("WiFi baglaniyor (%d/%d): %s\n", attempt, MAX_TRIES, ssid);

    WiFi.disconnect(true, true);
    delay(300);
    WiFi.mode(WIFI_OFF);
    delay(300);
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    delay(200);

    WiFi.begin(ssid, password);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < TRY_MS) {
      delay(400);
      Serial.print('.');
      readMegaSerialAndQueue();
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("WiFi baglandi");
      Serial.print("IP: ");
      Serial.println(WiFi.localIP());
      markBridgeStatusDirty();
      return true;
    }

    Serial.println("WiFi baglanamadi, tekrar denenecek...");
    delay(800);
  }

  Serial.println("WiFi baglanamadi.");
  return false;
}

// =====================
// MQTT bağlan
// =====================
bool connectMQTT() {
  clientId = "ESP32_" + String((uint32_t)ESP.getEfuseMac(), HEX);

  Serial.print("MQTT baglaniliyor... host=");
  Serial.print(mqtt_host);
  Serial.print(" cid=");
  Serial.println(clientId);

  const char* willMsg = "offline";

  bool ok = client.connect(
    clientId.c_str(),
    TOPIC_LWT,
    0,
    true,
    willMsg
  );

  if (!ok) {
    Serial.print("MQTT baglanti hatasi, state=");
    Serial.println(client.state());
    return false;
  }

  Serial.println("MQTT baglandi");

  client.subscribe(TOPIC_CMD);
  client.publish(TOPIC_HEARTBEAT, "online", true);
  client.publish(TOPIC_HEARTBEAT, "boot", false);
  publishBridgeStatus(true);

  return true;
}

void ensureMQTTConnected() {
  if (client.connected()) return;

  static unsigned long lastTry = 0;
  if (millis() - lastTry < 8000) return;
  lastTry = millis();

  connectMQTT();
}

// =====================
// MEGA seri hattini oku
// =====================
void readMegaSerialAndQueue() {
  while (Serial2.available()) {
    char c = (char)Serial2.read();

    if (c == '\r') continue;

    if (c == '\n') {
      megaLineBuffer.trim();

      if (megaLineBuffer.length() > 0) {
        if (megaLineOverflow) {
          megaLineBuffer += "|TRUNC=1";
          megaLineOverflow = false;
        }

        Serial.print("MEGA -> ");
        Serial.println(megaLineBuffer);
        enqueueMegaLineForPublish(megaLineBuffer);
      }

      megaLineBuffer = "";
      megaLineOverflow = false;
    } else if (megaLineBuffer.length() < MEGA_LINE_MAX) {
      megaLineBuffer += c;
    } else {
      megaLineOverflow = true;
    }
  }
}

// =====================
// Setup
// =====================
void setup() {
  Serial.begin(115200);
  delay(200);

  Serial2.setRxBufferSize(2048);
  Serial2.begin(MEGA_BAUD, SERIAL_8N1, MEGA_RX_PIN, MEGA_TX_PIN);
  Serial.println("Serial2 basladi (MEGA bridge)");

  client.setServer(mqtt_host, mqtt_port);
  client.setBufferSize(1024);
  client.setCallback(mqttCallback);

  if (connectWiFi()) {
    connectMQTT();
    Serial2.println("help");
  }
}

// =====================
// Loop
// =====================
void loop() {
  readMegaSerialAndQueue();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi koptu, yeniden baglaniyorum...");
    connectWiFi();
  }

  if (WiFi.status() == WL_CONNECTED) {
    ensureMQTTConnected();
    client.loop();
    flushMegaPublishQueue();
    publishBridgeStatus(false);
  }

  static unsigned long lastHeartbeat = 0;
  if (millis() - lastHeartbeat >= 10000) {
    lastHeartbeat = millis();

    if (client.connected()) {
      client.publish(TOPIC_HEARTBEAT, "ok", false);
      publishBridgeStatus(true);
    }
  }
}
