# Docs / PostgreSQL Geçiş Dokümanları

Bu klasör, MES PostgreSQL geçişine ait aktif planlama ve envanter dokümanlarını içerir.

## İçerik

| Dosya | Amaç |
|---|---|
| `mes-postgresql-transition-plan.md` | Faz 4A pasif PostgreSQL foundation planı. Feature flag politikası, migration kapsamı, smoke test ve mirror hook açıklamaları. |
| `mes-postgresql-transition-inventory.md` | Mevcut MES veri gruplarının envanteri. Hangi verilerin PostgreSQL adayı olduğu ve risk analizi. |

## Önemli Notlar

- Bu dokümanlar Faz 4A aşamasını ve mevcut durumu anlatır. Güncel ilerleme için `docs/agent_memory/01_current_progress.md` ve `04_postgresql_transition_plan.md` okunmalıdır.
- PostgreSQL şu anda **source-of-truth değildir**. Mevcut runtime hâlâ JSON/Excel/FERP/MQTT akışıyla çalışır.
- Güvenli default: `MES_WEB_DB_ENABLED=false` ve `MES_WEB_DB_MIRROR_WORK_ORDERS=false`.

## İlişkili Agent Memory Dosyaları

- `docs/agent_memory/04_postgresql_transition_plan.md` — Geçiş fazlarının özet durumu.
- `docs/agent_memory/05_current_database_schema.md` — Mevcut 15 tablo şeması.
- `docs/agent_memory/03_docker_postgres_runtime.md` — Docker komutları ve erişim bilgileri.
