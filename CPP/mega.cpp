#include <Arduino.h>
#include <Servo.h>
#include <EEPROM.h>
// Forward declarations to avoid Arduino auto-prototype issues
struct CalibData;
struct SensorSample {
  int R;
  int G;
  int B;
  long dXRaw;
  long relSum;
  String cls;
  bool objectPresent;
  bool confident;
};
struct PendingItem {
  String color;
  String decisionSource;
  unsigned long itemId;
  unsigned long measureId;
  unsigned long travelMs;
  bool reviewRequired;
};
// --- Forward declarations (Arduino needs these because functions below use step globals) ---
extern bool stepRunning;
void stepTick();
void stepStop();
void stepStartMove(long steps);
void stepStartMoveWithLimit(long steps, int dirToWatch, uint8_t pinToWatch);
void servoTick();
void delayWithStep(unsigned long ms);
void logEvent(const char* module, const String& msg);
void logAlarm(const char* code, const String& msg);
void printStatus();
void publishStatusNow();
void pausePendingTravelTimer();
const char* autoStateStr();
bool startQueuedPick(const String& triggerSource, unsigned long requestedItemId, bool logReject);
void clearPickRuntime();
extern bool pickStarted;
extern String activePickTriggerSource;
extern unsigned long activePickItemId;
extern unsigned long activePickMeasureId;
extern String activePickColor;
extern String activePickDecisionSource;
extern bool activePickReviewRequired;
extern bool activePickCompletedLogged;
void logActivePickCompleted(const char* stateLabel);
void logActivePickReturnDone(const char* stateLabel, bool useQueueLabel, uint8_t queueDepth);
long dist3(int r1,int g1,int b1,int r2,int g2,int b2);
const char* calibrationWorkflowExpectedLabel();
const char* calibrationWorkflowNextLabel(uint8_t step);
uint8_t calibrationWorkflowForTarget(const String& w);
void resetCalibrationWorkflow(bool announce);


/* =========================
   (1) KONVEYOR (L298N #1) PINLERİ
   NOT: DC motor OUT3-OUT4 kullanılıyor.
        Bu yüzden kontrol tarafında ENB + IN3 + IN4 kullanılacak.
   ========================= */
const int ENB = 5;   // PWM (L298N ENB)
const int IN3 = 8;   // L298N IN3
const int IN4 = 7;   // L298N IN4

int motorSpeed = 180;
bool dirForward = true;

void motorRun() {
  if (dirForward) { digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); }
  else            { digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH); }
  analogWrite(ENB, motorSpeed);
}
void motorStop() {
  analogWrite(ENB, 0);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

/* =========================
   (0) SERVO PINLERİ (MEGA)
   Servo sinyalleri: 10, 11, 12, 13 (kullanıcı sabitledi)
   Güç: 5V SMPS (+) / GND barası (-)  (MEGA 5V'dan BESLEME YOK)
   ========================= */
Servo sv1, sv2, sv3, sv4;
const uint8_t SV1_PIN = 10;
const uint8_t SV2_PIN = 11;
const uint8_t SV3_PIN = 12;
const uint8_t SV4_PIN = 13;

enum ServoAxis : uint8_t {
  SERVO_S1 = 0,
  SERVO_S2 = 1,
  SERVO_S3 = 2,
  SERVO_S4 = 3,
  SERVO_COUNT = 4
};

const unsigned long SERVO_STEP_INTERVAL_MS[SERVO_COUNT] = {12, 12, 12, 8};
int servoCurrent[SERVO_COUNT] = {90, 90, 90, 90};
int servoTarget[SERVO_COUNT]  = {90, 90, 90, 90};
unsigned long servoLastStepMs[SERVO_COUNT] = {0, 0, 0, 0};

/* =========================
   (3B) LIMIT SWITCH (MEGA)
   22: alma (smove + iken son nokta)
   23: birakma (smove - iken son nokta)
   ========================= */
const uint8_t LIM_PICK_PIN  = 22;
const uint8_t LIM_DROP_PIN  = 23;

// çoğu limit switch GND'ye basar -> INPUT_PULLUP ile LOW = basildi
const bool SWITCH_ACTIVE_LOW = true;

bool isSwitchPressed(uint8_t pin){
  int v = digitalRead(pin);
  return SWITCH_ACTIVE_LOW ? (v == LOW) : (v == HIGH);
}


static inline int clampAngle(int a){ return constrain(a, 0, 180); }

Servo& servoByAxis(uint8_t axis){
  switch(axis){
    case SERVO_S1: return sv1;
    case SERVO_S2: return sv2;
    case SERVO_S3: return sv3;
    default:       return sv4;
  }
}

void servoSetImmediate(uint8_t axis, int angle){
  angle = clampAngle(angle);
  servoCurrent[axis] = angle;
  servoTarget[axis] = angle;
  servoLastStepMs[axis] = millis();
  servoByAxis(axis).write(angle);
}

void servoSetTarget(uint8_t axis, int angle){
  servoTarget[axis] = clampAngle(angle);
}

bool servoAtTarget(uint8_t axis){
  return servoCurrent[axis] == servoTarget[axis];
}

bool servosAtTarget(){
  for(uint8_t axis = 0; axis < SERVO_COUNT; axis++){
    if(!servoAtTarget(axis)) return false;
  }
  return true;
}

void servoTick(){
  unsigned long now = millis();
  for(uint8_t axis = 0; axis < SERVO_COUNT; axis++){
    if(servoCurrent[axis] == servoTarget[axis]) continue;
    if(now - servoLastStepMs[axis] < SERVO_STEP_INTERVAL_MS[axis]) continue;
    servoLastStepMs[axis] = now;
    servoCurrent[axis] += (servoTarget[axis] > servoCurrent[axis]) ? 1 : -1;
    servoByAxis(axis).write(servoCurrent[axis]);
  }
}

void waitForServo(uint8_t axis, unsigned long timeoutMs = 2500){
  unsigned long t0 = millis();
  while(!servoAtTarget(axis) && (millis() - t0 < timeoutMs)){
    delayWithStep(1);
  }
}

void waitForServos(unsigned long timeoutMs = 4000){
  unsigned long t0 = millis();
  while(!servosAtTarget() && (millis() - t0 < timeoutMs)){
    delayWithStep(1);
  }
}

void setServos(int a1, int a2, int a3, int a4){
  servoSetTarget(SERVO_S1, a1);
  servoSetTarget(SERVO_S2, a2);
  servoSetTarget(SERVO_S3, a3);
  servoSetTarget(SERVO_S4, a4);
}

void setServosImmediate(int a1, int a2, int a3, int a4){
  servoSetImmediate(SERVO_S1, a1);
  servoSetImmediate(SERVO_S2, a2);
  servoSetImmediate(SERVO_S3, a3);
  servoSetImmediate(SERVO_S4, a4);
}

void moveServosBlocking(int a1, int a2, int a3, int a4){
  setServos(a1, a2, a3, a4);
  waitForServos();
}

void moveServoBlocking(uint8_t axis, int angle, unsigned long timeoutMs = 2500){
  servoSetTarget(axis, angle);
  waitForServo(axis, timeoutMs);
}


/* =========================
   (3C) ROBOT KOL SEKANSLARI
   ========================= */
void goPickPose(){
  // Alma konumu: s1:90,s2:130,s3:20,s4:100
  moveServosBlocking(90, 130, 20, 100);
}

void gripBox(){
  // Kapatmayi kademeli yap ki gripper urune sert vurmasin.
  moveServoBlocking(SERVO_S4, 160);
  delayWithStep(80);
  moveServoBlocking(SERVO_S4, 155);
}

void goLiftPose(){
  // Kutuyu kaldırma: s2:140,s3:30,s1:160 (kutuyu havaya al / güvenli taşıma)
  delayWithStep(500);
  moveServosBlocking(160, 140, 30, 155);
  delayWithStep(120);
}

void goTravelPose(){
  // Taşıma pozu: kafa YUKARIDA kalsın ki dönüşte kutuya/konveyöre çarpmasın
  // Not: s4 burada 170 (kapalı) kalsın, istersen 155 de olur.
  moveServosBlocking(160, 140, 30, 170);
  delayWithStep(120);
}

void releaseBox(){
  // Bırak: s4:100, sonra reset: s4:170
  moveServoBlocking(SERVO_S4, 100);
  delayWithStep(150);
  moveServoBlocking(SERVO_S4, 170);
  delayWithStep(120);
}

void runStepUntilStopOrTimeout(unsigned long timeoutMs){
  unsigned long t0 = millis();
  while(stepRunning){
    stepTick();
    servoTick();
    if(millis() - t0 > timeoutMs){
      logEvent("STEP", "ERROR=TIMEOUT|ACTION=STOP");
      stepStop();
      break;
    }
  }
}


void homeToPickLimit22(){
  logEvent("STEP", "HOME_START|TARGET=LIM22");
  // Güvenlik: homing sırasında kafa yukarıda olsun //geri dönerken lazım
  //goTravelPose();

  // 22 zaten basılıysa önce biraz geri kaç (switch'i bırak)
  if(isSwitchPressed(LIM_PICK_PIN)){
    stepStartMove(-30);                 // gerekirse 100-800 arası ayarla
    runStepUntilStopOrTimeout(1500);
  }

  // Şimdi + yönde 22'ye yürü ve vurunca dur
  stepStartMoveWithLimit(999999L, +1, LIM_PICK_PIN);
  runStepUntilStopOrTimeout(8000);

  logEvent("STEP", "HOME_DONE|TARGET=LIM22");
}


/* =========================
   (2C) NON-BLOCKING PICK&PLACE (22 -> grip -> 23 -> release -> 22)
   - doPickAndPlace() artik BLOKLAMAZ, sadece baslatir.
   - loop() icinde pickPlaceTick() cagrilmalidir.
   ========================= */

enum PickPlaceState {
  PP_IDLE,
  PP_HOME_ESCAPE_22,
  PP_HOME_GO_22,
  PP_PICK_POSE,
  PP_GRIP_160,
  PP_GRIP_155,
  PP_LIFT_WAIT,
  PP_LIFT_S2,
  PP_LIFT_SET,
  PP_GO_23_START,
  PP_GO_23_WAIT,
  PP_DROP_SETTLE,
  PP_RELEASE_100,
  PP_RELEASE_170,
  PP_TRAVEL_POSE,
  PP_GO_22_START,
  PP_GO_22_WAIT,
  PP_RETURN_ALIGN,
  PP_FINAL_PICKPOSE,
  PP_DONE
};

PickPlaceState ppSt = PP_IDLE;
unsigned long ppT0 = 0;
bool ppMoveStarted = false;
unsigned long ppLimitCooldownUntil = 0;

const long PP_ESCAPE_STEPS_22 = -90;   // 22 basiliysa kacis
const long PP_ESCAPE_STEPS_23 = +90;   // 23 basiliysa kacis (ters yone kac)
const unsigned long LIMIT_COOLDOWN_MS = 120;
const unsigned long DROP_SETTLE_MS = 200;

static inline bool ppElapsed(unsigned long ms){ return (millis() - ppT0) >= ms; }
static inline void ppEnter(uint8_t s){ ppSt = (PickPlaceState)s; ppT0 = millis(); ppMoveStarted = false; }

void pickPlaceStart(){
  if(ppSt != PP_IDLE && ppSt != PP_DONE) return; // zaten calisiyor
  logEvent("ROBOT", "PICKPLACE=START|MODE=NONBLOCKING");
  ppEnter((uint8_t)PP_HOME_ESCAPE_22);
}

bool pickPlaceBusy(){
  return (ppSt != PP_IDLE && ppSt != PP_DONE);
}
bool pickPlaceDone(){
  return (ppSt == PP_DONE);
}
void pickPlaceResetDone(){
  if(ppSt == PP_DONE) ppSt = PP_IDLE;
}

void pickPlaceTick(){
  // step her zaman akmali
  stepTick();
  servoTick();

  // limit spam azaltma: limit vurunca bir sure yeni hareket baslatma
  bool cool = (millis() < ppLimitCooldownUntil);

  switch(ppSt){
    case PP_IDLE: return;

    case PP_HOME_ESCAPE_22: {
      // 22 zaten basiliysa once kac
      if(isSwitchPressed(LIM_PICK_PIN)){
        if(!ppMoveStarted && !stepRunning && !cool){
          stepStartMove(PP_ESCAPE_STEPS_22);
          ppMoveStarted = true;
        }
        // kacis bitince devam
        if(ppMoveStarted && !stepRunning){
          ppLimitCooldownUntil = millis() + LIMIT_COOLDOWN_MS;
          ppEnter((uint8_t)PP_HOME_GO_22);
        }
      } else {
        ppEnter((uint8_t)PP_HOME_GO_22);
      }
      return;
    }

    case PP_HOME_GO_22: {
      // 22 zaten basiliysa direkt pick pose'a gec
      if(isSwitchPressed(LIM_PICK_PIN)){
        logEvent("ROBOT", "PICKPLACE=HOME_OK|LIMIT=LIM22");
        ppEnter((uint8_t)PP_PICK_POSE);
        return;
      }
      if(!ppMoveStarted && !stepRunning && !cool){
        stepStartMoveWithLimit(999999L, +1, LIM_PICK_PIN);
        ppMoveStarted = true;
      }
      if(ppMoveStarted && !stepRunning){
        ppLimitCooldownUntil = millis() + LIMIT_COOLDOWN_MS;
        logEvent("ROBOT", "PICKPLACE=HOME_REACHED|LIMIT=LIM22");
        ppEnter((uint8_t)PP_PICK_POSE);
      }
      return;
    }

    case PP_PICK_POSE: {
      setServos(90, 130, 20, 100);
      if(servosAtTarget()) ppEnter((uint8_t)PP_GRIP_160);
      return;
    }

    case PP_GRIP_160: {
      servoSetTarget(SERVO_S4, 160);
      if(servoAtTarget(SERVO_S4)) ppEnter((uint8_t)PP_GRIP_155);
      return;
    }
    case PP_GRIP_155: {
      servoSetTarget(SERVO_S4, 155);
      if(servoAtTarget(SERVO_S4)) ppEnter((uint8_t)PP_LIFT_WAIT);
      return;
    }

    case PP_LIFT_WAIT: {
      // Once sadece sol servo yukari alinsin; kutuyu arkadaki parcaya surtmeden kaldirsin.
      if(ppElapsed(500)) ppEnter((uint8_t)PP_LIFT_S2);
      return;
    }
    case PP_LIFT_S2: {
      setServos(90, 140, 20, 155);
      if(servoAtTarget(SERVO_S2)) ppEnter((uint8_t)PP_LIFT_SET);
      return;
    }
    case PP_LIFT_SET: {
      setServos(160, 140, 30, 155);
      if(servosAtTarget()) ppEnter((uint8_t)PP_GO_23_START);
      return;
    }

    case PP_GO_23_START: {
      // 23 zaten basiliysa once kac
      if(isSwitchPressed(LIM_DROP_PIN)){
        if(!ppMoveStarted && !stepRunning && !cool){
          stepStartMove(PP_ESCAPE_STEPS_23);
          ppMoveStarted = true;
        }
        if(ppMoveStarted && !stepRunning){
          ppLimitCooldownUntil = millis() + LIMIT_COOLDOWN_MS;
          ppEnter((uint8_t)PP_GO_23_START); // tekrar dene (artik basili olmayacak)
        }
        return;
      }

      if(!ppMoveStarted && !stepRunning && !cool){
        stepStartMoveWithLimit(-999999L, -1, LIM_DROP_PIN);
        ppMoveStarted = true;
        ppT0 = millis();
        ppSt = PP_GO_23_WAIT;
      }
      return;
    }

    case PP_GO_23_WAIT: {
      // timeout guvenlik
      if(stepRunning){
        if(millis() - ppT0 > 8000){
          logEvent("STEP", "ERROR=TIMEOUT|SOURCE=PICKPLACE|ACTION=STOP");
          stepStop();
        }
        return;
      }
      if(!isSwitchPressed(LIM_DROP_PIN)){
        logEvent("STEP", "WARN=DROP_LIMIT_NOT_REACHED|ACTION=RETRY");
        ppLimitCooldownUntil = millis() + LIMIT_COOLDOWN_MS;
        ppEnter((uint8_t)PP_GO_23_START);
        return;
      }
      ppLimitCooldownUntil = millis() + LIMIT_COOLDOWN_MS;
      logEvent("ROBOT", "PICKPLACE=DROP_REACHED|LIMIT=LIM23");
      ppEnter((uint8_t)PP_DROP_SETTLE);
      return;
    }

    case PP_DROP_SETTLE: {
      if(ppElapsed(DROP_SETTLE_MS)){
        ppEnter((uint8_t)PP_RELEASE_100);
      }
      return;
    }

    case PP_RELEASE_100: {
      servoSetTarget(SERVO_S4, 100);
      if(servoAtTarget(SERVO_S4)){
        logEvent(
          "ROBOT",
          String("EVENT=RELEASED|ITEM_ID=") + activePickItemId
            + "|MEASURE_ID=" + activePickMeasureId
            + "|TRIGGER=" + activePickTriggerSource
        );
        if(pickStarted && !activePickCompletedLogged){
          logActivePickCompleted("WAIT_ARM");
        }
        ppEnter((uint8_t)PP_RELEASE_170);
      }
      return;
    }
    case PP_RELEASE_170: {
      servoSetTarget(SERVO_S4, 170);
      if(servoAtTarget(SERVO_S4)) ppEnter((uint8_t)PP_TRAVEL_POSE);
      return;
    }

    case PP_TRAVEL_POSE: {
      setServos(160, 140, 30, 170);
      if(servosAtTarget()){
        logEvent(
          "ROBOT",
          String("EVENT=RETURN_STARTED|ITEM_ID=") + activePickItemId
            + "|MEASURE_ID=" + activePickMeasureId
            + "|TRIGGER=" + activePickTriggerSource
        );
        ppEnter((uint8_t)PP_GO_22_START);
      }
      return;
    }

    case PP_GO_22_START: {
      // 22 zaten basiliysa gec
      if(isSwitchPressed(LIM_PICK_PIN)){
        logEvent(
          "ROBOT",
          String("EVENT=RETURN_REACHED|ITEM_ID=") + activePickItemId
            + "|MEASURE_ID=" + activePickMeasureId
            + "|LIMIT=LIM22|TRIGGER=" + activePickTriggerSource
        );
        ppEnter((uint8_t)PP_RETURN_ALIGN);
        return;
      }
      if(!ppMoveStarted && !stepRunning && !cool){
        stepStartMoveWithLimit(999999L, +1, LIM_PICK_PIN);
        ppMoveStarted = true;
        ppT0 = millis();
        ppSt = PP_GO_22_WAIT;
      }
      return;
    }

    case PP_GO_22_WAIT: {
      if(stepRunning){
        if(millis() - ppT0 > 8000){
          logEvent("STEP", "ERROR=TIMEOUT|SOURCE=PICKPLACE|ACTION=STOP");
          stepStop();
        }
        return;
      }
      ppLimitCooldownUntil = millis() + LIMIT_COOLDOWN_MS;
      logEvent(
        "ROBOT",
        String("EVENT=RETURN_REACHED|ITEM_ID=") + activePickItemId
          + "|MEASURE_ID=" + activePickMeasureId
          + "|LIMIT=LIM22|TRIGGER=" + activePickTriggerSource
      );
      ppEnter((uint8_t)PP_RETURN_ALIGN);
      return;
    }

    case PP_RETURN_ALIGN: {
      // Donuste sirayi ters cevir: once s1/s3 yaklas, sonra s2 asagi insin.
      setServos(90, 140, 20, 170);
      if(servosAtTarget()) ppEnter((uint8_t)PP_FINAL_PICKPOSE);
      return;
    }

    case PP_FINAL_PICKPOSE: {
      setServos(90, 130, 20, 100);
      if(servosAtTarget()){
        logEvent("ROBOT", "PICKPLACE=RETURN_DONE");
        ppSt = PP_DONE;
      }
      return;
    }

    case PP_DONE: return;
  }
}

// Eski isim korunsun: komut bunu cagiriyordu
void doPickAndPlace(){
  pickPlaceStart();
}

/* =========================
   (3) STEP MOTOR (L298N #2) PINLERİ
   ========================= */
// L298N #2
const int ST_ENA = 44;   // PWM
const int ST_IN1 = 40;
const int ST_IN2 = 41;

const int ST_ENB = 45;   // PWM
const int ST_IN3 = 42;
const int ST_IN4 = 43;

// Step ayarları
volatile long stepTarget = 0;     // kalan adım (pozitif/negatif)
unsigned long stepDelayUs = 1200; // hız: küçük = hızlı
bool stepHold = false;           // bobin tutma
bool stepRunning = false;

bool limitCheckEnabled = false;
uint8_t limitPinToWatch = 255;
int limitDirToWatch = 0; // +1 veya -1

int stepIndex = 0;
// Full-step 4 adım sekansı (bipolar)
const int seq[4][4] = {
  {1,0, 1,0},  // A+ B+
  {0,1, 1,0},  // A- B+
  {0,1, 0,1},  // A- B-
  {1,0, 0,1}   // A+ B-
};

void stepApplyIndex(int idx){
  idx = (idx % 4 + 4) % 4;
  digitalWrite(ST_IN1, seq[idx][0]);
  digitalWrite(ST_IN2, seq[idx][1]);
  digitalWrite(ST_IN3, seq[idx][2]);
  digitalWrite(ST_IN4, seq[idx][3]);
}

void stepEnable(bool en){
  if(en){
    analogWrite(ST_ENA, 255);
    analogWrite(ST_ENB, 255);
  } else {
    analogWrite(ST_ENA, 0);
    analogWrite(ST_ENB, 0);
  }
}

void stepRelease(){
  digitalWrite(ST_IN1, LOW); digitalWrite(ST_IN2, LOW);
  digitalWrite(ST_IN3, LOW); digitalWrite(ST_IN4, LOW);
  stepEnable(false);
}

void stepStartMove(long steps){
  if(steps == 0) return;
  stepTarget = steps;
  stepRunning = true;
  stepEnable(true);
  stepApplyIndex(stepIndex);
}

void stepStartMoveWithLimit(long steps, int dirToWatch, uint8_t pinToWatch){
  if(steps == 0) return;
  limitCheckEnabled = true;
  limitDirToWatch = dirToWatch;   // +1 veya -1
  limitPinToWatch = pinToWatch;   // 22 veya 23
  stepStartMove(steps);
}


void stepStop(){
  limitCheckEnabled = false;
  limitPinToWatch = 255;
  limitDirToWatch = 0;

  stepTarget = 0;
  stepRunning = false;
  if(stepHold){
    stepEnable(true);
    stepApplyIndex(stepIndex);
  } else {
    stepRelease();
  }
}

// Non-blocking step update (loop kilitlenmez)
void stepTick(){
  static unsigned long lastUs = 0;
  if(!stepRunning) return;

  unsigned long now = micros();
  if(now - lastUs < stepDelayUs) return;
  lastUs = now;

  int dir = (stepTarget > 0) ? +1 : -1;

  // Limit kontrolu: sadece izlenen yone giderken tetikle
  if(limitCheckEnabled && limitPinToWatch != 255){
    if(dir == limitDirToWatch && isSwitchPressed(limitPinToWatch)){
      Serial1.print("MEGA|LIMIT|HIT|PIN=");
      Serial1.println(limitPinToWatch);
      stepStop();
      return;
    }
  }

  stepIndex += dir;
  stepApplyIndex(stepIndex);
  stepTarget -= dir;

  if(stepTarget == 0){
    stepStop();
  }
}

/* =========================
   STEP DOSTU BEKLEME / PULSE OKUMA
   ========================= */
void delayWithStep(unsigned long ms){
  unsigned long t0 = millis();
  while(millis() - t0 < ms){
    stepTick();
    servoTick();
    // istersen burada başka tick'ler de eklenebilir
  }
}

// pulseIn alternatif: stepTick çağırarak pulse ölçer
unsigned long pulseInStep(uint8_t pin, uint8_t state, unsigned long timeout_us){
  unsigned long start = micros();

  // 1) önce pinin "state değil" hale gelmesini bekle (önceki pulse kalıntısı vs.)
  while(digitalRead(pin) == state){
    stepTick();
    servoTick();
    if(micros() - start >= timeout_us) return 0UL;
  }

  // 2) pulse başlangıcını bekle
  while(digitalRead(pin) != state){
    stepTick();
    servoTick();
    if(micros() - start >= timeout_us) return 0UL;
  }

  // 3) pulse süresini ölç
  unsigned long pulseStart = micros();
  while(digitalRead(pin) == state){
    stepTick();
    servoTick();
    if(micros() - start >= timeout_us) return 0UL;
  }
  return micros() - pulseStart;
}

/* =========================
   (2) TCS3200 PINLERİ
   ========================= */
#define S0 2
#define S1 3
#define S2 4
#define S3 6
#define OUT_PIN 9

const int N = 10;

bool hasR=false, hasY=false, hasB=false, hasX=false;
int RR, RG, RB;
int YR, YG, YB;
int BRr, BGg, BBb;
int XR, XG, XB;

struct ColorSignature {
  int rawR;
  int rawG;
  int rawB;
  int contrastR;
  int contrastG;
  int contrastB;
  int invNormR;
  int invNormG;
  int invNormB;
};

ColorSignature sigR;
ColorSignature sigY;
ColorSignature sigB;

bool calibrationModelReady = false;
int runtimeXR = 0;
int runtimeXG = 0;
int runtimeXB = 0;
bool runtimeEmptyReady = false;
uint16_t runtimeEmptySamples = 0;

long emptyDistanceThresholdRaw = 150;
long objectContrastThreshold = 1000;
long colorDecisionGapThreshold = 120;

static const uint8_t CAL_FLOW_COMPLETE = 0;
static const uint8_t CAL_FLOW_EXPECT_X = 1;
static const uint8_t CAL_FLOW_EXPECT_R = 2;
static const uint8_t CAL_FLOW_EXPECT_Y = 3;
static const uint8_t CAL_FLOW_EXPECT_B = 4;

uint8_t calibrationWorkflowStep = CAL_FLOW_COMPLETE;

// ---------- EEPROM Calibration ----------
struct CalibData {
  uint32_t magic;
  uint8_t  version;
  uint8_t  flags; // bit0 R, bit1 Y, bit2 B, bit3 X
  uint16_t RR, RG, RB;
  uint16_t YR, YG, YB;
  uint16_t BRr, BGg, BBb;
  uint16_t XR, XG, XB;
  uint16_t crc;
};

static const uint32_t CAL_MAGIC = 0xC0A1B123UL;
static const uint8_t  CAL_VER   = 1;
static const int EEPROM_ADDR_CAL = 0;

static uint16_t calCrc(const CalibData &c){
  // very simple checksum: sum of bytes except crc field
  const uint8_t *p = (const uint8_t*)&c;
  size_t n = sizeof(CalibData) - sizeof(uint16_t);
  uint32_t sum = 0;
  for(size_t i=0;i<n;i++) sum += p[i];
  return (uint16_t)(sum & 0xFFFF);
}

static void applyCalib(const CalibData &c){
  hasR = (c.flags & 0x01); hasY = (c.flags & 0x02); hasB = (c.flags & 0x04); hasX = (c.flags & 0x08);
  RR=c.RR; RG=c.RG; RB=c.RB;
  YR=c.YR; YG=c.YG; YB=c.YB;
  BRr=c.BRr; BGg=c.BGg; BBb=c.BBb;
  XR=c.XR; XG=c.XG; XB=c.XB;
}

static void fillCalib(CalibData &c){
  c.magic = CAL_MAGIC;
  c.version = CAL_VER;
  c.flags = (hasR?0x01:0) | (hasY?0x02:0) | (hasB?0x04:0) | (hasX?0x08:0);
  c.RR=RR; c.RG=RG; c.RB=RB;
  c.YR=YR; c.YG=YG; c.YB=YB;
  c.BRr=BRr; c.BGg=BGg; c.BBb=BBb;
  c.XR=XR; c.XG=XG; c.XB=XB;
  c.crc = 0;
  c.crc = calCrc(c);
}

static void setDefaultCalib(){
  // "İçine gömülü" başlangıç kalibrasyonu (sonradan 'cal' ile iyileştirilebilir)
  hasR=true; hasY=true; hasB=true; hasX=true;

  RR=90; RG=30; RB=30;     // kırmızı tahmini
  YR=80; YG=80; YB=30;     // sarı tahmini
  BRr=40; BGg=30; BBb=110; // mavi tahmini
  XR=20; XG=20; XB=20;     // boş/arka plan tahmini
}

static bool loadCalibrationEEPROM(){
  CalibData c;
  EEPROM.get(EEPROM_ADDR_CAL, c);
  if(c.magic != CAL_MAGIC) return false;
  if(c.version != CAL_VER) return false;
  uint16_t crc = c.crc;
  c.crc = 0;
  if(calCrc(c) != crc) return false;
  c.crc = crc;
  applyCalib(c);
  return true;
}

static void saveCalibrationEEPROM(){
  CalibData c;
  fillCalib(c);
  EEPROM.put(EEPROM_ADDR_CAL, c);
}

static void normalizeInverseRGB(int Rm, int Gm, int Bm, int &Rn, int &Gn, int &Bn){
  long iR = 1000000L / max(Rm, 1);
  long iG = 1000000L / max(Gm, 1);
  long iB = 1000000L / max(Bm, 1);
  long sum = iR + iG + iB;

  if(sum <= 0){
    Rn = Gn = Bn = 0;
    return;
  }

  Rn = (int)((iR * 1000L) / sum);
  Gn = (int)((iG * 1000L) / sum);
  Bn = 1000 - Rn - Gn;
}

static void buildContrastRGB(int sampleR, int sampleG, int sampleB,
                             int emptyR, int emptyG, int emptyB,
                             int &contrastR, int &contrastG, int &contrastB){
  contrastR = constrain((int)(((long)(emptyR - sampleR) * 1000L) / max(emptyR, 1)), -1000, 1000);
  contrastG = constrain((int)(((long)(emptyG - sampleG) * 1000L) / max(emptyG, 1)), -1000, 1000);
  contrastB = constrain((int)(((long)(emptyB - sampleB) * 1000L) / max(emptyB, 1)), -1000, 1000);
}

#define APPLY_SIGNATURE(SIG, SAMPLE_R, SAMPLE_G, SAMPLE_B, EMPTY_R, EMPTY_G, EMPTY_B) do { \
  (SIG).rawR = (SAMPLE_R); \
  (SIG).rawG = (SAMPLE_G); \
  (SIG).rawB = (SAMPLE_B); \
  buildContrastRGB((SAMPLE_R), (SAMPLE_G), (SAMPLE_B), (EMPTY_R), (EMPTY_G), (EMPTY_B), \
                   (SIG).contrastR, (SIG).contrastG, (SIG).contrastB); \
  normalizeInverseRGB((SAMPLE_R), (SAMPLE_G), (SAMPLE_B), \
                      (SIG).invNormR, (SIG).invNormG, (SIG).invNormB); \
} while(0)

static void effectiveEmpty(int &emptyR, int &emptyG, int &emptyB){
  if(runtimeEmptyReady){
    emptyR = runtimeXR;
    emptyG = runtimeXG;
    emptyB = runtimeXB;
    return;
  }

  emptyR = XR;
  emptyG = XG;
  emptyB = XB;
}

static void resetRuntimeEmpty(){
  runtimeXR = XR;
  runtimeXG = XG;
  runtimeXB = XB;
  runtimeEmptyReady = hasX;
  runtimeEmptySamples = 0;
}

static void updateRuntimeEmpty(int sampleR, int sampleG, int sampleB){
  if(!hasX) return;
  if(!runtimeEmptyReady) resetRuntimeEmpty();

  const long KEEP_PCT = 82L;
  const long ADD_PCT = 18L;

  runtimeXR = (int)((runtimeXR * KEEP_PCT + (long)sampleR * ADD_PCT + 50L) / 100L);
  runtimeXG = (int)((runtimeXG * KEEP_PCT + (long)sampleG * ADD_PCT + 50L) / 100L);
  runtimeXB = (int)((runtimeXB * KEEP_PCT + (long)sampleB * ADD_PCT + 50L) / 100L);
  if(runtimeEmptySamples < 65535U) runtimeEmptySamples++;
}

static long signatureScore(int sampleContrastR, int sampleContrastG, int sampleContrastB,
                           int sampleInvR, int sampleInvG, int sampleInvB,
                           int refContrastR, int refContrastG, int refContrastB,
                           int refInvR, int refInvG, int refInvB){
  long dContrast = dist3(sampleContrastR, sampleContrastG, sampleContrastB,
                         refContrastR, refContrastG, refContrastB);
  long dInv = dist3(sampleInvR, sampleInvG, sampleInvB,
                    refInvR, refInvG, refInvB);
  return (dContrast * 3L) + (dInv / 2L);
}

static void colorScoresForRaw(int sampleR, int sampleG, int sampleB,
                              long &scoreR, long &scoreY, long &scoreB){
  int emptyR, emptyG, emptyB;
  effectiveEmpty(emptyR, emptyG, emptyB);

  ColorSignature sampleSig;
  APPLY_SIGNATURE(sampleSig, sampleR, sampleG, sampleB, emptyR, emptyG, emptyB);

  scoreR = signatureScore(sampleSig.contrastR, sampleSig.contrastG, sampleSig.contrastB,
                          sampleSig.invNormR, sampleSig.invNormG, sampleSig.invNormB,
                          sigR.contrastR, sigR.contrastG, sigR.contrastB,
                          sigR.invNormR, sigR.invNormG, sigR.invNormB);
  scoreY = signatureScore(sampleSig.contrastR, sampleSig.contrastG, sampleSig.contrastB,
                          sampleSig.invNormR, sampleSig.invNormG, sampleSig.invNormB,
                          sigY.contrastR, sigY.contrastG, sigY.contrastB,
                          sigY.invNormR, sigY.invNormG, sigY.invNormB);
  scoreB = signatureScore(sampleSig.contrastR, sampleSig.contrastG, sampleSig.contrastB,
                          sampleSig.invNormR, sampleSig.invNormG, sampleSig.invNormB,
                          sigB.contrastR, sigB.contrastG, sigB.contrastB,
                          sigB.invNormR, sigB.invNormG, sigB.invNormB);
}

static void rebuildCalibrationModel(){
  calibrationModelReady = false;
  if(!(hasR && hasY && hasB && hasX)) return;

  APPLY_SIGNATURE(sigR, RR, RG, RB, XR, XG, XB);
  APPLY_SIGNATURE(sigY, YR, YG, YB, XR, XG, XB);
  APPLY_SIGNATURE(sigB, BRr, BGg, BBb, XR, XG, XB);

  long dEmptyR = dist3(RR, RG, RB, XR, XG, XB);
  long dEmptyY = dist3(YR, YG, YB, XR, XG, XB);
  long dEmptyB = dist3(BRr, BGg, BBb, XR, XG, XB);
  long minEmptyRaw = dEmptyR;
  if(dEmptyY < minEmptyRaw) minEmptyRaw = dEmptyY;
  if(dEmptyB < minEmptyRaw) minEmptyRaw = dEmptyB;
  emptyDistanceThresholdRaw = constrain(minEmptyRaw / 3L, 90L, 220L);

  long relSumR = (long)sigR.contrastR + (long)sigR.contrastG + (long)sigR.contrastB;
  long relSumY = (long)sigY.contrastR + (long)sigY.contrastG + (long)sigY.contrastB;
  long relSumB = (long)sigB.contrastR + (long)sigB.contrastG + (long)sigB.contrastB;
  long minRelSum = relSumR;
  if(relSumY < minRelSum) minRelSum = relSumY;
  if(relSumB < minRelSum) minRelSum = relSumB;
  objectContrastThreshold = constrain(minRelSum / 2L, 650L, 1600L);

  long sepRY = signatureScore(sigR.contrastR, sigR.contrastG, sigR.contrastB,
                              sigR.invNormR, sigR.invNormG, sigR.invNormB,
                              sigY.contrastR, sigY.contrastG, sigY.contrastB,
                              sigY.invNormR, sigY.invNormG, sigY.invNormB);
  long sepRB = signatureScore(sigR.contrastR, sigR.contrastG, sigR.contrastB,
                              sigR.invNormR, sigR.invNormG, sigR.invNormB,
                              sigB.contrastR, sigB.contrastG, sigB.contrastB,
                              sigB.invNormR, sigB.invNormG, sigB.invNormB);
  long sepYB = signatureScore(sigY.contrastR, sigY.contrastG, sigY.contrastB,
                              sigY.invNormR, sigY.invNormG, sigY.invNormB,
                              sigB.contrastR, sigB.contrastG, sigB.contrastB,
                              sigB.invNormR, sigB.invNormG, sigB.invNormB);
  long minSep = sepRY;
  if(sepRB < minSep) minSep = sepRB;
  if(sepYB < minSep) minSep = sepYB;
  colorDecisionGapThreshold = constrain(minSep / 4L, 80L, 260L);

  resetRuntimeEmpty();
  calibrationModelReady = true;
}

static void printCalibrationProfile(const char* label, int rawR, int rawG, int rawB,
                                    int sigContrastR, int sigContrastG, int sigContrastB,
                                    int sigInvR, int sigInvG, int sigInvB){
  Serial1.print("MEGA|TCS3200|CAL_PROFILE|LABEL=");
  Serial1.print(label);
  Serial1.print("|RAW_R=");
  Serial1.print(rawR);
  Serial1.print("|RAW_G=");
  Serial1.print(rawG);
  Serial1.print("|RAW_B=");
  Serial1.print(rawB);
  Serial1.print("|SIG_R=");
  Serial1.print(sigContrastR);
  Serial1.print("|SIG_G=");
  Serial1.print(sigContrastG);
  Serial1.print("|SIG_B=");
  Serial1.print(sigContrastB);
  Serial1.print("|INV_R=");
  Serial1.print(sigInvR);
  Serial1.print("|INV_G=");
  Serial1.print(sigInvG);
  Serial1.print("|INV_B=");
  Serial1.println(sigInvB);
}

static void printCalibrationStatus(){
  Serial1.print("MEGA|TCS3200|CAL_STATUS|READY=");
  Serial1.print(calibrationModelReady ? 1 : 0);
  Serial1.print("|HAS_R=");
  Serial1.print(hasR ? 1 : 0);
  Serial1.print("|HAS_Y=");
  Serial1.print(hasY ? 1 : 0);
  Serial1.print("|HAS_B=");
  Serial1.print(hasB ? 1 : 0);
  Serial1.print("|HAS_X=");
  Serial1.print(hasX ? 1 : 0);
  Serial1.print("|EMPTY_RAW_THR=");
  Serial1.print(emptyDistanceThresholdRaw);
  Serial1.print("|OBJ_SIG_THR=");
  Serial1.print(objectContrastThreshold);
  Serial1.print("|GAP_THR=");
  Serial1.println(colorDecisionGapThreshold);

  if(!calibrationModelReady) return;

  printCalibrationProfile("KIRMIZI", RR, RG, RB,
                          sigR.contrastR, sigR.contrastG, sigR.contrastB,
                          sigR.invNormR, sigR.invNormG, sigR.invNormB);
  printCalibrationProfile("SARI", YR, YG, YB,
                          sigY.contrastR, sigY.contrastG, sigY.contrastB,
                          sigY.invNormR, sigY.invNormG, sigY.invNormB);
  printCalibrationProfile("MAVI", BRr, BGg, BBb,
                          sigB.contrastR, sigB.contrastG, sigB.contrastB,
                          sigB.invNormR, sigB.invNormG, sigB.invNormB);

  Serial1.print("MEGA|TCS3200|CAL_RUNTIME|EMPTY_R=");
  Serial1.print(runtimeXR);
  Serial1.print("|EMPTY_G=");
  Serial1.print(runtimeXG);
  Serial1.print("|EMPTY_B=");
  Serial1.print(runtimeXB);
  Serial1.print("|EMPTY_SAMPLES=");
  Serial1.println(runtimeEmptySamples);
}

const char* calibrationWorkflowExpectedLabel(){
  switch(calibrationWorkflowStep){
    case CAL_FLOW_EXPECT_X: return "BOS";
    case CAL_FLOW_EXPECT_R: return "KIRMIZI";
    case CAL_FLOW_EXPECT_Y: return "SARI";
    case CAL_FLOW_EXPECT_B: return "MAVI";
    default: return "DONE";
  }
}

const char* calibrationWorkflowNextLabel(uint8_t step){
  switch(step){
    case CAL_FLOW_EXPECT_X: return "BOS";
    case CAL_FLOW_EXPECT_R: return "KIRMIZI";
    case CAL_FLOW_EXPECT_Y: return "SARI";
    case CAL_FLOW_EXPECT_B: return "MAVI";
    default: return "DONE";
  }
}

uint8_t calibrationWorkflowForTarget(const String& w){
  if(w == "x") return CAL_FLOW_EXPECT_X;
  if(w == "r" || w == "k") return CAL_FLOW_EXPECT_R;
  if(w == "y" || w == "s") return CAL_FLOW_EXPECT_Y;
  if(w == "b" || w == "m") return CAL_FLOW_EXPECT_B;
  return CAL_FLOW_COMPLETE;
}

void resetCalibrationWorkflow(bool announce){
  calibrationWorkflowStep = CAL_FLOW_EXPECT_X;
  if(announce){
    logEvent("TCS3200", "CAL_FLOW=RESET|EXPECTED=BOS");
    Serial1.println("Kalibrasyon sirasi: cal x -> cal r -> cal y -> cal b");
  }
}

int readColor(bool s2, bool s3) {
  digitalWrite(S2, s2);
  digitalWrite(S3, s3);

  // sensör filtre geçişi için kısa settle (bloklamadan)
  delayWithStep(3);

  // pulseIn yerine step-tick’li ölçüm
  // 30ms timeout
  unsigned long pw = pulseInStep(OUT_PIN, LOW, 30000UL);
  if(pw == 0UL) return 30000;
  return (int)pw;
}

void sortInt(int *a, int n){
  for(int i=0;i<n-1;i++){
    for(int j=i+1;j<n;j++){
      if(a[j] < a[i]){ int t=a[i]; a[i]=a[j]; a[j]=t; }
    }
  }
}
int medianInt(int *a, int n){
  sortInt(a, n);
  return a[n/2];
}

void takeMedianRGB(int &Rm, int &Gm, int &Bm){
  int Rs[N], Gs[N], Bs[N];
  for(int i=0;i<N;i++){
    int R = readColor(LOW, LOW);
    int G = readColor(HIGH, LOW);
    int B = readColor(LOW, HIGH);

    Rs[i]=R; Gs[i]=G; Bs[i]=B;

    float BR = (float)B / max(R,1);
    int dBR = B - R;

    Serial1.print("#"); Serial1.print(i+1);
    Serial1.print(" R:"); Serial1.print(R);
    Serial1.print(" G:"); Serial1.print(G);
    Serial1.print(" B:"); Serial1.print(B);
    Serial1.print(" BR="); Serial1.print(BR,2);
    Serial1.print(" dBR="); Serial1.println(dBR);

    // eskiden delay(60) vardı -> step dostu bekleme
    delayWithStep(15);
  }
  Rm = medianInt(Rs, N);
  Gm = medianInt(Gs, N);
  Bm = medianInt(Bs, N);
}

long dist3(int r1,int g1,int b1,int r2,int g2,int b2){
  return (long)abs(r1-r2) + (long)abs(g1-g2) + (long)abs(b1-b2);
}

long colorDistWeighted(int r1,int g1,int b1,int r2,int g2,int b2){
  return (long)abs(r1-r2) + (long)abs(g1-g2) + 2L * (long)abs(b1-b2);
}

void normalizeRGB(int Rm, int Gm, int Bm, int &Rn, int &Gn, int &Bn){
  long sum = (long)Rm + (long)Gm + (long)Bm;
  if(sum <= 0){
    Rn = Gn = Bn = 0;
    return;
  }

  Rn = (int)((long)Rm * 1000L / sum);
  Gn = (int)((long)Gm * 1000L / sum);
  Bn = 1000 - Rn - Gn;
}

long colorDistanceNormalized(int Rm,int Gm,int Bm,int Cr,int Cg,int Cb){
  int Rn, Gn, Bn;
  int CnR, CnG, CnB;

  normalizeRGB(Rm, Gm, Bm, Rn, Gn, Bn);
  normalizeRGB(Cr, Cg, Cb, CnR, CnG, CnB);

  return dist3(Rn, Gn, Bn, CnR, CnG, CnB);
}

String classifyNearest(int Rm,int Gm,int Bm){
  if(!calibrationModelReady)
    return "CAL";

  long dR, dY, dB;
  colorScoresForRaw(Rm, Gm, Bm, dR, dY, dB);

  long dMin = dR;
  String label = "KIRMIZI";
  if(dY < dMin){ dMin = dY; label="SARI"; }
  if(dB < dMin){ dMin = dB; label="MAVI"; }

  return label;
}

String classifyStable(int Rm, int Gm, int Bm, bool &objectPresent, bool &confident,
                      long *dXRawOut = nullptr, long *relSumOut = nullptr){
  if(!calibrationModelReady){
    objectPresent = false;
    confident = false;
    if(dXRawOut) *dXRawOut = 0;
    if(relSumOut) *relSumOut = 0;
    return "CAL";
  }

  int emptyR, emptyG, emptyB;
  effectiveEmpty(emptyR, emptyG, emptyB);

  ColorSignature sampleSig;
  APPLY_SIGNATURE(sampleSig, Rm, Gm, Bm, emptyR, emptyG, emptyB);

  long dXRaw = dist3(Rm, Gm, Bm, emptyR, emptyG, emptyB);
  long relSum = max(sampleSig.contrastR, 0) + max(sampleSig.contrastG, 0) + max(sampleSig.contrastB, 0);
  if(dXRawOut) *dXRawOut = dXRaw;
  if(relSumOut) *relSumOut = relSum;
  objectPresent = ((dXRaw >= emptyDistanceThresholdRaw) && (relSum >= (objectContrastThreshold / 2L)))
               || (relSum >= objectContrastThreshold);

  if(!objectPresent){
    confident = true;
    return "BOS";
  }

  long dRColor = signatureScore(sampleSig.contrastR, sampleSig.contrastG, sampleSig.contrastB,
                                sampleSig.invNormR, sampleSig.invNormG, sampleSig.invNormB,
                                sigR.contrastR, sigR.contrastG, sigR.contrastB,
                                sigR.invNormR, sigR.invNormG, sigR.invNormB);
  long dYColor = signatureScore(sampleSig.contrastR, sampleSig.contrastG, sampleSig.contrastB,
                                sampleSig.invNormR, sampleSig.invNormG, sampleSig.invNormB,
                                sigY.contrastR, sigY.contrastG, sigY.contrastB,
                                sigY.invNormR, sigY.invNormG, sigY.invNormB);
  long dBColor = signatureScore(sampleSig.contrastR, sampleSig.contrastG, sampleSig.contrastB,
                                sampleSig.invNormR, sampleSig.invNormG, sampleSig.invNormB,
                                sigB.contrastR, sigB.contrastG, sigB.contrastB,
                                sigB.invNormR, sigB.invNormG, sigB.invNormB);

  long best = dRColor;
  long second = 2147483647L;
  String label = "KIRMIZI";

  if(dYColor < best){
    second = best;
    best = dYColor;
    label = "SARI";
  } else {
    second = dYColor;
  }

  if(dBColor < best){
    second = best;
    best = dBColor;
    label = "MAVI";
  } else if(dBColor < second){
    second = dBColor;
  }

  confident = ((second - best) >= colorDecisionGapThreshold);
  if(!confident){
    return "BELIRSIZ";
  }

  return label;
}

#undef APPLY_SIGNATURE

SensorSample quickClassifyOnce(){
  SensorSample s;

  s.R = readColor(LOW, LOW);
  s.G = readColor(HIGH, LOW);
  s.B = readColor(LOW, HIGH);
  s.dXRaw = 0;
  s.relSum = 0;
  s.objectPresent = false;
  s.confident = false;

  if(!(hasX && hasR && hasY && hasB)){
    logEvent("TCS3200", "ERROR=CAL_MISSING");
    s.cls = "CAL";
    return s;
  }
  s.cls = classifyStable(s.R, s.G, s.B, s.objectPresent, s.confident, &s.dXRaw, &s.relSum);
  return s;
}

void doCalibration(const String& which){
  String w = which; w.trim();
  w.toLowerCase();
  uint8_t requestedStep = calibrationWorkflowForTarget(w);
  if(requestedStep == CAL_FLOW_COMPLETE){
    logEvent("TCS3200", "ERROR=INVALID_CAL_TARGET");
    Serial1.println("HATA: cal r|k, cal y|s, cal b|m, cal x");
    return;
  }

  if(calibrationWorkflowStep == CAL_FLOW_COMPLETE){
    if(requestedStep == CAL_FLOW_EXPECT_X){
      resetCalibrationWorkflow(false);
    } else {
      logEvent("TCS3200", String("ERROR=CAL_SEQUENCE|EXPECTED=") + calibrationWorkflowExpectedLabel() + "|REQUESTED=" + w);
      Serial1.println("Kalibrasyon once cal x ile baslatilmali. Gerekirse 'cal reset' kullan.");
      return;
    }
  }

  if(requestedStep != calibrationWorkflowStep){
    logEvent("TCS3200", String("ERROR=CAL_SEQUENCE|EXPECTED=") + calibrationWorkflowExpectedLabel() + "|REQUESTED=" + w);
    Serial1.print("Beklenen sira: ");
    Serial1.println(calibrationWorkflowExpectedLabel());
    return;
  }

  int Rm,Gm,Bm;
  logEvent("TCS3200", "CAL=SAMPLING|COUNT=10|METHOD=MEDIAN");
  takeMedianRGB(Rm,Gm,Bm);

  String target = "HATA";

  if(w == "r" || w == "k"){ RR=Rm; RG=Gm; RB=Bm; hasR=true; target = "KIRMIZI"; }
  else if(w == "y" || w == "s"){ YR=Rm; YG=Gm; YB=Bm; hasY=true; target = "SARI"; }
  else if(w == "b" || w == "m"){ BRr=Rm; BGg=Gm; BBb=Bm; hasB=true; target = "MAVI"; }
  else if(w == "x"){ XR=Rm; XG=Gm; XB=Bm; hasX=true; target = "BOS"; }

  Serial1.print("MEGA|TCS3200|CAL_RESULT|TARGET=");
  Serial1.print(target);
  Serial1.print("|R=");
  Serial1.print(Rm);
  Serial1.print("|G=");
  Serial1.print(Gm);
  Serial1.print("|B=");
  Serial1.println(Bm);

  if(target == "HATA"){
    logEvent("TCS3200", "ERROR=INVALID_CAL_TARGET");
    Serial1.println("HATA: cal r|k, cal y|s, cal b|m, cal x");
    return;
  }

  // persist calibration
  saveCalibrationEEPROM();
  rebuildCalibrationModel();
  logEvent("TCS3200", String("CAL=SAVED|TARGET=") + target);
  if(requestedStep == CAL_FLOW_EXPECT_X) calibrationWorkflowStep = CAL_FLOW_EXPECT_R;
  else if(requestedStep == CAL_FLOW_EXPECT_R) calibrationWorkflowStep = CAL_FLOW_EXPECT_Y;
  else if(requestedStep == CAL_FLOW_EXPECT_Y) calibrationWorkflowStep = CAL_FLOW_EXPECT_B;
  else calibrationWorkflowStep = CAL_FLOW_COMPLETE;
  logEvent("TCS3200", String("CAL_FLOW=STEP_OK|DONE=") + target + "|NEXT=" + calibrationWorkflowNextLabel(calibrationWorkflowStep));
  printCalibrationStatus();
}

/* =========================
   (4) OTOMATIK DONGU (istenen akıs)
   - Konveyor surekli döner
   - Urun gorunce DUR -> okuma
   - Okumadan sonra tekrar calisir, TRAVEL_MS sonra DUR (robot alma noktası)
   - Robot pick&place bitince tekrar SEARCHING
   ========================= */

enum AutoState { SEARCHING, MEASURING, WAIT_ARM, STOPPED };
AutoState st = STOPPED;
bool autoMode = false;
bool stopRequested = false;

unsigned long lastSenseMs = 0;
const unsigned long sensePeriodMs = 120; // kutu merkeze daha yakin gelsin

String lastMeasured = "";
unsigned long lastTravelUpdateMs = 0;

const unsigned long SENSOR_LOG_PERIOD_MS = 2000;
unsigned long lastSensorLogMs = 0;
String lastSensorLogClass = "";

void logEvent(const char* module, const String& msg){
  Serial1.print("MEGA|");
  Serial1.print(module);
  Serial1.print("|");
  Serial1.print(msg);
  Serial1.print("|SRC_MS=");
  Serial1.println(millis());
}

void logAlarm(const char* code, const String& msg){
  Serial1.print("MEGA|ALARM|CODE=");
  Serial1.print(code);
  Serial1.print("|");
  Serial1.print(msg);
  Serial1.print("|SRC_MS=");
  Serial1.println(millis());
}

void logSensorReading(const SensorSample& s, const char* state, unsigned long now){
  bool changed = (s.cls != lastSensorLogClass);
  bool timed = (lastSensorLogMs == 0) || (now - lastSensorLogMs >= SENSOR_LOG_PERIOD_MS);

  if(changed || timed){
    Serial1.print("MEGA|TCS3200|STATE=");
    Serial1.print(state);
    Serial1.print("|CLASS=");
    Serial1.print(s.cls);
    Serial1.print("|R=");
    Serial1.print(s.R);
    Serial1.print("|G=");
    Serial1.print(s.G);
    Serial1.print("|B=");
    Serial1.print(s.B);
    Serial1.print("|OBJ=");
    Serial1.print(s.objectPresent ? 1 : 0);
    Serial1.print("|CONF=");
    Serial1.print(s.confident ? 1 : 0);
    Serial1.print("|DX=");
    Serial1.print(s.dXRaw);
    Serial1.print("|REL=");
    Serial1.println(s.relSum);

    lastSensorLogClass = s.cls;
    lastSensorLogMs = now;
  }
}



// BASELINE: 2026-03-16 itibariyla kararlı kabul edilen eski akış.
// Sonraki kapasite/tuning denemeleri bu noktadan dallanmalı.
// --- Ürün algılama / ölçüm için oy sayacı ---
uint8_t detectStreak = 0;                 // SEARCHING'de ardışık ürün görme sayacı
const uint8_t DETECT_STREAK_N = 3;        // false-positive azaltır (3 ardışık algı)

bool searchCenteringActive = false;
unsigned long searchCenteringStartedMs = 0;
unsigned long CENTER_MS = 100;

uint8_t measCount = 0;                    // 0..10
uint16_t voteBOS=0, voteR=0, voteY=0, voteB=0, voteCAL=0;
int measRs[N], measGs[N], measBs[N];
long measStrengths[N];
uint8_t measLabelCodes[N];
uint8_t detectLabelCodes[DETECT_STREAK_N];
uint8_t detectLabelCount = 0;
unsigned long lastMeasMs = 0;
unsigned long measSettleUntilMs = 0;
const unsigned long measPeriodMs = 120;   // motor durmuşken ölçüm periyodu (ms)
unsigned long MEAS_SETTLE_MS = 280;       // bant durduktan sonra olcum penceresini sabitle

bool sensorRearmRequired = false;
uint8_t sensorClearStreak = 0;
unsigned long sensorRearmRemainingMs = 0;
const uint8_t SENSOR_CLEAR_STREAK_N = 1;
const unsigned long SENSOR_REARM_MIN_RUN_MS = 900;
const long SENSOR_REARM_SAME_OBJECT_RAW_MAX = 120;
const long SENSOR_REARM_SAME_OBJECT_DX_DELTA_MAX = 90;

const uint8_t MAX_PENDING_ITEMS = 6;
PendingItem pendingItems[MAX_PENDING_ITEMS];
uint8_t pendingHead = 0;
uint8_t pendingCount = 0;
unsigned long nextMeasureId = 1;
unsigned long nextItemId = 1;
unsigned long activeMeasureId = 0;
bool pickStarted = false;
String activePickTriggerSource = "";
unsigned long activePickItemId = 0;
unsigned long activePickMeasureId = 0;
String activePickColor = "";
String activePickDecisionSource = "";
bool activePickReviewRequired = false;
bool activePickCompletedLogged = false;
int lastMeasuredR = 0;
int lastMeasuredG = 0;
int lastMeasuredB = 0;
long lastMeasuredDX = 0;
uint8_t lastMeasuredLabelCode = 0;
bool lastMeasuredSnapshotValid = false;

void logActivePickCompleted(const char* stateLabel){
  String trigger = activePickTriggerSource.length() > 0 ? activePickTriggerSource : "TIMER";
  uint8_t pendingAfterCompletion = pendingCount > 0 ? pendingCount - 1 : 0;
  logEvent(
    "AUTO",
    String("STATE=") + stateLabel
      + "|EVENT=PICKPLACE_DONE|ITEM_ID=" + activePickItemId
      + "|MEASURE_ID=" + activePickMeasureId
      + "|COLOR=" + activePickColor
      + "|DECISION_SOURCE=" + activePickDecisionSource
      + "|REVIEW=" + (activePickReviewRequired ? 1 : 0)
      + "|TRIGGER=" + trigger
      + "|PENDING=" + pendingAfterCompletion
  );
  activePickCompletedLogged = true;
}

void logActivePickReturnDone(const char* stateLabel, bool useQueueLabel, uint8_t queueDepth){
  String trigger = activePickTriggerSource.length() > 0 ? activePickTriggerSource : "TIMER";
  String msg = String("STATE=") + stateLabel
    + "|EVENT=PICKPLACE_RETURN_DONE|ITEM_ID=" + activePickItemId
    + "|MEASURE_ID=" + activePickMeasureId
    + "|COLOR=" + activePickColor
    + "|DECISION_SOURCE=" + activePickDecisionSource
    + "|REVIEW=" + (activePickReviewRequired ? 1 : 0)
    + "|TRIGGER=" + trigger;
  if(useQueueLabel) msg += "|QUEUE=" + queueDepth;
  else msg += "|PENDING=" + queueDepth;
  logEvent("AUTO", msg);
}

enum MeasLabelCode : uint8_t {
  MEAS_LABEL_BOS = 0,
  MEAS_LABEL_R = 1,
  MEAS_LABEL_Y = 2,
  MEAS_LABEL_B = 3,
  MEAS_LABEL_CAL = 4,
  MEAS_LABEL_OTHER = 5
};

uint8_t sampleLabelCode(const String& c){
  if(c == "BOS") return MEAS_LABEL_BOS;
  if(c == "KIRMIZI") return MEAS_LABEL_R;
  if(c == "SARI") return MEAS_LABEL_Y;
  if(c == "MAVI") return MEAS_LABEL_B;
  if(c == "CAL") return MEAS_LABEL_CAL;
  return MEAS_LABEL_OTHER;
}

void applyVoteForCode(uint8_t code, uint16_t &bos, uint16_t &r, uint16_t &y, uint16_t &b, uint16_t &cal){
  if(code == MEAS_LABEL_BOS) bos++;
  else if(code == MEAS_LABEL_R) r++;
  else if(code == MEAS_LABEL_Y) y++;
  else if(code == MEAS_LABEL_B) b++;
  else if(code == MEAS_LABEL_CAL) cal++;
}

String majorityLabelOf(uint16_t bos, uint16_t r, uint16_t y, uint16_t b, uint16_t cal){
  uint16_t best = bos;
  String lab = "BOS";
  if(r > best){ best = r; lab = "KIRMIZI"; }
  if(y > best){ best = y; lab = "SARI"; }
  if(b > best){ best = b; lab = "MAVI"; }
  if(cal > best){ best = cal; lab = "CAL"; }
  return lab;
}

uint16_t topVoteCountOf(uint16_t bos, uint16_t r, uint16_t y, uint16_t b, uint16_t cal){
  uint16_t best = bos;
  if(r > best) best = r;
  if(y > best) best = y;
  if(b > best) best = b;
  if(cal > best) best = cal;
  return best;
}

uint16_t secondVoteCountOf(uint16_t bos, uint16_t r, uint16_t y, uint16_t b, uint16_t cal){
  uint16_t scores[5] = { bos, r, y, b, cal };
  uint16_t best = 0;
  uint16_t second = 0;

  for(uint8_t i = 0; i < 5; i++){
    uint16_t v = scores[i];
    if(v >= best){
      second = best;
      best = v;
    } else if(v > second){
      second = v;
    }
  }

  return second;
}

String majorityLabel(){
  // en çok oyu alanı döndür
  uint16_t best = voteBOS; String lab="BOS";
  if(voteR > best){ best=voteR; lab="KIRMIZI"; }
  if(voteY > best){ best=voteY; lab="SARI"; }
  if(voteB > best){ best=voteB; lab="MAVI"; }
  if(voteCAL > best){ best=voteCAL; lab="CAL"; }
  return lab;
}

void resetVotes(){
  measCount=0;
  voteBOS=voteR=voteY=voteB=voteCAL=0;
  lastMeasMs = 0;
  measSettleUntilMs = 0;
}

void resetSearchCentering(){
  searchCenteringActive = false;
  searchCenteringStartedMs = 0;
}

void resetDetectLabels(){
  detectLabelCount = 0;
  for(uint8_t i = 0; i < DETECT_STREAK_N; i++) detectLabelCodes[i] = MEAS_LABEL_OTHER;
}

void noteDetectLabel(const String& cls){
  uint8_t code = sampleLabelCode(cls);
  if(code == MEAS_LABEL_BOS || code == MEAS_LABEL_CAL || code == MEAS_LABEL_OTHER) return;

  if(detectLabelCount < DETECT_STREAK_N){
    detectLabelCodes[detectLabelCount++] = code;
    return;
  }

  for(uint8_t i = 1; i < DETECT_STREAK_N; i++) detectLabelCodes[i - 1] = detectLabelCodes[i];
  detectLabelCodes[DETECT_STREAK_N - 1] = code;
}

String detectHintLabel(uint8_t *bestCountOut = nullptr, uint8_t *secondCountOut = nullptr){
  uint8_t voteHintR = 0;
  uint8_t voteHintY = 0;
  uint8_t voteHintB = 0;

  for(uint8_t i = 0; i < detectLabelCount; i++){
    if(detectLabelCodes[i] == MEAS_LABEL_R) voteHintR++;
    else if(detectLabelCodes[i] == MEAS_LABEL_Y) voteHintY++;
    else if(detectLabelCodes[i] == MEAS_LABEL_B) voteHintB++;
  }

  uint8_t best = voteHintR;
  String label = "KIRMIZI";
  if(voteHintY > best){ best = voteHintY; label = "SARI"; }
  if(voteHintB > best){ best = voteHintB; label = "MAVI"; }
  if(best == 0){
    if(bestCountOut) *bestCountOut = 0;
    if(secondCountOut) *secondCountOut = 0;
    return "BELIRSIZ";
  }

  uint8_t bestMatches = 0;
  uint8_t second = 0;
  uint8_t counts[3] = { voteHintR, voteHintY, voteHintB };
  for(uint8_t i = 0; i < 3; i++){
    uint8_t v = counts[i];
    if(v == best) bestMatches++;
    else if(v > second) second = v;
  }

  if(bestCountOut) *bestCountOut = best;
  if(secondCountOut) *secondCountOut = second;
  if(bestMatches > 1) return "BELIRSIZ";
  return label;
}

bool isColorDetectCode(uint8_t code){
  return code == MEAS_LABEL_R || code == MEAS_LABEL_Y || code == MEAS_LABEL_B;
}

bool isSearchDetectCandidate(const SensorSample& s){
  uint8_t code = sampleLabelCode(s.cls);
  if(!s.objectPresent || !s.confident || !isColorDetectCode(code)) return false;
  if(s.relSum >= objectContrastThreshold) return true;
  return s.dXRaw >= (emptyDistanceThresholdRaw + 80L);
}

bool shouldReleaseRearmForSample(const SensorSample& s){
  if(!isSearchDetectCandidate(s)) return false;
  if(!lastMeasuredSnapshotValid) return true;

  uint8_t code = sampleLabelCode(s.cls);
  long rawDelta = dist3(s.R, s.G, s.B, lastMeasuredR, lastMeasuredG, lastMeasuredB);
  long dxDelta = s.dXRaw - lastMeasuredDX;
  if(dxDelta < 0) dxDelta = -dxDelta;

  if(code == lastMeasuredLabelCode &&
     rawDelta < SENSOR_REARM_SAME_OBJECT_RAW_MAX &&
     dxDelta < SENSOR_REARM_SAME_OBJECT_DX_DELTA_MAX){
    return false;
  }

  return true;
}

void startMeasuring(unsigned long now){
  motorStop();
  pausePendingTravelTimer();
  activeMeasureId = nextMeasureId++;
  logEvent("AUTO", String("STATE=MEASURING|REASON=OBJECT_DETECTED|MEASURE_ID=") + activeMeasureId
    + "|SEARCH_HINT=" + detectHintLabel()
    + "|CENTER_MS=" + CENTER_MS);
  st = MEASURING;
  resetVotes();
  measSettleUntilMs = now + MEAS_SETTLE_MS;
  resetSearchCentering();
  publishStatusNow();
}

int medianFromBuffer(const int *src, int n){
  int tmp[N];
  for(int i = 0; i < n; i++) tmp[i] = src[i];
  return medianInt(tmp, n);
}

int medianFromIndexedBuffer(const int *src, const uint8_t *idxs, int n){
  int tmp[N];
  for(int i = 0; i < n; i++) tmp[i] = src[idxs[i]];
  return medianInt(tmp, n);
}

void sortIndicesByStrengthDesc(uint8_t *idxs, int n, const long *strengths){
  for(int i = 0; i < n - 1; i++){
    for(int j = i + 1; j < n; j++){
      if(strengths[idxs[j]] > strengths[idxs[i]]){
        uint8_t t = idxs[i];
        idxs[i] = idxs[j];
        idxs[j] = t;
      }
    }
  }
}

uint16_t topVoteCount(){
  uint16_t best = voteBOS;
  if(voteR > best) best = voteR;
  if(voteY > best) best = voteY;
  if(voteB > best) best = voteB;
  if(voteCAL > best) best = voteCAL;
  return best;
}

uint16_t secondVoteCount(){
  uint16_t scores[5] = { voteBOS, voteR, voteY, voteB, voteCAL };
  uint16_t best = 0;
  uint16_t second = 0;

  for(uint8_t i = 0; i < 5; i++){
    uint16_t v = scores[i];
    if(v >= best){
      second = best;
      best = v;
    } else if(v > second){
      second = v;
    }
  }

  return second;
}

bool hasPendingItems(){
  return pendingCount > 0;
}

uint8_t pendingTailIndex(){
  return (pendingHead + pendingCount) % MAX_PENDING_ITEMS;
}

String headPendingColor(){
  if(!hasPendingItems()) return "";
  return pendingItems[pendingHead].color;
}

unsigned long headPendingItemId(){
  if(!hasPendingItems()) return 0;
  return pendingItems[pendingHead].itemId;
}

unsigned long headPendingMeasureId(){
  if(!hasPendingItems()) return 0;
  return pendingItems[pendingHead].measureId;
}

String headPendingDecisionSource(){
  if(!hasPendingItems()) return "";
  return pendingItems[pendingHead].decisionSource;
}

bool headPendingReviewRequired(){
  if(!hasPendingItems()) return false;
  return pendingItems[pendingHead].reviewRequired;
}

unsigned long headPendingRemainingMs(){
  if(!hasPendingItems()) return 0;
  return pendingItems[pendingHead].travelMs;
}

bool enqueuePendingItem(const String& color, unsigned long travelMs, unsigned long itemId, unsigned long measureId,
                       const String& decisionSource, bool reviewRequired){
  if(pendingCount >= MAX_PENDING_ITEMS) return false;

  uint8_t idx = pendingTailIndex();
  pendingItems[idx].color = color;
  pendingItems[idx].decisionSource = decisionSource;
  pendingItems[idx].itemId = itemId;
  pendingItems[idx].measureId = measureId;
  pendingItems[idx].travelMs = travelMs;
  pendingItems[idx].reviewRequired = reviewRequired;
  pendingCount++;
  return true;
}

void dequeuePendingItem(){
  if(!hasPendingItems()) return;

  pendingItems[pendingHead].color = "";
  pendingItems[pendingHead].decisionSource = "";
  pendingItems[pendingHead].itemId = 0;
  pendingItems[pendingHead].measureId = 0;
  pendingItems[pendingHead].travelMs = 0;
  pendingItems[pendingHead].reviewRequired = false;
  pendingHead = (pendingHead + 1) % MAX_PENDING_ITEMS;
  pendingCount--;
}

void clearPickRuntime(){
  pickStarted = false;
  activePickTriggerSource = "";
  activePickItemId = 0;
  activePickMeasureId = 0;
  activePickColor = "";
  activePickDecisionSource = "";
  activePickReviewRequired = false;
  activePickCompletedLogged = false;
}

bool startQueuedPick(const String& triggerSource, unsigned long requestedItemId, bool logReject){
  String normalizedTrigger = triggerSource;
  normalizedTrigger.trim();
  normalizedTrigger.toUpperCase();
  if(normalizedTrigger.length() == 0) normalizedTrigger = "TIMER";

  String rejectReason = "";
  unsigned long headItemId = headPendingItemId();
  unsigned long headMeasureId = headPendingMeasureId();

  if(!hasPendingItems()){
    rejectReason = "QUEUE_EMPTY";
  } else if(!autoMode || stopRequested){
    rejectReason = "MODE_NOT_ALLOWED";
  } else if(normalizedTrigger == "EARLY" && requestedItemId == 0){
    rejectReason = "LATE_DECISION";
  } else if(normalizedTrigger == "EARLY" && headPendingRemainingMs() == 0){
    rejectReason = "LATE_DECISION";
  } else if(normalizedTrigger == "EARLY" && requestedItemId != 0 && requestedItemId != headItemId){
    rejectReason = "HEAD_CHANGED";
  } else if(stepRunning){
    rejectReason = "SAFETY_BLOCK";
  } else if(pickStarted || pickPlaceBusy() || st == WAIT_ARM){
    if(normalizedTrigger == "EARLY" && requestedItemId != 0 && requestedItemId == activePickItemId){
      rejectReason = "DUPLICATE_COMMAND";
    } else {
      rejectReason = "PICK_ALREADY_STARTED";
    }
  } else if(st != SEARCHING){
    rejectReason = "SAFETY_BLOCK";
  }

  if(rejectReason.length() > 0){
    if(logReject){
      unsigned long loggedItemId = requestedItemId != 0 ? requestedItemId : headItemId;
      logEvent(
        "AUTO",
        String("STATE=") + autoStateStr()
          + "|EVENT=PICK_EARLY_REJECT|ITEM_ID=" + loggedItemId
          + "|MEASURE_ID=" + headMeasureId
          + "|HEAD_ITEM_ID=" + headItemId
          + "|HEAD_MEASURE_ID=" + headMeasureId
          + "|TRIGGER=" + normalizedTrigger
          + "|REASON=" + rejectReason
      );
      publishStatusNow();
    }
    return false;
  }

  motorStop();
  pausePendingTravelTimer();
  pickStarted = true;
  activePickColor = headPendingColor();
  activePickDecisionSource = headPendingDecisionSource();
  activePickReviewRequired = headPendingReviewRequired();
  activePickCompletedLogged = false;
  activePickTriggerSource = normalizedTrigger;
  activePickItemId = headItemId;
  activePickMeasureId = headMeasureId;
  lastMeasured = activePickColor;
  pickPlaceResetDone();
  logEvent(
    "AUTO",
    String("STATE=WAIT_ARM|EVENT=ARM_POSITION_REACHED|ITEM_ID=") + activePickItemId
      + "|MEASURE_ID=" + activePickMeasureId
      + "|COLOR=" + activePickColor
      + "|DECISION_SOURCE=" + activePickDecisionSource
      + "|REVIEW=" + (activePickReviewRequired ? 1 : 0)
      + "|TRIGGER=" + activePickTriggerSource
  );
  pickPlaceStart();
  st = WAIT_ARM;
  publishStatusNow();
  return true;
}

void pausePendingTravelTimer(){
  lastTravelUpdateMs = 0;
}

void updatePendingTravel(unsigned long now){
  if(lastTravelUpdateMs == 0){
    lastTravelUpdateMs = now;
    return;
  }

  unsigned long delta = now - lastTravelUpdateMs;
  lastTravelUpdateMs = now;
  if(delta == 0) return;

  if(sensorRearmRemainingMs > 0){
    if(sensorRearmRemainingMs > delta) sensorRearmRemainingMs -= delta;
    else sensorRearmRemainingMs = 0;
  }

  if(!hasPendingItems()){
    return;
  }

  for(uint8_t i = 0; i < pendingCount; i++){
    uint8_t idx = (pendingHead + i) % MAX_PENDING_ITEMS;
    if(pendingItems[idx].travelMs > delta) pendingItems[idx].travelMs -= delta;
    else pendingItems[idx].travelMs = 0;
  }
}

void runConveyorAndTrack(unsigned long now){
  st = SEARCHING;
  updatePendingTravel(now);
  motorRun();
}

// Urunu sensörden kola tasima suresi (ms) - runtime ayarlanir:  t 4500
unsigned long TRAVEL_MS = 4500;
unsigned long lastStatusMs = 0;
const unsigned long statusPeriodMs = 1000;

const char* autoStateStr(){
  if(stopRequested){
    if(st == STOPPED) return "STOPPED";
    if(st == WAIT_ARM && pickPlaceBusy()) return "WAIT_ARM";
    return "PAUSED";
  }

  switch(st){
    case SEARCHING:   return "SEARCHING";
    case MEASURING:   return "MEASURING";
    case WAIT_ARM:    return "WAIT_ARM";
    case STOPPED:     return "STOPPED";
    default:          return "UNKNOWN";
  }
}

const char* conveyorStateStr(){
  if(stopRequested || !autoMode) return "STOP";
  if(st == STOPPED || st == MEASURING || st == WAIT_ARM) return "STOP";
  if(st == SEARCHING) return "RUN";
  return "STOP";
}

bool shouldPublishPeriodicStatus(){
  if(stepRunning || pickPlaceBusy()) return false;
  return autoMode || stopRequested || hasPendingItems() || st == MEASURING || st == WAIT_ARM;
}

const char* robotStateStr(){
  if(pickPlaceBusy()) return "BUSY";
  if(pickPlaceDone()) return "DONE";
  return "IDLE";
}

/* =========================
   SERİ KOMUT OKUMA
   ========================= */
String readCmd(){
  if(!Serial1.available()) return "";
  String cmd = Serial1.readStringUntil('\n');
  cmd.replace("\r",""); //CR temizleme
  cmd.trim();
  cmd.toLowerCase();
  return cmd;
}

bool parse4Ints(const String& s, int &a, int &b, int &c, int &d){
  String t = s;
  t.replace(',', ' ');
  int firstSpace = t.indexOf(' ');
  if(firstSpace < 0) return false;
  t = t.substring(firstSpace + 1);
  t.trim();
  int vals[4] = {0,0,0,0};
  int found = 0;
  int i = 0;
  while(found < 4 && i < (int)t.length()){
    while(i < (int)t.length() && t.charAt(i) == ' ') i++;
    if(i >= (int)t.length()) break;
    int j = i;
    while(j < (int)t.length() && t.charAt(j) != ' ') j++;
    String token = t.substring(i, j);
    vals[found++] = token.toInt();
    i = j;
  }
  if(found < 4) return false;
  a = vals[0]; b = vals[1]; c = vals[2]; d = vals[3];
  return true;
}

void printStatus(){
  Serial1.print("MEGA|STATUS|AUTO=");
  Serial1.print(autoMode ? 1 : 0);

  Serial1.print("|STATE=");
  Serial1.print(autoStateStr());

  Serial1.print("|CONVEYOR=");
  Serial1.print(conveyorStateStr());

  Serial1.print("|ROBOT=");
  Serial1.print(robotStateStr());

  Serial1.print("|DIR=");
  Serial1.print(dirForward ? "A" : "B");

  Serial1.print("|PWM=");
  Serial1.print(motorSpeed);

  Serial1.print("|TRAVEL_MS=");
  Serial1.print(TRAVEL_MS);

  Serial1.print("|CENTER_MS=");
  Serial1.print(CENTER_MS);

  Serial1.print("|SETTLE_MS=");
  Serial1.print(MEAS_SETTLE_MS);

  Serial1.print("|LAST=");
  Serial1.print(lastMeasured);

  Serial1.print("|LIM22=");
  Serial1.print(isSwitchPressed(LIM_PICK_PIN) ? 1 : 0);

  Serial1.print("|LIM23=");
  Serial1.print(isSwitchPressed(LIM_DROP_PIN) ? 1 : 0);

  Serial1.print("|STEP=");
  Serial1.print(stepRunning ? 1 : 0);

  Serial1.print("|STEP_HOLD=");
  Serial1.print(stepHold ? 1 : 0);

  Serial1.print("|STEP_US=");
  Serial1.print(stepDelayUs);

  Serial1.print("|QUEUE=");
  Serial1.print(pendingCount);

  Serial1.print("|STOP_REQ=");
  Serial1.print(stopRequested ? 1 : 0);

  Serial1.print("|SRC_MS=");
  Serial1.println(millis());
}

void publishStatusNow(){
  lastStatusMs = millis();
  printStatus();
}


void printHelp(){
  Serial1.println("----------------MEGA KONVEYOR KONTROL TERMINALI------------");

  Serial1.println("SISTEM:");
  Serial1.println("  help          (komut listesini goster)");
  Serial1.println("  status        (sistem durum paketi)");
  Serial1.println("  q             (tek seferlik renk testi)");

  Serial1.println("\nKONVEYOR:");
  Serial1.println("  start         (otomatik modu baslat)");
  Serial1.println("  stop          (otomatik modu durdur)");
  Serial1.println("  rev           (konveyor yonunu degistir)");
  Serial1.println("  speed X       (PWM hiz 0-255)");
  Serial1.println("  t MS          (urun seyahat suresi ms)");
  Serial1.println("  center MS     (algiladiktan sonra stop oncesi ek akis)");
  Serial1.println("  settle MS     (stop sonrasi olcum oncesi bekleme)");

  Serial1.println("\nROBOT KOL:");
  Serial1.println("  pickplace     (robot alma-birakma test)");
  Serial1.println("  epick ID      (head item icin kontrollu erken pick)");
  Serial1.println("  servo a b c d (4 servo acisi 0-180)");
  Serial1.println("  s1 A          (servo1 aci)");
  Serial1.println("  s2 A          (servo2 aci)");
  Serial1.println("  s3 A          (servo3 aci)");
  Serial1.println("  s4 A          (servo4 aci)");

  Serial1.println("\nSTEP MOTOR:");
  Serial1.println("  smove N       (N:+ ileri, N:- geri)");
  Serial1.println("  sspeed US     (adim gecikmesi mikro saniye)");
  Serial1.println("  shold 0/1     (bobinleri serbest birak / tut)");
  Serial1.println("  sstop         (step motoru durdur)");

  Serial1.println("\nKALIBRASYON:");
  Serial1.println("  cal reset     (sirali kalibrasyonu sifirdan baslat)");
  Serial1.println("  cal r / cal k (kirmizi kalibrasyonu)");
  Serial1.println("  cal y / cal s (sari kalibrasyonu)");
  Serial1.println("  cal b / cal m (mavi kalibrasyonu)");
  Serial1.println("  cal x         (bos zemin kalibrasyonu)");
  Serial1.println("  cal show      (yuklu/runtime kalibrasyonu yazdir)");
  Serial1.println("  sira          cal x -> cal r -> cal y -> cal b");

  Serial1.println("----------------------------------------------------------------\n");
}

void setup() {
  Serial1.begin(57600);
  
  // Load calibration from EEPROM; if not found use embedded defaults
  if(!loadCalibrationEEPROM()){
    setDefaultCalib();
    rebuildCalibrationModel();
    saveCalibrationEEPROM();
    logEvent("TCS3200", "CAL=DEFAULT_LOADED|SOURCE=EEPROM_EMPTY");
  } else {
    rebuildCalibrationModel();
    logEvent("TCS3200", "CAL=LOADED|SOURCE=EEPROM");
  }
  calibrationWorkflowStep = CAL_FLOW_COMPLETE;
  printCalibrationStatus();
  Serial1.setTimeout(50);

  pinMode(ENB, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  motorStop();


  pinMode(LIM_PICK_PIN, INPUT_PULLUP);
  pinMode(LIM_DROP_PIN, INPUT_PULLUP);

  sv1.attach(SV1_PIN);
  sv2.attach(SV2_PIN);
  sv3.attach(SV3_PIN);
  sv4.attach(SV4_PIN);

  pinMode(S0, OUTPUT); pinMode(S1, OUTPUT);
  pinMode(S2, OUTPUT); pinMode(S3, OUTPUT);
  pinMode(OUT_PIN, INPUT);
  digitalWrite(S0, HIGH);
  digitalWrite(S1, LOW);

  pinMode(ST_ENA, OUTPUT); pinMode(ST_ENB, OUTPUT);
  pinMode(ST_IN1, OUTPUT); pinMode(ST_IN2, OUTPUT);
  pinMode(ST_IN3, OUTPUT); pinMode(ST_IN4, OUTPUT);
  stepRelease();

  // STARTUP: HOME @ LIM22 ve kollar aşağıda
  setServosImmediate(160, 150, 40, 170);
  homeToPickLimit22();
  goPickPose();

  logEvent("SYSTEM", "STATUS=READY");
  Serial1.println("Kalibrasyon sirasi: cal reset -> cal x -> cal r -> cal y -> cal b");
  printHelp();
}


void loop() {
  // non-blocking robot pick&place
  pickPlaceTick();

  // ---- Komutlar ----
  String cmd = readCmd();
  if(cmd.length()){
    if(cmd == "help"){ printHelp(); }

    else if(cmd == "status"){ printStatus(); }

    else if(cmd == "q"){
      if(autoMode){
        logEvent("TCS3200", "ERROR=Q_BLOCKED|REASON=AUTO_MODE");
      } else {
        SensorSample s = quickClassifyOnce();

        Serial1.print("MEGA|TCS3200|TEST|CLASS=");
        Serial1.print(s.cls);
        Serial1.print("|R=");
        Serial1.print(s.R);
        Serial1.print("|G=");
        Serial1.print(s.G);
        Serial1.print("|B=");
        Serial1.print(s.B);
        Serial1.print("|OBJ=");
        Serial1.print(s.objectPresent ? 1 : 0);
        Serial1.print("|CONF=");
        Serial1.println(s.confident ? 1 : 0);
      }
    }

    else if(cmd == "start"){
      autoMode = true;
      stopRequested = false;
      if(st == STOPPED){
        detectStreak = 0;
        resetDetectLabels();
        resetSearchCentering();
        sensorRearmRequired = false;
        sensorClearStreak = 0;
        sensorRearmRemainingMs = 0;
        resetVotes();
        lastSenseMs = 0;
        runConveyorAndTrack(millis());
        logEvent("AUTO", "CMD=START|STATE=SEARCHING");
      } else {
        logEvent("AUTO", String("CMD=START|STATE=RESUME|QUEUE=") + pendingCount);
      }
      publishStatusNow();
    }
    else if(cmd == "stop"){
      autoMode = false;
      detectStreak = 0;
      resetDetectLabels();
      resetSearchCentering();
      motorStop();
      pausePendingTravelTimer();

      bool canFullyStop = (st == STOPPED) || (st == SEARCHING && !hasPendingItems() && !pickPlaceBusy());
      if(canFullyStop){
        stopRequested = false;
        st = STOPPED;
        logEvent("AUTO", "CMD=STOP|STATE=STOPPED");
      } else {
        stopRequested = true;
        String stopState = (st == WAIT_ARM && pickPlaceBusy()) ? "WAIT_ARM" : "PAUSED";
        logEvent("AUTO", String("CMD=STOP|STATE=") + stopState + "|QUEUE=" + pendingCount);
      }
      publishStatusNow();
    }
    else if(cmd == "rev"){
      dirForward = !dirForward;
      logEvent("CONVEYOR", String("DIR=") + (dirForward ? "A" : "B"));
      if(st == SEARCHING && autoMode) motorRun();
      publishStatusNow();
    
    }
    else if(cmd.startsWith("speed")){
      int sp = cmd.substring(5).toInt();
      sp = constrain(sp, 0, 255);
      motorSpeed = sp;
      logEvent("CONVEYOR", String("PWM=") + motorSpeed);
      if(st == SEARCHING && autoMode) motorRun();
      publishStatusNow();
    }
    else if(cmd.startsWith("t ")){
      long v = cmd.substring(2).toInt();
      if(v >= 500 && v <= 20000){
        TRAVEL_MS = (unsigned long)v;
        logEvent("AUTO", String("TRAVEL_MS=") + TRAVEL_MS);
        publishStatusNow();
      } else {
        logEvent("AUTO", "ERROR=INVALID_TRAVEL_MS");
        Serial1.println("HATA: t 500..20000 (ms)");
      }
    }
    else if(cmd.startsWith("center ")){
      long v = cmd.substring(7).toInt();
      if(v >= 0 && v <= 1500){
        CENTER_MS = (unsigned long)v;
        logEvent("AUTO", String("CENTER_MS=") + CENTER_MS);
        publishStatusNow();
      } else {
        logEvent("AUTO", "ERROR=INVALID_CENTER_MS");
        Serial1.println("HATA: center 0..1500 (ms)");
      }
    }
    else if(cmd.startsWith("settle ")){
      long v = cmd.substring(7).toInt();
      if(v >= 0 && v <= 2000){
        MEAS_SETTLE_MS = (unsigned long)v;
        logEvent("AUTO", String("SETTLE_MS=") + MEAS_SETTLE_MS);
        publishStatusNow();
      } else {
        logEvent("AUTO", "ERROR=INVALID_SETTLE_MS");
        Serial1.println("HATA: settle 0..2000 (ms)");
      }
    }

    else if(cmd.startsWith("smove")){
      if(autoMode){
        logEvent("STEP", "ERROR=MANUAL_BLOCKED|REASON=AUTO_MODE");
      }
      else if(pickPlaceBusy()){
        logEvent("STEP", "ERROR=MANUAL_BLOCKED|REASON=ROBOT_BUSY");
      }
      else if(stepRunning){
        logEvent("STEP", "ERROR=MANUAL_BLOCKED|REASON=STEP_RUNNING");
      }
      else {
        long steps = cmd.substring(5).toInt();
        if(steps == 0){
          logEvent("STEP", "ERROR=INVALID_STEPS");
        } else {
          stepStartMove(steps);
          logEvent("STEP", String("CMD=SMOVE|STEPS=") + steps);
          publishStatusNow();
        }
      }
    }

    else if(cmd.startsWith("sspeed")){
      long us = cmd.substring(6).toInt();
      if(us < 300 || us > 10000){
        logEvent("STEP", "ERROR=INVALID_STEP_US");
        Serial1.println("HATA: sspeed 300..10000");
      } else {
        stepDelayUs = (unsigned long)us;
        logEvent("STEP", String("STEP_US=") + stepDelayUs);
        publishStatusNow();
      }
    }

    else if(cmd.startsWith("shold")){
      int v = cmd.substring(5).toInt();
      if(v != 0 && v != 1){
        logEvent("STEP", "ERROR=INVALID_HOLD");
        Serial1.println("HATA: shold 0 veya shold 1");
      } else {
        stepHold = (v == 1);

        if(!stepRunning){
          if(stepHold){
            stepEnable(true);
            stepApplyIndex(stepIndex);
          } else {
            stepRelease();
          }
        }

        logEvent("STEP", String("HOLD=") + (stepHold ? 1 : 0));
        publishStatusNow();
      }
    }

    else if(cmd == "sstop"){
      stepStop();
      logEvent("STEP", "CMD=SSTOP|ACTION=STOP");
      publishStatusNow();
    }

    else if(cmd == "pickplace"){
      // manuel test: non-blocking başlat
      pickPlaceResetDone();
      pickPlaceStart();
      logEvent("ROBOT", "CMD=PICKPLACE_START");
    }
    else if(cmd.startsWith("epick")){
      String arg = cmd.substring(5);
      arg.trim();
      unsigned long requestedItemId = arg.toInt();
      startQueuedPick("EARLY", requestedItemId, true);
    }
    else if(cmd.startsWith("servo")){
      int a1,a2,a3,a4;
      if(parse4Ints(cmd, a1,a2,a3,a4)){
        a1 = clampAngle(a1); a2 = clampAngle(a2); a3 = clampAngle(a3); a4 = clampAngle(a4);
        setServos(a1,a2,a3,a4);

        Serial1.print("MEGA|ROBOT|SERVO|S1=");
        Serial1.print(a1);
        Serial1.print("|S2=");
        Serial1.print(a2);
        Serial1.print("|S3=");
        Serial1.print(a3);
        Serial1.print("|S4=");
        Serial1.println(a4);
      }
      else Serial1.println("SERVO komutu: servo a b c d (0-180)");
    }
    else if(cmd.startsWith("s1")){
      int a = cmd.substring(2).toInt();
      a = clampAngle(a);
      servoSetTarget(SERVO_S1, a);
      logEvent("ROBOT", String("S1=") + a);
    }
    else if(cmd.startsWith("s2")){
      int a = cmd.substring(2).toInt();
      a = clampAngle(a);
      servoSetTarget(SERVO_S2, a);
      logEvent("ROBOT", String("S2=") + a);
    }
    else if(cmd.startsWith("s3")){
      int a = cmd.substring(2).toInt();
      a = clampAngle(a);
      servoSetTarget(SERVO_S3, a);
      logEvent("ROBOT", String("S3=") + a);
    }
    else if(cmd.startsWith("s4")){
      int a = cmd.substring(2).toInt();
      a = clampAngle(a);
      servoSetTarget(SERVO_S4, a);
      logEvent("ROBOT", String("S4=") + a);
    }
    else if(cmd.startsWith("cal")){
      String calArg = cmd.substring(3);
      calArg.trim();
      if(calArg == "reset"){
        resetCalibrationWorkflow(true);
      } else if(calArg == "show"){
        logEvent("TCS3200", "CMD=CAL|TARGET=SHOW");
        printCalibrationStatus();
      } else {
        logEvent("TCS3200", String("CMD=CAL|TARGET=") + calArg);
        doCalibration(calArg);
      }
    }
    
    else {
      Serial1.print("Bilinmeyen komut: "); Serial1.println(cmd);
      Serial1.println("help yaz -> komut listesi");
    }
  }
  unsigned long nowStatus = millis();
  if(shouldPublishPeriodicStatus() && (nowStatus - lastStatusMs >= statusPeriodMs)){
    lastStatusMs = nowStatus;
    printStatus();
  }

  unsigned long now = millis();

  if(st == STOPPED){
    motorStop();
    pausePendingTravelTimer();
    return;
  }

  // 1) SEARCHING: bant döner, sıradaki küpler yaklaşır, uygunsa yeni küp ölçülür
  if(st == SEARCHING){
    if(!autoMode){
      motorStop();
      pausePendingTravelTimer();
      return;
    }

    runConveyorAndTrack(now);

    if(hasPendingItems() && headPendingRemainingMs() == 0){
      startQueuedPick("TIMER", headPendingItemId(), false);
      return;
    }

    if(searchCenteringActive && (now - searchCenteringStartedMs) >= CENTER_MS){
      startMeasuring(now);
      return;
    }

    if(now - lastSenseMs < sensePeriodMs){
      return;
    }
    lastSenseMs = now;

    SensorSample s = quickClassifyOnce();
    logSensorReading(s, "SEARCH", now);

    if(s.confident && (!s.objectPresent || s.cls == "BOS")){
      updateRuntimeEmpty(s.R, s.G, s.B);
    }

    if(sensorRearmRequired){
      if(!s.objectPresent || s.cls == "BOS"){
        sensorClearStreak++;
        if(sensorClearStreak >= SENSOR_CLEAR_STREAK_N){
          sensorRearmRequired = false;
          sensorClearStreak = 0;
          sensorRearmRemainingMs = 0;
          detectStreak = 0;
          resetDetectLabels();
          resetSearchCentering();
        }
      } else {
        sensorClearStreak = 0;
      }

      if(sensorRearmRequired && sensorRearmRemainingMs == 0 && shouldReleaseRearmForSample(s)){
        sensorRearmRequired = false;
        sensorClearStreak = 0;
        detectStreak = 0;
        resetDetectLabels();
        resetSearchCentering();
        logEvent("AUTO", String("STATE=SEARCHING|EVENT=REARM_TIMEOUT|ACTION=ALLOW_OBJECT|SEARCH_HINT=") + s.cls);
      }

      if(sensorRearmRequired){
        resetSearchCentering();
        return;
      }
    }

    if(s.cls == "CAL"){
      detectStreak = 0;
      resetDetectLabels();
      resetSearchCentering();
      return;
    }

    if(!s.objectPresent){
      detectStreak = 0;
      resetDetectLabels();
      resetSearchCentering();
      return; // ürün yok -> bant dönmeye devam
    }

    if(!isSearchDetectCandidate(s)){
      resetSearchCentering();
      return;
    }

    noteDetectLabel(s.cls);
    detectStreak++;
    if(detectStreak < DETECT_STREAK_N){
      return;
    }

    if(!searchCenteringActive){
      searchCenteringActive = true;
      searchCenteringStartedMs = now;
      logEvent("AUTO", String("STATE=SEARCHING|EVENT=OBJECT_LOCKED|SEARCH_HINT=") + detectHintLabel()
        + "|CENTER_MS=" + CENTER_MS);
      if(CENTER_MS > 0){
        return;
      }
    }

    startMeasuring(now);
    return;
  }

  // 2) MEASURING: motor durdu; küp okunur ve kuyruğa eklenir
  if(st == MEASURING){
    motorStop();
    pausePendingTravelTimer();

    if(!autoMode){
      return;
    }

    if(measSettleUntilMs != 0 && now < measSettleUntilMs){
      return;
    }

    if(lastMeasMs != 0 && (now - lastMeasMs) < measPeriodMs){
      return;
    }
    lastMeasMs = now;

    SensorSample s = quickClassifyOnce();
    String c = s.cls;
    int sampleEmptyR, sampleEmptyG, sampleEmptyB;
    effectiveEmpty(sampleEmptyR, sampleEmptyG, sampleEmptyB);
    measRs[measCount] = s.R;
    measGs[measCount] = s.G;
    measBs[measCount] = s.B;
    measStrengths[measCount] = s.objectPresent ? dist3(s.R, s.G, s.B, sampleEmptyR, sampleEmptyG, sampleEmptyB) : 0;
    measLabelCodes[measCount] = sampleLabelCode(c);

    if(c == "CAL") voteCAL++;
    else if(c == "BOS") voteBOS++;
    else if(c == "KIRMIZI") voteR++;
    else if(c == "SARI") voteY++;
    else if(c == "MAVI") voteB++;

    measCount++;
    if(measCount < 10){
      return;
    }

    uint8_t objectIdx[N];
    uint8_t objectCount = 0;
    for(uint8_t i = 0; i < N; i++){
      uint8_t code = measLabelCodes[i];
      if(measStrengths[i] > 0 && code != MEAS_LABEL_BOS && code != MEAS_LABEL_CAL){
        objectIdx[objectCount++] = i;
      }
    }
    if(objectCount > 1){
      sortIndicesByStrengthDesc(objectIdx, objectCount, measStrengths);
    }

    uint8_t selectedIdx[N];
    uint8_t selectedCount = 0;
    bool usedCoreWindow = (objectCount >= 3);
    if(usedCoreWindow){
      selectedCount = (objectCount > 6) ? 6 : objectCount;
      for(uint8_t i = 0; i < selectedCount; i++) selectedIdx[i] = objectIdx[i];
    } else {
      selectedCount = N;
      for(uint8_t i = 0; i < N; i++) selectedIdx[i] = i;
    }

    int medR = medianFromIndexedBuffer(measRs, selectedIdx, selectedCount);
    int medG = medianFromIndexedBuffer(measGs, selectedIdx, selectedCount);
    int medB = medianFromIndexedBuffer(measBs, selectedIdx, selectedCount);
    bool medianObject = false;
    bool medianConfident = false;
    uint16_t coreVoteBOS = 0;
    uint16_t coreVoteR = 0;
    uint16_t coreVoteY = 0;
    uint16_t coreVoteB = 0;
    uint16_t coreVoteCAL = 0;
    long coreScoreR = 0;
    long coreScoreY = 0;
    long coreScoreB = 0;
    long coreStrengthMax = 0;
    long coreStrengthMin = 2147483647L;

    for(uint8_t i = 0; i < selectedCount; i++){
      uint8_t idx = selectedIdx[i];
      applyVoteForCode(measLabelCodes[idx], coreVoteBOS, coreVoteR, coreVoteY, coreVoteB, coreVoteCAL);

      long sR = 0;
      long sY = 0;
      long sB = 0;
      colorScoresForRaw(measRs[idx], measGs[idx], measBs[idx], sR, sY, sB);
      coreScoreR += sR;
      coreScoreY += sY;
      coreScoreB += sB;

      if(measStrengths[idx] > coreStrengthMax) coreStrengthMax = measStrengths[idx];
      if(measStrengths[idx] < coreStrengthMin) coreStrengthMin = measStrengths[idx];
    }
    if(coreStrengthMin == 2147483647L) coreStrengthMin = 0;

    String voteCls = majorityLabelOf(coreVoteBOS, coreVoteR, coreVoteY, coreVoteB, coreVoteCAL);
    String medianNearest = classifyNearest(medR, medG, medB);
    String scoreNearest = "KIRMIZI";
    long bestScore = coreScoreR;
    if(coreScoreY < bestScore){ bestScore = coreScoreY; scoreNearest = "SARI"; }
    if(coreScoreB < bestScore){ bestScore = coreScoreB; scoreNearest = "MAVI"; }
    String finalCls = classifyStable(medR, medG, medB, medianObject, medianConfident);
    String finalSource = usedCoreWindow ? "CORE_STABLE" : "MEDIAN_STABLE";
    long medDR = 0;
    long medDY = 0;
    long medDB = 0;
    colorScoresForRaw(medR, medG, medB, medDR, medDY, medDB);
    int emptyR, emptyG, emptyB;
    effectiveEmpty(emptyR, emptyG, emptyB);
    long medDX = dist3(medR, medG, medB, emptyR, emptyG, emptyB);

    uint16_t voteWin = topVoteCountOf(coreVoteBOS, coreVoteR, coreVoteY, coreVoteB, coreVoteCAL);
    uint16_t voteSecond = secondVoteCountOf(coreVoteBOS, coreVoteR, coreVoteY, coreVoteB, coreVoteCAL);
    uint16_t classifiedVotes = coreVoteR + coreVoteY + coreVoteB;
    uint8_t searchHintWin = 0;
    uint8_t searchHintSecond = 0;
    String searchHint = detectHintLabel(&searchHintWin, &searchHintSecond);
    bool searchHintStrong = (searchHint != "BELIRSIZ" && searchHintWin >= 2 && searchHintWin > searchHintSecond);
    bool searchHintFallbackAllowed = (classifiedVotes >= 3 && voteWin >= 2);
    bool reviewRequired = false;

    if(finalCls == "KIRMIZI" && scoreNearest == "SARI" && coreVoteY >= coreVoteR && coreVoteY >= 2){
      finalCls = "SARI";
      finalSource = "CORE_SCORE_Y";
      reviewRequired = true;
    } else if(finalCls == "SARI" && scoreNearest == "KIRMIZI" && coreVoteR >= (coreVoteY + 2) && coreVoteR >= 3){
      finalCls = "KIRMIZI";
      finalSource = "CORE_SCORE_R";
      reviewRequired = false;
    }

    if(finalCls == "BELIRSIZ" && voteCls == medianNearest && voteCls != "BOS" && voteCls != "CAL" &&
       classifiedVotes >= 3 && voteWin >= 2 && ((voteWin * 100U) >= (classifiedVotes * 65U))){
      finalCls = voteCls;
      finalSource = "CORE_VOTE_MATCH";
    } else if(finalCls == "BELIRSIZ" && scoreNearest == voteCls && voteCls != "BOS" && voteCls != "CAL" &&
              classifiedVotes >= 4 && voteWin >= 3){
      finalCls = scoreNearest;
      finalSource = "CORE_SCORE_VOTE";
    }

    if(finalCls == "BELIRSIZ" &&
       medianNearest == "KIRMIZI" &&
       scoreNearest == "KIRMIZI" &&
       coreVoteR >= 2 &&
       coreVoteR > coreVoteY &&
       coreVoteR > coreVoteB){
      finalCls = "KIRMIZI";
      finalSource = "CORE_SCORE_R_FALLBACK";
      reviewRequired = true;
    }

    if(finalCls == "BELIRSIZ" && searchHintStrong && searchHintFallbackAllowed){
      finalCls = searchHint;
      finalSource = "SEARCH_HINT_STRONG";
      reviewRequired = true;
    } else if(searchHintStrong && searchHintFallbackAllowed && finalCls != searchHint &&
              (!medianConfident || classifiedVotes < 4 || finalSource == "CORE_SCORE_VOTE")){
      finalCls = searchHint;
      finalSource = "SEARCH_HINT_OVERRIDE";
      reviewRequired = true;
    }

    bool yellowEvidence = (medianNearest == "SARI") || (scoreNearest == "SARI") || (coreVoteY >= 2);
    if(searchHint == "SARI" && yellowEvidence){
      if((finalCls == "KIRMIZI" || finalCls == "MAVI") && (coreVoteY + 1) >= voteWin){
        finalCls = "SARI";
        finalSource = "SEARCH_HINT_Y";
        reviewRequired = true;
      } else if(finalCls == "BELIRSIZ"){
        finalCls = "SARI";
        finalSource = "SEARCH_HINT_FALLBACK";
        reviewRequired = true;
      }
    }

    if(finalCls == "SARI" && (voteWin <= (voteSecond + 1) || !medianConfident || searchHint != "SARI")){
      reviewRequired = true;
    }

    lastMeasured = finalCls;
    if(finalCls == "BOS" || finalCls == "CAL" || finalCls == "BELIRSIZ"){
      lastMeasuredSnapshotValid = false;
      lastMeasuredLabelCode = MEAS_LABEL_OTHER;
      lastMeasuredDX = 0;
    } else {
      lastMeasuredSnapshotValid = true;
      lastMeasuredR = medR;
      lastMeasuredG = medG;
      lastMeasuredB = medB;
      lastMeasuredDX = medDX;
      lastMeasuredLabelCode = sampleLabelCode(finalCls);
    }
    unsigned long measuredId = activeMeasureId;
    unsigned long queuedItemId = 0;
    bool queueAccepted = false;
    if(finalCls != "BOS" && finalCls != "CAL" && finalCls != "BELIRSIZ" && pendingCount < MAX_PENDING_ITEMS){
      queuedItemId = nextItemId++;
      queueAccepted = enqueuePendingItem(finalCls, TRAVEL_MS, queuedItemId, measuredId, finalSource, reviewRequired);
      if(!queueAccepted){
        queuedItemId = 0;
      }
    }

    Serial1.print("MEGA|TCS3200|STATE=MEASURING|MEASURE_ID=");
    Serial1.print(measuredId);
    Serial1.print("|ITEM_ID=");
    Serial1.print(queuedItemId);
    Serial1.print("|FINAL=");
    Serial1.print(finalCls);
    Serial1.print("|FINAL_SOURCE=");
    Serial1.print(finalSource);
    Serial1.print("|SEARCH_HINT=");
    Serial1.print(searchHint);
    Serial1.print("|SEARCH_HINT_WIN=");
    Serial1.print(searchHintWin);
    Serial1.print("|SEARCH_HINT_SECOND=");
    Serial1.print(searchHintSecond);
    Serial1.print("|SEARCH_HINT_STRONG=");
    Serial1.print(searchHintStrong ? 1 : 0);
    Serial1.print("|SEARCH_HINT_FALLBACK_ALLOWED=");
    Serial1.print(searchHintFallbackAllowed ? 1 : 0);
    Serial1.print("|REVIEW=");
    Serial1.print(reviewRequired ? 1 : 0);
    Serial1.print("|CORE_USED=");
    Serial1.print(usedCoreWindow ? 1 : 0);
    Serial1.print("|CORE_N=");
    Serial1.print(selectedCount);
    Serial1.print("|OBJ_N=");
    Serial1.print(objectCount);
    Serial1.print("|MEDIAN_NEAREST=");
    Serial1.print(medianNearest);
    Serial1.print("|SCORE_NEAREST=");
    Serial1.print(scoreNearest);
    Serial1.print("|MED_R=");
    Serial1.print(medR);
    Serial1.print("|MED_G=");
    Serial1.print(medG);
    Serial1.print("|MED_B=");
    Serial1.print(medB);
    Serial1.print("|MED_D_R=");
    Serial1.print(medDR);
    Serial1.print("|MED_D_Y=");
    Serial1.print(medDY);
    Serial1.print("|MED_D_B=");
    Serial1.print(medDB);
    Serial1.print("|MED_D_X=");
    Serial1.print(medDX);
    Serial1.print("|X_R=");
    Serial1.print(emptyR);
    Serial1.print("|X_G=");
    Serial1.print(emptyG);
    Serial1.print("|X_B=");
    Serial1.print(emptyB);
    Serial1.print("|MED_OBJ=");
    Serial1.print(medianObject ? 1 : 0);
    Serial1.print("|CONF=");
    Serial1.print(medianConfident ? 1 : 0);
    Serial1.print("|CORE_STR_MIN=");
    Serial1.print(coreStrengthMin);
    Serial1.print("|CORE_STR_MAX=");
    Serial1.print(coreStrengthMax);
    Serial1.print("|VOTE_WIN=");
    Serial1.print(voteWin);
    Serial1.print("|VOTE_SECOND=");
    Serial1.print(voteSecond);
    Serial1.print("|VOTE_CLASSIFIED=");
    Serial1.print(classifiedVotes);
    Serial1.print("|VOTE_BOS=");
    Serial1.print(coreVoteBOS);
    Serial1.print("|VOTE_R=");
    Serial1.print(coreVoteR);
    Serial1.print("|VOTE_Y=");
    Serial1.print(coreVoteY);
    Serial1.print("|VOTE_B=");
    Serial1.print(coreVoteB);
    Serial1.print("|VOTE_CAL=");
    Serial1.print(coreVoteCAL);
    Serial1.print("|TOT_R=");
    Serial1.print(voteR);
    Serial1.print("|TOT_Y=");
    Serial1.print(voteY);
    Serial1.print("|TOT_B=");
    Serial1.print(voteB);
    Serial1.print("|TOT_BOS=");
    Serial1.print(voteBOS);
    Serial1.print("|TOT_CAL=");
    Serial1.print(voteCAL);
    Serial1.print("|PENDING=");
    Serial1.println(pendingCount);

    detectStreak = 0;
    resetDetectLabels();
    resetSearchCentering();
    sensorRearmRequired = true;
    sensorClearStreak = 0;
    sensorRearmRemainingMs = SENSOR_REARM_MIN_RUN_MS;
    lastSenseMs = 0;
    activeMeasureId = 0;

    if(finalCls == "BOS" || finalCls == "CAL" || finalCls == "BELIRSIZ"){
      logEvent("AUTO", "STATE=SEARCHING|REASON=EMPTY_OR_UNCERTAIN");
    } else {
      if(!queueAccepted){
        logEvent("AUTO", "ERROR=QUEUE_FULL|ACTION=DROP_ITEM");
        logAlarm("QUEUE_FULL", String("LEVEL=WARN|ACTION=DROP_ITEM|STATE=") + autoStateStr());
      } else {
        logEvent("AUTO", String("QUEUE=ENQ|ITEM_ID=") + queuedItemId
          + "|MEASURE_ID=" + measuredId
          + "|COLOR=" + finalCls
          + "|DECISION_SOURCE=" + finalSource
          + "|REVIEW=" + (reviewRequired ? 1 : 0)
          + "|TRAVEL_MS=" + TRAVEL_MS
          + "|PENDING=" + pendingCount);
      }
    }

    if(!autoMode){
      st = SEARCHING;
      motorStop();
      pausePendingTravelTimer();
      logEvent("AUTO", String("STATE=PAUSED|EVENT=MEASURE_DONE|QUEUE=") + pendingCount);
      publishStatusNow();
      return;
    }

    runConveyorAndTrack(now);
    publishStatusNow();
    return;
  }

  // 3) WAIT_ARM: robot bitene kadar bekle; bitince kuyruktaki sonraki küpe geç
  if(st == WAIT_ARM){
    motorStop();
    pausePendingTravelTimer();
    if(pickPlaceDone()){
      if(!activePickCompletedLogged){
        logActivePickCompleted("WAIT_ARM");
      }
      dequeuePendingItem();
      pickPlaceResetDone();

      if(!autoMode){
        if(!hasPendingItems()){
          st = STOPPED;
          stopRequested = false;
          logActivePickReturnDone("STOPPED", false, pendingCount);
        } else {
          st = SEARCHING;
          logActivePickReturnDone("PAUSED", true, pendingCount);
        }
        clearPickRuntime();
        motorStop();
        pausePendingTravelTimer();
        publishStatusNow();
        return;
      }

      logActivePickReturnDone("SEARCHING", false, pendingCount);
      clearPickRuntime();
      lastSenseMs = 0;
      detectStreak = 0;
      resetDetectLabels();
      resetSearchCentering();
      runConveyorAndTrack(now);
      publishStatusNow();
    }
    return;
  }
}
