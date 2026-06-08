# Current Progress

Tamamlanan ana fazlar:

- Windows üzerinde Docker Desktop, WSL 2 ve Ubuntu kurulum/doğrulama süreci planlandı ve uygulandı.
- Docker `hello-world`, compose config, PostgreSQL health, Adminer ve MES Web 8080 doğrulandı.
- Faz 1 development Docker mode tamamlandı.
- Faz 2 portable Docker mode tamamlandı.
- Portable mode ile `mes_web` image içinde kaynak kod snapshot'ı ile çalıştı; `/app` için ana kaynak bind mount kaldırıldı.
- Docker altyapısı repo içine `docker/mes` altında alındı.
- PR #1: portable Docker setup main'e merge edildi.
- Faz 4 PostgreSQL mirror foundation commit'i oluşturuldu: `1be35fc Add PostgreSQL mirror foundation and remove obsolete gsheet links`.
- Obsolete `.gsheet` link dosyaları SQL transition branch içinde kaldırıldı.
- Initial migration manuel uygulandı.
- PostgreSQL içinde `mes` schema oluştu.
- 15 başlangıç tablo oluştu.
- `scripts/mirror_work_orders_to_db.py` ile runtime JSON'dan `mes.work_orders` içine 6 mirror kayıt yazıldı.
- `scripts/verify_work_orders_db_mirror.py` ile JSON/DB mirror doğrulandı.
- Optional runtime `work_orders` mirror hook eklendi.
- D2/D2.5: `deviceSessions` stable key / session identity analiz edildi ve `scripts/dry_run_device_sessions_mirror.py` ile dry-run gerçekleştirildi. Runtime JSON'daki session verilerinin sessionId veya startedAt içermediği, lastSeenAt'in ise natural key olarak kullanılmasının volatile olduğu tespit edildi. Bu sebeple `mes.device_sessions` için doğrudan apply (D3) adımı iptal edildi/ertelendi. Mirror çalışması `production_completions` alanına kaydırıldı.
- D3/D4/D5/D6/D7/D8: `production_completions` analizi, kontrollü testi ve veri aktarımı tamamlandı. `scripts/mirror_production_completions_to_db.py` ve `scripts/verify_production_completions_db_mirror.py` scriptleri oluşturuldu. Controlled apply testi ile 7 geçerli üretim kaydı (`APPLY_SAFE`) veritabanına aktarıldı, mükerrer kayıt bulunmamaktadır.
- E1: Controlled DB Population Status Report hazırlandı (`docs/agent_memory/13_db_population_status.md`).
- E2/E2A/E2B/E2C: `work_orders` status drift analizi tamamlandı ve `mes.work_orders` MVP için current-state mirror kabul edildi. E2B kontrollü resync işlemi tamamlandı ve drift temizlendi; veritabanı doğrulama (verify) işlemi temiz döndü. `production_completions` tablosunun verify sonuçları da tamamen temiz kalmaktadır.
- E3/E4: `vision_events` analizi tamamlandı. Runtime JSON'un raw vision event history barındırmadığı, sadece current-state/summary ve dedupe key listesi taşıdığı görüldü. Bu nedenle `vision_events` için JSON tabanlı dry-run/apply veya verify scriptleri yazılmayacaktır. Raw event source policy dokümante edildi. Sonraki adım olarak raw log kaynağı envanteri veya live MQTT hook entegrasyonu planlanmaktadır.


Doğrulanan work orders mirror sonucu (C2 Canlı Docker Doğrulaması - 2026-06-08):

```text
- Test date: 2026-06-08
- Runtime mode: portable Docker
- Flags temporarily enabled:
  - MES_WEB_DB_ENABLED=true
  - MES_WEB_DB_MIRROR_WORK_ORDERS=true
- Trigger endpoint:
  - POST /api/modules/konveyor_main/kiosk/register
- Before test:
  - mes.work_orders count = 6
  - updated_at values around 2026-06-08 11:25:37+00
- After test:
  - mes.work_orders count = 6
  - updated_at values changed to around 2026-06-08 12:04:58+00
- Result:
  - no duplicate records
  - idempotent upsert worked
  - runtime hook worked
  - MES Web stayed healthy
- Verify script result:
  - json_work_order_count: 6
  - db_work_order_count: 6
  - matched_external_refs: 6
  - missing_in_db: 0
  - extra_in_db: 0
  - changed_or_suspicious: 0
- Test cleanup:
  - MES_WEB_DB_ENABLED=false
  - MES_WEB_DB_MIRROR_WORK_ORDERS=false
  - final health 200
  - final mes.work_orders count = 6
```

Önemli Sınırlar ve Uyarılar:
- Bu bir source-of-truth geçişi değildir.
- Runtime DB read yoktur.
- JSON/Excel/FERP akışı hâlâ korunmaktadır.
- DB mirror sadece feature flag ile çalışır.
- Test sonunda flagler tekrar false yapılmıştır.

C3 Physical MQTT Validation:
- Fiziksel ESP32 / IoT MQTT bağlantısı kullanıcı tarafından başarıyla doğrulandı.
- MES Docker portable runtime ile MQTT bağlantısı birlikte çalışıyor.
- Bu aşamada kod değişikliği yapılmadı.
- DB mirror flagleri false güvenli moda geri alınmış durumda.
- Sonraki öneri: MQTT/device/vision eventlerinin DB mirror için dry-run envanteri.

Feature flag defaultları kapalıdır:

```text
MES_WEB_DB_ENABLED=false
MES_WEB_DB_MIRROR_WORK_ORDERS=false
```

Kalan işler:

- `device_sessions` mirror (gerçek session identity/registry çözümü tasarlandıktan sonra).
- `vision_events` mirror (raw log envanteri veya live MQTT hook entegrasyonu sonrası).
- `oee_snapshots`, `downtime_events` için mirror planı çıkar.
- FERP import/export metadata ve outbox mantığını mirror olarak tasarla.
- DB read tasarımı için ayrı plan hazırla.
- Source-of-truth geçişini ancak mirror doğrulama, backup/replay ve rollback yolları kanıtlandıktan sonra değerlendir.
