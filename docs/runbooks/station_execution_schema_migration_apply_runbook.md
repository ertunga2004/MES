# Station Execution Schema Migration Apply Runbook

## 1. Amaç

Bu runbook, `db/migrations/004_station_execution_schema.sql` migration dosyasını ileride lokal PostgreSQL üzerinde güvenli şekilde manuel uygulamak ve doğrulamak için operasyon taslağıdır.

Bu doküman migration'ı uygulamaz. Uygulama öncesinde backup alınmasını, destructive SQL kontrolü yapılmasını, sadece schema/table/index/constraint varlığının doğrulanmasını ve mevcut lifecycle, station-location API ve Kiosk read-only davranışlarının bozulmadığının kontrol edilmesini tarif eder.

Bu runbook seed, runtime engine, Kiosk dynamic action, IoT/MQTT adapter, OEE/KPI veya inventory movement başlatmaz.

## 2. Kapsam

Kapsam yalnızca şu dosyadır:

```text
db/migrations/004_station_execution_schema.sql
```

Beklenen yeni schema tabloları:

- `mes.items`
- `mes.process_routes`
- `mes.route_operations`
- `mes.operation_steps`
- `mes.station_event_sources`
- `mes.work_order_operation_execution_state`
- `mes.work_order_operation_steps`
- `mes.operation_events`
- `mes.operation_approvals`
- `mes.production_flow_events`

Migration additive schema migration olarak değerlendirilir. Beklenen doğrulama yüzeyi tablo, constraint ve index varlığıdır.

## 3. Kapsam Dışı

- Seed SQL apply yok.
- Manuel seed data insert yok.
- Runtime engine implementation yok.
- Kiosk dynamic action yok.
- IoT/MQTT adapter yok.
- OEE/KPI implementation yok.
- Inventory movement yok.
- Inventory balance/view yok.
- MESQL push/pull yok.
- `work_order_operations.status` mutation yok.
- `station_queue` mutation yok.
- `mes.locations` mutation yok.
- `mes.station_location_bindings` mutation yok.
- Docker volume silme yok.
- `docker compose down -v` yok.

## 4. Ön Koşullar

- Git çalışma ağacı kontrol edilmeli.
- `.agents/` görünüyorsa bu task dışıdır; okunmamalı, taşınmamalı, silinmemeli ve stage edilmemelidir.
- `db/migrations/004_station_execution_schema.sql` repo içinde mevcut olmalı.
- `db/migrations/003_add_station_locations.sql` daha önce uygulanmış olmalı.
- `mes.locations` ve `mes.station_location_bindings` tabloları mevcut olmalı.
- `mes.stations`, `mes.work_orders` ve `mes.work_order_operations` tabloları mevcut olmalı.
- `mes_postgres` container çalışıyor ve healthy olmalı.
- `mes_postgres_data` volume silinmemiş olmalı.
- `.env` commitlenmemeli.
- Migration apply öncesi PostgreSQL backup alınmalı.
- MESQL frozen kalmalı; açık onay olmadan MESQL push/pull çalıştırılmamalı.

## 5. Riskler

- Bu migration çok sayıda FK ve check constraint eklediği için baseline tabloların beklenen unique/business key yapısına bağlıdır.
- `production_flow_events.input_location_code` ve `output_location_code` alanları bilinçli olarak semantic reference olarak kalır; `mes.locations` tablosuna FK eklenmez.
- Migration seed içermediği için yeni tablolar apply sonrası boş kalmalıdır.
- Hatalı rollback amacıyla `DROP`, `TRUNCATE`, `DELETE` veya volume silme uygulanırsa lokal runtime veri kaybı oluşabilir.
- Kiosk/API regression kontrolü schema apply sonrası ayrı ve kontrollü şekilde yapılmalıdır; bu runbook test veya smoke komutlarını otomatik çalıştırmaz.

## 6. Pre-Apply Checklist

Bu komutlar migration uygulanacağı zaman çalıştırılmalıdır. Bu doküman oluşturulurken çalıştırılmamıştır.

Git durumu:

```powershell
git status --short
```

Migration dosyası var mı:

```powershell
Test-Path -LiteralPath "db\migrations\004_station_execution_schema.sql"
```

Portable servis durumu:

```powershell
docker compose -f docker\mes\compose.portable.yaml ps
```

Health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Temel tablo ön koşulları:

```powershell
@'
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'mes'
  AND table_name IN (
    'locations',
    'station_location_bindings',
    'stations',
    'work_orders',
    'work_order_operations'
  )
ORDER BY table_name;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
locations
station_location_bindings
stations
work_order_operations
work_orders
```

Station/location baseline count:

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

Beklenen lokal baseline:

```text
locations = 8
active_station_location_bindings = 8
```

## 7. Backup Planı

Backup root:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups
```

PowerShell backup komutu:

```powershell
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = "C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups"
$BackupFile = Join-Path $BackupDir "mes_postgres_before_004_station_execution_schema_$Stamp.sql"
docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > $BackupFile
Write-Output $BackupFile
```

Backup sonrası kontrol:

```powershell
Test-Path -LiteralPath $BackupFile
Get-Item -LiteralPath $BackupFile | Select-Object FullName, Length, LastWriteTime
```

Backup alınmadan migration apply yapılmamalıdır.

## 8. Destructive Keyword Kontrolü

Apply öncesi destructive keyword taraması:

```powershell
Select-String -Path "db\migrations\004_station_execution_schema.sql" -Pattern "DROP TABLE|DROP COLUMN|ALTER TABLE.*DROP|TRUNCATE|DELETE FROM|UPDATE mes\.work_order_operations|UPDATE mes\.station_queue|UPDATE mes\.locations|UPDATE mes\.station_location_bindings"
```

Beklenen sonuç:

```text
No matches
```

Match dönerse migration uygulanmamalıdır. Önce SQL içeriği ayrıca review edilmelidir.

## 9. Migration Apply Komutu Taslağı

Bu komut yalnızca açık uygulama onayı olduğunda çalıştırılmalıdır.

```powershell
Get-Content -Raw -LiteralPath "db\migrations\004_station_execution_schema.sql" |
  docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Bu form Windows host ortamındaki `$env:POSTGRES_USER`, `$env:POSTGRES_DB` ve `$env:POSTGRES_PASSWORD` değerlerine bağımlı değildir. Değerler `mes_postgres` container içindeki env değerlerinden okunur.

Apply sırasında:

- MESQL push/pull çalıştırma.
- Seed SQL çalıştırma.
- Docker volume silme.
- `docker compose down -v` çalıştırma.
- `.env` dosyasını stage veya commit etme.

## 10. Schema Verify Sorguları

Yeni tablolar:

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
    'production_flow_events'
  )
ORDER BY table_name;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç: 10 satır.

Expected table list:

```text
items
operation_approvals
operation_events
operation_steps
process_routes
production_flow_events
route_operations
station_event_sources
work_order_operation_execution_state
work_order_operation_steps
```

## 11. Constraint/Index Verify Sorguları

Constraint kontrolü:

```powershell
@'
SELECT conrelid::regclass AS table_name, conname, contype
FROM pg_constraint
WHERE connamespace = 'mes'::regnamespace
  AND conrelid::regclass::text IN (
    'mes.items',
    'mes.process_routes',
    'mes.route_operations',
    'mes.operation_steps',
    'mes.station_event_sources',
    'mes.work_order_operation_execution_state',
    'mes.work_order_operation_steps',
    'mes.operation_events',
    'mes.operation_approvals',
    'mes.production_flow_events'
  )
ORDER BY table_name::text, conname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Index kontrolü:

```powershell
@'
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'mes'
  AND tablename IN (
    'items',
    'process_routes',
    'route_operations',
    'operation_steps',
    'station_event_sources',
    'work_order_operation_execution_state',
    'work_order_operation_steps',
    'operation_events',
    'operation_approvals',
    'production_flow_events'
  )
ORDER BY tablename, indexname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Idempotency index kontrolü:

```powershell
@'
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'mes'
  AND tablename = 'operation_events'
  AND (
    indexdef ILIKE '%station_code%'
    OR indexdef ILIKE '%idempotency_key%'
  )
ORDER BY indexname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen idempotency indexleri:

```text
ux_mes_operation_events_idempotency_key
ux_mes_operation_events_station_source_external
```

Location FK yokluğu kontrolü:

```powershell
@'
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'mes'::regnamespace
  AND conrelid = 'mes.production_flow_events'::regclass
  AND pg_get_constraintdef(oid) ILIKE '%locations%';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
0 rows
```

`input_location_code` ve `output_location_code` semantic reference olarak kalır. Bu migration mevcut `mes.locations` tablosunu değiştirmez.

## 12. No-Seed/No-Data-Mutation Kontrolü

Yeni tablolar apply sonrası boş olmalıdır:

```powershell
@'
SELECT 'items' AS table_name, count(*) AS row_count FROM mes.items
UNION ALL
SELECT 'process_routes', count(*) FROM mes.process_routes
UNION ALL
SELECT 'route_operations', count(*) FROM mes.route_operations
UNION ALL
SELECT 'operation_steps', count(*) FROM mes.operation_steps
UNION ALL
SELECT 'station_event_sources', count(*) FROM mes.station_event_sources
UNION ALL
SELECT 'work_order_operation_execution_state', count(*) FROM mes.work_order_operation_execution_state
UNION ALL
SELECT 'work_order_operation_steps', count(*) FROM mes.work_order_operation_steps
UNION ALL
SELECT 'operation_events', count(*) FROM mes.operation_events
UNION ALL
SELECT 'operation_approvals', count(*) FROM mes.operation_approvals
UNION ALL
SELECT 'production_flow_events', count(*) FROM mes.production_flow_events
ORDER BY table_name;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
Her tablo için row_count = 0
```

Station/location baseline tekrar kontrol:

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

Beklenen lokal baseline değişmemeli:

```text
locations = 8
active_station_location_bindings = 8
```

## 13. Health/Regression Smoke Planı

Bu bölüm migration apply sonrası ayrı doğrulama planıdır. Bu doküman oluşturulurken çalıştırılmamıştır.

Minimum health:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Station/location read-only API kontrol planı:

- Feature flag kapalı/default durumda mevcut endpoint davranışı korunmalı.
- Feature flag açık context endpoint kontrolü ayrıca yapılmalı.
- Station/location API sadece read-only kalmalı.

Kiosk read-only card kontrol planı:

- Kiosk sayfası yüklenmeli.
- Station/location read-only kartı mevcut görsel düzeni bozmamalı.
- Kart yeni execution schema tablolarına write yapmamalı.

Lifecycle regression planı:

- Local successor activation smoke sadece ayrı açık onayla çalıştırılmalı.
- Operation start/complete testleri ayrı açık onay olmadan çalıştırılmamalı.
- `work_order_operations.status` ve `station_queue` mutation'ı bu migration apply runbook kapsamında yapılmamalı.

## 14. Rollback Stratejisi

Birincil rollback yöntemi apply öncesi alınan `pg_dump` backup dosyasından restore etmektir.

Yasaklı veya ayrı açık destructive onay gerektiren işlemler:

- `docker compose down -v`
- `docker volume rm`
- `mes_postgres_data` volume silme
- `DROP TABLE`
- `TRUNCATE`
- `DELETE`

Bu runbook rollback migration üretmez. Yeni tabloları drop etmek production-like ortam için önerilmez; böyle bir ihtiyaç doğarsa ayrı rollback planı ve açık destructive onay gerekir.

## 15. PASS/FAIL Kriterleri

PASS kriterleri:

- Backup alındı ve dosya yolu kaydedildi.
- Destructive keyword kontrolü match döndürmedi.
- Migration apply hatasız tamamlandı.
- 10 yeni tablo mevcut.
- Constraint ve index kontrolü beklenen tabloları kapsıyor.
- `operation_events` idempotency indexleri mevcut.
- `production_flow_events` -> `locations` FK kontrolü 0 satır döndürüyor.
- Yeni tabloların tamamı boş.
- `locations = 8` ve `active_station_location_bindings = 8` baseline'ı değişmedi.
- Health endpoint `ok` döndü.
- MESQL push/pull çalıştırılmadı.
- Lifecycle mutation yapılmadı.

FAIL kriterleri:

- Backup alınmadı.
- Migration apply hata verdi.
- Beklenen 10 tablodan biri eksik.
- Destructive keyword kontrolü match döndürdü.
- `production_flow_events` üzerinde `locations` FK bulundu.
- Yeni tablolarda beklenmeyen seed/data oluştu.
- `mes.locations` veya `mes.station_location_bindings` count değişti.
- Health endpoint başarısız oldu.
- MESQL push/pull çalıştırıldı.
- `work_order_operations` veya `station_queue` lifecycle mutation yapıldı.

## 16. Evidence Dosyası Önerisi

Uygulama sonrası evidence dosyası önerisi:

```text
docs/runbooks/station_execution_schema_migration_evidence_YYYYMMDD.md
```

Evidence içinde şu bilgiler kaydedilmelidir:

- Apply tarihi ve saat dilimi.
- Uygulanan dosya: `db/migrations/004_station_execution_schema.sql`
- Backup dosya yolu.
- `git status --short` çıktısı.
- Destructive keyword kontrol sonucu.
- Apply komutu ve sonucu.
- 10 tablo verify çıktısı.
- Constraint verify özeti.
- Index verify özeti.
- Idempotency index verify çıktısı.
- Location FK yokluğu çıktısı.
- No-seed/no-data-mutation count çıktısı.
- Station/location baseline count çıktısı.
- Health after sonucu.
- Regression smoke sonucu veya neden çalıştırılmadığı.
- Guardrail uyum notları.

## 17. Guardrails

Bu runbook hazırlanırken ve uygulanırken şu guardrail'ler korunmalıdır:

- DB'ye açık uygulama onayı olmadan bağlanma yok.
- `psql` açık uygulama onayı olmadan çalıştırma yok.
- Docker container başlatma/durdurma yok.
- `docker compose down -v` yok.
- Docker volume silme yok.
- MESQL push/pull yok.
- Seed SQL apply yok.
- Runtime data mutation yok.
- Python/API/CMD/compose/Dockerfile değişikliği yok.
- `.env` dosyasına dokunma yok.
- `.agents/` task dışı; okuma, değiştirme, silme, taşıma veya stage etme yok.
- Commit/push yok.
