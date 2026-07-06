# Station/Location Paket A Migration Evidence - 2026-07-06

## 1. Amaç

Bu doküman, `db/migrations/003_add_station_locations.sql` migration uygulama ve verification sonucunu evidence olarak kaydeder.

## 2. Uygulanan Migration

- Migration dosyası: `db/migrations/003_add_station_locations.sql`
- Kapsam: Paket A / static master data

Kapsam:

- `mes.locations`
- `mes.station_location_bindings`
- Minimum station seed
- Minimum location seed
- Station-location binding seed

Kapsam dışı:

- `inventory_movements`
- `inventory_balances`
- `sensor_event_links`
- MESQL push/pull
- Python/API değişikliği
- Docker image rebuild

## 3. Pre-Check Sonuçları

- `git status --short`: clean
- `docker compose ps`:
  - `mes_adminer` up
  - `mes_postgres` up healthy
  - `mes_web` up
- Health before:
  - `status`: ok
  - `time`: `2026-07-06T20:25:30.914+00:00`
- Code marker before:
  - `has_successor_sql True`
  - `orders_by_sequence_operation True`
  - `skips_terminal True`

## 4. Backup

Backup dosyası:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_20260706-232552.sql
```

Notlar:

- Backup migration öncesi alındı.
- `mes_postgres_data` volume silinmedi.
- `docker compose down -v` çalıştırılmadı.

## 5. Migration Apply Çıktısı

```text
NOTICE: schema "mes" already exists, skipping
CREATE SCHEMA
CREATE TABLE
CREATE INDEX
CREATE INDEX
CREATE INDEX
CREATE TABLE
CREATE INDEX
CREATE INDEX
CREATE INDEX
DO
INSERT 0 0
INSERT 0 8
INSERT 0 8
```

Yorum:

- `INSERT 0 0` station seed için beklenen davranış olabilir; `ASSEMBLY_01` ve `PACKAGING_01` zaten mevcut olduğu için duplicate üretmedi.
- `INSERT 0 8` location seed başarılı.
- `INSERT 0 8` station-location binding seed başarılı.

## 6. Table Verification

Doğrulanan tablolar:

- `mes.locations`
- `mes.station_location_bindings`

## 7. Seed Verification

- `location_count = 8`
- `active_binding_count = 8`

`HOLD_AREA` / `REWORK_AREA`:

- `HOLD_AREA active=false`
- `REWORK_AREA active=false`

## 8. Duplicate Verification

- Duplicate location query: 0 rows
- Duplicate active binding query: 0 rows

## 9. Index Verification

Şu 6 index doğrulandı:

- `ix_mes_locations_location_type_active`
- `ix_mes_locations_station_code`
- `ix_mes_station_location_bindings_location_code`
- `ix_mes_station_location_bindings_station_role`
- `ux_mes_locations_location_code`
- `ux_mes_station_location_bindings_active_scope`

## 10. Constraint Verification

Şu 2 constraint doğrulandı:

- `ck_mes_locations_location_type`
- `ck_mes_station_location_bindings_role`

## 11. Station Verification

`ASSEMBLY_01`:

- `station_name`: İstasyon 1 - Kutu Üretim
- `active`: true

`PACKAGING_01`:

- `station_name`: ??stasyon 2 - Paketleme
- `active`: true

Notlar:

- `PACKAGING_01` `station_name` alanında encoding/karakter bozulması mevcut görünüyor.
- Bu migration hatası değildir; migration mevcut station kayıtlarını update etmedi.
- Ayrı data quality cleanup konusu olarak ele alınmalıdır.
- Bu evidence kapsamında manuel `UPDATE` önerilmez.

## 12. Binding Verification

Şu 8 active binding doğrulandı:

- `ASSEMBLY_01 active_wip -> ASSEMBLY_WIP`
- `ASSEMBLY_01 input -> RAW_MATERIAL`
- `ASSEMBLY_01 output_buffer -> BETWEEN_ASSEMBLY_PACKAGING`
- `ASSEMBLY_01 output_good -> BETWEEN_ASSEMBLY_PACKAGING`
- `PACKAGING_01 active_wip -> PACKAGING_WIP`
- `PACKAGING_01 input -> BETWEEN_ASSEMBLY_PACKAGING`
- `PACKAGING_01 output_good -> FINISHED_GOODS`
- `PACKAGING_01 output_scrap -> SCRAP_AREA`

## 13. Second Apply / Idempotency Verification

İkinci kez migration apply edildi.

Çıktı özeti:

- Existing schema/table/index için expected `NOTICE` mesajları görüldü.
- `DO` block çalıştı.
- `INSERT 0 0`
- `INSERT 0 0`
- `INSERT 0 0`

Sonraki count:

- `location_count = 8`
- `active_binding_count = 8`

Yorum:

- Migration idempotent davranıyor.
- İkinci apply duplicate seed üretmedi.

## 14. Post-Check

- Health after:
  - `status`: ok
  - `time`: `2026-07-06T20:27:45.087+00:00`
- Code marker after:
  - `has_successor_sql True`
  - `orders_by_sequence_operation True`
  - `skips_terminal True`

## 15. Guardrails

- MESQL push/pull çalıştırılmadı.
- `docker compose down -v` çalıştırılmadı.
- Docker volume silinmedi.
- SQL `DROP`/`TRUNCATE`/`DELETE` uygulanmadı.
- Python/API/CMD/compose/Dockerfile değiştirilmedi.
- `.env` commitlenmedi.

## 16. Hüküm

Paket A station/location static master data migration lokal PostgreSQL üzerinde başarıyla uygulanmış ve doğrulanmıştır. Migration mevcut local successor activation kodunu değiştirmemiştir. Bir sonraki teknik adım, runtime'ın bu tabloları read-only olarak görebilmesi için DB query/helper tasarımı veya önce station_name encoding cleanup planıdır.

