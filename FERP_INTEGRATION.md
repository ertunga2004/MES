# FERP CSV Hazirligi

Bu repo icinde ilk entegrasyon katmani iki CSV dosyasidir:

- `production_events.csv`
- `production_completed.csv`

## `production_events.csv`

Append-only olay kaydidir. Sutunlar:

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

Beklenen kaynaklar:

- `mega`: `measurement_decision`, `queue_enq`, `arm_position_reached`, `pickplace_done`
- `vision`: `line_crossed`, `box_confirmed`, `box_lost`

## `production_completed.csv`

FERP'ye yuklenecek ana uretim tablosu icin hazir satirlar:

- `item_id`
- `detected_at`
- `completed_at`
- `color`
- `status`
- `travel_ms`
- `cycle_ms`
- `decision_source`

## FERP alan esleme taslagi

Su asamada FERP giris kontrati bilinmedigi icin asagidaki taslak kullanilmalidir:

- `item_id` -> uretim kaydi benzersiz anahtari
- `completed_at` -> uretim tamamlama zamani
- `color` -> urun varyanti / renk kodu
- `status` -> tamamlandi veya inceleme gerekli
- `cycle_ms` -> operasyon suresi
- `decision_source` -> karar kaynagi veya siniflandirma izi

## Sonraki adim

FERP tarafinda resmi API, import formati veya veritabani entegrasyon noktasi netlestiginde bu dokuman alan-ad-alan kesinlestirilmelidir. O asamaya kadar CSV dosyalari tek dogruluk kaynagi kabul edilir.
