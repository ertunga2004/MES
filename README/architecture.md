# System Architecture

## Kapsam

Bu proje, mini konveyor hattinda fiziksel hareketten ERP'ye veri tasimaya kadar olan zinciri kapsayan bir MES prototipidir. Mimari; kontrol, haberlesme, izleme ve entegrasyon katmanlarina bilincli olarak ayrilmistir.

## Katmanlar

### 1. Physical Layer

- Konveyor
- Robot kol
- Renk sensori ve limit switch'ler

### 2. Control Layer

- `mega.cpp`
- Gercek zamanli durum makinesi
- Renk olcumu, queue ve pick-place akisi

### 3. Edge Layer

- `esp32.cpp`
- Mega UART cikisini MQTT'ye tasiyan bridge

### 4. Communication Layer

- MQTT broker
- Topic root: `sau/iot/mega/konveyor/`

### 5. Application Layer

- `node-red.json`
- Dashboard, veri toplama ve entegrasyon akislari
- Gerekirse operator arayuzu veya kiosk katmani

### 6. Observation Layer

- `raspberry/` altindaki observer servisi
- Vision tabanli sayim, track ve capraz kontrol
- Pasif gozlemci rolunde calisir

### 7. Data and Integration Layer

- `production_events.csv`
- `production_completed.csv`
- JSON veya ERP import ciktilari

## Calisma Sorumluluklari

- Mega: fiziksel surecin ana otoritesi
- ESP32: haberlesme koprusu, komut iletimi ve telemetry forwarding
- Node-RED: operator gorunurlugu, veri akisi ve entegrasyon duzeni
- Raspberry observer: goruntu tabanli dogrulama ve sayim
- FERP entegrasyonu: CSV tabanli gecici sinir

## Ana Veri Akislari

### Kontrol Akisi

1. Sensor veya durum degisikligi Mega tarafinda algilanir.
2. Mega, konveyor ve robot kol davranisini belirler.
3. Mega log ve status satirlarini seri hat uzerinden ESP32'ye yollar.
4. ESP32 bunlari uygun MQTT topiclerine yayar.

### Entegrasyon Akisi

1. Olaylar `production_events.csv` tarafinda birikir.
2. Tamamlanan urunler `production_completed.csv` icine yazilir.
3. Node-RED veya sonraki bir entegrasyon katmani bu verileri FERP'ye hazirlar.

### Vision Akisi

1. Observer, kameradan ROI icinde kutulari tespit eder.
2. Tracker, kutulara `track_id` atar.
3. `status`, `heartbeat`, `tracks` ve `events` topicleri uzerinden JSON yayinlar.
4. Bu veri, ana karar mekanizmasini degistirmeden capraz kontrol icin kullanilir.

## Tasarim Sinirlari

- MQTT, kontrol katmaninin yerine gecmez; tasima ve gorunurluk amaciyla kullanilir.
- Vision servisi yardimci katmandir; sorting karari Mega'da kalir.
- FERP kontrati kesinlesene kadar CSV yapisi korunmalidir.
- Yeni bir bilesen eklenirken mevcut topic root ve veri akisi bozulmamalidir.

## AI Icin Notlar

- Mimari degisikligi onerirken hangi katmanin sahipligini degistirdiginizi acik yazin.
- Yeni topic, event veya CSV kolonu oneriyorsaniz bunun hangi katmanda uretilecegini belirtin.
- "Tum sistemi yeniden tasarla" yerine mevcut katmanlari koruyan kucuk degisiklikler tercih edilmelidir.
