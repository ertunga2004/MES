from __future__ import annotations

import unittest

from mes_web.parsers import (
    normalize_color,
    parse_bridge_status_line,
    parse_mega_event_from_log,
    parse_status_line,
    parse_tablet_fault_line,
    parse_tablet_oee_line,
    parse_vision_event,
)


class ParserTests(unittest.TestCase):
    def test_parse_status_line(self) -> None:
        parsed = parse_status_line(
            "MEGA|STATUS|AUTO=1|STATE=RUN|CONVEYOR=RUN|ROBOT=WAIT_ARM|LAST=KIRMIZI|DIR=FWD|PWM=255|TRAVEL_MS=1234|LIM22=0|LIM23=1|STEP=1|STEP_HOLD=0|STEP_US=800|QUEUE=3|STOP_REQ=0"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["mode"], "auto")
        self.assertEqual(parsed["system_state"], "run")
        self.assertEqual(parsed["robot_state"], "wait_arm")
        self.assertEqual(parsed["last_color"], "red")
        self.assertEqual(parsed["queue_depth"], 3)
        self.assertTrue(parsed["step_enabled"])

    def test_parse_bridge_status_line(self) -> None:
        parsed = parse_bridge_status_line("ESP32|BRIDGE|WIFI=1|MQTT=0|QUEUE=2|DROP_UART=1|DROP_PUB=3")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["state"], "degraded")
        self.assertEqual(parsed["queue"], 2)
        self.assertEqual(parsed["drop_uart"], 1)
        self.assertEqual(parsed["drop_pub"], 3)

    def test_parse_mega_queue_event(self) -> None:
        parsed = parse_mega_event_from_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=8|COLOR=SARI|DECISION_SOURCE=mega|PENDING=5|TRAVEL_MS=640"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["event_type"], "queue_enq")
        self.assertEqual(parsed["color"], "yellow")
        self.assertEqual(parsed["compare_color"], "yellow")
        self.assertEqual(parsed["travel_ms"], 640)
        self.assertEqual(parsed["mega_state"], "queue")

    def test_parse_mega_identifiers_skip_zero(self) -> None:
        parsed = parse_mega_event_from_log(
            "MEGA|TCS3200|STATE=MEASURING|ITEM_ID=0|MEASURE_ID=8|FINAL=BELIRSIZ|FINAL_SOURCE=CORE_STABLE"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["item_id"], "")
        self.assertEqual(parsed["measure_id"], "8")

    def test_parse_vision_event(self) -> None:
        parsed = parse_vision_event(
            {
                "event": "line_crossed",
                "color_name": "blue",
                "track_id": 17,
                "profile_id": "blue_box",
                "frame_index": 33,
                "confidence": 0.91,
                "item_id": "42",
                "measure_id": "8",
                "correlation_status": "MATCHED",
                "late_vision_audit_flag": False,
                "decision_applied": True,
                "review_required": False,
                "observed_at": "2026-04-02T10:15:27Z",
                "published_at": "2026-04-02T10:15:27.050Z",
                "received_at": "2026-04-02T10:15:27.090Z",
            }
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["event_type"], "line_crossed")
        self.assertEqual(parsed["color"], "blue")
        self.assertEqual(parsed["compare_color"], "blue")
        self.assertEqual(parsed["item_id"], "42")
        self.assertEqual(parsed["measure_id"], "8")
        self.assertEqual(parsed["confidence"], 0.91)
        self.assertEqual(parsed["correlation_status"], "matched")
        self.assertTrue(parsed["decision_applied"])
        self.assertEqual(parsed["vision_observed_at"], "2026-04-02T10:15:27Z")
        self.assertEqual(parsed["vision_published_at"], "2026-04-02T10:15:27.050Z")
        self.assertEqual(parsed["vision_received_at"], "2026-04-02T10:15:27.090Z")
        self.assertIn("profile=blue_box", parsed["notes"])

    def test_parse_mega_early_pick_reject_event(self) -> None:
        parsed = parse_mega_event_from_log(
            "MEGA|AUTO|STATE=SEARCHING|EVENT=PICK_EARLY_REJECT|ITEM_ID=42|MEASURE_ID=8|TRIGGER=EARLY|REASON=HEAD_CHANGED"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["event_type"], "pick_command_rejected")
        self.assertEqual(parsed["item_id"], "42")
        self.assertEqual(parsed["measure_id"], "8")
        self.assertEqual(parsed["trigger_source"], "early")
        self.assertEqual(parsed["reject_reason"], "head_changed")

    def test_parse_tablet_oee_line(self) -> None:
        parsed = parse_tablet_oee_line(
            "[02.04.2026 12:00:00.000] |Tablet|OEE| OEE:0.5470|KULL:0.6170|PERF:1.0000|KALITE:0.9000|MAVI_S:5|MAVI_R:1|MAVI_H:0|SARI_S:4|SARI_R:0|SARI_H:1|KIRMIZI_S:3|KIRMIZI_R:0|KIRMIZI_H:2"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["oee"], 54.7)
        self.assertEqual(parsed["availability"], 61.7)
        self.assertEqual(parsed["production"]["total"], 16)
        self.assertEqual(parsed["colors"]["blue"]["rework"], 1)
        self.assertEqual(parsed["colors"]["red"]["scrap"], 2)

    def test_parse_tablet_fault_line(self) -> None:
        parsed = parse_tablet_fault_line(
            "[02.04.2026 12:00:00.000] |Tablet|Ariza| KATEGORI:MEKANIK|NEDEN:Robot Kol Sikis masi|DURUM:BASLADI|BASLANGIC:12:00:00"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["reason"], "Robot Kol Sikis masi")
        self.assertEqual(parsed["status"], "BASLADI")
        self.assertEqual(parsed["started_at_text"], "12:00:00")

    def test_normalize_color(self) -> None:
        self.assertEqual(normalize_color("KIRMIZI"), "red")
        self.assertEqual(normalize_color("mavi"), "blue")


if __name__ == "__main__":
    unittest.main()
