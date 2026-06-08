# PostgreSQL Transition Plan

Şu an PostgreSQL source-of-truth değildir. MES runtime hâlâ JSON/Excel/FERP/MQTT akışıyla çalışır. DB read yoktur. DB write yalnızca manuel scriptler veya optional feature flag hook ile sınırlıdır.

Tamamlanan/geçerli fazlar:

1. Passive DB foundation
   - `mes_web/db/` helper katmanı eklendi.
   - `MES_WEB_DB_ENABLED=false` default kaldı.
   - DB yoksa MES Web startup zorunlu DB bağımlılığı taşımaz.

2. Initial migration
   - `db/migrations/001_initial_mes_schema.sql` oluşturuldu.
   - `mes` schema ve 15 tablo tanımlandı.
   - Migration manuel uygulandı, otomatik startup migration yok.

3. Manual DB smoke test
   - `scripts/check_mes_db_connection.py` DB enabled durumda read-only bağlantı kontrolü yapar.
   - DB disabled durumda bağlantı açmadan çıkar.

4. Runtime JSON dry-run analyzer
   - `scripts/analyze_oee_runtime_state_for_db.py` JSON state'i DB tablo adaylarına dry-run map eder.
   - DB'ye bağlanmaz, dosya yazmaz.

5. Work orders manual mirror
   - `scripts/mirror_work_orders_to_db.py` ile `workOrders.ordersById` -> `mes.work_orders` mirror apply yapıldı.
   - 6 kayıt yazıldı.

6. Work orders verification
   - `scripts/verify_work_orders_db_mirror.py` JSON ve DB mirror kayıtlarını read-only karşılaştırır.
   - Son sonuç temizdir: JSON 6, DB 6, missing 0, extra 0, suspicious 0.

7. Optional runtime work_orders mirror hook
   - `MES_WEB_DB_ENABLED=true` ve `MES_WEB_DB_MIRROR_WORK_ORDERS=true` birlikte true ise `sync_work_order_runtime(state)` sonrası `mes.work_orders` upsert denenir.
   - Default kapalıdır.
   - DB hatası runtime response'unu çökertmez.

Gelecek hedefler:

- `device_sessions` mirror.
- `vision_events` mirror.
- `oee_snapshots` mirror.
- `downtime_events` mirror.
- `production_completions` mirror.
- FERP import batch ve export outbox metadata.
- Feature-flagged DB read tasarımı.
- En son source-of-truth migration.

Source-of-truth geçişi için ön şartlar:

- Mirror karşılaştırmaları temiz olmalı.
- Idempotency kuralları kanıtlanmalı.
- Backup/replay ve rollback yolu hazır olmalı.
- Excel/JSON/FERP davranışı güvenli fallback olarak korunmalı.
