# Canonical Work Order Model

## 1. Amac

Bu dokuman, MES projesinde FERP import, runtime `workOrders`, workbook `7_Is_Emirleri` projection'i, OEE hesaplari, operational inventory ve FERP export arasindaki is emri modelini netlestirir.

Bu dokuman migration script'i, SQL DDL, kod degisikligi veya Excel sablonu degisikligi degildir. Sadece canonical is emri modelinin dokumantasyonudur.

Ana kararlar:

- Gunluk workbook canli transactional DB degildir; audit/projection/backfill/replay kaynagidir.
- `ferp_work_orders.json` import staging kaynagidir.
- FERP `lbl...` alanlari canonical MES kolonlari degildir.
- FERP label alanlari sadece staging/mapping sinirinda kalir.
- Canonical is emri modeli `work_orders`, `work_order_materials`, `work_order_operations` olarak ayrilmalidir.
- `oee_runtime_state.json > workOrders` canli runtime state'tir; gecmis kayit kaynagi degildir.
- `7_Is_Emirleri` workbook projection'idir; canonical `work_orders` modelinin yerine gecmez.

## 2. Mevcut Is Emri Kaynaklari

| Kaynak | Mevcut rol | Is emri acisindan anlam | Hedef sahiplik | Not |
|---|---|---|---|---|
| `mes_web/ferp_import/ferp_work_orders.json` | Import staging dosyasi | FERP'ten veya test import klasorunden gelen label'li/yarim normalize is emirleri | `ferp_import_batches`, `ferp_import_work_orders` | Canonical kaynak degil; import kontrati |
| `oee_runtime_state.json > workOrders` | Runtime state | Kuyruk, aktif is, tamamlanan son is, inventory ve transition bilgisi | current/projection state | Gecmis kayit kaynagi degil |
| `7_Is_Emirleri` | Workbook projection | Runtime is emrinin gunluk gorunum satiri | `work_order_projection` | Canonical `work_orders` yerine gecmez |
| `8_Depo_Stok` | Operational inventory projection | MES calisma anindaki stok/komponent yansimasi | `operational_inventory_projection` | Resmi ERP stok kaynagi degil |
| `4_Uretim_Tamamlanan` | Production completion audit/projection | Tamamlanan uretim kaydi | `production_completions` | Is emri kapanisini kanitlayan audit/projection kaynagi |
| `5_OEE_Anliklari` | Calculated OEE snapshot | OEE zaman serisi/snapshot | `oee_snapshots` | Is emri event'i degil |
| FERP export adaylari | Integration outbox | Tamamlanan is emrinden FERP'e gonderilecek cikti | `ferp_export_outbox`, `ferp_export_files`, `material_movement_candidates` | Export siniri canonical modelden ayrilmali |

## 3. Is Emri Katmanlari

| Katman | Girdi | Islem | Cikti | Sahiplik |
|---|---|---|---|---|
| FERP Import Staging | `ferp_work_orders.json`, FERP label payload | Label dogrulama, kaynak dosya ve batch bilgisiyle staging'e alma | `ferp_import_batches`, `ferp_import_work_orders` | Integration boundary |
| Canonical Work Order | Staging satiri veya elle/ileride API ile gelen normalize is emri | MES domain alanlarina map etme | `work_orders` | MES domain |
| Work Order Materials | Is emri materials/requirements bloklari | Bilesen, renk, miktar ve match key ayrimi | `work_order_materials` | MES domain |
| Work Order Operations | Is emri operations bloklari ve operasyon masterdata | Istasyon, operasyon sirasi, standart sure ve OEE kapsami ayrimi | `work_order_operations` | MES domain |
| Runtime WorkOrders State | Canonical/projection icin secilen aktif kuyruk | Aktif/kuyruk/tamamlanan calisma bellegi | current state/projection | Runtime engine |
| Workbook Projection | Runtime state snapshot | Gunluk workbook'a gorunum yazma/upsert | `7_Is_Emirleri` | Audit/projection |
| FERP Export | Completion, kalite, stok hareketi adaylari | Outbox dosyasi veya export paketi uretme | `ferp_export_outbox`, `ferp_export_files`, `material_movement_candidates` | Integration boundary |

## 4. FERP Import Staging Modeli

FERP import staging katmani, FERP label isimlerini ve kaynak payload izini korur. Bu katman MES domain modelinin kendisi degildir.

| Staging unsuru | Kaynak | Islem | Cikti | Not |
|---|---|---|---|---|
| Import batch | Import dosyasi/klasoru | Dosya, zaman ve kaynak sistem bilgisini kaydetme | `ferp_import_batches` | Birden cok is emri ayni batch altinda gruplanabilir |
| Work order raw row | `orders[]`, `ferp_labels`, `requirements`, `materials`, `operations` | Ham FERP payload'ini saklama ve validation sonucu ekleme | `ferp_import_work_orders` | FERP label alanlari burada kalir |
| Label validation | `ferp_labels.py` label katalogu | Required label ve bilinmeyen label kontrolu | validation warning/error | Bilinmeyen label canonical modele sessiz sizmamalidir |
| Mapping candidate | Staging row | Canonical alan adaylarini cikarma | normalize edilmis is emri taslagi | Mapping acik dokumante edilmelidir |

FERP label mapping ornekleri:

| FERP label veya alan | Canonical aday alan | Kural |
|---|---|---|
| `lblMMFB0_NUMBER` | `source_order_id`, gerekiyorsa `work_order_id` adayi | FERP kaynak is emri numarasi olarak ele alinmali |
| `lblMMFB0_QTY` | `target_qty` | Pozitif sayi olmali |
| `lblMTM00_CODE` | `stock_code` veya `product_code` | `products` masterdata ile eslesmeli |
| `lblMTM00_NAME` | `stock_name` | Display snapshot olabilir; stabil code yerine gecmez |
| `lblMUNT0_CODE` | `uom` | Birim kodu lookup adayi |
| `lblMMFB0_DESC` | `notes` | Serbest aciklama |
| `cycle_time_sec` | `ideal_cycle_ms` adayi | ms-first hedefe cevrilerek ele alinmali |
| `materials[].itemCode` | `work_order_materials.item_code` | Malzeme/bilesen kodu |
| `materials[].color` | `work_order_materials.color_code` | `colors` lookup adayi |
| `operations[].stationId` | `work_order_operations.station_id` | `stations` masterdata ile eslesmeli |
| `operations[].standardTimeSec` | `work_order_operations.ideal_cycle_ms` veya `planned_duration_ms` adayi | Anlami operasyon seviyesinde dogrulanmali |

## 5. Canonical Work Order Modeli

Canonical work order modeli, MES ic domain modelidir. FERP label isimleri bu katmanda kolon adi olarak kullanilmaz.

`work_orders` tablosu is emrinin ana kimligini, kaynak izini, urun/stok referansini, hedef miktari ve durumunu tutar. Bu tablo runtime queue'nun veya workbook projection'in birebir kopyasi olmamalidir.

Temel kurallar:

- `work_order_id` canonical ana kimliktir.
- `source_system`, `source_file`, `source_order_id` import izini tutar.
- `stock_code` ve `product_code` masterdata `products` ile eslestirilmelidir.
- `status_code` `work_order_statuses` lookup ile eslestirilmelidir.
- `target_qty` pozitif sayi olmalidir.
- FERP `lbl...` alanlari sadece staging/mapping tarafinda kalmalidir.

## 6. Work Order Materials Modeli

`work_order_materials`, is emrinin malzeme, urun veya bilesen ihtiyaclarini ayri tutar. Bu ayrim, paket/komponent bazli is emirleri ve operational inventory kontrolleri icin gereklidir.

Temel kurallar:

- Her satir bir is emrine bagli malzeme veya bilesen ihtiyacidir.
- `item_code` stabil is kodudur; display isimleri `item_name` alaninda kalir.
- `color_code` `colors` lookup ile eslesmeye adaydir.
- `qty_per_unit` bir uretim birimi icin gereken miktardir.
- `required_qty`, hedef miktar ve birim ihtiyacindan hesaplanabilir projection/plan alanidir.
- `match_key`, runtime inventory eslestirmesine yardimci olabilir; canonical kimlik yerine gecmez.

## 7. Work Order Operations Modeli

`work_order_operations`, is emrinin operasyon, istasyon, standart sure ve OEE baglamini ayirir.

Temel kurallar:

- `operation_code` veya `operation_seq` operasyon sirasini netlestirir.
- `station_id` `stations` masterdata ile eslesmelidir.
- `ideal_cycle_ms` ve `planned_duration_ms` ms-first yaklasimiyla belgelenmelidir.
- `oee_scope`, bu operasyonun OEE hesap kapsaminda nasil kullanilacagini gosterir.
- Operasyon masterdata ile is emri operasyon satiri karistirilmamalidir; is emri operasyonu planlanan/atanan operasyon snapshot'i olabilir.

## 8. Runtime WorkOrders State Ayrimi

Runtime `workOrders` state, canli calisma bellegidir. Bu state kuyruktaki, aktif ve tamamlanan son is emrini yonetir; gecmis kayit kaynagi olarak tasarlanmamalidir.

| Runtime alan ailesi | Anlam | Canonical karsilik | Not |
|---|---|---|---|
| `ordersById` | Runtime is emri sozlugu | `work_orders` icin kaynak adayi degil; current/projection state | Import sonrasi normalize gorunum olabilir |
| `orderSequence` | Kuyruk sirasi | Projection/current queue | Tarihsel event log yerine gecmez |
| `activeOrderId` | Aktif is emri referansi | current state | Canonical durumun gecici yansimasi |
| `lastCompletedOrderId`, `lastCompletedAt` | Son tamamlanan is izi | completion projection | Gecmis completion tablosu yerine gecmez |
| `transitionLog` | Runtime durum gecisi izi | `work_order_events` adayi | Kalicilik gerekecekse event tablosuna ayrilmali |
| `completionLog` | Runtime completion izi | `production_completions`/`work_order_events` adayi | Workbook audit ile birlikte dusunulmeli |
| `inventoryByProduct` | MES operational inventory state | `operational_inventory_projection` | Resmi ERP stok kaynagi degil |

DB'ye tasinacaksa `current_state` veya snapshot/projection mantigiyla tasinmalidir; history source olarak ele alinmamalidir.

## 9. `7_Is_Emirleri` Workbook Projection Ayrimi

`7_Is_Emirleri`, runtime `workOrders` state'inden uretilen gunluk workbook projection'idir. Bu sheet canonical `work_orders` tablosunun yerine gecmez.

| Workbook alan ailesi | Rol | Canonical ile iliski | Not |
|---|---|---|---|
| Kimlik alanlari | `work_order_record_id`, `order_id` | `order_id` canonical is emrine referans olabilir; `work_order_record_id` projection id'dir | Projection id canonical kimlik degildir |
| Durum alanlari | `status_code`, `status_tr`, `transition_reason` | `status_code` lookup ile eslesir | `status_tr` label snapshot'tir |
| Miktar alanlari | `target_qty`, `fulfilled_qty`, `production_qty`, `inventory_consumed_qty` | Target canonical; counter alanlari runtime/projection | Backfill icin faydali |
| Kalite alanlari | `good_qty`, `rework_qty`, `scrap_qty` | Quality/completion projection | Kalite kodu detayinin yerine gecmez |
| Sure alanlari | `ideal_cycle_ms`, `planned_duration_ms`, `runtime_ms`, `unplanned_downtime_ms` | ms-first projection | `*_sec` alanlari uyumluluk/turetilmis |
| OEE alanlari | `availability_pct`, `performance_pct`, `quality_pct`, `oee_pct` | Calculated projection | Snapshot/event degil, hesaplanmis gorunum |

## 10. OEE ile Is Emri Iliskisi

OEE hesaplari is emrine baglanabilir, fakat is emri modeli OEE snapshot tablosu olmamalidir.

| OEE unsuru | Is emri ile iliski | Hedef |
|---|---|---|
| `ideal_cycle_ms` | Is emri operasyonundan veya import standard time bilgisinden gelebilir | `work_order_operations.ideal_cycle_ms`, projection alanlari |
| `planned_duration_ms` | Hedef miktar ve standart sureden tureyebilir | `work_order_operations.planned_duration_ms`, `work_order_projection.planned_duration_ms` |
| Availability/Performance/Quality/OEE yuzdeleri | Runtime metriklerden hesaplanir | `work_order_projection`, `oee_snapshots` |
| `5_OEE_Anliklari` | Calculated OEE snapshot/time-series | `oee_snapshots` |

`5_OEE_Anliklari` is emri olayi degildir. Is emri baglami varsa referans olarak tasinabilir; event kimligi gibi kullanilmamalidir.

## 11. Operational Inventory ile Is Emri Iliskisi

Operational inventory, MES calisma anindaki stok/komponent yansimasidir. `8_Depo_Stok` resmi ERP stok kaynagi degildir.

| Iliski | Aciklama | Hedef |
|---|---|---|
| Material requirement | Is emrinin ihtiyac duydugu malzeme/bilesen | `work_order_materials` |
| Runtime stock check | Aktif is emri baslatilirken veya tamamlanirken kullanilan stok kontrolu | runtime `inventoryByProduct` |
| Inventory consumed | Is emri icin tuketilen operasyonel stok miktari | `work_order_projection.inventory_consumed_qty`, `material_movement_candidates` |
| ERP stock movement candidate | FERP'e gonderilebilecek stok hareketi adayi | `material_movement_candidates` |

Operational inventory projection, FERP resmi stok defterinin yerine gecmemelidir.

## 12. Quality / Completion ile Is Emri Iliskisi

`4_Uretim_Tamamlanan` production completion audit/projection kaynagidir. Is emri completion karari, kalite sonucundan ayridir.

| Alan/olay | Is emri ile iliski | Not |
|---|---|---|
| `completed_at` | Is emrinin tamamlanma zamani | Projection ve completion audit icin kritik |
| `good_qty`, `rework_qty`, `scrap_qty` | Completion/quality sayaclari | `quality_codes` ile anlamlandirilir |
| `finalization_reason` | Production finalization decision reason | Kalite kodu yerine gecmez |
| `pending_approval` | Otomatik tamamlanma sonrasi operator onayi bekleyen durum | Mevcut runtime davranisi olarak korunur |
| `completed` | Operator kabulunden sonra kapanan durum | Export adaylarini tetikleyebilir |

## 13. FERP Export ile Is Emri Iliskisi

FERP export, canonical work order ve completion sonuclarindan uretilen integration outbox surecidir. FERP label alanlari export sinirinda yeniden map edilir; MES domain kolonlarina sizdirilmaz.

| Export hedefi | Girdi | Islem | Cikti |
|---|---|---|---|
| `ferp_export_outbox` | Completed is emri, completion, kalite, stok hareketi adaylari | Gonderilecek is paketi olusturma | Bekleyen export kaydi |
| `ferp_export_files` | Outbox kaydi | Dosya/format uretimi ve teslim bilgisi | Export dosya izi |
| `material_movement_candidates` | Is emri material consumption ve operational inventory | FERP stok hareketi adayi uretme | Onaylanabilir stok hareketi |

Export siniri staging + canonical model + outbox olarak ayrilmalidir.

## 14. Alan Seviyesi Model Taslagi

Bu bolum SQL DDL degildir. Alanlar hedef model taslagi ve veri sozlugu hazirligi icindir.

### `work_orders`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `work_order_id` | Is emri kimligi | Canonical MES is emri ana kimligi | string | yes | MES domain | staging/runtime mapping | `work_orders.work_order_id` | yes | no | no | no | yes | `work_order_record_id` yerine gecmez; asil canonical id |
| `source_system` | Kaynak sistem | Is emrinin geldigi sistem | string | yes | integration | `ferp_work_orders.json.source.system` | `work_orders.source_system` | no | yes | no | no | yes | Ornek: `FERP` |
| `source_file` | Kaynak dosya | Import edilen dosya adi/yolu | string | no | integration | import runtime source | `work_orders.source_file` | no | no | no | yes | yes | Provenance alanidir |
| `source_order_id` | Kaynak is emri no | FERP veya dis kaynak is emri numarasi | string | conditional | integration | `lblMMFB0_NUMBER` | `work_orders.source_order_id` | no | no | no | yes | yes | Canonical id ile ayni olabilir ama ayni kabul edilmemeli |
| `erp_type` | ERP tipi | Import/ERP siniflandirmasi | string | no | integration | import payload/runtime order | `work_orders.erp_type` | no | yes | no | no | yes | FERP/ERP ayrimi icin |
| `stock_code` | Stok kodu | Uretilecek veya takip edilecek stok kodu | string | yes | MES domain | `lblMTM00_CODE`, runtime order | `work_orders.stock_code` | no | yes | no | no | yes | `products` ile eslesmeli |
| `stock_name` | Stok adi | Stok/urun display adi | string | no | integration/domain | `lblMTM00_NAME`, runtime order | `work_orders.stock_name` | no | no | no | yes | yes | Stabil code yerine gecmez |
| `product_code` | Urun kodu | MES urun kodu | string | conditional | MES domain | import/runtime mapping | `work_orders.product_code` | no | yes | no | no | yes | `products.product_code` ile eslesmeli |
| `product_color` | Urun rengi | Urun renk kodu veya label snapshot'i | string | conditional | MES domain | import/runtime order | `work_orders.product_color` | no | yes | no | no | yes | `colors` lookup adayi |
| `target_qty` | Hedef miktar | Is emri hedef uretim miktari | number | yes | MES domain | `lblMMFB0_QTY`, runtime order | `work_orders.target_qty` | no | no | no | no | yes | Pozitif sayi olmali |
| `uom` | Olcu birimi | Hedef miktar birimi | string | conditional | integration/domain | `lblMUNT0_CODE` | `work_orders.uom` | no | yes | no | no | yes | Birim lookup adayi |
| `status_code` | Durum kodu | Is emri durumu | string | yes | MES domain | runtime status | `work_orders.status_code` | no | yes | no | yes | yes | `work_order_statuses` ile eslesmeli |
| `priority` | Oncelik | Is emri kuyruk/oncelik bilgisi | integer | no | MES domain | import/runtime mapping | `work_orders.priority` | no | no | no | no | yes | Yoksa queue sirasi kullanilabilir |
| `planned_start_at` | Planlanan baslama | Planlanan baslangic zamani | datetime_iso | no | planning/domain | import/planning source | `work_orders.planned_start_at` | no | no | no | no | yes | Kaynakta yoksa bos kalabilir |
| `planned_end_at` | Planlanan bitis | Planlanan bitis zamani | datetime_iso | no | planning/domain | import/planning source | `work_orders.planned_end_at` | no | no | no | no | yes | Kaynakta yoksa bos kalabilir |
| `created_at` | Olusturma zamani | Canonical kayit olusturma zamani | datetime_iso | yes | MES domain | canonical persistence | `work_orders.created_at` | no | no | no | yes | yes | Import zamaniyla karistirilmamali |
| `updated_at` | Guncelleme zamani | Canonical kayit son guncelleme zamani | datetime_iso | yes | MES domain | canonical persistence | `work_orders.updated_at` | no | no | no | yes | yes | Runtime update degil canonical update |
| `notes` | Notlar | Serbest aciklama | text | no | integration/domain | `lblMMFB0_DESC`, runtime notes | `work_orders.notes` | no | no | no | yes | yes | Label veya kullanici notu olabilir |

### `work_order_materials`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `work_order_material_id` | Is emri malzeme kimligi | Canonical material satir kimligi | string | yes | MES domain | generated/canonical | `work_order_materials.work_order_material_id` | yes | no | no | no | yes | Satir kimligi |
| `work_order_id` | Is emri kimligi | Bagli canonical is emri | string | yes | MES domain | `work_orders.work_order_id` | `work_order_materials.work_order_id` | no | yes | no | no | yes | Foreign/reference alanidir |
| `item_code` | Kalem kodu | Malzeme/urun/bilesen kodu | string | yes | MES domain | `materials[].itemCode`, requirements | `work_order_materials.item_code` | no | yes | no | no | yes | Product/component lookup adayi |
| `item_name` | Kalem adi | Malzeme/urun/bilesen adi | string | no | integration/domain | `materials[].itemName` | `work_order_materials.item_name` | no | no | no | yes | yes | Display snapshot |
| `item_type` | Kalem tipi | Material/component/finished good ayrimi | string | conditional | MES domain | `materials[].itemType` | `work_order_materials.item_type` | no | yes | no | no | yes | Lookup adayi |
| `color_code` | Renk kodu | Malzeme veya komponent renk kodu | string | conditional | MES domain | `materials[].color` | `work_order_materials.color_code` | no | yes | no | no | yes | `colors` ile eslesmeli |
| `qty_per_unit` | Birim ihtiyac | Bir uretim birimi icin gereken miktar | number | yes | MES domain | `materials[].qtyPerUnit` | `work_order_materials.qty_per_unit` | no | no | no | no | yes | Pozitif olmali |
| `required_qty` | Gerekli toplam miktar | Is emri hedefi icin gereken toplam miktar | number | conditional | MES domain | calculated from target | `work_order_materials.required_qty` | no | no | no | no | yes | `target_qty * qty_per_unit` adayi |
| `uom` | Olcu birimi | Malzeme birimi | string | conditional | MES domain | import/material mapping | `work_order_materials.uom` | no | yes | no | no | yes | Birim lookup adayi |
| `match_key` | Eslesme anahtari | Runtime inventory ile eslesme yardimci anahtari | string | no | runtime/domain | material + color mapping | `work_order_materials.match_key` | no | no | yes | no | yes | Canonical kimlik yerine gecmez |
| `notes` | Notlar | Material satir aciklamasi | text | no | integration/domain | import/material notes | `work_order_materials.notes` | no | no | no | yes | yes | Serbest metin |

### `work_order_operations`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `work_order_operation_id` | Is emri operasyon kimligi | Canonical operation satir kimligi | string | yes | MES domain | generated/canonical | `work_order_operations.work_order_operation_id` | yes | no | no | no | yes | Satir kimligi |
| `work_order_id` | Is emri kimligi | Bagli canonical is emri | string | yes | MES domain | `work_orders.work_order_id` | `work_order_operations.work_order_id` | no | yes | no | no | yes | Foreign/reference alanidir |
| `operation_code` | Operasyon kodu | Stabil operasyon kodu | string | conditional | MES domain | `operations[].opNo`, masterdata | `work_order_operations.operation_code` | no | yes | no | no | yes | `operation_definitions` ile eslesmeli |
| `operation_name_tr` | Operasyon adi | Turkce operasyon gorunum adi | string | no | MES domain | `operations[].operationName` | `work_order_operations.operation_name_tr` | no | no | no | yes | yes | Display snapshot; canonical code yerine gecmez |
| `work_center_code` | Is merkezi kodu | Operasyonun bagli oldugu is merkezi | string | conditional | MES domain | operation/masterdata mapping | `work_order_operations.work_center_code` | no | yes | no | no | yes | Lines/stations ile iliskili |
| `station_id` | Istasyon kimligi | Operasyonun calisacagi istasyon | string | conditional | MES domain | `operations[].stationId` | `work_order_operations.station_id` | no | yes | no | no | yes | `stations` ile eslesmeli |
| `operation_seq` | Operasyon sirasi | Is emri icindeki operasyon sirasi | integer | conditional | MES domain | `operations[].opNo` | `work_order_operations.operation_seq` | no | no | no | no | yes | Siralama icin |
| `ideal_cycle_ms` | Ideal cycle ms | Operasyon ideal cycle suresi | duration_ms | conditional | MES domain | `standardTimeSec`, `cycle_time_sec` | `work_order_operations.ideal_cycle_ms` | no | no | no | no | yes | ms-first; sec kaynaklar cevrilmeli |
| `planned_duration_ms` | Planlanan sure ms | Operasyon planlanan sure | duration_ms | no | MES domain | calculated/planning | `work_order_operations.planned_duration_ms` | no | no | no | no | yes | ms-first |
| `oee_scope` | OEE kapsami | OEE hesap kapsam kodu | string | no | MES domain | operation/masterdata mapping | `work_order_operations.oee_scope` | no | yes | no | no | yes | `oee_scopes` lookup |
| `active_flag` | Aktif bayragi | Operasyonun aktif kullanilip kullanilmadigi | boolean | yes | MES domain | canonical/masterdata | `work_order_operations.active_flag` | no | yes | no | no | yes | Aktiflik flag'i |
| `notes` | Notlar | Operasyon aciklamasi | text | no | integration/domain | operation notes | `work_order_operations.notes` | no | no | no | yes | yes | Serbest metin |

### `work_order_projection`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `work_order_record_id` | Projection satir kimligi | Workbook work order projection id | integer | yes | runtime_projection | `7_Is_Emirleri.work_order_record_id` | `work_order_projection.work_order_record_id` | yes | no | yes | yes | yes | Canonical is emri kimligi degildir |
| `order_id` | Is emri referansi | Runtime/canonical is emri referansi | string | yes | runtime_projection | `7_Is_Emirleri.order_id` | `work_order_projection.order_id` | no | yes | yes | yes | yes | `work_orders.work_order_id` ile eslesebilir |
| `status_code` | Durum kodu | Projection anindaki durum | string | yes | runtime_projection | `7_Is_Emirleri.status_code` | `work_order_projection.status_code` | no | yes | yes | yes | yes | `work_order_statuses` lookup |
| `queued_at` | Kuyruk zamani | Is emri kuyruga alinma zamani | datetime_iso | conditional | runtime_projection | `7_Is_Emirleri.queued_at` | `work_order_projection.queued_at` | no | no | yes | yes | yes | ISO datetime |
| `started_at` | Baslama zamani | Is emri baslama zamani | datetime_iso | conditional | runtime_projection | `7_Is_Emirleri.started_at` | `work_order_projection.started_at` | no | no | yes | yes | yes | ISO datetime |
| `completed_at` | Tamamlanma zamani | Is emri tamamlanma zamani | datetime_iso | conditional | runtime_projection | `7_Is_Emirleri.completed_at` | `work_order_projection.completed_at` | no | no | yes | yes | yes | ISO datetime |
| `target_qty` | Hedef miktar | Projection hedef miktari | number | yes | runtime_projection | `7_Is_Emirleri.target_qty` | `work_order_projection.target_qty` | no | no | yes | yes | yes | Canonical target ile tutarli olmali |
| `fulfilled_qty` | Karsilanan miktar | Karsilanan toplam miktar | number | no | runtime_projection | `7_Is_Emirleri.fulfilled_qty` | `work_order_projection.fulfilled_qty` | no | no | yes | yes | yes | Runtime counter |
| `production_qty` | Uretim miktari | Uretilen miktar | number | no | runtime_projection | `7_Is_Emirleri.production_qty` | `work_order_projection.production_qty` | no | no | yes | yes | yes | Runtime/projection counter |
| `inventory_consumed_qty` | Tuketilen stok | Operasyonel stok tuketimi | number | no | runtime_projection | `7_Is_Emirleri.inventory_consumed_qty` | `work_order_projection.inventory_consumed_qty` | no | no | yes | yes | yes | Resmi ERP stok hareketi degildir |
| `good_qty` | Saglam miktar | GOOD miktari | number | no | runtime_projection | `7_Is_Emirleri.good_qty` | `work_order_projection.good_qty` | no | yes | yes | yes | yes | Quality count |
| `rework_qty` | Rework miktar | REWORK miktari | number | no | runtime_projection | `7_Is_Emirleri.rework_qty` | `work_order_projection.rework_qty` | no | yes | yes | yes | yes | Quality count |
| `scrap_qty` | Hurda miktar | SCRAP miktari | number | no | runtime_projection | `7_Is_Emirleri.scrap_qty` | `work_order_projection.scrap_qty` | no | yes | yes | yes | yes | Quality count |
| `availability_pct` | Availability yuzde | Calculated availability projection | decimal | no | runtime_projection | `7_Is_Emirleri.availability_pct` | `work_order_projection.availability_pct` | no | no | yes | yes | yes | OEE hesap sonucu |
| `performance_pct` | Performance yuzde | Calculated performance projection | decimal | no | runtime_projection | `7_Is_Emirleri.performance_pct` | `work_order_projection.performance_pct` | no | no | yes | yes | yes | OEE hesap sonucu |
| `quality_pct` | Quality yuzde | Calculated quality projection | decimal | no | runtime_projection | `7_Is_Emirleri.quality_pct` | `work_order_projection.quality_pct` | no | no | yes | yes | yes | OEE hesap sonucu |
| `oee_pct` | OEE yuzde | Calculated OEE projection | decimal | no | runtime_projection | `7_Is_Emirleri.oee_pct` | `work_order_projection.oee_pct` | no | no | yes | yes | yes | Event degil hesaplanmis projection |

## 15. State Transition ve Status Kurallari

Mevcut durum kodlari korunmalidir. Ek durumlar sadece ileride onerilebilir; mevcut davranisa zorunlu eklenmemelidir.

| status_code | Anlam | Gecis kaynagi | Kalicilik notu |
|---|---|---|---|
| `queued` | Is emri kuyrukta, henuz aktif degil | Import veya requeue | Canonical durum/projection |
| `active` | Is emri aktif calisiyor | Operator start veya runtime start | Runtime current state icin kritik |
| `pending_approval` | Hedef/kosul tamamlandi, operator onayi bekliyor | Runtime completion logic | Completion ile completed arasindaki karar durumu |
| `completed` | Is emri tamamlandi ve kabul edildi | Operator accept/finalization | Export adaylarini tetikleyebilir |
| `rolled_back` | Aktif/pending is geri alindi | Rollback action | Inventory iadesi ve transition log ile birlikte izlenmeli |
| `cancelled` | Iptal edildi | Ileri faz onerisi | Mevcut davranisa zorunlu eklenmemeli |
| `failed` | Basarisiz kapandi | Ileri faz onerisi | Mevcut davranisa zorunlu eklenmemeli |

Gecis kurallari:

- `queued -> active`: operator veya sistem baslatma islemi.
- `active -> pending_approval`: hedef miktar/komponent kosulu tamamlanir ve operator onayi gerekir.
- `pending_approval -> completed`: operator kabul/finalization karari.
- `active/pending_approval -> rolled_back`: rollback islemi ve operational inventory iadesi.
- `completed` durumundaki is emri tekrar runtime aktif is olarak ele alinmamalidir; gerekirse yeni canonical revizyon veya yeni is emri acilmalidir.

## 16. ID / Code / Reference Kurallari

| Alan ailesi | Kural | Not |
|---|---|---|
| Canonical id | `work_order_id` ana kimliktir | String kabul edilebilir; kaynak numara ile ayni olmak zorunda degildir |
| Projection id | `work_order_record_id` sadece workbook/projection satir kimligidir | Canonical is emri kimligi yerine kullanilmamalidir |
| Source reference | `source_system`, `source_file`, `source_order_id` import izini tutar | FERP ile izlenebilirlik icin gerekli |
| Product/stock code | `stock_code`, `product_code` masterdata `products` ile eslesmelidir | Display name yerine code kullanilmali |
| Status code | `status_code` `work_order_statuses` lookup ile eslesmelidir | `status_tr` label snapshot'tir |
| FERP labels | `lbl...` alanlari canonical kolon degildir | Sadece staging/mapping/outbox sinirinda kalir |
| Duration fields | `ideal_cycle_ms`, `planned_duration_ms` ms-first alanlardir | `*_sec` varsa turetilmis/uyumluluk olarak ele alinmali |

## 17. Backfill / Replay Acisindan Is Emri

Workbook canli transactional DB degildir; ancak audit/projection/backfill/replay icin kullanilabilir.

| Kaynak | Backfill/replay kullanimi | Sinir |
|---|---|---|
| `ferp_work_orders.json` | Import staging ve mapping replay | Ham/canonical ayrimi korunmali |
| `7_Is_Emirleri` | Runtime/projection son durum backfill adayi | Canonical `work_orders` yerine dogrudan kullanilmamali |
| `4_Uretim_Tamamlanan` | Completion audit backfill | Is emri kapanis kaniti olarak kullanilabilir |
| `5_OEE_Anliklari` | OEE time-series/snapshot backfill | Is emri event'i degil |
| `8_Depo_Stok` | Operational inventory projection replay | Resmi ERP stok bakiyesi degil |
| `99_Raw_Logs` | Debug/audit/archive incelemesi | Normal raporlama DB'sine tasinmamali |

Backfill yapilirken canonical model icin once mapping kurali, sonra validation, sonra replay sonucu dokumante edilmelidir.

## 18. SQL'e Geciste Tablo Karsiliklari

Bu bolum tablo karsiliklarini planlar; SQL DDL degildir.

| Mevcut kaynak/katman | Hedef tablo veya tablo grubu | Rol |
|---|---|---|
| `ferp_work_orders.json` import dosyasi | `ferp_import_batches`, `ferp_import_work_orders` | FERP import staging |
| FERP label katalogu/mapping | `ferp_label_mappings` | Label -> canonical mapping siniri |
| Canonical is emri | `work_orders` | MES domain is emri ana modeli |
| Material/requirement bloklari | `work_order_materials` | Is emri malzeme/bilesen ihtiyaclari |
| Operation bloklari | `work_order_operations` | Is emri operasyon/istasyon/sure modeli |
| Runtime `workOrders` current state | `current_work_order_state` veya projection tablolar | Canli state yansimasi |
| `7_Is_Emirleri` | `work_order_projection` | Gunluk projection/backfill |
| `8_Depo_Stok` | `operational_inventory_projection` | MES operational inventory projection |
| `4_Uretim_Tamamlanan` | `production_completions` | Completion audit/projection |
| `5_OEE_Anliklari` | `oee_snapshots` | Calculated OEE snapshot/time-series |
| FERP export adaylari | `ferp_export_outbox`, `ferp_export_files`, `material_movement_candidates` | Integration outbox |

## 19. Riskler ve Koruyucu Kurallar

| Risk | Etki | Koruyucu kural |
|---|---|---|
| FERP `lbl...` alanlarinin canonical MES kolonlarina sizmasi | Domain model FERP ekran isimlerine bagimli hale gelir | Label alanlari sadece staging/mapping/outbox sinirinda tutulur |
| `7_Is_Emirleri` sheet'inin canonical kaynak sanilmasi | Projection id ve runtime counter'lar ana modelle karisir | Workbook projection oldugu her dokumanda belirtilir |
| Runtime `workOrders` state'in history source gibi kullanilmasi | Gecmis kayit eksik veya yanlis kurulabilir | Runtime sadece current/projection state olarak ele alinir |
| `8_Depo_Stok`un ERP stok defteri sanilmasi | FERP stok hareketleri hatali yorumlanir | Sadece MES operational inventory projection olarak kullanilir |
| Completion ve kalite kararinin karismasi | `finalization_reason` kalite kodu gibi kullanilir | Finalization reason ve quality code ayri tutulur |
| OEE snapshot'in is emri event'i sanilmasi | Time-series verisi event log'a yanlis tasinir | `5_OEE_Anliklari` calculated snapshot olarak kalir |
| Duration birimlerinin karismasi | OEE ve plan sureleri yanlis hesaplanir | `*_ms` birincil, `*_sec` uyumluluk/turetilmis alan kabul edilir |
| Bilinmeyen FERP label'larinin sessiz kabul edilmesi | Mapping hatalari fark edilmez | Validation warning zorunlu hale getirilir |

Data quality kurallari:

- `work_order_id` canonical ana kimliktir.
- `work_order_record_id` projection id'dir; canonical is emri kimligi degildir.
- `stock_code` ve `product_code` masterdata `products` ile eslesmelidir.
- `status_code` `work_order_statuses` lookup ile eslesmelidir.
- `target_qty` pozitif sayi olmalidir.
- `ideal_cycle_ms` ve `planned_duration_ms` ms-first yaklasimiyla ele alinmalidir.
- FERP label mapping bilinmeyen label gorurse validation uyarisi uretmelidir.
- FERP import staging ile canonical model arasinda acik mapping olmalidir.

## 20. Uygulanacak Sonraki 5 Is

1. `ferp_work_orders.json` icindeki FERP label alanlari icin `ferp_import_work_orders -> work_orders` mapping tablosunu dokumante et.
2. `work_order_materials` icin `products`, `colors` ve operational inventory `match_key` eslesme kurallarini netlestir.
3. `work_order_operations` icin `operation_definitions`, `stations`, `ideal_cycle_ms` ve `oee_scope` kaynaklarini ayir.
4. `7_Is_Emirleri` projection alanlari ile canonical `work_orders` alanlari arasindaki backfill/replay karar tablosunu hazirla.
5. FERP export outbox icin completion, material movement ve label mapping sinirlarini ayri bir dokumanda detaylandir.
