from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from mes_web.oee_state import OeeRuntimeStateManager


class OeeRuntimeStateManagerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
