# Canonical V2 Controlled Route-Release API Smoke Plan

## Status

`PLANNED_REQUIRES_PHASE_5H_D1_PASS_AND_SEPARATE_APPROVAL`

Last updated: `2026-07-17`.

This Phase 5H-D plan does not authorize starting the API, Docker, PostgreSQL,
creating a clone, mutating source, or creating test data.

## Safety Boundary

- Phase 5H-D2 runs only after Phase 5H-D1 implementation and unit/API tests
  pass and after a separate explicit approval.
- D2 uses an isolated disposable database/clone and a separately started local
  HTTP process configured only for that database.
- Source `mes` is not a D2 target. Source access, backup, fixture choice, and
  HTTP smoke require separate Phase 5H-D3 approval.
- No production failure-injection flag is added. Unit-level helper exceptions
  are injected by monkeypatch/TestClient only.
- Direct SQL may create an isolated clean planned work-order fixture and perform
  read-only evidence queries. Release, replay, lifecycle, binding, queue, and
  operational transitions use existing reviewed helpers or the HTTP endpoint.

## Preconditions

Before D2:

1. D1 commit and exact changed-file scope are reviewed.
2. Targeted MESQL V2 and combined API/MESQL regression suites pass.
3. The HTTP feature flag defaults to false and has explicit test-process
   pass-through.
4. The isolated database contains the exact Canonical V2 migrations and seed
   needed by `release_work_order_to_route`.
5. Baseline table counts/digests, sequence states, audit/outbox/package/
   inventory state, and active sessions are recorded before the first request.
6. The isolated HTTP process points only to the disposable database identity.

Any identity or scope mismatch stops the smoke before mutation.

## Test Identity and Metadata

Use unique D2 identities:

```text
work_order_id = PHASE5HD2-API-SMOKE-<yyyyMMdd-HHmmss>
release_id = PHASE5HD2-API-RELEASE-<yyyyMMdd-HHmmss>
released_by = PHASE5HD2_LOCAL_PLANNER
```

Every D2 first-release request explicitly supplies:

```json
{
  "phase": "5H-D2",
  "purpose": "controlled_release_api_validation",
  "disposable_test": true,
  "production_release": false,
  "exclude_from_analytics": true,
  "retention_reason": "controlled_release_api_validation"
}
```

The API must persist this object exactly and must not add, remove, merge, or
interpret marker values.

## Disabled Behavior

Start or test the route with
`MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED=false` and send a syntactically
valid request.

Expected:

- HTTP `503` with
  `{"detail":"WORK_ORDER_ROUTE_RELEASE_DISABLED"}`;
- helper call count `0`;
- body parsing is not required to reach the result;
- all database table counts/digests and sequence states unchanged.

Repeat with the flag absent. The result must be identical.

## Bounded Parser and Invalid Requests

D1 TestClient tests and D2 HTTP checks jointly cover the parser in its normative
order.

### Raw Size

- Construct valid JSON whose actual encoded body is exactly `65,536` bytes;
  size validation passes and the request proceeds to semantic/helper handling.
- Construct the same request at exactly `65,537` bytes; receive HTTP `413` and
  `{"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE"}` with helper call
  count `0`.
- Repeat the oversize body with missing, false-smaller, and correct-larger
  `Content-Length` where the client/test harness permits. Actual bytes remain
  authoritative; no header variant bypasses the limit.
- A larger declared `Content-Length` may reject before the complete body is
  read, but the returned code remains exact.

### Encoding and JSON Shape

Each of the following returns HTTP `400`,
`{"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID"}`, and zero helper
calls:

- invalid UTF-8;
- empty body;
- malformed JSON;
- `NaN`, `Infinity`, or `-Infinity`;
- duplicate top-level request keys;
- duplicate keys directly inside metadata;
- duplicate keys in deeper nested metadata objects;
- injected object-pairs-hook validation failure;
- `RecursionError` or an excessive-nesting/parser-depth failure;
- top-level array, string, number, boolean, or null.

Duplicate-key cases must be rejected at every object level rather than using
last-value-wins behavior. Decode, JSON, duplicate-hook, recursion, and depth
failures are parser-owned invalid requests; all have helper call count `0` and
must never return FastAPI/Pydantic `422` or generic `500`.

### Field Policy

- Any of `mode`, `release_source`, or `operation_bindings` returns
  `400 WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED`.
- Any other unknown key returns
  `400 WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD`.
- Missing/blank/wrong-type text fields, boolean/zero/negative/string route
  version, and non-object metadata return the exact helper-compatible `400`
  detail.
- Omitted metadata is forwarded as `{}`.
- Whitespace trimming, identity/actor case preservation, and route uppercase
  normalization agree with direct helper behavior.

## Missing Parent and Route

With the feature enabled:

- a missing work order returns `404 WORK_ORDER_NOT_FOUND`;
- an absent exact route code/version returns `404 PROCESS_ROUTE_NOT_FOUND`;
- a present route code with the wrong version returns the same `404` and never
  falls back to latest/active/product selection;
- no release, lifecycle, binding, queue, audit, or sequence delta occurs.

## First Release

Create one isolated clean planned work order eligible for the exact seeded
route. Send one HTTP request with the explicit route/version and marker metadata.

Expected:

- HTTP `200`;
- response keys are exactly `ok`, `released`, `release`, `work_order`,
  `operations`, `bindings`, and `initial_queue`;
- `ok=true`, `released=true`;
- no `data` wrapper;
- release row, deterministic lifecycle operations, complete immutable bindings,
  one initial queue row, and queued work-order state match direct authoritative
  helpers;
- server-controlled source/mode/bindings are exact;
- metadata matches byte/structural request content after JSON decoding;
- no runtime initialization, step event, completion bridge, extra audit/outbox,
  package, or inventory effect occurs.

## Immediate Replay

Send the exact same path and body again.

Expected:

- HTTP `200`, `ok=true`, `released=false`;
- response snapshots agree with direct read helpers;
- release/lifecycle/binding/queue writer and advisory-rank call counts are `0`
  under instrumentation;
- all table counts/digests and sequence states are unchanged from the
  post-first-release baseline;
- changed actor, metadata, release ID, or route/version produces the helper's
  deterministic `409`, never replay success.

## Progressed Replay

Using reviewed internal runtime/lifecycle helpers, progress the isolated release
through OP10 and OP20 to a completed work order. Preserve the immutable release,
static operation snapshots, and binding set. Then send the original exact HTTP
request.

Expected:

- HTTP `200`, `ok=true`, `released=false`;
- completed lifecycle/queue/work-order status, quantity, timestamps, successor
  queue, runtime state, and events remain unchanged;
- initial queue in the response remains the minimum-sequence OP10 queue identity;
- legitimate OP20 successor queue is accepted but not adopted as initial queue;
- release writer and advisory-rank calls are `0`;
- independent pre/post table and sequence snapshots are exact.

## Identical Concurrent Requests

Against one fresh eligible work order, release two identical HTTP requests
concurrently from separate clients.

Expected unordered result set:

```text
200 / ok=true / released=true
200 / ok=true / released=false
```

Both responses agree on release identity, deterministic lifecycle UUIDs,
bindings, and initial queue. Only one complete artifact set exists; there are no
partial rows or extra sequence/table deltas beyond one first release.

## Cross-Order Release-ID Conflict

Use one `release_id` concurrently for two different eligible work orders.

Expected:

- one request may succeed;
- the other returns HTTP `409` and
  `{"detail":"WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT"}`;
- the losing work order has no release-generated partial artifacts or status/
  timestamp mutation.

## Same-Station Rank Concurrency

Release different eligible work orders whose initial operation targets the same
station concurrently.

Expected:

- both requests return `200`, `ok=true`, `released=true`;
- initial queue rows have distinct ranks valid under the active-rank predicate;
- no API-owned lock/retry appears; helper advisory serialization owns the
  result;
- exact replays of both requests return `released=false` with zero writes.

## Conflict Matrix

Independently verify representative helper passthrough:

- different release ID for an already released work order;
- same release ID with different route/version;
- actor or metadata mismatch;
- incomplete/different binding set;
- immutable lifecycle snapshot/count mismatch;
- incompatible/duplicate initial queue;
- non-releasable work-order/config state.

Each response uses the helper's exact HTTP status/detail and
`{"detail":"ERROR_CODE"}` only. No error response adds `ok=false` or a
separate `error_code` field.

## Unknown Error Propagation

D1 unit/API tests monkeypatch the helper to raise an unclassified exception and
assert:

```text
HTTP 500
{"detail":"INTERNAL_ERROR"}
helper call count = 1
```

The exception remains chained/logged internally. No raw SQLSTATE is converted
to `409` or replay success. D2 adds no production failure-injection switch; an
unexpected real-database error stops the smoke and is recorded as `FAIL`.

## Actor and Security Check

Confirm documentation and OpenAPI/route description do not claim an
authenticated actor. `released_by` is client-self-asserted and unverified. The
test process is bound only to the approved local interface/network and accessed
by the trusted smoke client. The feature flag is verified as enablement only,
not authentication.

## No-Extra-Audit and Source Boundaries

For first release, only the helper's expected release, lifecycle, binding,
initial queue, and work-order transition deltas are permitted. Immediate and
progressed replay permit zero deltas. Operation events, work-order events,
integration/FERP outbox, package, inventory, approval, Kiosk, IoT, and MESQL
effects remain unchanged.

Phase 5H-D2 never points at source `mes`. Phase 5H-D3 requires a separate task
and explicit approval, exact source identity/preflight, backup and quiescence
policy, plus one new marked nonproduction work order or an explicitly approved
candidate. The retained Phase 5H-C fixture may be used only for an approved
zero-write progressed replay; it must never be reused as a first-release test.

## Cleanup

- Stop the isolated HTTP process.
- Close all clone sessions and remove only the exact disposable clone after
  recording final evidence.
- Verify no matching clone or temporary process remains.
- Preserve source untouched during D2.
- A D3 source fixture, if separately authorized, follows its approved retention
  policy and is never silently deleted or repaired.

## Evidence and Acceptance

Evidence must record:

- implementation commit and exact file scope;
- process flag and database identity;
- test identities and explicit metadata;
- each HTTP status/body and authoritative helper readback;
- `65,536` acceptance and `65,537` rejection;
- top-level/nested duplicate rejection and parser-depth/recursion failure
  classification as `400` with zero helper calls;
- first/replay/progressed and concurrency results;
- writer/advisory instrumentation where required;
- table count/digest and sequence pre/post comparisons;
- no-extra-audit boundaries, health, cleanup, and retained artifacts.

D2 is `PASS` only when all required cases pass, no forbidden side effect exists,
the clone is cleaned, and source remains untouched. Contract/test failure is
`FAIL`. Identity, authorization, isolation, backup, or source-boundary ambiguity
is `BLOCKED`; no later phase starts.
