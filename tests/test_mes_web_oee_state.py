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
            self.assertEqual(state["idealCycleMs"], 10000)
            self.assertEqual(state["idealCycleSec"], 10.0)
            self.assertEqual(state["shift"]["targetQty"], 14)
            self.assertEqual(state["shift"]["idealCycleMs"], 10000)
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
            self.assertEqual(state["shift"]["idealCycleMs"], 2500)
            self.assertEqual(state["shift"]["idealCycleSec"], 2.5)
            self.assertEqual(state["shift"]["plannedStopMs"], 450000)
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
            self.assertEqual(state["idealCycleMs"], 1700)
            self.assertEqual(state["idealCycleSec"], 1.7)
            self.assertEqual(state["plannedStopMs"], 270000)
            self.assertEqual(state["plannedStopMin"], 4.5)

    def test_live_snapshot_prefers_explicit_zero_ms_over_legacy_minute_fallback(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 8,
            "plannedStopMs": 0,
            "plannedStopMin": 12.0,
            "counts": {
                "total": 2,
                "good": 2,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "yellow": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "blue": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 8,
                "plannedStopMs": 0,
                "plannedStopMin": 12.0,
                "idealCycleMs": 0,
                "idealCycleSec": 2.0,
            },
            "unplannedDowntimeMs": 0,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 9, 0, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertEqual(snapshot["plannedStopMs"], 0)
        self.assertEqual(snapshot["plannedStopBudgetMs"], 0)

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

    def test_reused_item_id_starts_new_cycle_and_counts_robot_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {
                        "order_id": "WO-RED-REUSE",
                        "stock_code": "BOX-RED",
                        "stock_name": "Kirmizi Kutu",
                        "qty": 1,
                        "unit": "ADET",
                        "product_color": "red",
                        "cycle_time_sec": 10,
                    }
                ],
                now=datetime(2026, 4, 2, 8, 0, 0),
            )
            state = manager.read_state()
            state["itemsById"]["42"] = {
                "item_id": "42",
                "measure_id": "7",
                "color": "blue",
                "final_color": "blue",
                "classification": "GOOD",
                "completed_at": "2026-04-02T07:55:00+03:00",
                "updated_at": "2026-04-02T07:55:30+03:00",
                "inventory_match_key": "blue",
                "inventoryAction": "off_order_completion",
            }
            state["recentItemIds"] = ["42"]
            state["workOrders"]["inventoryByProduct"] = {
                "blue": {
                    "matchKey": "blue",
                    "productCode": "BOX-BLUE",
                    "stockCode": "BOX-BLUE",
                    "stockName": "Mavi Kutu",
                    "color": "blue",
                    "quantity": 1,
                    "itemIds": ["42"],
                    "lastUpdatedAt": "2026-04-02T07:55:30+03:00",
                    "lastSource": "off_order_completion",
                }
            }
            manager.write_state(state)

            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=timezone(timedelta(hours=3))))
            manager.start_work_order("WO-RED-REUSE", operator_code="OP-REUSE", now=datetime(2026, 4, 2, 8, 0, 30, tzinfo=timezone(timedelta(hours=3))))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00+03:00",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=42|MEASURE_ID=7|TRIGGER=TIMER",
                "2026-04-02T08:01:05+03:00",
            )

            state = manager.read_state()
            current_item = state["itemsById"]["42"]
            archived_keys = [key for key in state["itemsById"] if key.startswith("archived:42:")]
            self.assertEqual(state["counts"]["total"], 1)
            self.assertEqual(state["counts"]["good"], 1)
            self.assertEqual(current_item["completed_at"], "2026-04-02T08:01:05+03:00")
            self.assertEqual(current_item["color"], "red")
            self.assertEqual(current_item["work_order_id"], "WO-RED-REUSE")
            self.assertEqual(current_item["inventory_match_key"], "")
            self.assertTrue(archived_keys)
            self.assertEqual(state["workOrders"]["inventoryByProduct"]["blue"]["itemIds"][0], archived_keys[0])

            work_order = state["workOrders"]["ordersById"]["WO-RED-REUSE"]
            work_order_snapshot = build_work_order_snapshot(
                state,
                work_order,
                now=datetime(2026, 4, 2, 8, 1, 5, tzinfo=timezone(timedelta(hours=3))),
            )
            self.assertEqual(work_order["productionQty"], 1)
            self.assertGreater(work_order_snapshot["performance"], 0.0)

    def test_quality_override_finds_archived_completed_item_after_item_id_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            state = manager.read_state()
            state["itemsById"]["archived:42:old"] = {
                "item_id": "42",
                "measure_id": "7",
                "color": "blue",
                "classification": "GOOD",
                "completed_at": "2026-04-02T08:01:05+03:00",
                "updated_at": "2026-04-02T08:01:05+03:00",
            }
            state["itemsById"]["42"] = {
                "item_id": "42",
                "measure_id": "8",
                "color": "red",
                "queue_status": "waiting_travel",
                "updated_at": "2026-04-02T08:05:00+03:00",
            }
            manager.write_state(state)

            result = manager.apply_quality_override("42", "SCRAP", now=datetime(2026, 4, 2, 8, 6, 0, tzinfo=timezone(timedelta(hours=3))))

            state = manager.read_state()
            self.assertEqual(result["item"]["classification"], "SCRAP")
            self.assertEqual(state["itemsById"]["archived:42:old"]["classification"], "SCRAP")
            self.assertNotIn("classification", state["itemsById"]["42"])

    def test_reset_runtime_counts_clears_quality_override_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=timezone(timedelta(hours=3))))
            state = manager.read_state()
            state["counts"]["total"] = 2
            state["counts"]["good"] = 2
            state["counts"]["byColor"]["red"]["total"] = 2
            state["counts"]["byColor"]["red"]["good"] = 2
            state["recentItemIds"] = ["42"]
            state["qualityOverrideLog"] = [{"item_id": "42", "classification": "SCRAP"}]
            state["itemsById"]["42"] = {
                "item_id": "42",
                "color": "red",
                "final_color": "red",
                "classification": "GOOD",
                "completed_at": "2026-04-02T08:01:05+03:00",
                "count_in_oee": True,
            }
            manager.write_state(state)

            result = manager.reset_runtime_counts(now=datetime(2026, 4, 2, 8, 3, 0, tzinfo=timezone(timedelta(hours=3))))

            state = manager.read_state()
            self.assertEqual(result["muted_completed_count"], 1)
            self.assertEqual(state["counts"]["total"], 0)
            self.assertEqual(state["recentItemIds"], [])
            self.assertEqual(state["qualityOverrideLog"], [])
            self.assertTrue(str(state["qualityOverrideResetAt"]).startswith("2026-04-02T08:03:00"))
            self.assertFalse(state["itemsById"]["42"]["count_in_oee"])

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

    def test_target_mode_uses_target_quantity_for_expected_output(self) -> None:
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

        self.assertAlmostEqual(snapshot["expected"], 16.0, places=4)
        self.assertAlmostEqual(snapshot["performance"], 3.0 / 16.0, places=4)
        self.assertIn("beklenen 16.0", snapshot["targetText"])

    def test_target_mode_does_not_jump_to_100_percent_after_first_item_when_target_is_six(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 6,
            "plannedStopMin": 0.0,
            "counts": {
                "total": 1,
                "good": 1,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "yellow": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                    "blue": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 6,
                "plannedStopMin": 0.0,
                "idealCycleSec": 0.0,
            },
            "unplannedDowntimeMs": 0,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 8, 5, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertAlmostEqual(snapshot["expected"], 6.0, places=4)
        self.assertAlmostEqual(snapshot["performance"], 1.0 / 6.0, places=4)

    def test_live_performance_is_capped_at_100_percent(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 1,
            "plannedStopMin": 0.0,
            "counts": {
                "total": 20,
                "good": 20,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 20, "good": 20, "rework": 0, "scrap": 0},
                    "yellow": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                    "blue": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 1,
                "plannedStopMin": 0.0,
                "idealCycleSec": 0.0,
            },
            "unplannedDowntimeMs": 0,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 12, 0, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertGreater(snapshot["expected"], 0.0)
        self.assertEqual(snapshot["performance"], 1.0)
        self.assertLessEqual(snapshot["oee"], 1.0)

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

    def test_vision_event_during_active_fault_is_excluded_from_accuracy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=MAVI|DECISION_SOURCE=CORE_STABLE|REVIEW=0|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00Z",
            )
            manager.apply_tablet_fault_log(
                "|Tablet|Ariza|DURUM:BASLADI|NEDEN:Robot Kol Sikis masi",
                "2026-04-02T08:01:01Z",
            )

            result = manager.apply_vision_event(
                {
                    "event": "line_crossed",
                    "track_id": 31,
                    "color_name": "yellow",
                    "confidence": 0.94,
                    "observed_at": "2026-04-02T08:01:01Z",
                    "published_at": "2026-04-02T08:01:01.040Z",
                },
                "2026-04-02T08:01:01.060Z",
            )

            state = manager.read_state()
            item = state["itemsById"]["42"]
            self.assertTrue(result["changed"])
            self.assertIsNone(result["publish_command"])
            self.assertEqual(result["payload"]["correlation_status"], "FAULT_ACTIVE")
            self.assertFalse(result["payload"]["decision_applied"])
            self.assertEqual(item["sensor_color"], "blue")
            self.assertEqual(item.get("vision_color", ""), "")
            self.assertEqual(item["final_color"], "blue")
            self.assertEqual(item["correlation_status"], "FAULT_ACTIVE")
            self.assertEqual(item["finalization_reason"], "SENSOR_FAULT_WINDOW")
            self.assertEqual(state["vision"]["metrics"]["mismatchCount"], 0)
            self.assertEqual(state["vision"]["metrics"]["lateAuditCount"], 0)

    def test_shift_runtime_logs_periodic_snapshot_every_30_seconds(self) -> None:
        local_tz = timezone(timedelta(hours=3))
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))

            state = manager.read_state()
            self.assertEqual(len(state["trend"]), 1)
            self.assertEqual(state["trend"][0]["reason"], "shift_start")

            self.assertFalse(manager.tick(now=datetime(2026, 4, 2, 8, 0, 20, tzinfo=local_tz)))
            state = manager.read_state()
            self.assertEqual(len(state["trend"]), 1)

            self.assertTrue(manager.tick(now=datetime(2026, 4, 2, 8, 0, 31, tzinfo=local_tz)))
            state = manager.read_state()
            self.assertEqual(len(state["trend"]), 2)
            self.assertEqual(state["trend"][-1]["reason"], "periodic_30s")

    def test_oee_affecting_events_append_snapshot_rows_immediately(self) -> None:
        local_tz = timezone(timedelta(hours=3))
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))
            manager.apply_control("set_target_qty", 24, now=datetime(2026, 4, 2, 8, 0, 5, tzinfo=local_tz))

            state = manager.read_state()
            self.assertEqual(len(state["trend"]), 2)
            self.assertEqual(state["trend"][-1]["reason"], "control:set_target_qty")

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=7|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:01:00+03:00",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=42|MEASURE_ID=7|TRIGGER=TIMER",
                "2026-04-02T08:01:01+03:00",
            )

            state = manager.read_state()
            self.assertEqual(state["trend"][-1]["reason"], "pick_released")
            self.assertGreaterEqual(len(state["trend"]), 3)

    def test_work_order_moves_to_pending_approval_when_required_quantity_is_finished(self) -> None:
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
            self.assertEqual(work_order["status"], "pending_approval")
            self.assertEqual(work_order["completedQty"], 2)
            self.assertEqual(work_order["productionQty"], 2)
            self.assertEqual(work_order["remainingQty"], 0)
            self.assertTrue(str(work_order["autoCompletedAt"]).startswith("2026-04-02T08:03:00"))
            self.assertGreaterEqual(float(work_order_snapshot["performance"]), 0.0)
            self.assertEqual(state["workOrders"]["transitionLog"][0]["eventType"], "auto_completed")
            self.assertIn("PERF=", state["workOrders"]["transitionLog"][0]["note"])
            self.assertIn("Plansiz Durus=", state["workOrders"]["transitionLog"][0]["note"])
            self.assertEqual(state["workOrders"]["activeOrderId"], "WO-RED-001")

    def test_operator_acceptance_closes_pending_work_order_but_metrics_stop_at_auto_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            local_tz = timezone(timedelta(hours=3))
            manager.import_work_orders(
                [
                    {
                        "order_id": "WO-RED-ACCEPT",
                        "stock_code": "BOX-RED",
                        "stock_name": "Kirmizi Kutu",
                        "qty": 1,
                        "unit": "ADET",
                        "product_color": "red",
                        "cycle_time_sec": 10,
                    }
                ],
                now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz),
            )
            manager.start_work_order("WO-RED-ACCEPT", operator_code="OP-001", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))
            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=150|MEASURE_ID=15|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:10:00+03:00",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=150|MEASURE_ID=15|TRIGGER=TIMER",
                "2026-04-02T08:10:00+03:00",
            )

            accept_result = manager.accept_active_work_order(now=datetime(2026, 4, 2, 8, 16, 0, tzinfo=local_tz))

            state = manager.read_state()
            work_order = state["workOrders"]["ordersById"]["WO-RED-ACCEPT"]
            snapshot = build_work_order_snapshot(state, work_order, now=datetime(2026, 4, 2, 8, 16, 0, tzinfo=local_tz))
            self.assertEqual(work_order["status"], "completed")
            self.assertEqual(work_order["completedAt"], "2026-04-02T08:16:00.000+03:00")
            self.assertEqual(work_order["autoCompletedAt"], "2026-04-02T08:10:00+03:00")
            self.assertEqual(snapshot["elapsedMs"], 10 * 60 * 1000)
            self.assertEqual(state["workOrders"]["activeOrderId"], "")
            self.assertEqual(state["workOrders"]["lastCompletedOrderId"], "WO-RED-ACCEPT")
            self.assertEqual(state["workOrders"]["lastCompletedAt"], "2026-04-02T08:16:00.000+03:00")
            self.assertIn("Oto Tamam=2026-04-02T08:10:00+03:00", state["workOrders"]["completionLog"][0]["note"])
            self.assertEqual(accept_result["order"]["status"], "completed")

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
        self.assertAlmostEqual(snapshot["oee"], (40.0 / 60.0) * (30.0 / 40.0) * (2.0 / 3.0), places=4)

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
            self.assertEqual(work_order["status"], "pending_approval")
            self.assertEqual(work_order["inventoryConsumedQty"], 1)
            self.assertEqual(work_order["productionQty"], 1)
            self.assertEqual(work_order["completedQty"], 2)
            self.assertEqual(state["workOrders"]["activeOrderId"], "WO-RED-002")

    def test_quality_override_scrap_removes_off_order_item_from_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            state = manager.read_state()
            state["workOrders"]["inventoryByProduct"] = {
                "red": {
                    "matchKey": "red",
                    "productCode": "BOX-RED",
                    "stockCode": "BOX-RED",
                    "stockName": "Kirmizi Kutu",
                    "color": "red",
                    "quantity": 1,
                    "itemIds": ["250"],
                    "lastUpdatedAt": "2026-04-02T08:01:00+03:00",
                    "lastSource": "off_order_completion",
                }
            }
            state["itemsById"]["250"] = {
                "item_id": "250",
                "measure_id": "25",
                "completed_at": "2026-04-02T08:01:00+03:00",
                "updated_at": "2026-04-02T08:01:00+03:00",
                "color": "red",
                "final_color": "red",
                "classification": "GOOD",
                "inventory_match_key": "red",
                "inventoryAction": "off_order_completion",
            }
            manager.write_state(state)

            manager.apply_quality_override("250", "SCRAP", now=datetime(2026, 4, 2, 8, 5, 0, tzinfo=timezone(timedelta(hours=3))))

            reloaded = manager.read_state()
            self.assertEqual(reloaded["itemsById"]["250"]["classification"], "SCRAP")
            self.assertEqual(reloaded["itemsById"]["250"]["inventory_match_key"], "")
            self.assertEqual(reloaded["itemsById"]["250"]["inventoryAction"], "scrap_excluded")
            self.assertEqual(reloaded["workOrders"]["inventoryByProduct"], {})

    def test_scrap_completed_item_is_not_backfilled_into_inventory_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "oee_runtime_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "itemsById": {
                            "251": {
                                "item_id": "251",
                                "measure_id": "26",
                                "completed_at": "2026-04-02T08:01:00+03:00",
                                "updated_at": "2026-04-02T08:01:00+03:00",
                                "color": "red",
                                "final_color": "red",
                                "classification": "SCRAP",
                            }
                        },
                        "workOrders": {"inventoryByProduct": {}},
                    }
                ),
                encoding="utf-8",
            )

            manager = OeeRuntimeStateManager(state_path)
            reloaded = manager.read_state()

            self.assertEqual(reloaded["workOrders"]["inventoryByProduct"], {})
            self.assertEqual(str(reloaded["itemsById"]["251"].get("inventory_match_key") or ""), "")

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
            self.assertEqual(reassigned_order["status"], "pending_approval")
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
                "color": "red",
                "final_color": "red",
                "work_order_id": "",
                "work_order_match_key": "",
                "inventory_match_key": "red",
                "inventoryAction": "off_order_completion",
            }
            state["itemsById"]["702"] = {
                "item_id": "702",
                "completed_at": "2026-04-02T08:01:30+03:00",
                "color": "red",
                "final_color": "red",
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
            self.assertTrue(state["itemsById"]["701"]["inventory_backfill_disabled"])
            self.assertEqual(state["itemsById"]["702"]["work_order_id"], "")
            self.assertEqual(state["itemsById"]["702"]["work_order_match_key"], "")
            self.assertTrue(state["itemsById"]["702"]["inventory_backfill_disabled"])

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
                "color": "blue",
                "final_color": "blue",
                "inventory_match_key": "blue",
                "inventoryAction": "off_order_completion",
            }
            state["itemsById"]["801"] = {
                "item_id": "801",
                "completed_at": "2026-04-02T08:01:00+03:00",
                "color": "blue",
                "final_color": "blue",
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
            self.assertTrue(state["itemsById"]["801"]["inventory_backfill_disabled"])
            self.assertEqual(state["itemsById"]["800"]["inventory_match_key"], "blue")

    def test_remove_inventory_stock_persists_without_recreating_backfill_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "oee_runtime_state.json"
            manager = OeeRuntimeStateManager(state_path)
            state = manager.read_state()
            state["workOrders"]["inventoryByProduct"] = {
                "red": {
                    "matchKey": "red",
                    "productCode": "BOX-RED",
                    "stockCode": "BOX-RED",
                    "stockName": "Kirmizi Kutu",
                    "color": "red",
                    "quantity": 1,
                    "itemIds": ["900"],
                    "lastUpdatedAt": "2026-04-02T08:00:00+03:00",
                    "lastSource": "off_order_completion",
                }
            }
            state["itemsById"]["900"] = {
                "item_id": "900",
                "completed_at": "2026-04-02T08:00:00+03:00",
                "color": "red",
                "final_color": "red",
                "inventory_match_key": "red",
                "inventoryAction": "off_order_completion",
            }
            manager.write_state(state)

            manager.remove_inventory_stock("red", now=datetime(2026, 4, 2, 8, 2, 0))

            reloaded = OeeRuntimeStateManager(state_path).read_state()
            self.assertEqual(reloaded["workOrders"]["inventoryByProduct"], {})
            self.assertTrue(reloaded["itemsById"]["900"]["inventory_backfill_disabled"])

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

            with self.assertRaisesRegex(ValueError, "ACTIVE_WORK_ORDER_EXISTS"):
                manager.start_work_order("WO-BLUE-003", operator_code="OP-003", now=datetime(2026, 4, 2, 8, 1, 30, tzinfo=local_tz))

            manager.accept_active_work_order(now=datetime(2026, 4, 2, 8, 2, 0, tzinfo=local_tz))

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
            self.assertEqual(work_order["status"], "pending_approval")
            self.assertEqual(work_order["completedQty"], 3)
            self.assertEqual(work_order["remainingQty"], 0)
            self.assertEqual(work_order["productionQty"], 3)
            self.assertEqual(state["workOrders"]["activeOrderId"], "WO-MIX-001")

    def test_start_work_order_consumes_legacy_completed_items_from_inventory_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "oee_runtime_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "itemsById": {
                            "501": {
                                "item_id": "501",
                                "measure_id": "50",
                                "color": "red",
                                "final_color": "red",
                                "classification": "GOOD",
                                "completed_at": "2026-04-02T08:00:00+03:00",
                                "updated_at": "2026-04-02T08:00:30+03:00",
                            },
                            "601": {
                                "item_id": "601",
                                "measure_id": "60",
                                "color": "blue",
                                "final_color": "blue",
                                "classification": "GOOD",
                                "completed_at": "2026-04-02T08:01:00+03:00",
                                "updated_at": "2026-04-02T08:01:30+03:00",
                            },
                        },
                        "workOrders": {
                            "ordersById": {
                                "WO-RED-LEGACY": {
                                    "orderId": "WO-RED-LEGACY",
                                    "stockCode": "BOX-RED",
                                    "stockName": "Kirmizi Kutu",
                                    "quantity": 1,
                                    "completedQty": 0,
                                    "remainingQty": 1,
                                    "productColor": "red",
                                    "status": "queued",
                                    "cycleTimeSec": 10,
                                }
                            },
                            "orderSequence": ["WO-RED-LEGACY"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            manager = OeeRuntimeStateManager(state_path)

            result = manager.start_work_order(
                "WO-RED-LEGACY",
                operator_code="OP-LEGACY",
                now=datetime(2026, 4, 2, 8, 5, 0, tzinfo=timezone(timedelta(hours=3))),
            )

            state = manager.read_state()
            order = state["workOrders"]["ordersById"]["WO-RED-LEGACY"]
            red_item = state["itemsById"]["501"]
            blue_item = state["itemsById"]["601"]
            inventory = state["workOrders"]["inventoryByProduct"]

            self.assertEqual(result["inventory_used"], 1)
            self.assertEqual(order["status"], "pending_approval")
            self.assertEqual(order["completedQty"], 1)
            self.assertEqual(order["inventoryConsumedQty"], 1)
            self.assertEqual(order["productionQty"], 0)
            self.assertEqual(order["remainingQty"], 0)
            self.assertEqual(red_item["work_order_id"], "WO-RED-LEGACY")
            self.assertEqual(red_item["inventoryAction"], "consumed_for_work_order")
            self.assertEqual(blue_item["work_order_id"], "")
            self.assertEqual(blue_item["inventory_match_key"], "blue")
            self.assertEqual(inventory["blue"]["quantity"], 1)

    def test_quality_override_reopens_pending_work_order_until_operator_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            local_tz = timezone(timedelta(hours=3))
            manager.import_work_orders(
                [
                    {
                        "order_id": "WO-RED-REOPEN",
                        "stock_code": "BOX-RED",
                        "stock_name": "Kirmizi Kutu",
                        "qty": 1,
                        "unit": "ADET",
                        "product_color": "red",
                        "cycle_time_sec": 10,
                    }
                ],
                now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz),
            )
            manager.start_work_order("WO-RED-REOPEN", operator_code="OP-009", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=910|MEASURE_ID=91|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:10:00+03:00",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=910|MEASURE_ID=91|TRIGGER=TIMER",
                "2026-04-02T08:10:00+03:00",
            )

            state = manager.read_state()
            self.assertEqual(state["workOrders"]["ordersById"]["WO-RED-REOPEN"]["status"], "pending_approval")

            manager.apply_quality_override("910", "SCRAP", now=datetime(2026, 4, 2, 8, 12, 0, tzinfo=local_tz))

            state = manager.read_state()
            reopened_order = state["workOrders"]["ordersById"]["WO-RED-REOPEN"]
            self.assertEqual(reopened_order["status"], "active")
            self.assertEqual(reopened_order["completedQty"], 0)
            self.assertEqual(reopened_order["remainingQty"], 1)
            self.assertEqual(reopened_order["autoCompletedAt"], "")

            manager.apply_mega_log(
                "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=911|MEASURE_ID=92|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
                "2026-04-02T08:15:00+03:00",
            )
            manager.apply_mega_log(
                "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=911|MEASURE_ID=92|TRIGGER=TIMER",
                "2026-04-02T08:15:00+03:00",
            )
            manager.accept_active_work_order(now=datetime(2026, 4, 2, 8, 16, 0, tzinfo=local_tz))

            state = manager.read_state()
            closed_order = state["workOrders"]["ordersById"]["WO-RED-REOPEN"]
            snapshot = build_work_order_snapshot(state, closed_order, now=datetime(2026, 4, 2, 8, 16, 0, tzinfo=local_tz))
            self.assertEqual(closed_order["status"], "completed")
            self.assertEqual(closed_order["autoCompletedAt"], "2026-04-02T08:15:00+03:00")
            self.assertEqual(closed_order["completedAt"], "2026-04-02T08:16:00.000+03:00")
            self.assertEqual(snapshot["elapsedMs"], 15 * 60 * 1000)
            self.assertEqual(snapshot["goodQty"], 1)
            self.assertEqual(snapshot["scrapQty"], 1)
            self.assertEqual(snapshot["fulfilledQty"], 1)

    def test_opening_checklist_duration_stays_outside_oee(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 12,
            "plannedStopMin": 0.0,
            "counts": {
                "total": 2,
                "good": 2,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "yellow": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "blue": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 12,
                "plannedStopMin": 0.0,
                "idealCycleSec": 0.0,
            },
            "maintenance": {
                "openingChecklistDurationMs": 15 * 60 * 1000,
                "closingChecklistDurationMs": 0,
            },
            "unplannedDowntimeMs": 0,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 9, 0, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertEqual(snapshot["plannedStopMs"], 0)
        self.assertEqual(snapshot["unplannedMs"], 0)
        self.assertEqual(snapshot["plannedProductionElapsedMs"], 60 * 60 * 1000)

    def test_closing_checklist_duration_counts_as_planned_stop(self) -> None:
        state = {
            "performanceMode": "TARGET",
            "targetQty": 12,
            "plannedStopMin": 0.0,
            "counts": {
                "total": 2,
                "good": 2,
                "rework": 0,
                "scrap": 0,
                "byColor": {
                    "red": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "yellow": {"total": 1, "good": 1, "rework": 0, "scrap": 0},
                    "blue": {"total": 0, "good": 0, "rework": 0, "scrap": 0},
                },
            },
            "shift": {
                "active": True,
                "startedAt": "2026-04-02T08:00:00+03:00",
                "planStart": "2026-04-02T08:00:00+03:00",
                "planEnd": "2026-04-02T16:00:00+03:00",
                "performanceMode": "TARGET",
                "targetQty": 12,
                "plannedStopMin": 0.0,
                "idealCycleSec": 0.0,
            },
            "maintenance": {
                "openingChecklistDurationMs": 0,
                "closingChecklistDurationMs": 20 * 60 * 1000,
            },
            "unplannedDowntimeMs": 0,
        }

        snapshot = build_live_snapshot(state, now=datetime(2026, 4, 2, 16, 0, 0, tzinfo=timezone(timedelta(hours=3))))

        self.assertEqual(snapshot["plannedStopMs"], 20 * 60 * 1000)
        self.assertEqual(snapshot["plannedProductionElapsedMs"], (8 * 60 - 20) * 60 * 1000)

    def test_opening_checklist_completion_starts_shift_and_closing_completion_stops_shift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            local_tz = timezone(timedelta(hours=3))
            start_time = datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz)
            stop_time = datetime(2026, 4, 2, 16, 0, 0, tzinfo=local_tz)
            opening_steps = [
                {"step_code": "opening_1", "step_label": "Guvenlik", "required": True},
                {"step_code": "opening_2", "step_label": "Temizlik", "required": True},
            ]
            closing_steps = [
                {"step_code": "closing_1", "step_label": "Kapanis", "required": True},
            ]

            open_result = manager.begin_maintenance_session(
                "opening",
                steps=opening_steps,
                device_id="kiosk-1",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=start_time,
            )
            self.assertEqual(open_result["state"]["operationalState"], "opening_checklist")

            complete_open_result = manager.complete_maintenance_session(
                "opening",
                completed_steps=[{"step_code": "opening_1"}, {"step_code": "opening_2"}],
                note="tamam",
                device_id="kiosk-1",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=start_time + timedelta(minutes=5),
            )
            self.assertTrue(complete_open_result["state"]["shift"]["active"])
            self.assertEqual(complete_open_result["state"]["operationalState"], "shift_active_running")

            manager.begin_maintenance_session(
                "closing",
                steps=closing_steps,
                device_id="kiosk-1",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=stop_time,
            )
            complete_close_result = manager.complete_maintenance_session(
                "closing",
                completed_steps=[{"step_code": "closing_1"}],
                note="bitti",
                device_id="kiosk-1",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=stop_time + timedelta(minutes=10),
            )
            self.assertFalse(complete_close_result["state"]["shift"]["active"])
            self.assertEqual(complete_close_result["state"]["operationalState"], "idle_ready")
            self.assertEqual(
                complete_close_result["state"]["maintenance"]["closingChecklistDurationMs"],
                10 * 60 * 1000,
            )

    def test_manual_fault_duration_accumulates_into_unplanned_stop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            local_tz = timezone(timedelta(hours=3))
            manager.apply_control("shift_start", now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=local_tz))

            manager.start_manual_fault(
                device_id="kiosk-1",
                reason_code="jam",
                reason_text="Sikisma",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=datetime(2026, 4, 2, 8, 30, 0, tzinfo=local_tz),
            )
            manager.clear_manual_fault(now=datetime(2026, 4, 2, 8, 45, 0, tzinfo=local_tz))

            state = manager.read_state()
            self.assertEqual(state["manualFaultDurationMs"], 15 * 60 * 1000)
            self.assertEqual(state["unplannedDowntimeMs"], 15 * 60 * 1000)
            self.assertEqual(state["operationalState"], "shift_active_running")

    def test_help_request_reuses_open_request_and_increments_repeat_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")

            first = manager.request_help(
                device_id="kiosk-1",
                bound_station_id="4",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=datetime(2026, 4, 2, 8, 0, 0, tzinfo=timezone.utc),
            )
            second = manager.request_help(
                device_id="kiosk-1",
                bound_station_id="4",
                operator_id="1",
                operator_code="OP-001",
                operator_name="Test",
                now=datetime(2026, 4, 2, 8, 1, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(first["request"]["requestId"], second["request"]["requestId"])
            self.assertEqual(second["request"]["repeatCount"], 2)

    def test_kiosk_quality_override_rejects_completed_work_order_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            state = manager.read_state()
            state["recentItemIds"] = ["42"]
            state["itemsById"]["42"] = {
                "item_id": "42",
                "measure_id": "7",
                "color": "blue",
                "classification": "GOOD",
                "completed_at": "2026-04-02T08:01:05+03:00",
                "updated_at": "2026-04-02T08:01:05+03:00",
                "count_in_oee": True,
                "work_order_id": "WO-LOCKED",
            }
            state["workOrders"]["ordersById"]["WO-LOCKED"] = {
                "orderId": "WO-LOCKED",
                "status": "completed",
                "quantity": 1,
                "completedQty": 1,
            }
            state["workOrders"]["orderSequence"] = ["WO-LOCKED"]
            state["shift"]["active"] = True
            state["shift"]["startedAt"] = "2026-04-02T08:00:00+03:00"
            manager.write_state(state)

            with self.assertRaisesRegex(ValueError, "WORK_ORDER_LOCKED_FOR_KIOSK_OVERRIDE"):
                manager.apply_kiosk_quality_override("42", "SCRAP", now=datetime(2026, 4, 2, 8, 5, 0, tzinfo=timezone(timedelta(hours=3))))

    def test_kiosk_quality_override_accepts_last_five_visible_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            state = manager.read_state()
            state["recentItemIds"] = ["42", "41", "40", "39", "38"]
            state["shift"]["active"] = True
            state["shift"]["startedAt"] = "2026-04-02T08:00:00+03:00"
            state["workOrders"]["ordersById"]["WO-ACTIVE"] = {
                "orderId": "WO-ACTIVE",
                "status": "active",
                "quantity": 5,
                "completedQty": 1,
                "startedAt": "2026-04-02T08:00:30+03:00",
            }
            state["workOrders"]["orderSequence"] = ["WO-ACTIVE"]
            state["workOrders"]["activeOrderId"] = "WO-ACTIVE"
            for index, item_id in enumerate(state["recentItemIds"], start=1):
                state["itemsById"][item_id] = {
                    "item_id": item_id,
                    "measure_id": str(index),
                    "color": "blue",
                    "classification": "GOOD",
                    "completed_at": f"2026-04-02T08:0{index}:00+03:00",
                    "updated_at": f"2026-04-02T08:0{index}:00+03:00",
                    "count_in_oee": True,
                    "work_order_id": "WO-ACTIVE",
                }
            manager.write_state(state)

            result = manager.apply_kiosk_quality_override("42", "SCRAP", reason_text="ezik", now=datetime(2026, 4, 2, 8, 9, 0, tzinfo=timezone(timedelta(hours=3))))

            self.assertEqual(result["item"]["classification"], "SCRAP")
            self.assertEqual(result["override"]["reason_text"], "ezik")


if __name__ == "__main__":
    unittest.main()
