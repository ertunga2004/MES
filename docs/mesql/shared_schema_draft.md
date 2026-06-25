# MESQL Shared Schema Draft

Bu dokuman 3B - Shared Schema Draft sprinti icin ortak veri tabani taslagini tarif eder. Production migration degildir; mevcut MES Web runtime davranisini, Docker/runtime ayarlarini ve `mes` schema cekirdegini degistirmez.

## Amac

MESQL ortak veri tabaninda BOM/BOP, ERP/F-ERP ve MES arasinda paylasilacak uretim hazirlik verisi icin ilk taslak domainleri, tablo ailelerini, iliskileri ve validation kararlarini netlestirmek.

Bu sprintin temel hedefi, ileride yazilacak migration ve importer icin karar zemini olusturmaktir.

## Kapsam Disi Alanlar

| Kapsam disi | Not |
|---|---|
| Production DB migration | `db/drafts/mesql_shared_schema_draft.sql` uygulanacak migration degildir |
| Runtime/Docker degisikligi | Docker, compose, env ve runtime adapter degismez |
| MES Web davranisi | Mevcut kiosk/dashboard/acceptance akisi degismez |
| Mevcut `mes` schema redesign | `mes.work_orders`, `mes.station_queue`, `mes.work_order_events`, `mes.package_component_wip` korunur |
| BOM/BOP gercek release JSON alan adlari | Henuz acik; bu dokuman is nesnesi seviyesinde kalir |
| MESQL Backend API endpointleri | Endpoint adi uydurulmaz |

## Sema Aileleri

| Sema | Rol |
|---|---|
| `mesql_master` | Urun, urun revizyonu ve komponent master adaylari |
| `mesql_manufacturing` | MBOM, BOP, operasyon-station mapping ve package BOM release taslaklari |
| `mes` | Mevcut MES operational runtime/mirror cekirdegi; bu sprintte degismez |

## `mesql_master` Domain

`mesql_master` domaini ERP/F-ERP, BOM/BOP ve MES arasinda paylasilacak master data adaylarini tutar.

| Tablo | Amac |
|---|---|
| `mesql_master.products` | Uretilecek urun/stok master adayi |
| `mesql_master.product_revisions` | Product revision ve release lifecycle |
| `mesql_master.components` | MBOM ve package BOM satirlarinda kullanilacak komponent master adayi |

ERP/F-ERP label siniri:

| Is anlami | Bilinen F-ERP label |
|---|---|
| Stok/urun/component kodu | `lblMTM00_CODE` |
| Stok/urun/component adi | `lblMTM00_NAME` |
| Stok tipi | `lblMTMT0_CODE` |
| Birim | `lblMUNT0_CODE` |

Component icin de yalniz bu bilinen stok label ailesi kullanilir; component'e ozel bilinmeyen F-ERP label uydurulmaz.

## `mesql_manufacturing` Domain

`mesql_manufacturing` domaini BOM/BOP tarafindan release edilen uretim hazirlik yapisini tutar. Operation/station mapping icin canonical kaynak bu domaindir.

| Tablo | Amac |
|---|---|
| `mesql_manufacturing.mbom_headers` | Product revision bazli MBOM release basligi |
| `mesql_manufacturing.mbom_lines` | MBOM component ihtiyac satirlari |
| `mesql_manufacturing.bop_headers` | Product revision bazli BOP/rota release basligi |
| `mesql_manufacturing.bop_operations` | BOP operasyon siralari ve sure adaylari |
| `mesql_manufacturing.operation_station_mapping` | Operasyonun MES station ve F-ERP work center baglami |
| `mesql_manufacturing.package_bom_headers` | Paket urun revision bazli package BOM basligi |
| `mesql_manufacturing.package_bom_lines` | Paket component ihtiyac satirlari |

## ERP/F-ERP Mapping Siniri

Bilinen label disina cikilmaz.

| MESQL alani | F-ERP label baglami | Not |
|---|---|---|
| `product_code`, `component_code` | `lblMTM00_CODE` | ERP'de yoksa create candidate |
| `product_name`, `component_name` | `lblMTM00_NAME` | Kod varsa uyumluluk kontrolu gerekir |
| `product_type`, `component_type` | `lblMTMT0_CODE` | Deger listesi henuz acik |
| `unit_code` | `lblMUNT0_CODE` | Birim uyumsuzlugu conflict sebebi |
| `work_center_code` | `lblMFW00_CODE` | Operation/station mapping icinde |
| `operation_code` | `lblMFWO0_CODE` | BOP operation icinde |
| `setup_time_seconds` | `lblMMFB4_SETUP_TIME` | Hazirlik suresi |
| `cycle_time_seconds` | `lblMMFB4_TIME` | Ideal cycle/islem suresi |

ERP'de stok karti varsa sessiz overwrite yoktur: kod yoksa create candidate, kod var ve uyumluysa map/skip, celiski varsa conflict-report/manual review, revizyon farki varsa revision review.

## MES Runtime ile Iliski

| MES runtime alani | Shared schema iliskisi |
|---|---|
| `mes.station_queue` | Gunluk operasyonel queue'dur; master data otoritesi degildir |
| `mes.work_orders` | ERP'den gelen is emri current-state mirror/read kaynagi |
| `mes.work_order_events` | Start, finish, accept, cancel, reorder ve package transition log |
| `mes.package_component_wip` | Paketleme komponent uygunluk ve reserve/consume kontrol kaydi |
| `mes.package_sessions` | Sonraki hazirlik alani; shared schema master data degildir |

MES'e dagitilacak operasyon mapping'siz olamaz. `RELEASED` olmayan hazirlik MES runtime'a dagitilmaz.

## Taslak Tablo Listesi

| Sema | Tablo |
|---|---|
| `mesql_master` | `products` |
| `mesql_master` | `product_revisions` |
| `mesql_master` | `components` |
| `mesql_manufacturing` | `mbom_headers` |
| `mesql_manufacturing` | `mbom_lines` |
| `mesql_manufacturing` | `bop_headers` |
| `mesql_manufacturing` | `bop_operations` |
| `mesql_manufacturing` | `operation_station_mapping` |
| `mesql_manufacturing` | `package_bom_headers` |
| `mesql_manufacturing` | `package_bom_lines` |

## Ana Iliskiler

| Iliski | Anlam |
|---|---|
| `product_revisions.product_id -> products.product_id` | Her product revision bir product'a baglidir |
| `mbom_headers.product_revision_id -> product_revisions.product_revision_id` | MBOM product revision bazlidir |
| `mbom_lines.mbom_id -> mbom_headers.mbom_id` | MBOM satirlari basliga baglidir |
| `mbom_lines.component_id -> components.component_id` | MBOM satiri komponent kullanir |
| `bop_headers.product_revision_id -> product_revisions.product_revision_id` | BOP product revision bazlidir |
| `bop_operations.bop_id -> bop_headers.bop_id` | BOP operasyonlari basliga baglidir |
| `operation_station_mapping.bop_operation_id -> bop_operations.bop_operation_id` | Mapping operasyon bazlidir |
| `package_bom_headers.package_product_revision_id -> product_revisions.product_revision_id` | Package BOM paket product revision bazlidir |
| `package_bom_lines.package_bom_id -> package_bom_headers.package_bom_id` | Package BOM satirlari basliga baglidir |
| `package_bom_lines.component_id -> components.component_id` | Package BOM satiri komponent kullanir |

## Unique Constraint Kararlari

| Nesne | Unique karar |
|---|---|
| Products | `UNIQUE(product_code)` |
| Product revisions | `UNIQUE(product_id, revision_code)` |
| MBOM headers | `UNIQUE(product_revision_id, mbom_revision, plant_code)` |
| BOP headers | `UNIQUE(product_revision_id, bop_revision, plant_code)` |
| Package BOM headers | `UNIQUE(package_product_revision_id, package_bom_revision, plant_code)` |
| BOP operations | `UNIQUE(bop_id, operation_sequence)` |

Ayni `product_revision_id` + `plant_code` icin ayni anda birden fazla aktif `RELEASED` MBOM/BOP olmamalidir. Draft SQL bunu `release_status = 'RELEASED' AND valid_to IS NULL` kosullu partial unique index ile gosterir. Alternatif olarak eski release `ARCHIVED` yapilabilir veya `valid_to` ile kapatilabilir.

## Release / Validation Kurallari

| Kural | Sonuc |
|---|---|
| Kabul edilen `release_status` degerleri | `DRAFT`, `IN_REVIEW`, `APPROVED`, `RELEASED`, `ARCHIVED`, `REJECTED`, `PENDING` |
| ERP/MES dagitimi | Sadece `RELEASED` veri gider |
| `APPROVED` veri | Uretime cikmak icin yeterli degildir |
| `PENDING` veri | Staging/import bekler |
| `ARCHIVED` / `REJECTED` veri | Uretime cikamaz |
| `required_quantity` | Pozitif olmali |
| `operation_sequence` | Pozitif olmali ve ayni BOP icinde tekil olmali |
| `validation_level` | `WARN`, `HOLD`, `FAIL`, `PASS` |
| `DRAFT` / `IN_REVIEW` mapping eksigi | WARN |
| `APPROVED` mapping eksigi | HOLD |
| `RELEASED` mapping eksigi | FAIL |

`RELEASED` BOP operation icin station mapping zorunlulugu SQL CHECK ile degil, validation job/trigger veya importer validation katmaninda ele alinmalidir. Bunun nedeni kuralin birden fazla tabloyu kapsamasidir.

## Acik Kalan Alanlar

| Alan | Etki |
|---|---|
| BOM/BOP gercek release JSON alan adlari | Importer mapping tasarimi |
| MESQL Backend API endpoint isimleri | API servis/client entegrasyonu |
| MESQL -> ERP hazirlik aktarim mekanizmasi | Faz 2 servis/entegrasyon katmani |
| F-ERP stok hareket quantity label eksikligi | Resmi stok hareket import kesinlestirme |
| WARN/FAIL hata kod sozlugu | Validation response standardi |
| Operation/station master datasinin uzun vadeli sahipligi | MESQL manufacturing domain karari bugun canonical; uzun vadeli governance ayrintisi acik |
| EBOM -> MBOM donusum kurali | Engineering -> manufacturing donusum sureci |
| ERP create/map/conflict lifecycle ayrintisi | ERP hazirlik aktarimi ve manual review akisi |

## 3C Icin Oneriler

| Oneri | Hedef |
|---|---|
| Shared schema DDL review | Draft SQL'i production migration'a donusturmeden once constraint ve naming review |
| Release importer contract | BOM/BOP gercek release JSON alan adlarini mapping dokumaniyla sabitlemek |
| Validation error dictionary | WARN/HOLD/FAIL/PASS icin hata kodlari ve response sozlugu |
| ERP preparation adapter plan | Manuel giris, Excel import, label-first JSON veya REST/API kararini kapatmak |
| Conflict report tasarimi | ERP'de var olan stok karti map/skip/conflict lifecycle'ini raporlamak |
