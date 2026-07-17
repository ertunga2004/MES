# Canonical V2 Controlled Route-Release API Contract

## Status

`READY_FOR_CONTROLLED_RELEASE_API_IMPLEMENTATION`

Last updated: `2026-07-17`.

This Phase 5H-D contract defines the future controlled HTTP surface. It does
not implement or enable that surface.

## Method and Path

```http
POST /api/v2/work-orders/{work_order_id}/route-release
Content-Type: application/json
```

The endpoint releases one existing work order to one exact route version. It
does not create the work order or choose a route.

## Feature Flag

```text
MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED=false
```

The flag is evaluated before reading the body. Missing or disabled:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"detail":"WORK_ORDER_ROUTE_RELEASE_DISABLED"}
```

The internal helper remains callable when the HTTP flag is disabled. The flag
does not authorize FERP/MESQL and is not authentication.

## Path Parameter

| Field | Type | Required | Normalization | Invalid result |
| --- | --- | --- | --- | --- |
| `work_order_id` | string | yes | trim, case preserved | helper-compatible `WORK_ORDER_ID_REQUIRED` or `WORK_ORDER_ID_INVALID` |

No lookup or inference occurs before the helper call.

## Request Body and Size

The raw body limit is exactly `65,536` bytes.

- `65,536` actual raw bytes: size gate passes and parsing continues.
- `65,537` actual raw bytes: `413 WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE`.
- A declared `Content-Length > 65536` may reject early.
- Missing, false, or smaller `Content-Length` never bypasses the limit; the
  accumulated ASGI body byte length is always checked.

Phase 5H-D1 must parse in this exact order:

```text
raw byte size
-> strict UTF-8 decode
-> standard JSON parse
-> duplicate-key validation at every object level
-> parser-depth/recursion failure classification
-> top-level object check
-> field allowlist and server-field rejection
-> scalar and metadata validation
-> one helper call
```

Automatic Pydantic body parsing is not the normative parser because it would
produce `422` for cases that this contract fixes at `400`.

## Request JSON Schema

Exact client field allowlist:

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `release_id` | string | yes | trim, nonblank, case preserved |
| `route_code` | string | yes | trim, nonblank, normalized uppercase |
| `route_version` | integer | yes | greater than zero; boolean is invalid |
| `released_by` | string | yes | trim, nonblank, case preserved; client-self-asserted |
| `metadata` | object | no | omitted means `{}`; no merge |

Canonical minimum request:

```json
{
  "release_id": "RELEASE-IDENTITY",
  "route_code": "ROUTE_BOX_PACKAGING_V2",
  "route_version": 2,
  "released_by": "LOCAL_PLANNER",
  "metadata": {}
}
```

Strings, numbers, booleans, arrays, and `null` are invalid as the top-level
body. Standard JSON is required; malformed UTF-8, malformed JSON, `NaN`,
`Infinity`, and `-Infinity` are invalid.

Duplicate keys are invalid at every object nesting level, including the
top-level request and objects inside metadata. The parser must use a
duplicate-aware object-pairs hook (or an equivalent mechanism) and must never
accept last-value-wins behavior. For example, both duplicate `release_id` and
duplicate nested metadata `purpose` keys return:

```http
HTTP/1.1 400 Bad Request

{"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID"}
```

Strict UTF-8 `UnicodeDecodeError`, JSON `JSONDecodeError`, non-finite constant
rejection, duplicate-key/object-pairs-hook validation failure,
`RecursionError`, and excessive-nesting/parser-depth failure are all parser-
owned invalid requests. They return the same `400` response with helper call
count `0`; they are never exposed as `422` or converted to generic `500`.

## Server-Controlled Values

The handler supplies exactly:

```text
release_source = "local_planning"
mode = "route_generated"
operation_bindings = None
```

If the client includes `release_source`, `mode`, or `operation_bindings`, even
with the supported value, the request returns:

```http
HTTP/1.1 400 Bad Request

{"detail":"WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED"}
```

Every other field outside the allowlist returns:

```http
HTTP/1.1 400 Bad Request

{"detail":"WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD"}
```

Unknown fields are never ignored, forwarded, or stored.

## Metadata Contract

- Omitted metadata becomes the exact empty object `{}`.
- A present value must be an object and must pass the helper's JSON-safe,
  finite-value validation.
- Caller metadata is passed unchanged after JSON decoding; it is not merged
  with server metadata.
- Structural equality is part of immutable replay identity.
- The endpoint does not add timestamps, actor/source fields, test markers, or
  trace identifiers to metadata.
- Metadata values and the complete payload are not logged by default.

Smoke callers may explicitly supply nonproduction markers such as:

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

The endpoint gives these keys no special execution behavior. Analytics/export
consumer exclusion remains a deferred requirement.

## Helper Invocation

After validation, the handler makes exactly one call equivalent to:

```python
release_work_order_to_route(
    app_config,
    release_id=release_id,
    work_order_id=work_order_id,
    route_code=route_code,
    route_version=route_version,
    release_source="local_planning",
    released_by=released_by,
    mode="route_generated",
    operation_bindings=None,
    metadata=metadata,
)
```

The API performs no database read/write, route resolution, replay classifier,
lock, queue-rank calculation, retry, or compensation around this call.

## Success Response

Repository API convention adds `ok=true`; helper fields remain top-level and
must not be wrapped under `data`.

First release:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "released": true,
  "release": {"release_id": "RELEASE-IDENTITY"},
  "work_order": {"order_id": "WO-IDENTITY"},
  "operations": [],
  "bindings": [],
  "initial_queue": {}
}
```

Exact replay:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "released": false,
  "release": {"release_id": "RELEASE-IDENTITY"},
  "work_order": {"order_id": "WO-IDENTITY"},
  "operations": [],
  "bindings": [],
  "initial_queue": {}
}
```

The abbreviated nested objects above illustrate the envelope only. Production
responses carry the complete JSON-safe snapshots returned by the helper.

## Replay Semantics

The same normalized work-order path, release ID, route/version, actor, and
metadata returns a normal idempotent success with `released=false`. No write is
performed on immediate or progressed replay.

Mutable operational progression alone is not a conflict: lifecycle and queue
statuses/ranks, quantities and timestamps may legitimately progress; successor
queues and runtime/events may exist; the work order may be completed. Immutable
release identity, static lifecycle snapshots, binding set, and digest remain
strict.

## Error Wire Format

Every error uses FastAPI repository convention:

```http
HTTP/1.1 <status>
Content-Type: application/json

{"detail":"<ERROR_CODE>"}
```

No `ok=false`, `error`, `error_code`, or `data` error envelope is introduced.

`MesqlV2Error.status_code` and `.detail` pass through unchanged. Examples:

| HTTP | Representative detail codes |
| --- | --- |
| `400` | `WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID` for decode/JSON/duplicate-key/parser-depth failures, `WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED`, `WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD`, `WORK_ORDER_ID_REQUIRED`, `RELEASE_ID_REQUIRED`, `ROUTE_CODE_REQUIRED`, `ROUTE_VERSION_REQUIRED`, `ROUTE_VERSION_INVALID`, `RELEASED_BY_REQUIRED`, `RELEASE_METADATA_INVALID` |
| `404` | `WORK_ORDER_NOT_FOUND`, `PROCESS_ROUTE_NOT_FOUND`, `ROUTE_OPERATION_NOT_FOUND` |
| `409` | `WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT`, `WORK_ORDER_ROUTE_ALREADY_RELEASED`, `WORK_ORDER_ROUTE_VERSION_CONFLICT`, `WORK_ORDER_RELEASE_MODE_CONFLICT`, `WORK_ORDER_RELEASE_OPERATION_COUNT_MISMATCH`, `WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH`, `WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT`, `WORK_ORDER_RELEASE_MAPPING_CONFLICT`, `WORK_ORDER_RELEASE_QUEUE_CONFLICT`, `WORK_ORDER_RELEASE_NOT_RELEASABLE` |
| `413` | `WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE` |
| `503` | `WORK_ORDER_ROUTE_RELEASE_DISABLED`, `DATABASE_DISABLED`, or another helper-classified readiness detail |
| `500` | `INTERNAL_ERROR` for any unclassified exception |

Oversize example:

```http
HTTP/1.1 413 Payload Too Large

{"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE"}
```

Generic failure example:

```http
HTTP/1.1 500 Internal Server Error

{"detail":"INTERNAL_ERROR"}
```

The handler preserves exception chaining and internal logging but does not
expose stack traces. It does not infer a domain result from raw PostgreSQL
SQLSTATE or translate an unknown failure to replay success or `409`.

## Actor and Security Contract

The repository currently has no authentication or authorization capability for
this route. `released_by` is therefore client-self-asserted and unverified; it
must not be described as an authenticated identity.

The contract permits it only for a trusted local operator or planning service
inside the controlled local network boundary. The default-disabled feature flag
is not authentication. Public or untrusted exposure requires a separate future
security design and is not allowed by this contract.

## Observability Contract

One structured record identifies the request outcome using event name,
work-order ID, release ID, route code/version, client-asserted actor, released
boolean, error detail code, and duration. Metadata values and the full request
body are excluded. The API adds no database audit, work-order/operation event,
outbox, package, or inventory write.

## Out of Scope

Automatic route selection, explicit operation mapping, FERP/MESQL sources,
reroute/cancel/delete, runtime execution, authentication, analytics exclusion,
and any database/schema/seed behavior are outside this initial contract.
