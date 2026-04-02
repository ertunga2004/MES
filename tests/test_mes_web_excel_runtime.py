from __future__ import annotations

import unittest

from mes_web.excel_runtime import WorkbookProjector


class WorkbookProjectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projector = WorkbookProjector()

    def test_measurement_queue_and_completion_flow_into_rows(self) -> None:
        measurement_rows = self.projector.consume_mega_log(
            "MEGA|TCS3200|STATE=MEASURING|ITEM_ID=42|MEASURE_ID=8|FINAL=KIRMIZI|FINAL_SOURCE=CORE_STABLE|SEARCH_HINT=SARI|SEARCH_HINT_WIN=2|SEARCH_HINT_SECOND=1|SEARCH_HINT_STRONG=1|SEARCH_HINT_FALLBACK_ALLOWED=1|CORE_USED=1|CORE_N=6|OBJ_N=10|MEDIAN_NEAREST=SARI|SCORE_NEAREST=SARI|MED_R=10|MED_G=20|MED_B=30|MED_D_R=11|MED_D_Y=22|MED_D_B=33|MED_D_X=44|X_R=101|X_G=102|X_B=103|MED_OBJ=1|CONF=0|CORE_STR_MIN=12|CORE_STR_MAX=24|VOTE_WIN=6|VOTE_SECOND=1|VOTE_CLASSIFIED=6|VOTE_BOS=3|VOTE_R=0|VOTE_Y=1|VOTE_B=2|VOTE_CAL=0|TOT_R=4|TOT_Y=5|TOT_B=6|TOT_BOS=7|TOT_CAL=0",
            "2026-04-02T10:15:25Z",
        )
        queue_rows = self.projector.consume_mega_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=42|MEASURE_ID=8|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=640",
            "2026-04-02T10:15:26Z",
        )
        completed_rows = self.projector.consume_mega_log(
            "MEGA|AUTO|EVENT=PICKPLACE_DONE|ITEM_ID=42|MEASURE_ID=8|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE",
            "2026-04-02T10:15:29Z",
        )

        self.assertIn("2_Olcumler", measurement_rows)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["item_id"], "42")
        self.assertEqual(measurement_rows["2_Olcumler"][0]["final_color_code"], "red")
        self.assertEqual(measurement_rows["2_Olcumler"][0]["search_hint"], "SARI")
        self.assertEqual(measurement_rows["2_Olcumler"][0]["search_hint_win"], 2)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["core_n"], 6)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["med_d_x"], 44)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["x_b"], 103)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["vote_x"], 3)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["tot_x"], 7)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["measurement_error_flag"], 1)
        self.assertEqual(measurement_rows["2_Olcumler"][0]["measurement_error_reason"], "confidence=0")
        self.assertEqual(queue_rows["1_Olay_Logu"][0]["event_type_code"], "queue_enq")
        self.assertEqual(queue_rows["1_Olay_Logu"][0]["mega_state_id"], 7)
        self.assertIn("4_Uretim_Tamamlanan", completed_rows)
        self.assertEqual(completed_rows["4_Uretim_Tamamlanan"][0]["item_id"], "42")
        self.assertEqual(completed_rows["4_Uretim_Tamamlanan"][0]["status_code"], "COMPLETED")
        self.assertEqual(completed_rows["4_Uretim_Tamamlanan"][0]["travel_ms"], 640)

    def test_vision_event_creates_vision_and_raw_rows(self) -> None:
        rows = self.projector.consume_vision_event(
            {
                "event": "line_crossed",
                "color_name": "blue",
                "track_id": 17,
                "frame_index": 33,
                "bbox": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
            },
            "2026-04-02T10:15:27Z",
        )

        self.assertIn("6_Vision", rows)
        self.assertEqual(rows["6_Vision"][0]["vision_track_id"], "17")
        self.assertEqual(rows["6_Vision"][0]["color_code"], "blue")
        self.assertEqual(rows["7_Raw_Logs"][0]["event_type_code"], "vision_event")

    def test_local_counts_reset_creates_system_rows(self) -> None:
        rows = self.projector.consume_local_counts_reset("2026-04-02T10:15:30Z")

        self.assertEqual(rows["1_Olay_Logu"][0]["source_code"], "system")
        self.assertEqual(rows["1_Olay_Logu"][0]["raw_line"], "SYSTEM|COUNTS|RESET")
        self.assertEqual(rows["7_Raw_Logs"][0]["source_topic"], "local/system")


if __name__ == "__main__":
    unittest.main()
