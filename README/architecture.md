# System Architecture

## Mimari Amac

Bu proje, saha cihazlarindan gelen telemetry'yi canli dashboard'a, operator kiosk'una, teknisyen cagri ekranina ve gunluk workbook kaydina donusturen katmanli bir MES prototipidir.

## Katmanlar

### 1. Physical Layer

- konveyor
- robot kol
- renk sensori
- limit switch'ler

Fiziksel hareket ve emniyet davranisi burada gerceklesir.

### 2. Control Layer

- `mega.cpp`

Sorumluluklari:

- obje algilama ve olcum akisini yonetmek
- queue mantigini isletmek
- robot kol tetikleme sirasini belirlemek
- durum ve olay satirlarini uretmek

Sorting kararinin ana otoritesi budur.

### 3. Edge / Bridge Layer

- `esp32.cpp`

Sorumluluklari:

- Mega seri cikisini okumak
- MQTT'ye publish etmek
- `cmd` topic'inden komut alip Mega'ya iletmek
- Wi-Fi, MQTT ve queue telemetry'sini raporlamak

### 4. Communication Layer

- MQTT broker
- varsayilan broker: `broker.emqx.io:1883`
- root: `sau/iot/mega/konveyor/`

Bu katman veri tasir. Browser dashboard, operator kiosk ve teknisyen kiosk MQTT'ye dogrudan baglanmaz.

### 5. Application Layer

- `mes_web/`

Sorumluluklari:

- MQTT ingest
- dashboard snapshot
- kiosk bootstrap snapshot
- teknisyen cagri bootstrap snapshot
- REST + WebSocket canli yayin
- komut publish
- work order, quality, fault, maintenance ve OEE runtime state yonetimi
- workbook tabanli kalici veri yazimi

### 6. Observation Layer

- `raspberry/`

Sorumluluklari:

- kutu tespiti
- track atama
- line crossing sayimi
- capraz renk gozlemi

Vision pasif gozlemci katmandir; ana sorting kararini vermez.

### 7. Data and Integration Layer

Aktif veri katmanlari:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
- `logs\oee_runtime_state.json`
- `logs\log_YYYY-MM-DD.txt`
- `logs\tablet_log_YYYY-MM-DD.txt`

## Canli Veri Akislari

### Dashboard Akisi

1. Mega olay uretir.
2. ESP32 bunu MQTT topiclerine tasir.
3. `mes_web` topicleri dinler.
4. Browser once REST snapshot alir.
5. Sonra WebSocket ile canli guncelleme alir.
6. Baglanti koparsa istemci reconnect dener.

### Kiosk Akisi

1. Tablet veya telefon `GET /kiosk/{device_id}` ile kiosk ekranini acar.
2. Kiosk `GET /api/modules/{module_id}/kiosk/bootstrap` ile ilk state'i alir.
3. Kiosk `WS /ws/modules/{module_id}/kiosk/{device_id}` ile canli snapshot'a baglanir.
4. Operatorden gelen aksiyonlar REST endpoint'leri ile backend'e gider.
5. `Ariza Bildir`, manuel fault ile birlikte teknisyen cagrisi acar.
6. Backend gerekli ise MQTT `cmd` topic'ine komut publish eder.

### Teknisyen Akisi

1. Teknisyen `GET /technician/{device_id}` ile cagri ekranini acar.
2. Ekran `GET /api/modules/{module_id}/technician/bootstrap` ile aktif ve gecmis cagrilari alir.
3. Ekran `WS /ws/modules/{module_id}/technician/{device_id}` ile canli snapshot'a baglanir.
4. `Cevapla`, cagri acilisindan kabul anina kadar cevap suresini sabitler.
5. `Tamamla`, giderme/toplam sureyi sabitler ve bagli aktif kiosk fault varsa kapatir.

### OEE Akisi

1. OEE runtime state `logs/oee_runtime_state.json` icinde tutulur.
2. Vardiya ve kontrol aksiyonlari backend tarafinda islenir.
3. Ic sure alanlari ms-first tutulur.
4. Durus siniflandirmasi su sekildedir:
   - `openingChecklistDurationMs` = OEE disi
   - `closingChecklistDurationMs` = planned stop / planned maintenance
   - `manualFaultDurationMs` = unplanned stop
5. Availability, Performance, Quality ve OEE backend tarafinda hesaplanir.

### Persistence Akisi

1. `mes_web` MQTT log ve eventlerini normalize eder.
2. Excel sink olaylari workbook sheet'lerine yazar.
3. Template workbook asla dogrudan ezilmez.
4. Her gun icin `logs/` altinda yeni tarihli workbook olusur.
5. Bakim detaylari `9_Bakim_Kayitlari`, fault detaylari `3_Arizalar`, audit ozeti `1_Olay_Logu` icine duser.

## Kaynak Otorite Sirasi

Bir alan cakisirsa su oncelik kullanilir:

1. fiziksel karar ve olaylar icin `mega.cpp`
2. vardiya ve OEE runtime state icin `oee_runtime_state.json`
3. kalici audit ve rapor kaydi icin gunluk workbook
4. parity veya gecmis referansi icin legacy arsivler

## Tasarim Kurallari

- MQTT tasima katmanidir; UI otoritesi degildir
- browser kiosk ve teknisyen ekranlari MQTT bilgisi bilmez
- cihaz bazli audit backend device registry ile tutulur
- Excel workbook bugunku birincil kalici sinirdir
- OEE sayimi aktif vardiya olmadan baslamaz
- sistem acilisinda acik kalan vardiya otomatik devam ettirilmez
- hurda olarak isaretli tamamlanmis urun depoya dusmez

## Bilincli Olarak Sonraya Birakilanlar

- direct JSON state topic ailesi
- workbook replay / rebuild araci
- FastAPI `lifespan` gecisi
