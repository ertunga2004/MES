#include <Arduino.h>
#include <Servo.h>

Servo giyotin;

// PINLER
const int SERVO_PIN = 9;
const int BTN_PIN   = 2;

// SERVO POZISYONLARI (senin mekanige gore degistirebilirsin)
const int POS_UP   = 150;
const int POS_DOWN = 0;

// ZAMANLAR
const int STEP_DELAY_MS = 4;
const int HOLD_DOWN_MS  = 1500;

// DURUM
bool busy = false;
bool lastBtn = HIGH;
bool armed = false;   // <<< is secilmeden FALSE

void moveSmooth(int from, int to) {
  if (from < to) {
    for (int p = from; p <= to; p++) { giyotin.write(p); delay(STEP_DELAY_MS); }
  } else {
    for (int p = from; p >= to; p--) { giyotin.write(p); delay(STEP_DELAY_MS); }
  }
  giyotin.write(to);
}

void doOneCut() {
  if (busy) return;
  busy = true;

  Serial.println("CUT_START");

  moveSmooth(giyotin.read(), POS_UP);

  moveSmooth(POS_UP, POS_DOWN);
  Serial.println("CUT_DOWN");
  delay(HOLD_DOWN_MS);

  moveSmooth(POS_DOWN, POS_UP);
  Serial.println("CUT_UP");

  Serial.println("CUT_DONE");
  busy = false;
}

void handleSerial() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  cmd.toUpperCase();

  if (cmd == "ARM") {
    armed = true;
    Serial.println("ARMED");
  } else if (cmd == "DISARM") {
    armed = false;
    Serial.println("DISARMED");
  } else if (cmd == "STATUS") {
    Serial.print("STATUS ");
    Serial.println(armed ? "ARMED" : "DISARMED");
  }
}

void setup() {
  Serial.begin(9600);

  pinMode(BTN_PIN, INPUT_PULLUP);
  giyotin.attach(SERVO_PIN);
  giyotin.write(POS_UP);

  delay(700);
  Serial.println("NANO_READY DISARMED");
}

void loop() {
  handleSerial();

  bool btn = digitalRead(BTN_PIN);

  // buton sadece ARM iken calissin
  if (armed && !busy && lastBtn == HIGH && btn == LOW) {
    Serial.println("BTN_PRESS");
    doOneCut();
    delay(50); // debounce
  }

  lastBtn = btn;
}
