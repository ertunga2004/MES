# Data Model

## Amac

Bu dokuman, projede bugun gercekten uretilen veri yapilarini aciklar. Eski CSV odakli model yerine aktif veri katmanlari, runtime state ve workbook sheet'leri uzerinden dusunulmelidir.

## Canli Veri Kaynaklari

### 1. MQTT Text ve JSON Akisi

Ana hat topicleri:

- `status`
- `logs`
- `heartbeat`
- `bridge/status`
- `tablet/log`

Vision topicleri:

- `vision/status`
- `vision/heartbeat`
- `vision/tracks`
- `vision/events`

Bu veri kalici model degil, operasyonel olay ve gorunurluk katmanidir.

### 2. Dashboard Snapshot

`mes_web` tarafinda browser'a giden ana modeldir.

Ana bloklar:

- `module_meta`
- `connection`
- `system_status`
- `hardware_status`
- `counts`
- `recent_logs`
- `command_permissions`
- `timestamps`
- `vision_ingest`
- `oee`

Bu model UI kontratidir. Frontend ve backend ayni snapshot semasini kullanir.

### 3. OEE Runtime State

Dosya:

- `logs\oee_runtime_state.json`

Ana alanlar:

- `shiftSelected`
- `performanceMode`
- `targetQty`
- `idealCycleSec`
- `plannedStopMin`
- `shift`
- `counts`
- `itemsById`
- `recentItemIds`
- `activeFault`
- `faultHistory`
- `unplannedDowntimeMs`
- `trend`
- `lastEventSummary`
- `lastUpdatedAt`

Bu dosya, vardiya kontrolu ve backend OEE hesabinin calisan kaynagidir.

### 4. Gunluk Workbook

Dosya:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`

Sheet'ler:

- `1_Olay_Logu`
- `2_Olcumler`
- `4_Uretim_Tamamlanan`
- `6_Vision`
- `7_Raw_Logs`

Bu workbook, bugunku birincil kalici veri siniridir.

## Kimlikler

### `item_id`

Bir urunun hatta girdikten sonra tamamlanana kadar tasidigi ana kimliktir.

### `measure_id`

Olcum veya siniflandirma anini temsil eden kimliktir.

### `vision_track_id`

Sadece vision observer tarafindaki izleme kimligidir. `item_id` yerine gecmez.

## Olay Mantigi

### Olcum ve Queue

- `measurement_decision`
  - renk kararinin verildigi an
- `queue_enq`
  - urun kuyruga alindigi an

### Robot ve Tamamlanma

- `arm_position_reached`
  - robot hazirlik / konum olayi
- `pickplace_done`
  - tamamlanmis urun olayi
- `pickplace_return_done`
  - robotun birakma sonrasi hazir bekleme pozisyonuna geri dondugu an

Aktif vardiyada `pickplace_done`, backend tarafinda:

- tamamlanan urun
- varsayilan kalite = `GOOD`

olarak sayilir.

## OEE Veri Kurallari

### Sayima Girme Kosulu

- vardiya aktif olmadan urun OEE sayacina girmez

### Varsayilan Kalite

- robotun biraktigi tamamlanmis urun ilk anda `Saglam` kabul edilir
- sonradan operator override edebilmelidir
- bu override UI'si sonraki fazdadir

### Formuller

- `Availability = runtime / elapsed`
- `runtime = elapsed - unplanned_downtime`
- `Performance = completed / target` veya `completed / expected_by_cycle`
- `Quality = good / total`
- `OEE = Availability * Performance * Quality`

### Fault Veri Kaynagi

- aktif fault bilgisi `tablet/log` satirlarindan gelir

## Workbook Sheet Modeli

### `1_Olay_Logu`

Amaç:

- normalize olay kaydi
- kaynak, event type, item, measure, color, decision source, queue depth gibi alanlari tutmak

### `2_Olcumler`

Amaç:

- TCS3200 karar detaylarini
- ham ve turetilmis olcum alanlarini
- search hint ve vote alanlarini

tutmak

### `4_Uretim_Tamamlanan`

Amaç:

- queue'dan tamamlanmis urune gecisi kaydetmek
- `detected_at` alanini sensor olcum/giris ani olarak tutmak
- `completed_at` alanini robot birakma/cikis ani olarak tutmak
- `flow_ms` alanini ayni urunun giris-cikis suresi olarak tutmak
- `cycle_ms` alanini ard arda iki cikis arasindaki fark olarak tutmak

### `6_Vision`

Amaç:

- vision event akisini normalize etmek

### `7_Raw_Logs`

Amaç:

- ham satiri kaybetmeden saklamak
- replay veya analiz icin ham payload'i korumak

## Eski CSV Durumu

`production_events.csv` ve `production_completed.csv` yeni veri modelinin merkezi degildir. Yeni dokumanlarda bu dosyalar ancak tarihsel veya legacy referans olarak anilmalidir.

## Sonraki Veri Modeli Adimlari

- manuel kalite override sonucu workbook ve runtime state'e baglanacak
- vardiya kapanis ozeti icin ayri rapor modeli netlesecek
- FERP icin resmi JSON kontrati workbook'tan turetilecek
