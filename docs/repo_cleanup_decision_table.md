# Repo Cleanup Decision Table

Bu tablo audit kararlarini ozetler. Bu sprintte listedeki hicbir dosya tasinmadi, silinmedi veya yeniden adlandirilmadi.

| File / group | Decision | Target | Confidence | Requires user approval | Note |
| --- | --- | --- | --- | --- | --- |
| `README.md` | KEEP_CURRENT | current | High | No | Repo giris noktasi. |
| `TODO.md` | KEEP_CURRENT | current | Medium | No | Aktif backlog olabilir; temizlik sonrasi ayrica sadeleştirilebilir. |
| `Baslaticilar/README.md` | KEEP_CURRENT | current | High | No | Klasor baglaminda calistirma rehberi. |
| `docker/mes/README.md` | KEEP_CURRENT | current | High | No | Docker klasorune bagli teknik README. |
| `mes_web/README.md` | KEEP_CURRENT | current | High | No | mes_web yasak kapsaminda; yerinde kalmali. |
| `mes_web/*.json` | KEEP_CURRENT | current | High | No | Runtime/sample veri; docs cleanup tarafindan tasinmamali. |
| `picktolight/**` md/json | KEEP_CURRENT | current | High | No | Alt proje dokumani ve data dosyalari. |
| `raspberry/**` md/json | KEEP_CURRENT | current | High | No | Observer config ornekleri ve README. |
| `db/drafts/mesql_shared_schema_draft.sql` | KEEP_CURRENT | current | High | No | Draft SQL kaynagi; migration degil. |
| `db/migrations/*.sql` | KEEP_CURRENT | current | High | No | Uygulanmis/versiyonlu migration zinciri; dokuman cleanup ile tasinmaz. |
| `docs/README.md` | KEEP_CURRENT | current | High | No | Docs giris noktasi. |
| `docs/AI_GUIDE.md` | KEEP_CURRENT | current | Medium | No | Agent rehberi; ileride INDEX ile linklenmeli. |
| `docs/notebooklm/NOTEBOOK_INDEX.md` | KEEP_CURRENT | current | High | No | NotebookLM kaynak indeksi. |
| `docs/archive/**` | KEEP_CURRENT | current | High | No | Zaten archive altinda. |
| `docs/examples/*.json` | KEEP_CURRENT | current | High | No | Contract/example payload ornekleri. |
| `docs/examples/bombop_source_payload_request_email.md` | KEEP_CURRENT | current | High | No | Ornek email; examples altinda dogru. |
| `docs/architecture.md` | KEEP_BUT_RELOCATE | `docs/architecture/overview.md` | High | Yes | Yeni docs yapisina uyar. |
| `docs/bombop_*.md` | KEEP_BUT_RELOCATE | `docs/bombop/` | High | Yes | BOM/BOP dokumanlarini tek domain altina toplar; source owner bloklu oldugu icin sadece tasima. |
| `docs/mesql_*.md` | KEEP_BUT_RELOCATE | `docs/mesql/` | High | Yes | Shared schema ve data exchange kararlari tek yerde okunmali. |
| `docs/FERP_INTEGRATION.md` | KEEP_BUT_RELOCATE | `docs/erp/FERP_INTEGRATION.md` | High | Yes | ERP/F-ERP domainine ait. |
| `docs/FERP_JSON_CONTRACT.md` | KEEP_BUT_RELOCATE | `docs/erp/FERP_JSON_CONTRACT.md` | High | Yes | ERP/F-ERP domainine ait. |
| `docs/erp_*.md` | KEEP_BUT_RELOCATE | `docs/erp/` | High | Yes | ERP hazirlik/lifecycle karar notlari. |
| `docs/field-test-plan.md` | KEEP_BUT_RELOCATE | `docs/runtime/field-test-plan.md` | Medium | Yes | Runtime/field test domaini. |
| `docs/hardware.md` | KEEP_BUT_RELOCATE | `docs/runtime/hardware.md` | Medium | Yes | Runtime/hardware domaini. |
| `docs/mqtt-topics.md` | KEEP_BUT_RELOCATE | `docs/runtime/mqtt-topics.md` | Medium | Yes | Runtime/MQTT domaini. |
| `docs/MVP_RUNBOOK.md` | KEEP_BUT_RELOCATE | `docs/runtime/MVP_RUNBOOK.md` | Medium | Yes | Runbook domaini. |
| `docs/tablet_plan.md` | KEEP_BUT_RELOCATE | `docs/runtime/tablet_plan.md` | Medium | Yes | Kiosk/tablet runtime plan. |
| `docs/db_pre_plan/**` | KEEP_BUT_RELOCATE | `docs/raw/db_pre_plan/` | Medium | Yes | Ham kaynak; aktif docs akisini kalabaliklastiriyor. |
| `docs/FERP_XLS/**` | KEEP_BUT_RELOCATE | `docs/raw/ferp/` | Medium | Yes | Ham FERP kaynaklari; label uydurmamak icin korunmali. |
| `docs/data-model.md` | MERGE_CANDIDATE | `docs/mesql/data_model.md` | Medium | Yes | DB inventory ve schema draft ile overlap riski var. |
| `docs/mes_mvp_db_inventory.md` | MERGE_CANDIDATE | `docs/mesql/db_inventory.md` | Medium | Yes | Agent memory DB notlariyla birlikte toparlanmali. |
| `docs/agent_memory/00_masterplan.md` | MERGE_CANDIDATE | `docs/architecture/roadmap.md` | Medium | Yes | Aktif roadmap ozeti cikarilip kaynak archive edilebilir. |
| `docs/agent_memory/07_workflow_for_future_agents.md` | MERGE_CANDIDATE | `docs/INDEX.md` or `docs/AI_GUIDE.md` | Medium | Yes | Agent onboarding bilgisini ana girise tasir. |
| `docs/agent_memory/08_guardrails_and_do_not_touch.md` | MERGE_CANDIDATE | `docs/AI_GUIDE.md` | Medium | Yes | Guardrail bilgisi tek agent rehberinde olmali. |
| `docs/agent_memory/10_db_pre_plan_summary.md` | MERGE_CANDIDATE | `docs/mesql/db_pre_plan_summary.md` | High | Yes | MESQL DB sprinti icin aktif bilgi. |
| `docs/agent_memory/17_sql_source_of_truth_transition_masterplan.md` | MERGE_CANDIDATE | `docs/mesql/sql_source_of_truth.md` | High | Yes | DB source-of-truth kararina bagli. |
| `docs/agent_memory/18_feature_flag_matrix.md` | MERGE_CANDIDATE | `docs/runtime/feature_flags.md` | Medium | Yes | Runtime feature flag dokumanina donusmeli. |
| `docs/agent_memory/19_schema_natural_key_inventory.md` | MERGE_CANDIDATE | `docs/mesql/natural_key_inventory.md` | High | Yes | Schema unique/revision kararlarina girdi. |
| `docs/agent_memory/README.md` | KEEP_CURRENT | current | High | No | Agent memory klasor indeksidir. |
| `docs/agent_memory/*` checkpointleri | ARCHIVE_CANDIDATE | `docs/archive/agent_memory/` | Medium | Yes | Tarihsel deger var; aktif docs akisini kalabaliklastiriyor. |
| `docs/postgres/**` | ARCHIVE_CANDIDATE | `docs/archive/postgres/` | Low | Yes | PostgreSQL gecis planlari tarihsel olabilir; aktif kullanim onayi gerekir. |
| `Giyotin_kontrol/pc_app/readme.md` | DELETE_CANDIDATE | N/A | Medium | Yes | 0 byte dosya; silme bu sprintte yapilmaz. |

## Sayisal Ozet

| Decision | Count |
| --- | ---: |
| KEEP_CURRENT | 42 |
| KEEP_BUT_RELOCATE | 60 |
| MERGE_CANDIDATE | 9 |
| ARCHIVE_CANDIDATE | 37 |
| DELETE_CANDIDATE | 1 |
| NEEDS_REVIEW | 0 |
