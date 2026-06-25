# BOM/BOP Docs

Bu klasor BOM/BOP sozlesme, source payload talebi, readiness ve MESQL release hazirlik dokumanlarini tutar.

## Ana Dokumanlar

- [Field Mapping Contract](field_mapping_contract.md)
- [BOM/BOP -> MESQL Release Contract](mesql_release_contract.md)
- [Payload Collection Runbook](payload_collection_runbook.md)
- [Release Importer Contract](release_importer_contract.md)
- [Source Field Discovery Report](source_field_discovery_report.md)
- [Source Field Mapping Readiness](source_field_mapping_readiness.md)
- [Source Owner Questionnaire](source_owner_questionnaire.md)
- [Source Payload Acceptance Checklist](source_payload_acceptance_checklist.md)
- [Source Payload Request](source_payload_request.md)
- [v1 Importer Contract Readiness](v1_importer_contract_readiness.md)

## Bu Klasorde Ne Yapilmamali?

- BOM/BOP source owner gelmeden yeni importer, adapter, v1 payload veya production mapping gelistirilmemeli.
- Gercek BOM/BOP source field adi uydurulmamali.
- Bilinmeyen F-ERP label eklenmemeli.
- DB migration veya runtime degisikligi bu klasor dokumanlarindan baslatilmamali.

## Ilgili Klasorler

- [MESQL](../mesql/README.md)
- [ERP / F-ERP](../erp/README.md)
- [Examples](../examples/)
- `docs/db_pre_plan/`
