# Station Execution Config Read Model Design

## 1. Amaç

Bu doküman, SQL-driven station execution minimal seed verisinin backend
tarafında read-only okunması için önerilen helper katmanını tasarlar.

`004_station_execution_schema.sql` uygulanmış ve
`005_station_execution_seed_minimal.sql` ile minimal master/config seed PASS
şekilde DB'ye işlenmiştir. Bu doküman runtime engine, Kiosk dynamic action,
IoT adapter, OEE/KPI veya inventory movement implementation değildir.

Hedef, runtime mutation yazmadan önce backend'in şu soruları güvenli şekilde
cevaplayabilmesini sağlamaktır:

- Bu istasyonda hangi route operation çalışabilir?
- Bu operation'ın input/output item'ı nedir?
- Bu operation'ın input/output/scrap location role'leri nedir?
- Bu operation hangi completion policy ile çalışır?
- Bu operation'ın step sırası nedir?
- Her step nasıl başlar/biter?
- Hangi step sensor/robot/kiosk kaynaklıdır?
- Bu station için tanımlı event source'lar nelerdir?
- Bir station + source_code geçerli mi?
- Route operation + step_code geçerli mi?

## 2. Baseline

Mevcut doğrulanmış durum:

- Station execution schema migration applied: PASS.
- Minimal station execution seed applied: PASS.
- Seed kapsamı yalnızca master/config tablolarıdır.
- Runtime/event/flow tabloları boş kalmıştır.
- Station/location baseline korunmuştur: `locations = 8`,
  `active_station_location_bindings = 8`.
- Mevcut station/location read-only helper pattern'i `mes_web/db/mesql_v2.py`
  içinde parametrik SQL ve explicit cast yaklaşımıyla çalışır.
- Mevcut unit testler fake connection/cursor pattern'iyle DB gerektirmeden
  çalışır.

Bu tasarım aynı read-only yaklaşımı station execution config tabloları için
genişletir.

## 3. Kapsam

Bu faz sadece read-only helper seviyesindedir.

Kapsamdaki tablolar:

```text
mes.items
mes.process_routes
mes.route_operations
mes.station_event_sources
mes.operation_steps
```

Kapsamdaki seed örnekleri:

```text
items:
  RAW_BOX
  COLOR_CLASSIFIED_BOX
  PACKAGED_PRODUCT

route:
  ROUTE_BOX_PACKAGING_V1 version 1

route_operations:
  ROUTE_BOX_PACKAGING_V1_OP10 / ASSEMBLY_01
  ROUTE_BOX_PACKAGING_V1_OP20 / PACKAGING_01

event_sources:
  ASSEMBLY_01 / COLOR_SENSOR_ENTRY
  ASSEMBLY_01 / ROBOT_ARM_DROP
  ASSEMBLY_01 / KIOSK_OPERATOR
  PACKAGING_01 / KIOSK_OPERATOR

operation_steps:
  3 assembly/classification steps
  2 packaging steps
```

## 4. Kapsam Dışı

Bu tasarım şu tabloları okumaz veya değiştirmez:

```text
mes.work_order_operation_execution_state
mes.work_order_operation_steps
mes.operation_events
mes.operation_approvals
mes.production_flow_events
mes.work_orders
mes.work_order_operations
mes.station_queue
```

Bu fazda yapılmayacaklar:

- Runtime/event/flow üretimi.
- Operation start/complete lifecycle mutation.
- Kiosk action POST.
- Kiosk dynamic action implementation.
- Runtime engine implementation.
- IoT/MQTT adapter implementation.
- OEE/KPI implementation.
- Inventory movement/balance implementation.
- MESQL push/pull.
- DB migration veya seed apply.

## 5. Domain Modeli

### Item

`mes.items`, station execution sırasında kullanılan input/output item master
datasını tutar.

Minimum read fields:

```text
item_code
item_name
item_type
unit
active
metadata
```

Normalize:

- `item_code`: uppercase.
- `item_type`: lowercase.
- `unit`: kaynak değeri korunur; seed için `piece`.

### Process Route

`mes.process_routes`, üretilecek item için versioned route bilgisini tutar.

Minimum read fields:

```text
route_code
version
route_name
item_code
active
metadata
```

Normalize:

- `route_code`: uppercase.
- `item_code`: uppercase.

### Route Operation

`mes.route_operations`, route içindeki station operation tanımını ve
input/output dönüşümünü tutar.

Minimum read fields:

```text
route_operation_id
route_code
route_version
sequence_no
operation_code
operation_name
station_code
input_item_code
output_item_code
input_qty_per_cycle
output_qty_per_cycle
input_location_role
output_location_role
scrap_location_role
operation_completion_policy
planned_cycle_time_sec
active
metadata
```

Normalize:

- `route_operation_id`: uppercase.
- `route_code`: uppercase.
- `operation_code`: uppercase.
- `station_code`: uppercase.
- `input_item_code`: uppercase.
- `output_item_code`: uppercase.
- location role ve policy alanları lowercase kalır.

### Station Event Source

`mes.station_event_sources`, station-scoped sensor/robot/kiosk/observer/PLC
event kaynaklarını tutar.

Minimum read fields:

```text
station_code
source_code
source_name
source_type
event_channel
mqtt_topic
active
metadata
```

Normalize:

- `station_code`: uppercase.
- `source_code`: uppercase.
- `source_type`: lowercase.
- `event_channel`: lowercase.

### Operation Step

`mes.operation_steps`, route operation altındaki step master config bilgisini
tutar.

Minimum read fields:

```text
route_operation_id
operation_code
step_no
step_code
step_name
start_mode
finish_mode
start_event_source_code
finish_event_source_code
required_for_completion
records_duration
approval_required_after_finish
actor_type
active
metadata
```

Normalize:

- `route_operation_id`: uppercase.
- `operation_code`: uppercase.
- `step_code`: uppercase.
- `start_event_source_code`: nullable uppercase.
- `finish_event_source_code`: nullable uppercase.
- `start_mode`, `finish_mode`, `actor_type`: lowercase.

## 6. Önerilen Helper Fonksiyonları

İlk implementation fazında helper'lar `mes_web/db/mesql_v2.py` içinde mevcut
station/location read-only helper stiline yakın yazılabilir.

Önerilen fonksiyonlar:

```text
list_items(config, active_only=True)
get_item_by_code(config, item_code)

list_process_routes(config, active_only=True, item_code=None)
get_process_route(config, route_code, version=1)

list_route_operations(config, route_code=None, station_code=None, active_only=True)
get_route_operation(config, route_operation_id)

list_station_event_sources(config, station_code, active_only=True)
resolve_station_event_source(config, station_code, source_code)

list_operation_steps(config, route_operation_id, active_only=True)
get_operation_step(config, route_operation_id, step_code)

get_route_operation_config(config, route_operation_id)
get_station_execution_config(config, station_code)
```

### `list_items(config, active_only=True)`

Read-only item listesi döner.

Minimum response:

```text
item_code
item_name
item_type
unit
active
metadata
```

Order:

```text
item_type ASC, item_code ASC
```

### `get_item_by_code(config, item_code)`

`item_code` normalize edilip tek item döner. Kayıt yoksa `None` döner.

### `list_process_routes(config, active_only=True, item_code=None)`

Route listesini döner. `item_code` verilirse ilgili output/product item route'u
filtrelenir.

Order:

```text
route_code ASC, version ASC
```

### `get_process_route(config, route_code, version=1)`

`route_code` ve `version` ile tek route döner. Kayıt yoksa `None` döner.

### `list_route_operations(config, route_code=None, station_code=None, active_only=True)`

Route operation listesini döner. `route_code` ve `station_code` opsiyonel
filtrelerdir.

Order:

```text
route_code ASC, route_version ASC, sequence_no ASC
```

### `get_route_operation(config, route_operation_id)`

`route_operation_id` ile tek route operation döner. Kayıt yoksa `None` döner.

### `list_station_event_sources(config, station_code, active_only=True)`

Station'a tanımlı event source listesini döner.

Order:

```text
source_type ASC, source_code ASC
```

### `resolve_station_event_source(config, station_code, source_code)`

Station-scoped source lookup yapar. `station_code + source_code` aktif ve
tanımlıysa source row döner; değilse `None` döner.

### `list_operation_steps(config, route_operation_id, active_only=True)`

Route operation altındaki step listesini döner.

Order:

```text
step_no ASC
```

### `get_operation_step(config, route_operation_id, step_code)`

Route-operation-scoped step lookup yapar. Kayıt yoksa `None` döner.

### `get_route_operation_config(config, route_operation_id)`

Bir route operation için item, step ve event source context'ini tek aggregate
olarak döner. Runtime state okumaz.

### `get_station_execution_config(config, station_code)`

Bir station için active route operations, event sources ve her operation'ın
aggregate config bilgisini döner. Runtime state okumaz.

## 7. Response Shape Tasarımı

### Item Row

```json
{
  "item_code": "RAW_BOX",
  "item_name": "Raw Box",
  "item_type": "raw_material",
  "unit": "piece",
  "active": true,
  "metadata": {}
}
```

### Process Route Row

```json
{
  "route_code": "ROUTE_BOX_PACKAGING_V1",
  "version": 1,
  "route_name": "Box Packaging Demo Route V1",
  "item_code": "PACKAGED_PRODUCT",
  "active": true,
  "metadata": {}
}
```

### Route Operation Row

```json
{
  "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
  "route_code": "ROUTE_BOX_PACKAGING_V1",
  "route_version": 1,
  "sequence_no": 10,
  "operation_code": "OP10_ASSEMBLY_CLASSIFICATION",
  "operation_name": "Assembly / Classification",
  "station_code": "ASSEMBLY_01",
  "input_item_code": "RAW_BOX",
  "output_item_code": "COLOR_CLASSIFIED_BOX",
  "input_qty_per_cycle": "1.000000",
  "output_qty_per_cycle": "1.000000",
  "input_location_role": "input",
  "output_location_role": "output_buffer",
  "scrap_location_role": "output_scrap",
  "operation_completion_policy": "auto_complete_pending_approval",
  "planned_cycle_time_sec": null,
  "active": true,
  "metadata": {}
}
```

### Station Event Source Row

```json
{
  "station_code": "ASSEMBLY_01",
  "source_code": "COLOR_SENSOR_ENTRY",
  "source_name": "Color Sensor Entry",
  "source_type": "sensor",
  "event_channel": "mqtt",
  "mqtt_topic": "mes/stations/ASSEMBLY_01/sources/COLOR_SENSOR_ENTRY/events",
  "active": true,
  "metadata": {}
}
```

### Operation Step Row

```json
{
  "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
  "operation_code": "OP10_ASSEMBLY_CLASSIFICATION",
  "step_no": 10,
  "step_code": "COLOR_SENSOR_ENTRY_EVIDENCE",
  "step_name": "Color Sensor Entry Evidence",
  "start_mode": "auto_start",
  "finish_mode": "auto_finish",
  "start_event_source_code": "COLOR_SENSOR_ENTRY",
  "finish_event_source_code": "COLOR_SENSOR_ENTRY",
  "required_for_completion": true,
  "records_duration": false,
  "approval_required_after_finish": false,
  "actor_type": "sensor",
  "active": true,
  "metadata": {}
}
```

## 8. Aggregate Response Tasarımı

### Route Operation Config Aggregate

`get_route_operation_config(config, route_operation_id)` şu shape'i döner:

```json
{
  "route_operation": {},
  "input_item": {},
  "output_item": {},
  "steps": [],
  "event_sources": [],
  "validation": {
    "missing_event_sources": [],
    "invalid_step_source_refs": []
  }
}
```

Kurallar:

- `route_operation` yoksa aggregate `None` dönebilir.
- `input_item` veya `output_item` bulunamazsa `validation` içine warning
  eklenir.
- `event_sources`, route operation'ın station'ı için active event source
  listesidir.
- `steps`, `step_no ASC` sıralıdır.
- Bu aggregate runtime state veya work order bilgisi içermez.

Önerilen validation alanları:

```json
{
  "missing_items": [],
  "missing_station": [],
  "missing_event_sources": [],
  "invalid_step_source_refs": [],
  "invalid_auto_mode_refs": []
}
```

### Station Execution Config Aggregate

`get_station_execution_config(config, station_code)` şu shape'i döner:

```json
{
  "station_code": "ASSEMBLY_01",
  "route_operations": [
    {
      "route_operation": {},
      "input_item": {},
      "output_item": {},
      "steps": [],
      "event_sources": [],
      "validation": {}
    }
  ],
  "event_sources": []
}
```

Kurallar:

- `station_code` uppercase normalize edilir.
- `route_operations`, station'a bağlı active route operation'ları içerir.
- Her route operation kendi aggregate config response'u ile döner.
- `event_sources`, station seviyesindeki active source listesidir.
- Runtime `work_order_operation_execution_state`,
  `work_order_operation_steps`, `operation_events` veya `station_queue`
  okunmaz.

## 9. Validation Tasarımı

Validation read-only olmalıdır. DB'ye hiçbir şey yazmaz; sadece aggregate
response içinde warning/error listeleri üretir.

Kontrol edilecekler:

```text
operation_steps.start_event_source_code null değilse:
  route_operation.station_code + source_code station_event_sources içinde active bulunmalı.

operation_steps.finish_event_source_code null değilse:
  route_operation.station_code + source_code station_event_sources içinde active bulunmalı.

auto_start step:
  start_event_source_code zorunlu.

auto_finish step:
  finish_event_source_code zorunlu.

manual_start step:
  start_event_source_code kiosk/operator source olabilir.

manual_finish step:
  finish_event_source_code kiosk/operator source olabilir.

route_operation input/output item:
  mes.items içinde bulunmalı.

route_operation station_code:
  mes.stations içinde bulunmalı.
```

Önerilen validation result shape:

```json
{
  "severity": "warning",
  "code": "MISSING_EVENT_SOURCE",
  "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
  "step_code": "ROBOT_ARM_DROP_COMPLETED",
  "field": "finish_event_source_code",
  "source_code": "ROBOT_ARM_DROP",
  "message": "Step references a station event source that is not active or missing."
}
```

İlk implementation'da exception fırlatmak yerine validation listesi döndürmek
daha güvenlidir. Runtime engine fazı bu validation sonucunu hard-fail'e
çevirebilir.

## 10. SQL Tasarım İlkeleri

Genel ilkeler:

- Parametreli SQL kullanılmalı.
- Read-only `SELECT` dışında SQL olmamalı.
- `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE` yok.
- `FOR UPDATE` yok.
- Existing lifecycle helper'lara dokunulmamalı.
- Runtime/event/flow tabloları okunmamalı.

Optional parametrelerde PostgreSQL/psycopg ambiguity önlenmelidir:

```sql
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
  AND (
      CAST(%(item_code)s AS text) IS NULL
      OR item_code = CAST(%(item_code)s AS text)
  )
```

Normalize edilmesi gereken alanlar:

```text
station_code
route_code
route_operation_id
item_code
source_code
step_code
```

Uppercase normalize edilebilecek alanlar:

```text
station_code
item_code
route_code
route_operation_id
source_code
step_code
operation_code
```

Lowercase kalması gereken alanlar:

```text
source_type
event_channel
start_mode
finish_mode
actor_type
operation_completion_policy
input_location_role
output_location_role
scrap_location_role
item_type
```

Önerilen SQL ordering:

```text
items: item_type, item_code
process_routes: route_code, version
route_operations: route_code, route_version, sequence_no
station_event_sources: source_type, source_code
operation_steps: step_no
```

## 11. Örnek SQL Sabitleri

Bu bölüm implementation değildir; sonraki fazda üretilecek SQL sabitleri için
tasarım referansıdır.

### Items

```sql
SELECT
    item_code,
    item_name,
    item_type,
    unit,
    active,
    metadata
FROM mes.items
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
ORDER BY item_type, item_code
```

### Process Routes

```sql
SELECT
    route_code,
    version,
    route_name,
    item_code,
    active,
    metadata
FROM mes.process_routes
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
  AND (
      CAST(%(item_code)s AS text) IS NULL
      OR item_code = CAST(%(item_code)s AS text)
  )
ORDER BY route_code, version
```

### Route Operations

```sql
SELECT
    route_operation_id,
    route_code,
    route_version,
    sequence_no,
    operation_code,
    operation_name,
    station_code,
    input_item_code,
    output_item_code,
    input_qty_per_cycle,
    output_qty_per_cycle,
    input_location_role,
    output_location_role,
    scrap_location_role,
    operation_completion_policy,
    planned_cycle_time_sec,
    active,
    metadata
FROM mes.route_operations
WHERE (CAST(%(active_only)s AS boolean) = false OR active = true)
  AND (
      CAST(%(route_code)s AS text) IS NULL
      OR route_code = CAST(%(route_code)s AS text)
  )
  AND (
      CAST(%(station_code)s AS text) IS NULL
      OR station_code = CAST(%(station_code)s AS text)
  )
ORDER BY route_code, route_version, sequence_no
```

### Station Event Sources

```sql
SELECT
    station_code,
    source_code,
    source_name,
    source_type,
    event_channel,
    mqtt_topic,
    active,
    metadata
FROM mes.station_event_sources
WHERE station_code = %(station_code)s
  AND (CAST(%(active_only)s AS boolean) = false OR active = true)
ORDER BY source_type, source_code
```

### Operation Steps

```sql
SELECT
    route_operation_id,
    operation_code,
    step_no,
    step_code,
    step_name,
    start_mode,
    finish_mode,
    start_event_source_code,
    finish_event_source_code,
    required_for_completion,
    records_duration,
    approval_required_after_finish,
    actor_type,
    active,
    metadata
FROM mes.operation_steps
WHERE route_operation_id = %(route_operation_id)s
  AND (CAST(%(active_only)s AS boolean) = false OR active = true)
ORDER BY step_no
```

## 12. Error Handling

Önerilen davranış:

- `database_connection(config)` `None` dönerse mevcut pattern gibi
  `MesqlV2Error("DATABASE_DISABLED", status_code=503)` kullanılabilir.
- Normalize sonrası required key boşsa list helper `[]`, get/resolve helper
  `None` dönebilir.
- Aggregate helper, ana `route_operation` bulunamazsa `None` dönebilir.
- Validation bulguları exception yerine `validation` alanında döner.

Bu yaklaşım read-only helper fazını runtime engine hard-fail davranışından ayrı
tutar.

## 13. Test Tasarımı

Yeni unit testler mevcut fake connection/cursor pattern'i ile
`tests/test_mes_web_mesql_v2.py` içine eklenebilir. DB, Docker veya psql
gerektirmemelidir.

Kapsanacak testler:

```text
list_items active_only filter SQL parametreleri
get_item_by_code normalization
list_process_routes item_code filter
get_process_route route_code/version
list_route_operations station_code filter
get_route_operation missing returns None
list_station_event_sources station-scoped filter
resolve_station_event_source normalization
list_operation_steps ordering by step_no
get_operation_step missing returns None
get_route_operation_config aggregate includes steps/items/event_sources
get_route_operation_config reports missing event source ref
get_station_execution_config includes route operations for station
helpers are read-only and do not call lifecycle mutation SQL
```

Read-only SQL testinde şu kontrol korunmalıdır:

```text
SQL lstrip startswith SELECT
FOR UPDATE yok
insert/update/delete/drop/truncate/alter/create yok
runtime/event/flow tablo isimleri yok
work_orders/work_order_operations/station_queue tablo isimleri yok
```

Fake cursor testleri şu davranışları simüle etmelidir:

- `fetchall()` item, route, operation, source ve step listeleri döner.
- `fetchone()` get/resolve helper'lar için tek row veya `None` döner.
- `executed` listesi üzerinden SQL ve parametreler doğrulanır.
- Aggregate helper'larda source eksikliği fake data ile üretilir.

## 14. İmplementasyon Sırası Önerisi

Bir sonraki implementation fazı dar tutulmalıdır:

1. SQL sabitlerini ekle.
2. Row mapper helper'larını ekle.
3. Basit list/get/resolve helper'ları ekle.
4. Aggregate helper'ları ekle.
5. Read-only validation builder ekle.
6. Fake cursor unit testlerini ekle.
7. `python -m unittest tests.test_mes_web_mesql_v2` ile offline doğrula.

Bu sıra runtime engine, Kiosk action ve IoT adapter ile karışmadan config
okuma katmanını kanıtlar.

## 15. Kabul Kriterleri

Bu tasarım implementation promptuna temel olmak için yeterlidir, eğer:

- Helper kapsamı beş master/config tabloyla sınırlıysa.
- Her helper'ın amacı ve minimum response alanları tanımlıysa.
- Aggregate response shape'leri tanımlıysa.
- Read-only validation yaklaşımı tanımlıysa.
- Parametrik SQL ve explicit cast ilkeleri yazılıysa.
- Unit test planı DB gerektirmeden çalışacak şekilde tanımlıysa.
- Runtime/event/flow, Kiosk dynamic action, IoT adapter, OEE/KPI, inventory ve
  MESQL kapsam dışı kalıyorsa.

## 16. Sonraki Faz Notu

Bu doküman implementation değildir.

Bir sonraki fazda sadece `mes_web/db/mesql_v2.py` içine read-only helper
fonksiyonları ve `tests/test_mes_web_mesql_v2.py` içine unit testler
eklenecektir.

Runtime engine, Kiosk dynamic action, IoT adapter, OEE/KPI, MESQL ve operation
lifecycle mutation hala kapsam dışıdır.
