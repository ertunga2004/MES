# Station/Location Read-Only API Design

## 1. Amaç

Bu doküman, station/location read model'in MES Web API üzerinden nasıl read-only expose edileceğini tasarlar.

Bu tur implementation değildir. Python route, SQL migration, DB write, smoke veya test çalıştırma içermez.

Tasarlanan API yalnızca `GET` endpointlerinden oluşacaktır. API hiçbir şekilde DB write, inventory movement, balance update, sensor link, MESQL sync veya operation lifecycle mutation başlatmayacaktır.

## 2. Mevcut Doğrulanmış Baseline

Mevcut baseline `docs/architecture/CURRENT_STATE.md`, `docs/runbooks/station_location_read_smoke_evidence_20260707.md` ve Paket A migration evidence'ına göre şöyledir:

- Paket A migration uygulandı.
- `mes.locations` ve `mes.station_location_bindings` tabloları mevcut.
- Read-only helper implementation tamamlandı.
- Optional `NULL` parametre cast fix'i tamamlandı.
- Unit tests: `Ran 27 tests ... OK`.
- Local PostgreSQL read smoke PASS.
- Smoke sonuçları:
  - `all_location_count = 8`
  - `active_location_count = 6`
  - `PACKAGING_01 active_binding_count = 4`
  - `ASSEMBLY_01 active_binding_count = 4`
  - `PACKAGING_01/output_good = FINISHED_GOODS`
  - `PACKAGING_01/output_scrap = SCRAP_AREA`
  - `ASSEMBLY_01/output_buffer = BETWEEN_ASSEMBLY_PACKAGING`
- Operation lifecycle source-of-truth değişmedi.
- MESQL frozen.
- API/UI henüz yok.

## 3. Kapsam

Bu tasarımın kapsamı:

- Read-only `GET` endpoint tasarımı.
- Location list endpoint.
- Location detail endpoint.
- Station binding list endpoint.
- Station location context endpoint.
- Query parameter davranışları.
- Response shape tasarımı.
- Error handling tasarımı.
- Feature flag davranışı.
- Test stratejisi.
- Guardrail ve kabul kriterleri.

## 4. Kapsam Dışı

Bu tasarımın dışında kalanlar:

- `POST`, `PUT`, `PATCH`, `DELETE` yok.
- DB write yok.
- SQL migration yok.
- Inventory movement yok.
- Inventory balance yok.
- Sensor event link yok.
- MESQL push/pull yok.
- Work order lifecycle değişikliği yok.
- Station queue değişikliği yok.
- Operation start/complete değişikliği yok.
- UI/Kiosk implementation yok.
- F-ERP entegrasyonu yok.
- Full WMS yok.
- Auth/role-based authorization bu turda zorunlu değildir; mevcut API pattern'i varsa ileride ele alınabilir.

## 5. Önerilen Endpointler

### 5.1 `GET /api/v2/locations`

Amaç:

- Location listesini okumak.

Query params:

- `active_only`: optional boolean, default `true`
- `location_type`: optional string

Helper:

- `list_locations(config, active_only=True, location_type=None)`

Response 200 örneği:

```json
{
  "ok": true,
  "data": [
    {
      "location_code": "FINISHED_GOODS",
      "location_name": "Finished Goods",
      "location_type": "finished_goods",
      "parent_location_code": null,
      "station_code": null,
      "active": true,
      "metadata": {}
    }
  ],
  "count": 1
}
```

Notlar:

- `location_pk` default response içinde dış API identity olarak sunulmayabilir.
- Debug modda veya internal endpointte gösterilebilir.
- Default public-ish response için `location_code` business key önerilir.

### 5.2 `GET /api/v2/locations/{location_code}`

Amaç:

- Tek location okumak.

Path param:

- `location_code`

Helper:

- `get_location_by_code(config, location_code)`

Behavior:

- `location_code` uppercase normalize edilir.
- Bulunursa 200 döner.
- Bulunamazsa 404 döner.

Response 200 örneği:

```json
{
  "ok": true,
  "data": {
    "location_code": "BETWEEN_ASSEMBLY_PACKAGING",
    "location_name": "Between Assembly and Packaging",
    "location_type": "buffer",
    "parent_location_code": null,
    "station_code": null,
    "active": true,
    "metadata": {}
  }
}
```

Response 404 örneği:

```json
{
  "ok": false,
  "error": {
    "code": "LOCATION_NOT_FOUND",
    "message": "Location not found.",
    "location_code": "DOES_NOT_EXIST"
  }
}
```

### 5.3 `GET /api/v2/stations/{station_code}/locations`

Amaç:

- Station'a bağlı binding/location listesini okumak.

Path param:

- `station_code`

Query params:

- `active_only`: optional boolean, default `true`
- `role`: optional string

Helper:

- `list_station_location_bindings(config, station_code, active_only=True, role=None)`

Behavior:

- `station_code` uppercase normalize edilir.
- `role` lowercase normalize edilir.
- Station binding yoksa 200 + boş liste dönebilir; 404 zorunlu değildir.
- Missing joined location varsa response içinde açıkça gösterilebilir.

Response 200 örneği:

```json
{
  "ok": true,
  "station_code": "PACKAGING_01",
  "data": [
    {
      "role": "input",
      "location_code": "BETWEEN_ASSEMBLY_PACKAGING",
      "priority": 100,
      "active": true,
      "location": {
        "location_code": "BETWEEN_ASSEMBLY_PACKAGING",
        "location_name": "Between Assembly and Packaging",
        "location_type": "buffer",
        "active": true
      }
    }
  ],
  "count": 1
}
```

### 5.4 `GET /api/v2/stations/{station_code}/location-context`

Amaç:

- Station'ın role bazlı birleşik location context'ini okumak.

Path param:

- `station_code`

Helper:

- `get_station_location_context(config, station_code)`

Response 200 örneği:

```json
{
  "ok": true,
  "station_code": "PACKAGING_01",
  "data": {
    "input_location": {
      "location_code": "BETWEEN_ASSEMBLY_PACKAGING",
      "location_type": "buffer"
    },
    "active_wip_location": {
      "location_code": "PACKAGING_WIP",
      "location_type": "wip"
    },
    "output_good_location": {
      "location_code": "FINISHED_GOODS",
      "location_type": "finished_goods"
    },
    "output_scrap_location": {
      "location_code": "SCRAP_AREA",
      "location_type": "scrap"
    },
    "output_buffer_location": null,
    "missing_roles": ["output_buffer"],
    "inactive_or_missing_locations": []
  }
}
```

Notlar:

- `PACKAGING_01` için `output_buffer` missing olması hata değildir.
- Missing role 500 üretmemelidir.
- Bu endpoint sadece bilgi verir; operation complete davranışı değişmez.

## 6. Response Modeli

Genel başarılı response önerisi:

```json
{
  "ok": true,
  "data": {},
  "count": 0
}
```

Genel hatalı response önerisi:

```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message."
  }
}
```

Önerilen error code'lar:

```text
LOCATION_NOT_FOUND
INVALID_QUERY_PARAM
INVALID_LOCATION_TYPE
INVALID_BINDING_ROLE
DATABASE_DISABLED
DATABASE_ERROR
STATION_LOCATION_READ_MODEL_DISABLED
```

Notlar:

- Existing MES Web route'ları çoğunlukla `HTTPException(..., detail="ERROR_CODE")` pattern'ini kullanıyor.
- Implementation sırasında mevcut API standardı bozulmamalıdır.
- Eğer typed `{ok, error}` response eklenirse yalnız station/location read endpointleri içinde tutarlı uygulanmalı veya mevcut global error pattern'iyle uyumlu hale getirilmelidir.

## 7. Query Parameter Validation

### `active_only`

Kabul edilen değerler:

- `true`
- `false`
- `1`
- `0`
- Boşsa default `true`

Invalid değer:

- 400 `INVALID_QUERY_PARAM`

### `location_type`

Kabul edilen değerler:

- `raw_material`
- `wip`
- `buffer`
- `finished_goods`
- `scrap`
- `hold`
- `rework`

Invalid değer:

- 400 `INVALID_LOCATION_TYPE`

### `role`

Kabul edilen değerler:

- `input`
- `active_wip`
- `output_good`
- `output_scrap`
- `output_buffer`

Invalid değer:

- 400 `INVALID_BINDING_ROLE`

Normalization:

- `location_code`: uppercase trim
- `station_code`: uppercase trim
- `role`: lowercase trim
- `location_type`: lowercase trim

## 8. Feature Flag Davranışı

Kullanılacak flag:

```text
MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED
```

Tasarım:

- Default `false`.
- `false` ise endpointler ya route olarak hiç açılmaz ya da 503 `STATION_LOCATION_READ_MODEL_DISABLED` döner.
- `true` ise endpointler helper çağırabilir.
- Bu flag write path açmaz.
- Bu flag MESQL açmaz.
- Bu flag inventory movement/balance açmaz.

### Seçenek A: Route Registration Flag ile Kontrol

Artılar:

- Disabled iken endpoint görünmez.

Eksiler:

- Route listesi runtime config'e göre değişir.
- Debug sırasında endpointin neden görünmediği daha zor anlaşılabilir.

### Seçenek B: Endpoint İçinde Guard

Artılar:

- Endpoint her zaman vardır, disabled ise açık error döner.
- Local debug ve smoke için daha anlaşılırdır.

Eksiler:

- UI endpoint'i görür ama disabled response alır.

Öneri:

- İlk implementation için endpoint içinde guard daha debug-friendly olabilir.

## 9. Helper Entegrasyon Noktası

Mevcut helper'lar:

- `list_locations`
- `get_location_by_code`
- `list_station_location_bindings`
- `resolve_station_location`
- `get_station_location_context`

Entegrasyon kuralları:

- API route'ları helper'ları çağırır.
- API route'ları SQL yazmaz.
- API route'ları DB connection detayını bilmemeli; helper katmanına bırakmalıdır.
- API route'ları response shaping ve validation yapmalıdır.
- Helper'lar operation lifecycle'a bağlı değildir.
- API route'ları `complete_operation_v2`, `start_operation_v2`, `read_station_queue_v2` veya MESQL helper'larını çağırmamalıdır.

## 10. Güvenlik ve Operasyon Guardrail'leri

- Sadece `GET`.
- Write method yok.
- DB write yok.
- SQL migration yok.
- No `FOR UPDATE`.
- No `INSERT/UPDATE/DELETE`.
- No MESQL push/pull.
- No station queue mutation.
- No work order mutation.
- No inventory movement.
- No balance update.
- No sensor event mutation.
- Endpoint read latency düşük olmalıdır; gerekirse ileride cache düşünülebilir ama bu turda cache yok.
- `.env` içine yeni zorunlu secret eklenmemelidir.

## 11. Test Stratejisi

Bu bölüm implementation turu için test planıdır. Bu dokümantasyon turunda test çalıştırılmaz.

### Unit/API Testleri

Önerilen testler:

```text
test_get_locations_endpoint_returns_active_locations
test_get_locations_endpoint_filters_by_location_type
test_get_locations_endpoint_rejects_invalid_location_type
test_get_location_endpoint_returns_404_when_missing
test_get_station_locations_endpoint_returns_bindings
test_get_station_locations_endpoint_filters_by_role
test_get_station_locations_endpoint_rejects_invalid_role
test_get_station_location_context_endpoint_returns_context
test_get_station_location_context_allows_missing_output_buffer
test_station_location_api_disabled_returns_503
test_station_location_api_uses_helpers_not_raw_sql
test_station_location_api_does_not_call_operation_lifecycle_helpers
```

Test yaklaşımı:

- `TestClient` ile route response shape doğrulanmalı.
- Helper fonksiyonları patch edilerek API'nin SQL yazmadığı doğrulanmalı.
- `start_operation_v2`, `complete_operation_v2`, `read_station_queue_v2`, MESQL push/pull helper'ları patch edilip çağrılmadıkları assert edilmeli.
- Feature flag kapalıyken endpoint guard 503 döndürmeli.
- Missing `output_buffer` 500 üretmemeli.

### Integration / Read Smoke

Gerçek DB smoke için önerilen kontroller:

- `GET /api/v2/locations?active_only=false` -> count 8
- `GET /api/v2/locations?active_only=true` -> count 6
- `GET /api/v2/locations/BETWEEN_ASSEMBLY_PACKAGING` -> type `buffer`
- `GET /api/v2/stations/PACKAGING_01/locations` -> count 4
- `GET /api/v2/stations/PACKAGING_01/location-context` -> `output_good = FINISHED_GOODS`, `output_scrap = SCRAP_AREA`
- `GET /api/v2/stations/ASSEMBLY_01/location-context` -> `output_buffer = BETWEEN_ASSEMBLY_PACKAGING`

No-write smoke:

- Before/after location count aynı.
- Before/after binding count aynı.
- Work order/station_queue mutate edilmedi.

## 12. Riskler

| Risk | Etki | Mitigation |
| --- | --- | --- |
| API'nin yanlışlıkla write path açması | DB state veya lifecycle bozulabilir | Sadece `GET`; helper çağrıları read-only SQL ile sınırlı. |
| Endpoint'in operation lifecycle helper'larını çağırması | Start/complete veya queue davranışı değişebilir | Unit testte lifecycle helper'larının çağrılmadığı assert edilmeli. |
| Missing role'un 500'e dönüşmesi | Kiosk/dashboard kırılabilir | `missing_roles` response field olarak dönmeli. |
| Feature flag kapalıyken UI'nin endpoint'e bağımlı hale gelmesi | UI disabled ortamda kırılır | 503 response ve UI fallback ayrı tasarlanmalı. |
| `location_pk` internal key'inin dış API identity gibi kullanılması | Public contract DB internal identity'ye bağlanır | Default identity `location_code` olmalı. |
| `location_id` ile yanlış lookup/join varsayımı | Actual schema ile uyumsuz sonuç | Join/lookup business key `location_code` olarak korunmalı. |
| API'nin MESQL sync gibi yorumlanması | Yanlış operasyonel beklenti doğar | Dokümantasyon ve guardrail: MESQL yok. |
| Inventory movement/balance fazına erken kayılması | Scope büyür ve lifecycle etkilenir | Bu API yalnız read-only visibility sağlar. |
| Response shape'in ileride UI için yetersiz kalması | UI ek alan isteyebilir | Metadata ve optional internal debug alanları ayrı değerlendirilmeli. |
| Çok fazla field expose edilmesi | API contract gereksiz genişler | Default response minimal, debug/internal response ayrı olmalı. |

## 13. Kabul Kriterleri

Bu tasarım dokümanı tamam sayılmak için:

- Sadece read-only `GET` endpointleri tanımlandı.
- Response shape önerildi.
- Error handling önerildi.
- Query parameter validation yazıldı.
- Feature flag davranışı yazıldı.
- Helper entegrasyon sınırı net.
- Operation lifecycle'a dokunulmayacağı net.
- MESQL yok.
- Inventory movement/balance yok.
- Test stratejisi var.
- Implementation promptuna temel olacak kadar açık.

## 14. Sonraki Adım

Bu tasarım onaylandıktan sonra bir sonraki teknik adım:

- read-only station/location API endpoint implementation
- route-level unit tests
- local API read smoke
- no DB write
- no operation lifecycle behavior change

Ancak bu doküman turunda implementation yapılmayacaktır.
