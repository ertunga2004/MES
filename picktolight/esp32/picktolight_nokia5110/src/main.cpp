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
const char* TOPIC_COMMAND = "sau/iot/mega/konveyor/picktolight/station/command";
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
constexpr unsigned long DEBOUNCE_MS = 35;
constexpr unsigned long DOUBLE_CLICK_MS = 320;
constexpr unsigned long RESET_HOLD_MS = 3000;
constexpr uint8_t MAX_QUEUED_PRESSES = 6;
constexpr uint8_t MAX_QUEUED_COMMANDS = 3;

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
bool buttonPressed = false;
bool longPressTriggered = false;
bool pendingSingleClick = false;
unsigned long lastDebounceAt = 0;
unsigned long buttonPressStartedAt = 0;
unsigned long firstClickReleasedAt = 0;
unsigned long lastWiFiTryAt = 0;
unsigned long lastMQTTTryAt = 0;
unsigned long lastHeartbeatAt = 0;
uint8_t queuedPressCount = 0;
uint8_t queuedUndoCount = 0;
uint8_t queuedResetCount = 0;

void renderDisplay();
void setStatusLines(const String& line1, const String& line2 = "", const String& line3 = "");
void applyDisplayPayload(const String& payload);
void ensureWiFi();
void ensureMQTT();
void publishStatus(const char* statusText);
void publishHeartbeat(const char* statusText);
bool publishCommand(const char* action);
bool publishButtonPress();
void flushPendingButtonActions();
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

bool publishCommand(const char* action) {
  if (!mqttClient.connected()) return false;

  String payload = "{\"source\":\"esp32_display\",\"action\":\"";
  payload += action;
  payload += "\"}";
  return mqttClient.publish(TOPIC_COMMAND, payload.c_str(), false);
}

bool publishButtonPress() {
  if (!mqttClient.connected()) return false;
  return mqttClient.publish(TOPIC_BUTTON, "press", false);
}

void flushPendingButtonActions() {
  if (pendingSingleClick && millis() - firstClickReleasedAt >= DOUBLE_CLICK_MS) {
    pendingSingleClick = false;
    if (queuedPressCount < MAX_QUEUED_PRESSES) {
      queuedPressCount++;
    }
    Serial.println("Button short press queued");
  }

  if (!mqttClient.connected()) return;

  if (queuedResetCount > 0) {
    if (publishCommand("reset")) {
      queuedResetCount--;
      Serial.println("Reset command sent");
    }
    return;
  }

  if (queuedUndoCount > 0) {
    if (publishCommand("undo")) {
      queuedUndoCount--;
      Serial.println("Undo command sent");
    }
    return;
  }

  if (queuedPressCount > 0) {
    if (publishButtonPress()) {
      queuedPressCount--;
      Serial.println("Button short press sent");
    }
  }
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

      if (stableButtonState == LOW) {
        buttonPressed = true;
        longPressTriggered = false;
        buttonPressStartedAt = millis();
      } else if (buttonPressed) {
        if (!longPressTriggered) {
          if (pendingSingleClick && millis() - firstClickReleasedAt <= DOUBLE_CLICK_MS) {
            pendingSingleClick = false;
            if (queuedUndoCount < MAX_QUEUED_COMMANDS) {
              queuedUndoCount++;
            }
            Serial.println("Button double press queued");
          } else {
            pendingSingleClick = true;
            firstClickReleasedAt = millis();
          }
        }

        buttonPressed = false;
        longPressTriggered = false;
      }
    }
  }

  if (
    buttonPressed &&
    !longPressTriggered &&
    millis() - buttonPressStartedAt >= RESET_HOLD_MS
  ) {
    pendingSingleClick = false;
    if (queuedResetCount < MAX_QUEUED_COMMANDS) {
      queuedResetCount++;
    }
    longPressTriggered = true;
    Serial.println("Button long press reset queued");
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
  readButton();
  flushPendingButtonActions();

  if (WiFi.status() == WL_CONNECTED && mqttClient.connected()) {
    mqttClient.loop();

    if (millis() - lastHeartbeatAt >= HEARTBEAT_MS) {
      lastHeartbeatAt = millis();
      publishHeartbeat("ok");
    }
  } else if (WiFi.status() != WL_CONNECTED) {
    setStatusLines("WiFi yok");
  }

  delay(5);
}
