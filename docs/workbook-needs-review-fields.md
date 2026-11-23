# Workbook Needs Review Fields

## 1. Amac

Bu dokuman, `docs/workbook-field-inventory.md` icinde `needs_review` olarak isaretlenen workbook alanlarini acikliga kavusturmak icin hazirlanmistir.

Kapsam kod degisikligi, migration, SQL DDL veya Excel sablonu degisikligi degildir. Amac, alan anlamlarini mevcut kod ve test davranisindan okuyup veri sozlugune aktarilabilecek karar seviyesine getirmektir.

Korunan kararlar:

- Gunluk workbook canli transactional DB degildir.
- Workbook audit/projection/backfill/replay kaynagidir.
- `2_Olcumler` sensor ve measurement detaylarini tasir.
- Sensor algoritmasi metrikleri MES ana domain modeline dogrudan karistirilmamalidir.
- `5_OEE_Anliklari` event degil, calculated OEE snapshot/time-series yapisidir.
- `4_Uretim_Tamamlanan.finalization_reason`, kalite sonucundan ayri bir karar/finalization gerekcesidir.

## 2. Kaynak Dosyalar

Incelenen kaynaklar:

- `docs/workbook-field-inventory.md`
- `docs/data-dictionary-plan.md`
- `docs/workbook-schema.md`
- `mes_web/excel_runtime.py`
- `mes_web/parsers.py`
- `mes_web/oee_state.py`
- `tests/test_mes_web_excel_runtime.py`
- `tests/test_mes_web_oee_state.py`
- Parser davranisini dolayli kullanan runtime ve workbook testleri

Kaynak okumada temel bulgu:

- Measurement alanlari `MEGA|TCS3200|STATE=MEASURING` satirindaki raw key/value payload'dan `2_Olcumler` sheet'ine projekte ediliyor.
- Parser bu payload'u genel `raw` dict olarak tasiyor; sensor algoritmasi alanlarinin matematiksel tanimi parser icinde ayrica belgelenmiyor.
- OEE `sample_cycle_tag`, snapshot'in kaynagini/etiketini gosteren calculated snapshot alanidir.
- `finalization_reason`, vision/sensor/fault/finalization mantigi ile doldurulan karar gerekcesidir.

## 3. Needs Review Alanlarinin Genel Siniflandirmasi

| Grup | Alanlar | Is/domain kritikligi | Onerilen sahiplik | Not |
| --- | --- | --- | --- | --- |
| Kaynak/provenance | `source_log_file` | Backfill ve audit icin kritik | audit_event | Kaynak ailesi `mqtt/logs` olarak yaziliyor |
| Search hint | `search_hint`, `search_hint_win`, `search_hint_second`, `search_hint_strong` | Sensor debug ve karar inceleme icin kritik | measurement_debug_metrics | Ana MES domain kolonlari gibi ele alinmamali |
| Sample/count metrikleri | `core_n`, `obj_n`, `med_obj`, `core_str_min`, `core_str_max` | Sensor algoritmasi acisindan kritik | measurement_metrics | Formul/algoritma sahipligi ayrica belgelenmeli |
| Median/distance metrikleri | `median_nearest`, `score_nearest`, `med_d_r`, `med_d_y`, `med_d_b`, `med_d_x`, `x_r`, `x_g`, `x_b` | Sensor algoritmasi acisindan kritik | measurement_metrics veya measurement_debug_metrics | Renk karari nedenini aciklamak icin kullanilabilir |
| Vote/total metrikleri | `vote_win`, `vote_second`, `vote_classified`, `vote_x`, `vote_r`, `vote_y`, `vote_b`, `vote_cal`, `tot_x`, `tot_cal` | Sensor debug ve replay dogrulama icin kritik | measurement_metrics veya measurement_debug_metrics | `x` mevcut payload'da `BOS`/empty adayina bagli gorunuyor |
| OEE snapshot etiketi | `sample_cycle_tag` | Snapshot izlenebilirligi icin kritik | workbook_projection | Event kimligi degildir |
| Production finalization | `finalization_reason` | Domain/audit icin kritik | audit_event | Kalite kodu degil, karar gerekcesidir |

## 4. Sensor / Measurement Algoritmasi Alanlari

`2_Olcumler` sheet'indeki `needs_review` alanlarinin buyuk bolumu sensor karar algoritmasinin ic metrikleridir. Bunlar:

- final renk kararini aciklamak icin degerlidir
- backfill/replay dogrulamasinda yardimci olabilir
- sensor algoritmasi tuning ve debug surecinde kritik olabilir
- ana MES domain modelinde urun, is emri, kalite veya stok gibi canonical is nesneleriyle ayni seviyeye konmamalidir

Onerilen hedef ayrimi:

| Alan grubu | Ana tabloda olsun mu? | Onerilen hedef |
| --- | --- | --- |
| Olcum kimligi, zaman, final renk, karar kaynagi | Evet | `measurements` |
| Sensor kararini aciklayan ozet metrikler | Sinirli | `measurement_metrics` |
| Algoritma ic debug metrikleri | Hayir | `measurement_debug_metrics` veya JSON/detail payload |
| Ham satir ve raw payload | Hayir | `raw_event_archive` veya measurement raw detail |

## 5. Vote / Median / Distance Metrikleri

Bu grup sensor algoritmasinin karar dayanaklarini temsil eder.

Koddan net okunanlar:

- `med_d_r`, `med_d_y`, `med_d_b`, `med_d_x` alanlari raw `MED_D_R`, `MED_D_Y`, `MED_D_B`, `MED_D_X` tokenlerinden gelir.
- `vote_r`, `vote_y`, `vote_b` alanlari raw `VOTE_R`, `VOTE_Y`, `VOTE_B` tokenlerinden gelir.
- `vote_x` raw `VOTE_BOS` tokeninden gelir.
- `tot_x` raw `TOT_BOS` tokeninden gelir.
- `vote_cal` ve `tot_cal` raw `VOTE_CAL` ve `TOT_CAL` tokenlerinden gelir.

Yorum:

- `r`, `y`, `b` kirmizi/sari/mavi adaylarini temsil eder.
- `x`, kod map'inde `BOS`/empty adayina bagli gorunur; canonical renk kodu olarak kullanilmamalidir.
- `cal` icin muhtemel anlam calibration'dir; ancak kodda acik dokuman yoktur.
- Bu metrikler uretim, kalite veya stok ana tablolarini sisirmemeli; sensor detail/debug katmaninda tutulmalidir.

## 6. Search Hint Alanlari

`search_hint` ailesi raw measurement payload'undan gelir:

- `search_hint` -> `SEARCH_HINT`
- `search_hint_win` -> `SEARCH_HINT_WIN`
- `search_hint_second` -> `SEARCH_HINT_SECOND`
- `search_hint_strong` -> `SEARCH_HINT_STRONG`

Bu alanlar final color veya canonical color yerine gecmez. Sensorun arama/aday karar baglamini yansitir.

Oneri:

- Veri sozlugunde `measurement_context` veya `sensor_algorithm_context` olarak belgelenmeli.
- Ana `measurements` tablosunda zorunlu domain alan yapilmamali.
- Geriye donuk sensor karar analizi gerekiyorsa `measurement_debug_metrics` icinde korunmali.

## 7. OEE Snapshot Alanlari

`sample_cycle_tag`, `5_OEE_Anliklari` sheet'indedir ve OEE snapshot'in kaynagini etiketler.

Koddan okunan davranis:

- Tablet OEE satirlarinda `tablet:<snapshot_id>` seklinde yazilir.
- Runtime state sync satirlarinda `runtime:<reason>:<snapshot_time>` seklinde yazilir.

Kural:

- `sample_cycle_tag` event id degildir.
- `sample_cycle_tag` production cycle id degildir.
- `sample_cycle_tag`, calculated OEE snapshot'in kaynak/sample etiketi olarak ele alinmalidir.
- Hedefte `oee_snapshots.sample_cycle_tag` icinde kalabilir.

## 8. Production Finalization Alanlari

`finalization_reason`, `4_Uretim_Tamamlanan` sheet'indedir ve final color/production completion kararinin neden bu sekilde kapandigini anlatir.

Kod ve testlerden gorulen degerler:

- `SENSOR_NO_VISION`
- `VISION_HIGH_CONF`
- `VISION_CORRECTED_MISMATCH`
- `SENSOR_LATE_VISION`
- `SENSOR_LOW_CONF_VISION_IGNORED`
- `SENSOR_FAULT_WINDOW`

Kural:

- `finalization_reason`, kalite sonucu degildir.
- `finalization_reason`, `final_quality_code` yerine gecmemelidir.
- `finalization_reason`, sensor/vision/fault/final karar gerekcesi olarak `production_completions` icinde veya ayrica lookup sozluguyle tutulmalidir.

## 9. Alan Bazli Aciklama Tablosu

| field_name | sheet_name | current_classification | inferred_meaning | source_code_reference | likely_data_type | domain_relevance | should_be_in_main_table | suggested_target | data_dictionary_status | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `source_log_file` | `2_Olcumler` | source_reference | Measurement satirinin kaynak log ailesi; mevcut projector `mqtt/logs` yazar | `mes_web/excel_runtime.py:905`, `docs/workbook-field-inventory.md:95` | string | Backfill/replay provenance icin kritik | yes | `measurements.source_log_file` | resolved | Fiziksel dosya yolu degil, kaynak etiketi gibi kullaniliyor |
| `search_hint` | `2_Olcumler` | measurement_context | Sensorun raw `SEARCH_HINT` aday/arama ipucu | `mes_web/excel_runtime.py:911`, `tests/test_mes_web_excel_runtime.py:18-43` | string | Sensor karar inceleme icin kritik | no | `measurement_debug_metrics.search_hint` | partially_resolved | Final color yerine gecmez; algoritma sahibiyle dogrulanmali |
| `search_hint_win` | `2_Olcumler` | measurement_context | Raw `SEARCH_HINT_WIN`; search hint icin pencere/sayac metriği | `mes_web/excel_runtime.py:912`, `tests/test_mes_web_excel_runtime.py:38` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.search_hint_win` | partially_resolved | Pencere tanimi kodda acik degil |
| `search_hint_second` | `2_Olcumler` | measurement_context | Raw `SEARCH_HINT_SECOND`; ikincil hint/sayac metriği | `mes_web/excel_runtime.py:913` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.search_hint_second` | partially_resolved | Ikincil hint mantigi kodda belgeli degil |
| `search_hint_strong` | `2_Olcumler` | measurement_context | Raw `SEARCH_HINT_STRONG`; guclu hint flag/sayac metriği | `mes_web/excel_runtime.py:914` | integer_or_boolean | Sensor debug icin kritik | no | `measurement_debug_metrics.search_hint_strong` | partially_resolved | Flag mi sayac mi oldugu payload kontratiyla netlesmeli |
| `core_n` | `2_Olcumler` | metric | Raw `CORE_N`; core sample sayisi gibi kullanilan sensor metriği | `mes_web/excel_runtime.py:918`, `tests/test_mes_web_excel_runtime.py:39` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.core_n` | partially_resolved | Core karar algoritmasinin sample sayisi olarak yorumlaniyor |
| `obj_n` | `2_Olcumler` | metric | Raw `OBJ_N`; object sample/sayac metriği | `mes_web/excel_runtime.py:919` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.obj_n` | partially_resolved | Object tanimi sensor firmware tarafinda dogrulanmali |
| `median_nearest` | `2_Olcumler` | metric | Raw `MEDIAN_NEAREST`; median bazli en yakin aday etiketi | `mes_web/excel_runtime.py:920`, `tests/test_mes_web_excel_runtime.py:18` | string | Sensor karar aciklanabilirligi icin kritik | no | `measurement_metrics.median_nearest` | partially_resolved | Aday etiketi gibi gorunuyor; canonical color degil |
| `score_nearest` | `2_Olcumler` | metric | Raw `SCORE_NEAREST`; adindan skor beklenir, test payload'inda aday etiketi gelebiliyor | `mes_web/excel_runtime.py:921`, `tests/test_mes_web_excel_runtime.py:18` | string_or_decimal | Sensor karar aciklanabilirligi icin kritik | no | `measurement_metrics.score_nearest` | unresolved | Veri tipi ve is anlami firmware kontratiyla netlesmeli |
| `med_d_r` | `2_Olcumler` | sensor_metric | Raw `MED_D_R`; median ile red/kirmizi aday mesafesi | `mes_web/excel_runtime.py:925` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.med_d_r` | partially_resolved | Mesafe birimi/formulu kodda yok |
| `med_d_y` | `2_Olcumler` | sensor_metric | Raw `MED_D_Y`; median ile yellow/sari aday mesafesi | `mes_web/excel_runtime.py:926` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.med_d_y` | partially_resolved | Mesafe birimi/formulu kodda yok |
| `med_d_b` | `2_Olcumler` | sensor_metric | Raw `MED_D_B`; median ile blue/mavi aday mesafesi | `mes_web/excel_runtime.py:927` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.med_d_b` | partially_resolved | Mesafe birimi/formulu kodda yok |
| `med_d_x` | `2_Olcumler` | sensor_metric | Raw `MED_D_X`; median ile empty/unknown aday mesafesi gibi gorunur | `mes_web/excel_runtime.py:928`, `tests/test_mes_web_excel_runtime.py:40` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.med_d_x` | partially_resolved | `x` ile `BOS` eslesmesi vote/total alanlarindan cikarsaniyor |
| `x_r` | `2_Olcumler` | sensor_metric | Raw `X_R`; `x` adayinin red kanal/ozellik degeri gibi gorunur | `mes_web/excel_runtime.py:929` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.x_r` | partially_resolved | `x` adayinin kesin anlami firmware tarafinda netlesmeli |
| `x_g` | `2_Olcumler` | sensor_metric | Raw `X_G`; `x` adayinin green kanal/ozellik degeri gibi gorunur | `mes_web/excel_runtime.py:930` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.x_g` | partially_resolved | Kanal/ozellik formulu kodda yok |
| `x_b` | `2_Olcumler` | sensor_metric | Raw `X_B`; `x` adayinin blue kanal/ozellik degeri gibi gorunur | `mes_web/excel_runtime.py:931`, `tests/test_mes_web_excel_runtime.py:41` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.x_b` | partially_resolved | Kanal/ozellik formulu kodda yok |
| `med_obj` | `2_Olcumler` | sensor_metric | Raw `MED_OBJ`; object median veya object varligi metriği | `mes_web/excel_runtime.py:932` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.med_obj` | partially_resolved | Object semantigi firmware/sensor algoritmasiyla netlesmeli |
| `core_str_min` | `2_Olcumler` | sensor_metric | Raw `CORE_STR_MIN`; core signal strength minimumu gibi gorunur | `mes_web/excel_runtime.py:934` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.core_str_min` | partially_resolved | Birim ve hesaplama araligi kodda yok |
| `core_str_max` | `2_Olcumler` | sensor_metric | Raw `CORE_STR_MAX`; core signal strength maksimumu gibi gorunur | `mes_web/excel_runtime.py:935` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.core_str_max` | partially_resolved | Birim ve hesaplama araligi kodda yok |
| `vote_win` | `2_Olcumler` | sensor_metric | Raw `VOTE_WIN`; vote pencere/sayac metriği | `mes_web/excel_runtime.py:936` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.vote_win` | partially_resolved | Window tanimi firmware kontratiyla netlesmeli |
| `vote_second` | `2_Olcumler` | sensor_metric | Raw `VOTE_SECOND`; ikincil vote metriği | `mes_web/excel_runtime.py:938` | integer | Sensor debug icin kritik | no | `measurement_metrics.vote_second` | partially_resolved | Ikincil vote anlami kodda yok |
| `vote_classified` | `2_Olcumler` | sensor_metric | Raw `VOTE_CLASSIFIED`; siniflanan vote sayisi/flag'i | `mes_web/excel_runtime.py:939` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.vote_classified` | partially_resolved | Count mu flag mi kontratla netlesmeli |
| `vote_x` | `2_Olcumler` | sensor_metric | Raw `VOTE_BOS`; empty/bos adayina verilen vote sayisi | `mes_web/excel_runtime.py:940`, `tests/test_mes_web_excel_runtime.py:42` | integer | Sensor debug icin kritik | no | `measurement_metrics.vote_x` | partially_resolved | `x` canonical color degil, BOS/empty adayidir |
| `vote_r` | `2_Olcumler` | sensor_metric | Raw `VOTE_R`; red/kirmizi aday vote sayisi | `mes_web/excel_runtime.py:941` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.vote_r` | partially_resolved | Vote kurali kodda yok |
| `vote_y` | `2_Olcumler` | sensor_metric | Raw `VOTE_Y`; yellow/sari aday vote sayisi | `mes_web/excel_runtime.py:937` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.vote_y` | partially_resolved | Vote kurali kodda yok |
| `vote_b` | `2_Olcumler` | sensor_metric | Raw `VOTE_B`; blue/mavi aday vote sayisi | `mes_web/excel_runtime.py:942` | integer | Sensor algoritmasi acisindan kritik | no | `measurement_metrics.vote_b` | partially_resolved | Vote kurali kodda yok |
| `vote_cal` | `2_Olcumler` | sensor_metric | Raw `VOTE_CAL`; calibration/cal adayina ait vote metriği olabilir | `mes_web/excel_runtime.py:943` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.vote_cal` | unresolved | `CAL` anlami kodda acik degil |
| `tot_x` | `2_Olcumler` | sensor_metric | Raw `TOT_BOS`; empty/bos aday toplam sayaci | `mes_web/excel_runtime.py:947`, `tests/test_mes_web_excel_runtime.py:43` | integer | Sensor debug ve replay dogrulama icin kritik | no | `measurement_metrics.tot_x` | partially_resolved | `x` canonical color degil, BOS/empty adayidir |
| `tot_cal` | `2_Olcumler` | sensor_metric | Raw `TOT_CAL`; calibration/cal toplam sayaci olabilir | `mes_web/excel_runtime.py:948` | integer | Sensor debug icin kritik | no | `measurement_debug_metrics.tot_cal` | unresolved | `CAL` anlami kodda acik degil |
| `sample_cycle_tag` | `5_OEE_Anliklari` | label | OEE snapshot'in kaynak/sample etiketi | `mes_web/excel_runtime.py:450`, `mes_web/excel_runtime.py:1560`, `docs/workbook-schema.md` | string | OEE snapshot izlenebilirligi icin kritik | yes | `oee_snapshots.sample_cycle_tag` | resolved | Event id veya cycle id gibi kullanilmamali |
| `finalization_reason` | `4_Uretim_Tamamlanan` | enum | Production completion final karar gerekcesi | `mes_web/excel_runtime.py:425-441`, `mes_web/oee_state.py:3436-3447`, `mes_web/oee_state.py:5624-5654`, `tests/test_mes_web_excel_runtime.py:253`, `tests/test_mes_web_excel_runtime.py:325`, `tests/test_mes_web_oee_state.py:756-842` | string_enum | Domain/audit icin kritik | yes | `production_completions.finalization_reason` ve lookup `production_finalization_reasons` | resolved | Kalite kodu degil; `final_quality_code` ile karistirilmamali |

## 10. Veri Sozlugune Aktarilacak Nihai Oneriler

| Alan grubu | Veri sozlugu karari | Target onerisi |
| --- | --- | --- |
| `source_log_file` | Measurement provenance alani olarak belgelenir | `measurements.source_log_file` |
| `search_hint*` | Sensor algorithm context olarak belgelenir | `measurement_debug_metrics` |
| `core_n`, `obj_n` | Sensor sample/count metrikleri olarak belgelenir | `measurement_metrics` |
| `median_nearest`, `med_d_*` | Median/distance karar metrikleri olarak belgelenir | `measurement_metrics` |
| `x_r`, `x_g`, `x_b`, `med_obj`, `core_str_*` | Debug/detail metriği olarak belgelenir | `measurement_debug_metrics` |
| `vote_*`, `tot_*` | Vote/total karar metrikleri olarak belgelenir | `measurement_metrics` veya `measurement_debug_metrics` |
| `sample_cycle_tag` | OEE snapshot source label olarak belgelenir | `oee_snapshots.sample_cycle_tag` |
| `finalization_reason` | Production finalization reason enum'u olarak belgelenir | `production_completions.finalization_reason` |

Data dictionary notlari:

- `*_tr` alanlari canonical kod yerine gecmemelidir.
- `x` alanlari `BOS`/empty adayina bagli teknik sensor metriği olarak ele alinmalidir.
- `finalization_reason` icin lookup sozlugu olusturulabilir, ancak kalite lookup'i ile birlestirilmemelidir.
- Sensor debug alanlari raporlama ihtiyacina gore JSON/detail alaninda tutulabilir; ilk fazda ana domain tablosuna zorunlu kolon yapilmamalidir.

## 11. Hala Belirsiz Kalan Alanlar

Tam netlesmeyen alanlar:

| field_name | Belirsizlik | Onerilen aksiyon |
| --- | --- | --- |
| `score_nearest` | Adindan skor bekleniyor, test payload'inda aday etiketi gibi deger var | Firmware/sensor payload kontratinda veri tipi netlestir |
| `vote_cal` | `CAL` acilimi kodda belgeli degil | Sensor algoritmasi sahibiyle calibration anlami dogrula |
| `tot_cal` | `CAL` toplam sayacinin anlami kodda belgeli degil | Sensor algoritmasi sahibiyle calibration anlami dogrula |
| `search_hint_win` | Pencere boyutu mu, pencere sonucu mu, sayac mi net degil | Firmware payload sozlesmesine ekle |
| `search_hint_second` | Ikincil hint mi, ikinci seviye karar mi net degil | Firmware payload sozlesmesine ekle |
| `search_hint_strong` | Flag mi sayac mi net degil | Veri tipi ve olasi degerleri belgeleyin |
| `med_obj` | Object median/object varligi metriğinin formulu yok | Sensor algoritmasi dokumaniyla acikla |
| `core_str_min`, `core_str_max` | Signal strength birimi ve araligi yok | Sensor metrik birimlerini belgeleyin |

## 12. Riskler ve Koruyucu Kurallar

| Risk | Etki | Koruyucu kural |
| --- | --- | --- |
| Sensor debug metrikleri ana MES domain tablosuna tasinir | Domain modeli sisir ve sensor firmware'e asiri bagimli olur | Bu alanlar `measurement_metrics`, `measurement_debug_metrics` veya JSON/detail katmaninda tutulmali |
| `x` alanlari canonical renk gibi yorumlanir | Renk lookup ve kalite raporu bozulabilir | `x`, `BOS`/empty teknik adayi olarak belgelenmeli |
| `sample_cycle_tag` event id sanilir | OEE replay ve event iliskileri yanlis kurulur | Source/sample label olarak tutulmali |
| `finalization_reason` kalite kodu sanilir | Kalite sonucu ile karar gerekcesi karisir | `final_quality_code` ve `finalization_reason` ayrimi korunmali |
| `score_nearest` numeric skor gibi zorlanir | Backfill/import sirasinda veri kaybi olur | Veri tipi `string_or_decimal` olarak kalmali, kontrat netlesince daraltilmali |
| Workbook transactional kaynak gibi okunur | Runtime state ve audit/projection siniri bozulur | Workbook sadece audit/projection/backfill/replay kaynagi olarak kullanilmali |
| Raw sensor metrikleri normal raporlama DB'sine karisir | Raporlama karmasikligi ve performans sorunu olusur | Raporlama icin ozet, debug icin detail/archive ayrimi yapilmali |

## 13. Uygulanacak Sonraki 5 Is

1. Sensor firmware/Mega payload sozlesmesi icin `SEARCH_HINT_*`, `SCORE_NEAREST`, `CAL`, `CORE_STR_*` ve `MED_OBJ` alanlarinin resmi anlamlarini kisa bir tabloyla dogrula.
2. `measurement_metrics` ve `measurement_debug_metrics` ayrimini veri sozlugu seviyesinde netlestir; hangi alanlar rapora, hangileri debug'a girecek belirle.
3. `finalization_reason` icin `production_finalization_reasons` lookup taslagini hazirla ve kalite lookup'undan ayri tut.
4. `sample_cycle_tag` icin kabul edilen formatlari belgeleyerek `tablet:*` ve `runtime:*` kaynaklarini veri sozlugune ekle.
5. Backfill/replay kontrol listesine sensor detail alanlari icin "opsiyonel debug validation" seviyesi ekle; bu alanlari zorunlu import kosulu yapma.
