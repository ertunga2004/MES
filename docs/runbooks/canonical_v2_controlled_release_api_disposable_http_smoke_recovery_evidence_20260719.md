# Canonical V2 Controlled Route-Release API Clone Smoke Recovery Evidence

Result: `PASS / VERIFIED_FOCUSED_STRUCTURED_LOGGING_RECOVERY`

Execution date: `2026-07-19`

This focused recovery preserves the immutable Phase 5H-D2 failure evidence at
`docs/runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_evidence_20260719.md`.
It supersedes only that evidence's failed real-process structured-logging
criterion. The historical functional HTTP, parser, release, replay,
progression, concurrency, conflict, isolation, side-effect, cleanup, and
regression results remain authoritative and were not rewritten or rerun as a
149-request matrix.

## Baseline and Retry Preflight

```text
logging implementation commit = 002c326bedf01d10b1f7d2c58f76018efaae807d
logging implementation subject = fix: emit route release structured logs in real process
branch/ahead/behind = main / 9 / 0
initial tree = clean; staged 0; untracked 0; no repository operation in progress
historical evidence SHA-256 = 960af3dae624cbb56de43c0db166db43287ada62caaf878c7dc27d46631208a8
recovery evidence pre-existed = no
```

The exact existing `mes_postgres` container was already available for the
retry. No lifecycle command was needed.

```text
container ID = c5e10132d9ce26bbbaecf0ca9c5fe95020d1c0450e2f55f53c318a89ba7afa27
container state = running / healthy
restart count = 0
PostgreSQL = 16.14
host/container PostgreSQL ports = 5433 / 5432
data mount = mes_postgres_data -> /var/lib/postgresql/data
backup bind = db_backups -> /backups
```

The container ID and mounts matched the historical D2 evidence and existing
installation. No compose, recreate, restart, remove, volume, source restore,
or source backup operation occurred.

## Retained Backup

```text
path = C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_phase5hc_release_replay_recovery_20260717-080314.sql
size = 2911692 bytes
SHA-256 = f4e19c0bd8f97ff898fbc3a1de63ee0c125ee67a437de78292d74c971740e2f0
format = PostgreSQL plain dump
dump PostgreSQL version = 16.14
```

The size, header, and SHA-256 were exact before mutation, exact after the
container copy, and exact again after cleanup. No alternate dump or new source
backup was used.

## Isolation and Clone Restore

```text
clone = mes_phase5hd2_api_recovery_20260719-142719
container temp = /tmp/mes_phase5hd2_api_recovery_20260719-142719.sql
primary order = PHASE5HD2-RECOVERY-WO-20260719-142719
primary release = PHASE5HD2-RECOVERY-RELEASE-20260719-142719
actor = PHASE5HD2_RECOVERY_PLANNER
restore target = exact clone only
source database mes targeted = no
retained Phase 5H-C fixture used = no
```

The clone was created from `template0` and the retained dump was restored with
`ON_ERROR_STOP=1`. Control-plane operations targeted only database `postgres`;
all data-plane reads, fixture SQL, and writer calls targeted only the exact
clone. Processes A and B had database access disabled. No HTTP request used
port `8080` or an existing source-backed process.

Post-restore identity and shape:

```text
current_database/current_user = mes_phase5hd2_api_recovery_20260719-142719 / mes
base tables/sequences = 40 / 35
Canonical V2 route/operations = 1 / 2
OP10/OP20 configured steps = 3 / 1
binding/release sidecars = present / present
restore baseline snapshot SHA-256 = ff95b446eac495e9aaacdcfc6559c7a92e0884b7da921fc1d4eff3e35d6106e1
```

The clone-backed process received an explicit environment with the exact clone
name. A redacted `AppConfig`/connection guard returned:

```text
config DB name = mes_phase5hd2_api_recovery_20260719-142719
current_database = mes_phase5hd2_api_recovery_20260719-142719
current_user = mes
server port = 5432
```

## Real-Process Identities

Every accepted recovery process was a normal
`.venv\Scripts\python.exe -m mes_web` subprocess bound only to `127.0.0.1` on a
dynamically allocated non-8080 port.

```text
Process A disabled: port 61354; launcher PID 48988; listener PID 48628
Process B DB-disabled: port 61365; launcher PID 48188; listener PID 37856
Process C clone-backed: port 61377; launcher PID 49580; listener PID 29476
```

Before the accepted Process A run, the verification harness used the wrong
health path (`/api/health`) for one startup probe. It timed out before sending
any route-release request, was stopped with no listener or temp remainder, and
made no database connection or mutation. The harness was aligned with the
repository's `/health` test contract, the same clone/order/release identity was
retained, and the accepted A/B/C sequence below then ran once. This pre-request
probe is not counted as a route-release request or structured event.

## Structured Event Results

The exact required key set was present on every event:

```text
event, work_order_id, release_id, route_code, route_version,
released_by, released, error_code, duration_ms
```

All event lines were standalone parseable JSON, `duration_ms` was nonnegative,
and textual identities contained no control characters.

### Disabled surface

```text
HTTP = 503
body = {"detail":"WORK_ORDER_ROUTE_RELEASE_DISABLED"}
event count = 1
```

```json
{"event":"work_order_route_release_request","work_order_id":"D2-RECOVERY-DISABLED","release_id":null,"route_code":null,"route_version":null,"released_by":null,"released":null,"error_code":"WORK_ORDER_ROUTE_RELEASE_DISABLED","duration_ms":0.016}
```

### Enabled surface with database disabled

```text
HTTP = 503
body = {"detail":"DATABASE_DISABLED"}
event count = 1
```

```json
{"event":"work_order_route_release_request","work_order_id":"D2-RECOVERY-DB-DISABLED","release_id":"D2-RECOVERY-DB-DISABLED-RELEASE","route_code":"ROUTE_BOX_PACKAGING_V2","route_version":2,"released_by":"PHASE5HD2_RECOVERY_PLANNER","released":null,"error_code":"DATABASE_DISABLED","duration_ms":0.192}
```

### Clone-backed parser rejection

```text
HTTP = 400
body = {"detail":"WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID"}
event count = 1
40-table/35-sequence delta = 0 / 0
```

```json
{"event":"work_order_route_release_request","work_order_id":"D2-RECOVERY-PARSER-INVALID","release_id":null,"route_code":null,"route_version":null,"released_by":null,"released":null,"error_code":"WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID","duration_ms":0.092}
```

### First release

```text
HTTP = 200
response keys = ok/released/release/work_order/operations/bindings/initial_queue
ok/released = true / true
operations/bindings = 2 / 2
initial queue = present, OP10 only
event count = 1
```

```json
{"event":"work_order_route_release_request","work_order_id":"PHASE5HD2-RECOVERY-WO-20260719-142719","release_id":"PHASE5HD2-RECOVERY-RELEASE-20260719-142719","route_code":"ROUTE_BOX_PACKAGING_V2","route_version":2,"released_by":"PHASE5HD2_RECOVERY_PLANNER","released":true,"error_code":null,"duration_ms":97.503}
```

### Immediate exact replay

```text
HTTP = 200
ok/released = true / false
event count = 1
```

```json
{"event":"work_order_route_release_request","work_order_id":"PHASE5HD2-RECOVERY-WO-20260719-142719","release_id":"PHASE5HD2-RECOVERY-RELEASE-20260719-142719","route_code":"ROUTE_BOX_PACKAGING_V2","route_version":2,"released_by":"PHASE5HD2_RECOVERY_PLANNER","released":false,"error_code":null,"duration_ms":51.853}
```

Process C had exactly `3` structured events for its three requests. The focused
recovery had exactly `5` structured events for five route-release requests.
Duplicate events were `0`; missing events were `0`; unparseable structured
event lines were `0`. Uvicorn access lines were not used as acceptance events.

## Log Exclusion Checks

The aggregate A/B/C stdout/stderr did not contain:

```text
raw request body or complete response
metadata object, keys, or values
D2_RECOVERY_METADATA_MUST_NOT_APPEAR
log_leak_probe
database password or MES_WEB_DB_PASSWORD
PostgreSQL connection string
complete helper response or database rows
stack-trace message content
```

Only normalized identity/outcome fields from the exact structured contract
were emitted. Metadata marker present = `false`; credentials present =
`false`.

## Clone-Only Fixture and First Release

The only direct data-plane SQL created one clean clone-only work order:

```text
status/product/target = planned / PACKAGED_PRODUCT / 1
started_at/completed_at = null / null
initial row digest = dfc4ac174d927558c10aa3431a357403544014dca25bd69170984535dd5b7c48
pre-existing release/lifecycle/binding/queue/runtime = 0/0/0/0/0
```

The first HTTP release changed exactly these five tables:

```text
work_orders = count delta 0; planned -> queued row update
work_order_route_releases = +1
work_order_operations = +2
work_order_operation_route_bindings = +2
station_queue = +1
other 35 base tables = unchanged
```

Changed sequences were exactly the release PK, binding PK, and station-queue PK
sequences. Lifecycle IDs are UUIDs and did not consume a sequence.

```text
operation-set digest = 204b745b793336dbcabc8a6c0033029a8bd97f753e418de1debf20dc71cec3a4
OP10 lifecycle UUID = 5911960b-7232-52a9-a017-d6a883e44d65
OP20 lifecycle UUID = 895a8859-32f2-53a5-846b-82200e3dfb37
OP10 binding ID = BINDING-WORK-ORDER-RELEASE-99917E05-A8D9-5545-90E9-2B4740285323
OP20 binding ID = BINDING-WORK-ORDER-RELEASE-93BDA314-2386-5EF8-81F4-EACEE5A34199
initial queue PK/rank/station/status/source = 6855 / 5 / ASSEMBLY_01 / queued / work_order_release
```

The UUIDv5 lifecycle and binding identities were independently recomputed with
the committed namespaces and exact single-LF canonical name. Operations were
ordered `10/20`, statuses were `queued/planned`, stations were
`ASSEMBLY_01/PACKAGING_01`, quantities were `1/0/0`, and UOM was `piece`. The
only queue referenced the exact OP10 lifecycle UUID. Since all other 35 table
digests were unchanged, runtime states/steps/events, approval,
production-flow/completion, work-order audit, integration inbox/outbox,
FERP, package, item/inventory, location, and station-location effects were all
absent.

## Immediate Replay Zero-Write

The exact normalized path and body were sent again after the first release.
The response was `200`, `ok=true`, `released=false`.

```text
pre/post 40 base-table counts and digests = exact
pre/post 35 sequence states = exact
release row/timestamps = exact
static operation snapshots/timestamps = exact
immutable binding set = exact
initial queue row/status/rank/timestamps = exact
work-order status/timestamps = exact
aggregate snapshot SHA-256 = 1e38ba0bacb2403ebc9658e9fdbbba16b44a08f47db5ec9d3b3d8d2d218683be
```

Replay write delta was exactly zero.

## Historical and Recovery Acceptance Composition

The immutable historical D2 evidence remains authoritative for:

```text
46 HTTP/parser cases
3 concurrency scenarios
9 deterministic conflict cases
first/immediate/progressed replay
OP10/OP20 runtime progression
side-effect matrix and source isolation
historical cleanup and regression
```

This fresh focused recovery adds authoritative acceptance for:

```text
real-process structured event visibility
disabled, DB-disabled, parser-invalid, first-release, and replay events
exact structured key set and one event per request
metadata/body/credential exclusion
fresh clone first-release integrity and immediate replay zero-write
fresh cleanup and current regression
```

Together, the immutable historical functional evidence and this focused
logging recovery satisfy Phase 5H-D2. The historical FAIL record remains
unchanged; only its logging criterion is superseded.

## Cleanup

```text
all accepted launcher/listener PIDs = stopped / absent
task ports 61354/61365/61377 = no listeners
clone session count before drop = 0
clone = absent
container temp = absent
host process temp/log/client files = absent
retained backup size/SHA-256 = exact
mes_postgres = same container ID, running / healthy, restart count 0
existing port 8080 = never used or mutated by recovery
```

No source cleanup, restore, repair, adoption, or fixture deletion occurred.

## Offline Regression

```text
API = 112 / OK
MESQL V2 = 632 / OK
combined API/station-config/station-location/MESQL V2 = 780 / OK
py_compile mes_web/__main__.py and API test = PASS
git diff --check before documentation = PASS
implementation tree before documentation = clean
```

The existing FastAPI `on_event` deprecation warnings remained non-failing and
unrelated to this recovery.

## Final Decision

`PASS / VERIFIED_FOCUSED_STRUCTURED_LOGGING_RECOVERY`

Phase 5H-D2 is verified through immutable historical functional evidence plus
this focused structured-logging recovery evidence. Phase 5H-D3 was not started
and still requires separate explicit approval. No implementation, test,
configuration, migration, seed, compose, source, FERP, MESQL, or push action
was performed by this recovery.
