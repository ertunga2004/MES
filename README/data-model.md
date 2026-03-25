# Data Model

## Amac

Bu dokuman, projedeki veri yapilarini iki seviyede aciklar:

- su anda gercekten uretilen calisan veri kaynaklari
- ileride MES seviyesine tasinmasi planlanan kavramsal varliklar

## Aktif Veri Kaynaklari

### 1. `production_events.csv`

Append-only olay kaydidir. Hattaki ham operasyonel olaylar burada tutulur.

Ana alanlar:

- `event_time`: olay zamani
- `item_id`: urun veya kutu kimligi
- `measure_id`: olcum/karar kimligi
- `source`: olay kaynagi (`mega`, `vision`)
- `event_type`: olay tipi
- `color`: renk veya varyant bilgisi
- `decision_source`: karar kaynagi
- `queue_depth`: kuyruk derinligi
- `mega_state`: Mega durum bilgisi
- `raw_r`, `raw_g`, `raw_b`: renk sensoru ham degerleri
- `confidence`: siniflandirma guveni
- `vision_track_id`: vision tarafindaki track kimligi
- `notes`: serbest not

### 2. `production_completed.csv`

FERP'ye gidecek ozet uretim kaydidir.

Ana alanlar:

- `item_id`
- `detected_at`
- `completed_at`
- `color`
- `status`
- `travel_ms`
- `cycle_ms`
- `decision_source`

### 3. MQTT Telemetry

MQTT topicleri operasyonel gorunurluk saglar, ancak sistemin kalici veri modeli yerine gecmez. Kalici entegrasyon acisindan CSV ciktilari halen daha onceliklidir.

## Kimlikler ve Iliskiler

- `item_id`: bir kutunun hatta girisinden tamamlanmasina kadar ortak kimligi olmalidir.
- `measure_id`: belirli bir olcum veya karar anini temsil eder.
- `vision_track_id`: sadece vision tarafindaki izleme kimligidir; `item_id` yerine gecmez.

Temel iliski mantigi:

- bir `item_id`, birden fazla `production_events` kaydina sahip olabilir
- bir `item_id`, en fazla bir `production_completed` kaydi ile kapanmalidir
- bir `measure_id`, olaylar ile siniflandirma adimini baglamak icin kullanilir

## Planlanan Kavramsal Varliklar

### Products

- `product_id`
- `color`
- `unit`

### Work Orders

- `work_order_id`
- `product_id`
- `quantity`
- `line`

### Lines

- `line_id`
- `name`

### Operators

- `operator_id`
- `name`

### Stations

- `station_id`
- `type`

### Downtime

- `type`
- `duration`
- `start_time`
- `end_time`

## OEE ve Raporlama Icin Turetilen Alanlar

- planli durus
- plansiz durus
- toplam uretim miktari
- hatali uretim miktari
- ortalama cycle suresi
- kuyruk bekleme ve tasima sureleri

Bu metriklerin bir kismi dogrudan kaydedilmiyor; event log uzerinden turetilmesi gerekiyor.

## Gelecek Asama

- CSV tabanli modelden iliskisel veritabani modeline gecis
- FERP kontratina gore alan isimlerinin netlestirilmesi
- work order ve operator bilgisinin hatta baglanmasi
- OEE hesaplari icin standart raporlama tablolari

## AI Icin Notlar

- Var olan CSV kolonlarini degistirmeden once `FERP_INTEGRATION.md` ile uyumu kontrol edin.
- Yeni alan onermeden once bunun olay seviyesi mi, ozet seviye mi oldugunu belirtin.
- `item_id`, `measure_id` ve `vision_track_id` birbirinin yerine kullanilmamalidir.
