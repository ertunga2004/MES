from __future__ import annotations

import unittest
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.db import work_order_transition_writer
from mes_web.db.work_order_transition_writer import (
    UPSERT_WORK_ORDER_EVENT_SQL,
    build_work_order_transition_event_rows,
    mirror_work_order_transition_from_state,
)


def _state(status: str = "active") -> dict:
    return {
        "lastUpdatedAt": "2026-06-16T09:05:30+00:00",
        "workOrders": {
            "source": {
                "folder": "C:/ferp",
                "file": "ferp_work_orders.json",
                "loadedAt": "2026-06-16T09:00:00+00:00",
            },
            "activeOrderId": "WO-1" if status in {"active", "pending_approval"} else "",
            "lastCompletedOrderId": "WO-1" if status == "completed" else "",
            "lastCompletedAt": "2026-06-16T09:10:00+00:00" if status == "completed" else "",
            "orderSequence": ["WO-1"],
            "transitionLog": [
                {
                    "eventType": "auto_completed",
                    "time": "2026-06-16T09:05:00+00:00",
                    "orderId": "WO-1",
                },
                {
                    "eventType": "started",
                    "time": "2026-06-16T09:01:00+00:00",
                    "orderId": "WO-1",
                },
            ],
            "completionLog": [
                {
                    "eventType": "completed",
                    "time": "2026-06-16T09:10:00+00:00",
                    "orderId": "WO-1",
                }
            ],
            "ordersById": {
                "WO-1": {
                    "orderId": "WO-1",
                    "erpType": "FERP",
                    "status": status,
                    "stockCode": "PKT-RED",
                    "productCode": "PKT-RED",
                    "stationCode": "PACKAGING_01",
                    "quantity": 1,
                    "targetQuantity": 1,
                    "queuedAt": "2026-06-16T09:00:00+00:00",
                    "startedAt": "2026-06-16T09:01:00+00:00" if status != "queued" else "",
                    "autoCompletedAt": "2026-06-16T09:05:00+00:00" if status in {"pending_approval", "completed"} else "",
                    "completedAt": "2026-06-16T09:10:00+00:00" if status == "completed" else "",
                    "completedQty": 1 if status in {"pending_approval", "completed"} else 0,
                    "remainingQty": 0 if status in {"pending_approval", "completed"} else 1,
                }
            },
        },
    }


def _state_after_accept_with_queued_sibling() -> dict:
    state = _state("completed")
    work_orders = state["workOrders"]
    work_orders["orderSequence"] = ["WO-1", "WO-2"]
    work_orders["ordersById"]["WO-2"] = {
        "orderId": "WO-2",
        "erpType": "FERP",
        "status": "queued",
        "stockCode": "PKT-BLUE",
        "productCode": "PKT-BLUE",
        "quantity": 1,
        "targetQuantity": 1,
        "queuedAt": "2026-06-16T09:00:00+00:00",
        "startedAt": "",
        "autoCompletedAt": "",
        "completedAt": "",
        "completedQty": 0,
        "remainingQty": 1,
    }
    return state


def _package_process_state(event_type: str) -> dict:
    state = _state("active" if event_type == "package_started" else "pending_approval")
    work_orders = state["workOrders"]
    work_orders["transitionLog"].insert(
        0,
        {
            "eventType": "package_started",
            "time": "2026-06-16T09:02:00+00:00",
            "orderId": "WO-1",
            "sessionId": "SESSION-1",
            "packageProcessStartedAt": "2026-06-16T09:02:00+00:00",
            "packageProcessStatus": "in_progress",
        },
    )
    if event_type == "package_finished":
        work_orders["completionLog"].insert(
            0,
            {
                "eventType": "package_finished",
                "time": "2026-06-16T09:04:05+00:00",
                "orderId": "WO-1",
                "sessionId": "SESSION-1",
                "packageProcessStartedAt": "2026-06-16T09:02:00+00:00",
                "packageProcessFinishedAt": "2026-06-16T09:04:05+00:00",
                "durationSeconds": 125.0,
            },
        )
        work_orders["ordersById"]["WO-1"]["lastAllocationAt"] = "2026-06-16T09:04:05+00:00"
    return state


class WorkOrderTransitionWriterTests(unittest.TestCase):
    def test_read_flag_does_not_trigger_transition_writer(self) -> None:
        with patch.object(
            work_order_transition_writer,
            "_execute_transition_write",
            side_effect=AssertionError("READ_WORK_ORDERS must not trigger transition writes"),
        ):
            result = mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_read_work_orders=True, db_hook_work_order_transitions=False),
                _state(),
                event_type="started",
            )

        self.assertEqual(result.reason, "live_hook_disabled")
        self.assertFalse(result.attempted)
        self.assertTrue(result.skipped)

    def test_hook_true_writes_current_state_and_event(self) -> None:
        captured = {}

        def fake_execute(config, current_rows, event_rows, *, replace_current):
            captured["config"] = config
            captured["current_rows"] = current_rows
            captured["event_rows"] = event_rows
            captured["replace_current"] = replace_current
            return {
                "current_row_count": len(current_rows),
                "event_row_count": len(event_rows),
                "deleted_current_rows": 0,
            }

        config = AppConfig(db_enabled=True, db_hook_work_order_transitions=True)
        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=fake_execute):
            result = mirror_work_order_transition_from_state(config, _state("active"), event_type="started", actor_id="OP-1")

        self.assertEqual(result.reason, "written")
        self.assertTrue(result.success)
        self.assertEqual(result.current_row_count, 1)
        self.assertEqual(result.event_row_count, 1)
        self.assertIs(captured["config"], config)
        self.assertFalse(captured["replace_current"])
        self.assertEqual(captured["current_rows"][0]["status"], "active")
        self.assertEqual(captured["current_rows"][0]["metadata"]["station_code"], "PACKAGING_01")
        self.assertEqual(captured["current_rows"][0]["metadata"]["queue_rank"], 0)
        self.assertEqual(captured["event_rows"][0].event_type, "started")
        self.assertEqual(captured["event_rows"][0].actor_id, "OP-1")
        self.assertIn("work_order_transition:started:WO-1", captured["event_rows"][0].external_ref)

    def test_finish_pending_and_cancelled_current_states_are_written(self) -> None:
        finished_state = _state("pending_approval")
        finished_state["workOrders"]["transitionLog"].insert(
            0,
            {"eventType": "finished", "time": "2026-06-16T09:06:00+00:00", "orderId": "WO-1"},
        )
        cancelled_state = _state("cancelled")
        cancelled_state["workOrders"]["transitionLog"].insert(
            0,
            {"eventType": "cancelled", "time": "2026-06-16T09:07:00+00:00", "orderId": "WO-1"},
        )

        finished_rows = []
        cancelled_rows = []

        def capture_finished(_config, current_rows, event_rows, *, replace_current):
            finished_rows.extend(current_rows)
            return {"current_row_count": len(current_rows), "event_row_count": len(event_rows), "deleted_current_rows": 0}

        def capture_cancelled(_config, current_rows, event_rows, *, replace_current):
            cancelled_rows.extend(current_rows)
            return {"current_row_count": len(current_rows), "event_row_count": len(event_rows), "deleted_current_rows": 0}

        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=capture_finished):
            mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_hook_work_order_transitions=True),
                finished_state,
                event_type="finished",
            )
        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=capture_cancelled):
            mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_hook_work_order_transitions=True),
                cancelled_state,
                event_type="cancelled",
            )

        self.assertEqual(finished_rows[0]["status"], "pending_approval")
        self.assertEqual(cancelled_rows[0]["status"], "cancelled")

    def test_accept_completed_writes_completed_current_state(self) -> None:
        captured = {}

        def fake_execute(_config, current_rows, event_rows, *, replace_current):
            captured["current_rows"] = current_rows
            captured["event_rows"] = event_rows
            captured["replace_current"] = replace_current
            return {
                "current_row_count": len(current_rows),
                "event_row_count": len(event_rows),
                "deleted_current_rows": 0,
            }

        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=fake_execute):
            result = mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_hook_work_order_transitions=True),
                _state("completed"),
                event_type="completed",
            )

        self.assertEqual(result.reason, "written")
        self.assertEqual(captured["current_rows"][0]["status"], "completed")
        self.assertEqual(captured["current_rows"][0]["completed_at"], "2026-06-16T09:10:00+00:00")
        self.assertEqual(captured["event_rows"][0].event_type, "completed")
        self.assertFalse(captured["replace_current"])

    def test_rollback_writes_queued_current_state(self) -> None:
        captured = {}
        state = _state("queued")
        state["workOrders"]["transitionLog"].insert(
            0,
            {
                "eventType": "rolled_back",
                "time": "2026-06-16T09:04:00+00:00",
                "orderId": "WO-1",
            },
        )

        def fake_execute(_config, current_rows, event_rows, *, replace_current):
            captured["current_rows"] = current_rows
            captured["event_rows"] = event_rows
            return {
                "current_row_count": len(current_rows),
                "event_row_count": len(event_rows),
                "deleted_current_rows": 0,
            }

        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=fake_execute):
            result = mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_hook_work_order_transitions=True),
                state,
                event_type="rolled_back",
            )

        self.assertEqual(result.reason, "written")
        self.assertEqual(captured["current_rows"][0]["status"], "queued")
        self.assertEqual(captured["event_rows"][0].event_type, "rolled_back")

    def test_pending_approval_event_is_inferred_from_started_sync(self) -> None:
        rows = build_work_order_transition_event_rows(_state("pending_approval"), event_type="started")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_type, "auto_completed")
        self.assertEqual(rows[0].event_at, "2026-06-16T09:05:00+00:00")
        self.assertIn("work_order_transition:auto_completed:WO-1", rows[0].external_ref)

    def test_completed_event_uses_completion_log(self) -> None:
        rows = build_work_order_transition_event_rows(_state("completed"), event_type="completed")

        self.assertEqual(rows[0].event_type, "completed")
        self.assertEqual(rows[0].event_at, "2026-06-16T09:10:00+00:00")

    def test_completed_transition_does_not_emit_events_for_queued_siblings(self) -> None:
        rows = build_work_order_transition_event_rows(_state_after_accept_with_queued_sibling(), event_type="completed")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].order_id, "WO-1")
        self.assertEqual(rows[0].event_type, "completed")

    def test_package_started_payload_contains_session_identity(self) -> None:
        rows = build_work_order_transition_event_rows(_package_process_state("package_started"), event_type="package_started")

        self.assertEqual(len(rows), 1)
        payload = rows[0].payload["package_process"]
        self.assertEqual(payload["session_id"], "SESSION-1")
        self.assertEqual(payload["package_order_id"], "WO-1")
        self.assertEqual(payload["started_at"], "2026-06-16T09:02:00+00:00")

    def test_package_finished_payload_contains_duration(self) -> None:
        rows = build_work_order_transition_event_rows(_package_process_state("package_finished"), event_type="package_finished")

        self.assertEqual(len(rows), 1)
        payload = rows[0].payload["package_process"]
        self.assertEqual(payload["session_id"], "SESSION-1")
        self.assertEqual(payload["started_at"], "2026-06-16T09:02:00+00:00")
        self.assertEqual(payload["finished_at"], "2026-06-16T09:04:05+00:00")
        self.assertEqual(payload["duration_seconds"], 125.0)

    def test_pending_current_state_does_not_write_completed_at(self) -> None:
        current_row = {
            "order_id": "WO-1",
            "status": "pending_approval",
            "completed_at": "2026-06-16T09:05:00+00:00",
            "payload": {},
            "metadata": {},
        }

        params = work_order_transition_writer._work_order_params(current_row)

        self.assertIsNone(params["completed_at"])

    def test_replace_current_empty_reset_still_attempts_delete_and_event(self) -> None:
        captured = {}
        empty_state = {"lastUpdatedAt": "2026-06-16T09:20:00+00:00", "workOrders": {"ordersById": {}, "source": {}}}

        def fake_execute(_config, current_rows, event_rows, *, replace_current):
            captured["current_rows"] = current_rows
            captured["event_rows"] = event_rows
            captured["replace_current"] = replace_current
            return {
                "current_row_count": len(current_rows),
                "event_row_count": len(event_rows),
                "deleted_current_rows": 6,
            }

        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=fake_execute):
            result = mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_hook_work_order_transitions=True),
                empty_state,
                event_type="reset",
                replace_current=True,
            )

        self.assertEqual(result.reason, "written")
        self.assertEqual(result.current_row_count, 0)
        self.assertEqual(result.event_row_count, 1)
        self.assertEqual(result.deleted_current_rows, 6)
        self.assertTrue(captured["replace_current"])
        self.assertEqual(captured["event_rows"][0].order_id, None)
        self.assertEqual(captured["event_rows"][0].event_type, "reset")

    def test_dry_run_wins_over_live_hook(self) -> None:
        with patch.object(
            work_order_transition_writer,
            "_execute_transition_write",
            side_effect=AssertionError("dry-run should not write"),
        ):
            result = mirror_work_order_transition_from_state(
                AppConfig(
                    db_enabled=True,
                    db_hook_work_order_transitions=True,
                    db_hook_work_order_transitions_dry_run=True,
                ),
                _state(),
                event_type="started",
            )

        self.assertEqual(result.reason, "dry_run_enabled")
        self.assertFalse(result.attempted)
        self.assertTrue(result.skipped)

    def test_db_error_fail_opens(self) -> None:
        with patch.object(work_order_transition_writer, "_execute_transition_write", side_effect=RuntimeError("db down")):
            result = mirror_work_order_transition_from_state(
                AppConfig(db_enabled=True, db_hook_work_order_transitions=True),
                _state(),
                event_type="started",
            )

        self.assertEqual(result.reason, "error_fail_open")
        self.assertTrue(result.attempted)
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "RuntimeError")

    def test_event_sql_is_duplicate_safe_and_current_delete_is_explicit_elsewhere(self) -> None:
        self.assertIn("ON CONFLICT (external_ref)", UPSERT_WORK_ORDER_EVENT_SQL)
        self.assertIn("DO UPDATE SET", UPSERT_WORK_ORDER_EVENT_SQL)
        self.assertNotIn("truncate", UPSERT_WORK_ORDER_EVENT_SQL.lower())
        self.assertNotIn("drop", UPSERT_WORK_ORDER_EVENT_SQL.lower())


if __name__ == "__main__":
    unittest.main()
