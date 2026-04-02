# System Architecture

## Mimari Amac

Bu proje, saha cihazlarindan gelen text telemetry'yi canli operator ekranina ve kalici workbook kaydina donusturen katmanli bir MES prototipidir. Mimari, kontrol tarafini uygulama ve raporlama tarafindan ayirmak icin bilerek parcali tasarlanmistir.

## Katmanlar

### 1. Physical Layer

- konveyor
- robot kol
- renk sensori
- limit switch'ler

Bu katman dogrudan fiziksel harekettir. Buradaki gercek karar ve emniyet mantigi uygulama katmanina degil, kontrol katmanina aittir.

### 2. Control Layer

- `mega.cpp`

Sorumluluklari:

- obje algilama ve olcum akisini yonetmek
- queue mantigini isletmek
- robot kol tetikleme sirasini belirlemek
- durum ve olay satirlarini uretmek

Bu katman, sorting kararinin tek ana otoritesidir.

### 3. Edge / Bridge Layer

- `esp32.cpp`

Sorumluluklari:

- Mega seri cikisini okumak
- MQTT'ye publish etmek
- komutlari `cmd` topic'inden alip Mega'ya iletmek
- Wi-Fi, MQTT ve queue telemetry'sini raporlamak

### 4. Communication Layer

- MQTT broker
- root: `sau/iot/mega/konveyor/`

Bu katman veri tasir. Karar vermez. Text topicler ana hat icin, JSON topicler vision ve yardimci moduller icin kullanilir.

### 5. Application Layer

#### Legacy Application

- repo disi Node-RED arsivi

Rol:

- gecis doneminde eski ekran ve akislari referans almak
- parity karsilastirmasi yapmak
- gerekirse saha gecmisini incelemek

#### Yeni Application

- `mes_web/`

Rol:

- MQTT ingest
- normalize dashboard snapshot
- REST bootstrap + WebSocket canli yayin
- komut publish
- OEE runtime ve vardiya kontrolu
- workbook tabanli kalici veri yazimi

Bugunku ana gelistirme hedefi bu katmandir.

### 6. Observation Layer

- `raspberry/`

Rol:

- kutu tespiti
- track atama
- line crossing sayimi
- sari / diger renk capraz kontrolu

Bu katman pasiftir. Mega kararini override etmez.

### 7. Data and Integration Layer

Aktif veri katmanlari:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
- `logs\oee_runtime_state.json`
- `logs\log_YYYY-MM-DD.txt`
- `logs\tablet_log_YYYY-MM-DD.txt`

Planlanan sonraki katman:

- workbook'tan turetilen FERP JSON cikisi

## Canli Veri Akislari

### Operasyon Akisi

1. Mega olay uretir.
2. ESP32 bunu `status`, `logs`, `heartbeat`, `bridge/status` topiclerine tasir.
3. `mes_web` bu topicleri dinler.
4. Browser ilk olarak `GET /api/modules/{module_id}/dashboard` cagirir.
5. Sonra `WS /ws/modules/{module_id}` ile canli snapshot alir.
6. WebSocket koparsa son snapshot korunur ve istemci reconnect dener.

### OEE Akisi

1. OEE runtime state `logs/oee_runtime_state.json` icinde tutulur.
2. Vardiya secimi ve baslatma/bitirme komutlari web UI'dan gelir.
3. Aktif vardiyada `PICKPLACE_DONE` olayi tamamlanan urun sayilir.
4. Tamamlanan urun varsayilan olarak `good` kabul edilir.
5. Fault verisi `tablet/log` satirlarindan okunur.
6. Availability, Performance, Quality ve OEE backend tarafinda hesaplanir.
7. Sonuc hem UI snapshot'ina hem trend dizisine yansir.

### Persistence Akisi

1. `mes_web` MQTT log ve eventlerini normalize eder.
2. Excel sink bu olaylari workbook icindeki sheet'lere yazar.
3. Template workbook asla dogrudan ezilmez.
4. Her gun icin `logs/` altinda yeni tarihli workbook olusur.

## Kaynak Dogruluk Sirasi

Bir alan cakisiyorsa su oncelik sirasini kullan:

1. fiziksel karar ve olaylar icin `mega.cpp`
2. vardiya ve OEE runtime ayarlari icin `oee_runtime_state.json`
3. kalici olay ve rapor kaydi icin gunluk workbook
4. legacy parity icin yerel Node-RED arsivi

## Tasarim Kurallari

- MQTT tasima katmanidir; kontrol otoritesi degildir.
- Vision yardimci gozlem katmanidir; sorting karari vermez.
- Node-RED repo icinde tutulmaz; yeni ana ekran ve veri katmani `mes_web` olarak kabul edilmelidir.
- Excel workbook su anda birincil kalici veri siniridir.
- OEE sayimi aktif vardiya olmadan baslamaz.
- Sistem acilisinda daha once acik kalan vardiya otomatik devam ettirilmez.

## Mimaride Bilincli Olarak Geciktilen Parcalar

- manuel kalite override operator ekrani
- workbook replay / rebuild araci
- resmi FERP JSON kontrati
- yerel Node-RED arsivine bagimliligin sifirlanmasi

Bu basliklar roadmap'te ayri is kalemleri olarak ele alinmalidir.
