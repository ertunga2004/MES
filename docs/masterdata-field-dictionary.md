# Masterdata Field Dictionary

## 1. Amac

Bu dokuman, mevcut `0_Tanimlamalar` sheet'inden gelen masterdata bloklari ve hedef `FERP_MasterData.xlsx` / SQL master tables icin alan seviyesinde veri sozlugu tanimlar.

Bu dokuman migration script'i, SQL DDL, kod degisikligi veya Excel sablonu degisikligi degildir. Sadece masterdata alan sozlugu dokumantasyonudur.

Temel kararlar:

- `0_Tanimlamalar` mevcut masterdata kaynagidir.
- Gunluk workbook uzun vadede masterdata kaynagi olarak buyutulmemelidir.
- Hedefte masterdata `FERP_MasterData.xlsx` veya SQL master tables icine ayrilmalidir.
- Runtime state, audit/event ve raw log alanlari masterdata'ya konmamalidir.
- FERP `lbl...` alanlari yalniz `ferp_label_mappings` sinirinda kalmalidir.

## 2. Kaynaklar

Dokuman kaynaklari:

- `docs/masterdata-design.md`
- `docs/data-dictionary-plan.md`
- `docs/workbook-schema.md`
- `docs/workbook-data-dictionary.md`
- `docs/database-plan.md`

Kod kaynaklari:

- `mes_web/masterdata.py`
- `mes_web/excel_runtime.py`
- `mes_web/oee_state.py`
- `mes_web/ferp_labels.py`

## 3. Mevcut Masterdata Kaynagi: `0_Tanimlamalar`

`0_Tanimlamalar`, mevcut sistemde workbook/template icindeki masterdata bloklarini tasir. `mes_web/masterdata.py` bu sheet'i blok bazli okur:

- Satir 1: blok adlari
- Satir 2: blok kolonlari
- Satir 3 ve sonrasi: veri satirlari
- Bir sonraki blok basligina kadar olan kolonlar ayni blok sayilir

Aktif okunan veya hedeflenen bloklar:

| Blok | Mevcut rol | Hedef tablo |
| --- | --- | --- |
| `operatorler` | Kiosk operator secim katalogu | `operators` |
| `istasyonlar` | Kiosk/default station katalogu | `stations` |
| `hatlar` | Hat katalogu | `lines` |
| `urunler` | Urun/stok/renk katalogu | `products` |
| `ariza_tipleri` | Kiosk fault secim katalogu | `fault_types` |
| `vardiyalar` | Vardiya katalogu | `shifts` |
| `renkler` | Renk lookup | `colors` |
| `kaynaklar` | Event source lookup | `sources` |
| `olay_tipleri` | Event type lookup | `event_types` |
| `karar_kaynaklari` | Decision source lookup | `decision_sources` |
| `mega_durumlari` | Mega state lookup | `mega_states` |
| `bakim*` / `maintenance*` | Bakim checklist katalogu | `maintenance_steps` |

Not:

- `masterdata.py` aktif olarak operator, station, fault option ve maintenance step kataloglarini okur.
- Bazi lookup listeleri su an `excel_runtime.py` icindeki hardcoded map'lerle de desteklenir.
- Bu dokuman, kod davranisini degistirmeden hedef alan sozlugunu sabitler.

## 4. Hedef Masterdata Yapisi

Hedef masterdata iki seviyede dusunulur:

| Seviye | Rol | Ornek |
| --- | --- | --- |
| `FERP_MasterData.xlsx` | Kod degismeden once ayrik masterdata workbook tasarimi | `MD_Operators`, `LK_Colors`, `MAP_FERPLabels` |
| SQL master tables | Ileride kaynak otoritesi olabilecek kalici masterdata katmani | `operators`, `stations`, `ferp_label_mappings` |

Hedef sheet/tablo gruplari:

- Master tables: `operators`, `stations`, `lines`, `products`, `operation_definitions`, `fault_types`, `maintenance_steps`, `shifts`, `devices`
- Lookup tables: `colors`, `sources`, `event_types`, `decision_sources`, `mega_states`, `work_order_statuses`, `quality_codes`, `oee_components`, `production_finalization_reasons`, `correlation_statuses`, `oee_scopes`
- FERP mapping: `ferp_label_mappings`

## 5. Masterdata Veri Sozlugu Kurallari

| Kural | Aciklama |
| --- | --- |
| `*_id` | Canonical tarafta string kabul edilebilir; workbook numeric gorunse bile normalize edilebilir |
| `*_code` | Stabil is kodudur; lookup ve entegrasyon iliskilerinde onceliklidir |
| `*_tr` | Goruntu/aciklama etiketi veya audit label snapshot'tir; canonical kod degildir |
| `active_flag` | Aktif kullanima acik satiri gosterir |
| `deprecated_flag` | Eski ama geriye uyumluluk icin tutulan satiri gosterir |
| Runtime alanlari | Aktif state, son gorulme, session, counter gibi alanlar masterdata'ya konmaz |
| Audit alanlari | Event zamani, completed_at, duration, raw payload gibi alanlar masterdata degildir |
| FERP labels | `lbl...` alanlari MES domain kolonlarina sizmaz; mapping tablosunda kalir |

Her tablo icin kullanilan alan formati:

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `example_field` | Ornek alan | Alanin is anlami | string | yes | masterdata | `0_Tanimlamalar` | `target_table.example_field` | no | no | no | no | yes | `ABC` | Sablon satirdir |

## 6. Master Tables Field Dictionary

### `operators`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `operator_id` | Operator id | Operator master kimligi | string | yes | masterdata | `0_Tanimlamalar.operatorler.operator_id` | `operators.operator_id` | yes | no | no | no | yes | `1` | Workbook numeric olabilir, canonical string kabul edilir |
| `operator_code` | Operator kodu | Stabil operator/personel kodu | string | yes | masterdata | `0_Tanimlamalar.operatorler.operator_code` | `operators.operator_code` | no | yes | no | no | yes | `OP-001` | Audit kayitlarinda snapshot olarak tekrar gorulebilir |
| `operator_name` | Operator adi | Gorunen operator adi | string | yes | masterdata | `0_Tanimlamalar.operatorler.operator_name` | `operators.operator_name` | no | no | no | no | yes | `Atanmadi` | Runtime session bilgisi degildir |
| `source_note` | Kaynak notu | Operator kaynagiyla ilgili serbest not | text | no | masterdata | `0_Tanimlamalar.operatorler.source_note` | `operators.source_note` | no | no | no | no | yes | `manual` | Mevcut blokta opsiyonel |
| `active_flag` | Aktif flag | Operator secilebilir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_Operators.active_flag` | `operators.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `stations`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `station_id` | Istasyon id | MES istasyon master kimligi | string | yes | masterdata | `0_Tanimlamalar.istasyonlar.station_id` | `stations.station_id` | yes | no | no | no | yes | `4` | Runtime station state degildir |
| `station_code` | Istasyon kodu | Stabil istasyon kodu | string | yes | masterdata | `0_Tanimlamalar.istasyonlar.station_code` | `stations.station_code` | no | yes | no | no | yes | `KSK-01` | Kiosk/default station eslesmesi icin |
| `station_name_tr` | Istasyon adi | Turkce gorunum adi | string | yes | masterdata | `0_Tanimlamalar.istasyonlar.station_name_tr` | `stations.station_name_tr` | no | no | no | no | yes | `Tablet Kiosk` | `*_tr` label'dir |
| `line_id` | Hat id | Istasyonun bagli oldugu hat | string | yes | masterdata | `0_Tanimlamalar.istasyonlar.line_id` | `stations.line_id` | no | yes | no | no | yes | `1` | `lines.line_id` referansi |
| `station_role` | Istasyon rolu | Sensor, robot, kiosk, packaging gibi rol | string | no | masterdata | `FERP_MasterData.xlsx.MD_Stations.station_role` | `stations.station_role` | no | yes | no | no | no | `operator_kiosk` | Runtime status degildir |
| `active_flag` | Aktif flag | Istasyon kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_Stations.active_flag` | `stations.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `lines`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `line_id` | Hat id | MES hat master kimligi | string | yes | masterdata | `0_Tanimlamalar.hatlar.line_id` | `lines.line_id` | yes | no | no | no | yes | `1` | Multi-line genisleme icin |
| `line_code` | Hat kodu | Stabil hat kodu | string | yes | masterdata | `0_Tanimlamalar.hatlar.line_code` | `lines.line_code` | no | yes | no | no | yes | `LINE-1` | Raporlama kirilimi |
| `line_name_tr` | Hat adi | Turkce hat gorunum adi | string | yes | masterdata | `0_Tanimlamalar.hatlar.line_name_tr` | `lines.line_name_tr` | no | no | no | no | yes | `Konveyor Hatti` | Label alanidir |
| `erp_ready` | ERP hazir flag | Hat FERP entegrasyonuna hazir mi | boolean | no | masterdata | `0_Tanimlamalar.hatlar.erp_ready` | `lines.erp_ready` | no | no | no | no | yes | `1` | Integration readiness metadata |
| `active_flag` | Aktif flag | Hat kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_Lines.active_flag` | `lines.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `products`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `product_id` | Urun id | MES urun master kimligi | string | yes | masterdata | `0_Tanimlamalar.urunler.product_id` | `products.product_id` | yes | no | no | no | yes | `P-RED` | Canonical string kabul edilir |
| `product_code` | Urun/stok kodu | MES/ERP urun veya stok kodu | string | yes | masterdata | `0_Tanimlamalar.urunler.product_code` | `products.product_code` | no | yes | no | no | yes | `BOX-RED` | Resmi stok miktari degildir |
| `product_name_tr` | Urun adi | Turkce urun gorunum adi | string | yes | masterdata | `0_Tanimlamalar.urunler.product_name_tr` | `products.product_name_tr` | no | no | no | no | yes | `Kirmizi Kutu` | Label alanidir |
| `color_id` | Renk id | Urunun varsayilan renk referansi | string | no | masterdata | `0_Tanimlamalar.urunler.color_id` | `products.color_id` | no | yes | no | no | yes | `1` | `colors.color_id` referansi |
| `product_type` | Urun tipi | Box, package, label, consumable gibi tip | string | no | masterdata | `FERP_MasterData.xlsx.MD_Products.product_type` | `products.product_type` | no | yes | no | no | no | `box` | FERP material mapping icin |
| `uom` | Birim | Urun olcu birimi | string | no | masterdata | `FERP_MasterData.xlsx.MD_Products.uom` | `products.uom` | no | yes | no | no | no | `ADET` | Birim lookup adayi |
| `active_flag` | Aktif flag | Urun kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_Products.active_flag` | `products.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `operation_definitions`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `operation_id` | Operasyon id | Operasyon master kimligi | string | yes | masterdata | `FERP_MasterData.xlsx.MD_OperationDefinitions.operation_id` | `operation_definitions.operation_id` | yes | no | no | no | no | `OP-PACK` | Mevcut `0_Tanimlamalar` icinde zorunlu aktif kaynak degil |
| `operation_code` | Operasyon kodu | MES/FERP operasyon kodu | string | yes | masterdata | FERP operasyon alanlari | `operation_definitions.operation_code` | no | yes | no | no | yes | `PACKAGING` | FERP/MES ortak kod olabilir |
| `operation_name_tr` | Operasyon adi | Turkce operasyon gorunum adi | string | yes | masterdata | `FERP_MasterData.xlsx.MD_OperationDefinitions.operation_name_tr` | `operation_definitions.operation_name_tr` | no | no | no | no | no | `Paketleme` | Label alanidir |
| `work_center_code` | Is merkezi kodu | FERP is merkezi kodu | string | no | masterdata | FERP operasyon alanlari | `operation_definitions.work_center_code` | no | yes | no | no | yes | `WC-PACK` | Integration lookup adayi |
| `work_station_code` | Is istasyonu kodu | FERP is istasyonu kodu | string | no | masterdata | FERP operasyon alanlari | `operation_definitions.work_station_code` | no | yes | no | no | yes | `WS-01` | MES station ile eslesebilir |
| `station_id` | MES istasyon id | Operasyonun bagli oldugu MES istasyonu | string | no | masterdata | `FERP_MasterData.xlsx.MD_OperationDefinitions.station_id` | `operation_definitions.station_id` | no | yes | no | no | no | `station2` | `stations.station_id` referansi |
| `standard_time_sec` | Standart sure saniye | Operasyon standart suresi | duration_sec | no | masterdata | `FERP_MasterData.xlsx.MD_OperationDefinitions.standard_time_sec` | `operation_definitions.standard_time_sec` | no | no | no | no | no | `15` | OEE planlama referansi |
| `active_flag` | Aktif flag | Operasyon kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_OperationDefinitions.active_flag` | `operation_definitions.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `fault_types`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fault_type_id` | Ariza tipi id | Fault type master kimligi | string | yes | masterdata | `0_Tanimlamalar.ariza_tipleri.fault_type_id` | `fault_types.fault_type_id` | yes | no | no | no | yes | `1` | Workbook numeric olabilir |
| `fault_type_code` | Ariza tipi kodu | Stabil fault type kodu | string | yes | masterdata | `0_Tanimlamalar.ariza_tipleri.fault_type_code` | `fault_types.fault_type_code` | no | yes | no | no | yes | `robot_arm_jam` | Kiosk fault seciminde kullanilir |
| `fault_category` | Ariza kategorisi | Fault kategori kodu/etiketi | string | yes | masterdata | `0_Tanimlamalar.ariza_tipleri.fault_category` | `fault_types.fault_category` | no | yes | no | no | yes | `MEKANIK` | Lookup adayi |
| `fault_reason_tr` | Ariza nedeni | Turkce fault gorunum etiketi | string | yes | masterdata | `0_Tanimlamalar.ariza_tipleri.fault_reason_tr` | `fault_types.fault_reason_tr` | no | no | no | no | yes | `Robot Kol Sikismasi` | `*_tr` label'dir |
| `default_station_id` | Varsayilan istasyon | Fault tipi icin varsayilan istasyon | string | no | masterdata | `0_Tanimlamalar.ariza_tipleri.default_station_id` | `fault_types.default_station_id` | no | yes | no | no | yes | `3` | `stations.station_id` referansi |
| `active_flag` | Aktif flag | Fault tipi secilebilir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_FaultTypes.active_flag` | `fault_types.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `maintenance_steps`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `step_id` | Bakim adim id | Maintenance step master kimligi | string | yes | masterdata | `FERP_MasterData.xlsx.MD_MaintenanceSteps.step_id` | `maintenance_steps.step_id` | yes | no | no | no | no | `opening_safety` | Hedef canonical id |
| `phase_code` | Faz kodu | Bakim fazi: opening/closing | string | yes | masterdata | `0_Tanimlamalar.<bakim*>.phase_code` | `maintenance_steps.phase_code` | no | yes | no | no | yes | `opening` | `masterdata.py` phase normalize eder |
| `step_code` | Adim kodu | Stabil checklist adim kodu | string | yes | masterdata | `0_Tanimlamalar.<bakim*>.step_code` veya default | `maintenance_steps.step_code` | no | yes | no | no | yes | `opening_safety` | Audit kaydi degil, sablon |
| `step_label_tr` | Adim etiketi | Turkce step gorunum etiketi | string | yes | masterdata | `0_Tanimlamalar.<bakim*>.step_label` veya default | `maintenance_steps.step_label_tr` | no | no | no | no | yes | `Guvenlik kontrolu` | `*_tr` label'dir |
| `step_order` | Adim sirasi | Checklist gosterim sirasi | integer | yes | masterdata | `FERP_MasterData.xlsx.MD_MaintenanceSteps.step_order` | `maintenance_steps.step_order` | no | no | no | no | no | `1` | Hedefte siralama icin |
| `required_flag` | Zorunlu flag | Step zorunlu mu | boolean | yes | masterdata | `0_Tanimlamalar.<bakim*>.required_flag` veya default | `maintenance_steps.required_flag` | no | no | no | no | yes | `1` | Session completion degildir |
| `active_flag` | Aktif flag | Step kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_MaintenanceSteps.active_flag` | `maintenance_steps.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `shifts`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `shift_id` | Vardiya id | Shift master kimligi | string | yes | masterdata | `0_Tanimlamalar.vardiyalar.shift_id` | `shifts.shift_id` | yes | no | no | no | yes | `1` | Aktif vardiya state'i degildir |
| `shift_code` | Vardiya kodu | Stabil vardiya kodu | string | yes | masterdata | `0_Tanimlamalar.vardiyalar.shift_code` | `shifts.shift_code` | no | yes | no | no | yes | `SHIFT-A` | Runtime state bu kodu referanslar |
| `shift_name_tr` | Vardiya adi | Turkce vardiya gorunum adi | string | yes | masterdata | `0_Tanimlamalar.vardiyalar.shift_name_tr` | `shifts.shift_name_tr` | no | no | no | no | yes | `Gunduz vardiyasi` | Label alanidir |
| `is_default` | Varsayilan flag | Varsayilan vardiya mi | boolean | no | masterdata | `0_Tanimlamalar.vardiyalar.is_default` | `shifts.is_default` | no | no | no | no | yes | `1` | Secim default'u, active state degil |
| `planned_start_time` | Plan baslangic | Planlanan vardiya baslangic saati | time_text | no | masterdata | `FERP_MasterData.xlsx.MD_Shifts.planned_start_time` | `shifts.planned_start_time` | no | no | no | no | no | `08:00` | Runtime `shift.startedAt` degildir |
| `planned_end_time` | Plan bitis | Planlanan vardiya bitis saati | time_text | no | masterdata | `FERP_MasterData.xlsx.MD_Shifts.planned_end_time` | `shifts.planned_end_time` | no | no | no | no | no | `17:00` | Runtime `shift.stoppedAt` degildir |
| `active_flag` | Aktif flag | Vardiya secilebilir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_Shifts.active_flag` | `shifts.active_flag` | no | no | no | no | no | `1` | Versioning/aktiflik alani |

### `devices`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `device_id` | Cihaz id | Cihaz definition master kimligi | string | yes | masterdata | `FERP_MasterData.xlsx.MD_Devices.device_id` | `devices.device_id` | yes | no | no | no | no | `kiosk-1` | Runtime device session degildir |
| `device_code` | Cihaz kodu | Stabil cihaz kodu | string | no | masterdata | `FERP_MasterData.xlsx.MD_Devices.device_code` | `devices.device_code` | no | yes | no | no | no | `KIOSK-01` | Optional |
| `device_name` | Cihaz adi | Cihaz gorunum adi | string | yes | masterdata | `FERP_MasterData.xlsx.MD_Devices.device_name` | `devices.device_name` | no | no | no | no | no | `Operator Kiosk` | Runtime presence degildir |
| `device_role` | Cihaz rolu | Operator kiosk, technician kiosk, sensor, bridge gibi rol | string | yes | masterdata | `FERP_MasterData.xlsx.MD_Devices.device_role` | `devices.device_role` | no | yes | no | no | no | `operator_kiosk` | `oee_state.py` runtime session'da da gorulur ama master definition ayridir |
| `default_station_id` | Varsayilan istasyon | Cihazin varsayilan bagli istasyonu | string | no | masterdata | `FERP_MasterData.xlsx.MD_Devices.default_station_id` | `devices.default_station_id` | no | yes | no | no | no | `station2` | `stations.station_id` referansi |
| `active_flag` | Aktif flag | Cihaz tanimi kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.MD_Devices.active_flag` | `devices.active_flag` | no | no | no | no | no | `1` | `last_seen_at` gibi runtime alanlar burada tutulmaz |

## 7. Lookup Tables Field Dictionary

### `colors`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `color_id` | Renk id | Renk lookup kimligi | string | yes | masterdata | `0_Tanimlamalar.renkler.color_id` | `colors.color_id` | yes | yes | no | no | yes | `1` | Workbook numeric olabilir |
| `color_code` | Renk kodu | Stabil renk kodu | string | yes | masterdata | `0_Tanimlamalar.renkler.color_code` ve `excel_runtime.COLOR_IDS` | `colors.color_code` | no | yes | no | no | yes | `red` | `red`, `yellow`, `blue`, `empty`, `uncertain` |
| `color_code_raw` | Raw renk kodu | Sensor/FERP raw renk tokeni | string | no | masterdata | `0_Tanimlamalar.renkler.color_code_raw` | `colors.color_code_raw` | no | yes | no | no | yes | `KIRMIZI` | Normalize icin |
| `color_name_tr` | Renk adi | Turkce renk etiketi | string | yes | masterdata | `0_Tanimlamalar.renkler.color_name_tr` | `colors.color_name_tr` | no | no | no | no | yes | `Kirmizi` | Label alanidir |
| `is_sortable` | Ayristirilabilir flag | Sensor/sorter tarafindan ayristirilabilir mi | boolean | no | masterdata | `0_Tanimlamalar.renkler.is_sortable` | `colors.is_sortable` | no | no | no | no | yes | `1` | `empty`/`uncertain` icin farkli olabilir |

### `sources`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `source_id` | Kaynak id | Event source lookup kimligi | string | yes | masterdata | `0_Tanimlamalar.kaynaklar.source_id` ve `excel_runtime.SOURCE_IDS` | `sources.source_id` | yes | yes | no | no | yes | `1` | Workbook numeric olabilir |
| `source_code` | Kaynak kodu | Stabil kaynak kodu | string | yes | masterdata | `0_Tanimlamalar.kaynaklar.source_code` | `sources.source_code` | no | yes | no | no | yes | `mega` | `mega`, `tablet`, `vision`, `system` |
| `source_name_tr` | Kaynak adi | Turkce kaynak etiketi | string | yes | masterdata | `0_Tanimlamalar.kaynaklar.source_name_tr` | `sources.source_name_tr` | no | no | no | no | yes | `Mega` | Label alanidir |
| `source_role` | Kaynak rolu | Sensor, UI, vision, system gibi rol | string | no | masterdata | `0_Tanimlamalar.kaynaklar.source_role` | `sources.source_role` | no | yes | no | no | yes | `sensor_controller` | Lookup/detail rol |

### `event_types`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `event_type_id` | Olay tipi id | Event type lookup kimligi | string | yes | masterdata | `0_Tanimlamalar.olay_tipleri.event_type_id` ve `excel_runtime.EVENT_TYPE_IDS` | `event_types.event_type_id` | yes | yes | no | no | yes | `2` | Workbook numeric olabilir |
| `event_type_code` | Olay tipi kodu | Stabil normalize event kodu | string | yes | masterdata | `0_Tanimlamalar.olay_tipleri.event_type_code` | `event_types.event_type_code` | no | yes | no | no | yes | `measurement_decision` | Event log tarafindan referanslanir |
| `event_name_tr` | Olay adi | Turkce event gorunum adi | string | yes | masterdata | `0_Tanimlamalar.olay_tipleri.event_name_tr` | `event_types.event_name_tr` | no | no | no | no | yes | `Olcum karari` | Label alanidir |
| `detail_sheet` | Detay sheet | Event detayinin yansidigi workbook sheet'i | string | no | masterdata | `0_Tanimlamalar.olay_tipleri.detail_sheet` | `event_types.detail_sheet` | no | yes | no | no | yes | `2_Olcumler` | Workbook projection baglami |

### `decision_sources`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `decision_source_id` | Karar kaynagi id | Decision source lookup kimligi | string | yes | masterdata | `0_Tanimlamalar.karar_kaynaklari.decision_source_id` ve `excel_runtime.DECISION_SOURCE_IDS` | `decision_sources.decision_source_id` | yes | yes | no | no | yes | `4` | Workbook numeric olabilir |
| `decision_source_code` | Karar kaynagi kodu | Stabil karar kaynagi kodu | string | yes | masterdata | `0_Tanimlamalar.karar_kaynaklari.decision_source_code` | `decision_sources.decision_source_code` | no | yes | no | no | yes | `VISION` | `CORE_STABLE`, `VISION`, `TABLET`, `SYSTEM` |
| `description_tr` | Aciklama | Turkce karar kaynagi aciklamasi | text | no | masterdata | `0_Tanimlamalar.karar_kaynaklari.description_tr` | `decision_sources.description_tr` | no | no | no | no | yes | `Vision karari` | Label/aciklama alanidir |

### `mega_states`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mega_state_id` | Mega durum id | Mega state lookup kimligi | string | yes | masterdata | `0_Tanimlamalar.mega_durumlari.mega_state_id` ve `excel_runtime.MEGA_STATE_IDS` | `mega_states.mega_state_id` | yes | yes | no | no | yes | `3` | Workbook numeric olabilir |
| `mega_state_code` | Mega durum kodu | Stabil Mega state kodu | string | yes | masterdata | `0_Tanimlamalar.mega_durumlari.mega_state_code` | `mega_states.mega_state_code` | no | yes | no | no | yes | `MEASURING` | Event log tarafindan referanslanir |
| `mega_state_tr` | Mega durum etiketi | Turkce Mega state etiketi | string | no | masterdata | `0_Tanimlamalar.mega_durumlari.mega_state_tr` | `mega_states.mega_state_tr` | no | no | no | no | yes | `Olcum` | Label alanidir |

### `work_order_statuses`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `status_code` | Status kodu | Stabil is emri status kodu | string | yes | masterdata | `excel_runtime._work_order_status_tr` ve runtime domain | `work_order_statuses.status_code` | yes | yes | no | no | yes | `active` | Projection'da kullanilir |
| `status_name_tr` | Status adi | Turkce status etiketi | string | yes | masterdata | `excel_runtime._work_order_status_tr` | `work_order_statuses.status_name_tr` | no | no | no | no | yes | `Aktif` | `*_tr` label'dir |
| `terminal_flag` | Terminal flag | Status is emri akisini kapatir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.LK_WorkOrderStatuses.terminal_flag` | `work_order_statuses.terminal_flag` | no | no | no | no | no | `0` | Hedef sozluk alani |
| `sort_order` | Siralama | UI/rapor sirasi | integer | no | masterdata | `FERP_MasterData.xlsx.LK_WorkOrderStatuses.sort_order` | `work_order_statuses.sort_order` | no | no | no | no | no | `20` | UI destek alani |

### `quality_codes`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `quality_code` | Kalite kodu | Stabil kalite sonucu kodu | string | yes | masterdata | `oee_state.py` kalite domaini | `quality_codes.quality_code` | yes | yes | no | no | yes | `GOOD` | `production_finalization_reasons` ile karistirilmaz |
| `quality_name_tr` | Kalite adi | Turkce kalite etiketi | string | yes | masterdata | `excel_runtime.apply_quality_override` | `quality_codes.quality_name_tr` | no | no | no | no | yes | `Saglam` | Label alanidir |
| `counts_as_good_flag` | Saglam sayilir flag | OEE quality hesabinda good sayilir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.LK_QualityCodes.counts_as_good_flag` | `quality_codes.counts_as_good_flag` | no | no | no | no | no | `1` | OEE hesap semantigi |
| `sort_order` | Siralama | UI/rapor sirasi | integer | no | masterdata | `FERP_MasterData.xlsx.LK_QualityCodes.sort_order` | `quality_codes.sort_order` | no | no | no | no | no | `10` | UI destek alani |

### `oee_components`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `component_code` | OEE bilesen kodu | Stabil OEE component kodu | string | yes | masterdata | OEE domain sozluk | `oee_components.component_code` | yes | yes | no | no | no | `availability` | `availability`, `performance`, `quality`, `oee` |
| `component_name_tr` | OEE bilesen adi | Turkce component etiketi | string | yes | masterdata | `FERP_MasterData.xlsx.LK_OEEComponents.component_name_tr` | `oee_components.component_name_tr` | no | no | no | no | no | `Kullanilabilirlik` | Label alanidir |
| `unit` | Birim | Component birimi | string | no | masterdata | `FERP_MasterData.xlsx.LK_OEEComponents.unit` | `oee_components.unit` | no | yes | no | no | no | `percent` | Hesap sonucu birimi |
| `sort_order` | Siralama | UI/rapor sirasi | integer | no | masterdata | `FERP_MasterData.xlsx.LK_OEEComponents.sort_order` | `oee_components.sort_order` | no | no | no | no | no | `10` | UI destek alani |

### `production_finalization_reasons`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `reason_code` | Final gerekce kodu | Production finalization decision reason kodu | string | yes | masterdata | `oee_state.py.finalization_reason` | `production_finalization_reasons.reason_code` | yes | yes | no | no | yes | `VISION_CORRECTED_MISMATCH` | Kalite kodu degildir |
| `reason_name_tr` | Final gerekce adi | Turkce finalization gerekce etiketi | string | yes | masterdata | `FERP_MasterData.xlsx.LK_ProductionFinalizationReasons.reason_name_tr` | `production_finalization_reasons.reason_name_tr` | no | no | no | no | no | `Vision uyumsuzlugu duzeltti` | Label alanidir |
| `decision_family` | Karar ailesi | Sensor, vision, fault, low_conf gibi aile | string | no | masterdata | `FERP_MasterData.xlsx.LK_ProductionFinalizationReasons.decision_family` | `production_finalization_reasons.decision_family` | no | yes | no | no | no | `vision` | Analitik gruplama |
| `review_required_default` | Varsayilan review | Bu gerekce normalde review gerektirir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.LK_ProductionFinalizationReasons.review_required_default` | `production_finalization_reasons.review_required_default` | no | no | no | no | no | `0` | Runtime kararini ezmez |

### `correlation_statuses`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `correlation_status_code` | Korelasyon kodu | Sensor/vision correlation status kodu | string | yes | masterdata | `excel_runtime._correlation_status_label_tr` ve `oee_state.py` | `correlation_statuses.correlation_status_code` | yes | yes | no | no | yes | `MATCHED` | Audit/projection bu kodu referanslar |
| `correlation_status_name_tr` | Korelasyon adi | Turkce correlation etiketi | string | yes | masterdata | `excel_runtime._correlation_status_label_tr` | `correlation_statuses.correlation_status_name_tr` | no | no | no | no | no | `Eslesti` | Label alanidir |
| `counts_for_accuracy_flag` | Accuracy sayimi | Vision accuracy hesabina dahil mi | boolean | no | masterdata | `FERP_MasterData.xlsx.LK_CorrelationStatuses.counts_for_accuracy_flag` | `correlation_statuses.counts_for_accuracy_flag` | no | no | no | no | no | `1` | Hedef analitik semantigi |
| `review_required_default` | Varsayilan review | Bu status normalde review gerektirir mi | boolean | no | masterdata | `FERP_MasterData.xlsx.LK_CorrelationStatuses.review_required_default` | `correlation_statuses.review_required_default` | no | no | no | no | no | `1` | Runtime kararini ezmez |

### `oee_scopes`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `oee_scope_code` | OEE kapsam kodu | OEE hesap kapsami kodu | string | yes | masterdata | `excel_runtime._oee_scope_for_event` | `oee_scopes.oee_scope_code` | yes | yes | no | no | yes | `station2_packaging_oee` | OEE hesap kapsamini tanimlar |
| `oee_scope_name_tr` | OEE kapsam adi | Turkce kapsam etiketi | string | yes | masterdata | `FERP_MasterData.xlsx.LK_OEEScopes.oee_scope_name_tr` | `oee_scopes.oee_scope_name_tr` | no | no | no | no | no | `Station2 paketleme OEE` | Label alanidir |
| `station_id` | Istasyon id | Kapsamin bagli oldugu varsayilan istasyon | string | no | masterdata | `FERP_MasterData.xlsx.LK_OEEScopes.station_id` | `oee_scopes.station_id` | no | yes | no | no | no | `station2` | `stations.station_id` referansi |
| `scope_type` | Kapsam tipi | component_transfer, final_package, packaging_oee gibi tip | string | no | masterdata | `FERP_MasterData.xlsx.LK_OEEScopes.scope_type` | `oee_scopes.scope_type` | no | yes | no | no | no | `packaging_oee` | Lookup/detail rol |

## 8. FERP Label Mapping Field Dictionary

### `ferp_label_mappings`

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `map_id` | Mapping id | FERP label mapping satir kimligi | string | yes | ferp_mapping | `MAP_FERPLabels.map_id` | `ferp_label_mappings.map_id` | yes | no | no | no | yes | `MAP-001` | Integration mapping id |
| `ferp_module` | FERP modul | FERP label workbook sheet/modul adi | string | yes | ferp_mapping | `docs/FERP_XLS/ferp_labels.xlsx` | `ferp_label_mappings.ferp_module` | no | yes | no | no | yes | `MM` | `ferp_labels.py` sheet title'dan okur |
| `ferp_screen` | FERP ekran | FERP ekran veya object bolumu adi | string | no | ferp_mapping | `docs/FERP_XLS/ferp_labels.xlsx` | `ferp_label_mappings.ferp_screen` | no | yes | no | no | yes | `Uretim emri` | Label text solundaki ekran adi olabilir |
| `ferp_object` | FERP nesne | FERP object kodu | string | yes | ferp_mapping | `ferp_labels.py.SUPPORTED_OBJECTS` | `ferp_label_mappings.ferp_object` | no | yes | no | no | yes | `mym4004` | Supported object listesiyle dogrulanir |
| `ferp_label_code` | FERP label kodu | FERP `lbl...` label kodu | string | yes | ferp_mapping | `docs/FERP_XLS/ferp_labels.xlsx` | `ferp_label_mappings.ferp_label_code` | no | yes | no | no | yes | `lblMMFB0_NUMBER` | MES domain kolonu degildir |
| `ferp_label_text` | FERP label metni | FERP UI label metni | string | no | ferp_mapping | `docs/FERP_XLS/ferp_labels.xlsx` | `ferp_label_mappings.ferp_label_text` | no | no | no | no | yes | `Belge No` | Gorunum/aciklama |
| `mes_entity` | MES varlik | Label'in map edildigi MES varlik adi | string | yes | ferp_mapping | `MAP_FERPLabels.mes_entity` | `ferp_label_mappings.mes_entity` | no | yes | no | no | yes | `work_order` | Canonical entity adi |
| `mes_field` | MES alan | Label'in map edildigi canonical MES alani | string | yes | ferp_mapping | `MAP_FERPLabels.mes_field` | `ferp_label_mappings.mes_field` | no | yes | no | no | yes | `target_qty` | `lbl...` yerine canonical alan kullanilir |
| `required_flag` | Zorunlu flag | Import/export icin label zorunlu mu | boolean | no | ferp_mapping | `ferp_labels.py.REQUIRED_LABELS_BY_OBJECT` | `ferp_label_mappings.required_flag` | no | no | no | no | yes | `1` | Validation icin |
| `direction` | Yon | import, export veya both | string | yes | ferp_mapping | `MAP_FERPLabels.direction` | `ferp_label_mappings.direction` | no | yes | no | no | yes | `import` | Entegrasyon yonu |
| `default_value` | Varsayilan deger | Kaynak bos gelirse mapping varsayilani | string | no | ferp_mapping | `MAP_FERPLabels.default_value` | `ferp_label_mappings.default_value` | no | no | no | no | no | `1` | Dikkatli kullanilmali |
| `active_flag` | Aktif flag | Mapping aktif mi | boolean | no | ferp_mapping | `MAP_FERPLabels.active_flag` | `ferp_label_mappings.active_flag` | no | no | no | no | no | `1` | Eski mapping deprecate edilebilir |
| `notes` | Notlar | Mapping notu | text | no | ferp_mapping | `MAP_FERPLabels.notes` | `ferp_label_mappings.notes` | no | no | no | no | no | `work order number` | Serbest aciklama |

## 9. Masterdata Versioning Alanlari

Bu alanlar master ve lookup tablolarina ortak metadata olarak eklenebilir. Ilk fazda dokumantasyon sozlesmesidir; mevcut Excel veya kod davranisini degistirmez.

| field_name | business_name_tr | description | data_type | required | source_owner | source_location | target_location | is_key | is_lookup | is_runtime | is_audit | backfill_candidate | example_value | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `schema_version` | Sema versiyonu | Masterdata tablo/sheet sema versiyonu | string | yes | masterdata | `FERP_MasterData.xlsx.<sheet>.schema_version` | `<master_table>.schema_version` | no | no | no | no | no | `1.0` | Kolon sozlesmesi versiyonu |
| `masterdata_version` | Masterdata versiyonu | Masterdata set versiyonu | string | yes | masterdata | `FERP_MasterData.xlsx.<sheet>.masterdata_version` | `<master_table>.masterdata_version` | no | no | no | no | no | `2026-06-v1` | Import/fark raporu icin |
| `effective_from` | Gecerlilik baslangici | Satirin gecerli olmaya basladigi zaman | datetime_iso | no | masterdata | `FERP_MasterData.xlsx.<sheet>.effective_from` | `<master_table>.effective_from` | no | no | no | no | no | `2026-06-01T00:00:00+03:00` | Tarihsel gecerlilik |
| `effective_to` | Gecerlilik bitisi | Satirin gecerli oldugu son zaman | datetime_iso | no | masterdata | `FERP_MasterData.xlsx.<sheet>.effective_to` | `<master_table>.effective_to` | no | no | no | no | no | `` | Bos ise hala gecerli |
| `active_flag` | Aktif flag | Satir kullanima acik mi | boolean | no | masterdata | `FERP_MasterData.xlsx.<sheet>.active_flag` | `<master_table>.active_flag` | no | no | no | no | no | `1` | UI secimlerinde filtrelenebilir |
| `deprecated_flag` | Deprecated flag | Satir geriye uyumluluk icin mi tutuluyor | boolean | no | masterdata | `FERP_MasterData.xlsx.<sheet>.deprecated_flag` | `<master_table>.deprecated_flag` | no | no | no | no | no | `0` | Silmek yerine deprecate et |
| `updated_at` | Guncelleme zamani | Masterdata satiri son guncelleme zamani | datetime_iso | no | masterdata | `FERP_MasterData.xlsx.<sheet>.updated_at` | `<master_table>.updated_at` | no | no | no | no | no | `2026-06-01T12:00:00+03:00` | Audit event degil, masterdata metadata |
| `updated_by` | Guncelleyen | Masterdata satirini guncelleyen kisi/sistem | string | no | masterdata | `FERP_MasterData.xlsx.<sheet>.updated_by` | `<master_table>.updated_by` | no | yes | no | no | no | `OP-ADMIN` | Operator/session runtime'i degil |

## 10. ID / Code / Name Alan Standartlari

| Alan tipi | Standart | Not |
| --- | --- | --- |
| `*_id` | Canonical string id | Workbook numeric gorunse bile SQL tarafinda string kabul edilebilir |
| `*_code` | Stabil is kodu | Entegrasyon ve lookup eslesmelerinde onceliklidir |
| `*_name_tr` | Turkce gorunum adi | Canonical kod degildir |
| `*_reason_tr` | Turkce gerekce/etiket | Audit label olarak snapshot alinabilir |
| `*_label_tr` | UI etiketi | Kod yerine kullanilmaz |
| `source_note`, `notes` | Serbest metin | Validation ve key iliskisi icin kullanilmaz |

Kural:

- ID alanlari benzersiz olmalidir.
- Code alanlari stabil ve geriye uyumlu tutulmalidir.
- Name/label alanlari degisebilir; bu nedenle foreign key gibi kullanilmamalidir.

## 11. Active / Deprecated / Version Alanlari

| Alan | Kullanim |
| --- | --- |
| `active_flag` | Yeni secimlerde kullanilabilir satir |
| `deprecated_flag` | Eski kayitlar icin korunur ama yeni secimde kullanilmaz |
| `effective_from` | Satirin gecerli olmaya basladigi tarih |
| `effective_to` | Satirin gecerli oldugu son tarih |
| `schema_version` | Alan/kolon sozlesmesi versiyonu |
| `masterdata_version` | Veri seti versiyonu |

Koruyucu kural:

- Masterdata satiri silmek yerine once `active_flag=0` veya `deprecated_flag=1` ile kapatilmalidir.
- Eski audit/event kayitlari eski kodlari referanslayabilecegi icin lookup satirlari geriye uyumlu tutulmalidir.

## 12. Runtime ve Audit'ten Ayrim Kurallari

Masterdata'ya konmayacak alanlar:

- Aktif vardiya state'i: `shift.active`, `startedAt`, `stoppedAt`
- Aktif fault state'i: `activeFault`, `faultStartedAt`
- Device session/presence: `lastSeenAt`, `sessionId`, `operatorName` current state
- Production completion audit alanlari: `completed_at`, `final_quality_code`, `finalization_reason` satir kaydi
- Measurement raw/debug alanlari: `core_n`, `vote_x`, `raw_line`
- OEE snapshot metrikleri: `oee`, `availability`, `performance`, `quality`
- Raw archive payload: `raw_payload`

Masterdata'ya konabilecek tanimlar:

- Operator, station, line, product, fault type ve maintenance step kataloglari
- Lookup kod sozlukleri
- OEE scope tanimlari
- FERP label mapping tanimlari

## 13. SQL'e Geciste Masterdata Alan Karsiliklari

| Kaynak | Hedef SQL | Not |
| --- | --- | --- |
| `0_Tanimlamalar.operatorler` | `operators` | Kiosk secim listesi |
| `0_Tanimlamalar.istasyonlar` | `stations` | Kiosk/default station ve raporlama |
| `0_Tanimlamalar.hatlar` | `lines` | Hat kirilimi |
| `0_Tanimlamalar.urunler` | `products` | Urun/stok/renk mapping |
| `0_Tanimlamalar.ariza_tipleri` | `fault_types` | Fault secim katalogu |
| `0_Tanimlamalar.vardiyalar` | `shifts` | Vardiya sozlugu, aktif vardiya state'i degil |
| `0_Tanimlamalar.<bakim*>` veya default | `maintenance_steps` | Checklist sablonu, kayit degil |
| `0_Tanimlamalar.renkler` | `colors` | Renk lookup |
| `0_Tanimlamalar.kaynaklar` | `sources` | Event source lookup |
| `0_Tanimlamalar.olay_tipleri` | `event_types` | Event type lookup |
| `0_Tanimlamalar.karar_kaynaklari` | `decision_sources` | Decision source lookup |
| `0_Tanimlamalar.mega_durumlari` | `mega_states` | Mega state lookup |
| `FERP_MasterData.xlsx.MD_OperationDefinitions` | `operation_definitions` | FERP operasyon mapping |
| `FERP_MasterData.xlsx.MD_Devices` | `devices` | Device definition, session degil |
| `docs/FERP_XLS/ferp_labels.xlsx` + `MAP_FERPLabels` | `ferp_label_mappings` | Integration mapping |

## 14. Data Quality ve Validation Kurallari

| Kural | Uygulama |
| --- | --- |
| Required alanlar bos kalmamali | `required=yes` alanlari masterdata import validasyonunda kontrol edilir |
| ID alanlari benzersiz olmali | Her master/lookup tablo icinde tekil olmali |
| Code alanlari stabil olmali | Kod degistirmek yerine yeni kod + deprecate akisi tercih edilmeli |
| Lookup referanslari eslesmeli | `stations.line_id`, `products.color_id`, `fault_types.default_station_id` gibi FK adaylari kontrol edilmeli |
| `*_tr` alanlari kod gibi kullanilmamali | UI/audit label olarak kalmali |
| Runtime alanlari reddedilmeli | `last_seen_at`, active state, counter, session alanlari masterdata importuna alinmamali |
| FERP label'lari dogrulanmali | `ferp_labels.py.SUPPORTED_OBJECTS` ve required label listesiyle kontrol edilmeli |
| Version metadata opsiyonel baslayabilir | Ama SQL gecisinden once `schema_version` ve `masterdata_version` zorunlu hale getirilmeli |

## 15. Riskler ve Koruyucu Kurallar

| Risk | Etki | Koruyucu kural |
| --- | --- | --- |
| `0_Tanimlamalar` gunluk workbook icinde buyur | Audit/projection ve masterdata siniri karisir | Hedefte `FERP_MasterData.xlsx` veya SQL master tables ayrimi yap |
| Runtime state masterdata'ya tasinir | Canli state katalog verisiyle karisir | Device/session, active shift, active fault alanlari masterdata disinda tutulur |
| Audit/event alanlari masterdata'ya konur | Veri sozlugu ve DB tasarimi siserek yanlis kaynak otoritesi olusur | Event/fact tablolar ayri kalir |
| FERP `lbl...` alanlari domain kolon olur | MES modeli FERP ekranlarina bagimli hale gelir | `ferp_label_mappings` + canonical `mes_field` ayrimi korunur |
| `production_finalization_reasons` kalite kodlariyla birlesir | Kalite sonucu ve karar gerekcesi karisir | `quality_codes` ayri, finalization reasons ayri tutulur |
| Lookup satirlari silinir | Eski workbook/audit kayitlari referanssiz kalir | Deletion yerine deprecate/active flag kullan |
| Hardcoded lookup ve masterdata ayrisir | Event id/color id/status tutarsizligi olusur | Fark raporu ve lookup sozlesmesi hazirlanir |

## 16. Uygulanacak Sonraki 5 Is

1. `0_Tanimlamalar` icindeki aktif bloklari bu dokumandaki tablo alanlariyla tek tek eslestiren fark kontrol listesini hazirla.
2. `FERP_MasterData.xlsx` icin sadece dokumantasyon seviyesinde sheet/kolon taslagini yaz; kod veya template degistirme.
3. `excel_runtime.py` hardcoded lookup map'leri ile hedef lookup tablolarini karsilastiran test planini dokumante et.
4. `ferp_label_mappings` icin `mes_entity` ve `mes_field` canonical alan listesini FERP import/export dokumanlariyla uyumlu hale getir.
5. SQL gecisinden once masterdata versioning, deprecate ve fark raporu kurallarini ayri bir kontrol listesine donustur.
