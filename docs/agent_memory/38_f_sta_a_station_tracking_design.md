# 38. F-STA-A Station Tracking Design

## 1. Purpose

F-STA-A defines the first safe PostgreSQL design for station-level item movement history.

The current MESQL runtime can write `mes.production_completions`, but that table only records the production result. It does not answer when an item entered a station, exited a station, moved into or out of a buffer, started or finished package flow, or became quality locked.

This document is design only:

- No migration was added or executed.
- No runtime flag was changed.
- No DB write path was added.
- PostgreSQL is still not source-of-truth.
- Runtime JSON, Excel, FERP, MQTT, and package flow behavior remain authoritative for the live application.

## 2. Current Evidence

Relevant current-state findings:

- `db/migrations/001_initial_mes_schema.sql` already defines `mes.stations`.
- `mes.stations.station_code` currently has a partial unique index:
  - `ux_mes_stations_station_code`
  - `WHERE station_code IS NOT NULL`
- `mes.item_station_events` does not exist yet.
- `mes_web/oee_state.py` package finish already emits station metadata inside the package item payload:
  - `station_code = "PACKAGING_01"`
  - `station_name = "Istasyon 2 - Paketleme"`
  - `upstream_station_code = "ASSEMBLY_01"`
  - `upstream_station_name = "Istasyon 1 - Montaj"`
- `docs/agent_memory/36_package_finish_live_hook_bridge.md` explicitly leaves station tracking as a separate future phase.
- `mes_web/masterdata.py` default station list is currently kiosk-oriented (`KSK-01`), not the physical process station master proposed here.

## 3. Boundary

`production_completions` and station tracking must remain separate.

`mes.production_completions` means result:

- one completed production/package item
- final classification
- completion timestamp
- work order relation
- payload/metadata describing the completion

`mes.item_station_events` means process history:

- station entry
- station exit
- buffer movement
- package lifecycle steps
- quality lock events
- station duration derivable from ordered events

One production completion may relate to many station events. Station events must not be collapsed into the completion row.

## 4. Station Master Model

Use the existing `mes.stations` table as the station master target.

Minimum physical process station seed candidates:

| station_code | station_name | active |
|---|---|---|
| `ASSEMBLY_01` | `Istasyon 1 - Montaj` | `true` |
| `PACKAGING_01` | `Istasyon 2 - Paketleme` | `true` |

Recommended semantics:

- `station_code` is the stable domain key used by runtime payloads and station events.
- `station_name` is display text and can change without changing historical event meaning.
- `active=false` should prevent new routing/use later, but must not invalidate historical events.

Important FK note:

The current partial unique index on `mes.stations(station_code)` is useful for duplicate prevention, but it is not a clean FK target unless `station_code` is hardened as a non-null unique key. F-STA-B must choose one of these:

1. Harden `mes.stations.station_code` to `NOT NULL` plus a full unique constraint, then add a DB FK.
2. Keep station events with a soft station-code reference first, then add the FK in a later hardening phase.

For MVP safety, option 2 is lower risk because it avoids changing existing station master constraints during the first station event design.

## 5. Station Event Model

Proposed table name:

```text
mes.item_station_events
```

Purpose:

Immutable append/upsert event log for item movement through stations.

Draft columns:

| Column | Type | Required | Meaning |
|---|---|---:|---|
| `item_station_event_pk` | `BIGSERIAL` | yes | Surrogate DB key |
| `event_type` | `TEXT` | yes | Controlled event type |
| `station_code` | `TEXT` | yes | Station domain key |
| `work_order_no` | `TEXT` | no | Runtime/FERP work order number |
| `package_id` | `TEXT` | no | Package item id, e.g. `PKG-*` |
| `serial_no` | `TEXT` | no | Physical/logical item id when available |
| `event_time` | `TIMESTAMPTZ` | yes | Time the movement event happened |
| `source` | `TEXT` | yes | Logical producer of the event |
| `external_ref` | `TEXT` | yes for live hook | Idempotency key within the source |
| `source_file` | `TEXT` | no | Runtime path/context, e.g. `runtime_hook` |
| `payload` | `JSONB` | yes | Original event/item shape |
| `metadata` | `JSONB` | yes | Hook version, derivation, policy data |
| `created_at` | `TIMESTAMPTZ` | yes | DB insert time |

Recommended defaults:

```sql
payload JSONB NOT NULL DEFAULT '{}'::jsonb
metadata JSONB NOT NULL DEFAULT '{}'::jsonb
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

## 6. Event Types

Initial allowed event types:

| event_type | Meaning |
|---|---|
| `ENTER` | Item enters a station |
| `EXIT` | Item exits a station |
| `COMPLETE` | Station-level work is complete |
| `BUFFER_IN` | Item enters a station/buffer queue |
| `BUFFER_OUT` | Item leaves a station/buffer queue |
| `PACKAGE_START` | Packaging session starts |
| `PACKAGE_FINISH` | Packaging session produces a package item |
| `QUALITY_LOCK` | Item quality state becomes locked against later override |

MVP policy:

- Store event types as `TEXT` first for migration simplicity.
- Enforce allowed values in application/dry-run validation first.
- Add a DB `CHECK` constraint only after F-STA-B finalizes whether the event type list is stable.

## 7. Example Flow Mapping

Assembly item flow:

```text
ASSEMBLY_01: ENTER -> COMPLETE -> EXIT
```

Packaging item flow:

```text
PACKAGING_01: ENTER -> PACKAGE_START -> PACKAGE_FINISH -> COMPLETE -> EXIT
```

Quality lock relation:

```text
ASSEMBLY_01 or PACKAGING_01: QUALITY_LOCK
```

For the current package flow, the package completion item already carries both packaging and upstream station fields. A future station hook can derive:

- `PACKAGE_FINISH` on `PACKAGING_01`
- `COMPLETE` on `PACKAGING_01`
- `QUALITY_LOCK` for the consumed upstream item

ENTER/EXIT events need a more explicit runtime trigger than the current completion hook gives. They should not be invented from `production_completions` unless the derivation is clearly marked as backfill/derived metadata.

## 8. Idempotency

Logical idempotency key:

```text
(source, external_ref)
```

Recommended source values:

| source | Use |
|---|---|
| `mes_web_runtime` | Live runtime hook generated from application state |
| `mes_web_backfill` | Controlled historical reconstruction from runtime JSON |
| `mes_web_package_flow` | Package lifecycle event generation if split from generic runtime |
| `manual_seed` | Station master/data seed, not runtime events |

`external_ref` policy examples:

| Event | external_ref draft |
|---|---|
| Assembly enter | `{item_id}:ASSEMBLY_01:ENTER:{event_time_or_event_key}` |
| Assembly complete | `{work_order_no}_{item_id}:ASSEMBLY_01:COMPLETE` |
| Packaging start | `{package_session_id}:PACKAGING_01:PACKAGE_START` |
| Packaging finish | `{package_session_id}:{package_id}:PACKAGING_01:PACKAGE_FINISH` |
| Quality lock | `{item_id}:QUALITY_LOCK:{quality_locked_at}` |

For live hooks, `external_ref` should be mandatory. A missing or blank `external_ref` should be skipped in the writer rather than inserted without idempotency.

## 9. Draft SQL Shape

This is a draft for a future migration, not applied in F-STA-A.

```sql
CREATE TABLE IF NOT EXISTS mes.item_station_events (
    item_station_event_pk BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    station_code TEXT NOT NULL,
    work_order_no TEXT,
    package_id TEXT,
    serial_no TEXT,
    event_time TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    source_file TEXT,
    external_ref TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_station_code
    ON mes.item_station_events (station_code);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_event_time
    ON mes.item_station_events (event_time);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_work_order_no
    ON mes.item_station_events (work_order_no);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_package_id
    ON mes.item_station_events (package_id);

CREATE INDEX IF NOT EXISTS ix_mes_item_station_events_external_ref
    ON mes.item_station_events (external_ref);

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_item_station_events_source_external_ref
    ON mes.item_station_events (source, external_ref)
    WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '';
```

Optional later FK after station master hardening:

```sql
ALTER TABLE mes.item_station_events
ADD CONSTRAINT fk_mes_item_station_events_station_code
FOREIGN KEY (station_code)
REFERENCES mes.stations (station_code);
```

Do not add the FK until `mes.stations.station_code` is a reliable non-null unique key.

## 10. Runtime Hook Strategy

Recommended phased path:

1. F-STA-A: design only.
2. F-STA-B: decide open semantics and constraints.
3. F-STA-C: add migration for `mes.item_station_events` and optional station seed.
4. F-STA-D: add dry-run station event builder/writer with no DB writes.
5. F-STA-E: run controlled dry-run observation against package and assembly flows.
6. F-STA-F: enable live hook only behind explicit flags after idempotency checks.

Future flags should follow the existing fail-open pattern:

```text
MES_WEB_DB_HOOK_ITEM_STATION_EVENTS_DRY_RUN=false
MES_WEB_DB_HOOK_ITEM_STATION_EVENTS=false
```

The station hook must not reuse `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS`. It is a separate write surface.

## 11. F-STA-B Decision Recommendations

1. Is `station_code` enough?
   - Recommendation: yes for MVP. Keep station hierarchy, equipment id, line topology, and multi-site out of scope.

2. Is `source` required?
   - Recommendation: yes. It is half of the idempotency key and distinguishes runtime, backfill, and package-derived events.

3. Is `external_ref` required?
   - Recommendation: yes for live writes. For any historical/import analysis, missing `external_ref` rows should be dry-run skipped until a stable key is available.

4. Should `COMPLETE` be used at every station?
   - Recommendation: yes when the station has meaningful completion work. Do not force it for pure pass-through stations in future phases.

5. Should `QUALITY_LOCK` become lock/unlock?
   - Recommendation: no for MVP. Keep only `QUALITY_LOCK`; add unlock/reopen only if a real rework workflow is designed.

6. How should event ordering work?
   - Recommendation: order primarily by `event_time`, then `created_at`, then `item_station_event_pk`. Add a later sequence column only if equal timestamps become a demonstrated problem.

## 12. Out of Scope

F-STA-A does not design or implement:

- OEE recalculation from station events
- shift model
- routing engine
- rework workflow
- station hierarchy
- multi-site support
- UI station timeline
- PostgreSQL read transition
- automatic DB source-of-truth switch

## 13. Completion Criteria For The Next Implementation Phase

Before any F-STA-C migration is applied:

- F-STA-B decisions must be accepted or amended.
- The station master FK strategy must be chosen.
- The live runtime event source points must be identified in code.
- Dry-run behavior must be specified for missing `station_code`, missing `event_time`, and missing `external_ref`.
- No station event live write flag should be enabled by default.
