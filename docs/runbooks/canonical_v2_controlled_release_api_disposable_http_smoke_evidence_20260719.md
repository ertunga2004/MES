# Canonical V2 Controlled Route-Release API Disposable HTTP Smoke Evidence

Result: `FAIL / STRUCTURED_ROUTE_RELEASE_EVENT_NOT_EMITTED`

Execution date: `2026-07-19`

This evidence is immutable failure evidence for Phase 5H-D2. The disposable
clone functional and HTTP contract matrix passed, but the dedicated real
process log did not contain the required `work_order_route_release_request`
structured event. Per the Phase 5H-D2 failure policy, this single unmet
acceptance condition makes the phase `FAIL` and prevents Phase 5H-D3.

## Baseline

```text
implementation commit = 9544d9272968b69144c1786ef08836af64454cde
implementation subject = feat: add controlled work-order route release api
branch/ahead = main / origin/main ahead 7
initial tree = clean; staged 0; untracked 0; no repository operation in progress
evidence pre-existed = no
```

The implementation commit contained exactly:

```text
docker/mes/.env.example
docker/mes/compose.portable.yaml
docker/mes/compose.yaml
mes_web/__main__.py
tests/test_mes_web_work_order_route_release_api.py
```

Retained plain dump:

```text
path = C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_phase5hc_release_replay_recovery_20260717-080314.sql
size = 2911692 bytes
SHA-256 = f4e19c0bd8f97ff898fbc3a1de63ee0c125ee67a437de78292d74c971740e2f0
header = PostgreSQL plain dump; dumped from/by PostgreSQL 16.14
```

The file was regular and exact before mutation. Size and SHA-256 were exact
again after cleanup.

## Isolation and Restore

```text
container = mes_postgres
container ID = c5e10132d9ce26bbbaecf0ca9c5fe95020d1c0450e2f55f53c318a89ba7afa27
container state = running / healthy
host PostgreSQL port = 5433
clone = mes_phase5hd2_api_smoke_20260719-125509
clone pre-existed = no
container temp = /tmp/mes_phase5hd2_api_smoke_20260719-125509.sql
create source = template0
restore target = mes_phase5hd2_api_smoke_20260719-125509 only
source mes used as SQL/helper/HTTP target = no
retained Phase 5H-C fixture used = no
```

Control-plane database checks used only `postgres`; smoke/readback connections
used only the exact clone. No command connected to database `mes`. No compose
lifecycle, volume, migration, seed, repair, source backup, restore, source
fixture mutation, or existing `mes_web` process mutation occurred.

Restore checks:

```text
current_database = mes_phase5hd2_api_smoke_20260719-125509
PostgreSQL = 16.14
base tables = 40
sequences = 35
work_order_operation_route_bindings retained rows = 2
work_order_route_releases retained rows = 1
ROUTE_BOX_PACKAGING_V2 exact route/version = 1
ROUTE_BOX_PACKAGING_V2 operations = 2
OP10 / OP20 configured steps = 3 / 1
restored baseline snapshot fingerprint = 05ba55d92ae15a4c55011030ba32adcf7654a9e4d4f1717c60060c40cc6c1689
```

The process launcher was outside the repository. Before binding, it loaded
`AppConfig`, rejected any non-D2 database name, opened a PostgreSQL connection,
and required `current_database()` to equal the exact clone. Each successful
startup logged the redacted guard:

```text
D2_DB_GUARD database=mes_phase5hd2_api_smoke_20260719-125509 user=mes server_port=5432
```

Child-process isolation set loopback HTTP/DB hosts, the clone database, and the
configured password through inherited environment only. The password value was
never written to a command, launcher, evidence, or log. MQTT was restricted to
unused loopback port `9`; publish, manual command, vision ingest, Excel, work
order mirror, DB hooks, shadow/read flags, and dry-run hooks were disabled.
Work-order import and OEE state paths were unique task paths outside the repo.

Windows used a venv launcher shim plus child interpreter. Both exact task PIDs
were verified; the child listener PID owned a single `127.0.0.1` listener.
Observed task process pairs/ports were:

```text
flag missing: launcher/listener 48624/31300, port 57674
flag false:   launcher/listener 48100/30300, port 57674
enabled:      launcher/listener 8120/26856, port 57674
continuation: launcher/listener 49980/36256, port 51736
final matrix: launcher/listener 52604/38704, port 51768
```

Every process returned `GET /health` as `200 / status=ok`. Process restarts
were harness-only continuations using the same clone and fixture identities;
no hidden clone or replacement test identity was used.

## Test Identity

```text
order_id = PHASE5HD2-API-SMOKE-20260719-125509
release_id = PHASE5HD2-API-RELEASE-20260719-125509
actor = PHASE5HD2_LOCAL_PLANNER
route = ROUTE_BOX_PACKAGING_V2 / version 2
item / target = PACKAGED_PRODUCT / 1
```

Exact request metadata:

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

One separate disposable omitted-metadata fixture was the documented narrow
exception. It persisted `{}` and replayed with `released=false`.

## HTTP Contract Matrix

The missing and explicit-false feature-flag processes both returned exact:

```http
503
{"detail":"WORK_ORDER_ROUTE_RELEASE_DISABLED"}
```

Their complete 40-table/35-sequence snapshots had zero delta.

Raw-body results:

```text
65536 actual bytes / Content-Length = 404 WORK_ORDER_NOT_FOUND, not 413, zero write
65537 actual bytes / chunked = 413 WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE, zero write
Content-Length 65537 header-only early guard = exact 413 body, zero write
missing Content-Length / chunked valid body = 404 WORK_ORDER_NOT_FOUND, zero write
misleading-smaller Content-Length = not safely representable as an honest real-wire body;
  no D2 claim; retained D1 handler-level unread-tail evidence applies
```

The normal 65,537-byte Content-Length attempt exposed the expected HTTP
transport caveat: Uvicorn emitted the 413 status while Windows reset the
connection with an unread body tail. The actual-byte limit was therefore
proved through chunked framing, while the declared-length early guard was
proved separately from headers. No production switch or implementation change
was introduced.

Each invalid-body case returned exact
`400 {"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID"}` with full
table/sequence zero delta:

```text
invalid UTF-8; empty; malformed JSON; top-level array/string/number/null;
NaN; Infinity; -Infinity; duplicate top-level key; duplicate direct metadata;
duplicate deep metadata; duplicate key inside a list object; complete request
with approximately 5000 nested metadata-array levels (10174 raw bytes)
```

Field policy passed:

```text
mode / release_source / operation_bindings, singly and combined
  -> 400 WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED
server-controlled plus unknown priority
  -> 400 WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED
unknown field -> 400 WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD
missing/blank/non-string release_id, route_code, released_by -> exact field code
missing/blank route_version -> ROUTE_VERSION_REQUIRED
bool/float/zero/negative/string route_version -> ROUTE_VERSION_INVALID
null/list/string metadata -> RELEASE_METADATA_INVALID
blank path work_order_id -> WORK_ORDER_ID_REQUIRED
```

All of these checks were real HTTP and zero-write. D1 offline evidence remains
the authority for injected object-pairs-hook failure, forced `RecursionError`,
and generic helper exception because no production failure switch was added.

Domain negatives passed with zero write and unchanged work-order
status/timestamps:

```text
missing work order -> 404 WORK_ORDER_NOT_FOUND
missing route -> 404 PROCESS_ROUTE_NOT_FOUND
wrong exact version 1 -> 404 PROCESS_ROUTE_NOT_FOUND; no fallback
```

## Release and Progression

First release returned HTTP `200`, exact top-level keys
`ok/released/release/work_order/operations/bindings/initial_queue`, and
`released=true`. It changed only release, lifecycle, binding, initial queue,
and work-order tables.

```text
operation-set digest = 6e4f840395f5cdb189d9962ac36e7e64a09cc62eb50cc58a4242323fe1c36091
OP10 lifecycle UUID = 214a6ad9-5a23-54ac-b1c2-06e1ff899a1a
OP20 lifecycle UUID = 54889f2c-b147-5681-adc9-eadbbb6aef57
OP10 binding ID = BINDING-WORK-ORDER-RELEASE-1876FF37-0F24-57F4-8AE7-8479392F0FE0
OP20 binding ID = BINDING-WORK-ORDER-RELEASE-C49D5BF4-0FDC-5CCA-B0C0-54F6BF5043C6
initial queue PK/rank/station/source = 6855 / 5 / ASSEMBLY_01 / work_order_release
```

UUIDv5 operation and binding identities were independently recomputed with the
committed namespaces and single-LF name. Lifecycle operations were ordered
10/20, queued/planned, stations ASSEMBLY_01/PACKAGING_01, quantities 1/0/0,
UOM `piece`. Bindings were complete and immutable with exact lifecycle UUID
join, actor, source, route-operation ID, and release metadata. Initial queue
pointed only to OP10.

Immediate exact HTTP replay returned `200`, `released=false`; all 40 table
count/digests and 35 sequence states were exact pre/post.

Runtime progression passed:

```text
OP10 initialization / initialization replay = new / existing zero-write
OP10 configured events = COLOR finish; ROBOT finish; PROCESS_END start+finish
OP10 final bridge / exact finish replay = true / false zero-write
OP20 initialization / replay = new / existing zero-write
OP20 PACKAGING start+finish bridge / finish replay = true / false zero-write
old OP10 final-finish replay after completion = false / zero-write
runtime states / steps / operation events / queues = 2 / 4 / 6 / 2
```

Only `operation_events`, `station_queue`, execution state/steps,
`work_order_operations`, and `work_orders` changed during progression. Final
authoritative primary state was:

```text
work order = completed at 2026-07-19T10:23:33.796298+00:00
OP10 = completed at 2026-07-19T10:23:32.581346+00:00
OP20 = completed at 2026-07-19T10:23:33.796298+00:00
OP10 queue = PK 6855, rank 5, completed, work_order_release
OP20 queue = PK 6856, rank 3, completed, runtime_completion_bridge
```

Progressed exact HTTP release replay returned `200`, `released=false`, kept
`initial_queue` tied to OP10, and had exact 40-table/35-sequence zero delta.

## Concurrency and Conflicts

Real concurrent client starts produced:

```text
identical order/release/request = 200 released=true + 200 released=false;
  exactly 1 release, 2 lifecycle rows, 2 bindings, 1 queue
same release ID across two fresh orders = winner 200; loser 409
  WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT; loser row/timestamps/artifacts unchanged
same ASSEMBLY_01 station, distinct orders/releases = both 200 released=true;
  ranks 8 and 9, no OP20 queue; both exact replays false/zero-write
```

Pass-through conflict matrix:

```text
new release ID on released order = WORK_ORDER_ROUTE_ALREADY_RELEASED
same release ID with version change = WORK_ORDER_ROUTE_VERSION_CONFLICT
actor mismatch = WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT
metadata mismatch = WORK_ORDER_ROUTE_RELEASE_ID_CONFLICT
static operation mutation = WORK_ORDER_RELEASE_OPERATION_SNAPSHOT_MISMATCH
missing binding = WORK_ORDER_RELEASE_PARTIAL_BINDING_CONFLICT
complete but altered binding identity = WORK_ORDER_RELEASE_MAPPING_CONFLICT
incompatible initial queue source = WORK_ORDER_RELEASE_QUEUE_CONFLICT
fresh completed work order = WORK_ORDER_RELEASE_NOT_RELEASABLE
```

All returned HTTP `409 {"detail":"<exact code>"}`. Destructive conflict
injections used separate clone-only fixtures and were not repaired or reused.

## Side-Effect Boundary

The only tables changed from the primary-fixture checkpoint were:

```text
operation_events
station_queue
work_order_operation_execution_state
work_order_operation_route_bindings
work_order_operation_steps
work_order_operations
work_order_route_releases
work_orders
```

Exact count/digest zero delta held for work-order audit events, approvals,
production flow/completion, item-station and vision events, FERP/integration
inbox/outbox, all five package tables, items, locations, and station-location
bindings. The exact 40-table inventory contains no dedicated inventory
movement/balance base table; no invented inventory table was queried. Final
clone shape remained 40 base tables and 35 sequences. The final aggregate
snapshot fingerprint was
`397364b737516d3d28d0a23752f46ce23c17a304cd57c87b15f4d1b72f7fb244`.

## Failing Acceptance: Real-Process Structured Log

The dedicated combined stdout/stderr file contained:

```text
guard lines = 15
HTTP route-release access lines = 149
work_order_route_release_request structured event lines = 0
request metadata values/body = absent
database credential = absent
complete DB rows/responses = absent
```

The endpoint source and D1 unit tests exercise `logger.info`/`logger.exception`,
but the normal `python -m mes_web`/Uvicorn process did not emit that named
application event under its real logging configuration. Uvicorn access lines
are not a substitute: they do not contain the contract's sanitized released,
error-code, duration, route/version, or client-asserted actor fields. This is a
real-process observability contract failure, so the otherwise successful smoke
cannot be reported as PASS.

No implementation/config file was changed to repair logging. Required next
work is a focused implementation fix and review that makes the sanitized event
observable under the normal process logging configuration without logging
metadata, bodies, credentials, or database rows. Phase 5H-D2 must then use a
new separately approved recovery task; this evidence must remain immutable.

## Harness Corrections

Temporary repo-external harness issues were recorded openly and did not change
production files or replace the clone/test identity:

- the launcher initially needed the repository added to `sys.path` before it
  could import; no listener or DB write occurred;
- the empty external work-order directory was reused after verifying it was
  empty;
- Windows venv shim/child PID ownership was modeled explicitly;
- actual-byte and declared-length oversize proofs were split after the unread
  tail transport reset;
- the depth payload was corrected to include all required fields;
- readback-only column names were corrected from harness guesses to schema
  `event_pk`, `release_mode`, and `route_operation_count`;
- continuations used the same exact clone and already-persisted checkpoint;
  fixtures were not repaired, reset, or silently replaced.

All pre-contract harness failures had zero endpoint write delta. One attempted
duplicate fixture insert rolled back on the existing unique key and did not
create or change a row.

## Cleanup

```text
matching task Python processes before clone drop = 0
matching listeners across observed ports = 0
clone sessions before drop = 0
clone database after drop = absent
container temp after cleanup = absent
host task temp after cleanup = absent (11 task-owned entries removed)
retained backup = present, 2911692 bytes, exact original SHA-256
mes_postgres = same container ID, running / healthy
existing HTTP health = status=ok
source cleanup/mutation = none
```

No existing container, volume, source process, retained source fixture, or
backup was removed or modified.

## Regression

Post-cleanup regression:

```text
API = 107 tests / OK
MESQL V2 = 632 tests / OK
combined = 775 tests / OK
py_compile mes_web/__main__.py + API test = PASS
```

Repository `git diff --check`, cached scope, and final docs-only commit checks
are recorded by the closure commit. No push was performed.

## Verdict

`FAIL — Phase 5H-D2`

Functional HTTP, release, replay, progression, concurrency, conflict, isolation,
side-effect, cleanup, and regression checks passed. The real process did not
emit the mandatory sanitized structured route-release event, so Phase 5H-D2 is
not complete and Phase 5H-D3 was not started.
