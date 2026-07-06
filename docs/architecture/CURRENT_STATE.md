# Current State

Last updated: 2026-07-02

## MESQL v2 Integration Baseline

This document records the current verified MESQL v2 integration state for the
local MES Web / MES DB prototype. It is a documentation snapshot only; it does
not define a migration or compose change.

## Verified State

- MESQL API is reachable from inside the `mes_web` container.
- MESQL pull works.
- Local MES DB v2 operation start and complete work.
- `integration_outbox` dry-run works.
- Live MESQL push succeeded for `WO-E2E-KIRMIZI-001`, operation `10`.
- Live push result: `pushed_count=2`, `failed_count=0`.
- Local outbox status changed to `pushed`.
- The Decimal JSON-safe fix is accepted as part of the current baseline.
- The transition timestamp fix is accepted as part of the current baseline.

## Known Issues

- After MESQL operation complete, the `PACKAGING_01` successor queue is not
  created or is not visible through the queue endpoint.
- `WO-TEST-003` and `WO-E2E-MAVI-001` can return to an older local state after
  pull because of older MESQL state.
- Old `WO-PKT-*` records are legacy or superseded artefacts.

## Operational Notes

- Treat `WO-E2E-KIRMIZI-001` operation `10` as the verified live push evidence.
- Treat old `WO-PKT-*` records as non-authoritative when validating the current
  MESQL v2 flow.
- Avoid using `WO-TEST-003` and `WO-E2E-MAVI-001` as clean-state proof unless
  the MESQL-side historical state has been reset or explicitly accounted for.

## Change Guardrail

For this checkpoint, no runtime code, database migration, Docker Compose file,
or container configuration change is required.
