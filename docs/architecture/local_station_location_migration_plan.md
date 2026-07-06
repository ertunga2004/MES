# Local Station / Location Migration Plan

## 1. Amaç

Bu doküman, `docs/architecture/local_station_location_buffer_blueprint.md` içinde tanımlanan station/location/buffer modelini ileride uygulanabilir additive migration planına dönüştürür.

Blueprint kavram sınırlarını tanımlar; bu plan ise gerçek migration implementasyonu öncesinde paketleri, tablo adaylarını, seed kararlarını, idempotency kurallarını, rollback yaklaşımını ve verification smoke kapsamını netleştirir.

Bu doküman migration dosyası değildir. SQL DDL, Python kodu, Docker ayarı, MESQL push/pull veya DB değişikliği içermez.

## 2. Kapsam Dışı

- SQL migration implementasyonu yok.
- Python/API değişikliği yok.
- Docker, compose, Dockerfile veya CMD değişikliği yok.
- MESQL push/pull yok.
- ERP/F-ERP implementasyonu yok.
- Tam WMS tasarımı yok.
- Existing tablo kırıcı değişiklik yok.
- DB bağlantısı, veri yazma veya test çalıştırma yok.

## 3. Mevcut Tablo/Akış Varsayımları

Bu plan, mevcut dokümantasyondaki local MES DB kullanımını şu şekilde varsayar:

- `work_orders`: Work order yaşam döngüsünün üst seviye kaydıdır. Local successor smoke sonunda work order completed durumuna geçebilmektedir.
- `work_order_operations`: Operation lifecycle için local execution source-of-truth kabul edilir. Execution identity `work_order_operation_id` seviyesinde korunmalıdır.
- `station_queue`: Station bazlı operation execution kuyruğudur. Mevcut doğrulanmış davranış repeated operation complete çağrısında duplicate successor queue üretmemelidir.
- Station events / operation lifecycle events: Start/complete ve sensor kaynaklı olaylar mevcut olabilir; bu plan exact event schema değişikliği zorunlu kılmaz.
- `integration_outbox`: Mevcut olabilir ve ileride export/sync için kullanılabilir; bu plan MESQL push/pull davranışı açmaz.
- Exact schema bu dokümanda zorunlu olarak değiştirilmez. Bu plan sadece additive tablo/view adaylarını ve migration sırasını tanımlar.

Mevcut verified baseline:

- `ASSEMBLY_01` op10 complete.
- `PACKAGING_01` op20 queued.
- Repeated op10 complete duplicate queue oluşturmadı.
- `PACKAGING_01` op20 complete.
- Work order completed.

## 4. Additive Migration Stratejisi

- Yeni tablolar `mes` schema altında eklenecek şekilde planlanmalıdır.
- Existing tablolar destructively değiştirilmeyecektir.
- İlk faz seed/read-only visibility olmalıdır.
- İkinci faz shadow-write olmalıdır.
- Üçüncü faz dashboard/kiosk/API read kullanımına kontrollü geçiş olmalıdır.
- Rollback için yeni tabloları ve feature flag'leri devre dışı bırakmak yeterli olmalıdır.
- İlk fazda existing runtime davranışı, local successor activation ve station queue visibility kırılmamalıdır.
- MESQL frozen kaldığı sürece hiçbir migration paketi MESQL push/pull ön koşulu taşımamalıdır.
- `mes_postgres_data` named volume korunmalıdır; volume silme rollback yöntemi değildir.

## 5. Önerilen Migration Paketleri

### Paket A - Static Master Data

Amaç: Location ve station-location binding kavramlarını local MES DB içinde additive olarak temsil etmek.

Ön koşul:

- Blueprint'teki location code ve binding role kararları kabul edilmiş olmalı.
- Existing `ASSEMBLY_01` ve `PACKAGING_01` station domain key'leri korunmalı.

Tablo/view adayları:

- `mes.locations`
- `mes.station_location_bindings`

Seed ihtiyacı:

- Minimum locations seed edilir.
- `ASSEMBLY_01` ve `PACKAGING_01` için default input, active_wip, output_good, output_scrap/output_buffer binding'leri seed edilir.

Risk:

- Station ile location karıştırılırsa buffer station gibi davranmaya başlar.
- Binding role isimleri erken sabitlenmezse migration sonrası API ve UI sözlüğü dağılır.

Kabul kriteri:

- Minimum seed tekrar çalıştırılabilir olmalıdır.
- Existing operation lifecycle ve station queue davranışı değişmemelidir.
- Buffer location subtype olarak kalmalıdır.

Rollback notu:

- Yeni master data tabloları kullanılmaz hale getirilebilir.
- Existing `work_orders`, `work_order_operations` ve `station_queue` akışı çalışmaya devam etmelidir.

### Paket B - Movement Ledger

Amaç: Operation start/complete, package close, correction ve sensor evidence kaynaklı stok etkilerini append-only ledger olarak yazabilecek altyapıyı tanımlamak.

Ön koşul:

- Paket A locations ve bindings mevcut olmalı.
- Operation lifecycle event kökünden idempotency key üretimi tasarlanmış olmalı.

Tablo/view adayları:

- `mes.inventory_movements`

Seed ihtiyacı:

- Static seed gerekmez.
- Movement type ve status sözlüğü uygulama veya DB seviyesinde sabitlenmelidir.

Risk:

- Idempotency key zorunlu olmazsa repeated complete duplicate movement üretir.
- Movement ledger yerine current balance tablo source-of-truth yapılırsa audit zayıflar.

Kabul kriteri:

- Aynı operation complete tekrar geldiğinde aynı logical movement ikinci kez yazılmamalıdır.
- Movement kayıtları source event ve operation bağlamını taşımalıdır.
- Shadow-write kapalıyken existing akış etkilenmemelidir.

Rollback notu:

- Shadow-write feature flag kapatılır.
- Ledger okunmuyorsa existing runtime ve DB operation lifecycle devam eder.

### Paket C - Balance Visibility

Amaç: Location/product bazında okunabilir inventory balance görünürlüğü sağlamak.

Ön koşul:

- Paket B movement ledger modeli tasarlanmış olmalı.
- Quantity ve UOM standardı en az MVP seviyesinde netleşmiş olmalı.

Tablo/view adayları:

- `mes.inventory_balances` view
- İleride materialized view
- İleride derived current-state tablo

Seed ihtiyacı:

- Balance view için seed gerekmez.
- Derived tablo seçilirse başlangıç snapshot stratejisi gerekir.

Risk:

- Balance tablo doğrudan elle güncellenirse ledger ile drift oluşur.
- Materialized view refresh politikası yanlışsa kiosk/dashboard eski veri gösterebilir.

Kabul kriteri:

- MVP'de balance değerleri ledger'dan türetilebilir olmalıdır.
- Read feature flag kapalıyken dashboard/kiosk mevcut davranışla çalışmalıdır.

Rollback notu:

- Balance read feature flag kapatılır.
- View veya derived tablo kullanılmaz; existing runtime projections korunur.

### Paket D - Event Linkage

Amaç: Sensor event, operation event ve movement arasında açıklanabilir bağ kurmak.

Ön koşul:

- Sensor event'in stok hareketi değil fiziksel kanıt olduğu kararına uyulmalı.
- Operation context yoksa movement posted edilmemesi kuralı kabul edilmeli.

Tablo/view adayları:

- `mes.sensor_event_links`
- Alternatif olarak existing sensor/operation event alanlarına ilişki stratejisi

Seed ihtiyacı:

- Static seed gerekmez.
- Interpretation ve confidence sözlüğü belirlenmelidir.

Risk:

- Sensor event doğrudan stok düşerse duplicate event negatif stok veya audit hatası yaratır.
- Confidence ve operation context olmadan movement üretmek yanlış stok lokasyonu oluşturur.

Kabul kriteri:

- Sensor event movement candidate/evidence olarak saklanabilmelidir.
- Movement posted için operation bağlamı ve idempotency kuralı aranmalıdır.

Rollback notu:

- Sensor event link feature flag kapatılır.
- Existing sensor event akışı stok ledger'ı etkilemeden devam eder.

## 6. Tablo Adayları ve Alan Önerileri

Bu bölüm DDL değildir. Alan adları migration tasarımı için aday listedir.

### `mes.locations`

| Alan | Not |
| --- | --- |
| `location_id` | Primary identity adayı. |
| `location_code` | İnsan okunur ve unique domain key adayı. |
| `location_name` | UI/readability için ad. |
| `location_type` | Location sınıfı. |
| `parent_location_id` | Nested alan veya bölge için nullable parent. |
| `station_code` | Bir station'a bağlı WIP gibi durumlar için nullable. |
| `active` | Soft enable/disable. |
| `metadata` | Esnek ek bilgi. |
| `created_at` | Oluşturma zamanı. |
| `updated_at` | Güncelleme zamanı. |

`location_type` örnekleri:

- `raw_material`
- `wip`
- `buffer`
- `finished_goods`
- `scrap`
- `hold`
- `rework`

### `mes.station_location_bindings`

| Alan | Not |
| --- | --- |
| `binding_id` | Primary identity adayı. |
| `station_code` | Station domain key. |
| `role` | Binding rolü. |
| `location_id` | Bound location. |
| `item_scope` | Ürün/item bazlı override için nullable. |
| `operation_scope` | Operation/route override için nullable. |
| `priority` | Birden fazla aday olduğunda seçim sırası. |
| `active` | Aktif binding filtresi. |
| `metadata` | Esnek ek bilgi. |
| `created_at` | Oluşturma zamanı. |
| `updated_at` | Güncelleme zamanı. |

`role` örnekleri:

- `input`
- `active_wip`
- `output_good`
- `output_scrap`
- `output_buffer`

### `mes.inventory_movements`

| Alan | Not |
| --- | --- |
| `movement_id` | Primary identity adayı. |
| `movement_type` | Stok hareket tipi. |
| `item_id` | Tekil item veya lot ilişkisi; nullable olabilir. |
| `order_id` | Readable/denormalized work order bağı. |
| `work_order_operation_id` | Operation execution identity bağı. |
| `station_code` | Movement kaynağı station. |
| `from_location_id` | Çıkış location; üretim çıktısında nullable olabilir. |
| `to_location_id` | Giriş location; consume hareketinde nullable olabilir. |
| `quantity` | Hareket miktarı. |
| `uom` | Ölçü birimi. |
| `source_event_type` | Operation complete, sensor event, package close gibi event türü. |
| `source_event_id` | Event identity. |
| `idempotency_key` | Duplicate prevention için doğal key. |
| `movement_status` | Pending/posted/voided durumu. |
| `occurred_at` | İşin gerçekleştiği zaman. |
| `metadata` | Reason, actor, confidence gibi ek bilgi. |
| `created_at` | Kayıt zamanı. |

`movement_type` örnekleri:

- `issue_to_operation`
- `move_to_wip`
- `operation_output_good`
- `operation_output_scrap`
- `transfer`
- `correction`
- `package_close`

`movement_status` örnekleri:

- `pending`
- `posted`
- `voided`

### `mes.inventory_balances`

Karar noktası:

- View mi olmalı?
- Materialized view mi olmalı?
- Tablo mu olmalı?

MVP önerisi:

- İlk MVP için view/derived read önerilir.
- Ledger source-of-truth kalır.
- Dashboard/kiosk performansı yetersiz kalırsa materialized view veya derived tablo ayrı fazda değerlendirilir.
- Derived tablo seçilirse refresh, reconciliation ve drift kontrolü ayrı runbook gerektirir.

### `mes.sensor_event_links`

| Alan | Not |
| --- | --- |
| `link_id` | Primary identity adayı. |
| `sensor_event_id` | Fiziksel event identity. |
| `work_order_operation_id` | İlişkili operation; varsa. |
| `movement_id` | Üretilen movement; nullable. |
| `station_code` | Event'in station bağlamı. |
| `interpretation` | Evidence, entry, exit, candidate, trigger gibi yorum. |
| `confidence` | Yorum güven skoru veya sınıfı. |
| `created_at` | Link oluşturma zamanı. |

## 7. Minimum Seed Planı

Locations:

| Location | Type | Not |
| --- | --- | --- |
| `RAW_MATERIAL` | `raw_material` | Assembly input stok alanı. |
| `ASSEMBLY_WIP` | `wip` | Assembly aktif/WIP alanı. |
| `BETWEEN_ASSEMBLY_PACKAGING` | `buffer` | Assembly ile packaging arası buffer. |
| `PACKAGING_WIP` | `wip` | Packaging aktif/WIP alanı. |
| `FINISHED_GOODS` | `finished_goods` | Good ürün çıkışı. |
| `SCRAP_AREA` | `scrap` | Scrap/reject alanı. |
| `HOLD_AREA` | `hold` | Opsiyonel kalite bekleme alanı. |
| `REWORK_AREA` | `rework` | Opsiyonel yeniden işleme alanı. |

Stations:

- `ASSEMBLY_01`
- `PACKAGING_01`

Binding:

| Station | Role | Location |
| --- | --- | --- |
| `ASSEMBLY_01` | `input` | `RAW_MATERIAL` |
| `ASSEMBLY_01` | `active_wip` | `ASSEMBLY_WIP` |
| `ASSEMBLY_01` | `output_good` / `output_buffer` | `BETWEEN_ASSEMBLY_PACKAGING` |
| `PACKAGING_01` | `input` | `BETWEEN_ASSEMBLY_PACKAGING` |
| `PACKAGING_01` | `active_wip` | `PACKAGING_WIP` |
| `PACKAGING_01` | `output_good` | `FINISHED_GOODS` |
| `PACKAGING_01` | `output_scrap` | `SCRAP_AREA` |

Seed işlemleri tekrar çalıştırılabilir olmalıdır. Aynı `location_code` veya active binding ikinci kez duplicate üretmemelidir.

## 8. Idempotency Planı

- `station_queue` duplicate prevention mevcut doğrulanmış davranışla uyumlu kalmalıdır.
- `inventory_movements` için `idempotency_key` zorunlu olmalıdır.
- Aynı operation complete tekrar gelirse aynı movement tekrar yazılmamalıdır.
- Sensor duplicate event toleransı gerekir.
- Unique constraint adayı kavramsal olarak `idempotency_key` üzerinde düşünülmelidir; DDL bu dokümanda yazılmaz.

Önerilen `idempotency_key` örnekleri:

| Event | Key örneği |
| --- | --- |
| Operation complete good | `operation_complete:{work_order_operation_id}:good` |
| Operation complete scrap | `operation_complete:{work_order_operation_id}:scrap` |
| Operation start issue/WIP | `operation_start:{work_order_operation_id}:issue` |
| Sensor movement candidate | `sensor_event:{sensor_event_id}:movement_candidate` |
| Package close | `package_close:{package_session_id}` |

Manual correction için idempotency key opsiyonel değilse bile actor, reason ve occurred_at bilgisi zorunlu olmalıdır. Her manual correction ayrı intentional movement sayılabilir.

## 9. Operation Lifecycle Mapping

| Olay | From | To | Movement type | Not |
| --- | --- | --- | --- | --- |
| `operation start` | input location | active_wip | `issue_to_operation` veya `move_to_wip` | Operation context yoksa movement yazılmamalı. |
| `operation complete good` | active_wip | output_good/output_buffer | `operation_output_good` | Assembly için buffer'a, packaging için finished goods'a gider. |
| `operation complete scrap` | active_wip | output_scrap | `operation_output_scrap` | Scrap quantity ayrı ele alınmalı. |
| `successor activation` | Yok | Yok | Yok | Direct stock movement değildir; execution queue update'tir. Önceki operation complete movement'ı ile sonraki station input location mantıksal olarak bağlanır. |
| `package session close` | packaging WIP/component reserve | finished/scrap/hold adayı | `package_close` | Final packing veya shipment-prep hareketi ileride değerlendirilebilir. |

Successor activation, local station queue visibility için mevcut davranışı korur. Inventory movement tarafı aynı operation event'ten türeyebilir, ancak queue update ile stok movement aynı şey değildir.

## 10. Sensor Event Mapping

- `sensor_event` doğrudan stok hareketi değildir.
- `sensor_event` movement candidate veya evidence olarak kalmalıdır.
- İş emri/operasyon bağlamı yoksa movement `posted` olmamalıdır.
- Duplicate sensor event toleransı gerekir.
- `confidence` ve `interpretation` alanları gerekebilir.
- Sensor event, station entry/exit, color detection veya physical proof olarak yorumlanabilir; stok etkisi policy ve operation context ile verilmelidir.
- Aynı sensor event'ten movement üretilecekse `sensor_event:{sensor_event_id}:movement_candidate` benzeri idempotency key kullanılmalıdır.

## 11. Backfill Stratejisi

İlk migration sonrasında mevcut smoke/work_order verilerinden otomatik backfill yapılması önerilmez.

Öneri:

- İlk MVP'de geçmiş veriye destructive backfill yapılmasın.
- Yeni tablolar seed edilsin.
- Shadow-write sadece yeni olaylardan başlasın.
- Mevcut smoke verileri verification referansı olarak kalsın.
- Backfill gerekiyorsa ayrı runbook olsun.
- Backfill runbook, source event seçimi, idempotency key üretimi, dry-run raporu ve rollback notu olmadan çalıştırılmamalıdır.

## 12. Rollback Stratejisi

- Yeni tablolar additive olduğu için existing operation lifecycle çalışmaya devam etmelidir.
- Shadow-write kapatılabilmelidir.
- Balance read feature flag ile kapatılabilmelidir.
- Yeni tabloları kullanmayan endpointler etkilenmemelidir.
- `mes_postgres_data` volume silinmemelidir.
- Rollback yöntemi Docker volume silmek veya runtime data temizlemek değildir.
- MESQL push/pull rollback aracı olarak kullanılmamalıdır.

## 13. Verification / Smoke Planı

Gelecekte migration yazıldıktan sonra şu smoke kontrolleri planlanmalıdır:

- Seed locations var mı?
- `station_location_bindings` var mı?
- `ASSEMBLY_01` input/active_wip/output binding'leri doğru mu?
- `PACKAGING_01` input/active_wip/output_good/output_scrap binding'leri doğru mu?
- Operation start shadow mode'da movement candidate yaratıyor mu?
- Operation complete good movement yaratıyor mu?
- Operation complete scrap movement yaratıyor mu?
- Repeated complete duplicate movement yaratmıyor mu?
- Balance view doğru topluyor mu?
- Existing local successor smoke hâlâ geçiyor mu?
- MESQL push/pull çalışmadan local akış doğrulanabiliyor mu?

Bu smoke planı ileride test veya runbook'a dönüşebilir; bu turda test çalıştırılmaz.

## 14. Feature Flag Önerisi

İleride implementasyon için önerilen flag'ler:

- `MES_WEB_DB_INVENTORY_MOVEMENTS_ENABLED`
- `MES_WEB_DB_INVENTORY_MOVEMENTS_DRY_RUN`
- `MES_WEB_DB_SENSOR_EVENT_LINKS_ENABLED`
- `MES_WEB_DB_INVENTORY_BALANCE_READ_ENABLED`

Bu flag'ler bu turda eklenmeyecek, sadece planlanacaktır.

## 15. Açık Kararlar

Henüz karar verilecek konular:

- `inventory_balances` view mi tablo mu?
- Operation start gerçekten stok düşmeli mi, yoksa sadece WIP movement mı olmalı?
- `item_id` kaynağı work_order mı, operation mı, package mı?
- UOM standardı ne olacak?
- Sensor event hangi confidence eşiğiyle movement candidate sayılacak?
- Scrap movement quantity operation complete üzerinden mi alınacak?
- MESQL export mapping hangi fazda açılacak?
- `HOLD_AREA` ve `REWORK_AREA` ilk seed içinde aktif mi, opsiyonel mi kalacak?
- Package close hareketi final goods, shipment-prep veya package traceability seviyesinde mi modellenmeli?

## 16. Kabul Kriterleri

Bu plan tamam sayılmak için:

- Destructive değişiklik önermemeli.
- Additive tablo paketlerini tanımlamalı.
- Seed planı içermeli.
- Idempotency stratejisi içermeli.
- Operation lifecycle mapping içermeli.
- Sensor event mapping içermeli.
- Backfill, rollback ve verification planı içermeli.
- Feature flag önerisi içermeli.
- SQL migration, Python/API değişikliği, Docker değişikliği, DB bağlantısı, MESQL push/pull veya test çalıştırma içermemeli.

## 17. Sonraki Uygulanabilir İş

Draft additive SQL migration for locations and station_location_bindings only

