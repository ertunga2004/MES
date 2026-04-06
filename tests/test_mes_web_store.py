from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.store import DashboardStore, utc_now_text


class DashboardStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._state_path = os.path.join(self._temp_dir.name, "oee_runtime_state.json")
        with open(self._state_path, "w", encoding="utf-8") as handle:
            handle.write("{}")
        self._env_patch = patch.dict(os.environ, {"MES_WEB_OEE_RUNTIME_STATE_PATH": self._state_path}, clear=False)
        self._env_patch.start()
        self.config = AppConfig.from_env()
        self.store = DashboardStore(self.config)
        self.module_id = self.config.module_id

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._temp_dir.cleanup()

    def test_counts_and_compare_follow_queue_events(self) -> None:
        self.store.apply_log_line(self.module_id, "MEGA|AUTO|QUEUE=ENQ|COLOR=KIRMIZI")
        self.store.apply_log_line(self.module_id, "MEGA|AUTO|QUEUE=ENQ|COLOR=SARI")
        self.store.apply_vision_event(self.module_id, {"event": "line_crossed", "color_name": "red"})

        snapshot = self.store.get_dashboard_snapshot(self.module_id)
        self.assertEqual(snapshot["counts"]["red"], 1)
        self.assertEqual(snapshot["counts"]["yellow"], 1)
        self.assertEqual(snapshot["counts"]["total"], 2)
        self.assertEqual(snapshot["vision_ingest"]["compare"]["mega"]["red"], 1)
        self.assertEqual(snapshot["vision_ingest"]["compare"]["vision"]["red"], 1)
        self.assertEqual(snapshot["vision_ingest"]["compare"]["diff"]["yellow"], 1)

    def test_utc_now_text_preserves_local_offset(self) -> None:
        local_time = datetime(2026, 4, 3, 9, 30, 0, tzinfo=timezone(timedelta(hours=3)))
        self.assertEqual(utc_now_text(local_time), "2026-04-03T09:30:00+03:00")

    def test_reset_counts(self) -> None:
        self.store.apply_log_line(self.module_id, "MEGA|AUTO|QUEUE=ENQ|COLOR=MAVI")
        self.store.reset_counts(self.module_id, received_at="2026-04-02T10:15:30Z")

        snapshot = self.store.get_dashboard_snapshot(self.module_id)
        self.assertEqual(snapshot["counts"]["total"], 0)
        self.assertEqual(snapshot["counts"]["last_reset_at"], "2026-04-02T10:15:30Z")
        self.assertEqual(snapshot["recent_logs"][0]["message"], "SYSTEM|COUNTS|RESET")

    def test_heartbeat_timeout_turns_offline(self) -> None:
        base = datetime(2026, 4, 2, 10, 0, 0, tzinfo=timezone.utc)
        self.store.apply_heartbeat(self.module_id, received_at=utc_now_text(base))

        online_snapshot = self.store.get_dashboard_snapshot(self.module_id, now=base + timedelta(seconds=5))
        offline_snapshot = self.store.get_dashboard_snapshot(self.module_id, now=base + timedelta(seconds=15))

        self.assertEqual(online_snapshot["connection"]["mega_heartbeat"]["state"], "online")
        self.assertEqual(offline_snapshot["connection"]["mega_heartbeat"]["state"], "offline")

    def test_status_fields_flow_into_snapshot(self) -> None:
        self.store.apply_status_line(
            self.module_id,
            "MEGA|STATUS|AUTO=1|STATE=RUN|CONVEYOR=RUN|ROBOT=WAIT_ARM|LAST=MAVI|DIR=REV|PWM=128|TRAVEL_MS=900|LIM22=1|LIM23=0|STEP=1|STEP_HOLD=1|STEP_US=700|QUEUE=4|STOP_REQ=1",
        )

        snapshot = self.store.get_dashboard_snapshot(self.module_id)
        self.assertEqual(snapshot["system_status"]["mode"], "auto")
        self.assertEqual(snapshot["system_status"]["last_color"], "blue")
        self.assertEqual(snapshot["hardware_status"]["direction"], "rev")
        self.assertEqual(snapshot["hardware_status"]["esp32_state"], "offline")

    def test_initial_snapshot_does_not_assume_device_values(self) -> None:
        snapshot = self.store.get_dashboard_snapshot(self.module_id)
        self.assertEqual(snapshot["system_status"]["mode"], "unknown")
        self.assertIsNone(snapshot["system_status"]["step_enabled"])
        self.assertIsNone(snapshot["system_status"]["queue_depth"])
        self.assertIsNone(snapshot["hardware_status"]["limit_22_pressed"])
        self.assertIsNone(snapshot["hardware_status"]["limit_23_pressed"])

    def test_command_permissions_follow_full_live_mode(self) -> None:
        permissions = self.store.command_permissions()

        self.assertEqual(permissions["mode"], "full_live")
        self.assertTrue(permissions["publish_enabled"])
        self.assertTrue(permissions["manual_command_enabled"])

    def test_command_permissions_follow_preset_live_mode(self) -> None:
        config = AppConfig(command_mode="preset_live")
        store = DashboardStore(config)

        permissions = store.command_permissions()

        self.assertEqual(permissions["mode"], "preset_live")
        self.assertTrue(permissions["publish_enabled"])
        self.assertFalse(permissions["manual_command_enabled"])

    def test_command_permissions_follow_read_only_mode(self) -> None:
        config = AppConfig(command_mode="read_only")
        store = DashboardStore(config)

        permissions = store.command_permissions()

        self.assertEqual(permissions["mode"], "read_only")
        self.assertFalse(permissions["publish_enabled"])
        self.assertFalse(permissions["manual_command_enabled"])

    def test_tablet_oee_line_flows_into_snapshot(self) -> None:
        self.store.apply_tablet_log(
            self.module_id,
            "|Tablet|OEE| OEE:0.5470|KULL:0.6170|PERF:1.0000|KALITE:0.9000|MAVI_S:5|MAVI_R:1|MAVI_H:0|SARI_S:4|SARI_R:0|SARI_H:1|KIRMIZI_S:3|KIRMIZI_R:0|KIRMIZI_H:2",
            received_at="2026-04-02T10:15:30Z",
        )

        snapshot = self.store.get_dashboard_snapshot(self.module_id)
        self.assertEqual(snapshot["oee"]["kpis"]["oee"], 54.7)
        self.assertEqual(snapshot["oee"]["production"]["total"], 16)
        self.assertEqual(snapshot["oee"]["colors"]["yellow"]["scrap"], 1)
        self.assertEqual(snapshot["oee"]["header"]["line_state"], "ready")

    def test_tablet_fault_line_updates_oee_fault_state(self) -> None:
        self.store.apply_tablet_log(
            self.module_id,
            "|Tablet|Ariza| KATEGORI:MEKANIK|NEDEN:Robot Kol Sikis masi|DURUM:BASLADI|BASLANGIC:12:00:00",
            received_at="2026-04-02T10:15:30Z",
        )

        snapshot = self.store.get_dashboard_snapshot(self.module_id)
        self.assertTrue(snapshot["oee"]["fault"]["active"])
        self.assertEqual(snapshot["oee"]["fault"]["reason"], "Robot Kol Sikis masi")
        self.assertEqual(snapshot["oee"]["header"]["line_state"], "stopped")

    def test_runtime_state_file_seeds_oee_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "oee_runtime_state.json")
            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"shiftSelected":"SHIFT-B","performanceMode":"IDEAL_CYCLE","targetQty":14,"idealCycleSec":2.5,"plannedStopMin":5.5,"shift":{"active":true,"code":"SHIFT-A","name":"A Vardiyasi"},'
                    '"counts":{"byColor":{"red":{"total":3,"good":2,"rework":1,"scrap":0},"yellow":{"total":2,"good":2,"rework":0,"scrap":0},"blue":{"total":1,"good":1,"rework":0,"scrap":0}}},'
                    '"trend":[{"time":"2026-04-02T10:00:00Z","oee":61.7,"quality":90.0,"performance":100.0,"loss":10.0}],'
                    '"lastEventSummary":"Kaydedilen vardiya durumu geri yuklendi.","lastUpdatedAt":"2026-04-02T10:00:00Z"}'
                )

            with patch.dict(os.environ, {"MES_WEB_OEE_RUNTIME_STATE_PATH": state_path}, clear=False):
                config = AppConfig.from_env()
                store = DashboardStore(config)
                snapshot = store.get_dashboard_snapshot(config.module_id)

            self.assertEqual(snapshot["oee"]["targets"]["target_qty"], 14)
            self.assertEqual(snapshot["oee"]["targets"]["ideal_cycle_sec"], 2.5)
            self.assertEqual(snapshot["oee"]["colors"]["red"]["rework"], 1)
            self.assertEqual(snapshot["oee"]["trend"][-1]["oee"], 61.7)
            self.assertEqual(snapshot["oee"]["shift"]["code"], "SHIFT-A")
            self.assertEqual(snapshot["oee"]["controls"]["selected_shift"], "SHIFT-B")
            self.assertEqual(snapshot["oee"]["controls"]["performance_mode"], "IDEAL_CYCLE")
            self.assertEqual(snapshot["oee"]["controls"]["planned_stop_min"], 5.5)

    def test_runtime_state_builds_live_oee_from_completed_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "oee_runtime_state.json")
            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"shiftSelected":"SHIFT-A","performanceMode":"TARGET","targetQty":10,'
                    '"shift":{"active":true,"code":"SHIFT-A","name":"A Vardiyasi","startedAt":"2026-04-02T08:00:00Z","planStart":"2026-04-02T08:00:00Z","planEnd":"2026-04-02T16:00:00Z","performanceMode":"TARGET","targetQty":10},'
                    '"counts":{"total":4,"good":4,"rework":0,"scrap":0,"byColor":{"red":{"total":1,"good":1,"rework":0,"scrap":0},"yellow":{"total":1,"good":1,"rework":0,"scrap":0},"blue":{"total":2,"good":2,"rework":0,"scrap":0}}},'
                    '"lastEventSummary":"Canli OEE backend hesapla","lastUpdatedAt":"2026-04-02T08:05:00Z"}'
                )

            with patch.dict(os.environ, {"MES_WEB_OEE_RUNTIME_STATE_PATH": state_path}, clear=False):
                config = AppConfig.from_env()
                store = DashboardStore(config)
                snapshot = store.get_dashboard_snapshot(config.module_id)

            self.assertEqual(snapshot["oee"]["production"]["total"], 4)
            self.assertEqual(snapshot["oee"]["production"]["good"], 4)
            self.assertEqual(snapshot["oee"]["colors"]["blue"]["good"], 2)
            self.assertEqual(snapshot["oee"]["kpis"]["quality"], 100.0)
            self.assertEqual(snapshot["oee"]["kpis"]["performance"], 40.0)

    def test_runtime_state_exposes_recent_items_for_quality_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "oee_runtime_state.json")
            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"shiftSelected":"SHIFT-A","performanceMode":"TARGET",'
                    '"itemsById":{"42":{"item_id":"42","measure_id":"7","color":"blue","classification":"REWORK","completed_at":"2026-04-02T08:01:05Z","updated_at":"2026-04-02T08:02:00Z","decision_source":"CORE_STABLE","review_required":false}},'
                    '"recentItemIds":["42"],'
                    '"counts":{"total":1,"good":0,"rework":1,"scrap":0,"byColor":{"red":{"total":0,"good":0,"rework":0,"scrap":0},"yellow":{"total":0,"good":0,"rework":0,"scrap":0},"blue":{"total":1,"good":0,"rework":1,"scrap":0}}}}'
                )

            with patch.dict(os.environ, {"MES_WEB_OEE_RUNTIME_STATE_PATH": state_path}, clear=False):
                config = AppConfig.from_env()
                store = DashboardStore(config)
                snapshot = store.get_dashboard_snapshot(config.module_id)

            self.assertEqual(snapshot["oee"]["recent_items"][0]["item_id"], "42")
            self.assertEqual(snapshot["oee"]["recent_items"][0]["classification"], "REWORK")
            self.assertEqual(snapshot["oee"]["controls"]["quality_override_options"], ["GOOD", "REWORK", "SCRAP"])

    def test_runtime_state_exposes_vision_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = os.path.join(temp_dir, "oee_runtime_state.json")
            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"shiftSelected":"SHIFT-A","performanceMode":"TARGET",'
                    '"itemsById":{"42":{"item_id":"42","measure_id":"7","sensor_color":"yellow","vision_color":"red","final_color":"red","color":"red","classification":"GOOD","completed_at":"2026-04-02T08:01:05Z","updated_at":"2026-04-02T08:02:00Z","decision_source":"VISION","finalization_reason":"VISION_CORRECTED_MISMATCH","correlation_status":"MATCHED","pick_trigger_source":"EARLY"}},'
                    '"recentItemIds":["42"],'
                    '"vision":{"healthState":"online","lastRejectReason":"HEAD_CHANGED","metrics":{"mismatchCount":1,"earlyAcceptedCount":2,"earlyRejectedCount":3,"lateAuditCount":4}},'
                    '"counts":{"total":1,"good":1,"rework":0,"scrap":0,"byColor":{"red":{"total":1,"good":1,"rework":0,"scrap":0},"yellow":{"total":0,"good":0,"rework":0,"scrap":0},"blue":{"total":0,"good":0,"rework":0,"scrap":0}}}}'
                )

            with patch.dict(os.environ, {"MES_WEB_OEE_RUNTIME_STATE_PATH": state_path}, clear=False):
                config = AppConfig.from_env()
                store = DashboardStore(config)
                snapshot = store.get_dashboard_snapshot(config.module_id)

            runtime = snapshot["vision_ingest"]["runtime"]
            self.assertEqual(runtime["health_state"], "online")
            self.assertEqual(runtime["mismatch_count"], 1)
            self.assertEqual(runtime["early_accepted_count"], 2)
            self.assertEqual(runtime["early_rejected_count"], 3)
            self.assertEqual(runtime["last_reject_reason"], "HEAD_CHANGED")
            self.assertEqual(runtime["last_item"]["sensor_color"], "yellow")
            self.assertEqual(runtime["last_item"]["vision_color"], "red")
            self.assertEqual(runtime["last_item"]["final_color"], "red")
            self.assertEqual(runtime["last_item"]["correlation_status"], "MATCHED")


if __name__ == "__main__":
    unittest.main()
