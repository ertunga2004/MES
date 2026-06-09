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
   - **C2 Canlı Docker Doğrulaması (2026-06-08):**
     - Kiosk register API (`POST /api/modules/konveyor_main/kiosk/register`) tetiklendiğinde idempotent upsert işlemi canlı Docker ortamında başarıyla doğrulanmıştır.
     - Çift kayıt (duplicate) oluşmamış, var olan 6 kayıt başarıyla güncellenmiştir (`updated_at` zaman damgaları güncellenmiştir).
     - Test sonrasında flagler kapatılarak default değerlerine (`false`) geri döndürülmüştür.
     - **Tasarım Sınırı Notu:** Bu bir source-of-truth geçişi değildir; veritabanı okuması (DB read) yapılmamakta ve JSON/Excel/FERP akışı aynen korunmaktadır.
8. Device sessions dry-run analyzer & identity decision (D2/D2.5 - 2026-06-08)
   - D2 `device_sessions` dry-run scripti eklendi (`scripts/dry_run_device_sessions_mirror.py`).
   - Script DB'ye bağlanmaz ve yazma yapmaz.
   - **D2 Device Sessions Dry-Run Result:**
     - Runtime JSON `deviceSessions` içinde 5 kayıt bulundu.
     - Bu kayıtlarda `sessionId` yok.
     - `connectedAt` / `startedAt` yok.
     - `lastSeenAt` var ama volatile olduğu için natural key üretiminde kullanılmadı.
     - Tüm kayıtlar `missing_stable_key` olarak değerlendirildi.
     - DB'ye yazma yapılmadı.
     - D3 apply script `device_sessions` için iptal/ertelendi.
   - **D2.5 Device Session Identity Decision:**
     - `deviceSessions` current-state / registry verisidir.
     - `mes.device_sessions` session history/log tablosudur.
     - Bu veri doğrudan `mes.device_sessions` tablosuna yazılmamalıdır.
     - İleride iki seçenek vardır:
       1. Runtime tarafında gerçek `sessionId` + `startedAt`/`endedAt` üretimi planlanır.
       2. Ayrı current-state tablo modeli düşünülür, örn. `mes.device_registry` / `mes.active_devices`.
     - Şimdilik PostgreSQL mirror çalışması `production_completions` gibi daha stabil log verilerine kaydırılacaktır.

9. Production completions dry-run analyzer (D3 - 2026-06-08)
   - `production_completions` dry-run scripti eklendi (`scripts/dry_run_production_completions_mirror.py`).
   - DB'ye yazma yapmaz.
   - `completionLog` ve `itemsById` verilerindeki overlap ve dedup riski analiz edilir.
   - Mevcut runtime JSON’da 8 candidate bulundu.
   - `order_id` eksikliği varsa apply ertelenmelidir; None/null `order_id` ile DB `external_ref` üretilmeyecektir.
   - Apply aşaması ancak stable key (order_id + item_id) temiz çıkarsa yapılacaktır.

10. Production completions mirror script (D6 - 2026-06-08)
   - `production_completions` mirror scripti eklendi (`scripts/mirror_production_completions_to_db.py`).
   - Varsayılan dry-run modundadır.
   - `--apply` argümanı ve `MES_WEB_DB_ENABLED=true` olmadan DB'ye yazmaz.
   - Sadece `APPLY_SAFE` (order_id ve completed_at içeren) kayıtları yazar.
   - `completionLog` kaynaklı eksik alanlı kayıtlar ve off-order (iş emri atanmamış) üretimler atlanır.
   - Apply işlemi henüz çalıştırılmadı.

11. Production completions read-only verify script (D8 - 2026-06-08)
   - D8 `production_completions` verify script eklendi (`scripts/verify_production_completions_db_mirror.py`).
   - Script read-only çalışır.
   - D7 kontrollü apply sonrasında oluşan 7 JSON `APPLY_SAFE` kayıt ile 7 DB kaydı karşılaştırılır.
   - Missing/extra/duplicate alanları temiz olmalıdır.

12. Work orders status drift policy (E2/E2A/E2B/E2C - 2026-06-08)
    - `work_orders` status policy: MVP için `mes.work_orders` tablosu current-state mirror olarak kabul edildi.
    - `status` alanı runtime JSON ile senkron tutulmalıdır.
    - E2B controlled resync ile 6 kayıt güncellendi, status drift temizlendi.
    - Status history/event modeli ileride `mes.work_order_events` ile değerlendirilebilir.

13. Vision events raw source policy (E3/E4 - 2026-06-08)
    - [x] **E4: Define Source Policy for vision_events**
      - Read-only analysis confirmed `oee_runtime_state.json` is insufficient.
      - Policy documented in `docs/agent_memory/15_vision_events_source_policy.md`.
    - [x] **E5A: Vision Raw Log Inventory**
      - Read-only analysis found Excel raw logs at `data/logs/MES_Konveyor_Veritabani_*.xlsx` which can be used for historical backfill.
    - [x] **E5B: Excel-based vision events dry-run script eklendi**
      - `scripts/dry_run_vision_events_from_excel.py` eklendi.
      - Script DB'ye bağlanmaz ve yazma yapmaz. Boş satır (blank row) filtresi ile sağlamlaştırıldı (E5B.1).
      - **E5B.2: Natural Key Hardening & Live Test (2026-06-09):**
        - Doğal anahtar kuralı `vision_track_id + event_type + detected_at` olarak değiştirildi.
        - `08-06-2026.xlsx` üzerindeki 17 live event kaydından `apply_safe_count = 17` üretildi, duplicate/unsafe hataları 0'a indirildi. Dry-run sonucu apply script yazımı için kararlı hale geldi.
    - [x] **E5C: Excel tabanlı vision_events mirror apply script hazırlığı**
      - `scripts/mirror_vision_events_from_excel.py` eklendi.
      - Varsayılan olarak dry-run modunda çalışır.
      - `--apply` ve `MES_WEB_DB_ENABLED=true` olmadan DB'ye yazmaz.
      - E5B.2 ile doğrulanan event-level `external_ref` kuralını kullanır.
      - Gelecek tarihli (`future_detected_at`) olaylar için timestamp koruması (APPLY_UNSAFE) içerir.
      - Apply henüz çalıştırılmadı.


Gelecek hedefler:

- `vision_events` apply script yazımı ve veritabanı yansıması (historical backfill).
- `device_sessions` mirror (gerçek session identity çözümü sonrası tekrar ele alınacak).
- MQTT raw stream / event log entegrasyonu (vision_events için).
- `oee_snapshots` mirror.
- `downtime_events` mirror.
- FERP import batch ve export outbox metadata.
- Feature-flagged DB read tasarımı.
- En son source-of-truth migration.

Source-of-truth geçişi için ön şartlar:

- Mirror karşılaştırmaları temiz olmalı.
- Idempotency kuralları kanıtlanmalı.
- Backup/replay ve rollback yolu hazır olmalı.
- Excel/JSON/FERP davranışı güvenli fallback olarak korunmalı.
