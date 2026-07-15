# Work-Order Route-Release Helper Contract

## Status

`READY_FOR_IMPLEMENTATION_AFTER_SCHEMA_VALIDATION`

Last updated: `2026-07-15`.

This document fixes the Phase 5B helper, deterministic identity, digest,
transaction, replay, and conflict contracts. It contains no Python or API
implementation and performs no database action.

## Scope

The helper boundary owns one local PostgreSQL transaction that:

```text
exact work order + exact route version
-> immutable release snapshot
-> complete lifecycle operation set
-> complete immutable operation bindings
-> one initial queue row
-> release-equivalent queued work-order state
```

It does not own runtime step execution or runtime-close to lifecycle-completion
bridging.

## Public Read Helpers

Proposed read-only contracts:

```python
get_work_order_route_release(
    config,
    work_order_id,
)
```

Returns the exact release row for normalized `work_order_id`, otherwise
`None`.

```python
get_work_order_route_release_by_id(
    config,
    release_id,
)
```

Returns the exact release row for normalized `release_id`, otherwise `None`.

```python
get_exact_process_route(
    config,
    route_code,
    route_version,
)
```

Runs an exact parameterized `route_code = ... AND version = ...` query. It
returns one route row or `None`; it never substitutes another version.

```python
list_process_route_operations(
    config,
    process_route_id,
)
```

Returns route operations belonging to the one resolved process-route identity,
ordered by `sequence_no ASC, route_operation_id ASC`. Missing route or no
operations returns an empty list; the write helper classifies that as a missing
or invalid route/config condition.

```python
get_work_order_release_snapshot(
    config,
    work_order_id,
)
```

Returns `None` when no release exists. Otherwise returns the release, work
order, ordered lifecycle operations, ordered bindings, and initial queue row.
It does not silently omit an incomplete join; snapshot completeness is
validated by the write/replay contract.

All read helpers use parameterized `SELECT`, perform no write or commit, and
propagate `DATABASE_DISABLED` (`503`) or PostgreSQL schema errors consistently
with existing MESQL V2 helpers.

## Core Write Helper

Exact proposed signature:

```python
release_work_order_to_route(
    config,
    *,
    release_id,
    work_order_id,
    route_code,
    route_version,
    release_source,
    released_by,
    mode,
    operation_bindings=None,
    metadata=None,
)
```

Phase 5D initial production enablement is restricted to:

```text
mode = route_generated
release_source = local_planning
```

The schema recognizes `explicit_existing_operation_mapping`, but the writer
must return `409 WORK_ORDER_RELEASE_MODE_NOT_ENABLED` for that mode until its
focused implementation and tests are separately completed.

## Request Contract

Required:

- nonblank `release_id`, `work_order_id`, `route_code`, and `released_by`;
- positive integer `route_version` (boolean is not accepted as integer);
- exact controlled `release_source` and `mode`;
- `metadata` omitted/`None` or a mapping serialized as a top-level JSON object.

Canonical text normalization before identity/digest work:

- convert accepted text inputs to string and trim leading/trailing whitespace;
- preserve case for `release_id`, `work_order_id`, and actor;
- apply the existing repository route-code normalization before the exact route
  query, then use the exact persisted route and route-operation text returned
  by the database;
- do not apply Unicode normalization, locale transforms, or platform newline
  conversion.

Generated mode requires `operation_bindings is None` or an empty list and
rejects caller-supplied lifecycle UUIDs. Explicit mode requires a list of
objects containing exactly `work_order_operation_id` and
`route_operation_id`; additional audit fields are not identity and must be
separately defined before acceptance.

Malformed/required/invalid scalar or JSON shape uses repository-convention
`400` domain errors. A future typed API may reject transport-model errors with
FastAPI `422` before calling the helper, but that does not change the core
helper contract.

## Response Contract

Exact logical response:

```python
{
    "released": True | False,
    "release": {...},
    "work_order": {...},
    "operations": [...],
    "bindings": [...],
    "initial_queue": {...},
}
```

Lists use canonical route sequence. First commit returns `released=True`.
Exact replay returns `released=False` and the authoritative persisted rows,
including original database timestamps and queue rank, unchanged.

## Release Modes

`route_generated`:

- MES reads the exact route-operation set;
- MES deterministically creates every lifecycle UUID and snapshot;
- MES creates every binding and only the initial queue row.

`explicit_existing_operation_mapping`:

- caller supplies stable existing lifecycle UUID/config-operation pairs;
- MES creates no lifecycle operation;
- set equality and all lifecycle snapshots are strictly validated;
- mode remains disabled in the initial Phase 5D writer.

The modes never mix. Mode is persisted and part of digest/replay comparison.

## Route Resolution

Resolution order:

1. Normalize exact route code and positive version.
2. Query `mes.process_routes` by both values.
3. Require one row; capture exact `route_id`, code, version, item, and active
   state.
4. Validate active as a release-time guard, not a selector.
5. List operations from that resolved identity and validate a nonempty active,
   uniquely sequenced config set.

No max-version, latest-active, product-to-route, station, operation-code, or
sequence inference is allowed. The persisted composite FK independently proves
that route ID/code/version belong to the same parent row.

## Work-Order Validation

Before the first write, lock/read the exact work order and require:

- row exists;
- normalized product code equals selected route item code in the MVP;
- status is `planned` or structurally clean `queued`;
- status is not active, completed/done, cancelled/canceled, or terminal;
- no prior release under either unique identity;
- no incompatible lifecycle operation, binding, queue, runtime, event,
  approval, or production-flow evidence;
- target quantity and required operation snapshot inputs are valid.

An exact existing complete release is handled by replay classification before
first-write eligibility is applied. An incomplete/corrupt release snapshot is
not repaired.

## Route-Generated Operation Contract

For every validated route operation in canonical order:

- derive deterministic `work_order_operation_id` using the operation UUID
  algorithm below;
- set `operation_no = sequence_no` under current lifecycle uniqueness;
- copy exact `operation_code`, `operation_name`, `sequence_no`, and
  `station_code` as lifecycle snapshots;
- set planned quantity from the validated work-order target where applicable;
- set first operation status `queued` and every successor status `planned`;
- reject any deterministic UUID, operation number, or sequence collision before
  writing.

Caller UUIDs, random-per-retry values, database-default UUIDs, timestamps,
Python `hash()`, and station/code/sequence-derived identity are prohibited in
this mode.

## Explicit Existing-Operation Mapping Contract

When later enabled, the mapping must satisfy exact set equality:

- every lifecycle UUID exists and belongs to the selected work order;
- every route-operation ID exists and belongs to the frozen route version;
- every required route operation appears exactly once;
- every lifecycle operation appears exactly once;
- no extra lifecycle operation or mapping exists;
- operation count equals selected route-operation count;
- lifecycle station, operation code, and sequence equal config snapshots;
- no lifecycle row is active, terminal, executed, or already queued
  incompatibly;
- no orphan/partial binding set exists;
- exact binding pairs are accepted only as replay of a matching complete
  release.

Snapshot equality is validation, never config identity inference.

## UUIDv5 Namespaces

Namespace derivation uses only the Python standard library:

```python
uuid.uuid5(uuid.NAMESPACE_URL, namespace_label)
```

Operation namespace:

```text
label = urn:mes:work-order-route-release:operation:v1
UUID  = 51e8ce07-9395-54f4-9677-a32d03162cdc
```

Binding namespace:

```text
label = urn:mes:work-order-route-release:binding:v1
UUID  = 2e5192a2-5d5a-5f76-a9f6-dc70df96564a
```

These literal UUIDs and labels are versioned protocol constants. An
implementation test must recompute each literal from `UUID.NAMESPACE_URL` and
fail if it differs.

## Operation UUID Algorithm

Canonical name string:

```text
<canonical release_id> + U+000A + <exact persisted route_operation_id>
```

The separator is exactly one LF (`\n`, UTF-8 byte `0x0A`), not the two
characters backslash+n and not a platform newline. There is no trailing LF.
The complete string is encoded as UTF-8 by `uuid.uuid5` with no Unicode
normalization.

Algorithm:

```python
canonical_name = f"{release_id}\n{route_operation_id}"
work_order_operation_id = uuid.uuid5(OPERATION_NAMESPACE, canonical_name)
```

Persist/serialize the UUID in canonical lowercase hyphenated form.

Fixed examples for `RELEASE-V2-EXAMPLE-001`:

```text
ROUTE_BOX_PACKAGING_V2_OP10
-> 5258d822-55bd-56b1-81ba-7f89193ba4eb

ROUTE_BOX_PACKAGING_V2_OP20
-> 26c50f67-2519-5e29-a958-e39eca44934e
```

## Binding ID Algorithm

Use the same canonical name string with the separate binding namespace:

```python
binding_uuid = uuid.uuid5(BINDING_NAMESPACE, canonical_name)
binding_id = f"BINDING-WORK-ORDER-RELEASE-{str(binding_uuid).upper()}"
```

Exact representation:

- prefix is ASCII uppercase `BINDING-WORK-ORDER-RELEASE-`;
- UUID portion is uppercase canonical hyphenated UUID;
- no whitespace, braces, or suffix.

Fixed examples:

```text
ROUTE_BOX_PACKAGING_V2_OP10
-> ad8e94ba-e408-59b5-be90-b7f348c17050
-> BINDING-WORK-ORDER-RELEASE-AD8E94BA-E408-59B5-BE90-B7F348C17050

ROUTE_BOX_PACKAGING_V2_OP20
-> b342d41d-6777-5999-a07e-ce10e04533ca
-> BINDING-WORK-ORDER-RELEASE-B342D41D-6777-5999-A07E-CE10E04533CA
```

The lowercase UUID line is the UUIDv5 value; the next line is the persisted
text binding ID. Replay must derive the same values.

## Canonical Operation-Set Digest

Algorithm constants:

```text
hash = SHA-256
text encoding = UTF-8
output = 64 lowercase hexadecimal characters
```

Pair preparation:

1. Validate sequence is an integer and unique before sorting.
2. Convert lifecycle UUID to canonical lowercase hyphenated text.
3. Sort by integer `sequence_no`, then by UTF-8 bytes of exact
   `route_operation_id` as a defensive collation-independent key.
4. Build exactly this logical payload:

```json
{
  "process_route_id": "<exact route id>",
  "release_mode": "<exact mode>",
  "route_code": "<exact route code>",
  "route_version": 2,
  "pairs": [
    {
      "sequence_no": 10,
      "route_operation_id": "<exact config operation id>",
      "work_order_operation_id": "<canonical lowercase UUID>"
    }
  ]
}
```

Serialize exactly:

```python
serialized = json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
```

There is no leading/trailing whitespace or newline. Versions and sequence
numbers are JSON numbers. Metadata, actor, source, release ID, timestamps,
operation code, and station are not in the digest. Process-route identity,
mode, and every config/lifecycle pair are included. Actor/source/metadata are
compared separately during replay. Digest alone never decides replay.

Fixed example inputs:

```text
release_id = RELEASE-V2-EXAMPLE-001
process_route_id = ROUTE_BOX_PACKAGING_V2
route_code = ROUTE_BOX_PACKAGING_V2
route_version = 2
release_mode = route_generated
```

Exact serialized UTF-8 text:

```json
{"pairs":[{"route_operation_id":"ROUTE_BOX_PACKAGING_V2_OP10","sequence_no":10,"work_order_operation_id":"5258d822-55bd-56b1-81ba-7f89193ba4eb"},{"route_operation_id":"ROUTE_BOX_PACKAGING_V2_OP20","sequence_no":20,"work_order_operation_id":"26c50f67-2519-5e29-a958-e39eca44934e"}],"process_route_id":"ROUTE_BOX_PACKAGING_V2","release_mode":"route_generated","route_code":"ROUTE_BOX_PACKAGING_V2","route_version":2}
```

Exact digest:

```text
4063a5c72fd4d38f11757a4bf1115f83e1c05e8b97624deb808193c5d0fcb2e2
```

An implementation unit test must recompute the operation UUIDs, binding IDs,
serialized text, and digest from these constants.

## Transaction-Scoped Internal Primitives

Phase 5D needs private primitives that share one caller-owned cursor:

- lock/read work order;
- read existing release by order ID;
- read existing release by release ID;
- resolve exact route;
- list and validate ordered route operations;
- compute deterministic generated operation set;
- compute deterministic binding set;
- compute canonical operation-set digest;
- insert release row;
- insert lifecycle operation with the caller-supplied deterministic UUID;
- insert/replay binding on the shared cursor;
- lock station scope and allocate initial queue rank;
- insert initial queue row;
- set or retain queued work-order status;
- read authoritative final snapshot;
- classify a unique violation by post-rollback readback.

The standalone public binding helper must not be called if it opens an
independent transaction. Existing logic may be refactored into a private
cursor-scoped primitive while preserving its public wrapper behavior.

## Transaction Ordering

Exact first-call order:

1. Normalize/validate request without database writes.
2. Begin local transaction.
3. Lock exact work order.
4. Read/lock releases by order ID and release ID.
5. Resolve and validate exact route/version and ordered config.
6. Lock/read lifecycle operations, bindings, runtime evidence, and relevant
   queue scope.
7. Classify first call, exact replay, conflict, or unsupported mode.
8. Compute all operation UUIDs, binding IDs, canonical pairs, count, and digest
   before the first write.
9. Insert immutable release row with count/digest.
10. Insert all deterministic lifecycle operations.
11. Insert all bindings on the shared cursor.
12. Allocate/insert exactly one initial queue row.
13. Set or retain work order `queued`.
14. Read and validate the authoritative full snapshot.
15. Commit and return `released=True`.

Any failure rolls back all writes. No primitive commits independently.

## Exact Replay

Exact replay requires equality of:

- release ID and work-order ID;
- exact process-route ID/code/version;
- mode and source;
- normalized actor;
- metadata by JSON structural equality;
- complete ordered config/lifecycle pair set;
- deterministic operation UUIDs and binding IDs;
- route operation count and digest;
- lifecycle snapshot/status contract;
- initial queue identity, station, status, source, and rank.

It returns `released=False`, original rows and timestamps, and performs no
write, UUID replacement, re-ranking, event, or audit append. A persisted
incomplete snapshot is a conflict/integrity failure, not replay.

## Conflict Classification

Conflicts are classified only after authoritative locked reads. At minimum:

- same release ID with different work order/request;
- same work order with different release ID/route/mode;
- same operation with different config operation;
- different complete pair set or digest;
- partial/orphan binding set;
- missing/extra operation;
- snapshot mismatch;
- incompatible/duplicate queue;
- nonreleasable status/evidence;
- recognized but not-yet-enabled explicit mode.

No conflict path changes a row.

## Queue Contract

- Queue only the route operation with the smallest unique sequence.
- Queue identity is generated/mapped `work_order_operation_id`.
- Config identity remains its immutable binding.
- Use exact lifecycle station, status `queued`, and source
  `work_order_release`.
- Allocate the next active station rank while the relevant queue scope is
  locked.
- Respect station/operation, station/order, and active-rank uniqueness.
- Exact replay returns the original row and rank without an update.
- A terminal initial operation or incompatible existing queue is a conflict.
- Successors remain `planned` and unqueued at release.

No route-operation ID is added to the queue schema.

## Error Codes

Required `409` errors:

- `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT`;
- `WORK_ORDER_ROUTE_ALREADY_RELEASED`;
- `WORK_ORDER_ROUTE_VERSION_CONFLICT`;
- `WORK_ORDER_RELEASE_MODE_CONFLICT`;
- `WORK_ORDER_RELEASE_MAPPING_CONFLICT`;
- `WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT`;
- `WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH`;
- `WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH`;
- `WORK_ORDER_RELEASE_QUEUE_CONFLICT`;
- `WORK_ORDER_RELEASE_NOT_RELEASABLE`.

Additional initial-enablement error:

- `WORK_ORDER_RELEASE_MODE_NOT_ENABLED` (`409`).

Malformed request uses specific `..._REQUIRED` / `..._INVALID` codes with
status `400`, following existing `MesqlV2Error` convention. Disabled database
uses `DATABASE_DISABLED` (`503`).

## Missing Parent Behavior

Required `404` codes:

- `WORK_ORDER_NOT_FOUND`;
- `PROCESS_ROUTE_NOT_FOUND`;
- `ROUTE_OPERATION_NOT_FOUND`;
- `WORK_ORDER_OPERATION_NOT_FOUND`.

Missing config components discovered after resolving a parent may use a more
specific existing config-validation code, but must not be converted to a
conflict or inferred from another row. PostgreSQL FK violations remain
authoritative safety failures and are not masked as successful replay.

## Concurrency and Unique-Violation Readback

Work-order row locking plus unique release/order constraints provide the main
serialization boundary. Station queue scope is locked before rank allocation.

If a concurrent transaction wins a unique constraint race:

1. let the current transaction roll back fully;
2. open a clean read transaction/connection as required by repository helper
   convention;
3. read release by both order ID and release ID;
4. read the complete authoritative snapshot;
5. return exact replay only when every replay field matches;
6. otherwise raise the deterministic conflict corresponding to the mismatch.

Never continue queries on an aborted PostgreSQL transaction, blindly retry a
write, or translate every unique violation into replay.

## Legacy Compatibility

- No existing work order/release is automatically adopted or backfilled.
- Retained V1 historical replay remains binding-table independent.
- Existing unbound/partial/ambiguous lifecycle data is rejected by new release.
- Explicit mapping is not a generic migration tool.
- Station, operation code, sequence, product, runtime metadata, or latest route
  never creates an identity.
- Manual legacy migration requires separate approval and evidence.

## Runtime Completion Boundary

Release ends after the initial queue and queued work-order state commit.
Runtime OP10 reaching `closed` does not currently complete the lifecycle
operation or activate OP20.

Phase 5F separately designs:

```text
runtime closed
-> exactly-once lifecycle operation completion
-> existing successor activation
-> successor binding/runtime resolution
```

Phase 5G implements and smokes that bridge. Release helper code must not call
the bridge.

## Deferred API Boundary

No endpoint or feature flag is added in Phase 5B-5E. A future API wraps the
core helper without duplicating transaction logic, supplies authenticated actor
identity, maps domain status codes, and never chooses a route version for the
caller.

FERP route selection/mapping, acknowledgement/outbox, and MESQL reconciliation
remain Phase 5H or later.

## Out of Scope

- Python/test implementation in Phase 5B.
- Migration apply or database/Docker access.
- Release, lifecycle operation, binding, queue, or status mutation.
- Source enablement, API, Kiosk, IoT/MQTT, Observer, OEE/KPI.
- Runtime completion bridge.
- Approval, production flow, inventory, FERP, or MESQL implementation.
- Existing-data backfill, reroute, cancellation, or supersession.
