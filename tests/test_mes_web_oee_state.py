from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from mes_web.oee_state import OeeRuntimeStateManager, WorkOrderTransitionReasonRequired, build_live_snapshot, build_work_order_snapshot


class OeeRuntimeStateManagerTests(unittest.TestCase):
    def test_default_runtime_state_starts_with_target_14_and_ideal_cycle_10(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")

            state = manager.read_state()

            self.assertEqual(state["targetQty"], 14)
            self.assertEqual(state["idealCycleSec"], 10.0)
            self.assertEqual(state["shift"]["targetQty"], 14)
            self.assertEqual(state["shift"]["idealCycleSec"], 10.0)

    def test_startup_deactivation_closes_open_shift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            start_time = datetime(2026, 4, 2, 8, 0, 0)
            manager.apply_control("shift_start", now=start_time)

            changed = manager.deactivate_active_shift_on_startup(now=datetime(2026, 4, 2, 8, 1, 0))

            state = manager.read_state()
            self.assertTrue(changed)
            self.assertFalse(state["shift"]["active"])

    def test_shift_start_persists_selected_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            fixed_now = datetime(2026, 4, 2, 9, 15, 0)

            manager.apply_control("select_shift", "SHIFT-B", now=fixed_now)
            manager.apply_control("set_performance_mode", "IDEAL_CYCLE", now=fixed_now)
            manager.apply_control("set_target_qty", "18", now=fixed_now)
            manager.apply_control("set_ideal_cycle_sec", "2.5", now=fixed_now)
            manager.apply_control("set_planned_stop_min", "7.5", now=fixed_now)
            result = manager.apply_control("shift_start", now=fixed_now)

            state = json.loads(manager.path.read_text(encoding="utf-8"))
            self.assertTrue(state["shift"]["active"])
            self.assertEqual(state["shift"]["code"], "SHIFT-B")
            self.assertEqual(state["shift"]["performanceMode"], "IDEAL_CYCLE")
            self.assertEqual(state["shift"]["targetQty"], 18)
            self.assertEqual(state["shift"]["idealCycleSec"], 2.5)
            self.assertEqual(state["shift"]["plannedStopMin"], 7.5)
            self.assertIn("VARDIYA_BASLADI", result["system_line"])

    def test_shift_stop_marks_shift_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            local_tz = timezone(timedelta(hours=3))
            start_time = datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz)
            stop_time = datetime(2026, 4, 2, 12, 30, 0, tzinfo=local_tz)

            manager.apply_control("shift_start", now=start_time)
            result = manager.apply_control("shift_stop", now=stop_time)

            state = json.loads(manager.path.read_text(encoding="utf-8"))
            self.assertFalse(state["shift"]["active"])
            self.assertTrue(state["shift"]["endedAt"].endswith("+03:00"))
            self.assertIn("VARDIYA_BITTI", result["system_line"])

    def test_target_and_cycle_inputs_preserve_decimal_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("set_target_qty", "12")
            manager.apply_control("set_ideal_cycle_sec", "1.7")
            manager.apply_control("set_planned_stop_min", "4.5")

            state = manager.read_state()
            self.assertEqual(state["targetQty"], 12)
            self.assertEqual(state["idealCycleSec"], 1.7)
            self.assertEqual(state["plannedStopMin"], 4.5)

    def test_pickplace_done_counts_completed_item_as_good(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            changed = manager.apply_mega_log(
                "MEGA|AUTO|STATE=SEARCHING|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|PENDING=0",
                "2026-04-02T08:01:05Z",
            )

            state = manager.read_state()
            self.assertTrue(changed)
            self.assertEqual(state["counts"]["total"], 1)
            self.assertEqual(state["counts"]["good"], 1)
            self.assertEqual(state["counts"]["byColor"]["blue"]["total"], 1)
            self.assertEqual(state["counts"]["byColor"]["blue"]["good"], 1)
            self.assertEqual(state["itemsById"]["42"]["classification"], "GOOD")

    def test_pick_released_counts_completed_item_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            manager.apply_mega_log(
                "MEGA|AUTO|STATE=WAIT_ARM|EVENT=ARM_POSITION_REACHED|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRIGGER=TIMER",
                "2026-04-02T08:01:03Z",
            )

            changed = manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=42|MEASURE_ID=7|TRIGGER=TIMER",
                "2026-04-02T08:01:05Z",
            )

            state = manager.read_state()
            self.assertTrue(changed)
            self.assertEqual(state["counts"]["total"], 1)
            self.assertEqual(state["counts"]["good"], 1)
            self.assertEqual(state["itemsById"]["42"]["released_at"], "2026-04-02T08:01:05Z")
            self.assertEqual(state["itemsById"]["42"]["completed_at"], "2026-04-02T08:01:05Z")

            changed = manager.apply_mega_log(
                "MEGA|AUTO|STATE=SEARCHING|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRIGGER=TIMER|PENDING=0",
                "2026-04-02T08:01:06Z",
            )

            state = manager.read_state()
            self.assertFalse(changed)
            self.assertEqual(state["counts"]["total"], 1)
            self.assertEqual(state["counts"]["good"], 1)

    def test_quality_override_recomputes_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            manager.apply_mega_log(
                "MEGA|AUTO|STATE=SEARCHING|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|PENDING=0",
                "2026-04-02T08:01:05Z",
            )

            result = manager.apply_quality_override("42", "SCRAP", now=datetime(2026, 4, 2, 8, 2, 0))

            state = manager.read_state()
            self.assertEqual(state["counts"]["good"], 0)
            self.assertEqual(state["counts"]["scrap"], 1)
            self.assertEqual(state["counts"]["byColor"]["blue"]["good"], 0)
            self.assertEqual(state["counts"]["byColor"]["blue"]["scrap"], 1)
            self.assertEqual(state["itemsById"]["42"]["classification"], "SCRAP")
            self.assertEqual(result["override"]["previous_classification"], "GOOD")

    def test_planned_stop_is_excluded_from_availability_denominator(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 12,
            "plannedStopMin": 60.0,
            "counts": {
                "total": 3,
                "good": 3,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "yellow": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "blue": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 12,
                "plannedStopMin": 60.0,
                "idealCycleSec": 0.0,
            },
            "unplannedDowntimeMs": 30 * 60 * 1000,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 12, 0, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertEqual(snapshot["plannedStopMs"], 60 * 60 * 1000)
        self.assertEqual(snapshot["plannedStopBudgetMs"], 30 * 60 * 1000)
        self.assertEqual(snapshot["plannedProductionElapsedMs"], 3 * 60 * 60 * 1000 + 30 * 60 * 1000)
        self.assertAlmostEqual(snapshot["availability"], 6.0 / 7.0, places=4)

    def test_target_mode_uses_time_based_expected_output(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 16,
            "plannedStopMin": 60.0,
            "counts": {
                "total": 3,
                "good": 3,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "yellow": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "blue": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 16,
                "plannedStopMin": 60.0,
                "idealCycleSec": 0.0,
            },
            "unplannedDowntimeMs": 0,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 12, 0, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertAlmostEqual(snapshot["expected"], 8.0, places=4)
        self.assertAlmostEqual(snapshot["performance"], 3.0 / 8.0, places=4)
        self.assertIn("beklenen 8.0", snapshot["targetText"])

    def test_pickplace_return_done_updates_completed_item_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            manager.apply_mega_log(
                "MEGA|AUTO|STATE=WAIT_ARM|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|PENDING=0",
                "2026-04-02T08:01:05Z",
            )

            changed = manager.apply_mega_log(
                "MEGA|AUTO|STATE=SEARCHING|EVENT=PICKPLACE_RETURN_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|PENDING=0",
                "2026-04-02T08:01:06Z",
            )

            state = manager.read_state()
            self.assertTrue(changed)
            self.assertEqual(state["itemsById"]["42"]["return_done_at"], "2026-04-02T08:01:06Z")

    def test_write_state_retries_after_transient_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            original_replace = Path.replace
            attempts = {"count": 0}

            def flaky_replace(path_obj: Path, target: Path) -> Path:
                if path_obj.suffix == ".tmp" and target == manager.path and attempts["count"] == 0:
                    attempts["count"] += 1
                    raise PermissionError(5, "Access is denied", str(target))
                return original_replace(path_obj, target)

            with patch.object(Path, "replace", autospec=True, side_effect=flaky_replace):
                manager.apply_control("set_target_qty", "12")

            state = manager.read_state()
            self.assertEqual(attempts["count"], 1)
            self.assertEqual(state["targetQty"], 12)

    def test_high_confidence_vision_can_request_and_accept_early_pick(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(
                Path(temp_dir) / "oee_runtime_state.json",
                vision_recovery_window_threshold=1,
            )
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=SARI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )

            manager.apply_vision_heartbeat({"timestamp": "2026-04-02T08:01:01Z"}, "2026-04-02T08:01:01Z")
            manager.apply_vision_status({"state": "running", "fps": 12.0}, "2026-04-02T08:01:01Z")
            result = manager.apply_vision_event(
                {
                    "event": "line_crossed",
                    "track_id": 17,
                    "color_name": "red",
                    "confidence": 0.91,
                    "observed_at": "2026-04-02T08:01:02Z",
                    "published_at": "2026-04-02T08:01:02.050Z",
                },
                "2026-04-02T08:01:02.100Z",
            )

            self.assertTrue(result["changed"])
            self.assertEqual(result["publish_command"], "epick 42")
            self.assertEqual(result["item_id"], "42")
            self.assertEqual(result["payload"]["correlation_status"], "MATCHED")
            self.assertTrue(result["payload"]["decision_applied"])

            manager.apply_early_pick_request("42", "2026-04-02T08:01:02.120Z")
            manager.apply_mega_log(
                "MEGA|AUTO|STATE=WAIT_ARM|EVENT=ARM_POSITION_REACHED|ITEM_ID=42|MEASURE_ID=7|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRIGGER=EARLY",
                "2026-04-02T08:01:02.150Z",
            )
            manager.apply_mega_log(
                "MEGA|AUTO|STATE=SEARCHING|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=7|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRIGGER=EARLY|PENDING=0",
                "2026-04-02T08:01:05Z",
            )

            state = manager.read_state()
            item = state["itemsById"]["42"]
            self.assertEqual(state["vision"]["healthState"], "online")
            self.assertEqual(item["sensor_color"], "yellow")
            self.assertEqual(item["vision_color"], "red")
            self.assertEqual(item["final_color"], "red")
            self.assertEqual(item["decision_source"], "VISION")
            self.assertTrue(item["mismatch_flag"])
            self.assertEqual(item["finalization_reason"], "VISION_CORRECTED_MISMATCH")
            self.assertEqual(item["early_pick_request_sent_at"], "2026-04-02T08:01:02.120Z")
            self.assertEqual(item["early_pick_accepted_at"], "2026-04-02T08:01:02.150Z")
            self.assertEqual(item["pick_trigger_source"], "EARLY")
            self.assertEqual(item["queue_status"], "completed")
            self.assertEqual(item["final_color_frozen_at"], "2026-04-02T08:01:05Z")
            self.assertEqual(state["vision"]["metrics"]["mismatchCount"], 1)
            self.assertEqual(state["vision"]["metrics"]["earlyAcceptedCount"], 1)

    def test_late_vision_event_is_audited_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(
                Path(temp_dir) / "oee_runtime_state.json",
                vision_recovery_window_threshold=1,
            )
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            manager.apply_vision_heartbeat({"timestamp": "2026-04-02T08:01:01Z"}, "2026-04-02T08:01:01Z")
            manager.apply_vision_status({"state": "running", "fps": 12.0}, "2026-04-02T08:01:01Z")

            result = manager.apply_vision_event(
                {
                    "event": "line_crossed",
                    "track_id": 19,
                    "color_name": "yellow",
                    "confidence": 0.93,
                    "observed_at": "2026-04-02T08:01:01Z",
                    "published_at": "2026-04-02T08:01:01.010Z",
                },
                "2026-04-02T08:01:01.450Z",
            )

            state = manager.read_state()
            item = state["itemsById"]["42"]
            self.assertTrue(result["changed"])
            self.assertIsNone(result["publish_command"])
            self.assertEqual(result["payload"]["correlation_status"], "LATE")
            self.assertTrue(result["payload"]["late_vision_audit_flag"])
            self.assertFalse(result["payload"]["decision_applied"])
            self.assertEqual(item["sensor_color"], "blue")
            self.assertEqual(item.get("vision_color", ""), "")
            self.assertEqual(item["final_color"], "blue")
            self.assertEqual(item["correlation_status"], "LATE")
            self.assertTrue(item["late_vision_audit_flag"])
            self.assertTrue(item["review_required"])
            self.assertEqual(item["finalization_reason"], "SENSOR_LATE_VISION")
            self.assertEqual(state["vision"]["metrics"]["lateAuditCount"], 1)

    def test_work_order_completes_when_required_quantity_is_finished(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {
                        "order_id": "WO-RED-001",
                        "stock_code": "BOX-RED",
                        "stock_name": "Kirmizi Kutu",
                        "qty": 2,
                        "unit": "ADET",
                        "product_color": "red",
                    }
                ],
                now=datetime(2026, 4, 2, 8, 0, 0),
            )
            manager.start_work_order("WO-RED-001", operator_code="OP-001", now=datetime(2026, 4, 2, 8, 1, 0))

            for item_id, measure_id, stamp in (("100", "10", "2026-04-02T08:02:00Z"), ("101", "11", "2026-04-02T08:03:00Z")):
                manager.apply_mega_log(
                    f"MEGA|AUTO|QUEUE=ENQ|ITEM_ID={item_id}|MEASURE_ID={measure_id}|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                    stamp,
                )
                manager.apply_mega_log(
                    f"MEGA|ROBOT|EVENT=RELEASED|ITEM_ID={item_id}|MEASURE_ID={measure_id}|TRIGGER=TIMER",
                    stamp,
                )

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-RED-001"]
            work_order_snapshot = build_work_order_snapshot(state, work_order, now=datetime(2026, 4, 2, 8, 3, 0, tzinfo=timezone.utc))
            self.assertEqual(work_order["status"], "completed")
            self.assertEqual(work_order["completedQty"], 2)
            self.assertEqual(work_order["productionQty"], 2)
            self.assertEqual(work_order["remainingQty"], 0)
            self.assertGreaterEqual(float(work_order_snapshot["oee"]), 0.0)
            self.assertIn("OEE=", state["workOrders"]["completionLog"][0]["note"])
            self.assertEqual(state["workOrders"]["activeOrderId"], "")

    def test_work_order_snapshot_uses_target_qty_and_reference_cycle(self) -> None:
        local_tz = timezone(timedelta(hours=3))
        snapshot = build_work_order_snapshot(
            {
                "idealCycleSec": 10.0,
                "itemsById": {
                    "1": {"work_order_id": "WO-OEE-01", "completed_at": "2026-04-02T08:00:15+03:00", "classification": "GOOD"},
                    "2": {"work_order_id": "WO-OEE-01", "completed_at": "2026-04-02T08:00:30+03:00", "classification": "GOOD"},
                    "3": {"work_order_id": "WO-OEE-01", "completed_at": "2026-04-02T08:00:45+03:00", "classification": "SCRAP"},
                },
                "faultHistory": [
                    {
                        "startedAt": "2026-04-02T08:00:20+03:00",
                        "endedAt": "2026-04-02T08:00:40+03:00",
                    }
                ],
            },
            {
                "orderId": "WO-OEE-01",
                "quantity": 6,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "status": "active",
            },
            now=datetime(2026, 4, 2, 8, 1, 0, tzinfo=local_tz),
        )

        self.assertEqual(snapshot["targetQty"], 6)
        self.assertEqual(snapshot["idealCycleSec"], 10.0)
        self.assertEqual(snapshot["plannedDurationMs"], 60_000)
        self.assertEqual(snapshot["runtimeMs"], 40_000)
        self.assertEqual(snapshot["unplannedMs"], 20_000)
        self.assertEqual(snapshot["productionQty"], 3)
        self.assertEqual(snapshot["fulfilledQty"], 3)
        self.assertEqual(snapshot["goodQty"], 2)
        self.assertEqual(snapshot["scrapQty"], 1)
        self.assertAlmostEqual(snapshot["availability"], 40.0 / 60.0, places=4)
        self.assertAlmostEqual(snapshot["performance"], 30.0 / 40.0, places=4)
        self.assertAlmostEqual(snapshot["quality"], 2.0 / 3.0, places=4)
        self.assertAlmostEqual(snapshot["oee"], 1.0 / 3.0, places=4)

    def test_off_order_completion_goes_to_inventory_and_is_consumed_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {
                        "order_id": "WO-RED-002",
                        "stock_code": "BOX-RED",
                        "stock_name": "Kirmizi Kutu",
                        "qty": 2,
                        "unit": "ADET",
                        "product_color": "red",
                    }
                ],
                now=datetime(2026, 4, 2, 8, 0, 0),
            )

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=200|MEASURE_ID=20|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=200|MEASURE_ID=20|TRIGGER=TIMER",
                "2026-04-02T08:01:01Z",
            )

            state = manager.read_state()
            self.assertEqual(state["workOrders"]["inventoryByProduct"]["red"]["quantity"], 1)

            manager.start_work_order("WO-RED-002", operator_code="OP-002", now=datetime(2026, 4, 2, 8, 5, 0))

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-RED-002"]
            self.assertEqual(work_order["status"], "active")
            self.assertEqual(work_order["inventoryConsumedQty"], 1)
            self.assertEqual(work_order["remainingQty"], 1)
            self.assertNotIn("red", state["workOrders"]["inventoryByProduct"])
            self.assertEqual(state["itemsById"]["200"]["work_order_id"], "WO-RED-002")

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=201|MEASURE_ID=21|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:06:00Z",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=201|MEASURE_ID=21|TRIGGER=TIMER",
                "2026-04-02T08:06:01Z",
            )

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-RED-002"]
            self.assertEqual(work_order["status"], "completed")
            self.assertEqual(work_order["inventoryConsumedQty"], 1)
            self.assertEqual(work_order["productionQty"], 1)
            self.assertEqual(work_order["completedQty"], 2)

    def test_rollback_active_work_order_returns_completed_boxes_to_inventory_and_reassigns_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {"order_id": "WO-ROLLBACK-A", "stock_code": "BOX-RED", "qty": 3, "product_color": "red"},
                    {"order_id": "WO-ROLLBACK-B", "stock_code": "BOX-RED", "qty": 2, "product_color": "red"},
                ],
                now=datetime(2026, 4, 2, 8, 0, 0),
            )

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=600|MEASURE_ID=60|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:00:30Z",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=600|MEASURE_ID=60|TRIGGER=TIMER",
                "2026-04-02T08:00:31Z",
            )

            manager.start_work_order("WO-ROLLBACK-A", operator_code="OP-ROLL", now=datetime(2026, 4, 2, 8, 1, 0))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=601|MEASURE_ID=61|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:02:00Z",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=601|MEASURE_ID=61|TRIGGER=TIMER",
                "2026-04-02T08:02:01Z",
            )

            rollback_result = manager.rollback_active_work_order(now=datetime(2026, 4, 2, 8, 3, 0))
            state = manager.read_state()
            rolled_back_order = state["workOrders"]["ordersById"]["WO-ROLLBACK-A"]
            self.assertEqual(rollback_result["returned_to_inventory"], 2)
            self.assertEqual(rolled_back_order["status"], "queued")
            self.assertEqual(rolled_back_order["completedQty"], 0)
            self.assertEqual(rolled_back_order["remainingQty"], 3)
            self.assertEqual(state["workOrders"]["inventoryByProduct"]["red"]["quantity"], 2)
            self.assertCountEqual(state["workOrders"]["inventoryByProduct"]["red"]["itemIds"], ["600", "601"])
            self.assertEqual(state["itemsById"]["600"]["work_order_id"], "")
            self.assertEqual(state["itemsById"]["601"]["work_order_id"], "")

            start_result = manager.start_work_order("WO-ROLLBACK-B", operator_code="OP-ROLL", now=datetime(2026, 4, 2, 8, 4, 0))
            state = manager.read_state()
            reassigned_order = state["workOrders"]["ordersById"]["WO-ROLLBACK-B"]
            reassigned_snapshot = build_work_order_snapshot(state, reassigned_order, now=datetime(2026, 4, 2, 8, 4, 0, tzinfo=timezone.utc))
            self.assertEqual(start_result["inventory_used"], 2)
            self.assertEqual(reassigned_order["status"], "completed")
            self.assertEqual(reassigned_order["inventoryConsumedQty"], 2)
            self.assertEqual(state["itemsById"]["600"]["work_order_id"], "WO-ROLLBACK-B")
            self.assertEqual(state["itemsById"]["601"]["work_order_id"], "WO-ROLLBACK-B")
            self.assertNotIn("red", state["workOrders"]["inventoryByProduct"])
            self.assertEqual(reassigned_snapshot["goodQty"], 2)
            self.assertEqual(reassigned_snapshot["fulfilledQty"], 2)

    def test_reset_work_orders_clears_queue_inventory_and_item_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {"order_id": "WO-RESET-A", "stock_code": "BOX-RED", "qty": 2, "product_color": "red"},
                    {"order_id": "WO-RESET-B", "stock_code": "BOX-BLUE", "qty": 1, "product_color": "blue"},
                ],
                now=datetime(2026, 4, 2, 8, 0, 0),
            )
            manager.start_work_order("WO-RESET-A", operator_code="OP-007", now=datetime(2026, 4, 2, 8, 1, 0))
            state = manager.read_state()
            state["workOrders"]["inventoryByProduct"] = {
                "red": {
                    "matchKey": "red",
                    "productCode": "BOX-RED",
                    "stockCode": "BOX-RED",
                    "stockName": "Kirmizi Kutu",
                    "color": "red",
                    "quantity": 1,
                    "itemIds": ["701"],
                    "lastUpdatedAt": "2026-04-02T08:02:00+03:00",
                    "lastSource": "off_order_completion",
                }
            }
            state["itemsById"]["701"] = {
                "item_id": "701",
                "completed_at": "2026-04-02T08:02:00+03:00",
                "work_order_id": "",
                "work_order_match_key": "",
                "inventory_match_key": "red",
                "inventoryAction": "off_order_completion",
            }
            state["itemsById"]["702"] = {
                "item_id": "702",
                "completed_at": "2026-04-02T08:01:30+03:00",
                "work_order_id": "WO-RESET-A",
                "work_order_match_key": "red",
                "inventory_match_key": "",
                "inventoryAction": "work_order",
            }
            manager.write_state(state)

            result = manager.reset_work_orders(now=datetime(2026, 4, 2, 8, 3, 0))

            state = manager.read_state()
            self.assertEqual(result["cleared_item_count"], 2)
            self.assertEqual(state["workOrders"]["ordersById"], {})
            self.assertEqual(state["workOrders"]["orderSequence"], [])
            self.assertEqual(state["workOrders"]["inventoryByProduct"], {})
            self.assertEqual(state["workOrders"]["activeOrderId"], "")
            self.assertEqual(state["itemsById"]["701"]["inventory_match_key"], "")
            self.assertEqual(state["itemsById"]["701"]["inventoryAction"], "")
            self.assertEqual(state["itemsById"]["702"]["work_order_id"], "")
            self.assertEqual(state["itemsById"]["702"]["work_order_match_key"], "")

    def test_remove_inventory_stock_drops_one_item_and_detaches_latest_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            state = manager.read_state()
            state["workOrders"]["inventoryByProduct"] = {
                "blue": {
                    "matchKey": "blue",
                    "productCode": "BOX-BLUE",
                    "stockCode": "BOX-BLUE",
                    "stockName": "Mavi Kutu",
                    "color": "blue",
                    "quantity": 2,
                    "itemIds": ["800", "801"],
                    "lastUpdatedAt": "2026-04-02T08:00:00+03:00",
                    "lastSource": "off_order_completion",
                }
            }
            state["itemsById"]["800"] = {
                "item_id": "800",
                "completed_at": "2026-04-02T08:00:00+03:00",
                "inventory_match_key": "blue",
                "inventoryAction": "off_order_completion",
            }
            state["itemsById"]["801"] = {
                "item_id": "801",
                "completed_at": "2026-04-02T08:01:00+03:00",
                "inventory_match_key": "blue",
                "inventoryAction": "off_order_completion",
            }
            manager.write_state(state)

            result = manager.remove_inventory_stock("blue", now=datetime(2026, 4, 2, 8, 2, 0))

            state = manager.read_state()
            self.assertEqual(result["removed_qty"], 1)
            self.assertEqual(result["remaining_qty"], 1)
            self.assertEqual(state["workOrders"]["inventoryByProduct"]["blue"]["quantity"], 1)
            self.assertEqual(state["workOrders"]["inventoryByProduct"]["blue"]["itemIds"], ["800"])
            self.assertEqual(state["itemsById"]["801"]["inventory_match_key"], "")
            self.assertEqual(state["itemsById"]["801"]["inventoryAction"], "manual_inventory_removed")
            self.assertEqual(state["itemsById"]["800"]["inventory_match_key"], "blue")

    def test_work_order_start_requires_reason_after_tolerance_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            local_tz = timezone(timedelta(hours=3))
            manager.import_work_orders(
                [
                    {"order_id": "WO-RED-003", "stock_code": "BOX-RED", "qty": 1, "product_color": "red"},
                    {"order_id": "WO-BLUE-003", "stock_code": "BOX-BLUE", "qty": 1, "product_color": "blue"},
                ],
                now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz),
            )
            manager.set_work_order_tolerance(1, now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))
            manager.start_work_order("WO-RED-003", operator_code="OP-003", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=300|MEASURE_ID=30|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:00:30+03:00",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=300|MEASURE_ID=30|TRIGGER=TIMER",
                "2026-04-02T08:01:00+03:00",
            )

            with self.assertRaises(WorkOrderTransitionReasonRequired):
                manager.start_work_order("WO-BLUE-003", operator_code="OP-003", now=datetime(2026, 4, 2, 8, 5, 0, tzinfo=local_tz))

            result = manager.start_work_order(
                "WO-BLUE-003",
                operator_code="OP-003",
                transition_reason="Makine temizlik ve operator bekleme",
                now=datetime(2026, 4, 2, 8, 5, 0, tzinfo=local_tz),
            )

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-BLUE-003"]
            self.assertEqual(work_order["status"], "active")
            self.assertEqual(work_order["transitionReason"], "Makine temizlik ve operator bekleme")
            self.assertIn("Kalan", result["summary"])

    def test_mixed_color_work_order_completes_across_multiple_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {
                        "order_id": "WO-MIX-001",
                        "stock_code": "BOX-MIX",
                        "stock_name": "Karisik Set",
                        "cycle_time_sec": 10,
                        "requirements": [
                            {"line_id": "RED", "stock_code": "BOX-RED", "color": "red", "qty": 1},
                            {"line_id": "YEL", "stock_code": "BOX-YEL", "color": "yellow", "qty": 1},
                            {"line_id": "BLU", "stock_code": "BOX-BLUE", "color": "blue", "qty": 1},
                        ],
                    }
                ],
                now=datetime(2026, 4, 2, 8, 0, 0),
            )
            manager.start_work_order("WO-MIX-001", operator_code="OP-004", now=datetime(2026, 4, 2, 8, 1, 0))

            for item_id, measure_id, color, stamp in (
                ("400", "40", "KIRMIZI", "2026-04-02T08:02:00Z"),
                ("401", "41", "SARI", "2026-04-02T08:03:00Z"),
            ):
                manager.apply_mega_log(
                    f"MEGA|AUTO|QUEUE=ENQ|ITEM_ID={item_id}|MEASURE_ID={measure_id}|COLOR={color}|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                    stamp,
                )
                manager.apply_mega_log(
                    f"MEGA|ROBOT|EVENT=RELEASED|ITEM_ID={item_id}|MEASURE_ID={measure_id}|TRIGGER=TIMER",
                    stamp,
                )

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-MIX-001"]
            self.assertEqual(work_order["status"], "active")
            self.assertEqual(work_order["completedQty"], 2)
            self.assertEqual(work_order["productColor"], "mixed")
            requirements = {row["lineId"]: row for row in work_order["requirements"]}
            self.assertEqual(requirements["RED"]["completedQty"], 1)
            self.assertEqual(requirements["YEL"]["completedQty"], 1)
            self.assertEqual(requirements["BLU"]["completedQty"], 0)

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=402|MEASURE_ID=42|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:04:00Z",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=402|MEASURE_ID=42|TRIGGER=TIMER",
                "2026-04-02T08:04:00Z",
            )

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-MIX-001"]
            self.assertEqual(work_order["status"], "completed")
            self.assertEqual(work_order["completedQty"], 3)
            self.assertEqual(work_order["remainingQty"], 0)
            self.assertEqual(work_order["productionQty"], 3)
            self.assertEqual(state["workOrders"]["activeOrderId"], "")


if __name__ == "__main__":
    unittest.main()
