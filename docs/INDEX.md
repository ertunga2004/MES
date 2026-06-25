# Docs Index

Bu indeks aktif dokumanlarin kanonik okuma haritasidir. Archive, raw kaynak ve DB migration dosyalari aktif sprint talimati gibi yorumlanmamalidir.

## Architecture

- [Architecture README](architecture/README.md)
- [Roadmap](architecture/roadmap.md)
- [System Architecture Overview](architecture/overview.md)

## MESQL

- [MESQL README](mesql/README.md)
- [ERP/BOM-BOP/MES Data Exchange](mesql/erp_bombop_mes_data_exchange.md)
- [DB Core Planning](mesql/db_core_planning.md)
- [Runtime / Shared Schema Boundary](mesql/runtime_shared_schema_boundary.md)
- [Migration Candidate Matrix](mesql/migration_candidate_matrix.md)
- [Compatibility Report Plan](mesql/compatibility_report_plan.md)
- [Target PC Deployment Plan](mesql/target_pc_deployment_plan.md)
- [DB Pre-Plan Summary](mesql/db_pre_plan_summary.md)
- [SQL Source of Truth](mesql/sql_source_of_truth.md)
- [Natural Key Inventory](mesql/natural_key_inventory.md)
- [Payload Versioning Policy](mesql/payload_versioning_policy.md)
- [Shared Schema Decision Note](mesql/shared_schema_decision_note.md)
- [Shared Schema Draft](mesql/shared_schema_draft.md)
- [Shared Schema Migration Review](mesql/shared_schema_migration_review.md)
- [Shared Schema Open Questions](mesql/shared_schema_open_questions.md)
- [Validation Error Dictionary](mesql/validation_error_dictionary.md)

## ERP / F-ERP

- [ERP README](erp/README.md)
- [FERP Integration](erp/FERP_INTEGRATION.md)
- [FERP JSON Contract](erp/FERP_JSON_CONTRACT.md)
- [ERP Create / Map / Conflict Lifecycle](erp/create_map_conflict_lifecycle.md)
- [ERP Preparation Adapter Decision Note](erp/preparation_adapter_decision_note.md)

## BOM/BOP

- [BOM/BOP README](bombop/README.md)
- [Field Mapping Contract](bombop/field_mapping_contract.md)
- [BOM/BOP -> MESQL Release Contract](bombop/mesql_release_contract.md)
- [Payload Collection Runbook](bombop/payload_collection_runbook.md)
- [Release Importer Contract](bombop/release_importer_contract.md)
- [Source Field Discovery Report](bombop/source_field_discovery_report.md)
- [Source Field Mapping Readiness](bombop/source_field_mapping_readiness.md)
- [Source Owner Questionnaire](bombop/source_owner_questionnaire.md)
- [Source Payload Acceptance Checklist](bombop/source_payload_acceptance_checklist.md)
- [Source Payload Request](bombop/source_payload_request.md)
- [v1 Importer Contract Readiness](bombop/v1_importer_contract_readiness.md)

## Runtime

- [Runtime README](runtime/README.md)
- [Field Test Plan](runtime/field-test-plan.md)
- [Feature Flags](runtime/feature_flags.md)
- [Hardware Notes](runtime/hardware.md)
- [MQTT Topics](runtime/mqtt-topics.md)
- [MVP Runbook](runtime/MVP_RUNBOOK.md)
- [Runtime Guardrails](runtime/runtime_guardrails.md)
- [Tablet Plan](runtime/tablet_plan.md)

## Examples

- `docs/examples/` canonical/example payload alanidir.
- JSON ornekleri contract dokumanlarini destekler; production payload veya runtime veri dosyasi gibi yorumlanmamalidir.

## Raw Sources

- `docs/db_pre_plan/` ve `docs/FERP_XLS/` bu fazda tasinmadi.
- Bu klasorler ham kaynak niteligindedir; F-ERP label ve DB pre-plan kararlarini uydurmamak icin korunur.
- Raw kaynaklar aktif karar dokumani degil, kaynak kanitidir.

## Archive

- `docs/archive/` tarihsel veya superseded dokuman alanidir.
- `docs/agent_memory/` ve `docs/postgres/` bu fazda tasinmadi.
- Agent memory checkpointleri aktif karar dokumanlarina merge edilmeden archive edilmemelidir.

## DB Drafts / Migrations

- `db/migrations/*` aktif migration zinciridir; docs cleanup ile tasinmaz.
- `db/drafts/mesql_shared_schema_draft.sql` production migration degildir ve DB'ye uygulanmamali.
- MESQL shared schema markdownlari `docs/mesql/` altindadir; draft SQL ile iliski migration sprintinden once tekrar kontrol edilmelidir.

## Sprint Guardrails

- BOM/BOP source owner gelmeden importer, v1 payload, adapter veya production mapping gelistirmesi acilmamalidir.
- Bu indeks dokuman navigasyonudur; runtime davranisi, DB migration veya API sozlesmesi degistirmez.
