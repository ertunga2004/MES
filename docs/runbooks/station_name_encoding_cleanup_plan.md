# PACKAGING_01 Station Name Encoding Cleanup Plan

## 1. Amaç

Bu doküman, `PACKAGING_01` station_name encoding/karakter bozulmasını kontrollü şekilde düzeltmek için data quality cleanup planıdır.

Bu doküman doğrudan uygulama yapmaz. DB bağlantısı, `psql`, `UPDATE`, Docker/compose/container komutu veya test çalıştırma bu turda yapılmamıştır.

## 2. Kapsam

- Sadece `mes.stations` tablosu.
- Sadece `station_code = 'PACKAGING_01'` kaydı.
- Sadece `station_name` alanı.
- Hedef değer: `İstasyon 2 - Paketleme`

Mevcut evidence:

```text
PACKAGING_01:
- station_name: ??stasyon 2 - Paketleme
- active: true
```

Hedef:

```text
PACKAGING_01:
- station_name: İstasyon 2 - Paketleme
- active: true
```

## 3. Kapsam Dışı

- `mes.locations` değişmeyecek.
- `mes.station_location_bindings` değişmeyecek.
- Work order / operation / `station_queue` değişmeyecek.
- SQL migration dosyaları değişmeyecek.
- Python/API değişmeyecek.
- Docker/compose değişmeyecek.
- MESQL push/pull yok.
- Runtime volume silme yok.
- Toplu master data cleanup yok.
- `ASSEMBLY_01` kaydı değişmeyecek.

## 4. Risk Notu: Encoding

Türkçe `İ` karakteri PowerShell 5.1, terminal encoding veya dosya encoding nedeniyle tekrar bozulabilir.

Bu yüzden düzeltme komutu doğrudan terminale rastgele yapıştırılmamalıdır. Tercih edilen yöntem UTF-8 encoding korunarak SQL here-string veya geçici UTF-8 SQL dosyası ile uygulanmalıdır.

Komut çalıştırılmadan önce output terminalinde hedef değer görsel olarak kontrol edilmelidir.

Daha güvenli alternatif olarak PostgreSQL Unicode escape literal kullanılabilir:

```sql
U&'\0130stasyon 2 - Paketleme'
```

Bu ifade `İstasyon 2 - Paketleme` değerini temsil eder ve terminalin `İ` karakterini bozma riskini azaltır. Yine de apply öncesi ve sonrası görsel doğrulama yapılmalıdır.

## 5. Ön Koşullar

- Git çalışma ağacı temiz olmalı.
- `mes_postgres` healthy olmalı.
- Health endpoint `ok` dönmeli.
- Backup alınmalı.
- MESQL frozen kalmalı.
- `mes_postgres_data` volume silinmemeli.
- Cleanup sadece açık onay sonrası uygulanmalı.
- Mevcut `PACKAGING_01` değeri apply öncesi kaydedilmeli.

## 6. Pre-Check Komutları

Bu komutlar cleanup uygulanacağı zaman çalıştırılmalıdır. Bu doküman oluşturulurken çalıştırılmamıştır.

Git status:

```powershell
git status --short
```

Portable servis durumu:

```powershell
docker compose -f docker\mes\compose.portable.yaml ps
```

Health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

Code marker:

```powershell
docker exec mes_web python -c "from mes_web.db import mesql_v2; sql=getattr(mesql_v2,'SELECT_SUCCESSOR_OPERATION_SQL',''); print('has_successor_sql', bool(sql)); print('orders_by_sequence_operation', 'ORDER BY sequence_no ASC, operation_no ASC' in sql); print('skips_terminal', 'status NOT IN' in sql)"
```

Mevcut station değerini oku:

```powershell
@'
SELECT station_code, station_name, active, updated_at
FROM mes.stations
WHERE station_code = 'PACKAGING_01';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

`PACKAGING_01` tekil mi:

```powershell
@'
SELECT count(*) AS packaging_station_count
FROM mes.stations
WHERE station_code = 'PACKAGING_01';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
packaging_station_count = 1
```

Hedef değeri görsel ve byte seviyesinde doğrulamak için hazırlık sorgusu:

```powershell
@'
SELECT
  U&'\0130stasyon 2 - Paketleme' AS target_station_name,
  encode(convert_to(U&'\0130stasyon 2 - Paketleme', 'UTF8'), 'hex') AS target_utf8_hex;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen hedef değer:

```text
target_station_name = İstasyon 2 - Paketleme
```

Beklenen UTF-8 hex başlangıcı:

```text
c4b0
```

## 7. Backup

Cleanup öncesi PostgreSQL backup alınmalıdır.

```cmd
docker\mes\launchers\maintenance\backup_mes_db.cmd
```

Backup hedefi:

```text
<portable-runtime-root>\data\db_backups
```

Backup raporunda dosya yolu kaydedilmelidir. Backup alınmadan `UPDATE` yapılmamalıdır.

## 8. Dry-Run SQL

Cleanup önce dry-run ile doğrulanmalıdır. Dry-run hiçbir satırı değiştirmez.

Dry-run guard koşulları:

- `station_code = 'PACKAGING_01'`
- `active = true`
- mevcut `station_name = '??stasyon 2 - Paketleme'`
- hedef değer `U&'\0130stasyon 2 - Paketleme'`

```powershell
@'
WITH candidate AS (
  SELECT
    station_code,
    station_name AS previous_station_name,
    U&'\0130stasyon 2 - Paketleme' AS target_station_name,
    active,
    updated_at
  FROM mes.stations
  WHERE station_code = 'PACKAGING_01'
    AND active = true
    AND station_name = '??stasyon 2 - Paketleme'
)
SELECT
  count(*) AS candidate_count,
  max(station_code) AS station_code,
  max(previous_station_name) AS previous_station_name,
  max(target_station_name) AS target_station_name,
  bool_and(active) AS active
FROM candidate;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
candidate_count = 1
previous_station_name = ??stasyon 2 - Paketleme
target_station_name = İstasyon 2 - Paketleme
active = true
```

Eğer `candidate_count` 1 değilse apply yapılmamalıdır. Önce mevcut değer yeniden okunmalı, encoding çıktısı incelenmeli ve plan güncellenmelidir.

## 9. Apply SQL

Bu işlem yalnız dry-run sonucu `candidate_count = 1` görüldükten ve açık onay alındıktan sonra uygulanmalıdır.

Tercih edilen güvenli form, transaction içinde hedef değeri PostgreSQL Unicode escape literal ile yazmaktır:

```powershell
@'
BEGIN;

WITH locked_candidate AS (
  SELECT
    station_pk,
    station_code,
    station_name AS previous_station_name,
    active
  FROM mes.stations
  WHERE station_code = 'PACKAGING_01'
    AND active = true
    AND station_name = '??stasyon 2 - Paketleme'
  FOR UPDATE
),
candidate_count AS (
  SELECT count(*) AS row_count
  FROM locked_candidate
),
updated AS (
  UPDATE mes.stations station
  SET
    station_name = U&'\0130stasyon 2 - Paketleme',
    updated_at = now(),
    metadata = COALESCE(station.metadata, '{}'::jsonb) || jsonb_build_object(
      'station_name_encoding_cleanup',
      jsonb_build_object(
        'applied_at',
        now(),
        'previous_station_name',
        locked_candidate.previous_station_name,
        'target',
        U&'\0130stasyon 2 - Paketleme',
        'reason',
        'fix existing PACKAGING_01 station_name encoding issue observed after Paket A migration evidence'
      )
    )
  FROM locked_candidate
  WHERE station.station_pk = locked_candidate.station_pk
    AND (SELECT row_count FROM candidate_count) = 1
  RETURNING
    station.station_code,
    locked_candidate.previous_station_name,
    station.station_name AS station_name_after,
    station.active,
    station.updated_at
)
SELECT
  (SELECT row_count FROM candidate_count) AS candidate_count,
  updated.station_code,
  updated.previous_station_name,
  updated.station_name_after,
  updated.active,
  updated.updated_at
FROM updated;

COMMIT;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Notlar:

- Guard koşulu `station_code`, `active=true` ve gözlenen eski `station_name` değerini birlikte arar.
- `candidate_count = 1` değilse `UPDATE` satır döndürmemelidir; bu durumda apply başarısız kabul edilmeli ve manuel inceleme yapılmalıdır.
- `previous_station_name` metadata içine kaydedilir.
- Apply çıktısı görsel olarak kontrol edilmelidir.
- `metadata` alanına cleanup evidence notu eklenir; bu migration dosyası değişikliği değildir.

## 10. Geçici UTF-8 SQL Dosyası Alternatifi

PowerShell 7+ kullanılıyorsa geçici UTF-8 SQL dosyası hazırlanabilir. Dosya repo içine değil geçici klasöre yazılmalıdır.

```powershell
$sqlPath = Join-Path $env:TEMP "packaging_01_station_name_cleanup.sql"
@'
BEGIN;

WITH locked_candidate AS (
  SELECT
    station_pk,
    station_code,
    station_name AS previous_station_name,
    active
  FROM mes.stations
  WHERE station_code = 'PACKAGING_01'
    AND active = true
    AND station_name = '??stasyon 2 - Paketleme'
  FOR UPDATE
),
candidate_count AS (
  SELECT count(*) AS row_count
  FROM locked_candidate
),
updated AS (
  UPDATE mes.stations station
  SET
    station_name = U&'\0130stasyon 2 - Paketleme',
    updated_at = now(),
    metadata = COALESCE(station.metadata, '{}'::jsonb) || jsonb_build_object(
      'station_name_encoding_cleanup',
      jsonb_build_object(
        'applied_at',
        now(),
        'previous_station_name',
        locked_candidate.previous_station_name,
        'target',
        U&'\0130stasyon 2 - Paketleme',
        'reason',
        'fix existing PACKAGING_01 station_name encoding issue observed after Paket A migration evidence'
      )
    )
  FROM locked_candidate
  WHERE station.station_pk = locked_candidate.station_pk
    AND (SELECT row_count FROM candidate_count) = 1
  RETURNING
    station.station_code,
    locked_candidate.previous_station_name,
    station.station_name AS station_name_after,
    station.active,
    station.updated_at
)
SELECT
  (SELECT row_count FROM candidate_count) AS candidate_count,
  updated.station_code,
  updated.previous_station_name,
  updated.station_name_after,
  updated.active,
  updated.updated_at
FROM updated;

COMMIT;
'@ | Set-Content -LiteralPath $sqlPath -Encoding utf8

Get-Content -Raw -LiteralPath $sqlPath |
  docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

PowerShell 5.1 kullanılıyorsa `Set-Content -Encoding utf8` BOM davranışı nedeniyle dikkatli olunmalıdır. Şüphe varsa here-string stdin yöntemi ve `U&'\0130...'` literal tercih edilmelidir.

## 11. Post-Check Komutları

Cleanup sonrası station değeri:

```powershell
@'
SELECT station_code, station_name, active, updated_at
FROM mes.stations
WHERE station_code = 'PACKAGING_01';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Byte-level doğrulama:

```powershell
@'
SELECT
  station_code,
  station_name,
  encode(convert_to(station_name, 'UTF8'), 'hex') AS station_name_utf8_hex
FROM mes.stations
WHERE station_code = 'PACKAGING_01';
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen görsel sonuç:

```text
PACKAGING_01 | İstasyon 2 - Paketleme | true
```

Beklenen UTF-8 hex başlangıcı:

```text
c4b0
```

Station/location binding etkilenmedi mi:

```powershell
@'
SELECT count(*) AS active_binding_count
FROM mes.station_location_bindings
WHERE station_code = 'PACKAGING_01'
  AND active = true;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen sonuç:

```text
active_binding_count = 4
```

Location count etkilenmedi mi:

```powershell
@'
SELECT count(*) AS location_count
FROM mes.locations;
'@ | docker exec -i mes_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Beklenen minimum sonuç:

```text
location_count >= 8
```

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

## 12. Regression Kontrolü

Cleanup sadece `mes.stations.station_name` alanını değiştirdiği için operation lifecycle davranışını değiştirmemelidir.

Yine de aşağıdaki referans smoke korunmalıdır:

```text
docs/runbooks/local_successor_activation_smoke.md
```

Beklenen davranış:

```text
ASSEMBLY_01 op10 complete
-> PACKAGING_01 op20 queued
-> repeated op10 complete duplicate queue oluşturmadı
-> PACKAGING_01 op20 complete
-> work_order completed
```

Smoke bu cleanup ile aynı oturumda çalıştırılacaksa önce kullanıcıdan açık onay alınmalıdır.

## 13. Rollback Planı

Tercih edilen rollback, transaction içinde apply sırasında hatalı değer görülürse `COMMIT` yerine `ROLLBACK` kullanmaktır.

Eğer commit sonrası rollback gerekirse:

1. Backup dosyası ve apply raporu incelenir.
2. Cleanup öncesi kaydedilen `previous_station_name` değeri doğrulanır.
3. Yeni bir açık onay alınır.
4. Sadece `PACKAGING_01.station_name` için kontrollü düzeltme yapılır.

Genel rollback için yapılmaması gerekenler:

- `DROP`
- `TRUNCATE`
- `DELETE`
- `docker compose down -v`
- `docker volume rm`
- `mes_postgres_data` silme
- MESQL push/pull ile geri alma

## 14. Kabul Kriterleri

- `PACKAGING_01 station_name` hedef değer olarak `İstasyon 2 - Paketleme` olmalı.
- `PACKAGING_01 active` değeri `true` kalmalı.
- Dry-run `candidate_count = 1` göstermiş olmalı.
- Apply output `previous_station_name` ve `station_name_after` alanlarını göstermeli.
- Metadata içinde `previous_station_name` kaydı oluşmalı.
- `mes.locations` değişmemeli.
- `mes.station_location_bindings` değişmemeli.
- `PACKAGING_01` active binding count `4` kalmalı.
- `location_count >= 8` kalmalı.
- Health endpoint `ok` dönmeli.
- MESQL push/pull çalıştırılmamış olmalı.
- Docker volume silinmemiş olmalı.
- SQL migration dosyaları değiştirilmemiş olmalı.
- Python/API/CMD/compose/Dockerfile değiştirilmemiş olmalı.

## 15. Operasyon Sonrası Rapor Formatı

```text
Cleanup:
- Target row: mes.stations station_code=PACKAGING_01
- Field: station_name
- Old value:
- New value: İstasyon 2 - Paketleme
- Applied at:

Pre-check:
- git status:
- health:
- backup path:
- current station_name:
- packaging_station_count:

Dry-run:
- candidate_count:
- previous_station_name:
- target_station_name:

Apply:
- SQL method: here-string / UTF-8 temp SQL file
- UPDATE row count:
- RETURNING output:
- metadata previous_station_name:

Verification:
- station_name visual check:
- station_name UTF-8 hex prefix:
- active_binding_count:
- location_count:
- health after:

Guardrails:
- MESQL push/pull run: no
- Docker volume delete: no
- docker compose down -v: no
- SQL migration changed: no
- Python/API/CMD/compose/Dockerfile changed: no
- .env touched: no
```
