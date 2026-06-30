# MESQL V2 Integration Smoke

This runbook is for the local MES Web plus local MES DB edge flow. It does not
drop data and does not reset Docker volumes.

## Preconditions

- `mes_postgres` is running.
- `mes_web` is running with code that includes the v2 endpoints.
- MESQL API is reachable at `http://ferptop:8090`.
- Apply `db/migrations/008_mesql_integration_v2.sql` manually before v2 DB writes.

## Contract Checks

```powershell
Invoke-RestMethod -Uri 'http://ferptop:8090/openapi.json' -TimeoutSec 10
Invoke-RestMethod -Uri 'http://ferptop:8090/api/v1/mes/stations/ASSEMBLY_01/queue' -TimeoutSec 10
Invoke-RestMethod -Uri 'http://ferptop:8090/api/v1/mes/stations/PACKAGING_01/queue' -TimeoutSec 10
```

MESQL operation push bodies are:

```json
{
  "order_id": "WO-E2E-MAVI-001",
  "operation_no": 10,
  "operator_id": "operator_mvp",
  "station_code": "ASSEMBLY_01",
  "started_at": "2026-06-30T12:00:00+00:00"
}
```

```json
{
  "order_id": "WO-E2E-MAVI-001",
  "operation_no": 10,
  "operator_id": "operator_mvp",
  "station_code": "ASSEMBLY_01",
  "good_quantity": 1,
  "scrap_quantity": 0,
  "uom_code": "ADET",
  "completed_at": "2026-06-30T12:05:00+00:00"
}
```

## Local V2 Smoke

Pull from MESQL into the local MES DB:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/integration/mesql/pull' `
  -ContentType 'application/json' `
  -Body '{"stations":["ASSEMBLY_01","PACKAGING_01"],"dry_run":false}'
```

Read the DB-authoritative queue:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/queue'
```

Start an operation:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/operations/<work_order_operation_id>/start' `
  -ContentType 'application/json' `
  -Body '{"actor_id":"operator_mvp"}'
```

Complete an operation:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/operations/<work_order_operation_id>/complete' `
  -ContentType 'application/json' `
  -Body '{"good_quantity":1,"scrap_quantity":0,"actor_id":"operator_mvp","classification":"good","metadata":{}}'
```

Dry-run push pending outbox events:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/integration/mesql/push' `
  -ContentType 'application/json' `
  -Body '{"limit":50,"dry_run":true}'
```

## DB Verification

```sql
SELECT order_id, status, started_at, completed_at
FROM mes.work_orders
WHERE order_id = 'WO-E2E-MAVI-001';

SELECT work_order_operation_id, order_id, operation_no, station_code, status, started_at, completed_at
FROM mes.work_order_operations
WHERE order_id = 'WO-E2E-MAVI-001'
ORDER BY operation_no;

SELECT station_code, queue_rank, order_id, work_order_operation_id, status
FROM mes.station_queue
WHERE order_id = 'WO-E2E-MAVI-001'
ORDER BY station_code, queue_rank;

SELECT order_id, event_type, event_at
FROM mes.work_order_events
WHERE order_id = 'WO-E2E-MAVI-001'
ORDER BY event_pk;

SELECT event_type, status, payload
FROM mes.integration_outbox
ORDER BY created_at DESC
LIMIT 10;
```

## Legacy Kiosk Migration Note

Keep the legacy kiosk UI on the existing endpoints until the v2 smoke is stable.
The lowest-risk UI migration is a separate change that reads
`GET /api/v2/stations/{station_code}/queue` for the work-order list and calls the
v2 start endpoint with `work_order_operation_id`. The likely files are
`mes_web/static/kiosk.js`, `mes_web/app.py`, and focused kiosk tests.
