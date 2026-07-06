# Station/Location Paket A Migration Uygulama Runbook'u

## 1. Amaç

Bu runbook, `db/migrations/003_add_station_locations.sql` migration dosyasını ileride güvenli şekilde manuel uygulamak, doğrulamak ve regression kontrolü yapmak için operasyon rehberidir.

Bu migration Paket A/static master data kapsamındadır. `mes.locations`, `mes.station_location_bindings`, minimum station seed, minimum location seed ve station-location binding seed verisini ekler.

Bu migration inventory movement, inventory balance veya sensor event link oluşturmaz.

## 2. Kapsam

- `mes.locations`
- `mes.station_location_bindings`
- `ASSEMBLY_01` / `PACKAGING_01` station seed
- Minimum location seed:
  - `RAW_MATERIAL`
  - `ASSEMBLY_WIP`
  - `BETWEEN_ASSEMBLY_PACKAGING`
  - `PACKAGING_WIP`
  - `FINISHED_GOODS`
  - `SCRAP_AREA`
  - `HOLD_AREA`
  - `REWORK_AREA`
- Station-location binding seed:
  - `ASSEMBLY_01 input -> RAW_MATERIAL`
  - `ASSEMBLY_01 active_wip -> ASSEMBLY_WIP`
  - `ASSEMBLY_01 output_good -> BETWEEN_ASSEMBLY_PACKAGING`
  - `ASSEMBLY_01 output_buffer -> BETWEEN_ASSEMBLY_PACKAGING`
  - `PACKAGING_01 input -> BETWEEN_ASSEMBLY_PACKAGING`
  - `PACKAGING_01 active_wip -> PACKAGING_WIP`
  - `PACKAGING_01 output_good -> FINISHED_GOODS`
  - `PACKAGING_01 output_scrap -> SCRAP_AREA`

## 3. Kapsam Dışı

- MESQL push/pull yok.
- Python/API değişikliği yok.
- Docker image rebuild yok.
- Compose değişikliği yok.
- Inventory movement yok.
- Balance view yok.
- Sensor event link yok.
- Full WMS yok.
- `docker compose down -v` yok.
- Docker volume silme yok.

## 4. Ön Koşullar

- `mes_postgres` container çalışıyor olmalı.
- `mes_postgres` healthy olmalı.
- `mes_postgres_data` volume silinmemiş olmalı.
- `001_initial_mes_schema.sql` daha önce uygulanmış olmalı.
- `002_unique_external_refs.sql` mevcut migration sırası içinde yer alıyor olmalı.
- `003_add_station_locations.sql` repo içinde mevcut olmalı.
- `.env` commitlenmemeli.
- MESQL frozen kalmalı; açık onay olmadan MESQL push/pull çalıştırılmamalı.
- Uygulama öncesi PostgreSQL backup alınması önerilir.

## 5. Başlangıç Güvenlik Kontrolleri

Bu komutlar migration uygulanacağı zaman çalıştırılmalıdır. Bu doküman oluşturulurken çalıştırılmamıştır.

Git çalışma ağacı:

```powershell
git status --short
```

Migration dosyası var mı:

```powershell
Test-Path -LiteralPath "db\migrations\003_add_station_locations.sql"
```

Destructive SQL taraması:

```powershell
Select-String -Path "db\migrations\003_add_station_locations.sql" -Pattern "\b(DROP|TRUNCATE|DELETE)\b"
```

Statik diff kontrolü:

```powershell
git diff --check -- db/migrations/003_add_station_locations.sql
```

Portable servis durumu:

```powershell
docker compose -f docker\mes\compose.portable.yaml ps
```

Health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Container code version marker:

```powershell
docker exec mes_web python -c "from mes_web.db import mesql_v2; sql=getattr(mesql_v2,'SELECT_SUCCESSOR_OPERATION_SQL',''); print('has_successor_sql', bool(sql)); print('orders_by_sequence_operation', 'ORDER BY sequence_no ASC, operation_no ASC' in sql); print('skips_terminal', 'status NOT IN' in sql)"
```

Expected marker output:

```text
has_successor_sql True
orders_by_sequence_operation True
skips_terminal True
```

## 6. Backup Önerisi

Migration additive olsa da uygulama öncesi PostgreSQL backup alınmalıdır. Mevcut bakım launcher'ı kullanılabilir:

```cmd
docker\mes\launchers\maintenance\backup_mes_db.cmd
```

Backup hedefi:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups
```

Bu backup PostgreSQL içindir. JSON, Excel, FERP veya diğer runtime file flow'larını değiştirmez.

## 7. Uygulama Komutu

Migration manuel uygulanır. MES Web startup bunu otomatik çalıştırmaz.

PowerShell ile dosyayı container içindeki `psql` sürecine aktararak uygulama örneği:

```powershell
Get-Content -Raw -LiteralPath "db\migrations\003_add_station_locations.sql" |
  docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Bu form Windows host ortamında `POSTGRES_USER`, `POSTGRES_DB` veya `POSTGRES_PASSWORD` tanımlı olmasını gerektirmez. Değerler `mes_postgres` container içindeki env değişkenlerinden okunur.

CMD alternatifi:

```cmd
type db\migrations\003_add_station_locations.sql | docker exec -i mes_postgres sh -lc "PGPASSWORD=""$POSTGRES_PASSWORD"" psql -U ""$POSTGRES_USER"" -d ""$POSTGRES_DB"" -v ON_ERROR_STOP=1"
```

Uygulama sırasında:

- MESQL push/pull çalıştırma.
- Docker volume silme.
- `docker compose down -v` çalıştırma.
- `.env` dosyasını commit'e ekleme.

## 8. Uygulama Sonrası Yapısal Doğrulama

Tablolar oluştu mu:

```powershell
@'
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'mes'
  AND tablename IN ('locations', 'station_location_bindings')
ORDER BY tablename;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Indexler var mı:

```powershell
@'
SELECT indexname
FROM pg_indexes
WHERE schemaname = 'mes'
  AND tablename IN ('locations', 'station_location_bindings')
  AND indexname IN (
    'ux_mes_locations_location_code',
    'ix_mes_locations_location_type_active',
    'ix_mes_locations_station_code',
    'ux_mes_station_location_bindings_active_scope',
    'ix_mes_station_location_bindings_station_role',
    'ix_mes_station_location_bindings_location_code'
  )
ORDER BY indexname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Check constraint'ler var mı:

```powershell
@'
SELECT conname
FROM pg_constraint
WHERE conrelid IN ('mes.locations'::regclass, 'mes.station_location_bindings'::regclass)
  AND conname IN (
    'ck_mes_locations_location_type',
    'ck_mes_station_location_bindings_role'
  )
ORDER BY conname;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

## 9. Seed Doğrulama

Station seed kontrolü:

```powershell
@'
SELECT station_code, station_name, line_id, active
FROM mes.stations
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
ORDER BY station_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen station count:

```powershell
@'
SELECT count(*) AS station_count
FROM mes.stations
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01');
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
station_count = 2
```

Location seed kontrolü:

```powershell
@'
SELECT location_code, location_type, station_code, active
FROM mes.locations
WHERE location_code IN (
  'RAW_MATERIAL',
  'ASSEMBLY_WIP',
  'BETWEEN_ASSEMBLY_PACKAGING',
  'PACKAGING_WIP',
  'FINISHED_GOODS',
  'SCRAP_AREA',
  'HOLD_AREA',
  'REWORK_AREA'
)
ORDER BY location_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen location count:

```powershell
@'
SELECT count(*) AS location_count
FROM mes.locations
WHERE location_code IN (
  'RAW_MATERIAL',
  'ASSEMBLY_WIP',
  'BETWEEN_ASSEMBLY_PACKAGING',
  'PACKAGING_WIP',
  'FINISHED_GOODS',
  'SCRAP_AREA',
  'HOLD_AREA',
  'REWORK_AREA'
);
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
location_count = 8
```

Opsiyonel location active kontrolü:

```powershell
@'
SELECT location_code, active
FROM mes.locations
WHERE location_code IN ('HOLD_AREA', 'REWORK_AREA')
ORDER BY location_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
HOLD_AREA   false
REWORK_AREA false
```

Binding seed kontrolü:

```powershell
@'
SELECT station_code, role, location_code, active
FROM mes.station_location_bindings
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
ORDER BY station_code, role, location_code;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen active binding count:

```powershell
@'
SELECT count(*) AS active_binding_count
FROM mes.station_location_bindings
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
  AND active = true;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
active_binding_count = 8
```

## 10. Idempotency Doğrulama

Migration tekrar çalıştırıldığında duplicate üretmemelidir. Güvenli doğrulama yöntemi:

1. İlk uygulama sonrası seed count değerlerini kaydet.
2. Aynı migration dosyasını ikinci kez uygula.
3. Aşağıdaki duplicate kontrollerini çalıştır.

Duplicate location var mı:

```powershell
@'
SELECT location_code, count(*) AS row_count
FROM mes.locations
GROUP BY location_code
HAVING count(*) > 1;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç: satır dönmemeli.

Duplicate active binding var mı:

```powershell
@'
SELECT
  station_code,
  role,
  location_code,
  COALESCE(item_scope, '') AS item_scope_key,
  COALESCE(operation_scope, '') AS operation_scope_key,
  count(*) AS row_count
FROM mes.station_location_bindings
WHERE active = true
GROUP BY
  station_code,
  role,
  location_code,
  COALESCE(item_scope, ''),
  COALESCE(operation_scope, '')
HAVING count(*) > 1;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç: satır dönmemeli.

## 11. Regression Kontrolü

Migration uygulandıktan sonra mevcut local execution davranışı etkilenmemelidir.

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Container code version:

```powershell
docker exec mes_web python -c "from mes_web.db import mesql_v2; sql=getattr(mesql_v2,'SELECT_SUCCESSOR_OPERATION_SQL',''); print('has_successor_sql', bool(sql)); print('orders_by_sequence_operation', 'ORDER BY sequence_no ASC, operation_no ASC' in sql); print('skips_terminal', 'status NOT IN' in sql)"
```

Local successor activation smoke referansı:

```text
docs/runbooks/local_successor_activation_smoke.md
```

Beklenen regression sonucu:

```text
ASSEMBLY_01 op10 complete
-> PACKAGING_01 op20 queued
-> repeated op10 complete duplicate queue oluşturmadı
-> PACKAGING_01 op20 complete
-> work_order completed
```

Bu migration operation lifecycle kodunu değiştirmediği için smoke başarısız olursa önce migration dışı servis, code version, DB bağlantısı ve mevcut operation verisi incelenmelidir.

## 12. Rollback / Geri Alma Notu

Bu migration additive olduğu için normal rollback yaklaşımı yeni tabloları kullanmamak ve ileride eklenecek feature flag/read path davranışlarını kapatmaktır.

Bu runbook kapsamında önerilmeyen rollback işlemleri:

- `DROP TABLE`
- `DELETE`
- `TRUNCATE`
- `docker compose down -v`
- `docker volume rm`
- `mes_postgres_data` silme
- MESQL push/pull ile geri alma

Bu migration henüz runtime read/write path'e bağlanmadığı sürece existing endpointler `mes.locations` veya `mes.station_location_bindings` tablolarını kullanmadan çalışmaya devam etmelidir.

## 13. Başarılı Uygulama Kabul Kriterleri

- `mes.locations` tablosu oluşmuş olmalı.
- `mes.station_location_bindings` tablosu oluşmuş olmalı.
- İlgili index ve check constraint'ler oluşmuş olmalı.
- `ASSEMBLY_01` ve `PACKAGING_01` station kayıtları mevcut olmalı.
- 8 location kaydı mevcut olmalı.
- `HOLD_AREA` ve `REWORK_AREA` `active=false` olmalı.
- 8 active station-location binding mevcut olmalı.
- Migration ikinci kez uygulandığında duplicate location veya active binding oluşmamalı.
- Health endpoint `ok` dönmeli.
- Existing local successor activation smoke hâlâ geçmeli.
- MESQL push/pull çalıştırılmamış olmalı.
- Docker volume silinmemiş olmalı.

## 14. Operasyon Sonrası Rapor Formatı

Uygulama tamamlanınca şu formatta raporlanmalıdır:

```text
Migration:
- Applied file: db/migrations/003_add_station_locations.sql
- Applied at:

Pre-check:
- git status:
- mes_postgres status:
- health:
- backup path:

Verification:
- stations count:
- locations count:
- active bindings count:
- duplicate locations:
- duplicate active bindings:
- constraints/indexes:

Regression:
- health after migration:
- code version markers:
- local successor smoke:

Guardrails:
- MESQL push/pull run: no
- Docker volume delete: no
- docker compose down -v: no
- .env committed: no
```
