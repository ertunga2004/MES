# Workbook Data Dictionary

## 1. Amac

Bu dokuman, gunluk MES workbook sheet'lerinde fiilen kullanilan kolonlar icin alan seviyesinde veri sozlugu tanimlar.

Bu dokuman migration script'i, SQL DDL, kod degisikligi veya Excel sablonu degisikligi degildir. Workbook kolon adlari korunur; amac mevcut workbook'u audit/projection/backfill/replay kaynagi olarak anlasilir hale getirmektir.

Temel karar:

- Gunluk workbook canli transactional DB degildir.
- Workbook audit, projection, backfill ve replay yardimci kaynagidir.
- Runtime karar otoritesi backend/runtime state tarafindadir.
- `7_Is_Emirleri` workbook projection'dir; canonical `work_orders` modeli yerine gecmez.
- `5_OEE_Anliklari` event degil, calculated OEE snapshot/time-series yapisidir.
- `99_Raw_Logs` normal raporlama DB'si degil, debug/audit/archive kaynagidir.

## 2. Kaynaklar

Dokuman kaynaklari:

- `docs/workbook-schema.md`
- `docs/masterdata-design.md`
- `docs/database-plan.md`
- `docs/data-dictionary-plan.md`
- `docs/workbook-field-inventory.md`
- `docs/workbook-needs-review-fields.md`

Kod ve test kaynaklari:

- `mes_web/excel_runtime.py`
- `mes_web/parsers.py`
- `mes_web/oee_state.py`
- `tests/test_mes_web_excel_runtime.py`
- `tests/test_mes_web_oee_state.py`

## 3. Kapsam ve Kapsam Disi Alanlar

Kapsam:

- `1_Olay_Logu`
- `2_Olcumler`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `5_OEE_Anliklari`
- `6_Vision`
- `7_Is_Emirleri`
- `8_Depo_Stok`
- `9_Bakim_Kayitlari`
- `99_Raw_Logs`

Kapsam disi:

- `0_Tanimlamalar` masterdata tasarimi; bunun ayrimi `docs/masterdata-design.md` icindedir.
- SQL DDL ve migration uygulamasi.
- Excel sablon kolonlarini degistirme onerisi.
- Python runtime davranisini degistirme.

## 4. Genel Veri Sozlugu Kurallari

| Kural | Aciklama |
| --- | --- |
| Kolon adi korunur | Mevcut workbook kolon adlari degistirilmez |
| Workbook source of truth degildir | Workbook audit/projection/backfill/replay kaynagidir |
| Projection ID canonical ID degildir | `*_record_id`, `work_order_record_id` gibi alanlar sheet/projection kimligidir |
| `*_tr` canonical kod degildir | Goruntu/audit label snapshot olarak ele alinir |
| `*_ms` birincildir | Sure alanlarinda ms-first kuralidir |
| `*_sec` turetilmistir | Uyumlu gorunum veya raporlama yardimci alanidir |
| Sensor debug metrikleri ayridir | Ana MES domain alanlari gibi modellenmemelidir |
| Lookup alanlari dogrulanir | Kod/id alanlari ilgili master/lookup tabloyla eslesmelidir |

## 5. Sheet Bazli Veri Sozlugu

### `1_Olay_Logu`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `log_event_id` | Olay kayit no | Normalized event/audit satir kimligi | integer | yes | audit_event | `1_Olay_Logu.log_event_id` | `event_log.log_event_id` | yes | no | no | yes | yes | `101` | Workbook event projection id |
| `event_time_text` | Olay zamani | Olayin alindigi veya uretildigi zaman | datetime_iso | yes | audit_event | `1_Olay_Logu.event_time_text` | `event_log.event_time` | no | no | no | yes | yes | `2026-04-02T10:15:25Z` | ISO datetime hedeflenir |
| `source_id` | Kaynak id | Event kaynagi lookup id | integer | yes | audit_event | `1_Olay_Logu.source_id` | `event_log.source_id` | no | yes | no | yes | yes | `1` | `sources` lookup |
| `source_code` | Kaynak kodu | Event kaynagi kodu | string | yes | audit_event | `1_Olay_Logu.source_code` | `event_log.source_code` | no | yes | no | yes | yes | `mega` | `sources` lookup canonical kodu |
| `event_type_id` | Olay tipi id | Event type lookup id | integer | yes | audit_event | `1_Olay_Logu.event_type_id` | `event_log.event_type_id` | no | yes | no | yes | yes | `3` | `event_types` lookup |
| `event_type_code` | Olay tipi kodu | Normalized event tipi kodu | string | yes | audit_event | `1_Olay_Logu.event_type_code` | `event_log.event_type_code` | no | yes | no | yes | yes | `measurement_decision` | Backfill sirasi icin kritik |
| `event_summary_tr` | Olay ozeti | Turkce gorunen event ozeti | text | no | audit_event | `1_Olay_Logu.event_summary_tr` | `event_log.event_summary_tr` | no | no | no | yes | no | `Olcum karari` | Label snapshot, canonical kod degil |
| `item_id` | Urun iz kimligi | Urun/nesne izleme referansi | string | conditional | audit_event | `1_Olay_Logu.item_id` | `event_log.item_id` | no | no | no | yes | yes | `42` | Bazi eventlerde bos olabilir |
| `measure_id` | Olcum kimligi | Measurement karar referansi | string | conditional | audit_event | `1_Olay_Logu.measure_id` | `event_log.measure_id` | no | no | no | yes | yes | `8` | Urun kimligi degildir |
| `fault_id` | Ariza kimligi | Fault event/session referansi | string | conditional | audit_event | `1_Olay_Logu.fault_id` | `event_log.fault_id` | no | no | no | yes | yes | `FLT-1` | Ariza eventlerinde dolu olabilir |
| `oee_snapshot_id` | OEE snapshot no | OEE snapshot referansi | integer | conditional | audit_event | `1_Olay_Logu.oee_snapshot_id` | `event_log.oee_snapshot_id` | no | no | no | yes | yes | `12` | Snapshot id, event id degil |
| `vision_event_id` | Vision olay no | Vision observation referansi | integer | conditional | audit_event | `1_Olay_Logu.vision_event_id` | `event_log.vision_event_id` | no | no | no | yes | yes | `31` | Vision audit satiri referansi |
| `line_id` | Hat id | Hat master referansi | string | conditional | audit_event | `1_Olay_Logu.line_id` | `event_log.line_id` | no | yes | no | yes | yes | `line1` | `lines` master lookup |
| `station_id` | Istasyon id | Istasyon master referansi | string | conditional | audit_event | `1_Olay_Logu.station_id` | `event_log.station_id` | no | yes | no | yes | yes | `station1` | `stations` master lookup |
| `oee_scope` | OEE kapsami | OEE hesap kapsami veya operasyon kapsami | string | no | audit_event | `1_Olay_Logu.oee_scope` | `event_log.oee_scope` | no | yes | no | yes | yes | `station1_component_transfer` | Lookup adayi |
| `package_cycle_id` | Paket cevrim id | Station2/package cycle referansi | string | no | audit_event | `1_Olay_Logu.package_cycle_id` | `event_log.package_cycle_id` | no | no | no | yes | yes | `PKG-1` | Canonical cycle id olarak zorlanmamali |
| `color_id` | Renk id | Renk lookup id | integer | conditional | audit_event | `1_Olay_Logu.color_id` | `event_log.color_id` | no | yes | no | yes | yes | `1` | `colors` lookup |
| `color_code` | Renk kodu | Normalize renk kodu | string | conditional | audit_event | `1_Olay_Logu.color_code` | `event_log.color_code` | no | yes | no | yes | yes | `red` | `colors` lookup canonical kodu |
| `decision_source_id` | Karar kaynagi id | Karar kaynagi lookup id | integer | conditional | audit_event | `1_Olay_Logu.decision_source_id` | `event_log.decision_source_id` | no | yes | no | yes | yes | `1` | `decision_sources` lookup |
| `decision_source_code` | Karar kaynagi kodu | Sensor/vision/system karar kaynagi | string | conditional | audit_event | `1_Olay_Logu.decision_source_code` | `event_log.decision_source_code` | no | yes | no | yes | yes | `CORE_STABLE` | `decision_sources` lookup |
| `mega_state_id` | Mega durum id | Mega state lookup id | integer | conditional | audit_event | `1_Olay_Logu.mega_state_id` | `event_log.mega_state_id` | no | yes | no | yes | yes | `7` | `mega_states` lookup |
| `mega_state_code` | Mega durum kodu | Mega runtime state kodu | string | conditional | audit_event | `1_Olay_Logu.mega_state_code` | `event_log.mega_state_code` | no | yes | no | yes | yes | `measuring` | `mega_states` lookup |
| `queue_depth` | Kuyruk derinligi | Olay anindaki kuyruk sayaci | integer | no | audit_event | `1_Olay_Logu.queue_depth` | `event_log.queue_depth` | no | no | no | yes | yes | `1` | Event-time metric |
| `review_required` | Inceleme gerekli | Event icin operator/kalite review flag'i | boolean | no | audit_event | `1_Olay_Logu.review_required` | `event_log.review_required` | no | no | no | yes | yes | `0` | Boolean 0/1 |
| `travel_ms` | Tasima suresi ms | Olayla iliskili travel duration | duration_ms | no | audit_event | `1_Olay_Logu.travel_ms` | `event_log.travel_ms` | no | no | no | yes | yes | `640` | ms-first |
| `notes` | Notlar | Event aciklama ve ek notlar | text | no | audit_event | `1_Olay_Logu.notes` | `event_log.notes` | no | no | no | yes | no | `search_hint=SARI` | Serbest metin |
| `raw_line` | Ham satir | Event'e kaynak ham log satiri | text | no | audit_event | `1_Olay_Logu.raw_line` | `event_log.raw_line` | no | no | no | yes | yes | `MEGA...` | Debug/backfill dogrulama icin |

### `2_Olcumler`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `measurement_row_id` | Olcum satir no | Workbook measurement satir kimligi | integer | yes | audit_event | `2_Olcumler.measurement_row_id` | `measurements.measurement_row_id` | yes | no | no | yes | yes | `1` | Projection row id |
| `measure_id` | Olcum kimligi | Sensor olcum/karar kimligi | string | yes | audit_event | `2_Olcumler.measure_id` | `measurements.measure_id` | yes | no | no | yes | yes | `8` | Urun kimligi degildir |
| `item_id` | Urun iz kimligi | Olcumun baglandigi item referansi | string | conditional | audit_event | `2_Olcumler.item_id` | `measurements.item_id` | no | no | no | yes | yes | `42` | Traceability icin onemli |
| `measured_at` | Olcum zamani | Olcum kararinin alindigi zaman | datetime_iso | yes | audit_event | `2_Olcumler.measured_at` | `measurements.measured_at` | no | no | no | yes | yes | `2026-04-02T10:15:25Z` | ISO datetime hedeflenir |
| `measurement_log_event_id` | Olcum event referansi | `1_Olay_Logu` measurement event id referansi | integer | yes | audit_event | `2_Olcumler.measurement_log_event_id` | `measurements.measurement_log_event_id` | no | no | no | yes | yes | `101` | Event log iliskisi |
| `source_log_file` | Kaynak log etiketi | Measurement kaynak log ailesi | string | no | audit_event | `2_Olcumler.source_log_file` | `measurements.source_log_file` | no | no | no | yes | yes | `mqtt/logs` | Resolved; fiziksel dosya yolu degil, provenance etiketi |
| `final_color_id` | Nihai renk id | Nihai renk lookup id | integer | yes | audit_event | `2_Olcumler.final_color_id` | `measurements.final_color_id` | no | yes | no | yes | yes | `1` | `colors` lookup |
| `final_color_code` | Nihai renk kodu | Normalize nihai renk kodu | string | yes | audit_event | `2_Olcumler.final_color_code` | `measurements.final_color_code` | no | yes | no | yes | yes | `red` | `colors` lookup |
| `final_color_raw` | Raw renk degeri | Sensor payload'undaki raw final renk tokeni | string | no | audit_event | `2_Olcumler.final_color_raw` | `measurements.final_color_raw` | no | no | no | yes | yes | `KIRMIZI` | Raw kaynak deger |
| `decision_source_id` | Karar kaynagi id | Karar kaynagi lookup id | integer | yes | audit_event | `2_Olcumler.decision_source_id` | `measurements.decision_source_id` | no | yes | no | yes | yes | `1` | `decision_sources` lookup |
| `decision_source_code` | Karar kaynagi kodu | Sensor karar kaynagi kodu | string | yes | audit_event | `2_Olcumler.decision_source_code` | `measurements.decision_source_code` | no | yes | no | yes | yes | `CORE_STABLE` | `decision_sources` lookup |
| `search_hint` | Arama ipucu | Sensor raw `SEARCH_HINT` aday/arama ipucu | string | no | audit_event | `2_Olcumler.search_hint` | `measurement_debug_metrics.search_hint` | no | no | no | yes | yes | `SARI` | partially_resolved; final color degildir |
| `search_hint_win` | Arama pencere metrigi | Raw `SEARCH_HINT_WIN` sensor metrigi | integer | no | audit_event | `2_Olcumler.search_hint_win` | `measurement_debug_metrics.search_hint_win` | no | no | no | yes | yes | `2` | partially_resolved; pencere anlami netlesmeli |
| `search_hint_second` | Ikincil arama metrigi | Raw `SEARCH_HINT_SECOND` sensor metrigi | integer | no | audit_event | `2_Olcumler.search_hint_second` | `measurement_debug_metrics.search_hint_second` | no | no | no | yes | yes | `1` | partially_resolved |
| `search_hint_strong` | Guclu arama metrigi | Raw `SEARCH_HINT_STRONG` flag/sayac metrigi | integer_or_boolean | no | audit_event | `2_Olcumler.search_hint_strong` | `measurement_debug_metrics.search_hint_strong` | no | no | no | yes | yes | `1` | partially_resolved; flag mi sayac mi net degil |
| `search_hint_fallback_allowed` | Fallback izin flag'i | Search hint fallback kullanilabilir flag'i | boolean | no | audit_event | `2_Olcumler.search_hint_fallback_allowed` | `measurement_debug_metrics.search_hint_fallback_allowed` | no | no | no | yes | yes | `1` | Sensor algorithm context |
| `review_required` | Inceleme gerekli | Measurement review flag'i | boolean | no | audit_event | `2_Olcumler.review_required` | `measurements.review_required` | no | no | no | yes | yes | `0` | Boolean 0/1 |
| `core_used` | Core kullanildi | Core karar algoritmasi kullanildi flag'i | boolean | no | audit_event | `2_Olcumler.core_used` | `measurement_metrics.core_used` | no | no | no | yes | yes | `1` | Sensor metric |
| `core_n` | Core sample sayisi | Raw `CORE_N` sample/sayac metrigi | integer | no | audit_event | `2_Olcumler.core_n` | `measurement_metrics.core_n` | no | no | no | yes | yes | `6` | partially_resolved |
| `obj_n` | Object sample sayisi | Raw `OBJ_N` sample/sayac metrigi | integer | no | audit_event | `2_Olcumler.obj_n` | `measurement_metrics.obj_n` | no | no | no | yes | yes | `10` | partially_resolved |
| `median_nearest` | En yakin median adayi | Median bazli en yakin aday etiketi | string | no | audit_event | `2_Olcumler.median_nearest` | `measurement_metrics.median_nearest` | no | no | no | yes | yes | `SARI` | partially_resolved; canonical color degil |
| `score_nearest` | En yakin skor | Raw `SCORE_NEAREST`; skor veya aday etiketi olabilir | string_or_decimal | no | audit_event | `2_Olcumler.score_nearest` | `measurement_metrics.score_nearest` | no | no | no | yes | yes | `SARI` | unresolved; veri tipi kontrati netlesmeli |
| `med_r` | Median red | Sensor median red kanal metrigi | integer | no | audit_event | `2_Olcumler.med_r` | `measurement_metrics.med_r` | no | no | no | yes | yes | `10` | Sensor detail |
| `med_g` | Median green | Sensor median green kanal metrigi | integer | no | audit_event | `2_Olcumler.med_g` | `measurement_metrics.med_g` | no | no | no | yes | yes | `20` | Sensor detail |
| `med_b` | Median blue | Sensor median blue kanal metrigi | integer | no | audit_event | `2_Olcumler.med_b` | `measurement_metrics.med_b` | no | no | no | yes | yes | `30` | Sensor detail |
| `med_d_r` | Median red mesafesi | Median ile red/kirmizi aday mesafesi | integer | no | audit_event | `2_Olcumler.med_d_r` | `measurement_metrics.med_d_r` | no | no | no | yes | yes | `11` | partially_resolved; formulu kodda yok |
| `med_d_y` | Median yellow mesafesi | Median ile yellow/sari aday mesafesi | integer | no | audit_event | `2_Olcumler.med_d_y` | `measurement_metrics.med_d_y` | no | no | no | yes | yes | `22` | partially_resolved |
| `med_d_b` | Median blue mesafesi | Median ile blue/mavi aday mesafesi | integer | no | audit_event | `2_Olcumler.med_d_b` | `measurement_metrics.med_d_b` | no | no | no | yes | yes | `33` | partially_resolved |
| `med_d_x` | Median empty mesafesi | Median ile `BOS`/empty aday mesafesi gibi gorunur | integer | no | audit_event | `2_Olcumler.med_d_x` | `measurement_metrics.med_d_x` | no | no | no | yes | yes | `44` | partially_resolved; `x` canonical renk degil |
| `x_r` | Empty red ozelligi | `X_R` sensor detail degeri | integer | no | audit_event | `2_Olcumler.x_r` | `measurement_debug_metrics.x_r` | no | no | no | yes | yes | `101` | partially_resolved; debug metrigi |
| `x_g` | Empty green ozelligi | `X_G` sensor detail degeri | integer | no | audit_event | `2_Olcumler.x_g` | `measurement_debug_metrics.x_g` | no | no | no | yes | yes | `102` | partially_resolved; debug metrigi |
| `x_b` | Empty blue ozelligi | `X_B` sensor detail degeri | integer | no | audit_event | `2_Olcumler.x_b` | `measurement_debug_metrics.x_b` | no | no | no | yes | yes | `103` | partially_resolved; debug metrigi |
| `med_obj` | Median object metrigi | Raw `MED_OBJ` object/median sensor metrigi | integer | no | audit_event | `2_Olcumler.med_obj` | `measurement_debug_metrics.med_obj` | no | no | no | yes | yes | `1` | partially_resolved |
| `confidence` | Guven skoru | Sensor confidence degeri | decimal | no | audit_event | `2_Olcumler.confidence` | `measurements.confidence` | no | no | no | yes | yes | `0.95` | 0 gelebilir ve error flag uretebilir |
| `core_str_min` | Core sinyal min | Raw `CORE_STR_MIN` signal strength minimumu | integer | no | audit_event | `2_Olcumler.core_str_min` | `measurement_debug_metrics.core_str_min` | no | no | no | yes | yes | `12` | partially_resolved; birim net degil |
| `core_str_max` | Core sinyal max | Raw `CORE_STR_MAX` signal strength maksimumu | integer | no | audit_event | `2_Olcumler.core_str_max` | `measurement_debug_metrics.core_str_max` | no | no | no | yes | yes | `24` | partially_resolved; birim net degil |
| `vote_win` | Vote pencere metrigi | Raw `VOTE_WIN` vote window/sayac metrigi | integer | no | audit_event | `2_Olcumler.vote_win` | `measurement_metrics.vote_win` | no | no | no | yes | yes | `6` | partially_resolved |
| `vote_second` | Ikincil vote | Raw `VOTE_SECOND` ikincil vote metrigi | integer | no | audit_event | `2_Olcumler.vote_second` | `measurement_metrics.vote_second` | no | no | no | yes | yes | `1` | partially_resolved |
| `vote_classified` | Siniflanan vote | Raw `VOTE_CLASSIFIED` siniflanan vote sayisi/flag'i | integer | no | audit_event | `2_Olcumler.vote_classified` | `measurement_metrics.vote_classified` | no | no | no | yes | yes | `6` | partially_resolved |
| `vote_x` | Empty vote | Raw `VOTE_BOS`; empty/bos aday vote sayisi | integer | no | audit_event | `2_Olcumler.vote_x` | `measurement_metrics.vote_x` | no | no | no | yes | yes | `3` | partially_resolved; `x` canonical renk degil |
| `vote_r` | Red vote | Red/kirmizi aday vote sayisi | integer | no | audit_event | `2_Olcumler.vote_r` | `measurement_metrics.vote_r` | no | no | no | yes | yes | `0` | Sensor metric |
| `vote_y` | Yellow vote | Yellow/sari aday vote sayisi | integer | no | audit_event | `2_Olcumler.vote_y` | `measurement_metrics.vote_y` | no | no | no | yes | yes | `1` | Sensor metric |
| `vote_b` | Blue vote | Blue/mavi aday vote sayisi | integer | no | audit_event | `2_Olcumler.vote_b` | `measurement_metrics.vote_b` | no | no | no | yes | yes | `2` | Sensor metric |
| `vote_cal` | Calibration vote | Raw `VOTE_CAL`; calibration/cal vote metrigi olabilir | integer | no | audit_event | `2_Olcumler.vote_cal` | `measurement_debug_metrics.vote_cal` | no | no | no | yes | yes | `0` | unresolved; `CAL` anlami net degil |
| `tot_r` | Toplam red | Red/kirmizi toplam sayaci | integer | no | audit_event | `2_Olcumler.tot_r` | `measurement_metrics.tot_r` | no | no | no | yes | yes | `4` | Sensor total metric |
| `tot_y` | Toplam yellow | Yellow/sari toplam sayaci | integer | no | audit_event | `2_Olcumler.tot_y` | `measurement_metrics.tot_y` | no | no | no | yes | yes | `5` | Sensor total metric |
| `tot_b` | Toplam blue | Blue/mavi toplam sayaci | integer | no | audit_event | `2_Olcumler.tot_b` | `measurement_metrics.tot_b` | no | no | no | yes | yes | `6` | Sensor total metric |
| `tot_x` | Toplam empty | Raw `TOT_BOS`; empty/bos toplam sayaci | integer | no | audit_event | `2_Olcumler.tot_x` | `measurement_metrics.tot_x` | no | no | no | yes | yes | `7` | partially_resolved; `x` canonical renk degil |
| `tot_cal` | Toplam calibration | Raw `TOT_CAL`; calibration/cal toplam sayaci olabilir | integer | no | audit_event | `2_Olcumler.tot_cal` | `measurement_debug_metrics.tot_cal` | no | no | no | yes | yes | `0` | unresolved; `CAL` anlami net degil |
| `measurement_error_flag` | Olcum hata flag'i | Measurement validation/error flag'i | boolean | no | audit_event | `2_Olcumler.measurement_error_flag` | `measurements.measurement_error_flag` | no | no | no | yes | yes | `1` | Confidence veya karar sorunu olabilir |
| `measurement_error_reason` | Olcum hata nedeni | Measurement hata aciklamasi | text | no | audit_event | `2_Olcumler.measurement_error_reason` | `measurements.measurement_error_reason` | no | no | no | yes | yes | `confidence=0` | Serbest hata nedeni |
| `raw_line` | Ham satir | Olcume kaynak raw Mega satiri | text | no | audit_event | `2_Olcumler.raw_line` | `measurements.raw_line` | no | no | no | yes | yes | `MEGA...` | Debug/backfill dogrulama |

### `3_Arizalar`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fault_record_id` | Ariza kayit no | Workbook fault satir kimligi | integer | yes | audit_event | `3_Arizalar.fault_record_id` | `fault_events.fault_record_id` | yes | no | no | yes | yes | `1` | Projection row id |
| `fault_id` | Ariza kimligi | Fault session/event kimligi | string | yes | audit_event | `3_Arizalar.fault_id` | `fault_events.fault_id` | yes | no | no | yes | yes | `FLT-001` | Fault history ana referansi |
| `status_code` | Durum kodu | Ariza durum kodu | string | yes | audit_event | `3_Arizalar.status_code` | `fault_events.status_code` | no | yes | no | yes | yes | `active` | Fault status lookup adayi |
| `status_tr` | Durum etiketi | Turkce durum gorunum etiketi | string | no | audit_event | `3_Arizalar.status_tr` | `fault_events.status_tr` | no | no | no | yes | no | `Aktif` | Label snapshot, canonical kod degil |
| `fault_type_code` | Ariza tipi kodu | Standard fault type kodu | string | yes | audit_event | `3_Arizalar.fault_type_code` | `fault_events.fault_type_code` | no | yes | no | yes | yes | `robot_arm_jam` | `fault_types` lookup |
| `fault_category` | Ariza kategorisi | Fault kategori kodu/etiketi | string | no | audit_event | `3_Arizalar.fault_category` | `fault_events.fault_category` | no | yes | no | yes | yes | `mechanical` | Lookup adayi |
| `fault_reason_tr` | Ariza nedeni | Turkce fault reason etiketi | text | no | audit_event | `3_Arizalar.fault_reason_tr` | `fault_events.fault_reason_tr` | no | no | no | yes | yes | `Robot kol sikismasi` | Label snapshot |
| `started_at` | Baslama zamani | Ariza baslama zamani | datetime_iso | yes | audit_event | `3_Arizalar.started_at` | `fault_events.started_at` | no | no | no | yes | yes | `2026-04-02T10:20:00Z` | ISO datetime |
| `ended_at` | Bitis zamani | Ariza kapanis zamani | datetime_iso | conditional | audit_event | `3_Arizalar.ended_at` | `fault_events.ended_at` | no | no | no | yes | yes | `2026-04-02T10:25:00Z` | Acik arizada bos olabilir |
| `duration_ms` | Sure ms | Ariza suresi ms | duration_ms | conditional | audit_event | `3_Arizalar.duration_ms` | `fault_events.duration_ms` | no | no | no | yes | yes | `300000` | ms-first |
| `duration_sec` | Sure saniye | Ariza suresi saniye | duration_sec | no | audit_event | `3_Arizalar.duration_sec` | `fault_events.duration_sec` | no | no | no | yes | no | `300` | Turetilmis/uyumluluk |
| `source_code` | Kaynak kodu | Ariza kaynagi | string | yes | audit_event | `3_Arizalar.source_code` | `fault_events.source_code` | no | yes | no | yes | yes | `tablet` | `sources` lookup |
| `device_id` | Cihaz id | Fault ile iliskili cihaz referansi | string | conditional | audit_event | `3_Arizalar.device_id` | `fault_events.device_id` | no | no | no | yes | yes | `tablet-1` | Device master adayi |
| `device_name` | Cihaz adi | Cihaz gorunum adi | string | no | audit_event | `3_Arizalar.device_name` | `fault_events.device_name` | no | no | no | yes | no | `Tablet 1` | Display snapshot |
| `bound_station_id` | Bagli istasyon | Fault cihazinin/olayin bagli istasyonu | string | conditional | audit_event | `3_Arizalar.bound_station_id` | `fault_events.bound_station_id` | no | yes | no | yes | yes | `station2` | `stations` lookup |
| `operator_id` | Operator id | Fault kaydini acan/kapatan operator referansi | string | conditional | audit_event | `3_Arizalar.operator_id` | `fault_events.operator_id` | no | yes | no | yes | yes | `OP-001` | `operators` master |
| `operator_code` | Operator kodu | Operator kod snapshot'i | string | conditional | audit_event | `3_Arizalar.operator_code` | `fault_events.operator_code` | no | yes | no | yes | yes | `OP-001` | Operator lookup/master kodu |
| `operator_name` | Operator adi | Operator gorunum adi | string | no | audit_event | `3_Arizalar.operator_name` | `fault_events.operator_name` | no | no | no | yes | no | `Operator 1` | Display snapshot |
| `shift_code` | Vardiya kodu | Fault anindaki vardiya kodu | string | conditional | audit_event | `3_Arizalar.shift_code` | `fault_events.shift_code` | no | yes | no | yes | yes | `SHIFT-A` | `shifts` lookup |
| `notes` | Notlar | Fault serbest not alani | text | no | audit_event | `3_Arizalar.notes` | `fault_events.notes` | no | no | no | yes | no | `Manual call` | Serbest metin |

### `4_Uretim_Tamamlanan`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `production_record_id` | Uretim kayit no | Workbook completed production satir kimligi | integer | yes | audit_event | `4_Uretim_Tamamlanan.production_record_id` | `production_completions.production_record_id` | yes | no | no | yes | yes | `1` | Projection row id |
| `item_id` | Urun iz kimligi | Tamamlanan urun/item referansi | string | yes | audit_event | `4_Uretim_Tamamlanan.item_id` | `production_completions.item_id` | yes | no | no | yes | yes | `42` | Traceability ana alani |
| `measure_id` | Olcum kimligi | Tamamlanan urunun measurement referansi | string | conditional | audit_event | `4_Uretim_Tamamlanan.measure_id` | `production_completions.measure_id` | no | no | no | yes | yes | `8` | Measurement ile baglanti |
| `queue_event_log_id` | Kuyruk event id | Kuyruga alma event referansi | integer | conditional | audit_event | `4_Uretim_Tamamlanan.queue_event_log_id` | `production_completions.queue_event_log_id` | no | no | no | yes | yes | `102` | Event log referansi |
| `completion_event_log_id` | Tamamlama event id | Tamamlama event referansi | integer | yes | audit_event | `4_Uretim_Tamamlanan.completion_event_log_id` | `production_completions.completion_event_log_id` | no | no | no | yes | yes | `105` | Event log referansi |
| `detected_at` | Algilama zamani | Urunun algilandigi/olculdugu zaman | datetime_iso | conditional | audit_event | `4_Uretim_Tamamlanan.detected_at` | `production_completions.detected_at` | no | no | no | yes | yes | `2026-04-02T10:15:25Z` | ISO datetime |
| `completed_at` | Tamamlanma zamani | Urunun tamamlandigi zaman | datetime_iso | yes | audit_event | `4_Uretim_Tamamlanan.completed_at` | `production_completions.completed_at` | no | no | no | yes | yes | `2026-04-02T10:15:29Z` | Production history icin kritik |
| `color_id` | Renk id | Tamamlanan urun renk lookup id | integer | yes | audit_event | `4_Uretim_Tamamlanan.color_id` | `production_completions.color_id` | no | yes | no | yes | yes | `1` | `colors` lookup |
| `color_code` | Renk kodu | Tamamlanan urun renk kodu | string | yes | audit_event | `4_Uretim_Tamamlanan.color_code` | `production_completions.color_code` | no | yes | no | yes | yes | `red` | `colors` lookup |
| `color_raw` | Raw renk | Completion payload raw renk degeri | string | no | audit_event | `4_Uretim_Tamamlanan.color_raw` | `production_completions.color_raw` | no | no | no | yes | yes | `KIRMIZI` | Raw source value |
| `status_code` | Durum kodu | Completion durum kodu | string | yes | audit_event | `4_Uretim_Tamamlanan.status_code` | `production_completions.status_code` | no | yes | no | yes | yes | `COMPLETED` | Completion status lookup adayi |
| `status_tr` | Durum etiketi | Turkce completion durum etiketi | string | no | audit_event | `4_Uretim_Tamamlanan.status_tr` | `production_completions.status_tr` | no | no | no | yes | no | `Tamamlandi` | Label snapshot |
| `travel_ms` | Tasima suresi ms | Olcumden/queue'dan pick'e travel suresi | duration_ms | no | audit_event | `4_Uretim_Tamamlanan.travel_ms` | `production_completions.travel_ms` | no | no | no | yes | yes | `640` | ms-first |
| `flow_ms` | Akis suresi ms | Urunun flow/tamamlanma suresi | duration_ms | no | audit_event | `4_Uretim_Tamamlanan.flow_ms` | `production_completions.flow_ms` | no | no | no | yes | yes | `4000` | ms-first |
| `cycle_ms` | Cevrim suresi ms | Cycle duration ms | duration_ms | no | audit_event | `4_Uretim_Tamamlanan.cycle_ms` | `production_completions.cycle_ms` | no | no | no | yes | yes | `15000` | ms-first; bos olabilir |
| `decision_source_id` | Karar kaynagi id | Final renk karar kaynagi lookup id | integer | yes | audit_event | `4_Uretim_Tamamlanan.decision_source_id` | `production_completions.decision_source_id` | no | yes | no | yes | yes | `4` | `decision_sources` lookup |
| `decision_source_code` | Karar kaynagi kodu | Sensor/vision final karar kaynagi | string | yes | audit_event | `4_Uretim_Tamamlanan.decision_source_code` | `production_completions.decision_source_code` | no | yes | no | yes | yes | `VISION` | `decision_sources` lookup |
| `review_required` | Inceleme gerekli | Tamamlanan urun review flag'i | boolean | no | audit_event | `4_Uretim_Tamamlanan.review_required` | `production_completions.review_required` | no | no | no | yes | yes | `1` | Late/ambiguous vision sonucu olabilir |
| `final_quality_code` | Nihai kalite kodu | GOOD/REWORK/SCRAP kalite sonucu | string | yes | audit_event | `4_Uretim_Tamamlanan.final_quality_code` | `production_completions.final_quality_code` | no | yes | no | yes | yes | `GOOD` | `quality_codes` lookup |
| `final_quality_tr` | Nihai kalite etiketi | Turkce kalite label snapshot'i | string | no | audit_event | `4_Uretim_Tamamlanan.final_quality_tr` | `production_completions.final_quality_tr` | no | no | no | yes | no | `Saglam` | Canonical kod degil |
| `override_flag` | Override flag'i | Kalite/final karar override uygulandi mi | boolean | no | audit_event | `4_Uretim_Tamamlanan.override_flag` | `production_completions.override_flag` | no | no | no | yes | yes | `0` | Quality override izleme |
| `override_source_code` | Override kaynagi | Override kaynagi kodu | string | no | audit_event | `4_Uretim_Tamamlanan.override_source_code` | `production_completions.override_source_code` | no | yes | no | yes | yes | `operator` | Lookup adayi |
| `override_applied_at` | Override zamani | Override uygulanma zamani | datetime_iso | conditional | audit_event | `4_Uretim_Tamamlanan.override_applied_at` | `production_completions.override_applied_at` | no | no | no | yes | yes | `2026-04-02T10:16:00Z` | Override yoksa bos |
| `sensor_color_code` | Sensor renk kodu | Sensorun verdigi renk kodu | string | conditional | audit_event | `4_Uretim_Tamamlanan.sensor_color_code` | `production_completions.sensor_color_code` | no | yes | no | yes | yes | `yellow` | `colors` lookup |
| `vision_color_code` | Vision renk kodu | Visionun verdigi renk kodu | string | conditional | audit_event | `4_Uretim_Tamamlanan.vision_color_code` | `production_completions.vision_color_code` | no | yes | no | yes | yes | `red` | `colors` lookup; bos olabilir |
| `final_color_code` | Final renk kodu | Completion icin dondurulan final renk kodu | string | yes | audit_event | `4_Uretim_Tamamlanan.final_color_code` | `production_completions.final_color_code` | no | yes | no | yes | yes | `red` | `colors` lookup |
| `mismatch_flag` | Uyumsuzluk flag'i | Sensor ve vision renkleri farkli mi | boolean | no | audit_event | `4_Uretim_Tamamlanan.mismatch_flag` | `production_completions.mismatch_flag` | no | no | no | yes | yes | `1` | Sensor/vision audit |
| `correlation_status` | Korelasyon durumu | Sensor/vision korelasyon durumu | string | no | audit_event | `4_Uretim_Tamamlanan.correlation_status` | `production_completions.correlation_status` | no | yes | no | yes | yes | `MATCHED` | Lookup/enum adayi |
| `finalization_reason` | Final karar gerekcesi | Production finalization decision reason | string_enum | yes | audit_event | `4_Uretim_Tamamlanan.finalization_reason` | `production_completions.finalization_reason` | no | yes | no | yes | yes | `VISION_CORRECTED_MISMATCH` | Resolved; kalite kodu degildir |
| `early_pick_triggered` | Erken pick flag'i | Early pick tetiklendi mi | boolean | no | audit_event | `4_Uretim_Tamamlanan.early_pick_triggered` | `production_completions.early_pick_triggered` | no | no | no | yes | yes | `1` | Robot/pick audit |
| `pick_trigger_source` | Pick tetik kaynagi | Pick trigger kaynagi | string | no | audit_event | `4_Uretim_Tamamlanan.pick_trigger_source` | `production_completions.pick_trigger_source` | no | yes | no | yes | yes | `EARLY` | Lookup/enum adayi |
| `early_pick_request_sent_at` | Early pick istek zamani | Early pick request gonderim zamani | datetime_iso | conditional | audit_event | `4_Uretim_Tamamlanan.early_pick_request_sent_at` | `production_completions.early_pick_request_sent_at` | no | no | no | yes | yes | `2026-04-02T10:15:27Z` | ISO datetime; bos olabilir |
| `early_pick_accepted_at` | Early pick kabul zamani | Early pick accepted zamani | datetime_iso | conditional | audit_event | `4_Uretim_Tamamlanan.early_pick_accepted_at` | `production_completions.early_pick_accepted_at` | no | no | no | yes | yes | `2026-04-02T10:15:27Z` | ISO datetime; bos olabilir |
| `final_color_frozen_at` | Final renk freeze zamani | Final color kararinin donduruldugu zaman | datetime_iso | conditional | audit_event | `4_Uretim_Tamamlanan.final_color_frozen_at` | `production_completions.final_color_frozen_at` | no | no | no | yes | yes | `2026-04-02T10:15:29Z` | Vision kararinda kritik |
| `station_id` | Istasyon id | Completion istasyon referansi | string | yes | audit_event | `4_Uretim_Tamamlanan.station_id` | `production_completions.station_id` | no | yes | no | yes | yes | `station1` | `stations` lookup |
| `oee_scope` | OEE kapsami | Completion OEE hesap kapsami | string | yes | audit_event | `4_Uretim_Tamamlanan.oee_scope` | `production_completions.oee_scope` | no | yes | no | yes | yes | `station1_component_transfer` | OEE scope lookup adayi |
| `package_cycle_id` | Paket cevrim id | Station2 package cycle referansi | string | no | audit_event | `4_Uretim_Tamamlanan.package_cycle_id` | `production_completions.package_cycle_id` | no | no | no | yes | yes | `PKG-1` | Canonical cycle id olarak zorlanmamali |

### `5_OEE_Anliklari`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `oee_snapshot_id` | OEE snapshot no | Workbook OEE snapshot satir kimligi | integer | yes | workbook_projection | `5_OEE_Anliklari.oee_snapshot_id` | `oee_snapshots.oee_snapshot_id` | yes | no | no | yes | yes | `1` | Snapshot id, event id degil |
| `snapshot_time` | Snapshot zamani | OEE hesap snapshot zamani | datetime_iso | yes | workbook_projection | `5_OEE_Anliklari.snapshot_time` | `oee_snapshots.snapshot_time` | no | no | no | yes | yes | `2026-04-02T10:30:00Z` | Time-series ana zamani |
| `event_log_id` | Event referansi | Snapshot'a kaynak event referansi | integer | conditional | workbook_projection | `5_OEE_Anliklari.event_log_id` | `oee_snapshots.event_log_id` | no | no | no | yes | yes | `110` | Runtime snapshot'ta bos olabilir |
| `sample_cycle_tag` | Snapshot kaynak etiketi | OEE snapshot source/sample etiketi | string | no | workbook_projection | `5_OEE_Anliklari.sample_cycle_tag` | `oee_snapshots.sample_cycle_tag` | no | no | no | yes | yes | `runtime:shift_start:2026-04-02T08:00:00Z` | Resolved; event id veya cycle id degildir |
| `oee` | OEE | Hesaplanmis OEE yuzdesi | decimal | yes | workbook_projection | `5_OEE_Anliklari.oee` | `oee_snapshots.oee` | no | no | no | yes | yes | `61.7` | Calculated metric |
| `availability` | Availability | OEE availability bileseni | decimal | yes | workbook_projection | `5_OEE_Anliklari.availability` | `oee_snapshots.availability` | no | no | no | yes | yes | `83.3` | Calculated metric |
| `performance` | Performance | OEE performance bileseni | decimal | yes | workbook_projection | `5_OEE_Anliklari.performance` | `oee_snapshots.performance` | no | no | no | yes | yes | `75.0` | Calculated metric |
| `quality` | Quality | OEE quality bileseni | decimal | yes | workbook_projection | `5_OEE_Anliklari.quality` | `oee_snapshots.quality` | no | no | no | yes | yes | `98.0` | Calculated metric |
| `mavi_s` | Mavi saglam | Mavi good count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.mavi_s` | `oee_snapshots.mavi_s` | no | no | no | yes | yes | `3` | Calculated/count snapshot |
| `mavi_r` | Mavi rework | Mavi rework count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.mavi_r` | `oee_snapshots.mavi_r` | no | no | no | yes | yes | `0` | Calculated/count snapshot |
| `mavi_h` | Mavi hurda | Mavi scrap count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.mavi_h` | `oee_snapshots.mavi_h` | no | no | no | yes | yes | `0` | Calculated/count snapshot |
| `sari_s` | Sari saglam | Sari good count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.sari_s` | `oee_snapshots.sari_s` | no | no | no | yes | yes | `4` | Calculated/count snapshot |
| `sari_r` | Sari rework | Sari rework count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.sari_r` | `oee_snapshots.sari_r` | no | no | no | yes | yes | `0` | Calculated/count snapshot |
| `sari_h` | Sari hurda | Sari scrap count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.sari_h` | `oee_snapshots.sari_h` | no | no | no | yes | yes | `0` | Calculated/count snapshot |
| `kirmizi_s` | Kirmizi saglam | Kirmizi good count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.kirmizi_s` | `oee_snapshots.kirmizi_s` | no | no | no | yes | yes | `5` | Calculated/count snapshot |
| `kirmizi_r` | Kirmizi rework | Kirmizi rework count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.kirmizi_r` | `oee_snapshots.kirmizi_r` | no | no | no | yes | yes | `0` | Calculated/count snapshot |
| `kirmizi_h` | Kirmizi hurda | Kirmizi scrap count snapshot'i | integer | no | workbook_projection | `5_OEE_Anliklari.kirmizi_h` | `oee_snapshots.kirmizi_h` | no | no | no | yes | yes | `0` | Calculated/count snapshot |
| `is_full_cycle_reference` | Tam cevrim referansi | Snapshot tam cycle referansi mi flag'i | boolean | no | workbook_projection | `5_OEE_Anliklari.is_full_cycle_reference` | `oee_snapshots.is_full_cycle_reference` | no | no | no | yes | yes | `1` | Calculated snapshot context |
| `station_id` | Istasyon id | Snapshot istasyon referansi | string | conditional | workbook_projection | `5_OEE_Anliklari.station_id` | `oee_snapshots.station_id` | no | yes | no | yes | yes | `station2` | `stations` lookup |
| `oee_scope` | OEE kapsami | Snapshot OEE kapsami | string | yes | workbook_projection | `5_OEE_Anliklari.oee_scope` | `oee_snapshots.oee_scope` | no | yes | no | yes | yes | `station2_packaging_oee` | OEE scope lookup adayi |
| `package_cycle_id` | Paket cevrim id | Snapshot package cycle referansi | string | no | workbook_projection | `5_OEE_Anliklari.package_cycle_id` | `oee_snapshots.package_cycle_id` | no | no | no | yes | yes | `PKG-1` | Event id degil |
| `notes` | Notlar | Snapshot notlari | text | no | workbook_projection | `5_OEE_Anliklari.notes` | `oee_snapshots.notes` | no | no | no | yes | no | `reason=runtime_state` | Serbest metin |
| `raw_line` | Ham satir | Snapshot'a kaynak raw satir | text | no | workbook_projection | `5_OEE_Anliklari.raw_line` | `oee_snapshots.raw_line` | no | no | no | yes | yes | `Tablet OEE` | Debug/backfill dogrulama |

### `6_Vision`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `vision_event_id` | Vision olay no | Vision observation satir kimligi | integer | yes | audit_event | `6_Vision.vision_event_id` | `vision_observations.vision_event_id` | yes | no | no | yes | yes | `1` | Append audit id |
| `event_time` | Event zamani | Vision event alinis zamani | datetime_iso | yes | audit_event | `6_Vision.event_time` | `vision_observations.event_time` | no | no | no | yes | yes | `2026-04-02T10:15:27Z` | ISO datetime |
| `source_code` | Kaynak kodu | Vision event kaynagi | string | yes | audit_event | `6_Vision.source_code` | `vision_observations.source_code` | no | yes | no | yes | yes | `vision` | `sources` lookup |
| `vision_track_id` | Vision track id | Vision observer track kimligi | string | conditional | audit_event | `6_Vision.vision_track_id` | `vision_observations.vision_track_id` | no | no | no | yes | yes | `21` | `item_id` yerine gecmez |
| `event_type` | Vision event tipi | Vision event kodu | string | yes | audit_event | `6_Vision.event_type` | `vision_observations.event_type` | no | yes | no | yes | yes | `line_crossed` | Event type lookup adayi |
| `color_id` | Renk id | Vision renk lookup id | integer | conditional | audit_event | `6_Vision.color_id` | `vision_observations.color_id` | no | yes | no | yes | yes | `2` | `colors` lookup |
| `color_code` | Renk kodu | Vision normalize renk kodu | string | conditional | audit_event | `6_Vision.color_code` | `vision_observations.color_code` | no | yes | no | yes | yes | `yellow` | `colors` lookup |
| `item_id` | Urun iz kimligi | Vision event item referansi | string | conditional | audit_event | `6_Vision.item_id` | `vision_observations.item_id` | no | no | no | yes | yes | `42` | Bos olabilir |
| `measure_id` | Olcum kimligi | Vision event measurement referansi | string | conditional | audit_event | `6_Vision.measure_id` | `vision_observations.measure_id` | no | no | no | yes | yes | `8` | Measurement baglantisi |
| `confidence` | Guven skoru | Vision confidence skoru | decimal | no | audit_event | `6_Vision.confidence` | `vision_observations.confidence` | no | no | no | yes | yes | `0.95` | Numeric score |
| `confidence_tier` | Guven seviyesi | Vision confidence tier'i | string | no | audit_event | `6_Vision.confidence_tier` | `vision_observations.confidence_tier` | no | yes | no | yes | yes | `high` | Lookup/enum adayi |
| `correlation_status` | Korelasyon durumu | Vision/sensor correlation sonucu | string | no | audit_event | `6_Vision.correlation_status` | `vision_observations.correlation_status` | no | yes | no | yes | yes | `late` | Lookup/enum adayi |
| `late_vision_audit_flag` | Gec vision audit flag'i | Late vision audit flag'i | boolean | no | audit_event | `6_Vision.late_vision_audit_flag` | `vision_observations.late_vision_audit_flag` | no | no | no | yes | yes | `1` | Late vision finalization ile iliskili |
| `vision_observed_at` | Vision gozlem zamani | Vision tarafinda gozlem zamani | datetime_iso | conditional | audit_event | `6_Vision.vision_observed_at` | `vision_observations.vision_observed_at` | no | no | no | yes | yes | `2026-04-02T10:15:27Z` | ISO datetime |
| `vision_published_at` | Vision yayin zamani | Vision payload publish zamani | datetime_iso | conditional | audit_event | `6_Vision.vision_published_at` | `vision_observations.vision_published_at` | no | no | no | yes | yes | `2026-04-02T10:15:27Z` | ISO datetime |
| `vision_received_at` | Vision alinma zamani | Backend tarafinda alinan zaman | datetime_iso | yes | audit_event | `6_Vision.vision_received_at` | `vision_observations.vision_received_at` | no | no | no | yes | yes | `2026-04-02T10:15:27Z` | ISO datetime |
| `line_id` | Hat id | Vision event hat referansi | string | conditional | audit_event | `6_Vision.line_id` | `vision_observations.line_id` | no | yes | no | yes | yes | `line1` | `lines` lookup |
| `station_id` | Istasyon id | Vision event istasyon referansi | string | conditional | audit_event | `6_Vision.station_id` | `vision_observations.station_id` | no | yes | no | yes | yes | `station1` | `stations` lookup |
| `bbox_x1` | BBox x1 | Vision bounding box x1 koordinati | decimal | no | audit_event | `6_Vision.bbox_x1` | `vision_observations.bbox_x1` | no | no | no | yes | no | `10.5` | Vision geometry debug |
| `bbox_y1` | BBox y1 | Vision bounding box y1 koordinati | decimal | no | audit_event | `6_Vision.bbox_y1` | `vision_observations.bbox_y1` | no | no | no | yes | no | `20.5` | Vision geometry debug |
| `bbox_x2` | BBox x2 | Vision bounding box x2 koordinati | decimal | no | audit_event | `6_Vision.bbox_x2` | `vision_observations.bbox_x2` | no | no | no | yes | no | `110.5` | Vision geometry debug |
| `bbox_y2` | BBox y2 | Vision bounding box y2 koordinati | decimal | no | audit_event | `6_Vision.bbox_y2` | `vision_observations.bbox_y2` | no | no | no | yes | no | `120.5` | Vision geometry debug |
| `direction` | Yon | Vision object direction etiketi | string | no | audit_event | `6_Vision.direction` | `vision_observations.direction` | no | yes | no | yes | no | `left_to_right` | Lookup/enum adayi |
| `is_placeholder` | Placeholder flag'i | Placeholder/sentinel vision row flag'i | boolean | no | audit_event | `6_Vision.is_placeholder` | `vision_observations.is_placeholder` | no | no | no | yes | no | `0` | Technical flag |
| `notes` | Notlar | Vision notlari | text | no | audit_event | `6_Vision.notes` | `vision_observations.notes` | no | no | no | yes | no | `profile=red` | Serbest metin |

### `7_Is_Emirleri`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `work_order_record_id` | Is emri projection no | Workbook work order projection satir kimligi | integer | yes | runtime_projection | `7_Is_Emirleri.work_order_record_id` | `work_order_projection.work_order_record_id` | yes | no | yes | yes | yes | `1` | Projection id, canonical work order id degil |
| `order_id` | Is emri no | Is emri domain referansi | string | yes | runtime_projection | `7_Is_Emirleri.order_id` | `work_order_projection.order_id` | yes | no | yes | yes | yes | `WO-001` | Canonical `work_orders` modeline aday ama projection bu modelin yerine gecmez |
| `erp_type` | ERP tipi | FERP/ERP is emri tipi | string | no | runtime_projection | `7_Is_Emirleri.erp_type` | `work_order_projection.erp_type` | no | yes | yes | yes | yes | `FERP` | Import classification |
| `source_file` | Kaynak dosya | Work order import kaynak dosyasi | string | no | runtime_projection | `7_Is_Emirleri.source_file` | `work_order_projection.source_file` | no | no | yes | yes | yes | `ferp_work_orders.json` | Import provenance |
| `queued_at` | Kuyruga alinma zamani | Is emri queued zamani | datetime_iso | conditional | runtime_projection | `7_Is_Emirleri.queued_at` | `work_order_projection.queued_at` | no | no | yes | yes | yes | `2026-04-02T08:00:00Z` | ISO datetime |
| `started_at` | Baslama zamani | Is emri baslama zamani | datetime_iso | conditional | runtime_projection | `7_Is_Emirleri.started_at` | `work_order_projection.started_at` | no | no | yes | yes | yes | `2026-04-02T08:01:00Z` | ISO datetime |
| `completed_at` | Tamamlanma zamani | Is emri tamamlanma zamani | datetime_iso | conditional | runtime_projection | `7_Is_Emirleri.completed_at` | `work_order_projection.completed_at` | no | no | yes | yes | yes | `2026-04-02T08:30:00Z` | Completed degilse bos |
| `status_code` | Durum kodu | Is emri durum kodu | string | yes | runtime_projection | `7_Is_Emirleri.status_code` | `work_order_projection.status_code` | no | yes | yes | yes | yes | `active` | `work_order_statuses` lookup |
| `status_tr` | Durum etiketi | Turkce durum gorunum etiketi | string | no | runtime_projection | `7_Is_Emirleri.status_tr` | `work_order_projection.status_tr` | no | no | yes | yes | no | `Aktif` | Label snapshot |
| `stock_code` | Stok kodu | Is emrindeki stok/urun kodu | string | yes | runtime_projection | `7_Is_Emirleri.stock_code` | `work_order_projection.stock_code` | no | yes | yes | yes | yes | `BOX-RED` | Product/stok lookup adayi |
| `stock_name` | Stok adi | Stok/urun display adi | string | no | runtime_projection | `7_Is_Emirleri.stock_name` | `work_order_projection.stock_name` | no | no | yes | yes | no | `Red Box` | Display snapshot |
| `product_color` | Urun rengi | Is emri urun renk kodu | string | conditional | runtime_projection | `7_Is_Emirleri.product_color` | `work_order_projection.product_color` | no | yes | yes | yes | yes | `red` | `colors` lookup adayi |
| `target_qty` | Hedef miktar | Is emri hedef miktari | integer | yes | runtime_projection | `7_Is_Emirleri.target_qty` | `work_order_projection.target_qty` | no | no | yes | yes | yes | `10` | Canonical work order icin kritik |
| `fulfilled_qty` | Karsilanan miktar | Is emrinde karsilanan toplam miktar | integer | no | runtime_projection | `7_Is_Emirleri.fulfilled_qty` | `work_order_projection.fulfilled_qty` | no | no | yes | yes | yes | `7` | Projection counter |
| `production_qty` | Uretim miktari | Uretilen miktar | integer | no | runtime_projection | `7_Is_Emirleri.production_qty` | `work_order_projection.production_qty` | no | no | yes | yes | yes | `7` | Projection counter |
| `inventory_consumed_qty` | Tuketilen stok miktari | Operasyonel inventory tuketim miktari | integer | no | runtime_projection | `7_Is_Emirleri.inventory_consumed_qty` | `work_order_projection.inventory_consumed_qty` | no | no | yes | yes | yes | `7` | Resmi ERP stok hareketi degildir |
| `good_qty` | Saglam miktar | GOOD miktari | integer | no | runtime_projection | `7_Is_Emirleri.good_qty` | `work_order_projection.good_qty` | no | yes | yes | yes | yes | `7` | `quality_codes` ile anlamlandirilir |
| `rework_qty` | Rework miktar | REWORK miktari | integer | no | runtime_projection | `7_Is_Emirleri.rework_qty` | `work_order_projection.rework_qty` | no | yes | yes | yes | yes | `0` | Quality count |
| `scrap_qty` | Hurda miktar | SCRAP miktari | integer | no | runtime_projection | `7_Is_Emirleri.scrap_qty` | `work_order_projection.scrap_qty` | no | yes | yes | yes | yes | `0` | Quality count |
| `ideal_cycle_ms` | Ideal cycle ms | Ideal cycle suresi ms | duration_ms | no | runtime_projection | `7_Is_Emirleri.ideal_cycle_ms` | `work_order_projection.ideal_cycle_ms` | no | no | yes | yes | yes | `15000` | ms-first |
| `ideal_cycle_sec` | Ideal cycle saniye | Ideal cycle suresi saniye | duration_sec | no | runtime_projection | `7_Is_Emirleri.ideal_cycle_sec` | `work_order_projection.ideal_cycle_sec` | no | no | yes | yes | no | `15` | Turetilmis/uyumluluk |
| `planned_duration_ms` | Planlanan sure ms | Planlanan is emri suresi ms | duration_ms | no | runtime_projection | `7_Is_Emirleri.planned_duration_ms` | `work_order_projection.planned_duration_ms` | no | no | yes | yes | yes | `150000` | ms-first |
| `planned_duration_sec` | Planlanan sure saniye | Planlanan is emri suresi saniye | duration_sec | no | runtime_projection | `7_Is_Emirleri.planned_duration_sec` | `work_order_projection.planned_duration_sec` | no | no | yes | yes | no | `150` | Turetilmis/uyumluluk |
| `runtime_ms` | Runtime ms | Is emri runtime suresi ms | duration_ms | no | runtime_projection | `7_Is_Emirleri.runtime_ms` | `work_order_projection.runtime_ms` | no | no | yes | yes | yes | `120000` | ms-first |
| `runtime_sec` | Runtime saniye | Is emri runtime suresi saniye | duration_sec | no | runtime_projection | `7_Is_Emirleri.runtime_sec` | `work_order_projection.runtime_sec` | no | no | yes | yes | no | `120` | Turetilmis/uyumluluk |
| `unplanned_downtime_ms` | Plansiz durus ms | Is emri plansiz durus suresi ms | duration_ms | no | runtime_projection | `7_Is_Emirleri.unplanned_downtime_ms` | `work_order_projection.unplanned_downtime_ms` | no | no | yes | yes | yes | `30000` | ms-first |
| `unplanned_downtime_sec` | Plansiz durus saniye | Plansiz durus suresi saniye | duration_sec | no | runtime_projection | `7_Is_Emirleri.unplanned_downtime_sec` | `work_order_projection.unplanned_downtime_sec` | no | no | yes | yes | no | `30` | Turetilmis/uyumluluk |
| `availability_pct` | Availability yuzde | Is emri availability ozeti | decimal | no | runtime_projection | `7_Is_Emirleri.availability_pct` | `work_order_projection.availability_pct` | no | no | yes | yes | yes | `83.3` | Calculated projection |
| `performance_pct` | Performance yuzde | Is emri performance ozeti | decimal | no | runtime_projection | `7_Is_Emirleri.performance_pct` | `work_order_projection.performance_pct` | no | no | yes | yes | yes | `75.0` | Calculated projection |
| `quality_pct` | Quality yuzde | Is emri quality ozeti | decimal | no | runtime_projection | `7_Is_Emirleri.quality_pct` | `work_order_projection.quality_pct` | no | no | yes | yes | yes | `98.0` | Calculated projection |
| `oee_pct` | OEE yuzde | Is emri OEE ozeti | decimal | no | runtime_projection | `7_Is_Emirleri.oee_pct` | `work_order_projection.oee_pct` | no | no | yes | yes | yes | `61.7` | Calculated projection |
| `started_by` | Baslatan operator | Is emrini baslatan operator kod/id | string | no | runtime_projection | `7_Is_Emirleri.started_by` | `work_order_projection.started_by` | no | yes | yes | yes | yes | `OP-001` | `operators` master adayi |
| `started_by_name` | Baslatan operator adi | Baslatan operator gorunum adi | string | no | runtime_projection | `7_Is_Emirleri.started_by_name` | `work_order_projection.started_by_name` | no | no | yes | yes | no | `Operator 1` | Display snapshot |
| `transition_reason` | Gecis nedeni | Is emri transition/aciklama nedeni | text | no | runtime_projection | `7_Is_Emirleri.transition_reason` | `work_order_projection.transition_reason` | no | no | yes | yes | yes | `operator_start` | Projection note |
| `notes` | Notlar | Is emri projection notlari | text | no | runtime_projection | `7_Is_Emirleri.notes` | `work_order_projection.notes` | no | no | yes | yes | no | `Imported` | Serbest metin |

### `8_Depo_Stok`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `inventory_record_id` | Stok projection no | Workbook inventory projection satir kimligi | integer | yes | runtime_projection | `8_Depo_Stok.inventory_record_id` | `operational_inventory_projection.inventory_record_id` | yes | no | yes | yes | yes | `1` | Projection id |
| `match_key` | Eslesme anahtari | Operasyonel inventory match key | string | yes | runtime_projection | `8_Depo_Stok.match_key` | `operational_inventory_projection.match_key` | yes | no | yes | yes | yes | `BOX-RED:red` | Runtime/projection key |
| `product_code` | Urun kodu | MES product code referansi | string | conditional | runtime_projection | `8_Depo_Stok.product_code` | `operational_inventory_projection.product_code` | no | yes | yes | yes | yes | `BOX-RED` | `products` lookup adayi |
| `stock_code` | Stok kodu | Stok/product code referansi | string | yes | runtime_projection | `8_Depo_Stok.stock_code` | `operational_inventory_projection.stock_code` | no | yes | yes | yes | yes | `BOX-RED` | `products` lookup adayi |
| `stock_name` | Stok adi | Stok display adi | string | no | runtime_projection | `8_Depo_Stok.stock_name` | `operational_inventory_projection.stock_name` | no | no | yes | yes | no | `Red Box` | Display snapshot |
| `color_code` | Renk kodu | Inventory renk kodu | string | conditional | runtime_projection | `8_Depo_Stok.color_code` | `operational_inventory_projection.color_code` | no | yes | yes | yes | yes | `red` | `colors` lookup |
| `quantity` | Miktar | MES operasyonel stok miktari | integer | yes | runtime_projection | `8_Depo_Stok.quantity` | `operational_inventory_projection.quantity` | no | no | yes | yes | yes | `12` | Resmi ERP stok defteri degildir |
| `last_updated_at` | Son guncelleme | Inventory projection son guncelleme zamani | datetime_iso | yes | runtime_projection | `8_Depo_Stok.last_updated_at` | `operational_inventory_projection.last_updated_at` | no | no | yes | yes | yes | `2026-04-02T08:30:00Z` | ISO datetime |
| `last_source` | Son kaynak | Son inventory update kaynagi | string | no | runtime_projection | `8_Depo_Stok.last_source` | `operational_inventory_projection.last_source` | no | yes | yes | yes | yes | `ferp_import` | Source/action lookup adayi |
| `source_file` | Kaynak dosya | Inventory import/projection kaynak dosyasi | string | no | runtime_projection | `8_Depo_Stok.source_file` | `operational_inventory_projection.source_file` | no | no | yes | yes | yes | `ferp_work_orders.json` | Provenance |
| `notes` | Notlar | Inventory projection notlari | text | no | runtime_projection | `8_Depo_Stok.notes` | `operational_inventory_projection.notes` | no | no | yes | yes | no | `Operational stock` | Serbest metin |

### `9_Bakim_Kayitlari`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `maintenance_record_id` | Bakim kayit no | Workbook maintenance satir kimligi | integer | yes | audit_event | `9_Bakim_Kayitlari.maintenance_record_id` | `maintenance_step_records.maintenance_record_id` | yes | no | no | yes | yes | `1` | Projection row id |
| `maintenance_row_key` | Bakim satir anahtari | Session + step bazli satir anahtari | string | yes | audit_event | `9_Bakim_Kayitlari.maintenance_row_key` | `maintenance_step_records.maintenance_row_key` | yes | no | no | yes | yes | `MNT-1:opening_safety` | Projection/detail key |
| `session_id` | Bakim oturum no | Bakim session referansi | string | yes | audit_event | `9_Bakim_Kayitlari.session_id` | `maintenance_step_records.session_id` | no | no | no | yes | yes | `MNT-001` | Maintenance session id |
| `phase_code` | Faz kodu | Bakim faz kodu | string | yes | audit_event | `9_Bakim_Kayitlari.phase_code` | `maintenance_step_records.phase_code` | no | yes | no | yes | yes | `opening` | Lookup/enum adayi |
| `phase_tr` | Faz etiketi | Turkce faz label snapshot'i | string | no | audit_event | `9_Bakim_Kayitlari.phase_tr` | `maintenance_step_records.phase_tr` | no | no | no | yes | no | `Acilis` | Canonical kod degil |
| `step_code` | Adim kodu | Maintenance checklist step kodu | string | yes | audit_event | `9_Bakim_Kayitlari.step_code` | `maintenance_step_records.step_code` | no | yes | no | yes | yes | `opening_safety` | `maintenance_steps` lookup |
| `step_label_tr` | Adim etiketi | Turkce maintenance step label snapshot'i | string | no | audit_event | `9_Bakim_Kayitlari.step_label_tr` | `maintenance_step_records.step_label_tr` | no | no | no | yes | no | `Guvenlik kontrolu` | Canonical kod degil |
| `required_flag` | Zorunlu flag | Step zorunlu mu | boolean | yes | audit_event | `9_Bakim_Kayitlari.required_flag` | `maintenance_step_records.required_flag` | no | no | no | yes | yes | `1` | Checklist state |
| `completed_flag` | Tamamlandi flag | Step tamamlandi mi | boolean | yes | audit_event | `9_Bakim_Kayitlari.completed_flag` | `maintenance_step_records.completed_flag` | no | no | no | yes | yes | `1` | Checklist state |
| `completed_at` | Tamamlanma zamani | Step tamamlanma zamani | datetime_iso | conditional | audit_event | `9_Bakim_Kayitlari.completed_at` | `maintenance_step_records.completed_at` | no | no | no | yes | yes | `2026-04-02T07:55:00Z` | Bos olabilir |
| `session_started_at` | Oturum baslama | Maintenance session baslama zamani | datetime_iso | yes | audit_event | `9_Bakim_Kayitlari.session_started_at` | `maintenance_step_records.session_started_at` | no | no | no | yes | yes | `2026-04-02T07:50:00Z` | ISO datetime |
| `session_ended_at` | Oturum bitis | Maintenance session bitis zamani | datetime_iso | conditional | audit_event | `9_Bakim_Kayitlari.session_ended_at` | `maintenance_step_records.session_ended_at` | no | no | no | yes | yes | `2026-04-02T08:00:00Z` | Acik session'da bos |
| `duration_ms` | Sure ms | Bakim/step suresi ms | duration_ms | no | audit_event | `9_Bakim_Kayitlari.duration_ms` | `maintenance_step_records.duration_ms` | no | no | no | yes | yes | `600000` | ms-first |
| `duration_sec` | Sure saniye | Bakim/step suresi saniye | duration_sec | no | audit_event | `9_Bakim_Kayitlari.duration_sec` | `maintenance_step_records.duration_sec` | no | no | no | yes | no | `600` | Turetilmis/uyumluluk |
| `shift_code` | Vardiya kodu | Bakim anindaki vardiya kodu | string | conditional | audit_event | `9_Bakim_Kayitlari.shift_code` | `maintenance_step_records.shift_code` | no | yes | no | yes | yes | `SHIFT-A` | `shifts` lookup |
| `device_id` | Cihaz id | Bakim yapilan cihaz referansi | string | conditional | audit_event | `9_Bakim_Kayitlari.device_id` | `maintenance_step_records.device_id` | no | no | no | yes | yes | `robot-arm-1` | Device master adayi |
| `device_name` | Cihaz adi | Cihaz display adi | string | no | audit_event | `9_Bakim_Kayitlari.device_name` | `maintenance_step_records.device_name` | no | no | no | yes | no | `Robot Arm` | Display snapshot |
| `device_role` | Cihaz rolu | Cihaz rol kodu | string | no | audit_event | `9_Bakim_Kayitlari.device_role` | `maintenance_step_records.device_role` | no | yes | no | yes | yes | `robot` | Lookup/enum adayi |
| `bound_station_id` | Bagli istasyon | Cihazin bagli oldugu istasyon | string | conditional | audit_event | `9_Bakim_Kayitlari.bound_station_id` | `maintenance_step_records.bound_station_id` | no | yes | no | yes | yes | `station2` | `stations` lookup |
| `operator_id` | Operator id | Bakim operator referansi | string | conditional | audit_event | `9_Bakim_Kayitlari.operator_id` | `maintenance_step_records.operator_id` | no | yes | no | yes | yes | `OP-001` | `operators` master |
| `operator_code` | Operator kodu | Operator kod snapshot'i | string | conditional | audit_event | `9_Bakim_Kayitlari.operator_code` | `maintenance_step_records.operator_code` | no | yes | no | yes | yes | `OP-001` | Operator lookup/master kodu |
| `operator_name` | Operator adi | Operator display adi | string | no | audit_event | `9_Bakim_Kayitlari.operator_name` | `maintenance_step_records.operator_name` | no | no | no | yes | no | `Operator 1` | Display snapshot |
| `note` | Not | Bakim step/session notu | text | no | audit_event | `9_Bakim_Kayitlari.note` | `maintenance_step_records.note` | no | no | no | yes | no | `Checked` | Serbest metin |

### `99_Raw_Logs`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `raw_log_id` | Raw log no | Raw archive satir kimligi | integer | yes | raw_archive | `99_Raw_Logs.raw_log_id` | `raw_event_archive.raw_log_id` | yes | no | no | yes | yes | `1` | Normal raporlama disi |
| `logged_at` | Log zamani | Raw payload kayit zamani | datetime_iso | yes | raw_archive | `99_Raw_Logs.logged_at` | `raw_event_archive.logged_at` | no | no | no | yes | yes | `2026-04-02T10:15:25Z` | ISO datetime |
| `source_topic` | Kaynak topic | Raw payload kaynak topic/kanal | string | no | raw_archive | `99_Raw_Logs.source_topic` | `raw_event_archive.source_topic` | no | yes | no | yes | yes | `mega/logs` | `sources` veya topic lookup adayi |
| `source_code` | Kaynak kodu | Raw payload source code | string | yes | raw_archive | `99_Raw_Logs.source_code` | `raw_event_archive.source_code` | no | yes | no | yes | yes | `mega` | `sources` lookup |
| `parsed_flag` | Parse edildi flag'i | Raw payload parse edilebildi mi | boolean | yes | raw_archive | `99_Raw_Logs.parsed_flag` | `raw_event_archive.parsed_flag` | no | no | no | yes | yes | `1` | Debug/audit archive |
| `event_type_code` | Olay tipi kodu | Parse sonucu event type kodu | string | conditional | raw_archive | `99_Raw_Logs.event_type_code` | `raw_event_archive.event_type_code` | no | yes | no | yes | yes | `measurement_decision` | `event_types` lookup |
| `item_id` | Urun iz kimligi | Raw payload item referansi | string | conditional | raw_archive | `99_Raw_Logs.item_id` | `raw_event_archive.item_id` | no | no | no | yes | yes | `42` | Normal raporlama icin birincil kaynak degil |
| `measure_id` | Olcum kimligi | Raw payload measurement referansi | string | conditional | raw_archive | `99_Raw_Logs.measure_id` | `raw_event_archive.measure_id` | no | no | no | yes | yes | `8` | Debug/backfill dogrulama |
| `color_code` | Renk kodu | Raw payload normalize color code | string | conditional | raw_archive | `99_Raw_Logs.color_code` | `raw_event_archive.color_code` | no | yes | no | yes | yes | `red` | `colors` lookup |
| `station_id` | Istasyon id | Raw payload station referansi | string | conditional | raw_archive | `99_Raw_Logs.station_id` | `raw_event_archive.station_id` | no | yes | no | yes | yes | `station1` | `stations` lookup |
| `oee_scope` | OEE kapsami | Raw payload OEE scope degeri | string | no | raw_archive | `99_Raw_Logs.oee_scope` | `raw_event_archive.oee_scope` | no | yes | no | yes | yes | `station1_component_transfer` | Debug/audit archive |
| `package_cycle_id` | Paket cevrim id | Raw payload package cycle referansi | string | no | raw_archive | `99_Raw_Logs.package_cycle_id` | `raw_event_archive.package_cycle_id` | no | no | no | yes | yes | `PKG-1` | Normal raporlama kaynagi degil |
| `notes` | Notlar | Raw archive notlari | text | no | raw_archive | `99_Raw_Logs.notes` | `raw_event_archive.notes` | no | no | no | yes | no | `parsed` | Debug note |
| `raw_payload` | Ham payload | Parse edilmeden saklanan payload | text | yes | raw_archive | `99_Raw_Logs.raw_payload` | `raw_event_archive.raw_payload` | no | no | no | yes | yes | `<raw_payload>` | Normal reporting disi raw archive |

## 6. Anahtar ve Referans Alanlari

| Alan grubu | Alanlar | Kural |
| --- | --- | --- |
| Workbook row id | `log_event_id`, `measurement_row_id`, `production_record_id`, `oee_snapshot_id`, `vision_event_id`, `work_order_record_id`, `inventory_record_id`, `maintenance_record_id`, `raw_log_id` | Projection/audit satir kimligidir; canonical domain id yerine gecmez |
| Domain referans | `item_id`, `measure_id`, `fault_id`, `order_id`, `session_id`, `match_key` | Backfill ve traceability icin kritik referanslardir |
| Event referans | `measurement_log_event_id`, `queue_event_log_id`, `completion_event_log_id`, `event_log_id` | Event/projection iliskisini kurar |
| Master/lookup referans | `source_id`, `color_id`, `decision_source_id`, `line_id`, `station_id`, `operator_id`, `shift_code` | Ilgili lookup/master tabloyla dogrulanmalidir |

## 7. Timestamp ve Sure Alanlari

Timestamp alanlari ISO datetime hedefiyle belgelenir:

- `event_time_text`
- `measured_at`
- `detected_at`
- `completed_at`
- `override_applied_at`
- `early_pick_request_sent_at`
- `early_pick_accepted_at`
- `final_color_frozen_at`
- `snapshot_time`
- `event_time`
- `vision_observed_at`
- `vision_published_at`
- `vision_received_at`
- `queued_at`
- `started_at`
- `ended_at`
- `last_updated_at`
- `session_started_at`
- `session_ended_at`
- `logged_at`

Sure kurali:

- `*_ms` alanlari birincil sure alanidir.
- `*_sec` alanlari turetilmis/uyumluluk alanidir.
- Backfill sirasinda `*_ms` varken `*_sec` canonical hesap kaynagi yapilmamalidir.

## 8. Lookup / Enum Alanlari

| Alan grubu | Alanlar | Lookup/master hedefi |
| --- | --- | --- |
| Source | `source_id`, `source_code`, `source_topic`, `last_source` | `sources` |
| Event type | `event_type_id`, `event_type_code`, `event_type` | `event_types` |
| Color | `color_id`, `color_code`, `final_color_code`, `sensor_color_code`, `vision_color_code`, `product_color` | `colors` |
| Decision source | `decision_source_id`, `decision_source_code`, `override_source_code` | `decision_sources` |
| Mega state | `mega_state_id`, `mega_state_code` | `mega_states` |
| Work order status | `status_code` in `7_Is_Emirleri` | `work_order_statuses` |
| Quality | `final_quality_code`, `good_qty`, `rework_qty`, `scrap_qty` | `quality_codes` |
| Fault | `fault_type_code`, `fault_category` | `fault_types` |
| Maintenance | `phase_code`, `step_code`, `device_role` | `maintenance_steps` and related lookups |
| Correlation/finalization | `correlation_status`, `finalization_reason`, `confidence_tier`, `pick_trigger_source` | domain lookup candidates |

## 9. Runtime Projection Alanlari

Runtime projection sheet'leri:

- `7_Is_Emirleri`
- `8_Depo_Stok`

Kural:

- Bu sheet'ler workbook icinde son gorunum/projection'dir.
- Canonical is emri ve resmi stok modeli yerine gecmez.
- `work_order_record_id` ve `inventory_record_id` projection id'dir.
- `order_id`, canonical work order modeline aday domain referanstir, ancak workbook projection'i tek kaynak yapilmamalidir.

## 10. Audit / Event Alanlari

Audit/event sheet'leri:

- `1_Olay_Logu`
- `2_Olcumler`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `6_Vision`
- `9_Bakim_Kayitlari`

Kural:

- Bu sheet'ler backfill ve raporlama icin degerlidir.
- Append veya targeted update davranisi olabilir; workbook yine transactional DB degildir.
- `raw_line` ve raw referanslar debug/backfill dogrulama icindir.

## 11. Calculated Snapshot Alanlari

`5_OEE_Anliklari` calculated OEE snapshot/time-series yapisidir.

Kritik alanlar:

- `oee_snapshot_id`
- `snapshot_time`
- `sample_cycle_tag`
- `oee`
- `availability`
- `performance`
- `quality`
- renk bazli good/rework/scrap count alanlari

Kural:

- `sample_cycle_tag` event id veya cycle id degildir.
- `event_log_id` bos olabilir.
- OEE snapshot sheet'i raw event store gibi replay edilmemelidir.

## 12. Raw Archive Alanlari

`99_Raw_Logs` debug/audit/archive kaynagidir.

Kural:

- Normal raporlama DB'sine dogrudan karistirilmamalidir.
- `raw_event_archive` gibi ayri archive katmani adayi olarak dusunulmelidir.
- Backfill sirasinda dogrulama, parse kontrolu veya eksik event inceleme icin kullanilabilir.

## 13. Needs Review Alanlarinin Veri Sozlugune Aktarimi

| Alan grubu | Aktarim karari |
| --- | --- |
| `source_log_file` | Resolved; measurement provenance olarak `measurements.source_log_file` icinde tutulabilir |
| `search_hint*` | Partially resolved; sensor algorithm context olarak `measurement_debug_metrics` icinde tutulmali |
| `core_n`, `obj_n`, `median_nearest`, `med_d_*`, `vote_*`, `tot_*` | Partially resolved; sensor metrics olarak `measurement_metrics` veya debug detail icinde tutulmali |
| `score_nearest`, `vote_cal`, `tot_cal` | Unresolved; alan silinmez, veri tipi daraltilmaz, firmware kontratiyla netlestirilir |
| `sample_cycle_tag` | Resolved; OEE snapshot source/sample etiketi |
| `finalization_reason` | Resolved; production finalization decision reason, kalite kodu degil |

## 14. Backfill / Replay Icin Kritik Alanlar

| Kategori | Kritik alanlar |
| --- | --- |
| Event sirasi | `event_time_text`, `log_event_id`, `event_type_code`, `source_code` |
| Measurement | `measure_id`, `item_id`, `measured_at`, `final_color_code`, `decision_source_code`, `raw_line` |
| Production | `item_id`, `measure_id`, `completed_at`, `final_quality_code`, `finalization_reason`, `station_id`, `oee_scope` |
| Fault | `fault_id`, `fault_type_code`, `started_at`, `ended_at`, `duration_ms` |
| OEE snapshot | `snapshot_time`, `oee`, `availability`, `performance`, `quality`, `sample_cycle_tag` |
| Vision | `vision_event_id`, `vision_track_id`, `color_code`, `confidence`, `correlation_status` |
| Work order projection | `order_id`, `status_code`, `target_qty`, `fulfilled_qty`, `started_at`, `completed_at` |
| Inventory projection | `match_key`, `stock_code`, `color_code`, `quantity`, `last_updated_at` |
| Maintenance | `session_id`, `phase_code`, `step_code`, `completed_at`, `duration_ms` |
| Raw archive | `logged_at`, `source_topic`, `parsed_flag`, `raw_payload` |

## 15. Data Quality ve Validation Kurallari

| Kural | Uygulama |
| --- | --- |
| Required alanlar bos kalmamali | `required=yes` satirlari import/backfill validasyonunda kontrol edilmeli |
| Conditional alanlar baglama gore kontrol edilmeli | Event tipi veya status gerektiriyorsa bos kalmamali |
| Lookup alanlari eslesmeli | `colors`, `sources`, `event_types`, `decision_sources`, `stations`, `operators`, `shifts` ile dogrulanmali |
| Timestamp ISO hedeflenmeli | Timezone bilgisi kaybedilmemeli |
| Projection ID ayrimi korunmali | Workbook row id canonical domain id yerine gecmemeli |
| Sensor debug metrikleri zorunlu yapilmamali | Eksik debug metric backfill'i bloke etmemeli |
| `*_tr` alanlari canonical sayilmamali | UI/audit label snapshot olarak kalmali |
| Raw archive ayri tutulmali | Normal raporlama modeline dogrudan alinmamali |

## 16. Riskler ve Koruyucu Kurallar

| Risk | Etki | Koruyucu kural |
| --- | --- | --- |
| Workbook transactional DB gibi kullanilir | Runtime state ve audit/projection siniri bozulur | Workbook sadece audit/projection/backfill/replay kaynagi olarak kullanilmali |
| Projection ID canonical ID sanilir | DB tasariminda yanlis primary key secilir | Projection id ve domain id ayrimi notlarda korunmali |
| Sensor debug metrikleri domain modele karisir | Ana MES modeli sensor firmware'e asiri bagimli olur | `measurement_metrics` ve `measurement_debug_metrics` ayrimi yapilmali |
| `sample_cycle_tag` event id gibi kullanilir | OEE replay ve event iliskileri hatali kurulur | Snapshot source/sample etiketi olarak belgelenmeli |
| `finalization_reason` kalite kodu sanilir | Kalite sonucu ve karar gerekcesi karisir | `final_quality_code` ile ayrimi korunmali |
| Raw logs raporlama DB'sine tasinir | Gurultu, performans ve semantik kirlilik olusur | `raw_event_archive` ayri tutulmali |
| `*_sec` canonical sure olur | Sure hesaplari tutarsizlasir | `*_ms` birincil, `*_sec` turetilmis kabul edilmeli |

## 17. Uygulanacak Sonraki 5 Is

1. Bu veri sozlugunu `docs/workbook-field-inventory.md` ile capraz kontrol ederek her sheet icin kolon sayisi uyumunu dogrula.
2. `score_nearest`, `vote_cal`, `tot_cal`, `search_hint_*`, `core_str_*` ve `med_obj` alanlari icin sensor firmware payload kontratini netlestir.
3. Lookup/enum adaylari icin `colors`, `sources`, `event_types`, `decision_sources`, `work_order_statuses`, `quality_codes` ve `production_finalization_reasons` sozluklerini dokumante et.
4. Backfill validasyon planinda required, conditional, lookup ve timestamp kontrollerini ayri seviyeler olarak tanimla.
5. SQL'e gecis oncesi workbook yazimini bozmadan shadow/read-model icin field mapping kontrol listesi hazirla.
