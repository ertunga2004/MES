# Canonical V2 Controlled Route-Release Entrypoint Design

## Status

`READY_FOR_CONTROLLED_RELEASE_API_IMPLEMENTATION`

Last updated: `2026-07-17`.

This Phase 5H-D record is a design only. It creates no HTTP route, Python
implementation, test, database change, Docker change, feature-flag wiring, or
source mutation.

## Scope

The first controlled HTTP entry point exposes the existing atomic
`release_work_order_to_route` helper to a trusted local operator or planning
service. Its supported scope is deliberately narrow:

- `release_mode=route_generated`;
- `release_source=local_planning`;
- caller-supplied exact `route_code + route_version`;
- one existing local work order;
- default-disabled HTTP exposure;
- first release and exact idempotent replay.

The endpoint does not create work orders, select a route automatically,
initialize runtime state, execute steps, call the completion bridge, or write
release artifacts directly.

## Verified Baseline

- Phase 5H-C verified closure commit:
  `301ae800d3c06311409c5260be0ec4767fa42768`
  (`docs: record verified canonical v2 source-local flow`).
- Writer replay fix commit:
  `c7e7ea2698d873a7ac5c8737bddd97b349355675`
  (`fix: allow route release replay after queue progression`).
- Regression baseline: targeted `632 / OK`, combined `668 / OK`.
- The source-local first release, immediate replay, OP10/OP20 execution,
  completion, and progressed final replay are verified as one evidence chain.
- Retained fixture replay returned `released=false` on clone and source with
  `40/40` table and `35/35` sequence equality and zero writer/advisory calls.
- `release_work_order_to_route` already owns normalization, the PostgreSQL
  transaction, locks, deterministic identities, inserts, replay validation,
  concurrency recovery, and authoritative readback.
- Repository HTTP routes use FastAPI `HTTPException` with
  `{"detail":"ERROR_CODE"}`. Existing V2 read routes are registered from
  `mes_web.__main__` and use independent default-disabled environment flags.
- The repository currently has no application authentication or authorization
  layer for this endpoint.

## Entry-Point Boundary

The selected entry point is:

```text
POST /api/v2/work-orders/{work_order_id}/route-release
```

Phase 5H-D1 will add a dedicated registrar following the existing
`mes_web.__main__` V2 route-registration pattern. The handler will:

1. enforce the HTTP feature flag;
2. read and validate one bounded JSON request;
3. call `release_work_order_to_route` exactly once with server-controlled mode,
   source, and operation bindings;
4. add `ok=true` to the helper result;
5. translate errors only at the existing FastAPI boundary.

It must not perform a release pre-read, issue SQL, acquire a lock, allocate a
queue rank, implement retry, classify replay, or compensate a failed helper
call. Those behaviors remain exclusively owned by the helper.

## Feature Flag

Exact environment flag:

```text
MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED
```

The default is `false`. Truthy parsing follows the current V2 registrar
convention: trimmed, case-insensitive `true`, `1`, `yes`, or `on` enables the
route; every other or missing value disables it.

The flag is checked before request-body parsing. When disabled, the endpoint
returns:

```text
HTTP 503
{"detail":"WORK_ORDER_ROUTE_RELEASE_DISABLED"}
```

The helper is not called. This flag controls only the HTTP entry point. It does
not disable the internal Python helper, enable a read-model flag, authorize
FERP/MESQL, or provide authentication. Compose/environment pass-through is a
Phase 5H-D1 implementation concern and remains unchanged in this phase.

## Route Selection

Route identity is always supplied explicitly as `route_code` and
`route_version`. The helper resolves that exact pair. The HTTP layer provides
no latest/active-version fallback and performs no product-, station-, operation
code-, work-order metadata-, or legacy-state inference.

The initial endpoint accepts only:

```text
mode = route_generated
release_source = local_planning
operation_bindings = None
```

These values are server-controlled and are never accepted from the caller.
Explicit existing-operation mapping, FERP/MESQL sources, legacy adoption,
backfill, reroute, cancellation, supersession, and deletion remain disabled.

## Request Validation

Path identity:

```text
work_order_id: required nonblank string
```

Request JSON allowlist:

```text
required: release_id, route_code, route_version, released_by
optional: metadata
```

The implementation must not rely on FastAPI/Pydantic automatic request parsing
because malformed or non-object JSON is normatively a `400`, not a generated
`422`. Phase 5H-D1 uses a bounded raw-body parser in this exact order:

1. Reject a declared `Content-Length` above `65,536` as an early optimization.
2. Read ASGI request-body chunks while counting actual raw bytes; stop and
   reject as soon as the total exceeds `65,536`.
3. Decode the complete accepted body as strict UTF-8.
4. Parse standard JSON with duplicate-key detection at every object nesting
   level, rejecting malformed JSON and nonstandard numeric constants.
5. Convert UTF-8/JSON decode errors, duplicate-key hook failures,
   `RecursionError`, and excessive-nesting/parser-depth failures to the same
   invalid-request result.
6. Require the top-level value to be an object.
7. Reject server-controlled fields, then reject every other unknown field.
8. Validate required scalar types, positive integer version, and metadata
   object shape.
9. Call the helper with the validated values and server-controlled constants.

The limit is exact raw request-body bytes: `65,536` bytes are accepted for
further parsing; `65,537` bytes are rejected. `Content-Length` alone is never
authoritative; actual accumulated bytes are always checked. Oversize returns:

```text
HTTP 413
{"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE"}
```

Malformed UTF-8, malformed/empty/non-object JSON, non-finite numeric constants,
duplicate keys at the top level or inside metadata/nested objects,
`object_pairs_hook` validation failures, `RecursionError`, and excessive JSON
nesting/parser-depth failures return
`400 WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID` with zero helper calls. Duplicate
objects never use JSON's conventional last-value-wins behavior. Presence of
`release_source`, `mode`, or `operation_bindings` returns
`400 WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED`. Other unknown fields
return `400 WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD`.

The API preserves helper normalization:

- surrounding whitespace is trimmed;
- `work_order_id`, `release_id`, and `released_by` preserve case;
- `route_code` is normalized to uppercase;
- `route_version` must be an integer greater than zero and cannot be a boolean;
- no Unicode or platform normalization is added.

Omitted metadata becomes `{}`. Metadata must be a JSON object, is passed to the
helper without merge, and must remain structurally identical on replay. The
normal endpoint adds no server metadata and no Phase 5H-C test marker.

## Response Contract

First release and exact replay both return HTTP `200`. The repository API
convention adds only `ok=true` and keeps the helper fields at the top level:

```json
{
  "ok": true,
  "released": true,
  "release": {},
  "work_order": {},
  "operations": [],
  "bindings": [],
  "initial_queue": {}
}
```

First release returns `released=true`; exact replay returns `released=false`.
The helper fields must not be nested under `data`, renamed, omitted, or
reconstructed by the API. All returned persisted snapshots remain
authoritative helper output.

## Replay and Idempotency

An exact HTTP replay has the same normalized:

- path `work_order_id`;
- `release_id`;
- route code/version;
- client-asserted actor;
- metadata object.

It returns `200`, `ok=true`, and `released=false` with zero writes. Legitimate
operational progression does not invalidate immutable replay: OP10 may be
completed, OP20 may be queued/active/completed, the work order may be
completed, successor queues may exist, and runtime/events may be present.

The API never pre-reads persisted state, bypasses the helper, creates a release
or queue during retry, or implements a second replay classifier. Immutable
release, lifecycle snapshot, binding, digest, and identity conflicts continue
to be raised by the helper.

## Concurrency Ownership

All concurrency ownership remains in `release_work_order_to_route`:

- two identical concurrent first requests produce one `released=true` and one
  `released=false` authoritative response;
- the same release ID used for different work orders produces one success and
  one `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT`;
- same-station releases for different work orders receive distinct valid active
  queue ranks.

The API adds no mutex, advisory lock, rank allocator, database retry, or unique-
violation recovery. HTTP timeout/retry infrastructure must resend the exact
immutable request and interpret `released` from the successful response.

## Error Boundary

All errors use the repository FastAPI wire format:

```text
HTTP <status>
{"detail":"<ERROR_CODE>"}
```

There is no separate `error_code` envelope. `MesqlV2Error.status_code` and
`MesqlV2Error.detail` are transferred unchanged through `HTTPException`.

- `400`: bounded-parser/request-field, metadata, duplicate-key, decode, and
  parser-depth/recursion errors plus unsupported-input errors;
- `404`: missing work order or exact route/operation configuration;
- `409`: release identity, eligibility, route, lifecycle, binding, mapping, or
  queue conflicts;
- `413`: actual request body exceeds `65,536` bytes;
- `503`: endpoint disabled, database disabled, or a helper-classified readiness
  error;
- `500 INTERNAL_ERROR`: every unclassified exception.

The API must not convert a generic exception or raw SQLSTATE into `409`, replay
success, or an invented domain code. The original exception remains chained
and logged internally; the client receives `500 {"detail":"INTERNAL_ERROR"}`.

## Audit and Observability

One structured completion/failure log record uses:

```text
event = work_order_route_release_request
work_order_id
release_id
route_code
route_version
released_by
released
error_code
duration_ms
```

The implementation does not log the complete payload, metadata values,
credentials, or database rows by default. It must not create a new audit row,
operation/work-order event, integration outbox row, or other side effect beyond
the existing helper transaction.

Nonproduction markers such as `disposable_test`, `production_release`,
`exclude_from_analytics`, and `retention_reason` are accepted only when the
caller explicitly includes them in metadata. The endpoint never adds them and
never special-cases the retained Phase 5H-C fixture or its prefix. Future OEE,
KPI, analytics, reporting, FERP/MESQL, and generic export consumers must exclude
marked fixtures; consumer implementation remains deferred.

## Security and Network Boundary

Authentication and authorization are currently absent. Consequently,
`released_by` is client-self-asserted and unverified; it is not an authenticated
principal. It is accepted only within the trusted local operator/planning-
service boundary.

The feature flag is operational enablement, not authentication or
authorization. Exposing this write endpoint to a public or untrusted network
without a separately designed identity, authorization, transport, and network
control layer is an explicit security risk and is prohibited by this design.

## Implementation Phases

- Phase 5H-D1: flag/config wiring, bounded raw-body parser, registrar/handler,
  exact success/error serialization, structured logging, and unit/API tests.
  No database schema, migration, or seed change.
- Phase 5H-D2: separately authorized disposable/clone HTTP smoke covering
  disabled, first/replay, progressed replay, conflicts, concurrency, and
  no-extra-audit invariants.
- Phase 5H-D3: separately authorized controlled source HTTP smoke using one new
  marked nonproduction work order or an explicitly approved candidate. The
  retained Phase 5H-C fixture is eligible only as a zero-write progressed replay
  candidate, never as a new first-release fixture.
- Phase 5I: FERP mapping, acknowledgements/outbox, retry, and reconciliation may
  be designed only after D1-D3 PASS.

## Acceptance Criteria

- The route is default-disabled and calls only the existing helper.
- The request parser enforces actual `65,536`-byte maximum and returns no
  Pydantic-generated `422` for the normative invalid-body cases.
- Client and server-controlled fields, normalization, metadata, and unknown-
  field behavior are deterministic.
- Success is `200` with top-level `ok=true` plus unchanged helper fields.
- Errors use only `{"detail":"ERROR_CODE"}` with exact helper status/detail.
- First release, immediate replay, progressed replay, and concurrency preserve
  helper transaction/idempotency ownership.
- No authentication capability is implied; the actor is documented as
  unverified and the local trusted boundary is explicit.
- No automatic route selection, extra audit/event/outbox write, FERP/MESQL
  exposure, or special test-fixture logic is introduced.

## Deferred FERP/MESQL Integration

FERP/MESQL request mapping, non-local release sources, acknowledgement/outbox,
external idempotency, delivery retry, reconciliation, and authenticated service
identity are deferred to Phase 5I or later. They must reuse the proven helper
and explicit route/version identity rather than widening this endpoint
implicitly.

## Out of Scope

- Python, FastAPI route, parser, config, test, compose, or environment changes;
- database schema, migration, seed, repair, restore, or source mutation;
- automatic/latest/product route selection or station inference;
- explicit existing-operation mapping, legacy adoption, or backfill;
- reroute, cancellation, deletion, or release supersession;
- runtime initialization, step execution, completion-bridge orchestration;
- authentication/authorization implementation;
- analytics/export exclusion implementation;
- API, Kiosk, FERP, MESQL, inventory, or package integration.
