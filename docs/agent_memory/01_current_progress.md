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

Doğrulanan work orders mirror sonucu:

```text
json_work_order_count: 6
db_work_order_count: 6
missing_in_db: 0
extra_in_db: 0
changed_or_suspicious: 0
```

Feature flag defaultları kapalıdır:

```text
MES_WEB_DB_ENABLED=false
MES_WEB_DB_MIRROR_WORK_ORDERS=false
```

Kalan işler:

- Local `main` branch'i ve Docker runtime klasörünü son commit/PR durumuna göre güncelle.
- Docker runtime klasöründe portable image rebuild/restart yap.
- Flagler kapalıyken sistemin eskisi gibi kalktığını doğrula.
- İki flag true iken work_orders mirror hook'u canlı Docker ortamında kontrollü test et.
- `device_sessions`, `vision_events`, `oee_snapshots`, `downtime_events`, `production_completions` için mirror planı çıkar.
- FERP import/export metadata ve outbox mantığını mirror olarak tasarla.
- DB read tasarımı için ayrı plan hazırla.
- Source-of-truth geçişini ancak mirror doğrulama, backup/replay ve rollback yolları kanıtlandıktan sonra değerlendir.
