# PACKAGING_01 Station Name Encoding Cleanup Evidence - 2026-07-07

## 1. Amaç

Bu doküman, `PACKAGING_01.station_name` encoding cleanup sonucunu evidence olarak kaydeder.

Cleanup lokal PostgreSQL üzerinde uygulanmıştır. Bu dokümantasyon turunda DB bağlantısı, `psql`, `UPDATE`, Docker/compose/container komutu, MESQL push/pull veya test/smoke çalıştırılmamıştır.

## 2. Cleanup Kapsamı

- Hedef tablo: `mes.stations`
- Hedef satır: `station_code = 'PACKAGING_01'`
- Hedef alan: `station_name`
- Eski değer: `??stasyon 2 - Paketleme`
- Yeni değer: `İstasyon 2 - Paketleme`
- Hedef UTF-8 hex prefix: `c4b0`

Kapsam dışı:

- `mes.locations` değişmedi.
- `mes.station_location_bindings` değişmedi.
- `work_orders`, `work_order_operations`, `station_queue` değişmedi.
- SQL migration dosyaları değişmedi.
- Python/API/CMD/compose/Dockerfile değişmedi.
- MESQL push/pull çalıştırılmadı.
- Docker volume silinmedi.

## 3. Pre-Check Sonuçları

Git status:

- `git status --short`: clean

Docker compose ps:

- `mes_adminer`: Up
- `mes_postgres`: Up, healthy
- `mes_web`: Up

Health before:

- `status`: ok
- `time`: `2026-07-06T21:28:17.000+00:00`

Code marker before:

- `has_successor_sql True`
- `orders_by_sequence_operation True`
- `skips_terminal True`

## PACKAGING_01 Uniqueness Check

```text
packaging_station_count = 1
```

Yorum:

- Cleanup tek bir `PACKAGING_01` station satırı üzerinde uygulanabilir durumda doğrulandı.
- Birden fazla `PACKAGING_01` satırı görülmedi.

## Target Encoding Check

```text
target_station_name = İstasyon 2 - Paketleme
target_utf8_hex = c4b073746173796f6e2032202d2050616b65746c656d65
```

Yorum:

- `target_utf8_hex` değeri `c4b0` ile başlıyor.
- `c4b0`, Türkçe büyük `İ` karakterinin UTF-8 byte dizisidir.

## 4. Backup

Backup dosyası:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_20260707-002848.sql
```

Notlar:

- Backup cleanup öncesi alındı.
- `mes_postgres_data` volume silinmedi.
- `docker compose down -v` çalıştırılmadı.
- MESQL push/pull çalıştırılmadı.

## 5. Current Station Row Before Cleanup

```text
station_code | station_name              | active | updated_at
PACKAGING_01 | ??stasyon 2 - Paketleme   | t      | 2026-06-12 11:30:48.799909+00
```

## 6. Dry-Run Result

```text
candidate_count = 1
station_code = PACKAGING_01
previous_station_name = ??stasyon 2 - Paketleme
target_station_name = İstasyon 2 - Paketleme
active = true
```

Yorum:

- Dry-run sonucu cleanup için tam olarak 1 aday satır olduğunu doğruladı.
- Guard koşulu `station_code = 'PACKAGING_01'`, `active = true` ve mevcut bozuk `station_name` değerine göre çalıştı.
- Dry-run herhangi bir satır değiştirmedi.

## 7. Cleanup Apply Result

Cleanup işlemi yalnız `mes.stations` tablosunda `PACKAGING_01` satırının `station_name` alanını hedef değere taşımıştır.

Apply result:

```text
candidate_count = 1
station_code = PACKAGING_01
previous_station_name = ??stasyon 2 - Paketleme
station_name_after = İstasyon 2 - Paketleme
active = true
updated_at = 2026-07-06 21:29:18.233041+00
```

DB timestamp UTC olarak döndü:

```text
2026-07-06 21:29:18.233041+00
```

Bu zaman, Europe/Istanbul yerel saatinde 2026-07-07 00:29 civarına karşılık gelir. Bu yüzden evidence dosya adında yerel tarih olarak `20260707` kullanılmıştır.

Metadata evidence:

```text
previous_station_name = ??stasyon 2 - Paketleme
target = İstasyon 2 - Paketleme
```

## 8. Current Station Row After Cleanup

Beklenen ve kaydedilen sonuç:

```text
station_code | station_name             | active | updated_at
PACKAGING_01 | İstasyon 2 - Paketleme   | t      | 2026-07-06 21:29:18.233041+00
```

## 9. Encoding Verification

- Görsel hedef değer doğrulandı: `İstasyon 2 - Paketleme`
- UTF-8 hex prefix doğrulama hedefi: `c4b0`
- Full `station_name_utf8_hex`: `c4b073746173796f6e2032202d2050616b65746c656d65`

`c4b0`, Türkçe büyük `İ` karakterinin UTF-8 başlangıç byte dizisidir.

## 10. Related Data Verification

Station/location binding:

```text
active_binding_count = 4
```

Location count:

```text
location_count = 8
```

Yorum:

- `PACKAGING_01` active binding sayısı değişmedi.
- Paket A ile oluşturulan 8 location kaydı korunuyor.

## 11. Post-Check

Health after:

```text
status = ok
```

Code marker after:

```text
has_successor_sql True
orders_by_sequence_operation True
skips_terminal True
```

## 12. Guardrails

- DB evidence bu dokümana sonradan kaydedildi; bu dokümantasyon turunda DB’ye bağlanılmadı.
- `psql` çalıştırılmadı.
- `UPDATE` çalıştırılmadı.
- Docker/compose/container çalıştırılmadı.
- MESQL push/pull çalıştırılmadı.
- Docker volume silinmedi.
- `docker compose down -v` çalıştırılmadı.
- SQL migration dosyaları değiştirilmedi.
- Python/API/CMD/compose/Dockerfile değiştirilmedi.
- `.env` dosyasına dokunulmadı.

## 13. Hüküm

`PACKAGING_01.station_name` encoding cleanup başarıyla uygulanmış ve evidence olarak kaydedilmiştir. Eski değer `??stasyon 2 - Paketleme`, hedef değer `İstasyon 2 - Paketleme` olarak düzeltilmiştir.

Bu cleanup Paket A station/location migration hatası değildir; migration station seed aşamasında mevcut station kayıtlarını update etmediği için önceden var olan station master data encoding/data quality sorunu ayrı olarak temizlenmiştir.

Bir sonraki teknik adım, runtime'ın `mes.locations` ve `mes.station_location_bindings` tablolarını read-only görebilmesi için DB query/helper tasarımıdır.
