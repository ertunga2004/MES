# MESQL Compatibility Report Plan

Bu dokuman production migration oncesi calismasi gereken read-only raporlari tanimlar. Raporlar migration uygulamaz, veri degistirmez ve sadece SELECT/read-only analiz mantigiyla tasarlanmalidir.

## Genel Ilke

Her production migration adayindan once:

- Hedef PC'de DB backup alinmalidir.
- Compatibility report read-only calismalidir.
- Duplicate, null/blank, orphan ve timestamp riskleri raporlanmalidir.
- Rapor temiz degilse migration apply yapilmamalidir.

## Runtime `mes` Kontrolleri

| Alan | Read-only kontrol | Migration etkisi |
| --- | --- | --- |
| `mes.work_orders.order_id` | Null/blank `order_id`, duplicate `order_id`, count, status dagilimi. | Read overlay ve import/mirror guvenligi. |
| `mes.production_completions.external_ref` | Null/blank, duplicate, timestamp sanity, source dagilimi. | Live hook idempotency ve unique key guvenligi. |
| `mes.vision_events.external_ref` | Null/blank, duplicate, `event_key`/track policy uyumu, detected_at sanity. | Vision event idempotency ve live hook gate. |
| `mes.work_order_events.external_ref` | Null/blank, duplicate, orphan `order_id`, event type dagilimi. | Transition event log guvenligi. |
| `mes.item_station_events(source, external_ref)` | Duplicate pair, blank fields, station_code dagilimi. | Station event writer idempotency. |
| `mes.station_queue` | `station_code + order_id` uniqueness, active rank duplicate, orphan order_id. | Gunluk queue tutarliligi. |
| `mes.package_sessions` | Package order relation, station/status dagilimi, open session duplicate. | Package execution/session guvenligi. |
| `mes.package_bom_lines` | Active component duplicate, quantity positive, source relation. | Runtime package BOM support guvenligi. |
| `mes.package_component_wip` | Duplicate source/external_ref, session relation, status dagilimi. | Reserve/consume flow guvenligi. |
| `mes.package_traceability` | Duplicate external_ref, package/session relation. | Runtime traceability guvenligi. |

## Shared Schema Kontrolleri

Shared MESQL schema icin read-only compatibility raporu ancak gercek source payload geldikten sonra anlamli olur.

| Alan | Neden source payload gerekir |
| --- | --- |
| Product master uniqueness | Gercek product_code ve ERP map/skip/conflict davranisi bilinmeli. |
| Product revision uniqueness | Gercek revision field ve product relation bilinmeli. |
| MBOM uniqueness | Gercek MBOM revision, plant ve active release davranisi bilinmeli. |
| BOP uniqueness | Gercek BOP revision, operation sequence ve plant davranisi bilinmeli. |
| Operation/station mapping | Gercek station/work center mapping kaynagi bilinmeli. |
| Package BOM uniqueness | Gercek package BOM revision ve line yapisi bilinmeli. |

## Duplicate / Null / Orphan Rapor Tipleri

| Rapor tipi | Amac |
| --- | --- |
| Count baseline | Migration oncesi ve sonrasi veri sayisini karsilastirmak. |
| Null/blank key report | Unique/index uygulanamayacak kayitlari bulmak. |
| Duplicate key report | Idempotency ve unique migration riskini bulmak. |
| Orphan relation report | Soft-reference kopukluklarini bulmak. |
| Timestamp sanity report | Gelecek/fazla eski timestamp risklerini bulmak. |
| Status distribution report | Release/runtime state gecis risklerini gormek. |

## Rapor Sinirlari

- Rapor SQL'i `SELECT` disinda veri degistiren ifade kullanmamalidir.
- Rapor otomatik cleanup yapmamalidir.
- Rapor sonucu migration onayi degildir; sadece gate girdisidir.
- Fail sonucu alinirsa cleanup planı ayri yazilmalidir.

## Sonuc

Compatibility report, migration dosyasindan once gelmelidir. Hedef PC'de backup, read-only rapor, temiz sonuc ve rollback planı olmadan production migration uygulanmamalidir.
