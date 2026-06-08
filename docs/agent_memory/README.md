# MES Agent Memory

Bu klasör, MES Docker/PostgreSQL geçişinin Antigravity ve sonraki ajanlar tarafından hızlı ve güvenli anlaşılması için hazırlanmış dokümantasyon hafızasıdır. Buradaki dosyalar kod, migration veya runtime veri yerine karar bağlamı, çalışma sınırları ve sonraki adımları özetler.

Önerilen kısa okuma sırası:

1. `00_masterplan.md`
2. `01_current_progress.md`
3. `02_system_architecture.md`
4. `04_postgresql_transition_plan.md`
5. `08_guardrails_and_do_not_touch.md`
6. `09_antigravity_handoff.md`

Dosya haritası:

- `00_masterplan.md`: Ana hedef, repo/runtime ayrımı ve nihai Docker + PostgreSQL yönü.
- `01_current_progress.md`: Tamamlanan fazlar, doğrulama sonuçları ve kalan işler.
- `02_system_architecture.md`: MES kaynak repo, Docker runtime klasörü, servisler, portlar ve portable/development farkı.
- `03_docker_postgres_runtime.md`: Docker komutları, backup/export, Adminer ve PostgreSQL erişim bilgisi.
- `04_postgresql_transition_plan.md`: Kademeli PostgreSQL geçiş fazları ve source-of-truth sınırı.
- `05_current_database_schema.md`: Mevcut `mes` şeması ve 15 başlangıç tablonun kavramsal özeti.
- `06_runtime_data_flow.md`: JSON, Excel, FERP, MQTT ve optional PostgreSQL mirror akışı.
- `07_workflow_for_future_agents.md`: Yeni ajanların plan, uygulama, test, verify ve PR akışı.
- `08_guardrails_and_do_not_touch.md`: Kesin sınırlar ve riskli işlemler.
- `09_antigravity_handoff.md`: Antigravity için doğrudan çalışma notu.
- `10_db_pre_plan_summary.md`: `docs/db_pre_plan/` ön analiz dosyalarının PostgreSQL geçişiyle ilişkisi.

Bu klasör karar belleğidir; nihai doğruluk için ilgili kaynak dosyalar ayrıca okunmalıdır.
