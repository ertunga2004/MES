# MESQL Migration Candidate Matrix

Bu matris production migration degildir. Aday alanlari, gerekli on kosullari ve onerilen fazlari listeler.

Status degerleri:

- `MVP_CANDIDATE`
- `COMPATIBILITY_REPORT_FIRST`
- `WAIT_FOR_BOM_BOP_SOURCE`
- `DRAFT_ONLY`
- `FUTURE_PHASE`
- `DO_NOT_TOUCH`

| candidate_area | source_file_or_table | target_schema | target_table | migration_candidate_status | reason | required_precondition | risk_level | recommended_phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Existing work orders | `db/migrations/001_initial_mes_schema.sql`, `mes.work_orders` | `mes` | `work_orders` | COMPATIBILITY_REPORT_FIRST | Runtime read overlay mevcut; mevcut veri ve `order_id` uniqueness dogrulanmali. | Read-only count, duplicate `order_id`, null/blank key report. | Medium | Compatibility report |
| Work order events | `001_initial_mes_schema.sql`, `004_work_order_transition_events.sql` | `mes` | `work_order_events` | COMPATIBILITY_REPORT_FIRST | Transition event log runtime icin kritik; external_ref uniqueness kontrolu gerekir. | Duplicate/null `external_ref`, orphan order_id report. | Medium | Compatibility report |
| Production completions | `001_initial_mes_schema.sql`, `002_unique_external_refs.sql` | `mes` | `production_completions` | COMPATIBILITY_REPORT_FIRST | Live hook ve unique external_ref var; hedef PC verisi tekrar dogrulanmali. | Duplicate/null `external_ref`, count, timestamp sanity. | High | Compatibility report |
| Vision events | `001_initial_mes_schema.sql`, `002_unique_external_refs.sql` | `mes` | `vision_events` | COMPATIBILITY_REPORT_FIRST | Backfill/live source ayrimi ve external_ref key kritik. | Duplicate/null `external_ref`, event_key policy, timestamp sanity. | High | Compatibility report |
| OEE snapshots | `001_initial_mes_schema.sql` | `mes` | `oee_snapshots` | FUTURE_PHASE | Snapshot policy ve natural key net degil. | `snapshot_at + shift_id` policy, shadow report plan. | Medium | Future planning |
| Downtime events | `001_initial_mes_schema.sql` | `mes` | `downtime_events` | FUTURE_PHASE | Runtime event kaynagi ve lifecycle netlesmeli. | Downtime source event policy. | Medium | Future planning |
| Maintenance records | `001_initial_mes_schema.sql` | `mes` | `maintenance_records` | FUTURE_PHASE | Maintenance event source ve session relation netlesmeli. | Source event and session identity review. | Medium | Future planning |
| Quality override | `001_initial_mes_schema.sql` | `mes` | `quality_overrides` | MVP_CANDIDATE | Mevcut runtime quality override davranisi var; sinirli quality cekirdegi olabilir. | Read-only current data report, contract review. | Medium | Core planning after compatibility |
| Device sessions | `001_initial_mes_schema.sql` | `mes` | `device_sessions` | FUTURE_PHASE | Session identity volatile; live hook unsafe. | Stable session id/start policy. | High | Future planning |
| FERP import batches | `001_initial_mes_schema.sql` | `mes` | `ferp_import_batches` | MVP_CANDIDATE | ERP/F-ERP import trace icin MVP cekirdek olabilir. | FERP import lifecycle and file boundary review. | Medium | Core planning |
| FERP export outbox | `001_initial_mes_schema.sql` | `mes` | `ferp_export_outbox` | MVP_CANDIDATE | ERP/F-ERP export/outbox planina hizmet eder. | ERP preparation mechanism decision. | Medium | Core planning |
| Operators/stations/error types/maintenance steps | `001_initial_mes_schema.sql` | `mes` | reference tables | MVP_CANDIDATE | Minimum audit/ref domain icin kullanilabilir. | Code list ownership review. | Low | Core planning |
| Station tracking | `003_station_tracking_schema.sql` | `mes` | `item_station_events` | COMPATIBILITY_REPORT_FIRST | Station event writer mevcut; idempotency key kontrolu gerekir. | Duplicate `source, external_ref`, station code report. | High | Compatibility report |
| Station queue | `006_station_queue.sql` | `mes` | `station_queue` | COMPATIBILITY_REPORT_FIRST | Gunluk operasyonel queue; master mapping degil. | Station/order active rank uniqueness, orphan order report. | High | Compatibility report |
| Package BOM runtime lines | `005_package_bom_wip.sql` | `mes` | `package_bom_lines` | COMPATIBILITY_REPORT_FIRST | Runtime package support; shared package BOM master degil. | Active component uniqueness and source relation report. | Medium | Compatibility report |
| Package component WIP | `005_package_bom_wip.sql` | `mes` | `package_component_wip` | COMPATIBILITY_REPORT_FIRST | Runtime reserve/consume flow; session relation kontrol ister. | Duplicate source/external_ref, status/session report. | High | Compatibility report |
| Package traceability | `005_package_bom_wip.sql` | `mes` | `package_traceability` | COMPATIBILITY_REPORT_FIRST | Traceability runtime kaydi; full traceability modeli degil. | Duplicate external_ref and package/session relation report. | Medium | Compatibility report |
| Package sessions | `007_package_sessions.sql` | `mes` | `package_sessions` | COMPATIBILITY_REPORT_FIRST | Runtime package execution/session; DB read/write gate ister. | Package order, station/status, orphan relation report. | High | Compatibility report |
| Product master | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_master` | `products` | WAIT_FOR_BOM_BOP_SOURCE | Shared master data adayi; source payload ve ERP conflict lifecycle bekliyor. | Real source payload, ERP map/skip/conflict rules. | High | After source payload |
| Product revision | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_master` | `product_revisions` | WAIT_FOR_BOM_BOP_SOURCE | Revision unique modeli var ama source field yok. | Revision source field and status crosswalk. | High | After source payload |
| Component master | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_master` | `components` | WAIT_FOR_BOM_BOP_SOURCE | Component label ailesi biliniyor; gercek source field yok. | Source payload and ERP conflict review. | High | After source payload |
| MBOM | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_manufacturing` | `mbom_headers`, `mbom_lines` | WAIT_FOR_BOM_BOP_SOURCE | MBOM source field/nesting yok. | Real MBOM source payload, active RELEASED policy. | High | After source payload |
| BOP | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_manufacturing` | `bop_headers`, `bop_operations` | WAIT_FOR_BOM_BOP_SOURCE | BOP operations ve sequence source field yok. | Real BOP source payload, operation sequence policy. | High | After source payload |
| Operation/station mapping | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_manufacturing` | `operation_station_mapping` | WAIT_FOR_BOM_BOP_SOURCE | Canonical shared mapping; source owner ve mapping validation bekliyor. | Real mapping payload, station/work center ownership. | High | After source payload |
| Package BOM shared master | `db/drafts/mesql_shared_schema_draft.sql` | `mesql_manufacturing` | `package_bom_headers`, `package_bom_lines` | WAIT_FOR_BOM_BOP_SOURCE | Runtime package tables ile karistirilmamali; source payload bekliyor. | Real package BOM payload and revision policy. | High | After source payload |
| Full engineering domain | `docs/mesql/db_pre_plan_summary.md` | TBD | TBD | FUTURE_PHASE | MVP disi full engineering master data. | Engineering ownership and EBOM policy. | Medium | Future phase |
| Analytics/BI | `docs/mesql/db_pre_plan_summary.md` | TBD | TBD | FUTURE_PHASE | KPI/DW/time-series ihtiyaci kanitlanmadi. | Volume/query proof. | Medium | Future phase |
| Search/time-series/cache/agent memory DB | `docs/mesql/db_pre_plan_summary.md` | TBD | TBD | DO_NOT_TOUCH | Bu sprint ve MVP cekirdek disi altyapi. | Separate architecture decision. | High | Not in core planning |
