# Unique external_ref Migration Plan

## 1. Purpose
F1F aşamasında PostgreSQL canlı veritabanında (mes.production_completions ve mes.vision_events) kopya (duplicate) log oluşmasını önlemek için UNIQUE kısıtlamasının partial index ile eklenmesi ve uygulama adımlarının planlanması amaçlanmıştır.

## 2. F1E Compatibility Prerequisites
- **production_completions:** PASS
- **vision_events:** PASS
- Veritabanında (E5F populated) herhangi bir `null` veya `blank` external_ref tespit edilmemiştir.
- Herhangi bir duplicate tespit edilmemiştir.

## 3. Migration Scope
Yalnızca iki partial unique index oluşturulacaktır:
1. `mes.ux_mes_production_completions_external_ref`
2. `mes.ux_mes_vision_events_external_ref`
- Kapsam `WHERE external_ref IS NOT NULL AND btrim(external_ref) <> ''` ile sınırlandırılmıştır.

## 4. SQL Files
- `002_unique_external_refs.sql`: CREATE UNIQUE INDEX komutlarını içerir.
- `002_unique_external_refs_rollback.sql`: DROP INDEX komutlarını içerir.

## 5. Safety Rules
- Uygulama öncesi mutlaka veritabanı backup (pg_dump) alınmalıdır.
- Migration başlı başına ayrı bir faz olarak (F1F-B) değerlendirilmelidir.
- Aynı faz içerisinde canlı (runtime) koda hook veya read transition eklenmemelidir.
- Docker volume silinmemelidir (`docker compose down -v` KESİNLİKLE YAPILMAMALIDIR).

## 6. Apply Plan for F1F-B
1. **Health Check:** `http://127.0.0.1:8080/health` (Durum kontrolü).
2. **Runtime Flag Check:** F1B config flag'lerinin (hook/read) ve genel DB_ENABLED kapalı/false olduğunun doğrulanması.
3. **Backup:** Mevcut DB durumunun yedeklenmesi.
4. **Pre-counts & Pre-duplicate checks:** SELECT ile kayıtların sayılması.
5. **Apply SQL:** `002_unique_external_refs.sql` migration dosyasının çalıştırılması.
6. **Inspect pg_indexes:** İndekslerin şemaya düzgün yansıdığının SELECT ile teyit edilmesi.
7. **Verify Scripts:** Mevcut Python test/verify scriptlerinin (mirror doğrulama) bozulmadığından emin olmak.
8. **Final Counts:** Operasyon sonrası veri kaybı yaşanmadığının kontrolü.

## 7. Rollback Plan
- Index oluşturma sırasında herhangi bir sorun yaşanırsa, **sadece ve sadece** `002_unique_external_refs_rollback.sql` dosyası çalıştırılacaktır.
- Ardından indekslerin kalktığı `pg_indexes` üzerinden kontrol edilecektir.
- Tekrar verify scriptleri çalıştırılacaktır.

## 8. Post-Migration Verification Commands
- `production_completions` null/duplicate SELECT kontrolleri.
- `vision_events` null/duplicate SELECT kontrolleri.
- `pg_indexes` şema incelemesi.
- `python scripts/verify_production_completions_db_mirror.py`
- `python scripts/verify_vision_events_db_mirror.py`

## 9. Things Not To Do
- Migration esnasında canlı hook açma.
- Read transition işlemlerini başlatma.
- Data cleanup operasyonlarını index oluşturma ile aynı faza taşıma.
- Docker volume (`db_data`) silme.

## 10. Next Recommended Step
- **F1F-A commit/push:** Hazırlanan SQL scriptlerinin ve bu dokümanın repoya gönderilmesi.
- **Sonraki:** F1F-B controlled migration apply (SQL'in kontrollü ortamda canlı DB'ye işlenmesi).
