# Canonical V2 Controlled Route-Release API Source HTTP Smoke Evidence

Result: `PASS / VERIFIED_SOURCE_PROGRESSED_REPLAY_ZERO_WRITE`

Execution date: `2026-07-19`

This is the final controlled HTTP smoke for the Phase 5H-D route-release API
chain. It sent exactly one progressed replay for the previously verified,
completed, explicitly nonproduction Phase 5H-C fixture. It created no new work
order, release, lifecycle, binding, queue, runtime, event, or other source
artifact.

## Baseline and Prior Acceptance

```text
HEAD = 15485d44f665c963a3aa255894c93404db0b0730
subject = docs: record controlled route release api clone smoke recovery
branch/ahead/behind = main / 10 / 0
initial tree = clean; staged 0; untracked 0; no repository operation in progress
D3 evidence pre-existed = no
```

Phase 5H-D1 implementation baseline is
`9544d9272968b69144c1786ef08836af64454cde`; real-process logging fix is
`002c326bedf01d10b1f7d2c58f76018efaae807d`. The immutable historical D2
functional evidence and focused D2 structured-logging recovery evidence remain
unchanged and authoritative. Their combined result is
`PASS / VERIFIED_FOCUSED_STRUCTURED_LOGGING_RECOVERY`.

Read-only normative and historical references were verified before source
work. None was modified by the smoke:

```text
docs/architecture/canonical_v2_controlled_release_entrypoint_design.md
docs/architecture/canonical_v2_controlled_release_api_contract.md
docs/runbooks/canonical_v2_controlled_release_api_smoke_plan.md
docs/runbooks/canonical_v2_source_local_functional_smoke_evidence_20260715.md
docs/runbooks/canonical_v2_source_local_release_replay_recovery_evidence_20260717.md
docs/runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_evidence_20260719.md
docs/runbooks/canonical_v2_controlled_release_api_disposable_http_smoke_recovery_evidence_20260719.md
```

## Source Identity and Quiescence

```text
container = mes_postgres
container ID = c5e10132d9ce26bbbaecf0ca9c5fe95020d1c0450e2f55f53c318a89ba7afa27
container state = running / healthy
container restart count = 0
database/user = mes / mes
PostgreSQL = 16.14
host/container port = 5433 / 5432
```

The exact container ID, volume, backup bind, and port mapping matched prior
evidence. No container lifecycle command was needed. Compose, recreate,
restart, remove, volume mutation, source restore, repair, adoption, and fixture
mutation were not performed.

`pg_stat_activity` checks found zero other source `mes` sessions:

```text
initial preflight = 0
accepted REPEATABLE READ READ ONLY pre-snapshot = 0
immediately before HTTP replay = 0
post-process cleanup = 0
```

No active query, active transaction, idle-in-transaction session, or external
writer was present. No session was terminated.

## Byte-Safe Pre-Source Backup

The backup was created inside the existing container with `pg_dump -Fp -f`;
PowerShell native redirection was not used.

```text
container temp = /tmp/mes_before_phase5hd3_source_http_replay_20260719-145108.sql
retained host path = C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_before_phase5hd3_source_http_replay_20260719-145108.sql
container size = 2911692 bytes
host size = 2911692 bytes
container SHA-256 = e43334eef0859ac0cebeec6fb694e1aa48d8261ad3db4abd8f20182fa471592e
host SHA-256 = e43334eef0859ac0cebeec6fb694e1aa48d8261ad3db4abd8f20182fa471592e
format = PostgreSQL plain dump
```

Container and host bytes were exact. The container temp was removed after the
smoke; the host backup remains retained. No restore was executed.

## Authoritative Retained Fixture Preflight

The accepted source baseline was one `REPEATABLE READ READ ONLY` transaction
using deterministic MD5 over ordered JSONB rows with exact `|` separators and
independent sequence-state reads.

```text
base tables/sequences = 40 / 35
aggregate table/sequence snapshot SHA-256 = ff95b446eac495e9aaacdcfc6559c7a92e0884b7da921fc1d4eff3e35d6106e1
complete fixture snapshot SHA-256 = c124bf35e3be90e0195ce63a6fb02ea7a93bf030e8ef3fdd1614510a2c13c1fc
protected audit/outbox/package/inventory snapshot SHA-256 = de619f140ef4f48cd3a0860c2be9cd02ca887a3dfcebaf2c9f2250fc57682c66
```

Exact retained identity:

```text
work order = PHASE5HC-SOURCE-SMOKE-20260715-181940
release = PHASE5HC-SOURCE-RELEASE-20260715-181940
actor = PHASE5HC_SOURCE_SMOKE
route/version = ROUTE_BOX_PACKAGING_V2 / 2
work-order state = completed
completed_at = 2026-07-15T18:35:41.238660+00:00
release digest = 8cb642eb8c2db238adf59891fb30aac5b1673ec16de6da2a4a10a5d04338cba9
```

Persisted fixture counts and identities were exact:

```text
work order/release/lifecycle/bindings = 1/1/2/2
queues/runtime states/runtime steps/operation events = 2/2/4/6
OP10 UUID = 52fb8cd4-005e-51f2-9557-a6ff31ce5063
OP20 UUID = d78c3f30-9e49-51a3-ad58-a13e45f3705f
OP10 queue = PK 6853 / completed / work_order_release
OP20 queue = PK 6854 / completed / runtime_completion_bridge
runtime states = both closed
runtime steps = all completed
```

Release actor, route/version, operation count, and exact metadata object matched
the retained Phase 5H-C request. Fixture-scoped system-transition events,
approvals, production flow/completion, work-order audit events,
integration/FERP inbox/outbox, package rows, item-station events, and vision
events were all `0`.

Configuration was exact:

```text
V1 route = 1 / 163f416bfdcf16ca469e43adbd47b324
V1 operations = 2 / 92a859fc57182954c5070670928c89e6
V1 steps = 5 / 3829d1b0a5185a4ac59a509532b4abc8
V2 route/operations/steps = 1/2/4
```

No mismatch or partial retained state required repair.

## Isolated Source HTTP Process

The existing HTTP process/container was not used or modified. A separate
normal repository subprocess ran:

```text
command = .venv\Scripts\python.exe -m mes_web
bind = 127.0.0.1:59030
launcher PID = 47276
listener PID = 17312
configured/current database = mes / mes
route-release feature flag = true
GET /health = 200 / status=ok
```

All database mirror/write hooks, observer reads, Excel/publish/manual/vision
surfaces, and external runtime paths were disabled or redirected to
task-specific temporary paths. MQTT used unused loopback. The password was
passed only through process environment and was never written to a command
line, repository file, log, response, or evidence.

## Exact Progressed Replay Request

Exactly one route-release POST was sent; it was not retried and no alternate
identity was used.

```text
path = /api/v2/work-orders/PHASE5HC-SOURCE-SMOKE-20260715-181940/route-release
request count = 1
HTTP status = 200
response keys = ok/released/release/work_order/operations/bindings/initial_queue
ok/released = true / false
work-order status = completed
operations = exact OP10/OP20 UUIDs
bindings = exact two immutable bindings
initial queue = retained OP10 queue PK 6853
```

The response's release, work order, operations, bindings, and initial queue
were exact-equal to a separate authoritative
`get_work_order_release_snapshot` readback.

## Structured Log Acceptance

The normal process emitted exactly one standalone, parseable JSON event with
the exact nine-key contract:

```json
{"event":"work_order_route_release_request","work_order_id":"PHASE5HC-SOURCE-SMOKE-20260715-181940","release_id":"PHASE5HC-SOURCE-RELEASE-20260715-181940","route_code":"ROUTE_BOX_PACKAGING_V2","route_version":2,"released_by":"PHASE5HC_SOURCE_SMOKE","released":false,"error_code":null,"duration_ms":95.382}
```

```text
matching event count = 1
duplicate events = 0
unparseable event lines = 0
duration_ms >= 0 = true
```

The aggregate process log contained no raw body, metadata keys/values,
database password, password variable, connection string, complete response,
database rows, or stack trace. Uvicorn access output was not counted as the
structured event.

## Post-Request Source Integrity

A new independent `REPEATABLE READ READ ONLY` snapshot was taken immediately
after the single HTTP response.

```text
pre snapshot SHA-256 = ff95b446eac495e9aaacdcfc6559c7a92e0884b7da921fc1d4eff3e35d6106e1
post snapshot SHA-256 = ff95b446eac495e9aaacdcfc6559c7a92e0884b7da921fc1d4eff3e35d6106e1
table counts = 40/40 exact
table digests = 40/40 exact
sequence states = 35/35 exact
complete retained fixture = exact
Canonical V2/V1 config = exact
protected audit/outbox/package/inventory scope = exact
source write delta = 0
```

Work-order, release, lifecycle, binding, queue, runtime, step, and event rows
and all timestamps/statuses/ranks/sources remained exact. No operation/system
transition, approval, production-flow/completion, work-order audit,
integration/FERP inbox/outbox, package, item/inventory, location,
station-location, or config/master side effect occurred.

The authoritative full-table/sequence/fixture equality proves that no writer
artifact, queue-rank allocation, timestamp update, or sequence consumption
occurred on replay. No production instrumentation or monkeypatch was added.

## Cleanup

```text
launcher/child process = stopped / absent
port 59030 listener = absent
task runtime/temp paths = absent
source sessions after cleanup = 0
container backup temp = absent
host backup = retained with exact size/SHA-256
mes_postgres = same container ID, running / healthy, restart count 0
retained fixture = unchanged
```

No source cleanup, compensation, repair, delete, restore, or second replay was
performed.

## Offline Regression

```text
API = 112 / OK
MESQL V2 = 632 / OK
combined API/station-config/station-location/MESQL V2 = 780 / OK
py_compile mes_web/__main__.py and API test = PASS
git diff --check before documentation = PASS
implementation tree before documentation = clean
```

The existing FastAPI `on_event` deprecation warnings were non-failing and
unrelated to this smoke.

## Final Decision

`PASS / VERIFIED_SOURCE_PROGRESSED_REPLAY_ZERO_WRITE`

Phase 5H-D1/D2/D3 controlled route-release API chain is complete. This task
did not start station execution integration, MQTT/automatic events,
Kiosk/manual actions, product entry/exit tracking, operation-step execution,
FERP/MESQL integration, or any other next phase.
