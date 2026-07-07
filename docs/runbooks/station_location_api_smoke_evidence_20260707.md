# Station/Location Read-Only API Smoke Evidence - 2026-07-07

## 1. Amaç

Bu doküman, station/location read-only API endpointlerinin route-level unit testler ve gerçek local HTTP API smoke ile doğrulandığını kaydeder.

API yalnız `GET` endpointlerinden oluşur.

Smoke DB write, SQL migration, MESQL push/pull, UI/Kiosk değişikliği veya operation lifecycle mutation içermez.

## 2. Kapsam

Kapsamdaki endpointler:

```text
GET /api/v2/locations
GET /api/v2/locations/{location_code}
GET /api/v2/stations/{station_code}/locations
GET /api/v2/stations/{station_code}/location-context
```

Kapsamdaki feature flag:

```text
MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED
```

Kapsamdaki test/smoke:

- Route-level unit tests.
- `mesql_v2` regression tests.
- Real local HTTP GET smoke.
- Error/validation smoke.
- No-write before/after count guardrail.
- Logs check.
- Post-smoke base compose reset / disabled flag behavior check.

Kapsam dışı:

- `POST`, `PUT`, `PATCH`, `DELETE`.
- DB write.
- SQL migration.
- MESQL push/pull.
- Inventory movement/balance.
- Sensor event link.
- Operation lifecycle mutation.
- UI/Kiosk implementation.
- F-ERP entegrasyonu.

## 3. Implementation Commit Notu

Son commit geçmişinde görülen ilgili commitler:

```text
c95d395 "feat: add read-only station location api"
7c3e312 "docs: design station location read api"
21cf8d3 "fix: cast station location read filter parameters"
f571716 "feat: add read-only station location helpers"
```

## 4. Unit Test Sonuçları

```text
tests.test_mes_web_station_location_api: Ran 14 tests ... OK
tests.test_mes_web_mesql_v2: Ran 27 tests ... OK
```

## 5. Rebuild/Recreate Bilgisi

- Smoke için geçici override ile `MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED=true` verildi.
- Komut:

```powershell
docker compose -f docker\mes\compose.portable.yaml -f $SmokeOverride up -d --build mes_web
```

- `mes_web` rebuilt/recreated successfully.
- Health after rebuild: `ok`.
- Temporary override file removed after smoke.

## 6. Endpoint Smoke Sonuçları

Location endpointleri:

```text
GET /api/v2/locations?active_only=false -> count = 8
GET /api/v2/locations?active_only=true -> count = 6
GET /api/v2/locations?location_type=BUFFER -> BETWEEN_ASSEMBLY_PACKAGING, type = buffer
GET /api/v2/locations/BETWEEN_ASSEMBLY_PACKAGING -> type = buffer
GET /api/v2/locations/FINISHED_GOODS -> type = finished_goods
GET /api/v2/locations/SCRAP_AREA -> type = scrap
```

`PACKAGING_01`:

```text
GET /api/v2/stations/PACKAGING_01/locations -> count = 4

input = BETWEEN_ASSEMBLY_PACKAGING
active_wip = PACKAGING_WIP
output_good = FINISHED_GOODS
output_scrap = SCRAP_AREA

GET /api/v2/stations/PACKAGING_01/locations?role=OUTPUT_GOOD -> count = 1, location_code = FINISHED_GOODS
```

`ASSEMBLY_01`:

```text
GET /api/v2/stations/ASSEMBLY_01/locations -> count = 4

input = RAW_MATERIAL
active_wip = ASSEMBLY_WIP
output_good = BETWEEN_ASSEMBLY_PACKAGING
output_buffer = BETWEEN_ASSEMBLY_PACKAGING
```

Context endpointleri:

```text
GET /api/v2/stations/PACKAGING_01/location-context -> expected input/WIP/good/scrap OK, output_buffer_location = null
GET /api/v2/stations/ASSEMBLY_01/location-context -> expected input/WIP/good/output_buffer OK
```

## 7. Error / Validation Smoke

```text
GET /api/v2/locations/DOES_NOT_EXIST -> 404 LOCATION_NOT_FOUND
GET /api/v2/locations?location_type=unknown -> 400 INVALID_LOCATION_TYPE
GET /api/v2/stations/PACKAGING_01/locations?role=unknown -> 400 INVALID_BINDING_ROLE
GET /api/v2/stations/DOES_NOT_EXIST/locations -> 200, count = 0, data = []
```

## 8. No-Write Guardrail

Before/after count sonuçları:

```text
all location count: 8 -> 8
PACKAGING_01 binding count: 4 -> 4
ASSEMBLY_01 binding count: 4 -> 4
```

Yorum:

- API smoke read-only kaldı.
- Location/binding count değişmedi.
- Work order / operation / station_queue mutate edilmedi.

## 9. Logs Kontrolü

- 500 yok.
- MESQL push/pull yok.
- Operation lifecycle mutation yok.
- Logs only show startup, health, expected GET 200s, expected 400/404 validation responses.

## 10. Post-Smoke Feature Flag Baseline

Base compose recreate command:

```powershell
docker compose -f docker\mes\compose.portable.yaml up -d --build mes_web
```

Health after base compose recreate:

```text
ok
```

Default disabled behavior:

```text
GET /api/v2/locations with default base compose env -> 503 STATION_LOCATION_READ_MODEL_DISABLED
```

Yorum:

- Feature flag default disabled baseline doğrulandı.
- `.env` değiştirilmedi.
- Smoke override kalıcılaştırılmadı.

## 11. Guardrails

- API yalnız `GET`.
- DB write yok.
- `psql` yok.
- Docker volume silme yok.
- `docker compose down -v` yok.
- SQL migration yok.
- MESQL push/pull yok.
- Inventory movement/balance yok.
- Sensor event link yok.
- Operation lifecycle mutate edilmedi.
- UI/Kiosk yok.
- Runtime data değişmedi.
- `.env` değişmedi.

## 12. Hüküm

Station/location read-only API endpointleri route-level unit testler, `mesql_v2` regression testleri ve gerçek local HTTP API read smoke ile doğrulanmıştır. Endpointler sadece `GET` davranışı sergilemiş, expected response/error modellerini üretmiş, no-write count guardrail'leri korunmuş ve smoke sonrası base compose ortamında feature flag default disabled davranışı `503 STATION_LOCATION_READ_MODEL_DISABLED` ile doğrulanmıştır.

## 13. Sonraki Adım

- Evidence commit sonrası `CURRENT_STATE.md` checkpoint'i tamamlanır.
- Sonraki teknik karar: API'nin UI/Kiosk tarafından okunması mı, yoksa önce API smoke'un CI/test dokümantasyonuna alınması mı?
- Inventory movement/balance hâlâ sonraki fazdır.
