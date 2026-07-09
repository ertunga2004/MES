# Station Execution Runtime Init Smoke Evidence

## Summary

Runtime Engine V0 Phase 1 initialize helper smoke 2026-07-09 tarihinde gerçek
local PostgreSQL üzerinde PASS olarak doğrulandı.

Doğrulanan helperlar:

- `initialize_execution_state`
- `get_execution_state`
- `list_execution_steps`

Bu smoke sadece V0 allowed runtime tablolarına write yaptı:

- `mes.work_order_operation_execution_state`
- `mes.work_order_operation_steps`

İlk `docker exec mes_web python ...` denemesi import aşamasında durdu çünkü
çalışan `mes_web` container image içindeki kod henüz
`initialize_execution_state` helperını içermiyordu. Bu deneme DB write
yapmadı; runtime table count kontrolü `execution_state = 0` ve
`execution_steps = 0` olarak kaldı.

Smoke, Docker image rebuild yapmadan host `.venv` içindeki güncel committed
helper kodu ile gerçek PostgreSQL portu `127.0.0.1:5433` üzerinden
çalıştırıldı.

## Commit / Files

- Commit: `80ac95a "feat: add station execution runtime init helpers"`
- Önceki plan commit: `ad16153 "docs: plan station execution runtime engine v0"`
- Helper implementation:
  - `mes_web/db/mesql_v2.py`
- Unit tests:
  - `tests/test_mes_web_mesql_v2.py`

Precheck:

```text
## main...origin/main
```

Son log:

```text
80ac95a "feat: add station execution runtime init helpers"
ad16153 "docs: plan station execution runtime engine v0"
5aed9b3 "docs: verify station execution config api flag wiring"
809c12a chore: wire station execution config api feature flag
03cfd2e "docs: record station execution config api smoke"
116ef77 "feat: add station execution config read api"
2109537 "docs: design station execution config read api"
732592e "docs: record station execution config read smoke"
```

## Backup

Backup file:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_runtime_init_smoke_20260709-214819.sql
```

Backup size:

```text
2887257 bytes
```

Not: İlk backup denemesinde uzun yol tablo formatı nedeniyle `Length`
görüntüsü yanıltıcı okundu. Geçerli backup dosyasının içeriği `pg_dump`
başlığı ile doğrulandı ve byte boyutu doğrudan `.Length` property değeriyle
kaydedildi.

## Unit Regression

Targeted helper regression:

```text
Ran 49 tests in 0.093s

OK
```

API/helper regression:

```text
Ran 85 tests in 0.361s

OK
```

## Baseline Before

Smoke öncesi count:

```text
scope                  | count
-----------------------+------
execution_state        | 0
execution_steps        | 0
operation_events       | 0
operation_approvals    | 0
production_flow_events | 0
work_orders            | 12
work_order_operations  | 8
station_queue          | 13
```

## Selected Operation

Mevcut `ASSEMBLY_01` operation adayları içinden yeni work order veya operation
oluşturmadan şu kayıt seçildi:

```text
work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808
order_id                = WO-E2E-MAVI-001
operation_code          = OP-ASSEMBLY
station_code            = ASSEMBLY_01
status                  = queued
route_operation_id      = ROUTE_BOX_PACKAGING_V1_OP10
```

## Initialize Smoke

İlk başarılı initialize çağrısı sonucu:

```text
status = ok
initialized = true
execution_state.execution_status = ready
execution_state.operation_completion_policy = auto_complete_pending_approval
steps count = 3
step statuses = pending, pending, pending
```

Oluşan execution state:

```text
execution_state_id       = EXEC_STATE_c8f0be13-9dc7-4e66-9fbb-43547a5f1808
work_order_operation_id  = c8f0be13-9dc7-4e66-9fbb-43547a5f1808
work_order_id            = WO-E2E-MAVI-001
station_code             = ASSEMBLY_01
operation_code           = OP10_ASSEMBLY_CLASSIFICATION
execution_status         = ready
created_at               = 2026-07-09T18:51:14.733110+00:00
```

Oluşan steps:

```text
COLOR_SENSOR_ENTRY_EVIDENCE   | 10 | pending
ROBOT_ARM_DROP_COMPLETED      | 20 | pending
OPERATOR_OBSERVATION_APPROVAL | 30 | pending
```

## Idempotency Check

Aynı helper aynı `work_order_operation_id` ile ikinci kez çalıştırıldı.

Sonuç:

```text
status = ok
initialized = false
execution_state_count = 1
steps count = 3
duplicate state yok
duplicate step yok
```

## DB Verification

Row-level verification:

```text
execution_state_count = 1
```

Step verification:

```text
step_code                       | step_no | status
--------------------------------+---------+--------
COLOR_SENSOR_ENTRY_EVIDENCE     | 10      | pending
ROBOT_ARM_DROP_COMPLETED        | 20      | pending
OPERATOR_OBSERVATION_APPROVAL   | 30      | pending
```

Forbidden event/approval/flow verification:

```text
operation_events_count = 0
approvals_count        = 0
production_flow_count  = 0
```

## Forbidden Mutation Verification

Smoke sonrası count:

```text
scope                  | count
-----------------------+------
execution_state        | 1
execution_steps        | 3
operation_events       | 0
operation_approvals    | 0
production_flow_events | 0
work_orders            | 12
work_order_operations  | 8
station_queue          | 13
```

Baseline karşılaştırması:

- `work_order_operation_execution_state`: `0 -> 1`
- `work_order_operation_steps`: `0 -> 3`
- `operation_events`: unchanged, `0`
- `operation_approvals`: unchanged, `0`
- `production_flow_events`: unchanged, `0`
- `work_orders`: unchanged, `12`
- `work_order_operations`: unchanged, `8`
- `station_queue`: unchanged, `13`

## Cleanup / Retention

Cleanup yapılmadı.

Smoke kayıtları V0 allowed runtime tablolarında bırakıldı:

- `work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808`
- Bu kayıtlar sonraki Runtime Engine V0 step start/finish smoke için tekrar
  kullanılabilir.

## Guardrails

- Allowed V0 tablolar dışında write yapılmadı.
- `mes.work_orders` write yok.
- `mes.work_order_operations` write yok.
- `mes.station_queue` write yok.
- `mes.operation_events` write yok.
- `mes.operation_approvals` write yok.
- `mes.production_flow_events` write yok.
- Config/master/location tablolarına write yok.
- Start/finish helper yok.
- Approval helper yok.
- API route yok.
- Kiosk yok.
- IoT yok.
- OEE yok.
- MESQL push/pull yok.
- Seed/migration apply yok.
- `docker compose down -v` yok.
- Docker volume silme yok.
- Commit/push yok.
- `.agents/` dokunulmadı.

## Result

PASS.
