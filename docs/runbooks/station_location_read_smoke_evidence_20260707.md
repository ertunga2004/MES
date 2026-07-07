# Station/Location Read-Only Helper Smoke Evidence - 2026-07-07

## 1. Amaç

Bu doküman, `mes.locations` ve `mes.station_location_bindings` için eklenen read-only helper fonksiyonlarının unit test ve gerçek local PostgreSQL read smoke ile doğrulandığını kaydeder.

Bu smoke DB write, migration, MESQL, API/UI veya operation lifecycle mutation içermez.

Bu evidence dokümantasyon turunda DB bağlantısı, `psql`, Docker/compose/container komutu, MESQL push/pull veya test/smoke tekrar çalıştırılmamıştır; aşağıdaki sonuçlar önceki implementation/smoke turundan kaydedilmiştir.

## 2. Kapsam

Kapsamdaki helper fonksiyonları:

- `list_locations`
- `get_location_by_code`
- `list_station_location_bindings`
- `resolve_station_location`
- `get_station_location_context`

Kapsamdaki SQL constant'ları:

- `SELECT_LOCATIONS_SQL`
- `SELECT_LOCATION_BY_CODE_SQL`
- `SELECT_STATION_LOCATION_BINDINGS_SQL`
- `SELECT_RESOLVE_STATION_LOCATION_SQL`

Ek doğrulanan fix:

- Optional `NULL` parametre cast fix'i.

Kapsam dışı:

- SQL migration yok.
- DB write yok.
- `psql` yok.
- Docker volume silme yok.
- MESQL push/pull yok.
- API endpoint yok.
- UI/Kiosk yok.
- Inventory movement/balance yok.
- Operation lifecycle mutation yok.

## 3. Implementation Commit Notu

Son commit geçmişinde görülen ilgili commitler:

```text
21cf8d3 "fix: cast station location read filter parameters"
f571716 "feat: add read-only station location helpers"
```

## 4. Kök Neden ve Fix Özeti

İlk smoke `psycopg.errors.AmbiguousParameter` ile fail oldu.

Fail noktası:

```text
list_locations(config, active_only=False, location_type=None)
```

Neden:

PostgreSQL/psycopg, `NULL` gelen optional parametrelerde `%(location_type)s IS NULL` pattern'inde tip çıkarımı yapamadı.

Fix:

Optional parametreler explicit cast edildi:

```text
CAST(%(location_type)s AS text)
CAST(%(role)s AS text)
CAST(%(item_scope)s AS text)
CAST(%(operation_scope)s AS text)
CAST(%(active_only)s AS boolean)
```

## 5. Unit Test Sonucu

Çalıştırılan regression:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_mesql_v2
```

Sonuç:

```text
Ran 27 tests ... OK
```

## 6. Read Smoke Sonucu

Smoke sonucu:

```text
STATION_LOCATION_READ_SMOKE_RESULT = PASS
```

Location sonuçları:

```text
all_location_count = 8
active_location_count = 6
```

Known location doğrulamaları:

```text
RAW_MATERIAL = OK
ASSEMBLY_WIP = OK
BETWEEN_ASSEMBLY_PACKAGING = OK, type=buffer
PACKAGING_WIP = OK
FINISHED_GOODS = OK, type=finished_goods
SCRAP_AREA = OK, type=scrap
HOLD_AREA = OK
REWORK_AREA = OK
```

`PACKAGING_01` binding sonuçları:

```text
PACKAGING_01 active_binding_count = 4
input = BETWEEN_ASSEMBLY_PACKAGING
active_wip = PACKAGING_WIP
output_good = FINISHED_GOODS
output_scrap = SCRAP_AREA
```

`ASSEMBLY_01` binding sonuçları:

```text
ASSEMBLY_01 active_binding_count = 4
input = RAW_MATERIAL
active_wip = ASSEMBLY_WIP
output_good = BETWEEN_ASSEMBLY_PACKAGING
output_buffer = BETWEEN_ASSEMBLY_PACKAGING
```

Resolve sonuçları:

```text
PACKAGING_01/input = BETWEEN_ASSEMBLY_PACKAGING
PACKAGING_01/output_good = FINISHED_GOODS
PACKAGING_01/output_scrap = SCRAP_AREA
ASSEMBLY_01/output_buffer = BETWEEN_ASSEMBLY_PACKAGING
normalization_packaging_output_good = FINISHED_GOODS
```

Missing behavior:

```text
missing_location = None
missing_role = None
missing_station_bindings = []
```

## 7. No-Write Guardrail

Before/after count sonuçları:

```text
before_all_location_count = 8
after_all_location_count = 8

before_PACKAGING_01_active_binding_count = 4
after_PACKAGING_01_active_binding_count = 4

before_ASSEMBLY_01_active_binding_count = 4
after_ASSEMBLY_01_active_binding_count = 4
```

Yorum:

- Smoke read-only kaldı.
- Location/binding count değişmedi.
- Work order / operation / station_queue mutate edilmedi.

## 8. Guardrails

- `psql` kullanılmadı.
- DB write yapılmadı.
- Station/location read helper SQL seti içinde `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `FOR UPDATE` yok.
- Docker volume silinmedi.
- `docker compose down -v` çalıştırılmadı.
- MESQL push/pull çalıştırılmadı.
- API/UI değişmedi.
- Inventory movement/balance/sensor link eklenmedi.
- Operation lifecycle mutate edilmedi.
- SQL migration değişmedi.
- `.env` değişmedi.

## 9. Hüküm

`mes.locations` ve `mes.station_location_bindings` için read-only helper implementation, unit testler ve gerçek local PostgreSQL read smoke ile doğrulanmıştır. Helper'lar `location_code` join key üzerinden doğru station/location context üretebilmekte, optional filter parametreleri PostgreSQL/psycopg uyumlu explicit cast ile çalışmakta ve smoke boyunca DB write gerçekleşmemektedir.

## 10. Sonraki Adım

Bir sonraki teknik adım:

- Read-only helper için dokümantasyon commit'i sonrası API endpoint tasarımı veya helper evidence commit'i.
- API açılacaksa sadece `GET` endpointleri düşünülmeli.
- Inventory movement/balance hâlâ sonraki fazdır.
