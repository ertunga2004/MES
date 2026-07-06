# ADR: Local Execution Station and Location Model

## Context

MESQL integration is temporarily frozen. The immediate priority is that the local MES DB can run the physical conveyor line independently.

The read-only analysis in `docs/architecture/local_station_inventory_model.md` shows that local MES already has useful pieces for execution: `work_order_operations`, `station_queue`, `work_orders`, `package_sessions`, `package_component_wip`, `item_station_events`, runtime `packagingBuffer`, and runtime `inventoryByProduct`.

The current gap is not basic operation start/complete persistence. The gap is execution semantics: station, location, buffer, queue identity, successor activation, package session, sensor evidence, and inventory movement must have clear boundaries before implementation continues.

## Decision

1. Local MES DB is the source-of-truth for operation lifecycle during local execution.
2. MESQL is, for now, a central sync, visibility, and outbox target. Local execution must not require a MESQL response to continue.
3. Station and location are separate concepts.
4. Buffer is not a station. Buffer is a location subtype.
5. `station_queue` must work operation-first. `work_order_operation_id` is the execution identity.
6. `order_id` may remain in `station_queue` as a readable and denormalized field.
7. Operation complete must perform local successor activation idempotently.
8. `package_session` and `packaging_unit` must not replace `work_order`.
9. Sensor event is not direct stock consumption. It is physical evidence that can later drive inventory movement or backflush semantics.
10. Inventory movement ledger is the target architecture, but the first P0 implementation is limited to local successor activation.
11. The current `mes` schema will not be torn down. Side-by-side additive migration remains the preferred path.

## Rationale

The physical line must keep running even when MESQL is unavailable, delayed, or inconsistent. Operation lifecycle decisions therefore belong in local execution first.

Station and location need to be separated because a station is an execution resource, while a location is where material physically or logically sits. A packaging buffer, assembly output lane, station WIP area, and finished goods area are inventory locations, not independent work centers.

`station_queue` must be operation-first because a single work order can have multiple operations across different stations. `order_id` alone cannot safely identify what the operator or machine should execute.

Successor activation must be local and idempotent because completing operation 10 should reliably make operation 20 visible to the next station without waiting for MESQL. Idempotency is required so retries, duplicate complete calls, or sync replays do not create duplicate queue rows.

Package session belongs below operation/work order level. It tracks a packaging process run, reservation, consumption, duration, and traceability. Treating it as a work order replacement would mix production planning with execution session state.

Sensor events are reliable physical evidence, but they do not by themselves define accounting semantics. The system must first decide whether a sensor event means item detection, station entry, station WIP, consume, produce, transfer, or backflush.

## Consequences

Local MES can progress operations without depending on MESQL availability.

The next implementation should focus narrowly on operation complete -> successor operation activation -> next station queue visibility.

Queue consumers should move toward `work_order_operation_id` as the primary identity. UI and API payloads can still include `order_id` for readability.

Existing package flow can continue, but package sessions must be treated as execution sub-records, not as primary work order records.

Inventory movement remains intentionally deferred. Current runtime inventory and package WIP projections may continue to exist while the ledger model is designed.

The architecture accepts a transition period where runtime state, current-state DB tables, and future ledger tables coexist.

## Non-goals

- No MESQL-side successor activation fix in this ADR.
- No live MESQL push behavior change.
- No SQL migration definition.
- No DB schema change.
- No Docker, volume, or deployment change.
- No immediate replacement of runtime `inventoryByProduct`.
- No immediate replacement of runtime `packagingBuffer`.
- No full inventory ledger implementation in P0.
- No package BOM/session redesign in P0.

## P0 Implementation Boundary

P0 is limited to local successor activation after operation completion.

Expected P0 behavior:

1. Complete the current operation in local DB.
2. Mark the current operation queue row completed.
3. Find the next operation for the same `order_id` by `sequence_no` or `operation_no`.
4. If a next operation exists and is not completed/cancelled, set it to queued/ready according to the local status vocabulary.
5. Insert or update exactly one `station_queue` row for the next operation's `station_code`.
6. Use `work_order_operation_id` as the queue execution identity.
7. Keep `order_id` in the queue row for readable joins and UI display.
8. If no successor exists, complete or advance the work order according to existing local lifecycle rules.
9. Make the operation complete flow retry-safe and duplicate-safe.

P0 must not introduce inventory movement, location tables, station-location bindings, or package session redesign.

## Future Work

- Add explicit location model for input, output, WIP, buffer, scrap, and finished goods locations.
- Add station-location bindings for default input/output/WIP locations.
- Add inventory movement ledger for consume, produce, transfer, reserve, release, scrap, adjust, and backflush events.
- Bind sensor events to movement semantics after location and backflush rules are explicit.
- Move packaging buffer behavior from runtime-only projection toward location-based inventory current-state.
- Add package session component rows for multi-component package BOM execution.
- Make kiosk and dashboard queue reads operation-first by default.
- Add reconciliation rules between local execution state and MESQL visibility state when MESQL integration is resumed.

## Risks

- Runtime state and DB state can drift during the transition period.
- Existing code paths may still treat queue as work-order-first instead of operation-first.
- Successor activation can create duplicate queue rows if idempotency keys are not enforced consistently.
- Package work orders and package sessions can remain semantically mixed unless later boundaries are enforced.
- Sensor events may be overinterpreted as stock movement before inventory policy is ready.
- Deferring inventory ledger means stock/location visibility remains incomplete after P0.
- Additive side-by-side migration reduces breakage risk but increases temporary model complexity.

