# Station Execution Config Read API Design

## 1. Amaç

Bu doküman, station execution config read-only helper katmanını HTTP GET API
olarak açmadan önce endpoint sözleşmesini, feature flag davranışını, response
shape'lerini, error modelini ve test planını tanımlar.

Bu doküman implementation değildir. Kod, DB, Docker, psql, migration, seed,
Kiosk, runtime engine, IoT adapter, OEE/KPI, inventory movement/balance veya
MESQL davranışı değiştirmez.

## 2. Baseline

Mevcut doğrulanmış durum:

```text
Station execution schema migration: APPLIED / PASS
Minimal station execution seed: APPLIED / PASS
Config read helpers: IMPLEMENTED / PASS
Real local PostgreSQL config read smoke: PASS
Runtime/event/flow tables: 0
Kiosk dynamic action: NOT_STARTED
Runtime engine: NOT_STARTED
IoT adapter: NOT_STARTED
OEE/KPI: NOT_STARTED
MESQL: frozen
```

Config helper kapsamı:

```text
list_items
get_item_by_code
list_process_routes
get_process_route
list_route_operations
get_route_operation
list_station_event_sources
resolve_station_event_source
list_operation_steps
get_operation_step
get_route_operation_config
get_station_execution_config
```

Bu API bu helper'ları read-only endpoint sözleşmesine taşımayı hedefler.

## 3. Kapsam

API yalnızca station execution master/config verisini okuyacaktır:

```text
mes.items
mes.process_routes
mes.route_operations
mes.station_event_sources
mes.operation_steps
mes.stations
```

API şu soruları HTTP GET ile cevaplayabilmelidir:

```text
Sistemde hangi station execution item'ları var?
Hangi route'lar var?
Bir route'un operation listesi nedir?
Bir station için hangi route operation tanımlı?
Bir station için hangi event source'lar tanımlı?
Bir route operation'ın step listesi nedir?
Bir route operation'ın aggregate config'i nedir?
Bir station'ın aggregate execution config'i nedir?
```

## 4. Kapsam Dışı

Bu API şu verileri okumaz veya değiştirmez:

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

Bu fazda yok:

- Runtime state read/write.
- Work order read/write.
- Queue read/write.
- Operation start/complete.
- Event ingest.
- Kiosk action POST.
- Runtime engine transition.
- Inventory movement/balance.
- MESQL push/pull.

## 5. Feature Flag

Yeni API ayrı bir feature flag ile kapalı gelmelidir:

```text
MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED
```

Default:

```text
false
```

Flag disabled ise tüm yeni endpointler şu response ile `503` dönmelidir:

```json
{
  "detail": "STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED"
}
```

Bu flag mevcut station/location read model flag'inden bağımsızdır:

```text
MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED
```

İki flag birbirini etkilememelidir. Station/location endpointleri kendi flag'i
ile, station execution config endpointleri kendi flag'i ile kontrol edilir.

## 6. Önerilen Endpoint Seti

Implementation için önerilen net path seti:

```text
GET /api/v2/station-execution/items
GET /api/v2/station-execution/items/{item_code}

GET /api/v2/station-execution/routes
GET /api/v2/station-execution/routes/{route_code}

GET /api/v2/station-execution/route-operations
GET /api/v2/station-execution/route-operations/{route_operation_id}

GET /api/v2/stations/{station_code}/execution-event-sources
GET /api/v2/stations/{station_code}/execution-config

GET /api/v2/station-execution/route-operations/{route_operation_id}/steps
GET /api/v2/station-execution/route-operations/{route_operation_id}/config
```

Naming notu:

- `station-execution` prefix'i master/config kaynaklarını tek namespace altında
  toplar.
- Station-scoped context endpointleri mevcut
  `/api/v2/stations/{station_code}/...` convention'ını korur.
- `execution-event-sources` adı, bu kaynakların station/location binding değil
  station execution event source olduğunu açıkça ayırır.

## 7. Query Parametreleri

### Items

```text
GET /api/v2/station-execution/items?active_only=true
```

Parametreler:

```text
active_only: boolean, default true
```

### Routes

```text
GET /api/v2/station-execution/routes?active_only=true&item_code=PACKAGED_PRODUCT
```

Parametreler:

```text
active_only: boolean, default true
item_code: optional string
```

### Get Route

```text
GET /api/v2/station-execution/routes/{route_code}?version=1
```

Parametreler:

```text
version: integer, default 1
```

`version < 1` invalid kabul edilmeli ve `400 INVALID_QUERY_PARAM` dönmelidir.

### Route Operations

```text
GET /api/v2/station-execution/route-operations?active_only=true&route_code=ROUTE_BOX_PACKAGING_V1&station_code=ASSEMBLY_01
```

Parametreler:

```text
active_only: boolean, default true
route_code: optional string
station_code: optional string
```

### Event Sources

```text
GET /api/v2/stations/{station_code}/execution-event-sources?active_only=true
```

Parametreler:

```text
active_only: boolean, default true
```

### Steps

```text
GET /api/v2/station-execution/route-operations/{route_operation_id}/steps?active_only=true
```

Parametreler:

```text
active_only: boolean, default true
```

## 8. Boolean Validation

Boolean query parser mevcut station/location API ile uyumlu olmalıdır.

Kabul edilecek değerler:

```text
true
false
1
0
```

Boş veya eksik değer default davranışa düşer:

```text
active_only = true
```

Invalid örnek:

```text
active_only=maybe
```

Beklenen response:

```json
{
  "detail": "INVALID_QUERY_PARAM"
}
```

Status:

```text
400
```

## 9. Path ve Query Normalization

Path ve query parametreleri route layer'da normalize edilmelidir:

```text
item_code -> uppercase/strip
route_code -> uppercase/strip
route_operation_id -> uppercase/strip
station_code -> uppercase/strip
source_code -> uppercase/strip
step_code -> uppercase/strip
```

Response içinde canonical uppercase değer dönmelidir.

Policy/mode/type alanları lowercase kalmalıdır:

```text
item_type
source_type
event_channel
start_mode
finish_mode
actor_type
operation_completion_policy
input_location_role
output_location_role
scrap_location_role
```

## 10. Response Shape

Mevcut station/location API `{"ok": true, ...}` pattern'i kullandığı için bu
API de aynı pattern'i korumalıdır. Endpoint-specific field'lar ayrıca açık
dönmelidir.

### List Items

```json
{
  "ok": true,
  "items": [],
  "count": 0
}
```

### Get Item

Found:

```json
{
  "ok": true,
  "item": {}
}
```

Missing:

```json
{
  "detail": "ITEM_NOT_FOUND"
}
```

Status:

```text
404
```

### List Routes

```json
{
  "ok": true,
  "routes": [],
  "count": 0
}
```

### Get Route

Found:

```json
{
  "ok": true,
  "route": {}
}
```

Missing:

```json
{
  "detail": "PROCESS_ROUTE_NOT_FOUND"
}
```

Status:

```text
404
```

### List Route Operations

```json
{
  "ok": true,
  "route_operations": [],
  "count": 0
}
```

### Get Route Operation

Found:

```json
{
  "ok": true,
  "route_operation": {}
}
```

Missing:

```json
{
  "detail": "ROUTE_OPERATION_NOT_FOUND"
}
```

Status:

```text
404
```

### Station Event Sources

```json
{
  "ok": true,
  "station_code": "ASSEMBLY_01",
  "event_sources": [],
  "count": 0
}
```

Station yoksa ilk faz davranışı:

```text
200 empty list
```

Gerekçe:

- Helper source listesi station validation yapmaz.
- Station aggregate endpointi validation içinde `missing_station` warning
  dönebilir.
- Runtime engine fazı bunu hard-fail'e çevirebilir.

### Route Operation Steps

```json
{
  "ok": true,
  "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
  "steps": [],
  "count": 0
}
```

Route operation yoksa:

```json
{
  "detail": "ROUTE_OPERATION_NOT_FOUND"
}
```

Status:

```text
404
```

### Route Operation Aggregate Config

```json
{
  "ok": true,
  "config": {
    "route_operation": {},
    "input_item": {},
    "output_item": {},
    "steps": [],
    "event_sources": [],
    "validation": {}
  }
}
```

Missing operation:

```json
{
  "detail": "ROUTE_OPERATION_NOT_FOUND"
}
```

Status:

```text
404
```

### Station Execution Aggregate Config

```json
{
  "ok": true,
  "config": {
    "station_code": "ASSEMBLY_01",
    "route_operations": [],
    "event_sources": [],
    "validation": {}
  }
}
```

Station yoksa ilk faz davranışı:

```text
200 + validation.missing_station warning
```

Gerekçe:

- Bu faz read-only config discovery fazıdır.
- UI/setup ekranları missing config'i görebilmelidir.
- Runtime engine fazında aynı durum hard-fail olabilir.

## 11. Error Modeli

| Detail | Status | Anlam |
| --- | ---: | --- |
| `STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED` | 503 | Feature flag kapalı |
| `INVALID_QUERY_PARAM` | 400 | Boolean veya version parametresi invalid |
| `ITEM_NOT_FOUND` | 404 | `item_code` bulunamadı |
| `PROCESS_ROUTE_NOT_FOUND` | 404 | `route_code/version` bulunamadı |
| `ROUTE_OPERATION_NOT_FOUND` | 404 | `route_operation_id` bulunamadı |
| `DATABASE_DISABLED` | 503 | DB disabled veya helper `MesqlV2Error` |
| `INTERNAL_ERROR` | 500 | Beklenmeyen exception için fallback |

`DATABASE_DISABLED`, mevcut `MesqlV2Error` davranışı üzerinden geliyorsa route
layer bunu bozmamalıdır.

## 12. API Implementation Notları

Bu doküman implementation yapmaz. Sonraki fazda route'lar muhtemelen
`mes_web/__main__.py` içine, mevcut `register_station_location_read_routes`
pattern'ine benzer ayrı bir register fonksiyonu olarak eklenebilir:

```text
register_station_execution_config_read_routes(app, app_config)
```

Import edilecek helper'lar:

```text
list_items
get_item_by_code
list_process_routes
get_process_route
list_route_operations
get_route_operation
list_station_event_sources
list_operation_steps
get_route_operation_config
get_station_execution_config
MesqlV2Error
```

Feature flag helper mevcut pattern'e benzer olmalıdır:

```text
_station_execution_config_read_model_enabled()
```

Mevcut `_parse_active_only` yeniden kullanılabilir veya aynı behavior korunarak
ortaklaştırılabilir. Bu fazda station/location flag behavior'ı
değiştirilmemelidir.

## 13. Test Tasarımı

Yeni route-level test dosyası:

```text
tests/test_mes_web_station_execution_config_api.py
```

Testler DB gerektirmemelidir. Helper fonksiyonları patch/mock edilmelidir.

Kapsanacak testler:

```text
disabled flag returns 503 for all new endpoint groups
invalid active_only returns 400 INVALID_QUERY_PARAM
list items returns items
get item normalizes item_code and returns item
get missing item returns 404 ITEM_NOT_FOUND

list routes passes active_only and item_code
get route uses version default 1
get route rejects invalid version
get missing route returns 404 PROCESS_ROUTE_NOT_FOUND

list route operations passes route_code/station_code filters
get route operation returns route_operation
get missing route operation returns 404 ROUTE_OPERATION_NOT_FOUND

station event sources endpoint returns station_code and event_sources
route operation steps endpoint returns steps
route operation steps returns 404 when operation missing
route operation config endpoint returns aggregate config
route operation config missing returns 404
station execution config endpoint returns aggregate config

MesqlV2Error DATABASE_DISABLED maps to 503
unexpected exception maps to 500 or follows existing app convention
new API routes do not call lifecycle helpers
new API routes do not access raw database_connection directly
```

Regression:

```text
tests/test_mes_web_station_location_api.py must still pass.
tests/test_mes_web_mesql_v2.py must still pass.
```

## 14. HTTP Smoke Tasarımı

Implementation sonrası local smoke ayrı fazda yapılacaktır.

Feature flag disabled:

```text
GET /api/v2/station-execution/items -> 503
```

Feature flag enabled:

```text
GET /api/v2/station-execution/items -> 200, items >= 3
GET /api/v2/station-execution/routes -> 200, route exists
GET /api/v2/station-execution/route-operations?station_code=ASSEMBLY_01 -> 200, count 1
GET /api/v2/stations/ASSEMBLY_01/execution-config -> 200, route_operations count 1
GET /api/v2/stations/PACKAGING_01/execution-config -> 200, route_operations count 1
```

Smoke guardrails:

- Write SQL yok.
- POST yok.
- Kiosk action yok.
- Runtime state yok.
- Work order/queue mutation yok.
- MESQL yok.

## 15. Güvenlik / Guardrails

Bu API read-only config API'dir.

Şunları yapmaz:

```text
Runtime execution başlatmaz.
Operation complete etmez.
Event ingest yapmaz.
Work order oluşturmaz/değiştirmez.
Station queue değiştirmez.
Inventory movement/balance üretmez.
MESQL push/pull yapmaz.
Kiosk action POST sağlamaz.
Runtime/event/flow tablosu okumaz veya yazmaz.
```

## 16. Kabul Kriterleri

- Endpoint listesi net.
- Feature flag behavior net.
- Query param validation net.
- Path/query normalization net.
- Response shape net.
- Error model net.
- Test planı DB gerektirmeden route-level mock ile çalışacak şekilde net.
- HTTP smoke beklentisi ayrı faz için tanımlı.
- Runtime/event/flow, Kiosk action, MESQL ve lifecycle mutation kapsam dışı.
- Station/location API flag ve behavior etkilenmiyor.
