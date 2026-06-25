# Repo Docs Cleanup Inventory

Bu envanter sprinti sadece okuma ve raporlama amaclidir. Dosya silme, tasima, yeniden adlandirma, runtime kodu, test, Docker veya migration degisikligi yapilmamistir.

## Kapsam

Incelenen kaynaklar:

- Repo genelindeki `*.md`, `*.docx`, `*.json`, `*.sql`
- `docs/**`
- `db/**`
- `docs/examples/**`
- `docs/agent_memory/**`
- `docs/db_pre_plan/**`
- Kok dizindeki dokuman dosyalari

Toplam incelenen dosya: 149

## Dosya Tipi Ozeti

| Type | Count |
| --- | ---: |
| `.md` | 89 |
| `.json` | 16 |
| `.sql` | 11 |
| `.xlsx` | 15 |
| `.xls` | 11 |
| `.csv` | 6 |
| `.docx` | 1 |

## Sinif Ozeti

| Classification | Count | Yorum |
| --- | ---: | --- |
| KEEP_CURRENT | 42 | Aktif README, runtime sample, mevcut migration/draft ve ornek payload dosyalari yerinde kalmali. |
| KEEP_BUT_RELOCATE | 60 | Korunmali; ancak yeni `docs/` domain yapisina veya `docs/raw/` altina alinmali. |
| MERGE_CANDIDATE | 9 | Ana dokumanlara ozetlenmeli; tek basina aktif akis icin tekrara dusuyor. |
| ARCHIVE_CANDIDATE | 37 | Tarihsel checkpoint degeri var; aktif dokuman akisindan ayrilmali. |
| DELETE_CANDIDATE | 1 | Bos/isyukleyici olmayan dosya; silme icin kullanici onayi gerekir. |
| NEEDS_REVIEW | 0 | Bu audit kapsaminda kararsiz bir dosya birakilmadi; dusuk guven kararlar open questions'a alindi. |

## Grup Bazli Karar Mantigi

| Grup | Current purpose | Proposed classification | Proposed target path | Reason | Risk if moved/deleted |
| --- | --- | --- | --- | --- | --- |
| Kok README/TODO ve alt proje README'leri | Calistirma, proje girisi, alt modul rehberi | KEEP_CURRENT | Mevcut yer | Kullanim baglami bulundugu klasore bagli | Tasima linkleri ve onboarding'i bozabilir |
| `db/drafts` ve `db/migrations` | DB draft ve uygulanmis migration kayitlari | KEEP_CURRENT | Mevcut yer | Runtime/migration hiyerarsisi dokuman degil operasyonel kayit | Tasima migration tooling ve audit izini bozabilir |
| `docs/examples` | Contract/example payload ornekleri | KEEP_CURRENT | Mevcut yer | Zaten hedef example klasorunde | Silme contract test fixture algisini bozabilir |
| `docs/bombop_*.md` | BOM/BOP sozlesme ve readiness dokumanlari | KEEP_BUT_RELOCATE | `docs/bombop/` | Domain bazli okunurluk artar | Erken tasima linkleri kirabilir; BOM/BOP source owner bekleniyor |
| `docs/mesql_*.md` | MESQL shared schema ve data exchange karar akisi | KEEP_BUT_RELOCATE | `docs/mesql/` | MESQL kararlarini tek domain altinda toplar | DB sprintinden once referans linkleri guncellenmeli |
| ERP/FERP markdownlari | ERP/F-ERP entegrasyon sozlesmeleri | KEEP_BUT_RELOCATE | `docs/erp/` | ERP konularini BOM/BOP ve MESQL'den ayirir | F-ERP label kaynaklariyla bag kopmamali |
| `docs/FERP_XLS/**` | Ham FERP label/export kaynaklari | KEEP_BUT_RELOCATE | `docs/raw/ferp/` | Bunlar aktif dokuman degil ham kaynak | Yanlis tasima label validation referansini karistirabilir |
| `docs/db_pre_plan/**` | DB pre-plan ham tasarim dosyalari | KEEP_BUT_RELOCATE | `docs/raw/db_pre_plan/` | Ham kaynaklar aktif contract'tan ayrilmali | Shared schema calismasi bu kaynaklara referans veriyor |
| `docs/agent_memory/**` checkpointleri | Agent handoff ve tarihsel karar hafizasi | ARCHIVE_CANDIDATE veya MERGE_CANDIDATE | `docs/archive/agent_memory/` veya ana dokuman | Aktif docs kokunu kalabaliklastiriyor | Erken arxivleme agent onboarding referanslarini etkileyebilir |
| `docs/postgres/**` | PostgreSQL gecis planlari | ARCHIVE_CANDIDATE | `docs/archive/postgres/` | Stabil main sonrasi tarihsel gecis plani niteliginde | Hala kullaniliyorsa yanlis archive karari olabilir |
| Bos giyotin readme | Icerik yok | DELETE_CANDIDATE | N/A | 0 byte dokuman | Kullanici onayi olmadan silinmemeli |

## KEEP_CURRENT Dosyalari

- `Baslaticilar\README.md`
- `db\drafts\mesql_shared_schema_draft.sql`
- `db\migrations\001_initial_mes_schema.sql`
- `db\migrations\002_unique_external_refs.sql`
- `db\migrations\002_unique_external_refs_rollback.sql`
- `db\migrations\003_station_tracking_schema.sql`
- `db\migrations\003_station_tracking_schema_rollback.sql`
- `db\migrations\004_work_order_transition_events.sql`
- `db\migrations\004_work_order_transition_events_rollback.sql`
- `db\migrations\005_package_bom_wip.sql`
- `db\migrations\006_station_queue.sql`
- `db\migrations\007_package_sessions.sql`
- `docker\mes\README.md`
- `docs\agent_memory\README.md`
- `docs\AI_GUIDE.md`
- `docs\archive\legacy_plans\roadmap.md`
- `docs\archive\README.md`
- `docs\examples\bombop_release_payload.canonical.example.json`
- `docs\examples\bombop_source_payload.required.example.json`
- `docs\examples\bombop_source_payload_request_email.md`
- `docs\examples\bombop_validation_response.example.json`
- `docs\examples\erp_preparation_staging_export.example.json`
- `docs\notebooklm\NOTEBOOK_INDEX.md`
- `docs\README.md`
- `mes_web\ferp_import\ferp_work_orders.json`
- `mes_web\README.md`
- `mes_web\work_orders\sample_work_orders.json`
- `picktolight\data\erp_snapshot.json`
- `picktolight\data\inventory.json`
- `picktolight\data\mqtt_config.json`
- `picktolight\data\operators.json`
- `picktolight\data\products.json`
- `picktolight\data\station_state.json`
- `picktolight\docs\wiring.md`
- `picktolight\README.md`
- `raspberry\config\boxes.example.json`
- `raspberry\config\observer.example.json`
- `raspberry\config\observer.pi.example.json`
- `raspberry\config\observer.pi.legacy.example.json`
- `raspberry\README.md`
- `README.md`
- `TODO.md`

## KEEP_BUT_RELOCATE Dosyalari

- `docs\architecture.md` -> `docs/architecture/overview.md`
- `docs\bombop_field_mapping_contract.md` -> `docs/bombop/field_mapping_contract.md`
- `docs\bombop_mesql_release_contract.md` -> `docs/bombop/mesql_release_contract.md`
- `docs\bombop_payload_collection_runbook.md` -> `docs/bombop/payload_collection_runbook.md`
- `docs\bombop_release_importer_contract.md` -> `docs/bombop/release_importer_contract.md`
- `docs\bombop_source_field_discovery_report.md` -> `docs/bombop/source_field_discovery_report.md`
- `docs\bombop_source_field_mapping_readiness.md` -> `docs/bombop/source_field_mapping_readiness.md`
- `docs\bombop_source_owner_questionnaire.md` -> `docs/bombop/source_owner_questionnaire.md`
- `docs\bombop_source_payload_acceptance_checklist.md` -> `docs/bombop/source_payload_acceptance_checklist.md`
- `docs\bombop_source_payload_request.md` -> `docs/bombop/source_payload_request.md`
- `docs\bombop_v1_importer_contract_readiness.md` -> `docs/bombop/v1_importer_contract_readiness.md`
- `docs\db_pre_plan\Agent_Memory_Knowledge_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Agent_Memory_Knowledge_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Bu sistem için tek bir veri tabanı yeterli olmaz.docx` -> `docs/raw/db_pre_plan/Bu sistem için tek bir veri tabanı yeterli olmaz.docx`
- `docs\db_pre_plan\Data_Warehouse_BI_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Data_Warehouse_BI_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Engineering_Master_Data_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Engineering_Master_Data_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\ERP_Integration_Database_Detayli_Tasarim (1).xlsx` -> `docs/raw/db_pre_plan/ERP_Integration_Database_Detayli_Tasarim (1).xlsx`
- `docs\db_pre_plan\Event_Altyapisi_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Event_Altyapisi_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Manufacturing_Master_Data_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Manufacturing_Master_Data_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\MES_Operational_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/MES_Operational_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Quality_Management_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Quality_Management_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Redis_Cache_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Redis_Cache_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Search_Full_Text_Arama_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Search_Full_Text_Arama_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Time_Series_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Time_Series_Database_Detayli_Tasarim.xlsx`
- `docs\db_pre_plan\Traceability_Database_Detayli_Tasarim.xlsx` -> `docs/raw/db_pre_plan/Traceability_Database_Detayli_Tasarim.xlsx`
- `docs\erp_create_map_conflict_lifecycle.md` -> `docs/erp/create_map_conflict_lifecycle.md`
- `docs\erp_preparation_adapter_decision_note.md` -> `docs/erp/preparation_adapter_decision_note.md`
- `docs\FERP_INTEGRATION.md` -> `docs/erp/FERP_INTEGRATION.md`
- `docs\FERP_JSON_CONTRACT.md` -> `docs/erp/FERP_JSON_CONTRACT.md`
- `docs\FERP_XLS\FERP_IS_EMRİ.xls` -> `docs/raw/ferp/FERP_IS_EMRİ.xls`
- `docs\FERP_XLS\FERP_import_csv\FERP_depo_transfer_aktar.xlsx` -> `docs/raw/ferp/import_csv/FERP_depo_transfer_aktar.xlsx`
- `docs\FERP_XLS\FERP_import_csv\FERP_metod_aktar.csv` -> `docs/raw/ferp/import_csv/FERP_metod_aktar.csv`
- `docs\FERP_XLS\FERP_import_csv\FERP_musteri_karti.csv` -> `docs/raw/ferp/import_csv/FERP_musteri_karti.csv`
- `docs\FERP_XLS\FERP_import_csv\FERP_personel_kartı.csv` -> `docs/raw/ferp/import_csv/FERP_personel_kartı.csv`
- `docs\FERP_XLS\FERP_import_csv\FERP_recete_aktar.csv` -> `docs/raw/ferp/import_csv/FERP_recete_aktar.csv`
- `docs\FERP_XLS\FERP_import_csv\FERP_stok_karti.csv` -> `docs/raw/ferp/import_csv/FERP_stok_karti.csv`
- `docs\FERP_XLS\FERP_import_csv\FERP_tedarikci_karti.csv` -> `docs/raw/ferp/import_csv/FERP_tedarikci_karti.csv`
- `docs\FERP_XLS\FERP_İŞ_İSTASYONU.xls` -> `docs/raw/ferp/FERP_İŞ_İSTASYONU.xls`
- `docs\FERP_XLS\FERP_İŞ_MERKEZİ.xls` -> `docs/raw/ferp/FERP_İŞ_MERKEZİ.xls`
- `docs\FERP_XLS\ferp_labels.xlsx` -> `docs/raw/ferp/ferp_labels.xlsx`
- `docs\FERP_XLS\FERP_MAMUL_IS_EMRI.xls` -> `docs/raw/ferp/FERP_MAMUL_IS_EMRI.xls`
- `docs\FERP_XLS\FERP_MÜŞTERİ.xls` -> `docs/raw/ferp/FERP_MÜŞTERİ.xls`
- `docs\FERP_XLS\FERP_OPERASYON_TANIMLARI.xls` -> `docs/raw/ferp/FERP_OPERASYON_TANIMLARI.xls`
- `docs\FERP_XLS\FERP_PERSONEL.xls` -> `docs/raw/ferp/FERP_PERSONEL.xls`
- `docs\FERP_XLS\FERP_STOK_DEĞİŞİM_İŞ_EMRİ.xls` -> `docs/raw/ferp/FERP_STOK_DEĞİŞİM_İŞ_EMRİ.xls`
- `docs\FERP_XLS\FERP_STOK_KARTI.xls` -> `docs/raw/ferp/FERP_STOK_KARTI.xls`
- `docs\FERP_XLS\FERP_TEDARİKÇİ.xls` -> `docs/raw/ferp/FERP_TEDARİKÇİ.xls`
- `docs\FERP_XLS\FERP_TÜM_LABEL_VE_ZORUNLULAR.xlsx` -> `docs/raw/ferp/FERP_TÜM_LABEL_VE_ZORUNLULAR.xlsx`
- `docs\FERP_XLS\FERP_YARI_MAMUL_IS_EMRI.xls` -> `docs/raw/ferp/FERP_YARI_MAMUL_IS_EMRI.xls`
- `docs\field-test-plan.md` -> `docs/runtime/field-test-plan.md`
- `docs\hardware.md` -> `docs/runtime/hardware.md`
- `docs\mesql_erp_bombop_mes_data_exchange.md` -> `docs/mesql/erp_bombop_mes_data_exchange.md`
- `docs\mesql_payload_versioning_policy.md` -> `docs/mesql/payload_versioning_policy.md`
- `docs\mesql_shared_schema_decision_note.md` -> `docs/mesql/shared_schema_decision_note.md`
- `docs\mesql_shared_schema_draft.md` -> `docs/mesql/shared_schema_draft.md`
- `docs\mesql_shared_schema_migration_review.md` -> `docs/mesql/shared_schema_migration_review.md`
- `docs\mesql_shared_schema_open_questions.md` -> `docs/mesql/shared_schema_open_questions.md`
- `docs\mesql_validation_error_dictionary.md` -> `docs/mesql/validation_error_dictionary.md`
- `docs\mqtt-topics.md` -> `docs/runtime/mqtt-topics.md`
- `docs\MVP_RUNBOOK.md` -> `docs/runtime/MVP_RUNBOOK.md`
- `docs\tablet_plan.md` -> `docs/runtime/tablet_plan.md`

## MERGE_CANDIDATE Dosyalari

- `docs\agent_memory\00_masterplan.md` -> `docs/architecture/roadmap.md`
- `docs\agent_memory\07_workflow_for_future_agents.md` -> `docs/INDEX.md` veya `docs/AI_GUIDE.md`
- `docs\agent_memory\08_guardrails_and_do_not_touch.md` -> `docs/AI_GUIDE.md`
- `docs\agent_memory\10_db_pre_plan_summary.md` -> `docs/mesql/db_pre_plan_summary.md`
- `docs\agent_memory\17_sql_source_of_truth_transition_masterplan.md` -> `docs/mesql/sql_source_of_truth.md`
- `docs\agent_memory\18_feature_flag_matrix.md` -> `docs/runtime/feature_flags.md`
- `docs\agent_memory\19_schema_natural_key_inventory.md` -> `docs/mesql/natural_key_inventory.md`
- `docs\data-model.md` -> `docs/mesql/data_model.md`
- `docs\mes_mvp_db_inventory.md` -> `docs/mesql/db_inventory.md`

## ARCHIVE_CANDIDATE Dosyalari

- `docs\agent_memory\01_current_progress.md`
- `docs\agent_memory\02_system_architecture.md`
- `docs\agent_memory\03_docker_postgres_runtime.md`
- `docs\agent_memory\04_postgresql_transition_plan.md`
- `docs\agent_memory\05_current_database_schema.md`
- `docs\agent_memory\06_runtime_data_flow.md`
- `docs\agent_memory\09_antigravity_handoff.md`
- `docs\agent_memory\11_launcher_inventory.md`
- `docs\agent_memory\12_physical_mqtt_validation.md`
- `docs\agent_memory\13_db_population_status.md`
- `docs\agent_memory\14_work_orders_status_policy.md`
- `docs\agent_memory\15_vision_events_source_policy.md`
- `docs\agent_memory\16_validated_db_population_checkpoint.md`
- `docs\agent_memory\20_external_ref_compatibility_report.md`
- `docs\agent_memory\21_unique_external_ref_migration_plan.md`
- `docs\agent_memory\22_unique_external_ref_migration_applied.md`
- `docs\agent_memory\23_production_completions_event_semantics.md`
- `docs\agent_memory\24_f2b_production_completions_dryrun_hook.md`
- `docs\agent_memory\25_f2b_runobs_observation_report.md`
- `docs\agent_memory\26_f2b_resync_checkpoint.md`
- `docs\agent_memory\27_f2c_production_completions_live_hook.md`
- `docs\agent_memory\28_f2c_live_hook_test_checkpoint.md`
- `docs\agent_memory\29_f2c_multirun_observation_checkpoint.md`
- `docs\agent_memory\30_mvp_sql_transition_checkpoint.md`
- `docs\agent_memory\31_work_order_source_reload_diagnosis.md`
- `docs\agent_memory\32_work_order_source_restoration_plan.md`
- `docs\agent_memory\33_package_routing_matching_diagnosis.md`
- `docs\agent_memory\34_package_flow_implementation.md`
- `docs\agent_memory\35_package_ui_routing_integration.md`
- `docs\agent_memory\36_package_finish_live_hook_bridge.md`
- `docs\agent_memory\37_package_flow_runtime_test_result.md`
- `docs\agent_memory\38_f_sta_a_station_tracking_design.md`
- `docs\agent_memory\39_sql_mvp_cutover_checkpoint.md`
- `docs\agent_memory\39_station_kiosk_package_bom_design.md`
- `docs\postgres\mes-postgresql-transition-inventory.md`
- `docs\postgres\mes-postgresql-transition-plan.md`
- `docs\postgres\README.md`

## DELETE_CANDIDATE Dosyasi

- `Giyotin_kontrol\pc_app\readme.md`

## NEEDS_REVIEW

Bu audit'te dosya seviyesi NEEDS_REVIEW kalmadi. Ancak tasima/merge/silme kararlarinin onay gerektiren noktalari `docs/repo_cleanup_open_questions.md` icinde ayrica listelenmistir.
