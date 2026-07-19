# Documentation Index

This is a curated documentation navigation and authority index, not an
exhaustive listing of every tracked Markdown artifact. Use it for canonical,
current, active, and high-value historical entry points. The repository tree
or `git ls-files '*.md'` is authoritative for the complete technical
inventory. A document omitted from this index is not thereby deleted or
invalid; historical evidence may remain at its original path.

This index does not authorize implementation, migration apply, source writes,
Docker lifecycle operations, physical-broker tests, or Phase 6B work.

## Canonical current documents

| Document | Purpose | Status | Authority |
| --- | --- | --- | --- |
| [Project README](../README.md) | Short repository entry point and system boundary | Current | General orientation |
| [Current Verified State](architecture/CURRENT_STATE.md) | Current verified capabilities, data baseline, flags, compatibility, and deferred scope | Current | Canonical verified state |
| [Phase 6B Entry](architecture/PHASE_6B_ENTRY.md) | Entry gate and frozen Phase 6A invariants | `NOT_STARTED` | Canonical phase boundary |
| [Phase 6A acceptance](runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md) | Final station-integration execution and review result | `PASS` | Canonical acceptance evidence |

Detailed execution facts come from acceptance/smoke evidence. A design or plan
cannot substitute for evidence that an operation ran or passed.

## Governance

| Document | Purpose | Status | Authority |
| --- | --- | --- | --- |
| [Root AGENTS](../AGENTS.md) | Repository mission, precedence, workflow, and safety | Active | Root Codex governance |
| [MES Web AGENTS](../mes_web/AGENTS.md) | Production transaction, identity, concurrency, MQTT, and compatibility rules | Active | Scoped governance for `mes_web/` |
| [Tests AGENTS](../tests/AGENTS.md) | Deterministic tests, replay/conflict, clone, and cleanup rules | Active | Scoped governance for `tests/` |
| [Docs AGENTS](AGENTS.md) | Documentation authority and evidence-integrity rules | Active | Scoped governance for `docs/` |
| [Antigravity AGENTS](../.agents/AGENTS.md) | Antigravity-only workspace rules | Tool-specific | Not a Codex governance source |

## Active phase boundary

- [Phase 6B Entry](architecture/PHASE_6B_ENTRY.md) — `NOT_STARTED`;
  implementation scope requires an explicit design decision and approval.
- [Current Verified State](architecture/CURRENT_STATE.md) — freezes the Phase
  6A baseline and identifies deferred work that is not automatically Phase 6B.

## Active designs and contracts

The documents in the implemented lineage describe decisions that now have
linked verification evidence. Phase-readiness labels embedded in an older
design or plan are historical and are superseded by `CURRENT_STATE.md` and the
linked implementation evidence. Their presence never authorizes a new apply or
rollout.

### Implemented and retained design lineage

#### Station and location

- [Local execution station/location ADR](architecture/adr-local-execution-station-location.md)
- [Station/location inventory model](architecture/local_station_inventory_model.md)
- [Station/location buffer blueprint](architecture/local_station_location_buffer_blueprint.md)
- [Station/location migration plan](architecture/local_station_location_migration_plan.md)
- [Station/location read model](architecture/station_location_read_model_design.md)
- [Station/location API](architecture/station_location_read_api_design.md)
- [Station/location Kiosk UI](architecture/station_location_ui_readonly_design.md)

#### Station execution

- [Execution model](architecture/station_execution_model_design.md)
- [Schema plan](architecture/station_execution_schema_plan.md)
- [Schema review checkpoint](architecture/station_execution_schema_review_checkpoint.md)
- [Migration plan](architecture/station_execution_migration_plan.md)
- [Seed setup plan](architecture/station_execution_seed_setup_plan.md)
- [Runtime engine design](architecture/station_execution_runtime_engine_design.md)
- [Runtime V0 implementation plan](architecture/station_execution_runtime_engine_v0_implementation_plan.md)
- [Config read model](architecture/station_execution_config_read_model_design.md)
- [Config read API](architecture/station_execution_config_read_api_design.md)
- [Kiosk dynamic actions](architecture/kiosk_dynamic_action_design.md)
- [IoT event adapter](architecture/iot_event_adapter_design.md)
- [Observation/quality boundary](architecture/observation_quality_control_boundary_decision.md)
  — accepted semantic boundary; the Canonical V2 observation step is
  implemented while separate quality-control and approval extensions remain
  deferred.
- [Observation/quality transition](architecture/observation_quality_control_transition_plan.md)
  — `IMPLEMENTED_CORE_WITH_DEFERRED_FOLLOW_UPS`: the versioned Canonical V2
  `PROCESS_END_OBSERVATION` route/config and verified execution path are
  implemented ([source apply](runbooks/canonical_v2_source_schema_seed_apply_evidence_20260715.md),
  [OP10 execution](runbooks/station_execution_canonical_v2_op10_execution_isolated_smoke_evidence_20260715.md));
  a separate quality-control operation, approval/completion extensions,
  legacy transition/backfill, and remaining rollout work are deferred.

#### Work-order binding and release

- [Binding decision](architecture/work_order_route_operation_binding_decision.md)
- [Binding implementation plan](architecture/work_order_route_operation_binding_implementation_plan.md)
- [Binding schema plan](architecture/work_order_route_operation_binding_schema_plan.md)
- [Release/route-binding decision](architecture/work_order_release_route_binding_decision.md)
- [Release/route-binding implementation plan](architecture/work_order_release_route_binding_implementation_plan.md)
- [Release schema plan](architecture/work_order_route_release_schema_plan.md)
- [Release helper contract](architecture/work_order_release_helper_contract.md)
- [Release transaction design](architecture/work_order_release_transaction_primitive_design.md)
- [Release concurrency/idempotency](architecture/work_order_release_concurrency_idempotency_plan.md)

#### Completion bridge and controlled rollout

- [Completion-bridge design](architecture/runtime_lifecycle_completion_bridge_design.md)
- [Completion-bridge concurrency](architecture/runtime_lifecycle_completion_bridge_concurrency_plan.md)
- [Canonical V2 source rollout](architecture/canonical_v2_source_rollout_design.md)
- [Controlled release API contract](architecture/canonical_v2_controlled_release_api_contract.md)
- [Controlled release entry point](architecture/canonical_v2_controlled_release_entrypoint_design.md)

### Deferred or unimplemented designs

- [OEE/KPI V0](architecture/oee_kpi_v0_design.md) — design input only;
  canonical station-event analytics and retained-fixture filtering are
  deferred.

- [MESQL registry](mesql/README.md) — frozen reference unless explicitly
  reactivated.
- [ERP/F-ERP registry](erp/README.md) — contracts and source-label references;
  production rollout is deferred.
- [BOM/BOP registry](bombop/README.md) — source-owner readiness and importer
  contracts; no inferred production payload.
- [Runtime registry](runtime/README.md) — retained runtime, hardware, feature
  flags, MQTT, and field-test references.

## Operational runbooks

Runbooks are reusable procedures, not proof that their actions ran. Apply,
source, physical, or destructive steps still require explicit authorization.

### Station/location and station execution

- [Apply station/location migration](runbooks/apply_station_locations_migration.md)
- [Station/location API smoke](runbooks/station_location_api_smoke_runbook.md)
- [Station-name cleanup plan](runbooks/station_name_encoding_cleanup_plan.md)
- [Station-execution schema apply](runbooks/station_execution_schema_migration_apply_runbook.md)
- [Station-execution seed apply](runbooks/station_execution_seed_minimal_apply_runbook.md)
- [Canonical V2 seed apply](runbooks/station_execution_canonical_v2_seed_apply_runbook.md)

### Binding, release, completion, and controlled HTTP

- [Binding migration apply](runbooks/work_order_route_operation_binding_migration_apply_runbook.md)
- [Release migration apply](runbooks/work_order_route_release_migration_apply_runbook.md)
- [Release writer isolated smoke](runbooks/work_order_release_writer_isolated_smoke_plan.md)
- [Release/route-binding isolated smoke](runbooks/work_order_release_route_binding_isolated_smoke_plan.md)
- [Completion-bridge isolated smoke](runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_plan.md)
- [Source schema/seed apply](runbooks/canonical_v2_source_schema_seed_apply_runbook.md)
- [Source-local functional smoke](runbooks/canonical_v2_source_local_functional_smoke_plan.md)
- [Controlled release API smoke](runbooks/canonical_v2_controlled_release_api_smoke_plan.md)

## Acceptance and smoke evidence

Evidence files are immutable records of what ran. Historical failure records
remain valid history even when a later recovery supersedes their final result.

### Station/location

- [Migration evidence](runbooks/station_locations_migration_evidence_20260706.md)
- [Read-model evidence](runbooks/station_location_read_smoke_evidence_20260707.md)
- [API evidence](runbooks/station_location_api_smoke_evidence_20260707.md)
- [Tier 1 CI evidence](runbooks/station_location_api_tier1_ci_evidence_20260707.md)
- [Kiosk visual evidence](runbooks/station_location_kiosk_manual_visual_evidence_20260707.md)

### Station execution

- [Schema migration evidence](runbooks/station_execution_schema_migration_evidence_20260709.md)
- [V1 seed evidence](runbooks/station_execution_seed_minimal_evidence_20260709.md)
- [Config read evidence](runbooks/station_execution_config_read_smoke_evidence_20260709.md)
- [Config API evidence](runbooks/station_execution_config_read_api_smoke_evidence_20260709.md)
- [Config API feature-flag wiring](runbooks/station_execution_config_read_api_feature_flag_wiring_smoke_20260709.md)
- [Runtime initialization](runbooks/station_execution_runtime_init_smoke_evidence_20260709.md)
- [Event ledger](runbooks/station_execution_event_ledger_smoke_evidence_20260709.md)
- [Step start](runbooks/station_execution_step_start_smoke_evidence_20260710.md)
- [Step finish](runbooks/station_execution_step_finish_smoke_evidence_20260710.md)
- [Implicit start/finish](runbooks/station_execution_robot_implicit_finish_smoke_evidence_20260710.md)
- [Completion policies](runbooks/station_execution_completion_policy_isolated_smoke_evidence_20260710.md)
- [Phase 6A final acceptance](runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)

### Binding, release, and completion bridge

- [Binding migration](runbooks/work_order_route_operation_binding_migration_isolated_smoke_evidence_20260714.md)
- [Binding reads](runbooks/work_order_route_operation_binding_read_helper_isolated_smoke_evidence_20260714.md)
- [Binding writes](runbooks/work_order_route_operation_binding_write_helper_isolated_smoke_evidence_20260714.md)
- [Release schema](runbooks/work_order_route_release_migration_isolated_smoke_evidence_20260715.md)
- [Release reads](runbooks/work_order_route_release_read_helper_isolated_smoke_evidence_20260715.md)
- [Release writer](runbooks/work_order_release_writer_isolated_smoke_evidence_20260715.md)

### Controlled source and HTTP release

- [Source schema/seed apply](runbooks/canonical_v2_source_schema_seed_apply_evidence_20260715.md)
- [Source replay recovery](runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md)
- [HTTP clone logging recovery](runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_recovery_evidence_20260719.md)
- [HTTP source progressed replay](runbooks/canonical_v2_controlled_release_api_source_http_smoke_evidence_20260719.md)

### Historical integration validation

| Document | Purpose | Status | Authority |
| --- | --- | --- | --- |
| [MESQL pull/push smoke](runbooks/mesql_pull_push_smoke.md) | Records the controlled MESQL v2 pull, local operation/outbox, and one live-push result, including known successor-queue and state-reversion risks | Retained historical smoke evidence; MESQL integration remains frozen/deferred unless explicitly scoped | Historical evidence/reference only; not current local MES execution source-of-truth and not authorization to rerun pull/push |

## Historical failure and recovery chains

| Chain | Historical failure | Verified recovery/current result |
| --- | --- | --- |
| Canonical V2 isolated apply/runtime initialization | [Initial BLOCKED](runbooks/station_execution_canonical_v2_isolated_apply_runtime_init_evidence_20260710.md) | [Retry remained BLOCKED](runbooks/station_execution_canonical_v2_isolated_apply_runtime_init_retry_evidence_20260710.md); both records remain source-integrity evidence, not a PASS |
| Canonical V2 bound runtime initialization | [Initial failure](runbooks/station_execution_canonical_v2_bound_runtime_init_isolated_smoke_evidence_20260714.md) | [Retry PASS](runbooks/station_execution_canonical_v2_bound_runtime_init_retry_evidence_20260715.md) |
| Runtime-to-lifecycle completion bridge | [Initial failure](runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_evidence_20260715.md) | [Retry PASS](runbooks/runtime_lifecycle_completion_bridge_isolated_smoke_retry_evidence_20260715.md) |
| Source-local Canonical V2 flow | [Final replay failure](runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md) | [Replay recovery PASS](runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md) |
| Controlled release HTTP clone | [Structured-log failure](runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_evidence_20260719.md) | [Focused logging recovery PASS](runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_recovery_evidence_20260719.md) |

The recovery supersedes only the corrected acceptance result. It does not
rewrite or erase the historical failure.

## Archived or superseded context

- [Archive policy](archive/README.md) — archived documents are noncanonical.
- `docs/agent_memory/` — historical checkpoints with unique information;
  retained in place pending a separately reviewed merge/archive batch.
- `docs/postgres/` — older PostgreSQL transition context; retained for manual
  review and not promoted over current state.
- `docs/repo_cleanup_*.md` — previous cleanup audit records; historical input,
  not current cleanup authority.
- `TODO.md` and the empty guillotine component README remain manual-review
  items; neither is safe for automatic deletion under the exact-duplicate-only
  policy.

Superseded general AI guidance and pre-Phase-6 overview/roadmap documents are
kept under `docs/archive/legacy_plans/` after link-safe archival.

## Document authority rules

When documents differ, follow the repository source order in
[root AGENTS](../AGENTS.md): current task, scoped governance, root governance,
verified current state, relevant design, acceptance/smoke evidence, README,
then historical/superseded context.

That order governs instructions, scope, and intended contracts. For claims
about what actually ran, acceptance/smoke evidence is authoritative. Report a
design/evidence conflict rather than treating either as proof of the other.

Do not:

- treat archived or agent-memory material as current authority;
- treat a design as execution evidence;
- erase historical FAIL evidence after a recovery;
- describe deferred work as implemented;
- infer Phase 6B scope from old plans;
- use a runbook as authorization to mutate a database or runtime.
