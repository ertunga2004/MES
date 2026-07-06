# Local Successor Activation Smoke

Last updated: 2026-07-06

## Purpose

Verify that the local MES DB operation lifecycle can advance a work order from
one operation to its successor without depending on MESQL push/pull.

## Scope

This smoke is local-only:

- Local PostgreSQL `mes` schema.
- Local MES Web v2 operation start/complete endpoints.
- No MESQL pull.
- No MESQL push.
- No Docker volume deletion.
- No schema migration.

## Verified Result

The real local PostgreSQL smoke completed successfully:

```text
ASSEMBLY_01 op10 complete
-> PACKAGING_01 op20 queued
-> repeated op10 complete did not create duplicate PACKAGING_01 queue
-> PACKAGING_01 op20 start/complete
-> work_order completed
```

Smoke IDs used during verification:

```text
order_id: WO-LOCAL-SUCCESSOR-SMOKE-6d64de50
op10:     5cc64ece-b191-4d54-a788-3c9161d783f4
op20:     3dec8371-d01d-401e-a435-f441d7701e21
```

Final observed state:

```text
work_order: completed
op10 ASSEMBLY_01: completed, good_quantity=1
op20 PACKAGING_01: completed, good_quantity=1
PACKAGING_01 queue count for op20: 1
```

## API Calls Used

```powershell
Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/operations/5cc64ece-b191-4d54-a788-3c9161d783f4/complete' `
  -ContentType 'application/json' `
  -Body '{"good_quantity":1,"scrap_quantity":0,"actor_id":"local_smoke"}'

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/operations/5cc64ece-b191-4d54-a788-3c9161d783f4/complete' `
  -ContentType 'application/json' `
  -Body '{"good_quantity":1,"scrap_quantity":0,"actor_id":"local_smoke"}'

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/stations/PACKAGING_01/operations/3dec8371-d01d-401e-a435-f441d7701e21/start' `
  -ContentType 'application/json' `
  -Body '{"actor_id":"local_smoke"}'

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8080/api/v2/stations/PACKAGING_01/operations/3dec8371-d01d-401e-a435-f441d7701e21/complete' `
  -ContentType 'application/json' `
  -Body '{"good_quantity":1,"scrap_quantity":0,"actor_id":"local_smoke"}'
```

## Container Code Version Check

Use this diagnostic before repeating the smoke:

```powershell
docker exec mes_web python -c "from mes_web.db import mesql_v2; sql=getattr(mesql_v2,'SELECT_SUCCESSOR_OPERATION_SQL',''); print('has_successor_sql', bool(sql)); print('orders_by_sequence_operation', 'ORDER BY sequence_no ASC, operation_no ASC' in sql); print('skips_terminal', 'status NOT IN' in sql)"
```

Expected output:

```text
has_successor_sql True
orders_by_sequence_operation True
skips_terminal True
```

## Portable Runtime Paths

```text
Repo root:
C:\Users\ertun\Documents\.CODE\codex\MES

Docker control root:
C:\Users\ertun\Documents\.CODE\codex\MES\docker\mes

Portable runtime/data root:
C:\Users\ertun\Documents\.CODE\.DOCKER\MES
```

Runtime data:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\logs
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\work_orders
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups
```

## Guardrails

- Do not run MESQL push/pull without explicit approval.
- Do not run `docker compose down -v`.
- Do not run `docker volume rm`.
- Do not delete the `mes_postgres_data` named volume.
- Do not commit `.env`.
- Do not run migrations as part of this smoke.
