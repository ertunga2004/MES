# Station Execution Event Ledger Smoke Evidence

## Summary

Runtime Engine V0 Phase 2A operation event ledger helper smoke 2026-07-09
tarihinde gerçek local PostgreSQL üzerinde PASS olarak doğrulandı.

Doğrulanan helperlar:

- `record_operation_event`
- `get_operation_event_by_idempotency_key`
- `get_operation_event_by_external_event`

Bu smoke yalnızca append-only event ledger tablosuna write yaptı:

- `mes.operation_events`

State, step, approval, production flow, work order, operation ve queue
tabloları değişmedi.

## Commit / Files

- Commit: `3072de2 "feat: add station execution event ledger helpers"`
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
3072de2 "feat: add station execution event ledger helpers"
e7a6e0d "docs: record station execution runtime init smoke"
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
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups\mes_postgres_before_event_ledger_smoke_20260709-220327.sql
```

Backup size:

```text
2889091 bytes
```

## Unit Regression

Targeted helper regression:

```text
Ran 60 tests in 0.098s

OK
```

API/helper regression:

```text
Ran 96 tests in 0.378s

OK
```

## Baseline Before

Smoke öncesi count:

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

## Smoke Target

Önceki runtime init smoke sırasında initialize edilmiş operation kullanıldı:

```text
work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808
station_code            = ASSEMBLY_01
event_source            = COLOR_SENSOR_ENTRY
external_event_id       = event-ledger-smoke-20260709-001
event_type              = evidence
```

Target state/step precheck:

```text
execution_status = ready
```

```text
COLOR_SENSOR_ENTRY_EVIDENCE   | 10 | pending
ROBOT_ARM_DROP_COMPLETED      | 20 | pending
OPERATOR_OBSERVATION_APPROVAL | 30 | pending
```

## Event Insert Smoke

İlk `record_operation_event` çağrısı sonucu:

```text
status = ok
inserted = true
event_type = evidence
station_code = ASSEMBLY_01
event_source = COLOR_SENSOR_ENTRY
external_event_id = event-ledger-smoke-20260709-001
idempotency_key = ASSEMBLY_01:COLOR_SENSOR_ENTRY:event-ledger-smoke-20260709-001
accepted = true
```

Oluşan event:

```text
event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:event-ledger-smoke-20260709-001
work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808
payload.source = event_ledger_smoke
payload.actor_id = SMOKE
payload.step_code = COLOR_SENSOR_ENTRY_EVIDENCE
event_time = 2026-07-09T19:03:51.423062+00:00
```

## Idempotency Check

Aynı helper aynı `external_event_id` ile ikinci kez çalıştırıldı.

Sonuç:

```text
status = ok
inserted = false
duplicate event yok
existing event returned
```

İkinci çağrıda yeni payload `event_ledger_smoke_duplicate` gönderilmiş olsa da
helper mevcut event’i döndürdü; DB’de duplicate row oluşmadı.

## DB Verification

Row-level verification:

```text
event_id = OP_EVENT_ASSEMBLY_01:COLOR_SENSOR_ENTRY:event-ledger-smoke-20260709-001
station_code = ASSEMBLY_01
work_order_operation_id = c8f0be13-9dc7-4e66-9fbb-43547a5f1808
event_source = COLOR_SENSOR_ENTRY
event_type = evidence
external_event_id = event-ledger-smoke-20260709-001
idempotency_key = ASSEMBLY_01:COLOR_SENSOR_ENTRY:event-ledger-smoke-20260709-001
accepted = t
rejection_reason = null
payload = {"source": "event_ledger_smoke", "actor_id": "SMOKE", "step_code": "COLOR_SENSOR_ENTRY_EVIDENCE"}
```

Count verification:

```text
event_count = 1
```

## Forbidden Mutation Verification

Smoke sonrası count:

```text
scope                  | count
-----------------------+------
execution_state        | 1
execution_steps        | 3
operation_events       | 1
operation_approvals    | 0
production_flow_events | 0
work_orders            | 12
work_order_operations  | 8
station_queue          | 13
```

Baseline karşılaştırması:

- `operation_events`: `0 -> 1`
- `work_order_operation_execution_state`: unchanged, `1`
- `work_order_operation_steps`: unchanged, `3`
- `operation_approvals`: unchanged, `0`
- `production_flow_events`: unchanged, `0`
- `work_orders`: unchanged, `12`
- `work_order_operations`: unchanged, `8`
- `station_queue`: unchanged, `13`

## Cleanup / Retention

Cleanup yapılmadı.

Smoke event kaydı append-only ledger içinde bırakıldı:

- `external_event_id = event-ledger-smoke-20260709-001`
- `idempotency_key = ASSEMBLY_01:COLOR_SENSOR_ENTRY:event-ledger-smoke-20260709-001`

Bu event step start/finish state mutation değildir. Sonraki step start/finish
smoke için duplicate/idempotency referansı olarak kullanılabilir.

## Guardrails

- Only `mes.operation_events` write yapıldı.
- Execution state update yok.
- Step state update yok.
- Approval write yok.
- Production flow write yok.
- `work_orders` mutation yok.
- `work_order_operations` mutation yok.
- `station_queue` mutation yok.
- Config/master/location tablolarına write yok.
- Step start helper yok.
- Step finish helper yok.
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
