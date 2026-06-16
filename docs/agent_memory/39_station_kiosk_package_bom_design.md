# 39. Station-Based Kiosk and Package BOM Design

## 1. Amaç

Bu doküman, çalışan MESQL SQL MVP üzerine istasyon bazlı kiosk ve paket ürün/BOM mimarisini tasarlar.

Bu çalışma sadece tasarımdır:

- Kod değişikliği yapılmadı.
- Migration yazılmadı veya çalıştırılmadı.
- DB değişikliği yapılmadı.
- Runtime deploy yapılmadı.
- Commit/push yapılmadı.

Hedef davranış:

- `/kiosk/` açıldığında önce istasyon seçimi görünür.
- `ASSEMBLY_01` = `İstasyon 1 - Kutu Üretim`
- `PACKAGING_01` = `İstasyon 2 - Paketleme`
- Her istasyon aynı kiosk UI/component yapısını kullanır.
- Her istasyon sadece kendi iş emirlerini ve kendi aksiyonlarını görür.
- Paket ürünlerde iş emri miktarı bitmiş paket adedidir; paket içeriği BOM satırlarından gelir.

## 2. Mevcut Repo Bulguları

| Alan | Mevcut bulgu | Sonuç |
|---|---|---|
| Kiosk route | `mes_web/app.py` içinde `/kiosk/{device_id}` ve `/api/modules/{module_id}/kiosk/bootstrap` var. | Kiosk tek ekran olarak çalışıyor; station selector yok. |
| Kiosk UI | `mes_web/static/kiosk.html`, `kiosk.js`, `kiosk.css` aynı ekranı render ediyor. | Aynı component yapısı korunabilir. |
| Station state | `kiosk.js` localStorage içinde `station_id` saklıyor ve `currentActorPayload()` bunu gönderiyor. | Frontend tarafında station seçimi için başlangıç zemini var. |
| Station master | `mes_web/masterdata.py` Excel `0_Tanimlamalar` içinden stations okuyor. Default station hâlâ `KSK-01`. | `ASSEMBLY_01` / `PACKAGING_01` fallback ve masterdata tarafında netleşmeli. |
| DB station schema | `db/migrations/003_station_tracking_schema.sql` `mes.stations` seed ve `mes.item_station_events` tablosunu tanımlıyor. | Station event altyapısı hazır/planlanmış durumda. |
| Station writer | `mes_web/db/station_event_writer.py` `ASSEMBLY_01`, `PACKAGING_01`, `BUFFER_IN`, `PACKAGE_START`, `PACKAGE_FINISH` eventleri üretiyor. | İstasyon geçmişi için doğru temel var. |
| Work orders SQL | `mes.work_orders` current-state tablo; payload JSONB olarak runtime order shape saklanıyor. | Kısa vadede station/BOM alanları payload içinde taşınabilir. |
| Work order read | `mes_web/db/work_order_read.py` DB read overlay yapıyor ve runtime drift fallback koruyor. | Station filter, overlay sonrası projection katmanında uygulanmalı. |
| Package flow | `OeeRuntimeStateManager.start_package_flow()` tek buffer item rezerve ediyor. | Çoklu komponent BOM için yetersiz. |
| Package completion | `finish_package_flow()` tek source item tüketip bir package item üretiyor. | `PKG_BLUE_3` için 3 komponenti atomik tüketen yeni model gerekir. |
| FERP package source | `mes_web/ferp_import/ferp_work_orders.json` içinde `WO-PKT-BLUE-001` `lblMMFB0_QTY=3`. | Şu an mavi paket 3 ayrı paket çıktısı gibi davranmaya yatkın. |

## 3. Mevcut Tablolar Nasıl Kullanılmalı

### `mes.stations`

Station master olarak kullanılmalı.

Minimum seed:

| station_code | station_name | station_role |
|---|---|---|
| `ASSEMBLY_01` | `İstasyon 1 - Kutu Üretim` | `assembly` |
| `PACKAGING_01` | `İstasyon 2 - Paketleme` | `packaging` |

Not:

- `003_station_tracking_schema.sql` şu an `ASSEMBLY_01` için `İstasyon 1 - Montaj` adını kullanıyor.
- Yeni domain dili için display name `İstasyon 1 - Kutu Üretim` olmalı.
- `station_code` kalıcı domain key olmalı; `station_name` değişebilir.

### `mes.item_station_events`

Station geçmişi ve release kanıtı olarak kullanılmalı.

Kullanım:

- `ASSEMBLY_01 COMPLETE`: kutu üretimi tamamlandı.
- `ASSEMBLY_01 BUFFER_IN`: GOOD kutu paketleme bufferına girdi.
- `PACKAGING_01 PACKAGE_START`: paketleme oturumu başladı.
- `PACKAGING_01 PACKAGE_FINISH`: paket ürün çıktı.
- `PACKAGING_01 COMPLETE`: paket work order operasyonu tamamlandı.
- `QUALITY_LOCK`: paketleme için tüketilen komponent artık kalite override ile değişmemeli.

Bu tablo current-state değil, append/idempotent event log olmalı.

### `mes.work_orders`

Kısa vadede current-state olarak kalmalı.

Kullanım:

- `order_id`
- `status`
- `product_code`
- `target_quantity`
- `payload`
- `metadata`

Kısa vadede station ve operation bilgisi `payload` / `metadata` içinde taşınabilir:

```text
payload.station_code
payload.operation_code
payload.operation_sequence
payload.product_type
payload.bom_code
payload.planned_qty
payload.requirements[]
```

Ancak bu kalıcı normalize model yerine sadece geçiş kolaylığıdır.

### `mes.work_order_events`

Work order state transition log olarak kalmalı.

Kullanım:

- `started`
- `auto_completed`
- `completed`
- `rolled_back`
- `package_started`
- `package_finished`

Station-specific filtering için ana kaynak olmamalı. Bunun yerine `work_orders` current-state + station operation modeli kullanılmalı.

### `mes.production_completions`

Üretilen fiziksel/logical çıktı sonucu olarak kalmalı.

Kullanım:

- `BOX_RED`, `BOX_BLUE`, `BOX_YELLOW` gibi komponent kutu completionları.
- `PKG_BLUE_3`, `PKG_RED_YELLOW` gibi paket ürün completionları.

Station hareketleri bu tabloya gömülmemeli. Bir completion birden fazla station event ile ilişkilenebilir.

## 4. Minimum SQL Model Önerisi

Mevcut tablolar yeterli değildir. Station bazlı kiosk ve doğru paket BOM için minimum yeni model gerekir.

### 4.1 Item Master

Önerilen tablo:

```text
mes.item_master
```

Amaç:

- Ürün/yarı mamul/komponent ayrımını netleştirmek.

Minimum alanlar:

| Alan | Anlam |
|---|---|
| `item_code` | Kalıcı stok/ürün kodu |
| `item_name` | Görünen ad |
| `item_type` | `component`, `semi_finished`, `finished_good`, `package` |
| `color_code` | `red`, `blue`, `yellow`, `mixed` |
| `uom` | `ADET` |
| `active` | Kullanımda mı |
| `payload` | Kaynak sistem alanları |
| `metadata` | migration/import bilgisi |

Örnek kayıtlar:

| item_code | item_type | color_code |
|---|---|---|
| `RED_BOX` | `semi_finished` | `red` |
| `BLUE_BOX` | `semi_finished` | `blue` |
| `YELLOW_BOX` | `semi_finished` | `yellow` |
| `PKG_BLUE_3` | `package` | `blue` |
| `PKG_RED_YELLOW` | `package` | `mixed` |

### 4.2 Station Routes / Operation Sequence

Önerilen tablo:

```text
mes.item_station_routes
```

Amaç:

- Hangi ürün hangi istasyonda hangi operasyonla üretilir?

Minimum alanlar:

| Alan | Anlam |
|---|---|
| `route_code` | Route domain key |
| `item_code` | Üretilen item |
| `operation_sequence` | Sıra |
| `station_code` | İstasyon |
| `operation_code` | `BOX_PRODUCTION`, `PACKAGING` |
| `input_policy` | `sensor`, `bom_component_buffer`, `manual` |
| `output_policy` | `component_buffer`, `finished_package`, `scrap_rework` |
| `active` | Kullanımda mı |

Örnek:

| item_code | station_code | operation_code |
|---|---|---|
| `RED_BOX` | `ASSEMBLY_01` | `BOX_PRODUCTION` |
| `BLUE_BOX` | `ASSEMBLY_01` | `BOX_PRODUCTION` |
| `YELLOW_BOX` | `ASSEMBLY_01` | `BOX_PRODUCTION` |
| `PKG_BLUE_3` | `PACKAGING_01` | `PACKAGING` |
| `PKG_RED_YELLOW` | `PACKAGING_01` | `PACKAGING` |

### 4.3 Package BOM

Önerilen tablolar:

```text
mes.bom_headers
mes.bom_lines
```

Amaç:

- Paket ürünün kaç adet hangi komponentten tükettiğini modellemek.

Minimum `bom_headers`:

| Alan | Anlam |
|---|---|
| `bom_code` | `BOM_PKG_BLUE_3` |
| `parent_item_code` | Paket ürün |
| `revision` | MVP için `A` |
| `active` | Kullanımda mı |

Minimum `bom_lines`:

| Alan | Anlam |
|---|---|
| `bom_code` | Header ilişkisi |
| `line_no` | Sıra |
| `component_item_code` | Tüketilecek komponent |
| `component_qty` | 1 paket için gereken miktar |
| `uom` | `ADET` |

Örnek BOM:

| parent_item_code | component_item_code | component_qty |
|---|---|---:|
| `PKG_BLUE_3` | `BLUE_BOX` | 3 |
| `PKG_RED_YELLOW` | `RED_BOX` | 1 |
| `PKG_RED_YELLOW` | `YELLOW_BOX` | 1 |

### 4.4 Station-Specific Work Order Operations

Önerilen tablo:

```text
mes.work_order_operations
```

Amaç:

- Bir iş emrinin istasyon bazlı görünürlüğünü ve durumunu ayırmak.
- Paket orderını tek current-state row olarak tutarken, operasyon seviyesinde station filtreleme yapmak.

Minimum alanlar:

| Alan | Anlam |
|---|---|
| `work_order_id` | `mes.work_orders.order_id` |
| `operation_id` | Domain key, örn. `WO-PKT-BLUE-001:PACKAGING_01` |
| `station_code` | Görüneceği kiosk |
| `operation_code` | `BOX_PRODUCTION` / `PACKAGING` |
| `sequence_no` | Operasyon sırası |
| `status` | `blocked`, `queued`, `active`, `pending_approval`, `completed` |
| `planned_qty` | Bu operasyonun üreteceği çıktı adedi |
| `completed_qty` | Üretilen çıktı adedi |
| `released_at` | İstasyona görünür olduğu zaman |
| `blocked_reason` | BOM/buffer eksikliği gibi sebep |
| `payload` | Runtime uyumluluk |
| `metadata` | Kaynak/import bilgisi |

MVP için tek operasyonlu yapı yeterli:

- Kutu iş emirleri: `ASSEMBLY_01`
- Paket iş emirleri: `PACKAGING_01`

Ama bu tablo gelecekte çok operasyonlu route için kapı açar.

### 4.5 Buffer / Available Component Quantity Modeli

Önerilen current-state tablo:

```text
mes.station_component_inventory
```

veya daha event-sourced yaklaşım:

```text
mes.component_buffer_items
```

MVP için item bazlı buffer daha güvenlidir:

| Alan | Anlam |
|---|---|
| `buffer_item_id` | Runtime item id |
| `component_item_code` | `BLUE_BOX`, `RED_BOX`, `YELLOW_BOX` |
| `source_work_order_id` | Üreten assembly iş emri |
| `source_completion_ref` | `production_completions.external_ref` veya runtime ref |
| `quality_status` | `GOOD`, `REWORK`, `SCRAP` |
| `status` | `available`, `reserved`, `consumed`, `quality_locked` |
| `reserved_by_order_id` | Paket iş emri |
| `reserved_by_session_id` | Paketleme oturumu |
| `completed_at` | Komponent üretim zamanı |
| `consumed_at` | Paket tüketim zamanı |

Neden miktar tablosu tek başına yetmez:

- Quality lock ve traceability için hangi 3 mavi kutunun hangi pakete girdiği bilinmeli.
- Paket finish idempotency için session/component item listesi saklanmalı.

## 5. Migration Gerekecek mi?

Evet, tam ve temiz model için migration gerekir.

Mevcut migrationlar şunları karşılıyor:

- `mes.stations`
- `mes.item_station_events`
- `mes.work_orders`
- `mes.work_order_events`
- `mes.production_completions`

Eksik olanlar:

- `mes.item_master`
- `mes.item_station_routes`
- `mes.bom_headers`
- `mes.bom_lines`
- `mes.work_order_operations`
- `mes.component_buffer_items` veya eşdeğer buffer current-state tablosu
- opsiyonel: `mes.package_sessions`
- opsiyonel: `mes.package_session_components`

Migration yazımı bu dokümanda yapılmadı. İlk sprintte migration yazılacaksa ayrı onay ve ayrı güvenli DB backup akışı gerekir.

## 6. `/kiosk/` Station Selection Route/UI Planı

Önerilen davranış:

1. `/kiosk/` açılır.
2. Kullanıcı station selection ekranını görür.
3. İki kart listelenir:
   - `İstasyon 1 - Kutu Üretim`
   - `İstasyon 2 - Paketleme`
4. Seçim localStorage içine kaydedilir.
5. Kullanıcı station kiosk ekranına yönlenir.

Önerilen path:

```text
/kiosk/
/kiosk/ASSEMBLY_01
/kiosk/PACKAGING_01
```

Alternatif query param:

```text
/kiosk/?station_code=ASSEMBLY_01
```

Karar:

- Ana yaklaşım path olmalı: `/kiosk/{station_code}`.
- Query param sadece backwards-compatible fallback olabilir.

Neden path daha iyi:

- Fiziksel tablet bookmark için nettir.
- Station identity URL'de görünür.
- Aynı UI bundle farklı station context ile açılır.
- `device_id` ile station ayrıştırması karışmaz.

Mevcut `/kiosk/{device_id}` davranışıyla çakışma riski:

- Bugün path param `device_id` gibi kullanılıyor.
- Yeni route tasarımında `station_code` ve `device_id` ayrılmalı.

Önerilen uyumluluk:

```text
/kiosk/                          -> station selector
/kiosk/station/{station_code}     -> station kiosk
/kiosk/device/{device_id}         -> legacy/backward-compatible device kiosk
```

Bu, mevcut `/kiosk/{device_id}` çakışmasını en az riskle çözer.

## 7. Station-Specific Work Order Filtering

Filtering backend snapshot katmanında yapılmalı.

Mevcut yer:

- `mes_web/app.py::_build_kiosk_snapshot()`
- `ordered_orders`
- `queue_orders`
- `active_order`
- `packaging_state`
- `_kiosk_big_action()`

Önerilen yeni input:

```text
station_code = URL path veya query param
```

Filtering mantığı:

```text
ASSEMBLY_01:
  show work orders where operation station_code == ASSEMBLY_01
  or product item route station_code == ASSEMBLY_01
  or legacy fallback product_code in RED/BLUE/YELLOW box family

PACKAGING_01:
  show work orders where operation station_code == PACKAGING_01
  or product item type == package
  or legacy fallback order is package order
```

Active order seçimi de station scoped olmalı:

- Global `activeOrderId` tek başına yeterli değil.
- Aynı anda iki istasyonda iki farklı aktif operasyon isteniyorsa `workOrders.activeOrderId` modeli yetersiz kalır.
- MVP'de aynı anda tek aktif iş emri korunacaksa station filter sadece görünürlük sağlar.
- Hedef mimaride `work_order_operations.status` station bazlı aktifliği taşımalı.

MVP karar:

- Faz 1 için tek global active korunabilir.
- Station ekranı, kendi stationına ait olmayan active orderı göstermemeli.
- Başlatma endpoint'i station_code almalı ve sadece o stationın queue listesinden seçim yapmalı.
- Paketleme stationı assembly active order yüzünden kilitlenmemeli hedefleniyorsa Faz 2'de operation-level active state gerekir.

## 8. Station 1 Completion Sonrası Station 2 Release

İstenen kural:

```text
İstasyon 1 tamamlanmadan hiçbir şey İstasyon 2'ye düşmemeli.
```

Doğru release koşulu:

Bir komponent `PACKAGING_01` bufferına ancak şu koşullarla düşer:

1. `ASSEMBLY_01` iş emrinde bir item tamamlanmış olmalı.
2. Item classification `GOOD` olmalı.
3. İş emri veya item onay süreci ürün politikası gerektiriyorsa onay tamamlanmış olmalı.
4. Item daha önce paketleme için reserve/consume edilmemiş olmalı.
5. `mes.item_station_events` içinde `BUFFER_IN` veya runtime buffer row idempotent şekilde oluşmalı.

Mevcut kodda:

- GOOD completion sonrası packaging buffer runtime state içinde oluşuyor.
- `station_event_writer.py` `BUFFER_IN` üretebiliyor.
- Package flow `PACKAGING_01` içinde buffer item tüketiyor.

Tasarım değişikliği:

- Station 2 work orderları sadece order listesi olarak görünmemeli.
- Her package order için BOM availability hesaplanmalı.
- Availability sağlanmadan action disabled olmalı.

Örnek:

```text
PKG_BLUE_3 visible in PACKAGING_01:
  planned_qty = 1 package
  requires BLUE_BOX x3
  available BLUE_BOX GOOD count >= 3 ise start enabled
  aksi halde visible olabilir ama "Komponent bekliyor" durumunda olmalı
```

## 9. Paket Ürün Quantity Semantics

Bu bölüm kritik karardır.

Yanlış model:

```text
PKT-BLUE qty = 3
```

Bu model sistem tarafından 3 paket çıktısı olarak yorumlanır.

Doğru model:

```text
Work order:
  product_code = PKG_BLUE_3
  planned_qty = 1

BOM:
  BLUE_BOX x3

Completion:
  3 adet BLUE_BOX tüketilir
  1 adet PKG_BLUE_3 üretilir
```

Benzer:

```text
Work order:
  product_code = PKG_RED_YELLOW
  planned_qty = 1

BOM:
  RED_BOX x1
  YELLOW_BOX x1
```

Kural:

- `work_orders.target_quantity` / `planned_qty`: bitmiş ürün adedi.
- `bom_lines.component_qty`: bir bitmiş ürün için gereken komponent adedi.
- `completed_qty`: üretilen bitmiş ürün adedi.
- `component_consumed_qty`: BOM tüketiminden hesaplanır; work order target ile karıştırılmaz.

UI gösterimi:

```text
PKG_BLUE_3
Plan: 1 paket
BOM: Mavi Kutu 3/3
```

`content_counts` artık paket order için hedef ürünün planned quantity'si değil, BOM availability/progress olarak gösterilmeli.

## 10. Package Flow İçin Gerekli Runtime Davranış Değişikliği

Mevcut `start_package_flow()` tek buffer item seçiyor.

Yeni davranış:

1. Package order BOM bulunur.
2. Her BOM line için yeterli `available` component item aranır.
3. Tüm komponentler atomik olarak `reserved` yapılır.
4. Session içine component listesi yazılır.
5. Finish sırasında tüm reserved componentler `consumed` olur.
6. Tek package item üretilir.
7. `production_completions` içine tek package completion yazılır.
8. `item_station_events` içine her komponent için `BUFFER_OUT`/`QUALITY_LOCK`, paket için `PACKAGE_FINISH`/`COMPLETE`/`EXIT` yazılır.

Önerilen session shape:

```json
{
  "session_id": "...",
  "package_order_id": "WO-PKG-BLUE-001",
  "package_item_code": "PKG_BLUE_3",
  "status": "reserved",
  "components": [
    {"component_item_code": "BLUE_BOX", "buffer_item_id": "42"},
    {"component_item_code": "BLUE_BOX", "buffer_item_id": "43"},
    {"component_item_code": "BLUE_BOX", "buffer_item_id": "44"}
  ]
}
```

## 11. API Tasarım Planı

Station selector:

```text
GET /kiosk/
GET /api/modules/{module_id}/kiosk/stations
GET /kiosk/station/{station_code}
```

Station bootstrap:

```text
GET /api/modules/{module_id}/kiosk/bootstrap?station_code=ASSEMBLY_01&device_id=...
```

veya:

```text
GET /api/modules/{module_id}/kiosk/stations/{station_code}/bootstrap?device_id=...
```

Station-scoped actions:

```text
POST /api/modules/{module_id}/kiosk/stations/{station_code}/work-orders/start
POST /api/modules/{module_id}/kiosk/stations/{station_code}/work-orders/accept-active
POST /api/modules/{module_id}/kiosk/stations/{station_code}/package/start
POST /api/modules/{module_id}/kiosk/stations/{station_code}/package/finish
```

Backward compatibility:

- Existing endpoints can continue for dashboard/global flows.
- New station endpoints should call the same service layer with explicit `station_code`.

## 12. Feature Flags

Önerilen yeni flagler:

| Flag | Varsayılan | Amaç |
|---|---:|---|
| `MES_WEB_KIOSK_STATION_ROUTING` | `false` | `/kiosk/` station selector ve station scoped bootstrap |
| `MES_WEB_KIOSK_STATION_FILTER_WORK_ORDERS` | `false` | Kiosk work order listesini stationa göre filtrele |
| `MES_WEB_PACKAGE_BOM_MODE` | `false` | Paket flowda BOM/component tüketimi kullan |
| `MES_WEB_DB_READ_BOM` | `false` | BOM masterı DB'den oku |
| `MES_WEB_DB_READ_WORK_ORDER_OPERATIONS` | `false` | Operation current-state DB read |

Fail-open:

- Station filter hata verirse mevcut global kiosk snapshot'a fallback yapılabilir, ama UI'da warning metadata olmalı.
- BOM read hata verirse package action disabled olmalı; tek item legacy fallback sadece flag kapalıyken kullanılmalı.

## 13. En Küçük Uygulanabilir Sprint Planı

### Faz 1 - Station Selector ve Runtime Filter

Amaç:

- `/kiosk/` station selector açılır.
- `/kiosk/station/ASSEMBLY_01` ve `/kiosk/station/PACKAGING_01` aynı kiosk UI'ı açar.
- Backend bootstrap station_code alır.
- Work order listesi stationa göre filtrelenir.

Schema:

- Yeni migration gerekmeden yapılabilir.
- Station mapping runtime payload/masterdata fallback ile başlatılabilir.

Değişecek dosyalar:

- `mes_web/app.py`
- `mes_web/static/kiosk.html`
- `mes_web/static/kiosk.js`
- `mes_web/static/kiosk.css`
- `mes_web/masterdata.py`
- `tests/test_mes_web_kiosk_app.py`

Başarı kriteri:

- `ASSEMBLY_01` kiosk kırmızı/sarı/mavi kutu iş emirlerini görür.
- `PACKAGING_01` kiosk paket iş emirlerini görür.
- İki station aynı UI componentlerini kullanır.
- Smoke PASS kalır.

### Faz 2 - Package BOM Semantics Tasarımı ve Source Normalization

Amaç:

- `PKG_BLUE_3 planned_qty=1`, `BLUE_BOX x3`.
- `PKG_RED_YELLOW planned_qty=1`, `RED_BOX x1 + YELLOW_BOX x1`.

Schema:

- Tercihen migration gerekir:
  - `item_master`
  - `bom_headers`
  - `bom_lines`
- Kısa vadeli demo için JSON/FERP payload içinde `bom` alanı taşınabilir, ama kalıcı model olmamalı.

Değişecek dosyalar:

- `mes_web/ferp_import/ferp_work_orders.json`
- `mes_web/oee_state.py`
- `mes_web/app.py`
- `mes_web/static/kiosk.js`
- `tests/test_mes_web_oee_state.py`
- `tests/test_mes_web_kiosk_app.py`

Başarı kriteri:

- Mavi paket UI'da `1 paket`, `Mavi Kutu 0/3` olarak görünür.
- 3 GOOD mavi kutu yoksa package start disabled.
- 3 GOOD mavi kutu varsa tek package session başlar.

### Faz 3 - Multi-Component Package Runtime

Amaç:

- `start_package_flow()` tek buffer item yerine BOM component listesi reserve eder.
- `finish_package_flow()` tüm componentleri consume edip tek package item üretir.

Schema:

- `component_buffer_items`, `package_sessions`, `package_session_components` önerilir.
- Runtime JSON fallback korunmalı.

Değişecek dosyalar:

- `mes_web/oee_state.py`
- `mes_web/db/station_event_writer.py`
- `mes_web/db/production_completion_writer.py` gerekirse payload projection
- `tests/test_mes_web_oee_state.py`
- `tests/test_mes_web_station_events.py`
- `tests/test_mes_web_production_completion_writer.py`

Başarı kriteri:

- `PKG_BLUE_3` için 3 component consumed, 1 package completion.
- `production_completions` duplicate yok.
- `item_station_events` duplicate yok.

### Faz 4 - SQL Operation/BOM Read Cutover

Amaç:

- Station work order listeleri DB operation/BOM modelinden okunur.
- Runtime JSON fallback devam eder.

Schema:

- `work_order_operations`
- `item_master`
- `bom_headers`
- `bom_lines`
- buffer/session tabloları uygulanmış olmalı.

Değişecek dosyalar:

- `mes_web/db/` altında yeni read adapters
- `mes_web/app.py`
- `mes_web/store.py`
- `mes_web/oee_state.py`
- `tests/test_mes_web_*`

Başarı kriteri:

- `MES_WEB_DB_READ_WORK_ORDER_OPERATIONS=true` ile station listesi DB'den gelir.
- DB hata/boşsa runtime fallback.
- Smoke PASS.

## 14. Riskler

- Mevcut `workOrders.activeOrderId` globaldir. Aynı anda iki stationda aktif operasyon istenirse bu model yetersiz kalır.
- Package flow şu an tek komponent tüketir; BOM'a geçerken idempotency ve partial reservation riski vardır.
- `WO-PKT-BLUE-001` gibi mevcut test data `qty=3` içerdiği için önce source normalization yapılmazsa UI davranışı yine yanlış anlaşılır.
- Station selector route, mevcut `/kiosk/{device_id}` route ile çakışabilir.
- Excel masterdata default station hâlâ `KSK-01`; fallback düzeltilmezse station seçiminde yanlış default gelebilir.
- FERP import/export alanlarına erken müdahale canlı demo akışını bozabilir.
- `production_completions` result, `item_station_events` process history ayrımı korunmazsa raporlama tutarsızlaşır.

## 15. Test Senaryoları

Station selector:

1. `/kiosk/` açılır.
2. `ASSEMBLY_01` ve `PACKAGING_01` listelenir.
3. `ASSEMBLY_01` seçilince station kiosk açılır.
4. `PACKAGING_01` seçilince aynı UI farklı station context ile açılır.

Station filter:

1. Assembly kiosk kırmızı/sarı/mavi kutu iş emirlerini görür.
2. Assembly kiosk paket iş emirlerini görmez.
3. Packaging kiosk paket iş emirlerini görür.
4. Packaging kiosk kutu üretim iş emirlerini görmez.

Release:

1. Assembly'de BLUE_BOX GOOD tamamlanmadan packaging availability `0`.
2. Assembly'de BLUE_BOX GOOD tamamlanınca buffer count artar.
3. BLUE_BOX x3 olmadan `PKG_BLUE_3` start disabled.
4. BLUE_BOX x3 olduğunda `PKG_BLUE_3` start enabled.

Package BOM:

1. `PKG_BLUE_3 planned_qty=1`.
2. BOM `BLUE_BOX x3`.
3. Start 3 component reserve eder.
4. Finish 3 component consume eder.
5. Tek `PKG_BLUE_3` package completion oluşur.
6. `production_completions` duplicate external_ref = 0.
7. `item_station_events` duplicate source/external_ref = 0.

Regression:

1. Dashboard global work order görünümü bozulmaz.
2. Existing `/api/modules/{module_id}/kiosk/bootstrap` fallback çalışır.
3. Smoke check PASS kalır.
4. Station events hook davranışı bozulmaz.
5. Production completion hook davranışı bozulmaz.

## 16. Hangi Dosyalar Değişir

Faz 1 beklenen dosyalar:

- `mes_web/app.py`
- `mes_web/masterdata.py`
- `mes_web/static/kiosk.html`
- `mes_web/static/kiosk.js`
- `mes_web/static/kiosk.css`
- `tests/test_mes_web_kiosk_app.py`

Faz 2 ve sonrası beklenen dosyalar:

- `mes_web/oee_state.py`
- `mes_web/ferp_import/ferp_work_orders.json`
- `mes_web/db/station_event_writer.py`
- `mes_web/db/work_order_read.py`
- `mes_web/db/work_order_mirror.py`
- `tests/test_mes_web_oee_state.py`
- `tests/test_mes_web_station_events.py`
- `tests/test_mes_web_work_order_read.py`
- `tests/test_mes_web_work_order_mirror.py`
- `db/migrations/*` yeni migration dosyaları

## 17. Önerilen Faz 1 Implementation

Önerilen ilk uygulama yalnızca station selector + station filter olmalı.

Kapsam:

- `/kiosk/` station selection ekranı.
- `/kiosk/station/{station_code}` route.
- Bootstrap response içine `station_context`.
- `ASSEMBLY_01` ve `PACKAGING_01` fallback station master.
- Kiosk work order projection filter:
  - Assembly: kutu üretim emirleri.
  - Packaging: package emirleri.
- Package BOM runtime değişikliği yok.
- Migration yok.
- DB write yok.

Bu faz, kullanıcı deneyimini doğru istasyon ayrımına taşır ama paket BOM tüketim problemini yalnızca görünürlük açısından hazırlar.

## 18. Riskler

- Faz 1 package BOM problemini tamamen çözmez; sadece station ayrımını düzeltir.
- Global `activeOrderId` nedeniyle aynı anda iki station aktif iş emri hedefi Faz 1'de desteklenmez.
- Legacy `/kiosk/{device_id}` route korunurken route çakışması dikkatli tasarlanmalı.
- Station filter yanlış sınıflandırılırsa iş emri yanlış kioskta gizlenebilir.

## 19. Test Senaryoları

- `/kiosk/` station selection render eder.
- `/kiosk/station/ASSEMBLY_01` HTTP 200.
- `/kiosk/station/PACKAGING_01` HTTP 200.
- Bootstrap `station_context.station_code=ASSEMBLY_01` döner.
- Assembly queue içinde `BOX-RED`, `BOX-YEL`, `BOX-BLUE` görünür.
- Assembly queue içinde `PKT-*` görünmez.
- Packaging queue içinde `PKT-*` görünür.
- Packaging queue içinde `BOX-*` görünmez.
- Existing kiosk action endpointleri station_code ile çalışır veya fallback bozulmaz.
- Smoke check PASS kalır.

## 20. Hangi Dosyaların Değişeceği

Faz 1 için beklenen dosya değişiklikleri:

- `mes_web/app.py`
- `mes_web/masterdata.py`
- `mes_web/static/kiosk.html`
- `mes_web/static/kiosk.js`
- `mes_web/static/kiosk.css`
- `tests/test_mes_web_kiosk_app.py`

Faz 1'de özellikle değişmemesi gerekenler:

- `db/migrations/*`
- Runtime `.env`
- Docker compose dosyaları
- MQTT/observer/simulator akışı
- `mes_web/db/production_completion_writer.py`
- `mes_web/db/station_event_writer.py`

