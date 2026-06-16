from __future__ import annotations

import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db.station_event_writer import (
    ASSEMBLY_STATION_CODE,
    PACKAGING_STATION_CODE,
    UPSERT_STATION_EVENT_SQL,
    build_buffer_in_station_events,
    build_completion_station_events,
    build_package_finish_station_events,
    build_package_start_station_events,
    build_station_event_row,
    format_station_event_dry_run,
    mirror_station_events_from_rows,
)
from mes_web.oee_state import _station_event_hooks


class StationEventHookTests(unittest.TestCase):
    def test_station_event_flags_default_false(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MES_WEB_DB_HOOK_STATION_EVENTS": "",
                "MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN": "",
            },
            clear=False,
        ):
            os.environ.pop("MES_WEB_DB_HOOK_STATION_EVENTS", None)
            os.environ.pop("MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN", None)
            config = AppConfig.from_env()

        self.assertFalse(config.db_hook_station_events)
        self.assertFalse(config.db_hook_station_events_dry_run)

    def test_station_event_flags_read_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MES_WEB_DB_HOOK_STATION_EVENTS": "true",
                "MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN": "true",
            },
            clear=False,
        ):
            config = AppConfig.from_env()

        self.assertTrue(config.db_hook_station_events)
        self.assertTrue(config.db_hook_station_events_dry_run)

    def test_completion_builder_emits_assembly_complete_exit(self) -> None:
        rows = build_completion_station_events(
            {
                "item_id": "42",
                "work_order_id": "WO-RED-001",
                "classification": "GOOD",
                "completed_at": "2026-06-12T10:00:00+00:00",
            }
        )

        self.assertEqual([row.event_type for row in rows], ["COMPLETE", "EXIT"])
        self.assertEqual({row.station_code for row in rows}, {ASSEMBLY_STATION_CODE})
        self.assertEqual({row.work_order_no for row in rows}, {"WO-RED-001"})
        self.assertEqual({row.serial_no for row in rows}, {"42"})
        self.assertEqual(
            {row.external_ref for row in rows},
            {
                "WO-RED-001_42:ASSEMBLY_01:COMPLETE",
                "WO-RED-001_42:ASSEMBLY_01:EXIT",
            },
        )
        self.assertTrue(all(row.apply_safe for row in rows))

    def test_buffer_in_builder_uses_upstream_external_ref(self) -> None:
        rows = build_buffer_in_station_events(
            {
                "item_id": "42",
                "upstream_order_id": "WO-RED-001",
                "upstream_external_ref": "WO-RED-001_42",
                "completed_at": "2026-06-12T10:00:00+00:00",
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_type, "BUFFER_IN")
        self.assertEqual(rows[0].station_code, ASSEMBLY_STATION_CODE)
        self.assertEqual(rows[0].external_ref, "WO-RED-001_42:ASSEMBLY_01:BUFFER_IN")

    def test_package_start_and_finish_builders_emit_packaging_events(self) -> None:
        session = {
            "session_id": "sess-1",
            "package_order_id": "WO-PKT-RED-001",
            "buffer_item_id": "42",
            "started_at": "2026-06-12T10:01:00+00:00",
            "finished_at": "2026-06-12T10:02:00+00:00",
        }
        start_rows = build_package_start_station_events(session, {"item_id": "42"})
        finish_rows = build_package_finish_station_events(
            {
                "item_id": "PKG-42-a",
                "work_order_id": "WO-PKT-RED-001",
                "package_session_id": "sess-1",
                "consumed_item_id": "42",
                "upstream_order_id": "WO-RED-001",
                "completed_at": "2026-06-12T10:02:00+00:00",
                "quality_locked": True,
                "quality_locked_at": "2026-06-12T10:02:00+00:00",
            },
            session=session,
            source_item={
                "item_id": "42",
                "work_order_id": "WO-RED-001",
                "quality_locked": True,
                "quality_locked_at": "2026-06-12T10:02:00+00:00",
            },
            buffer_row={"item_id": "42"},
        )

        self.assertEqual([row.event_type for row in start_rows], ["ENTER", "PACKAGE_START"])
        self.assertEqual({row.station_code for row in start_rows}, {PACKAGING_STATION_CODE})
        self.assertEqual(
            [row.event_type for row in finish_rows],
            ["PACKAGE_FINISH", "COMPLETE", "EXIT", "QUALITY_LOCK"],
        )
        self.assertEqual(
            [row.station_code for row in finish_rows],
            [PACKAGING_STATION_CODE, PACKAGING_STATION_CODE, PACKAGING_STATION_CODE, ASSEMBLY_STATION_CODE],
        )
        self.assertTrue(all(row.apply_safe for row in start_rows + finish_rows))

    def test_dry_run_format_and_live_writer_upserts_apply_safe_rows(self) -> None:
        row = build_completion_station_events(
            {
                "item_id": "42",
                "work_order_id": "WO-RED-001",
                "classification": "GOOD",
                "completed_at": "2026-06-12T10:00:00+00:00",
            }
        )[0]
        formatted = format_station_event_dry_run(row)
        config = AppConfig(db_enabled=True, db_hook_station_events=True)
        with patch("mes_web.db.station_event_writer._upsert_station_event_rows") as upsert:
            result = mirror_station_events_from_rows(config, [row])

        self.assertIn("[DRY_RUN:station_events]", formatted)
        self.assertIn("event_type=COMPLETE", formatted)
        self.assertEqual(result.reason, "success")
        self.assertTrue(result.attempted)
        self.assertTrue(result.success)
        self.assertFalse(result.skipped)
        upsert.assert_called_once()
        self.assertEqual(upsert.call_args.args[1], [row])

    def test_live_writer_filters_unsafe_rows_and_uses_idempotent_key(self) -> None:
        safe_row = build_completion_station_events(
            {
                "item_id": "42",
                "work_order_id": "WO-RED-001",
                "classification": "GOOD",
                "completed_at": "2026-06-12T10:00:00+00:00",
            }
        )[0]
        unsafe_row = build_station_event_row(
            event_type="UNKNOWN",
            station_code=ASSEMBLY_STATION_CODE,
            event_time="2026-06-12T10:00:00+00:00",
            source="mes_web_runtime",
            external_ref="unsafe",
        )
        config = AppConfig(db_enabled=True, db_hook_station_events=True)

        with patch("mes_web.db.station_event_writer._upsert_station_event_rows") as upsert:
            result = mirror_station_events_from_rows(config, [unsafe_row, safe_row])

        self.assertEqual(result.reason, "success")
        self.assertTrue(result.success)
        self.assertEqual(upsert.call_args.args[1], [safe_row])
        self.assertIn("ON CONFLICT (source, external_ref) DO UPDATE", UPSERT_STATION_EVENT_SQL)

    def test_live_writer_skips_when_no_apply_safe_rows(self) -> None:
        unsafe_row = build_station_event_row(
            event_type="UNKNOWN",
            station_code=ASSEMBLY_STATION_CODE,
            event_time="2026-06-12T10:00:00+00:00",
            source="mes_web_runtime",
            external_ref="unsafe",
        )
        config = AppConfig(db_enabled=True, db_hook_station_events=True)

        with patch("mes_web.db.station_event_writer._upsert_station_event_rows") as upsert:
            result = mirror_station_events_from_rows(config, [unsafe_row])

        self.assertEqual(result.reason, "no_apply_safe_rows")
        self.assertFalse(result.attempted)
        self.assertTrue(result.skipped)
        upsert.assert_not_called()

    def test_station_event_hook_is_silent_by_default_and_logs_in_dry_run(self) -> None:
        row = build_completion_station_events(
            {
                "item_id": "42",
                "work_order_id": "WO-RED-001",
                "classification": "GOOD",
                "completed_at": "2026-06-12T10:00:00+00:00",
            }
        )[0]

        silent = StringIO()
        with patch.dict(
            os.environ,
            {
                "MES_WEB_DB_ENABLED": "true",
                "MES_WEB_DB_HOOK_STATION_EVENTS": "false",
                "MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN": "false",
            },
            clear=False,
        ), redirect_stdout(silent):
            _station_event_hooks([row])

        logged = StringIO()
        with patch.dict(
            os.environ,
            {
                "MES_WEB_DB_ENABLED": "true",
                "MES_WEB_DB_HOOK_STATION_EVENTS": "false",
                "MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN": "true",
            },
            clear=False,
        ), redirect_stdout(logged):
            _station_event_hooks([row])

        self.assertEqual(silent.getvalue(), "")
        self.assertIn("[DRY_RUN:station_events]", logged.getvalue())
        self.assertIn("event_type=COMPLETE", logged.getvalue())


if __name__ == "__main__":
    unittest.main()
