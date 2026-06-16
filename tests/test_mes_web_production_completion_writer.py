from __future__ import annotations

import unittest
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db import production_completion_writer
from mes_web.db.production_completion_writer import (
    PRODUCTION_COMPLETION_UPSERT_SQL,
    build_production_completion_row,
    mirror_production_completion_from_item,
)


def _item() -> dict:
    return {
        "item_id": "42",
        "work_order_id": "WO-RED-001",
        "classification": "GOOD",
        "completed_at": "2026-06-16T09:00:00+00:00",
    }


class ProductionCompletionWriterTests(unittest.TestCase):
    def test_build_row_uses_stable_external_ref(self) -> None:
        row = build_production_completion_row(_item())

        self.assertTrue(row.apply_safe)
        self.assertEqual(row.external_ref, "WO-RED-001_42")
        self.assertEqual(row.reason, "apply_safe")

    def test_dry_run_wins_over_live_flag(self) -> None:
        with patch.object(
            production_completion_writer,
            "_upsert_production_completion_row",
            side_effect=AssertionError("upsert should not be called"),
        ):
            result = mirror_production_completion_from_item(
                AppConfig(
                    db_enabled=True,
                    db_hook_production_completions=True,
                    db_hook_production_completions_dry_run=True,
                ),
                _item(),
            )

        self.assertEqual(result.reason, "dry_run_enabled")
        self.assertFalse(result.attempted)
        self.assertTrue(result.skipped)

    def test_live_writer_fail_opens_on_db_error(self) -> None:
        with patch.object(
            production_completion_writer,
            "_upsert_production_completion_row",
            side_effect=RuntimeError("db down"),
        ):
            result = mirror_production_completion_from_item(
                AppConfig(db_enabled=True, db_hook_production_completions=True),
                _item(),
            )

        self.assertEqual(result.reason, "error_fail_open")
        self.assertTrue(result.attempted)
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "RuntimeError")

    def test_live_writer_sql_preserves_external_ref_idempotency(self) -> None:
        self.assertIn("ON CONFLICT (external_ref)", PRODUCTION_COMPLETION_UPSERT_SQL)
        self.assertNotIn("delete", PRODUCTION_COMPLETION_UPSERT_SQL.lower())
        self.assertNotIn("truncate", PRODUCTION_COMPLETION_UPSERT_SQL.lower())


if __name__ == "__main__":
    unittest.main()
