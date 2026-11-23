# Workbook Field Inventory

## 1. Amac

Bu dokuman, gunluk MES workbook sheet'lerinde fiilen kullanilan kolonlari sheet bazinda envanterler. Kaynak kolon listeleri `mes_web/excel_runtime.py` icindeki sabitlerden alinmistir.

Bu dokuman kod, migration, SQL DDL veya Excel sablonu degisikligi degildir. Amac, mevcut kolon adlarini degistirmeden alan sozlugu calismasina hazir bir envanter olusturmaktir.

Korunan kararlar:

- Gunluk workbook canli transactional DB degildir.
- Workbook audit/projection/backfill/replay kaynagidir.
- `7_Is_Emirleri` workbook icinde projection'dir; canonical is emri modeli ayri tasarlanir.
- `5_OEE_Anliklari` event degil, calculated OEE snapshot/time-series yapisidir.
- `99_Raw_Logs` normal raporlama DB'si degil; debug/audit/archive adayidir.

## 2. Kaynak Dosyalar

- `mes_web/excel_runtime.py`
- `docs/workbook-schema.md`
- `docs/data-dictionary-plan.md`

Kullanilan kolon listeleri:

- `EVENT_LOG_COLUMNS`
- `MEASUREMENT_COLUMNS`
- `COMPLETED_COLUMNS`
- `OEE_SNAPSHOT_COLUMNS`
- `VISION_COLUMNS`
- `RAW_LOG_COLUMNS`
- `WORK_ORDER_COLUMNS`
- `INVENTORY_COLUMNS`
- `FAULT_COLUMNS`
- `MAINTENANCE_COLUMNS`
- `SHEET_COLUMNS`

## 3. Sheet -> Kolon Listesi Ozeti

| Sheet | Kolon sabiti | Kolon sayisi | Siniflandirma |
| --- | --- | --- | --- |
| `1_Olay_Logu` | `EVENT_LOG_COLUMNS` | 27 | normalized audit/event projection |
| `2_Olcumler` | `MEASUREMENT_COLUMNS` | 52 | measurement audit/projection |
| `3_Arizalar` | `FAULT_COLUMNS` | 20 | fault audit/projection |
| `4_Uretim_Tamamlanan` | `COMPLETED_COLUMNS` | 37 | production completion audit/projection |
| `5_OEE_Anliklari` | `OEE_SNAPSHOT_COLUMNS` | 23 | calculated OEE snapshot |
| `6_Vision` | `VISION_COLUMNS` | 25 | vision observation audit |
| `7_Is_Emirleri` | `WORK_ORDER_COLUMNS` | 35 | work order projection |
| `8_Depo_Stok` | `INVENTORY_COLUMNS` | 11 | operational inventory projection |
| `9_Bakim_Kayitlari` | `MAINTENANCE_COLUMNS` | 23 | maintenance audit/projection |
| `99_Raw_Logs` | `RAW_LOG_COLUMNS` | 14 | raw log archive/debug |

## 4. Sheet Bazli Kolon Envanteri

### `1_Olay_Logu`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `1_Olay_Logu` | `log_event_id` | key | integer | audit_event | `event_log` | yes | no | no | audit row id |
| `1_Olay_Logu` | `event_time_text` | timestamp | datetime_iso | audit_event | `event_log` | no | no | yes | event time |
| `1_Olay_Logu` | `source_id` | lookup_id | integer | audit_event | `event_log` | yes | yes | no | `sources` lookup |
| `1_Olay_Logu` | `source_code` | lookup_code | string | audit_event | `event_log` | no | yes | no | `sources` lookup |
| `1_Olay_Logu` | `event_type_id` | lookup_id | integer | audit_event | `event_log` | yes | yes | no | `event_types` lookup |
| `1_Olay_Logu` | `event_type_code` | lookup_code | string | audit_event | `event_log` | no | yes | no | `event_types` lookup |
| `1_Olay_Logu` | `event_summary_tr` | label | text | audit_event | `event_log` | no | no | no | Turkish event summary |
| `1_Olay_Logu` | `item_id` | reference | string | audit_event | `event_log` | yes | no | no | item trace reference |
| `1_Olay_Logu` | `measure_id` | reference | string | audit_event | `event_log` | yes | no | no | measurement reference |
| `1_Olay_Logu` | `fault_id` | reference | string | audit_event | `event_log` | yes | no | no | fault reference |
| `1_Olay_Logu` | `oee_snapshot_id` | reference | integer | audit_event | `event_log` | yes | no | no | OEE snapshot reference |
| `1_Olay_Logu` | `vision_event_id` | reference | integer | audit_event | `event_log` | yes | no | no | vision reference |
| `1_Olay_Logu` | `line_id` | lookup_id | string | audit_event | `event_log` | yes | yes | no | `lines` lookup |
| `1_Olay_Logu` | `station_id` | lookup_id | string | audit_event | `event_log` | yes | yes | no | `stations` lookup |
| `1_Olay_Logu` | `oee_scope` | enum | string | audit_event | `event_log` | no | yes | no | OEE scope lookup candidate |
| `1_Olay_Logu` | `package_cycle_id` | reference | string | audit_event | `event_log` | yes | no | no | station2/package cycle reference |
| `1_Olay_Logu` | `color_id` | lookup_id | integer | audit_event | `event_log` | yes | yes | no | `colors` lookup |
| `1_Olay_Logu` | `color_code` | lookup_code | string | audit_event | `event_log` | no | yes | no | `colors` lookup |
| `1_Olay_Logu` | `decision_source_id` | lookup_id | integer | audit_event | `event_log` | yes | yes | no | `decision_sources` lookup |
| `1_Olay_Logu` | `decision_source_code` | lookup_code | string | audit_event | `event_log` | no | yes | no | `decision_sources` lookup |
| `1_Olay_Logu` | `mega_state_id` | lookup_id | integer | audit_event | `event_log` | yes | yes | no | `mega_states` lookup |
| `1_Olay_Logu` | `mega_state_code` | lookup_code | string | audit_event | `event_log` | no | yes | no | `mega_states` lookup |
| `1_Olay_Logu` | `queue_depth` | metric | integer | audit_event | `event_log` | no | no | no | queue metric |
| `1_Olay_Logu` | `review_required` | flag | boolean | audit_event | `event_log` | no | no | no | review flag |
| `1_Olay_Logu` | `travel_ms` | duration | duration_ms | audit_event | `event_log` | no | no | no | ms-first duration |
| `1_Olay_Logu` | `notes` | note | text | audit_event | `event_log` | no | no | no | free-form note |
| `1_Olay_Logu` | `raw_line` | raw_reference | text | audit_event | `event_log` | no | no | no | raw source line |

### `2_Olcumler`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `2_Olcumler` | `measurement_row_id` | key | integer | audit_event | `measurements` | yes | no | no | measurement row id |
| `2_Olcumler` | `measure_id` | key | string | audit_event | `measurements` | yes | no | no | measurement id |
| `2_Olcumler` | `item_id` | reference | string | audit_event | `measurements` | yes | no | no | item reference |
| `2_Olcumler` | `measured_at` | timestamp | datetime_iso | audit_event | `measurements` | no | no | yes | measurement time |
| `2_Olcumler` | `measurement_log_event_id` | reference | integer | audit_event | `measurements` | yes | no | no | event_log reference |
| `2_Olcumler` | `source_log_file` | source_reference | string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `final_color_id` | lookup_id | integer | audit_event | `measurements` | yes | yes | no | `colors` lookup |
| `2_Olcumler` | `final_color_code` | lookup_code | string | audit_event | `measurements` | no | yes | no | `colors` lookup |
| `2_Olcumler` | `final_color_raw` | raw_value | string | audit_event | `measurements` | no | no | no | raw color token |
| `2_Olcumler` | `decision_source_id` | lookup_id | integer | audit_event | `measurements` | yes | yes | no | `decision_sources` lookup |
| `2_Olcumler` | `decision_source_code` | lookup_code | string | audit_event | `measurements` | no | yes | no | `decision_sources` lookup |
| `2_Olcumler` | `search_hint` | measurement_context | string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `search_hint_win` | measurement_context | string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `search_hint_second` | measurement_context | string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `search_hint_strong` | measurement_context | string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `search_hint_fallback_allowed` | flag | boolean | audit_event | `measurements` | no | no | no | fallback flag |
| `2_Olcumler` | `review_required` | flag | boolean | audit_event | `measurements` | no | no | no | review flag |
| `2_Olcumler` | `core_used` | flag | boolean | audit_event | `measurements` | no | no | no | measurement algorithm flag |
| `2_Olcumler` | `core_n` | metric | integer | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `obj_n` | metric | integer | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `median_nearest` | metric | decimal_or_string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `score_nearest` | metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `med_r` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | median red metric |
| `2_Olcumler` | `med_g` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | median green metric |
| `2_Olcumler` | `med_b` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | median blue metric |
| `2_Olcumler` | `med_d_r` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `med_d_y` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `med_d_b` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `med_d_x` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `x_r` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `x_g` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `x_b` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `med_obj` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `confidence` | metric | decimal | audit_event | `measurements` | no | no | no | confidence score |
| `2_Olcumler` | `core_str_min` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `core_str_max` | sensor_metric | decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_win` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_second` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_classified` | sensor_metric | string | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_x` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_r` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_y` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_b` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `vote_cal` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `tot_r` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | total red metric |
| `2_Olcumler` | `tot_y` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | total yellow metric |
| `2_Olcumler` | `tot_b` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | total blue metric |
| `2_Olcumler` | `tot_x` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `tot_cal` | sensor_metric | integer_or_decimal | audit_event | `measurements` | no | no | no | needs_review |
| `2_Olcumler` | `measurement_error_flag` | flag | boolean | audit_event | `measurements` | no | no | no | error flag |
| `2_Olcumler` | `measurement_error_reason` | error_reason | text | audit_event | `measurements` | no | no | no | error detail |
| `2_Olcumler` | `raw_line` | raw_reference | text | audit_event | `measurements` | no | no | no | raw source line |

### `3_Arizalar`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `3_Arizalar` | `fault_record_id` | key | integer | audit_event | `fault_events` | yes | no | no | fault row id |
| `3_Arizalar` | `fault_id` | key | string | audit_event | `fault_events` | yes | no | no | fault session id |
| `3_Arizalar` | `status_code` | lookup_code | string | audit_event | `fault_events` | no | yes | no | fault status lookup candidate |
| `3_Arizalar` | `status_tr` | label | string | audit_event | `fault_events` | no | no | no | Turkish status |
| `3_Arizalar` | `fault_type_code` | lookup_code | string | audit_event | `fault_events` | no | yes | no | `fault_types` lookup |
| `3_Arizalar` | `fault_category` | lookup_or_label | string | audit_event | `fault_events` | no | yes | no | category lookup candidate |
| `3_Arizalar` | `fault_reason_tr` | label | text | audit_event | `fault_events` | no | no | no | Turkish reason |
| `3_Arizalar` | `started_at` | timestamp | datetime_iso | audit_event | `fault_events` | no | no | yes | fault start |
| `3_Arizalar` | `ended_at` | timestamp | datetime_iso | audit_event | `fault_events` | no | no | yes | fault end |
| `3_Arizalar` | `duration_ms` | duration | duration_ms | audit_event | `fault_events` | no | no | no | ms-first |
| `3_Arizalar` | `duration_sec` | duration | duration_sec | audit_event | `fault_events` | no | no | no | derived/compatibility |
| `3_Arizalar` | `source_code` | lookup_code | string | audit_event | `fault_events` | no | yes | no | `sources` lookup |
| `3_Arizalar` | `device_id` | reference | string | audit_event | `fault_events` | yes | no | no | device reference |
| `3_Arizalar` | `device_name` | label | string | audit_event | `fault_events` | no | no | no | device display snapshot |
| `3_Arizalar` | `bound_station_id` | lookup_id | string | audit_event | `fault_events` | yes | yes | no | station reference |
| `3_Arizalar` | `operator_id` | lookup_id | string | audit_event | `fault_events` | yes | yes | no | operator reference |
| `3_Arizalar` | `operator_code` | lookup_code | string | audit_event | `fault_events` | no | yes | no | operator code snapshot |
| `3_Arizalar` | `operator_name` | label | string | audit_event | `fault_events` | no | no | no | operator display snapshot |
| `3_Arizalar` | `shift_code` | lookup_code | string | audit_event | `fault_events` | no | yes | no | `shifts` lookup |
| `3_Arizalar` | `notes` | note | text | audit_event | `fault_events` | no | no | no | free-form note |

### `4_Uretim_Tamamlanan`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `4_Uretim_Tamamlanan` | `production_record_id` | key | integer | audit_event | `production_completions` | yes | no | no | production row id |
| `4_Uretim_Tamamlanan` | `item_id` | key | string | audit_event | `production_completions` | yes | no | no | item trace id |
| `4_Uretim_Tamamlanan` | `measure_id` | reference | string | audit_event | `production_completions` | yes | no | no | measurement reference |
| `4_Uretim_Tamamlanan` | `queue_event_log_id` | reference | integer | audit_event | `production_completions` | yes | no | no | event_log reference |
| `4_Uretim_Tamamlanan` | `completion_event_log_id` | reference | integer | audit_event | `production_completions` | yes | no | no | event_log reference |
| `4_Uretim_Tamamlanan` | `detected_at` | timestamp | datetime_iso | audit_event | `production_completions` | no | no | yes | detection time |
| `4_Uretim_Tamamlanan` | `completed_at` | timestamp | datetime_iso | audit_event | `production_completions` | no | no | yes | completion time |
| `4_Uretim_Tamamlanan` | `color_id` | lookup_id | integer | audit_event | `production_completions` | yes | yes | no | `colors` lookup |
| `4_Uretim_Tamamlanan` | `color_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | `colors` lookup |
| `4_Uretim_Tamamlanan` | `color_raw` | raw_value | string | audit_event | `production_completions` | no | no | no | raw color token |
| `4_Uretim_Tamamlanan` | `status_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | completion status |
| `4_Uretim_Tamamlanan` | `status_tr` | label | string | audit_event | `production_completions` | no | no | no | Turkish status |
| `4_Uretim_Tamamlanan` | `travel_ms` | duration | duration_ms | audit_event | `production_completions` | no | no | no | ms-first |
| `4_Uretim_Tamamlanan` | `flow_ms` | duration | duration_ms | audit_event | `production_completions` | no | no | no | ms-first |
| `4_Uretim_Tamamlanan` | `cycle_ms` | duration | duration_ms | audit_event | `production_completions` | no | no | no | ms-first |
| `4_Uretim_Tamamlanan` | `decision_source_id` | lookup_id | integer | audit_event | `production_completions` | yes | yes | no | `decision_sources` lookup |
| `4_Uretim_Tamamlanan` | `decision_source_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | `decision_sources` lookup |
| `4_Uretim_Tamamlanan` | `review_required` | flag | boolean | audit_event | `production_completions` | no | no | no | review flag |
| `4_Uretim_Tamamlanan` | `final_quality_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | `quality_codes` lookup |
| `4_Uretim_Tamamlanan` | `final_quality_tr` | label | string | audit_event | `production_completions` | no | no | no | Turkish quality label |
| `4_Uretim_Tamamlanan` | `override_flag` | flag | boolean | audit_event | `production_completions` | no | no | no | quality override flag |
| `4_Uretim_Tamamlanan` | `override_source_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | override source lookup candidate |
| `4_Uretim_Tamamlanan` | `override_applied_at` | timestamp | datetime_iso | audit_event | `production_completions` | no | no | yes | override time |
| `4_Uretim_Tamamlanan` | `sensor_color_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | sensor color |
| `4_Uretim_Tamamlanan` | `vision_color_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | vision color |
| `4_Uretim_Tamamlanan` | `final_color_code` | lookup_code | string | audit_event | `production_completions` | no | yes | no | final color |
| `4_Uretim_Tamamlanan` | `mismatch_flag` | flag | boolean | audit_event | `production_completions` | no | no | no | sensor/vision mismatch |
| `4_Uretim_Tamamlanan` | `correlation_status` | enum | string | audit_event | `production_completions` | no | yes | no | correlation lookup candidate |
| `4_Uretim_Tamamlanan` | `finalization_reason` | enum | string | audit_event | `production_completions` | no | yes | no | needs_review |
| `4_Uretim_Tamamlanan` | `early_pick_triggered` | flag | boolean | audit_event | `production_completions` | no | no | no | early pick flag |
| `4_Uretim_Tamamlanan` | `pick_trigger_source` | enum | string | audit_event | `production_completions` | no | yes | no | trigger source lookup candidate |
| `4_Uretim_Tamamlanan` | `early_pick_request_sent_at` | timestamp | datetime_iso | audit_event | `production_completions` | no | no | yes | early pick request time |
| `4_Uretim_Tamamlanan` | `early_pick_accepted_at` | timestamp | datetime_iso | audit_event | `production_completions` | no | no | yes | early pick accept time |
| `4_Uretim_Tamamlanan` | `final_color_frozen_at` | timestamp | datetime_iso | audit_event | `production_completions` | no | no | yes | final color freeze time |
| `4_Uretim_Tamamlanan` | `station_id` | lookup_id | string | audit_event | `production_completions` | yes | yes | no | `stations` lookup |
| `4_Uretim_Tamamlanan` | `oee_scope` | enum | string | audit_event | `production_completions` | no | yes | no | OEE scope |
| `4_Uretim_Tamamlanan` | `package_cycle_id` | reference | string | audit_event | `production_completions` | yes | no | no | package cycle reference |

### `5_OEE_Anliklari`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `5_OEE_Anliklari` | `oee_snapshot_id` | key | integer | workbook_projection | `oee_snapshots` | yes | no | no | calculated snapshot id |
| `5_OEE_Anliklari` | `snapshot_time` | timestamp | datetime_iso | workbook_projection | `oee_snapshots` | no | no | yes | snapshot time |
| `5_OEE_Anliklari` | `event_log_id` | reference | integer | workbook_projection | `oee_snapshots` | yes | no | no | optional event reference |
| `5_OEE_Anliklari` | `sample_cycle_tag` | label | string | workbook_projection | `oee_snapshots` | no | no | no | needs_review |
| `5_OEE_Anliklari` | `oee` | calculated_metric | decimal | workbook_projection | `oee_snapshots` | no | no | no | calculated_snapshot |
| `5_OEE_Anliklari` | `availability` | calculated_metric | decimal | workbook_projection | `oee_snapshots` | no | no | no | calculated_snapshot |
| `5_OEE_Anliklari` | `performance` | calculated_metric | decimal | workbook_projection | `oee_snapshots` | no | no | no | calculated_snapshot |
| `5_OEE_Anliklari` | `quality` | calculated_metric | decimal | workbook_projection | `oee_snapshots` | no | no | no | calculated_snapshot |
| `5_OEE_Anliklari` | `mavi_s` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | blue good count |
| `5_OEE_Anliklari` | `mavi_r` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | blue rework count |
| `5_OEE_Anliklari` | `mavi_h` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | blue scrap count |
| `5_OEE_Anliklari` | `sari_s` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | yellow good count |
| `5_OEE_Anliklari` | `sari_r` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | yellow rework count |
| `5_OEE_Anliklari` | `sari_h` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | yellow scrap count |
| `5_OEE_Anliklari` | `kirmizi_s` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | red good count |
| `5_OEE_Anliklari` | `kirmizi_r` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | red rework count |
| `5_OEE_Anliklari` | `kirmizi_h` | color_quality_count | integer | workbook_projection | `oee_snapshots` | no | yes | no | red scrap count |
| `5_OEE_Anliklari` | `is_full_cycle_reference` | flag | boolean | workbook_projection | `oee_snapshots` | no | no | no | snapshot classification flag |
| `5_OEE_Anliklari` | `station_id` | lookup_id | string | workbook_projection | `oee_snapshots` | yes | yes | no | `stations` lookup |
| `5_OEE_Anliklari` | `oee_scope` | enum | string | workbook_projection | `oee_snapshots` | no | yes | no | OEE scope |
| `5_OEE_Anliklari` | `package_cycle_id` | reference | string | workbook_projection | `oee_snapshots` | yes | no | no | package cycle reference |
| `5_OEE_Anliklari` | `notes` | note | text | workbook_projection | `oee_snapshots` | no | no | no | snapshot note |
| `5_OEE_Anliklari` | `raw_line` | raw_reference | text | workbook_projection | `oee_snapshots` | no | no | no | source raw line |

### `6_Vision`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `6_Vision` | `vision_event_id` | key | integer | audit_event | `vision_observations` | yes | no | no | vision row id |
| `6_Vision` | `event_time` | timestamp | datetime_iso | audit_event | `vision_observations` | no | no | yes | vision event time |
| `6_Vision` | `source_code` | lookup_code | string | audit_event | `vision_observations` | no | yes | no | `sources` lookup |
| `6_Vision` | `vision_track_id` | reference | string | audit_event | `vision_observations` | yes | no | no | vision track; not item id |
| `6_Vision` | `event_type` | lookup_code | string | audit_event | `vision_observations` | no | yes | no | vision event type |
| `6_Vision` | `color_id` | lookup_id | integer | audit_event | `vision_observations` | yes | yes | no | `colors` lookup |
| `6_Vision` | `color_code` | lookup_code | string | audit_event | `vision_observations` | no | yes | no | `colors` lookup |
| `6_Vision` | `item_id` | reference | string | audit_event | `vision_observations` | yes | no | no | item reference |
| `6_Vision` | `measure_id` | reference | string | audit_event | `vision_observations` | yes | no | no | measurement reference |
| `6_Vision` | `confidence` | metric | decimal | audit_event | `vision_observations` | no | no | no | confidence score |
| `6_Vision` | `confidence_tier` | enum | string | audit_event | `vision_observations` | no | yes | no | lookup candidate |
| `6_Vision` | `correlation_status` | enum | string | audit_event | `vision_observations` | no | yes | no | correlation lookup candidate |
| `6_Vision` | `late_vision_audit_flag` | flag | boolean | audit_event | `vision_observations` | no | no | no | late audit flag |
| `6_Vision` | `vision_observed_at` | timestamp | datetime_iso | audit_event | `vision_observations` | no | no | yes | observed time |
| `6_Vision` | `vision_published_at` | timestamp | datetime_iso | audit_event | `vision_observations` | no | no | yes | published time |
| `6_Vision` | `vision_received_at` | timestamp | datetime_iso | audit_event | `vision_observations` | no | no | yes | received time |
| `6_Vision` | `line_id` | lookup_id | string | audit_event | `vision_observations` | yes | yes | no | `lines` lookup |
| `6_Vision` | `station_id` | lookup_id | string | audit_event | `vision_observations` | yes | yes | no | `stations` lookup |
| `6_Vision` | `bbox_x1` | geometry_metric | decimal | audit_event | `vision_observations` | no | no | no | bounding box |
| `6_Vision` | `bbox_y1` | geometry_metric | decimal | audit_event | `vision_observations` | no | no | no | bounding box |
| `6_Vision` | `bbox_x2` | geometry_metric | decimal | audit_event | `vision_observations` | no | no | no | bounding box |
| `6_Vision` | `bbox_y2` | geometry_metric | decimal | audit_event | `vision_observations` | no | no | no | bounding box |
| `6_Vision` | `direction` | enum | string | audit_event | `vision_observations` | no | yes | no | direction lookup candidate |
| `6_Vision` | `is_placeholder` | flag | boolean | audit_event | `vision_observations` | no | no | no | placeholder flag |
| `6_Vision` | `notes` | note | text | audit_event | `vision_observations` | no | no | no | free-form note |

### `7_Is_Emirleri`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `7_Is_Emirleri` | `work_order_record_id` | projection_key | integer | runtime_projection | `work_order_projection` | yes | no | no | projection_not_canonical |
| `7_Is_Emirleri` | `order_id` | domain_reference | string | runtime_projection | `work_order_projection` | yes | no | no | canonical work order id candidate |
| `7_Is_Emirleri` | `erp_type` | enum | string | runtime_projection | `work_order_projection` | no | yes | no | FERP/import classification |
| `7_Is_Emirleri` | `source_file` | source_reference | string | runtime_projection | `work_order_projection` | no | no | no | import source |
| `7_Is_Emirleri` | `queued_at` | timestamp | datetime_iso | runtime_projection | `work_order_projection` | no | no | yes | queued time |
| `7_Is_Emirleri` | `started_at` | timestamp | datetime_iso | runtime_projection | `work_order_projection` | no | no | yes | start time |
| `7_Is_Emirleri` | `completed_at` | timestamp | datetime_iso | runtime_projection | `work_order_projection` | no | no | yes | completion time |
| `7_Is_Emirleri` | `status_code` | lookup_code | string | runtime_projection | `work_order_projection` | no | yes | no | `work_order_statuses` lookup |
| `7_Is_Emirleri` | `status_tr` | label | string | runtime_projection | `work_order_projection` | no | no | no | Turkish status |
| `7_Is_Emirleri` | `stock_code` | product_reference | string | runtime_projection | `work_order_projection` | no | yes | no | product/stock lookup candidate |
| `7_Is_Emirleri` | `stock_name` | label | string | runtime_projection | `work_order_projection` | no | no | no | stock display snapshot |
| `7_Is_Emirleri` | `product_color` | lookup_code | string | runtime_projection | `work_order_projection` | no | yes | no | color lookup candidate |
| `7_Is_Emirleri` | `target_qty` | quantity | integer | runtime_projection | `work_order_projection` | no | no | no | target quantity |
| `7_Is_Emirleri` | `fulfilled_qty` | quantity | integer | runtime_projection | `work_order_projection` | no | no | no | fulfilled quantity |
| `7_Is_Emirleri` | `production_qty` | quantity | integer | runtime_projection | `work_order_projection` | no | no | no | produced quantity |
| `7_Is_Emirleri` | `inventory_consumed_qty` | quantity | integer | runtime_projection | `work_order_projection` | no | no | no | consumed inventory |
| `7_Is_Emirleri` | `good_qty` | quality_count | integer | runtime_projection | `work_order_projection` | no | yes | no | quality count |
| `7_Is_Emirleri` | `rework_qty` | quality_count | integer | runtime_projection | `work_order_projection` | no | yes | no | quality count |
| `7_Is_Emirleri` | `scrap_qty` | quality_count | integer | runtime_projection | `work_order_projection` | no | yes | no | quality count |
| `7_Is_Emirleri` | `ideal_cycle_ms` | duration | duration_ms | runtime_projection | `work_order_projection` | no | no | no | ms-first |
| `7_Is_Emirleri` | `ideal_cycle_sec` | duration | duration_sec | runtime_projection | `work_order_projection` | no | no | no | derived/compatibility |
| `7_Is_Emirleri` | `planned_duration_ms` | duration | duration_ms | runtime_projection | `work_order_projection` | no | no | no | ms-first |
| `7_Is_Emirleri` | `planned_duration_sec` | duration | duration_sec | runtime_projection | `work_order_projection` | no | no | no | derived/compatibility |
| `7_Is_Emirleri` | `runtime_ms` | duration | duration_ms | runtime_projection | `work_order_projection` | no | no | no | ms-first |
| `7_Is_Emirleri` | `runtime_sec` | duration | duration_sec | runtime_projection | `work_order_projection` | no | no | no | derived/compatibility |
| `7_Is_Emirleri` | `unplanned_downtime_ms` | duration | duration_ms | runtime_projection | `work_order_projection` | no | no | no | ms-first |
| `7_Is_Emirleri` | `unplanned_downtime_sec` | duration | duration_sec | runtime_projection | `work_order_projection` | no | no | no | derived/compatibility |
| `7_Is_Emirleri` | `availability_pct` | calculated_metric | decimal | runtime_projection | `work_order_projection` | no | no | no | calculated |
| `7_Is_Emirleri` | `performance_pct` | calculated_metric | decimal | runtime_projection | `work_order_projection` | no | no | no | calculated |
| `7_Is_Emirleri` | `quality_pct` | calculated_metric | decimal | runtime_projection | `work_order_projection` | no | no | no | calculated |
| `7_Is_Emirleri` | `oee_pct` | calculated_metric | decimal | runtime_projection | `work_order_projection` | no | no | no | calculated |
| `7_Is_Emirleri` | `started_by` | operator_reference | string | runtime_projection | `work_order_projection` | no | yes | no | operator code/id candidate |
| `7_Is_Emirleri` | `started_by_name` | label | string | runtime_projection | `work_order_projection` | no | no | no | operator display snapshot |
| `7_Is_Emirleri` | `transition_reason` | note | text | runtime_projection | `work_order_projection` | no | no | no | operator transition reason |
| `7_Is_Emirleri` | `notes` | note | text | runtime_projection | `work_order_projection` | no | no | no | free-form note |

### `8_Depo_Stok`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `8_Depo_Stok` | `inventory_record_id` | projection_key | integer | runtime_projection | `operational_inventory_projection` | yes | no | no | projection row id |
| `8_Depo_Stok` | `match_key` | domain_key | string | runtime_projection | `operational_inventory_projection` | yes | no | no | operational inventory key |
| `8_Depo_Stok` | `product_code` | product_reference | string | runtime_projection | `operational_inventory_projection` | no | yes | no | `products` lookup candidate |
| `8_Depo_Stok` | `stock_code` | product_reference | string | runtime_projection | `operational_inventory_projection` | no | yes | no | stock/product code |
| `8_Depo_Stok` | `stock_name` | label | string | runtime_projection | `operational_inventory_projection` | no | no | no | stock display snapshot |
| `8_Depo_Stok` | `color_code` | lookup_code | string | runtime_projection | `operational_inventory_projection` | no | yes | no | `colors` lookup |
| `8_Depo_Stok` | `quantity` | quantity | integer | runtime_projection | `operational_inventory_projection` | no | no | no | MES operational stock |
| `8_Depo_Stok` | `last_updated_at` | timestamp | datetime_iso | runtime_projection | `operational_inventory_projection` | no | no | yes | last update |
| `8_Depo_Stok` | `last_source` | lookup_code | string | runtime_projection | `operational_inventory_projection` | no | yes | no | source/action lookup candidate |
| `8_Depo_Stok` | `source_file` | source_reference | string | runtime_projection | `operational_inventory_projection` | no | no | no | import source |
| `8_Depo_Stok` | `notes` | note | text | runtime_projection | `operational_inventory_projection` | no | no | no | free-form note |

### `9_Bakim_Kayitlari`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `9_Bakim_Kayitlari` | `maintenance_record_id` | key | integer | audit_event | `maintenance_step_records` | yes | no | no | maintenance row id |
| `9_Bakim_Kayitlari` | `maintenance_row_key` | key | string | audit_event | `maintenance_step_records` | yes | no | no | session + step key |
| `9_Bakim_Kayitlari` | `session_id` | reference | string | audit_event | `maintenance_step_records` | yes | no | no | maintenance session id |
| `9_Bakim_Kayitlari` | `phase_code` | lookup_code | string | audit_event | `maintenance_step_records` | no | yes | no | opening/closing |
| `9_Bakim_Kayitlari` | `phase_tr` | label | string | audit_event | `maintenance_step_records` | no | no | no | Turkish phase label |
| `9_Bakim_Kayitlari` | `step_code` | lookup_code | string | audit_event | `maintenance_step_records` | no | yes | no | `maintenance_steps` lookup |
| `9_Bakim_Kayitlari` | `step_label_tr` | label | string | audit_event | `maintenance_step_records` | no | no | no | Turkish step label |
| `9_Bakim_Kayitlari` | `required_flag` | flag | boolean | audit_event | `maintenance_step_records` | no | no | no | required step flag |
| `9_Bakim_Kayitlari` | `completed_flag` | flag | boolean | audit_event | `maintenance_step_records` | no | no | no | completed step flag |
| `9_Bakim_Kayitlari` | `completed_at` | timestamp | datetime_iso | audit_event | `maintenance_step_records` | no | no | yes | step completion time |
| `9_Bakim_Kayitlari` | `session_started_at` | timestamp | datetime_iso | audit_event | `maintenance_step_records` | no | no | yes | session start |
| `9_Bakim_Kayitlari` | `session_ended_at` | timestamp | datetime_iso | audit_event | `maintenance_step_records` | no | no | yes | session end |
| `9_Bakim_Kayitlari` | `duration_ms` | duration | duration_ms | audit_event | `maintenance_step_records` | no | no | no | ms-first |
| `9_Bakim_Kayitlari` | `duration_sec` | duration | duration_sec | audit_event | `maintenance_step_records` | no | no | no | derived/compatibility |
| `9_Bakim_Kayitlari` | `shift_code` | lookup_code | string | audit_event | `maintenance_step_records` | no | yes | no | `shifts` lookup |
| `9_Bakim_Kayitlari` | `device_id` | reference | string | audit_event | `maintenance_step_records` | yes | no | no | device reference |
| `9_Bakim_Kayitlari` | `device_name` | label | string | audit_event | `maintenance_step_records` | no | no | no | device display snapshot |
| `9_Bakim_Kayitlari` | `device_role` | enum | string | audit_event | `maintenance_step_records` | no | yes | no | device role lookup candidate |
| `9_Bakim_Kayitlari` | `bound_station_id` | lookup_id | string | audit_event | `maintenance_step_records` | yes | yes | no | station reference |
| `9_Bakim_Kayitlari` | `operator_id` | lookup_id | string | audit_event | `maintenance_step_records` | yes | yes | no | operator reference |
| `9_Bakim_Kayitlari` | `operator_code` | lookup_code | string | audit_event | `maintenance_step_records` | no | yes | no | operator code snapshot |
| `9_Bakim_Kayitlari` | `operator_name` | label | string | audit_event | `maintenance_step_records` | no | no | no | operator display snapshot |
| `9_Bakim_Kayitlari` | `note` | note | text | audit_event | `maintenance_step_records` | no | no | no | free-form note |

### `99_Raw_Logs`

| sheet_name | column_name | inferred_role | likely_data_type | likely_source_owner | likely_target_table | is_key_candidate | is_lookup_candidate | is_timestamp_candidate | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `99_Raw_Logs` | `raw_log_id` | key | integer | raw_archive | `raw_event_archive` | yes | no | no | normal_reporting_disi |
| `99_Raw_Logs` | `logged_at` | timestamp | datetime_iso | raw_archive | `raw_event_archive` | no | no | yes | normal_reporting_disi |
| `99_Raw_Logs` | `source_topic` | source_reference | string | raw_archive | `raw_event_archive` | no | yes | no | normal_reporting_disi |
| `99_Raw_Logs` | `source_code` | lookup_code | string | raw_archive | `raw_event_archive` | no | yes | no | `sources` lookup |
| `99_Raw_Logs` | `parsed_flag` | flag | boolean | raw_archive | `raw_event_archive` | no | no | no | normal_reporting_disi |
| `99_Raw_Logs` | `event_type_code` | lookup_code | string | raw_archive | `raw_event_archive` | no | yes | no | `event_types` lookup |
| `99_Raw_Logs` | `item_id` | reference | string | raw_archive | `raw_event_archive` | yes | no | no | normal_reporting_disi |
| `99_Raw_Logs` | `measure_id` | reference | string | raw_archive | `raw_event_archive` | yes | no | no | normal_reporting_disi |
| `99_Raw_Logs` | `color_code` | lookup_code | string | raw_archive | `raw_event_archive` | no | yes | no | `colors` lookup |
| `99_Raw_Logs` | `station_id` | lookup_id | string | raw_archive | `raw_event_archive` | yes | yes | no | station reference |
| `99_Raw_Logs` | `oee_scope` | enum | string | raw_archive | `raw_event_archive` | no | yes | no | normal_reporting_disi |
| `99_Raw_Logs` | `package_cycle_id` | reference | string | raw_archive | `raw_event_archive` | yes | no | no | normal_reporting_disi |
| `99_Raw_Logs` | `notes` | note | text | raw_archive | `raw_event_archive` | no | no | no | normal_reporting_disi |
| `99_Raw_Logs` | `raw_payload` | raw_payload | text | raw_archive | `raw_event_archive` | no | no | no | normal_reporting_disi |

## 5. Anahtar Alanlar

Anahtar adaylari:

- `log_event_id`
- `measurement_row_id`
- `measure_id`
- `fault_record_id`
- `fault_id`
- `production_record_id`
- `item_id`
- `oee_snapshot_id`
- `vision_event_id`
- `vision_track_id`
- `work_order_record_id`
- `order_id`
- `inventory_record_id`
- `match_key`
- `maintenance_record_id`
- `maintenance_row_key`
- `session_id`
- `raw_log_id`

Notlar:

- Workbook projection id'leri canonical domain id yerine gecmez.
- `work_order_record_id`, canonical `work_order_id` degildir.
- `vision_track_id`, `item_id` yerine gecmez.
- `measure_id`, urun kimligi degil olcum/karar kimligidir.

## 6. Timestamp Alanlari

Timestamp adaylari:

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

Kural:

- Hedef data dictionary'de bu alanlar `datetime_iso` olarak belgelenmelidir.
- Timezone bilgisi korunmalidir.
- Workbook text formatta tutsa bile hedef sozlukte zaman semantigi acik yazilmalidir.

## 7. Lookup/Enum Alanlari

Lookup/enum adaylari:

- `source_id`, `source_code`, `source_topic`
- `event_type_id`, `event_type_code`, `event_type`
- `color_id`, `color_code`, `final_color_code`, `sensor_color_code`, `vision_color_code`, `product_color`
- `decision_source_id`, `decision_source_code`
- `mega_state_id`, `mega_state_code`
- `line_id`, `station_id`, `bound_station_id`
- `status_code`, `status_tr`
- `fault_type_code`, `fault_category`
- `final_quality_code`, `final_quality_tr`
- `correlation_status`, `confidence_tier`
- `oee_scope`, `phase_code`, `device_role`
- `shift_code`, `operator_code`

Kural:

- Lookup alanlari hedefte ilgili lookup/master tabloyla eslesmelidir.
- `*_tr` alanlari genelde gorunen etiket snapshot'idir; canonical kod yerine gecmemelidir.

## 8. Runtime Projection Alanlari

Runtime projection sheet'leri:

- `7_Is_Emirleri`
- `8_Depo_Stok`

Runtime projection alan gruplari:

- Is emri status ve zamanlari: `status_code`, `queued_at`, `started_at`, `completed_at`
- Is emri miktarlari: `target_qty`, `fulfilled_qty`, `production_qty`, `inventory_consumed_qty`
- Is emri OEE ozeti: `availability_pct`, `performance_pct`, `quality_pct`, `oee_pct`
- Operasyonel stok: `match_key`, `quantity`, `last_updated_at`, `last_source`

Kural:

- Bu alanlar workbook icinde son gorunum/projection'dir.
- Canonical is emri ve stok modeli ayri tasarlanmalidir.

## 9. Audit/Event Alanlari

Audit/event sheet'leri:

- `1_Olay_Logu`
- `2_Olcumler`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `6_Vision`
- `9_Bakim_Kayitlari`

Calculated snapshot:

- `5_OEE_Anliklari`

Raw archive:

- `99_Raw_Logs`

Kural:

- Audit/event alanlari backfill ve raporlama icin degerlidir.
- `5_OEE_Anliklari` event store degil, hesaplanmis time-series olarak ele alinmalidir.
- Raw log alanlari normal raporlama modeli disinda tutulmalidir.

## 10. Backfill Adayi Alanlar

Backfill icin yuksek degerli alan gruplari:

- Event sirasi: `log_event_id`, `event_time_text`, `event_type_code`
- Urun izleme: `item_id`, `measure_id`, `detected_at`, `completed_at`
- Kalite: `final_quality_code`, `override_flag`, `override_applied_at`
- OEE: `snapshot_time`, `oee`, `availability`, `performance`, `quality`
- Fault: `fault_id`, `fault_type_code`, `started_at`, `ended_at`, `duration_ms`
- Bakim: `session_id`, `phase_code`, `step_code`, `completed_at`, `duration_ms`
- Raw dogrulama: `logged_at`, `source_topic`, `parsed_flag`, `raw_payload`

Kisit:

- Upsert/projection sheet'leri tam degisiklik gecmisi tasimayabilir.
- Raw logs yalniz dogrulama/debug/archive amacli kullanilmalidir.

## 11. Eksik Aciklama Gerektiren Alanlar

`needs_review` olarak isaretlenen veya alan sozlugunde detaylandirilmasi gereken baslica alanlar:

- `source_log_file`
- `search_hint`
- `search_hint_win`
- `search_hint_second`
- `search_hint_strong`
- `core_n`
- `obj_n`
- `median_nearest`
- `score_nearest`
- `med_d_r`
- `med_d_y`
- `med_d_b`
- `med_d_x`
- `x_r`
- `x_g`
- `x_b`
- `med_obj`
- `core_str_min`
- `core_str_max`
- `vote_win`
- `vote_second`
- `vote_classified`
- `vote_x`
- `vote_r`
- `vote_y`
- `vote_b`
- `vote_cal`
- `tot_x`
- `tot_cal`
- `sample_cycle_tag`
- `finalization_reason`

Bu alanlar muhtemelen sensor karar algoritmasi, OEE snapshot etiketi veya finalization logic ile ilgilidir. Alan sozlugunun sonraki fazinda business anlamlari kod ve test davranislariyla dogrulanmalidir.

## 12. Uygulanacak Sonraki 5 Is

1. Bu envanterdeki tum kolonlar icin `docs/data-dictionary-plan.md` formatindaki 15 kolonlu veri sozlugu tablosunu doldur.
2. `needs_review` alanlari icin parser, projector ve test davranislarindan is anlami cikar.
3. Lookup/enum adaylarini `docs/masterdata-design.md` icindeki lookup tablolarla eslestir.
4. Backfill adaylarini append, upsert, snapshot ve raw archive olarak ayirip okuma sirasi tanimla.
5. Workbook kolon sozlesmesi icin geriye uyumluluk kurali ekle: kolon adlari keyfi degistirilmez, yeni kolon eklenirse mevcut anlam bozulmaz.
