# Masterdata Design

## 1. Amac

Bu dokuman, MES projesinde mevcut `0_Tanimlamalar` sheet'inin hangi masterdata bloklarini tasidigini ve bu bloklarin hedefte nasil ayrilacagini tanimlar.

Hedef, mevcut calisan akisi kirmadan once dokumantasyon ve sema tasarimi yapmaktir. Bu nedenle bu dokuman bir migration talimati degil, masterdata sahipligi ve hedef mimari planidir.

Ana kararlar:

- Mevcut sistemde `0_Tanimlamalar` masterdata kaynagidir.
- Gunluk workbook canli transactional database degildir.
- Runtime state, audit/event ve raw log alanlari masterdata'ya karistirilmamalidir.
- Hedefte masterdata once `FERP_MasterData.xlsx` gibi ayri bir workbook'a, daha sonra gerekirse SQL master tables yapisina ayrilabilir.
- Kod davranisi degistirilmeden once sheet ve tablo sozlesmeleri netlestirilmelidir.

## 2. Mevcut Masterdata Kaynagi: 0_Tanimlamalar

Mevcut masterdata kaynagi gunluk workbook veya template icindeki `0_Tanimlamalar` sheet'idir.

Kaynak secim sirasi:

1. Gunluk workbook varsa `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
2. Yoksa template workbook: `MES_Konveyor_Veritabani_Sablonu.xlsx`
3. Ikisi de yoksa kod icindeki default kataloglar

`mes_web/masterdata.py` bu sheet'i su mantikla okur:

- Satir 1: blok adlari
- Satir 2: blok icindeki kolon adlari
- Satir 3 ve sonrasi: veri satirlari
- Bir sonraki blok basligina kadar olan kolonlar ayni blok sayilir

Mevcut template'te gorulen bloklar:

| Blok | Mevcut kolonlar | Mevcut kullanim | Hedef |
| --- | --- | --- | --- |
| `renkler` | `color_id`, `color_code`, `color_code_raw`, `color_name_tr`, `is_sortable` | Kod tarafinda lookup kismen hardcoded | `colors` master table |
| `olay_tipleri` | `event_type_id`, `event_type_code`, `event_name_tr`, `detail_sheet` | Event id esleme kismen hardcoded | `event_types` lookup |
| `ariza_tipleri` | `fault_type_id`, `fault_type_code`, `fault_category`, `fault_reason_tr`, `default_station_id` | `masterdata.py` tarafindan kiosk fault secimi icin okunur | `fault_types` master table |
| `karar_kaynaklari` | `decision_source_id`, `decision_source_code`, `description_tr` | Kod tarafinda lookup kismen hardcoded | `decision_sources` lookup |
| `kaynaklar` | `source_id`, `source_code`, `source_name_tr`, `source_role` | Kod tarafinda lookup kismen hardcoded | `sources` lookup |
| `mega_durumlari` | `mega_state_id`, `mega_state_code`, `mega_state_tr` | Kod tarafinda lookup kismen hardcoded | `mega_states` lookup |
| `hatlar` | `line_id`, `line_code`, `line_name_tr`, `erp_ready` | Hedef masterdata adayi | `lines` master table |
| `istasyonlar` | `station_id`, `station_code`, `station_name_tr`, `line_id` | `masterdata.py` tarafindan kiosk station ve default station icin okunur | `stations` master table |
| `urunler` | `product_id`, `product_code`, `product_name_tr`, `color_id` | Hedef masterdata adayi | `products` master table |
| `operatorler` | `operator_id`, `operator_code`, `operator_name`, `source_note` | `masterdata.py` tarafindan operator secimi icin okunur | `operators` master table |
| `vardiyalar` | `shift_id`, `shift_code`, `shift_name_tr`, `is_default` | Hedef masterdata adayi | `shifts` master table |

Ek not:

- `masterdata.py` bakim adimi bloklarini da destekler; blok adinda `bakim` veya `maintenance` gecerse acilis/kapanis checklist adimlari normalize edilebilir.
- Mevcut template'te bakim adimlari ayri blok olarak gorunmediginde kod default opening/closing checklist adimlarini kullanir.

## 3. Masterdata ile Runtime/Audit Ayrimi

Masterdata, nadiren degisen referans veridir. Runtime state ve audit/event kayitlari masterdata degildir.

| Veri tipi | Ornek | Sahiplik | Masterdata mi? |
| --- | --- | --- | --- |
| Operator tanimi | `OP-001`, operator adi | Masterdata | Evet |
| Istasyon tanimi | `SENS-01`, `KSK-01` | Masterdata | Evet |
| Ariza tipi | `robot_arm_jam` | Masterdata | Evet |
| Renk lookup | `red`, `yellow`, `blue` | Lookup masterdata | Evet |
| Aktif vardiya | `shift.active`, `started_at` | Runtime state | Hayir |
| Aktif ariza | `activeFault` | Runtime state | Hayir |
| Tamamlanan urun kaydi | `4_Uretim_Tamamlanan` satiri | Audit/projection | Hayir |
| OEE snapshot | `5_OEE_Anliklari` satiri | Calculated snapshot | Hayir |
| Ham payload | `99_Raw_Logs` | Raw archive/debug | Hayir |
| FERP label registry | `lblMMFB0_NUMBER` eslesmesi | Integration mapping | Evet, mapping masterdata gibi yonetilebilir |

Kural:

- Masterdata tablolarinda olay zamani, aktif state, runtime counter veya audit log tutulmamalidir.
- Runtime state canli karar icindir; gecmis kayit kaynagi olarak modellenmemelidir.
- Workbook sheet'leri audit/projection ciktisidir; masterdata kaynagi olarak sadece `0_Tanimlamalar` ozel durumdur.

## 4. Hedef Masterdata Mimarisi

Hedef mimari uc fazli dusunulmelidir.

### Faz 0 - Mevcut uyum

- `0_Tanimlamalar` aynen kalir.
- `mes_web/masterdata.py` mevcut sheet'i okumaya devam eder.
- Kod ve Excel template degistirilmez.
- Bu dokuman masterdata sahipligini netlestirir.

### Faz 1 - Ayri masterdata workbook

- `FERP_MasterData.xlsx` adli ayri bir masterdata workbook tasarlanir.
- `0_Tanimlamalar` icindeki bloklar ayri sheet'lere bolunur.
- Gunluk audit workbook masterdata kaynagi olmaktan cikarilir.
- Gunluk workbook sadece audit/projection ciktisi olur.

### Faz 2 - SQL master tables

- Masterdata SQL tablolarina tasinir.
- Workbook kaynaklari import/export ve saha kontrol dosyasi olarak kalabilir.
- `FERP_MasterData.xlsx` SQL'e gecis icin staging veya manuel bakim kaynagi olarak kullanilabilir.

Bu fazlarin hicbiri mevcut sistemi aniden kiracak zorunlu migration olarak uygulanmamalidir.

## 5. Onerilen FERP_MasterData.xlsx Sheet Listesi

| Sheet | Amac | Kaynak blok |
| --- | --- | --- |
| `MD_Operators` | Operator kataloglari | `operatorler` |
| `MD_Stations` | Istasyon ve hat eslesmeleri | `istasyonlar`, `hatlar` |
| `MD_FaultTypes` | Ariza tipi ve kategori kataloglari | `ariza_tipleri` |
| `MD_MaintenanceSteps` | Acilis/kapanis bakim checklist adimlari | Bakim/maintenance bloklari veya default liste |
| `MD_Products` | Urun, stok ve renk eslesmeleri | `urunler` |
| `MD_Shifts` | Vardiya tanimlari | `vardiyalar` |
| `LK_Colors` | Renk lookup degerleri | `renkler` |
| `LK_Sources` | Olay kaynaklari | `kaynaklar` |
| `LK_EventTypes` | Normalize event type listesi | `olay_tipleri` |
| `LK_DecisionSources` | Renk karar kaynagi listesi | `karar_kaynaklari` |
| `LK_WorkOrderStatuses` | Is emri status lookup | Runtime/domain status listesi |
| `MD_OperationDefinitions` | Operasyon, is merkezi, istasyon, standart sure | FERP is emri ve operasyon alanlari |
| `MAP_FERPLabels` | FERP label ile MES canonical alan eslesmesi | `ferp_labels.xlsx` ve FERP JSON kontrati |

## 6. Sheet Bazli Girdi -> Islem -> Cikti Analizi

| Hedef sheet | Girdi | Islem | Cikti |
| --- | --- | --- | --- |
| `MD_Operators` | `operatorler` blok satirlari | Operator id, kod ve ad normalize edilir | Kiosk ve audit icin operator katalogu |
| `MD_Stations` | `istasyonlar`, `hatlar` | Istasyonlar hatlarla iliskilendirilir | Kiosk bound station ve raporlama kirilimi |
| `MD_FaultTypes` | `ariza_tipleri` | Ariza kodu, kategori, varsayilan istasyon ayrilir | Standart fault secim listesi |
| `MD_MaintenanceSteps` | Bakim bloklari veya default adimlar | Faz, sira, zorunluluk ve etiket normalize edilir | Acilis/kapanis checklist katalogu |
| `MD_Products` | `urunler`, FERP stok kodlari, is emri material satirlari | Urun kodu, stok kodu, renk ve tip eslestirilir | Is emri ve stok/renk dogrulama katalogu |
| `MD_Shifts` | `vardiyalar` | Shift kodu, ad, default bilgisi ayrilir | Vardiya secim listesi |
| `LK_Colors` | `renkler` | Renk kodu ve raw sensor degeri eslestirilir | Renk lookup |
| `LK_Sources` | `kaynaklar` | Kaynak kodu ve rol ayrilir | Event source lookup |
| `LK_EventTypes` | `olay_tipleri` | Event kodu ve hedef detail sheet ayrilir | Event type lookup |
| `LK_DecisionSources` | `karar_kaynaklari` | Karar kaynagi kodu ve aciklamasi ayrilir | Decision source lookup |
| `LK_WorkOrderStatuses` | Runtime/domain status kodlari | Status kodu ve UI etiketi ayrilir | Work order status lookup |
| `MD_OperationDefinitions` | FERP operasyon alanlari, is merkezi, istasyon, standart sure | Operasyon katalogu olusturulur | OEE ve is emri planlama referansi |
| `MAP_FERPLabels` | `ferp_labels.xlsx`, FERP JSON alanlari, MES canonical alanlari | Label kodlari MES alanlariyla eslestirilir | Import/export mapping katalogu |

## 7. Minimum Masterdata v0 Tablolari

Minimum v0, mevcut sistemi kirmadan dokumante edilecek en kucuk masterdata setidir.

### `operators`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `operator_id` | MES ic operator kimligi | Evet |
| `operator_code` | Operator kodu, FERP/personel koduna baglanabilir | Evet |
| `operator_name` | Gorunen operator adi | Evet |
| `active_flag` | Kullanima acik mi | Hayir |
| `source_note` | Kaynak veya aciklama | Hayir |

### `stations`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `station_id` | MES ic istasyon kimligi | Evet |
| `station_code` | Istasyon kodu | Evet |
| `station_name_tr` | Gorunen istasyon adi | Evet |
| `line_id` | Hat iliskisi | Evet |
| `station_role` | sensor, buffer, robot, kiosk, packaging gibi rol | Hayir |
| `active_flag` | Kullanima acik mi | Hayir |

### `fault_types`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `fault_type_id` | Ariza tipi kimligi | Evet |
| `fault_type_code` | Stabil ariza kodu | Evet |
| `fault_category` | MEKANIK, ELEKTRIK, SENSOR vb. kategori | Evet |
| `fault_reason_tr` | Operator/teknisyen ekrani etiketi | Evet |
| `default_station_id` | Varsayilan bagli istasyon | Hayir |
| `active_flag` | Kullanima acik mi | Hayir |

### `maintenance_steps`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `step_id` | Bakim adim kimligi | Evet |
| `phase_code` | `opening` veya `closing` | Evet |
| `step_code` | Stabil adim kodu | Evet |
| `step_label_tr` | Operator ekraninda gorunen ad | Evet |
| `step_order` | Siralama | Evet |
| `required_flag` | Zorunlu mu | Evet |
| `active_flag` | Kullanima acik mi | Hayir |

### `products`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `product_id` | MES ic urun kimligi | Evet |
| `product_code` | MES/ERP stok kodu | Evet |
| `product_name_tr` | Urun adi | Evet |
| `color_id` | Renk lookup iliskisi | Hayir |
| `product_type` | box, package, label, consumable vb. | Hayir |
| `uom` | Birim | Hayir |
| `active_flag` | Kullanima acik mi | Hayir |

### `shifts`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `shift_id` | Vardiya kimligi | Evet |
| `shift_code` | `SHIFT-A`, `SHIFT-B` gibi kod | Evet |
| `shift_name_tr` | Gorunen vardiya adi | Evet |
| `is_default` | Varsayilan vardiya mi | Hayir |
| `planned_start_time` | Planlanan baslangic | Hayir |
| `planned_end_time` | Planlanan bitis | Hayir |

### `operation_definitions`

| Alan | Aciklama | Zorunlu |
| --- | --- | --- |
| `operation_id` | Operasyon kimligi | Evet |
| `operation_code` | MES/FERP operasyon kodu | Evet |
| `operation_name_tr` | Operasyon adi | Evet |
| `work_center_code` | FERP is merkezi | Hayir |
| `work_station_code` | FERP is istasyonu veya MES station | Hayir |
| `station_id` | MES istasyon iliskisi | Hayir |
| `standard_time_sec` | Standart sure | Hayir |
| `source` | manual, time_study, FERP vb. | Hayir |

## 8. Lookup Tablolari

Lookup tablolar stabil kod sozlukleri olarak ele alinmalidir.

| Tablo | Kaynak | Amac |
| --- | --- | --- |
| `colors` | `renkler` | Sensor/vision/urun renk eslesmesi |
| `sources` | `kaynaklar` | Event kaynagi lookup'u |
| `event_types` | `olay_tipleri` | Normalize event tipleri |
| `decision_sources` | `karar_kaynaklari` | Sensor/vision/tablet/system karar kaynagi |
| `mega_states` | `mega_durumlari` | Mega state kodlari |
| `work_order_statuses` | Runtime/domain status listesi | queued, active, pending_approval, completed, rolled_back |

### `work_order_statuses`

| Status | Anlam | Not |
| --- | --- | --- |
| `queued` | Kuyrukta | Baslatilmamis is emri |
| `active` | Aktif | Uretim veya paketleme akisinda |
| `pending_approval` | Onay bekliyor | Operator kabul/onay adimi bekliyor |
| `completed` | Tamamlandi | Is emri kapanmis |
| `rolled_back` | Geri alindi | Aktif is emri geri alinmis |

## 9. Urun / Stok / Renk Eslesmesi

Urun/stok/renk tasarimi, MES ile FERP arasindaki en onemli masterdata sinirlarindan biridir.

Mevcut durumda:

- `urunler` blogu `product_id`, `product_code`, `product_name_tr`, `color_id` alanlarini tasir.
- FERP is emri JSON'larinda stok kodlari `lblMTM00_CODE`, stok adlari `lblMTM00_NAME` ile gelir.
- Paketleme is emirlerinde `materials` satirlari `itemCode`, `itemName`, `itemType`, `color`, `qtyPerUnit` alanlarini tasir.

Hedef eslesme:

| MES alan | FERP/Malzeme alani | Amac |
| --- | --- | --- |
| `product_code` | `lblMTM00_CODE`, `itemCode` | Stok/urun kodu eslesmesi |
| `product_name_tr` | `lblMTM00_NAME`, `itemName` | Operator gorunumu |
| `color_id` | `color`, `color_code` | Renk dogrulama |
| `product_type` | `itemType` | box, package, label, consumable ayrimi |
| `uom` | `lblMUNT0_CODE` | Birim |

Koruyucu kural:

- ERP resmi stok kaynagi MES masterdata'si degildir.
- MES masterdata'si, operasyonel secim, dogrulama ve mapping icindir.
- Resmi stok miktari FERP/ERP tarafinda kalmalidir.

## 10. Operator / Istasyon / Cihaz / Bakim Tasarimi

### Operator

Operator masterdata'si secim listesi ve audit baglami icindir.

- Kiosk operator secimi `operators` tablosundan beslenmelidir.
- Audit/event kayitlarinda operator kodu ve adi snapshot olarak tutulabilir.
- Operator masterdata'si runtime session bilgisi tasimamalidir.

### Istasyon

Istasyon masterdata'si hat ve cihaz baglaminin temelidir.

- `stations` tablosu `line_id` ile iliskili olmalidir.
- Kiosk varsayilan istasyon secimi masterdata'dan gelebilir.
- Istasyon runtime durumu `station1`, `station2` gibi runtime state bloklarinda kalmalidir.

### Cihaz

Cihaz kaydi ikiye ayrilmalidir:

- Masterdata/device definition: cihaz tipi, rol, varsayilan istasyon
- Runtime/device session: son gorulme zamani, aktif operator, browser session

Mevcut `deviceRegistry` ve `deviceSessions` runtime state kapsaminda kalmalidir. Ileride SQL'e gecerse current/session tablolari olarak modellenmelidir.

### Bakim

Bakim tasarimi iki katmandan olusur:

- `maintenance_steps`: hangi adimlarin yapilacagi
- `maintenance_records`: hangi oturumda hangi adimlarin tamamlandigi

`maintenance_steps` masterdata'dir. `9_Bakim_Kayitlari` ise audit/projection kaydidir.

## 11. FERP Label Mapping ile Iliski

FERP label mapping, masterdata ile integration boundary arasinda durur.

Mevcut kaynaklar:

- `docs\FERP_XLS\ferp_labels.xlsx`
- FERP is emri JSON alanlari
- `mes_web/ferp_import/ferp_work_orders.json`
- `docs/FERP_INTEGRATION.md`

`MAP_FERPLabels` hedef sheet/tablo onerisi:

| Alan | Aciklama |
| --- | --- |
| `map_id` | Mapping kimligi |
| `ferp_module` | FERP modul adi |
| `ferp_screen` | FERP ekran adi |
| `ferp_object` | `mym4004`, `mym2008` gibi nesne kodu |
| `ferp_label_code` | `lblMMFB0_NUMBER` gibi label |
| `ferp_label_text` | FERP ekran etiketi |
| `mes_entity` | `work_order`, `product`, `operator`, `movement` vb. |
| `mes_field` | MES canonical alan adi |
| `required_flag` | Zorunlu mu |
| `direction` | import, export, both |
| `default_value` | Bos gelirse kullanilacak deger |
| `notes` | Mapping notu |

Kural:

- FERP label kodlari ic MES domain modelinin ana kolon isimleri olmamalidir.
- Label'lar import/export sinirinda canonical MES alanlarina cevrilmelidir.
- `MAP_FERPLabels` bu ceviriyi dokumante eden integration masterdata olarak ele alinmalidir.

## 12. Ileride SQL'e Gecis Karsiliklari

| Hedef workbook sheet | SQL karsiligi | Gecis tipi |
| --- | --- | --- |
| `MD_Operators` | `operators` | Master table |
| `MD_Stations` | `lines`, `stations` | Master table |
| `MD_FaultTypes` | `fault_types` | Master table |
| `MD_MaintenanceSteps` | `maintenance_steps` | Master table |
| `MD_Products` | `products`, `product_color_map` | Master table |
| `MD_Shifts` | `shifts` | Master table |
| `LK_Colors` | `colors` | Lookup |
| `LK_Sources` | `sources` | Lookup |
| `LK_EventTypes` | `event_types` | Lookup |
| `LK_DecisionSources` | `decision_sources` | Lookup |
| `LK_WorkOrderStatuses` | `work_order_statuses` | Lookup |
| `MD_OperationDefinitions` | `operation_definitions` | Master table |
| `MAP_FERPLabels` | `ferp_label_mappings` | Integration mapping |

Gecis kurallari:

- Ilk fazda mevcut `0_Tanimlamalar` okunmaya devam etmelidir.
- SQL master tables yazilmadan once workbook ve SQL arasinda fark raporu uretilmelidir.
- Runtime state SQL'e tasinacaksa masterdata tablolarindan ayrilmalidir.
- Audit workbook yazimi ilk fazda korunmalidir.

## 13. Riskler ve Koruyucu Kurallar

| Risk | Etki | Koruyucu kural |
| --- | --- | --- |
| `0_Tanimlamalar` gunluk audit workbook icinde kalmaya devam eder | Masterdata ile audit/projection siniri karisir | Hedefte `FERP_MasterData.xlsx` veya SQL master tables ayrimi yap |
| Kod lookup'lari ile sheet lookup'lari farkli kalir | Event id, color id veya source id tutarsizligi olusur | Lookup sozlesmesini tek dokumanda sabitle ve test planla |
| FERP label kodlari domain kolonlarina sizabilir | MES modeli FERP'e bagimli hale gelir | `MAP_FERPLabels` ile canonical alanlara cevir |
| Cihaz session bilgisi masterdata'ya yazilir | Canli runtime state kataloglarla karisir | Device definition ile device session ayrimi yap |
| Bakim kaydi ile bakim adim katalogu karisir | Checklist gecmisi yanlis kaynakta tutulur | `maintenance_steps` masterdata, `maintenance_records` audit olarak ayrilir |
| Urun/stok masterdata'si resmi ERP stok gibi kullanilir | Stok dogrulugu ve sorumluluk karisir | MES urun katalogu operasyonel mapping icindir; resmi stok ERP'dedir |

## 14. Uygulanacak Sonraki 5 Is

1. `0_Tanimlamalar` kolon sozlesmesini blok blok dokumante et ve mevcut kodda hangi bloklarin aktif okundugunu isaretle.
2. `FERP_MasterData.xlsx` icin bos sheet/kolon taslagini dokumantasyon olarak hazirla; henuz template veya kod degistirme.
3. `MAP_FERPLabels` icin MES canonical alan sozlugunu `docs/database-plan.md` ile uyumlu hale getir.
4. Masterdata lookup'lari ile `excel_runtime.py` icindeki hardcoded lookup degerleri arasinda fark kontrolu icin test planini yaz.
5. Database fazinda masterdata tablolarinin once read-only shadow olarak eklenecegi, sonra kaynak otoritesi olarak devralacagi gecis planini hazirla.
