# MESQL Docs

Bu klasor MESQL shared schema, payload versioning, validation ve ERP/BOM-BOP/MES veri alisverisi kararlarini tutar.

## Ana Dokumanlar

- [ERP/BOM-BOP/MES Data Exchange](erp_bombop_mes_data_exchange.md)
- [DB Core Planning](db_core_planning.md)
- [Runtime / Shared Schema Boundary](runtime_shared_schema_boundary.md)
- [Migration Candidate Matrix](migration_candidate_matrix.md)
- [Compatibility Report Plan](compatibility_report_plan.md)
- [Read-Only Compatibility Reports](read_only_compatibility_reports.md)
- [Read-Only Compatibility Report Result Template](read_only_compatibility_report_result_template.md)
- [Target PC Deployment Plan](target_pc_deployment_plan.md)
- [DB Pre-Plan Summary](db_pre_plan_summary.md)
- [SQL Source of Truth](sql_source_of_truth.md)
- [Natural Key Inventory](natural_key_inventory.md)
- [Payload Versioning Policy](payload_versioning_policy.md)
- [Shared Schema Decision Note](shared_schema_decision_note.md)
- [Shared Schema Draft](shared_schema_draft.md)
- [Shared Schema Migration Review](shared_schema_migration_review.md)
- [Shared Schema Open Questions](shared_schema_open_questions.md)
- [Validation Error Dictionary](validation_error_dictionary.md)
- [Target PC Execution Plan](target_pc_execution_plan.md)

## Bu Klasorde Ne Yapilmamali?

- Production migration yazilmamali.
- `db/drafts/mesql_shared_schema_draft.sql` DB'ye uygulanacak migration gibi sunulmamali.
- F-ERP label veya BOM/BOP gercek source field adi uydurulmamali.

## Ilgili Klasorler

- [ERP / F-ERP](../erp/README.md)
- [BOM/BOP](../bombop/README.md)
- [Examples](../examples/)
- `db/drafts/mesql_shared_schema_draft.sql`
- `db/migrations/`
