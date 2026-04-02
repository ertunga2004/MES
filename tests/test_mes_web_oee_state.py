from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

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
            start_time = datetime(2026, 4, 2, 8, 0, 0)
            stop_time = datetime(2026, 4, 2, 12, 30, 0)

            manager.apply_control("shift_start", now=start_time)
            result = manager.apply_control("shift_stop", now=stop_time)

            state = json.loads(manager.path.read_text(encoding="utf-8"))
            self.assertFalse(state["shift"]["active"])
            self.assertTrue(state["shift"]["endedAt"].endswith("Z"))
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


if __name__ == "__main__":
    unittest.main()
