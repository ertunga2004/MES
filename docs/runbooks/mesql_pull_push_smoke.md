# MESQL Pull / Push Smoke

Last updated: 2026-07-02

This runbook records the verified MESQL v2 pull, local operation, outbox, and
push smoke state. It is documentation-only and should not be read as an
instruction to change code, migrations, or Docker Compose files.

## Scope

- MESQL API reachability from `mes_web`.
- MESQL pull into the local MES DB.
- Local MES DB v2 operation start and complete.
- `integration_outbox` dry-run.
- Live MESQL push for one verified work order operation.

## Verified Result

- MESQL API was reachable from inside the `mes_web` container.
- MESQL pull completed successfully.
- Local MES DB v2 operation start completed successfully.
- Local MES DB v2 operation complete completed successfully.
- `integration_outbox` dry-run completed successfully.
- Live MESQL push completed successfully for:
  - Work order: `WO-E2E-KIRMIZI-001`
  - Operation: `10`
- Push counters:
  - `pushed_count=2`
  - `failed_count=0`
- Local outbox status became `pushed`.
- Decimal JSON-safe handling is accepted as baseline.
- Transition timestamp handling is accepted as baseline.

## Known Issues

- After MESQL operation complete, the `PACKAGING_01` successor queue is not
  created or is not visible through the queue endpoint.
- `WO-TEST-003` and `WO-E2E-MAVI-001` can revert locally after pull because
  MESQL still has older state for those orders.
- Old `WO-PKT-*` records are legacy or superseded artefacts.

## Smoke Checklist

1. Confirm MESQL API reachability from inside `mes_web`.
2. Run MESQL pull.
3. Start a local MES DB v2 operation.
4. Complete the local MES DB v2 operation.
5. Run `integration_outbox` push with `dry_run=true`.
6. Run live MESQL push only for the intended verified work order operation.
7. Confirm push counters are `pushed_count=2` and `failed_count=0`.
8. Confirm local outbox rows are marked `pushed`.
9. Check whether `PACKAGING_01` successor queue appears; current baseline says
   this remains a known issue.

## Evidence Anchor

The current clean live-push evidence is `WO-E2E-KIRMIZI-001`, operation `10`.
Use it as the baseline reference for future MESQL v2 pull / push smoke checks.

## Do Not Change During This Smoke

- Runtime code.
- Database migrations.
- Docker Compose files.
- Container configuration.
