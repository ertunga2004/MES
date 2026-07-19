# Station Execution Minimal Seed Apply Runbook

## 1. Amaç

Bu runbook, `db/migrations/005_station_execution_seed_minimal.sql` dosyasının
ileride lokal PostgreSQL üzerinde kontrollü şekilde uygulanması ve doğrulanması
için operasyon taslağıdır.

Bu doküman seed'i uygulamaz. Bu turda DB bağlantısı, `psql`, Docker, seed apply,
runtime implementation veya Kiosk dynamic action yoktur.

## 2. Kapsam

Bu seed apply task'ı şu tablolara minimal demo master/config verisi ekler:

- `mes.items`
- `mes.process_routes`
- `mes.route_operations`
- `mes.station_event_sources`
- `mes.operation_steps`

Seed senaryosu:

- Demo route: `ROUTE_BOX_PACKAGING_V1`
- Stations: `ASSEMBLY_01`, `PACKAGING_01`
- Items: `RAW_BOX`, `COLOR_CLASSIFIED_BOX`, `PACKAGED_PRODUCT`
- Route operations: OP10 assembly/classification, OP20 packaging
- Event sources: color sensor, robot arm, kiosk operator
- Operation steps: 3 assembly steps, 2 packaging steps

## 3. Kapsam dışı

Bu seed apply task'ı şu tablolara veri eklemez:

- `mes.work_order_operation_execution_state`
- `mes.work_order_operation_steps`
- `mes.operation_events`
- `mes.operation_approvals`
- `mes.production_flow_events`
- `mes.work_orders`
- `mes.work_order_operations`
- `mes.station_queue`
- `mes.locations`
- `mes.station_location_bindings`

Ek kapsam dışı işler:

- Runtime engine implementation yok.
- Kiosk dynamic action implementation yok.
- IoT adapter implementation yok.
- OEE/KPI implementation yok.
- Inventory movement/balance yok.
- MESQL push/pull yok.
- Operation start/complete lifecycle smoke yok.
- Docker volume silme yok.
- `docker compose down -v` yok.

## 4. Ön koşullar

- `004_station_execution_schema.sql` local PostgreSQL üzerinde PASS ile
  uygulanmış olmalı.
- Evidence mevcut olmalı:
  `docs/runbooks/station_execution_schema_migration_evidence_20260709.md`
- `db/migrations/005_station_execution_seed_minimal.sql` repo içinde mevcut
  olmalı.
- `mes_postgres` container çalışıyor ve healthy olmalı.
- `mes_postgres_data` volume silinmemiş olmalı.
- `mes.stations` içinde `ASSEMBLY_01` ve `PACKAGING_01` mevcut ve active olmalı.
- `mes.locations` ve `mes.station_location_bindings` baseline'ı korunmuş olmalı.
- `.env` commitlenmemeli.
- Seed apply öncesi PostgreSQL backup alınmalı.
- MESQL frozen kalmalı; açık onay olmadan MESQL push/pull çalıştırılmamalı.

## 5. Riskler

- Seed master/config tablolarını güncel tutmak için idempotent upsert kullanır.
- Seed, route/step policy'yi tanımlar; runtime engine henüz yoksa bu veriler
  yalnızca configuration olarak kalır.
- `station_event_sources.source_code` global unique değildir; geçerlilik
  `station_code + source_code` olarak değerlendirilmelidir.
- `operation_steps.start_event_source_code` ve
  `operation_steps.finish_event_source_code` station-scoped semantic reference
  olarak değerlendirilir. Geçerlilik, `route_operations.station_code` ve
  `source_code` kombinasyonu üzerinden future setup/runtime validator ile
  kontrol edilmelidir.
- Kiosk dynamic action implementation başlamadan bu seed tek başına operatör
  buton davranışını değiştirmez.
- Manual rollback için seed satırlarını silmek önerilmez; önce backup restore
  planı değerlendirilmelidir.

## 6. Pre-Apply Checklist

Bu komutlar seed uygulanacağı zaman çalıştırılmalıdır. Bu doküman oluşturulurken
çalıştırılmamıştır.

Git çalışma ağacı:

```powershell
git status --short
```

Seed dosyası var mı:

```powershell
Test-Path -LiteralPath "db\migrations\005_station_execution_seed_minimal.sql"
```

Portable servis durumu:

```powershell
docker compose -f docker\mes\compose.portable.yaml ps
```

Bu ortamda `docker compose` desteklenmiyorsa salt-okuma status için şu form
kullanılabilir:

```powershell
docker-compose -f docker\mes\compose.portable.yaml ps
```

Health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Ön koşul tabloları:

```powershell
@'
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'mes'
  AND table_name IN (
    'items',
    'process_routes',
    'route_operations',
    'operation_steps',
    'station_event_sources',
    'work_order_operation_execution_state',
    'work_order_operation_steps',
    'operation_events',
    'operation_approvals',
    'production_flow_events',
    'locations',
    'station_location_bindings',
    'stations'
  )
ORDER BY table_name;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen:

- 10 station execution tablosu mevcut.
- `locations`, `station_location_bindings`, `stations` mevcut.

Station prerequisite:

```powershell
@'
SELECT station_code, active
FROM mes.stations
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
ORDER BY station_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen:

- `ASSEMBLY_01` mevcut ve active.
- `PACKAGING_01` mevcut ve active.

Station/location baseline:

```powershell
@'
SELECT 'locations' AS table_name, count(*) AS row_count
FROM mes.locations
UNION ALL
SELECT 'active_station_location_bindings' AS table_name, count(*) AS row_count
FROM mes.station_location_bindings
WHERE active = true;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen:

```text
locations = 8
active_station_location_bindings = 8
```

## 7. Backup planı

Seed apply öncesi backup alınmalıdır.

Backup root:

```text
<portable-runtime-root>\data\db_backups
```

Örnek backup adı:

```text
mes_postgres_before_005_station_execution_seed_minimal_YYYYMMDD-HHMMSS.sql
```

PowerShell backup komutu:

```powershell
$PortableRuntimeRootInput = '<approved-portable-runtime-root>'
if ([string]::IsNullOrWhiteSpace($PortableRuntimeRootInput) -or
    $PortableRuntimeRootInput -eq '<approved-portable-runtime-root>') {
  throw 'Set PortableRuntimeRootInput to the approved portable runtime root.'
}
$PortableRuntimeRoot =
  (Resolve-Path -LiteralPath $PortableRuntimeRootInput -ErrorAction Stop).Path
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $PortableRuntimeRoot "data\db_backups"
if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) {
  throw "Approved backup directory is missing: $BackupDir"
}
$BackupFile = Join-Path $BackupDir "mes_postgres_before_005_station_execution_seed_minimal_$Stamp.sql"
docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > $BackupFile
Write-Output $BackupFile
Test-Path -LiteralPath $BackupFile
Get-Item -LiteralPath $BackupFile | Select-Object FullName, Length, LastWriteTime
```

Backup oluşmazsa veya dosya boyutu 0 ise seed uygulanmamalıdır.

## 8. Destructive keyword kontrolü

Seed SQL için destructive/forbidden table taraması:

```powershell
Select-String -Path "db\migrations\005_station_execution_seed_minimal.sql" -Pattern "DROP TABLE|DROP COLUMN|ALTER TABLE|TRUNCATE|DELETE FROM|UPDATE mes\.work_orders|UPDATE mes\.work_order_operations|UPDATE mes\.station_queue|UPDATE mes\.locations|UPDATE mes\.station_location_bindings|INSERT INTO mes\.work_orders|INSERT INTO mes\.work_order_operations|INSERT INTO mes\.station_queue|INSERT INTO mes\.locations|INSERT INTO mes\.station_location_bindings"
```

Beklenen:

```text
No matches
```

Not: Seed SQL içinde `ON CONFLICT DO UPDATE` kullanılabilir. Bu genel `UPDATE`
kelimesi olarak değil, yalnızca forbidden table update pattern'leri açısından
değerlendirilmelidir.

Runtime/event insert kontrolü:

```powershell
Select-String -Path "db\migrations\005_station_execution_seed_minimal.sql" -Pattern "INSERT INTO mes\.work_order_operation_execution_state|INSERT INTO mes\.work_order_operation_steps|INSERT INTO mes\.operation_events|INSERT INTO mes\.operation_approvals|INSERT INTO mes\.production_flow_events"
```

Beklenen:

```text
No matches
```

## 9. Seed apply komutu taslağı

Bu komut yalnızca açık uygulama onayı olduğunda çalıştırılmalıdır.

```powershell
Get-Content -Raw -LiteralPath "db\migrations\005_station_execution_seed_minimal.sql" |
  docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Bu form Windows host ortamındaki `$env:POSTGRES_USER`, `$env:POSTGRES_DB` ve
`$env:POSTGRES_PASSWORD` değerlerine bağımlı değildir. Değerler `mes_postgres`
container içindeki env değerlerinden okunur.

## 10. Seed verify sorguları

Items:

```powershell
@'
SELECT item_code, item_type, active
FROM mes.items
WHERE item_code IN ('RAW_BOX', 'COLOR_CLASSIFIED_BOX', 'PACKAGED_PRODUCT')
ORDER BY item_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Route:

```powershell
@'
SELECT route_code, version, item_code, active
FROM mes.process_routes
WHERE route_code = 'ROUTE_BOX_PACKAGING_V1';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Route operations:

```powershell
@'
SELECT route_operation_id, route_code, route_version, sequence_no,
       operation_code, station_code, input_item_code, output_item_code,
       operation_completion_policy, active
FROM mes.route_operations
WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
ORDER BY sequence_no;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Station event sources:

```powershell
@'
SELECT station_code, source_code, source_type, event_channel, active
FROM mes.station_event_sources
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
ORDER BY station_code, source_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Operation steps:

```powershell
@'
SELECT route_operation_id, step_no, step_code, start_mode, finish_mode,
       start_event_source_code, finish_event_source_code,
       required_for_completion, approval_required_after_finish, actor_type, active
FROM mes.operation_steps
WHERE route_operation_id IN (
  'ROUTE_BOX_PACKAGING_V1_OP10',
  'ROUTE_BOX_PACKAGING_V1_OP20'
)
ORDER BY route_operation_id, step_no;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Expected counts:

```powershell
@'
SELECT 'items' AS scope, count(*) AS row_count
FROM mes.items
WHERE item_code IN ('RAW_BOX', 'COLOR_CLASSIFIED_BOX', 'PACKAGED_PRODUCT')
UNION ALL
SELECT 'process_routes', count(*)
FROM mes.process_routes
WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
UNION ALL
SELECT 'route_operations', count(*)
FROM mes.route_operations
WHERE route_code = 'ROUTE_BOX_PACKAGING_V1'
UNION ALL
SELECT 'station_event_sources', count(*)
FROM mes.station_event_sources
WHERE (station_code, source_code) IN (
  ('ASSEMBLY_01', 'COLOR_SENSOR_ENTRY'),
  ('ASSEMBLY_01', 'ROBOT_ARM_DROP'),
  ('ASSEMBLY_01', 'KIOSK_OPERATOR'),
  ('PACKAGING_01', 'KIOSK_OPERATOR')
)
UNION ALL
SELECT 'operation_steps', count(*)
FROM mes.operation_steps
WHERE route_operation_id IN (
  'ROUTE_BOX_PACKAGING_V1_OP10',
  'ROUTE_BOX_PACKAGING_V1_OP20'
);
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Expected:

```text
items = 3
process_routes = 1
route_operations = 2
station_event_sources = 4
operation_steps = 5
```

## 11. No-runtime/no-event-data kontrolü

Seed apply sonrası runtime/event/flow tabloları hala 0 satır olmalıdır:

```powershell
@'
SELECT 'work_order_operation_execution_state' AS table_name, count(*) FROM mes.work_order_operation_execution_state
UNION ALL
SELECT 'work_order_operation_steps', count(*) FROM mes.work_order_operation_steps
UNION ALL
SELECT 'operation_events', count(*) FROM mes.operation_events
UNION ALL
SELECT 'operation_approvals', count(*) FROM mes.operation_approvals
UNION ALL
SELECT 'production_flow_events', count(*) FROM mes.production_flow_events;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen:

```text
Bu seed apply sonrası bu runtime/event/flow tabloları hala 0 satır olmalı.
```

## 12. Station/location baseline kontrolü

Seed apply `mes.locations` ve `mes.station_location_bindings` tablolarına
yazmamalıdır.

```powershell
@'
SELECT 'locations' AS table_name, count(*) AS row_count
FROM mes.locations
UNION ALL
SELECT 'active_station_location_bindings' AS table_name, count(*) AS row_count
FROM mes.station_location_bindings
WHERE active = true;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen:

```text
locations = 8
active_station_location_bindings = 8
```

## 13. Health/limited regression planı

Seed apply sonrası health kontrolü:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Station/location read-only API default-disabled kontrolü:

```powershell
try {
  Invoke-RestMethod http://127.0.0.1:8080/api/v2/locations
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

Beklenen default davranış:

```text
503
```

Feature flag ortamda açıksa endpoint 200 dönebilir; evidence içinde
`feature flag open environment` olarak not düşülmelidir.

Kiosk static smoke sadece HTTP GET ile yapılabilir:

```powershell
Invoke-WebRequest http://127.0.0.1:8080/kiosk -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8080/static/kiosk.js -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8080/static/kiosk.css -UseBasicParsing | Select-Object StatusCode
```

Bu smoke sırasında:

- Kiosk action POST yapma.
- Start/complete yapma.
- Queue mutation yapma.
- Operation lifecycle smoke çalıştırma.

## 14. Rollback stratejisi

- Birincil rollback: seed apply öncesi alınan `pg_dump` backup restore.
- Manuel seed row removal önerilmez.
- Eğer sadece seed satırları geri alınacaksa ayrı explicit destructive approval
  ve ayrı rollback SQL gerekir.
- `docker compose down -v` yok.
- Docker volume silme yok.
- Bu runbook rollback SQL üretmez.

## 15. PASS/FAIL kriterleri

PASS kriterleri:

- Backup alındı ve dosya yolu kaydedildi.
- Destructive keyword kontrolü clean.
- Runtime/event insert kontrolü clean.
- Seed apply hatasız tamamlandı.
- Items count = 3.
- Process route count = 1.
- Route operations count = 2.
- Station event sources count = 4.
- Operation steps count = 5.
- Runtime/event/flow tabloları 0 satır kaldı.
- `locations = 8`.
- `active_station_location_bindings = 8`.
- Health endpoint `ok`.
- MESQL push/pull yok.
- Operation lifecycle mutation yok.

FAIL kriterleri:

- Backup alınmadı.
- Seed apply hata verdi.
- Destructive keyword veya forbidden table match döndü.
- Runtime/event/flow tablolarına veri yazıldı.
- Beklenen seed count değerleri oluşmadı.
- Station/location baseline değişti.
- Health endpoint başarısız oldu.
- MESQL push/pull çalıştırıldı.
- Operation lifecycle mutation yapıldı.

## 16. Evidence dosyası önerisi

Future evidence dosyası:

```text
docs/runbooks/station_execution_seed_minimal_evidence_YYYYMMDD.md
```

Evidence içeriği:

- Backup path.
- Destructive keyword check.
- Runtime/event insert check.
- Seed apply result.
- Seed verify outputs.
- Expected counts.
- Runtime/event/flow table counts.
- Station/location baseline.
- Health/limited regression.
- Guardrails.
- PASS/FAIL.

## 17. Guardrails

- Bu runbook hazırlanırken seed apply yapılmaz.
- DB'ye bağlanma yok.
- `psql` çalıştırma yok.
- Docker/compose/container çalıştırma yok.
- Runtime/event/flow tablolarına seed insert yok.
- Existing lifecycle tablolarına insert/update yok.
- `mes.locations` ve `mes.station_location_bindings` yazımı yok.
- Kiosk dynamic action implementation yok.
- Runtime engine implementation yok.
- IoT adapter implementation yok.
- OEE/KPI implementation yok.
- Inventory movement/balance yok.
- MESQL push/pull yok.
- Operation start/complete lifecycle smoke yok.
- Commit/push yok.
- `.agents/` task dışı; okuma, değiştirme, silme, taşıma veya stage etme yok.
