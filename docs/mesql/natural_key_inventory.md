# MESQL Natural Key Inventory

Bu dokuman MESQL schema unique/natural-key kararlarini aktif dokumana konsolide eder. Kaynak notlar: `docs/agent_memory/19_schema_natural_key_inventory.md`, `docs/mesql/shared_schema_decision_note.md`, `docs/mesql/shared_schema_migration_review.md` ve BOM/BOP contract dokumanlari.

Bu dokuman production migration degildir. Migration yazmadan once compatibility report, backup ve kullanici onayi gerekir.

## Genel Ilke

MESQL tarafinda surrogate primary key kullanilabilir; fakat integration, import ve release lifecycle icin natural key ve unique kararlar ayrica net olmalidir. Unique constraint yazilacaksa once mevcut veriyle uyumluluk kanitlanmalidir.

## Product ve Revision

| Karar | Natural/unique key | Not |
| --- | --- | --- |
| Product master | `product_code` unique | Product code product master seviyesinde benzersiz olmalidir. |
| Product revision | `UNIQUE(product_id, revision_code)` | Revision code tek basina global unique kabul edilmez. |
| Component master | Component code icin product/component ayrimi netlesmeli | F-ERP stok karti davranisiyla uyumlu olmali. |

## MBOM / BOP / Package BOM

| Nesne | Onerilen uniqueness | Production migration oncesi durum |
| --- | --- | --- |
| MBOM | `UNIQUE(product_revision_id, mbom_revision, plant_code)` | Gercek source payload bekleniyor. |
| BOP | `UNIQUE(product_revision_id, bop_revision, plant_code)` | Gercek source payload bekleniyor. |
| Package BOM | `UNIQUE(package_product_revision_id, package_bom_revision, plant_code)` | Gercek source payload bekleniyor. |

Ayni `product_revision_id + plant_code` icin ayni anda birden fazla aktif `RELEASED` MBOM/BOP olmamalidir. Yeni release geldiginde eski release `ARCHIVED` yapilmali veya `valid_to` ile kapatilmalidir.

## Operation ve Mapping

| Karar | Natural/unique key | Not |
| --- | --- | --- |
| BOP operation sequence | BOP icinde `operation_sequence` unique | Duplicate sequence validation FAIL olmalidir. |
| Operation code | Source ve ERP/F-ERP mapping icin stable code gerekir | Gercek BOM/BOP field adi bekleniyor. |
| Station mapping | Operation + station/work center + plant/revision baglami netlesmeli | Mapping'siz RELEASED operasyon MES'e dagitilamaz. |
| Work center mapping | ERP/F-ERP work center aktarimi icin code conflict kuralina tabi | Bilinen label disina cikilmamalidir. |

Operation/station mapping icin canonical kaynak MESQL manufacturing domainidir. MES `station_queue` gunluk operasyonel siralamadir; master data otoritesi degildir.

## Runtime `mes` Schema Natural Keyleri

Mevcut runtime mirror/foundation tarafinda agent memory envanteri su karar kapilarini verir:

| Runtime tablo | Natural key | Durum |
| --- | --- | --- |
| `mes.work_orders` | `order_id` | Mevcut unique constraint var. |
| `mes.production_completions` | `external_ref` | UNIQUE migration oncesi compatibility report gerekir. |
| `mes.vision_events` | `external_ref` | `vision_track_id` tek basina key degildir; event_key veya `vision_track_id + event_type + detected_at` gerekir. |
| `mes.oee_snapshots` | `snapshot_at + shift_id` | Policy netlesmeden hook/migration yok. |
| `mes.device_sessions` | Belirsiz | Current-state/session ayrimi netlesmeden live hook unsafe. |

## ERP / F-ERP Conflict Kurali

- ERP'de `lblMTM00_CODE` varsa sessiz overwrite yapilmaz.
- Kod yoksa create candidate.
- Kod var ve ad/tip/birim uyumluysa map/skip.
- Kod var ama ad/tip/birim celisiyorsa conflict report/manual review.
- Revizyon farki varsa revision review.

Bu kurallar product/component master key kararlarini etkiler. F-ERP label uydurulmaz; sadece kaynak dokumanlarda bilinen label'lar kullanilir.

## Release Status ve Validation Etkisi

Release status listesi:

- `DRAFT`
- `IN_REVIEW`
- `APPROVED`
- `RELEASED`
- `ARCHIVED`
- `REJECTED`
- `PENDING`

Kurallar:

- ERP/MES'e sadece `RELEASED` veri gider.
- `APPROVED` uretime cikmak icin yeterli degildir.
- `PENDING` staging/import bekleyen durumdur.
- `ARCHIVED` ve `REJECTED` uretime cikamaz.
- `RELEASED` mapping eksikse FAIL.
- `APPROVED` mapping eksikse HOLD.
- `DRAFT` / `IN_REVIEW` mapping eksikse WARN.

## Production Migration Oncesi Kapanmasi Gerekenler

- Gercek BOM/BOP source payload ve field adlari alinmali.
- Release status crosswalk kaynak sistemle dogrulanmali.
- Product/revision/MBOM/BOP/package BOM source revision field'lari netlesmeli.
- Active released uniqueness modeli mevcut veriyle test edilmeli.
- Operation sequence ve station/work center mapping uniqueness netlesmeli.
- Runtime `production_completions.external_ref` ve `vision_events.external_ref` icin read-only compatibility report temiz olmali.
- DB backup alinmadan migration uygulanmamali.
- Migration, runtime hook veya importer gelistirmesinden ayri fazda yapilmali.
