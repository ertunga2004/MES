# Runtime and Shared Schema Boundary

Bu dokuman runtime `mes` schema ile MESQL shared schema sinirini tanimlar. Migration veya runtime degisikligi degildir.

## Runtime `mes` Schema Amaci

Runtime `mes` schema, mevcut MES Web calismasini guvenli sekilde mirror etmek, dogrulamak ve kademeli DB gecisine hazirlamak icindir.

Runtime schema ozellikleri:

- Mevcut MES Web davranisini destekler.
- JSON/workbook/FERP/MQTT yollarini bir anda ortadan kaldirmaz.
- Feature flag ile read/write gecislerine izin verir.
- Station queue, package session ve event log gibi operasyonel runtime verisini tutar.

## MESQL Shared Schema Amaci

MESQL shared schema, ERP/F-ERP, BOM/BOP ve MES arasinda ortak master/manufacturing veri sozlesmesini tasarlamak icindir.

Shared schema ozellikleri:

- Product, revision, component, MBOM, BOP, operation/station mapping ve package BOM gibi hazirlik verisini hedefler.
- BOM/BOP source owner ve gercek payload gelmeden production importer'a donmez.
- Master data ve release lifecycle kararlarini tasir.

## Veri Sinifi

| Veri | Sinif | Not |
| --- | --- | --- |
| Work orders | Runtime mirror/foundation | ERP/FERP otoritesi; `mes.work_orders` runtime read overlay icin kullanilabilir. |
| Production completions | Runtime event/mirror | Event-level log; `external_ref` compatibility ve unique gate ister. |
| Vision events | Runtime event/backfill/live aday | `vision_track_id` tek basina key degildir; source policy gerekir. |
| OEE snapshots | Runtime analytics snapshot adayi | Policy ve natural key netlesmeden migration/hook yok. |
| Package BOM runtime lines | Runtime package flow support | `mes.package_bom_lines` shared package BOM master yerine gecmez. |
| Package sessions | Runtime execution/session | Package preparation state; shared master data degildir. |
| Station queue | Runtime daily queue | Master data otoritesi degildir; operasyonel siralama verisidir. |
| Product master | Shared master | MESQL shared schema adayi; ERP/FERP conflict kuralina bagli. |
| MBOM/BOP | Shared manufacturing | Source owner gelmeden production migration/importer yok. |
| Operation/station mapping | Shared manufacturing canonical | MES'e dagitim icin gerekli; station_queue ile karistirilmaz. |

## JSON / Workbook / Runtime State Rolu

- `logs/oee_runtime_state.json` runtime state icin atomik sinirdir.
- Workbook audit/reporting ve is emri durum akislari icin korunur.
- FERP import/export dosyalari entegrasyon siniri olarak kalir.
- SQL gecisi bu yollarin aniden kaldirilmasi anlamina gelmez.

## Feature Flag Kurallari

- DB write hook ve DB read ayni fazda acilmaz.
- Migration ve runtime hook ayni sprintte yapilmaz.
- Flag kapaliyken runtime davranisi degismez.
- DB hatasi runtime'i cokertmez.
- Shadow read/compare temiz olmadan read source switch yapilmaz.

## Karistirilmamasi Gereken Noktalar

| Yanlis varsayim | Dogru sinir |
| --- | --- |
| `mes.station_queue` master operation/station mapping'dir. | Degildir; gunluk operasyonel queue'dur. |
| `mes.package_bom_lines` shared package BOM master'dir. | Degildir; runtime package flow support tablosudur. |
| Shared schema draft SQL production migration'dir. | Degildir; `db/drafts` altinda review taslagidir. |
| Work order DB read overlay full SQL source-of-truth'tur. | Degildir; guarded MVP read overlay'dir. |
| BOM/BOP canonical payload gercek source field kanitidir. | Degildir; source owner payload gerekir. |
