#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_GFX.h>
#include <Adafruit_PCD8544.h>

// ---------------------
// Wi-Fi
// ---------------------
const char* ssid     = "TOMRIS_IoT";
const char* password = "Kataturk1881.";

// ---------------------
// MQTT
// ---------------------
const char* mqttHost = "broker.emqx.io";
const uint16_t mqttPort = 1883;

const char* TOPIC_DISPLAY = "sau/iot/mega/konveyor/picktolight/station/display";
const char* TOPIC_BUTTON = "sau/iot/mega/konveyor/picktolight/station/button";
const char* TOPIC_STATUS = "sau/iot/mega/konveyor/picktolight/station/esp32_status";
const char* TOPIC_HEARTBEAT = "sau/iot/mega/konveyor/picktolight/station/heartbeat";

// ---------------------
// Nokia 5110 pins
// ---------------------
constexpr int PIN_LCD_CLK = 18;
constexpr int PIN_LCD_DIN = 23;
constexpr int PIN_LCD_DC = 27;
constexpr int PIN_LCD_CE = 26;
constexpr int PIN_LCD_RST = 33;

// ---------------------
// Optional button
// ---------------------
constexpr int PIN_BUTTON = 25;
constexpr unsigned long DEBOUNCE_MS = 60;

// ---------------------
// Timing
// ---------------------
constexpr unsigned long WIFI_RETRY_MS = 12000;
constexpr unsigned long MQTT_RETRY_MS = 8000;
constexpr unsigned long HEARTBEAT_MS = 15000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
Adafruit_PCD8544 display(
  PIN_LCD_CLK,
  PIN_LCD_DIN,
  PIN_LCD_DC,
  PIN_LCD_CE,
  PIN_LCD_RST
);

String clientId;
String displayLines[6] = {
  "PickToLight",
  "WiFi bekliyor",
  "",
  "",
  "",
  ""
};

int lastButtonReading = HIGH;
int stableButtonState = HIGH;
unsigned long lastDebounceAt = 0;
unsigned long lastWiFiTryAt = 0;
unsigned long lastMQTTTryAt = 0;
unsigned long lastHeartbeatAt = 0;

void renderDisplay();
void setStatusLines(const String& line1, const String& line2 = "", const String& line3 = "");
void applyDisplayPayload(const String& payload);
void ensureWiFi();
void ensureMQTT();
void publishStatus(const char* statusText);
void publishHeartbeat(const char* statusText);
void readButton();

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  message.reserve(length + 1);

  for (unsigned int index = 0; index < length; index++) {
    message += (char)payload[index];
  }

  message.trim();

  if (String(topic) == TOPIC_DISPLAY) {
    applyDisplayPayload(message);
    renderDisplay();
  }
}

void renderDisplay() {
  display.clearDisplay();
  display.setTextColor(BLACK);
  display.setTextSize(1);

  for (int row = 0; row < 6; row++) {
    display.setCursor(0, row * 8);
    display.print(displayLines[row].substring(0, 14));
  }

  display.display();
}

void setStatusLines(const String& line1, const String& line2, const String& line3) {
  displayLines[0] = "PickToLight";
  displayLines[1] = line1;
  displayLines[2] = line2;
  displayLines[3] = line3;
  displayLines[4] = "";
  displayLines[5] = "";
  renderDisplay();
}

void applyDisplayPayload(const String& payload) {
  int start = 0;
  int row = 0;

  while (row < 6) {
    int separator = payload.indexOf('~', start);
    if (separator < 0) {
      displayLines[row] = payload.substring(start);
      row++;
      break;
    }

    displayLines[row] = payload.substring(start, separator);
    start = separator + 1;
    row++;
  }

  while (row < 6) {
    displayLines[row] = "";
    row++;
  }
}

void publishStatus(const char* statusText) {
  if (!mqttClient.connected()) return;

  String payload = "{\"source\":\"esp32_display\",\"status\":\"";
  payload += statusText;
  payload += "\"}";
  mqttClient.publish(TOPIC_STATUS, payload.c_str(), true);
}

void publishHeartbeat(const char* statusText) {
  if (!mqttClient.connected()) return;

  String payload = "{\"source\":\"esp32_display\",\"status\":\"";
  payload += statusText;
  payload += "\"}";
  mqttClient.publish(TOPIC_HEARTBEAT, payload.c_str(), false);
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastWiFiTryAt < WIFI_RETRY_MS) return;

  lastWiFiTryAt = millis();
  WiFi.disconnect(true, true);
  delay(200);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(ssid, password);
  setStatusLines("WiFi baglaniyor");
}

void ensureMQTT() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqttClient.connected()) return;
  if (millis() - lastMQTTTryAt < MQTT_RETRY_MS) return;

  lastMQTTTryAt = millis();
  setStatusLines("MQTT baglaniyor");

  if (mqttClient.connect(clientId.c_str())) {
    mqttClient.subscribe(TOPIC_DISPLAY);
    publishStatus("online");
    publishHeartbeat("online");
    setStatusLines("Display bekliyor");
  }
}

void readButton() {
  int reading = digitalRead(PIN_BUTTON);

  if (reading != lastButtonReading) {
    lastDebounceAt = millis();
    lastButtonReading = reading;
  }

  if ((millis() - lastDebounceAt) > DEBOUNCE_MS) {
    if (reading != stableButtonState) {
      stableButtonState = reading;

      if (stableButtonState == LOW && mqttClient.connected()) {
        mqttClient.publish(TOPIC_BUTTON, "press", false);
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(PIN_BUTTON, INPUT_PULLUP);

  display.begin();
  display.setContrast(57);
  display.clearDisplay();
  display.display();

  setStatusLines("Baslatiliyor");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);

  clientId = "ptl_";
  clientId += String((uint32_t)ESP.getEfuseMac(), HEX);

  mqttClient.setServer(mqttHost, mqttPort);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  ensureWiFi();
  ensureMQTT();

  if (WiFi.status() == WL_CONNECTED && mqttClient.connected()) {
    mqttClient.loop();
    readButton();

    if (millis() - lastHeartbeatAt >= HEARTBEAT_MS) {
      lastHeartbeatAt = millis();
      publishHeartbeat("ok");
    }
  } else if (WiFi.status() != WL_CONNECTED) {
    setStatusLines("WiFi yok");
  }

  delay(15);
}
