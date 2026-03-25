# FERP Integration Boundary

## Mevcut Durum

Bu repoda FERP entegrasyonu icin resmi API veya dogrudan veritabani kontrati henuz net degildir. Bu nedenle ilk entegrasyon siniri iki CSV dosyasi uzerinden tanimlanmistir:

- `production_events.csv`
- `production_completed.csv`

Bu iki dosya, entegrasyon netlesene kadar gecici ama baglayici veri siniri kabul edilmelidir.

## `production_events.csv`

Bu dosya append-only olay kaydidir. Olay bazli geriye donuk izleme icin kullanilir.

Alanlar:

- `event_time`
- `item_id`
- `measure_id`
- `source`
- `event_type`
- `color`
- `decision_source`
- `queue_depth`
- `mega_state`
- `raw_r`
- `raw_g`
- `raw_b`
- `confidence`
- `vision_track_id`
- `notes`

Beklenen kaynaklar ve tipik olaylar:

- `mega`
  - `measurement_decision`
  - `queue_enq`
  - `arm_position_reached`
  - `pickplace_done`
- `vision`
  - `box_confirmed`
  - `box_lost`
  - `line_crossed`

## `production_completed.csv`

Bu dosya FERP'ye aktarilabilecek ozet uretim kaydini temsil eder.

Alanlar:

- `item_id`
- `detected_at`
- `completed_at`
- `color`
- `status`
- `travel_ms`
- `cycle_ms`
- `decision_source`

## Alan Esleme Taslagi

FERP tarafinda resmi alan isimleri netlesene kadar asagidaki esleme taslagi kullanilmalidir:

- `item_id` -> uretim kaydinin benzersiz anahtari
- `completed_at` -> uretim tamamlama zamani
- `color` -> urun varyanti veya renk kodu
- `status` -> tamamlandi / inceleme gerekli gibi sonuc bilgisi
- `cycle_ms` -> operasyon suresi
- `decision_source` -> karar kaynagi veya siniflandirma izi

## Degisiklik Kurallari

- Mevcut kolon adlari keyfi olarak degistirilmemelidir.
- Yeni alan eklemek gerekiyorsa once bu alanin FERP'de bir karsiligi olup olmadigi yazilmalidir.
- Kesin kontrat olusana kadar append-only mantigi korunmalidir.
- Entegrasyon sinirinda ana veri kaynagi CSV dosyalaridir; MQTT mesajlari yardimci telemetry olarak ele alinmalidir.

## Sonraki Adimlar

- FERP tarafinda resmi import formati veya API tanimini almak
- Alan bazli dogrulama kurallarini netlestirmek
- CSV -> JSON -> FERP akisinda hangi katmanin donusum yapacagini belirlemek
- Hata durumlari icin retry ve reconciliation kuralini tanimlamak

## AI Icin Notlar

- AI'dan entegrasyon isi isterken mutlaka hedef FERP cikti formatini veya eldeki ornekleri ekleyin.
- Yeni kolon, durum kodu veya event tipi onerileri bu dosya ile birlikte degerlendirilmelidir.
- "FERP'ye gonder" gibi belirsiz bir gorev yerine hangi alanlardan hangi kayda donusum beklendigi yazilmalidir.
