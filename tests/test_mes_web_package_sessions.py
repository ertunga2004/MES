"""Unit tests for mes_web.db.package_sessions shadow-write module.

These tests are intentionally offline (no real DB connection needed).
They verify that:
  - upsert_package_session_started writes status='in_progress'
  - upsert_package_session_finished writes status='finished' with all timing fields
  - upsert_package_session_cancelled writes status='cancelled'
  - missing session_id / package_order_id causes a skipped (not erroring) write
  - db_disabled config causes skipped write without touching the DB
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db import package_sessions as ps_module


# ---------------------------------------------------------------------------
# Fake DB plumbing
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.executed_params: list[object] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed_sql.append(sql)
        self.executed_params.append(params)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _enabled_config() -> AppConfig:
    return AppConfig(db_enabled=True)


def _disabled_config() -> AppConfig:
    return AppConfig(db_enabled=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class PackageSessionsUpsertTests(unittest.TestCase):

    def _run_with_fake_db(self, fn, session: dict, **kwargs):
        """Run the given upsert function with a fake DB and return (result, cursor, connection)."""
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)
        config = _enabled_config()
        with patch.object(ps_module, "database_connection", return_value=conn):
            result = fn(config, session, **kwargs)
        return result, cursor, conn

    # -- started -------------------------------------------------------------

    def test_started_sets_status_in_progress(self) -> None:
        session = {
            "session_id": "SESSION-001",
            "package_order_id": "WO-PKT-BLUE-001",
            "station_code": "PACKAGING_01",
            "started_at": "2026-06-17T13:00:00+00:00",
        }
        result, cursor, conn = self._run_with_fake_db(ps_module.upsert_package_session_started, session)

        self.assertTrue(result.attempted)
        self.assertTrue(result.success)
        self.assertTrue(conn.committed)
        params = cursor.executed_params[0]
        self.assertEqual(params["status"], "in_progress")
        self.assertEqual(params["session_id"], "SESSION-001")
        self.assertEqual(params["package_order_id"], "WO-PKT-BLUE-001")
        self.assertEqual(params["station_code"], "PACKAGING_01")
        self.assertIsNotNone(params["started_at"])
        self.assertIsNone(params["finished_at"])
        self.assertIsNone(params["duration_seconds"])

    def test_started_accepts_camelcase_keys(self) -> None:
        session = {
            "sessionId": "SESSION-CAM-001",
            "packageOrderId": "WO-PKT-RED-001",
            "stationCode": "PACKAGING_01",
            "startedAt": "2026-06-17T14:00:00+00:00",
        }
        result, cursor, _ = self._run_with_fake_db(ps_module.upsert_package_session_started, session)

        self.assertTrue(result.success)
        params = cursor.executed_params[0]
        self.assertEqual(params["session_id"], "SESSION-CAM-001")
        self.assertEqual(params["package_order_id"], "WO-PKT-RED-001")

    # -- finished ------------------------------------------------------------

    def test_finished_sets_status_finished_with_timing(self) -> None:
        session = {
            "session_id": "SESSION-002",
            "package_order_id": "WO-PKT-BLUE-001",
            "station_code": "PACKAGING_01",
            "started_at": "2026-06-17T13:00:00+00:00",
            "finished_at": "2026-06-17T13:05:30+00:00",
            "duration_seconds": 330.0,
        }
        result, cursor, conn = self._run_with_fake_db(ps_module.upsert_package_session_finished, session)

        self.assertTrue(result.success)
        self.assertTrue(conn.committed)
        params = cursor.executed_params[0]
        self.assertEqual(params["status"], "finished")
        self.assertIsNotNone(params["finished_at"])
        self.assertAlmostEqual(float(params["duration_seconds"]), 330.0)

    def test_finished_accepts_camelcase_timing_keys(self) -> None:
        session = {
            "sessionId": "SESSION-003",
            "packageOrderId": "WO-PKT-BLUE-001",
            "stationCode": "PACKAGING_01",
            "startedAt": "2026-06-17T13:00:00+00:00",
            "finishedAt": "2026-06-17T13:10:00+00:00",
            "durationSeconds": 600,
        }
        result, cursor, _ = self._run_with_fake_db(ps_module.upsert_package_session_finished, session)

        self.assertTrue(result.success)
        params = cursor.executed_params[0]
        self.assertEqual(params["status"], "finished")
        self.assertAlmostEqual(float(params["duration_seconds"]), 600.0)

    # -- cancelled -----------------------------------------------------------

    def test_cancelled_sets_status_cancelled(self) -> None:
        session = {
            "session_id": "SESSION-004",
            "package_order_id": "WO-PKT-YELLOW-001",
            "station_code": "PACKAGING_01",
            "started_at": "2026-06-17T12:00:00+00:00",
            "cancelled_at": "2026-06-17T12:02:00+00:00",
        }
        result, cursor, _ = self._run_with_fake_db(ps_module.upsert_package_session_cancelled, session)

        self.assertTrue(result.success)
        params = cursor.executed_params[0]
        self.assertEqual(params["status"], "cancelled")
        # cancelled_at should be stored in finished_at column
        self.assertIsNotNone(params["finished_at"])

    # -- missing required fields ---------------------------------------------

    def test_missing_session_id_is_skipped(self) -> None:
        session = {
            "session_id": "",
            "package_order_id": "WO-PKT-BLUE-001",
            "station_code": "PACKAGING_01",
        }
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)
        config = _enabled_config()
        with patch.object(ps_module, "database_connection", return_value=conn):
            result = ps_module.upsert_package_session_finished(config, session)

        self.assertTrue(result.skipped)
        self.assertFalse(result.attempted)
        self.assertEqual(result.reason, "missing_required_fields")
        # No SQL should have been executed
        self.assertEqual(len(cursor.executed_sql), 0)

    def test_missing_package_order_id_is_skipped(self) -> None:
        session = {
            "session_id": "SESSION-005",
            "package_order_id": "",
            "station_code": "PACKAGING_01",
        }
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)
        config = _enabled_config()
        with patch.object(ps_module, "database_connection", return_value=conn):
            result = ps_module.upsert_package_session_started(config, session)

        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "missing_required_fields")

    # -- db disabled ---------------------------------------------------------

    def test_db_disabled_skips_without_touching_db(self) -> None:
        session = {
            "session_id": "SESSION-006",
            "package_order_id": "WO-PKT-BLUE-001",
            "station_code": "PACKAGING_01",
        }
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)
        config = _disabled_config()
        with patch.object(ps_module, "database_connection", return_value=conn):
            result = ps_module.upsert_package_session_finished(config, session)

        self.assertTrue(result.skipped)
        self.assertFalse(result.attempted)
        self.assertEqual(result.reason, "db_disabled")
        self.assertEqual(len(cursor.executed_sql), 0)

    # -- station_code fallback -----------------------------------------------

    def test_station_code_defaults_to_packaging_01_when_missing(self) -> None:
        session = {
            "session_id": "SESSION-007",
            "package_order_id": "WO-PKT-BLUE-001",
            # no station_code / stationCode
        }
        result, cursor, _ = self._run_with_fake_db(ps_module.upsert_package_session_started, session)

        self.assertTrue(result.success)
        params = cursor.executed_params[0]
        self.assertEqual(params["station_code"], ps_module.PACKAGING_STATION_CODE)

    # -- SQL shape -----------------------------------------------------------

    def test_upsert_sql_contains_on_conflict_do_update(self) -> None:
        """Verify the SQL template itself includes upsert semantics."""
        self.assertIn("ON CONFLICT (session_id) DO UPDATE", ps_module.UPSERT_PACKAGE_SESSION_SQL)

    def test_upsert_sql_preserves_existing_started_at_on_conflict(self) -> None:
        """COALESCE on started_at ensures we don't overwrite an earlier value."""
        self.assertIn(
            "started_at = COALESCE(EXCLUDED.started_at, mes.package_sessions.started_at)",
            ps_module.UPSERT_PACKAGE_SESSION_SQL,
        )


if __name__ == "__main__":
    unittest.main()
