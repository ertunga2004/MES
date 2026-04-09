from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
RASPBERRY_ROOT = REPO_ROOT / "raspberry"
if str(RASPBERRY_ROOT) not in sys.path:
    sys.path.insert(0, str(RASPBERRY_ROOT))

from observer.config import LineCounterConfig, TrackerConfig
from observer.models import Detection
from observer.system_clock import SystemClockSetter, should_apply_system_clock
from observer.time_sync import TimestampOffsetClock
from observer.tracker import CentroidTracker


class RaspberryTrackerTests(unittest.TestCase):
    def test_line_crossed_uses_leading_edge_for_left_to_right(self) -> None:
        tracker = CentroidTracker(
            TrackerConfig(
                max_distance=200,
                min_confirmed_frames=1,
            ),
            LineCounterConfig(enabled=True, x=100, direction="left_to_right"),
        )

        first_detection = Detection(
            profile_id="red_box",
            label="Red Box",
            color_name="red",
            bbox=(40, 20, 50, 60),
            centroid=(65, 50),
            area=3000.0,
            confidence=0.95,
            overlay_bgr=(0, 0, 255),
            metadata={},
        )
        second_detection = Detection(
            profile_id="red_box",
            label="Red Box",
            color_name="red",
            bbox=(50, 20, 50, 60),
            centroid=(75, 50),
            area=3000.0,
            confidence=0.95,
            overlay_bgr=(0, 0, 255),
            metadata={},
        )

        _, first_events = tracker.update([first_detection], frame_index=1, timestamp_iso="2026-04-09T10:00:00Z")
        _, second_events = tracker.update([second_detection], frame_index=2, timestamp_iso="2026-04-09T10:00:01Z")

        self.assertTrue(any(event["event"] == "box_confirmed" for event in first_events))
        line_events = [event for event in second_events if event["event"] == "line_crossed"]
        self.assertEqual(len(line_events), 1)
        self.assertEqual(line_events[0]["leading_edge_x"], 100)
        self.assertEqual(line_events[0]["total_crossings"], 1)

    def test_line_crossed_uses_left_edge_for_right_to_left(self) -> None:
        tracker = CentroidTracker(
            TrackerConfig(
                max_distance=200,
                min_confirmed_frames=1,
                expected_direction="right_to_left",
            ),
            LineCounterConfig(enabled=True, x=100, direction="right_to_left"),
        )

        first_detection = Detection(
            profile_id="blue_box",
            label="Blue Box",
            color_name="blue",
            bbox=(110, 20, 50, 60),
            centroid=(135, 50),
            area=3000.0,
            confidence=0.92,
            overlay_bgr=(255, 0, 0),
            metadata={},
        )
        second_detection = Detection(
            profile_id="blue_box",
            label="Blue Box",
            color_name="blue",
            bbox=(100, 20, 50, 60),
            centroid=(125, 50),
            area=3000.0,
            confidence=0.92,
            overlay_bgr=(255, 0, 0),
            metadata={},
        )

        tracker.update([first_detection], frame_index=1, timestamp_iso="2026-04-09T10:00:00Z")
        _, events = tracker.update([second_detection], frame_index=2, timestamp_iso="2026-04-09T10:00:01Z")

        line_events = [event for event in events if event["event"] == "line_crossed"]
        self.assertEqual(len(line_events), 1)
        self.assertEqual(line_events[0]["leading_edge_x"], 100)


class RaspberryTimeSyncTests(unittest.TestCase):
    def test_sync_from_iso_payload_sets_clock_status(self) -> None:
        clock = TimestampOffsetClock()
        result = clock.sync_from_payload({"timestamp": "2026-04-09T12:34:56+03:00"}, source="mqtt")
        status = clock.status()
        now = datetime.fromisoformat(clock.iso_now())
        target = datetime.fromisoformat(result.target_timestamp)

        self.assertTrue(status["clock_synced"])
        self.assertEqual(status["clock_last_sync_source"], "mqtt:timestamp")
        self.assertLess(abs((now - target).total_seconds()), 2.0)

    def test_sync_from_unix_ms_payload_is_supported(self) -> None:
        clock = TimestampOffsetClock()
        result = clock.sync_from_payload({"unix_ms": 0}, source="mqtt")

        self.assertEqual(result.target_timestamp, "1970-01-01T00:00:00+00:00")
        self.assertEqual(clock.status()["clock_last_sync_source"], "mqtt:unix_ms")


class RaspberrySystemClockTests(unittest.TestCase):
    def test_should_apply_system_clock_reads_flag(self) -> None:
        self.assertTrue(should_apply_system_clock({"set_system_clock": True}))
        self.assertTrue(should_apply_system_clock({"set_system_clock": "true"}))
        self.assertFalse(should_apply_system_clock({"set_system_clock": False}))
        self.assertFalse(should_apply_system_clock("2026-04-09T12:34:56+03:00"))

    @patch("observer.system_clock.subprocess.run")
    def test_system_clock_setter_runs_configured_command(self, run_mock) -> None:
        run_mock.return_value.stdout = "updated"
        run_mock.return_value.stderr = ""
        setter = SystemClockSetter(command="/usr/bin/sudo -n /tmp/set_system_time.sh")

        result = setter.apply("2026-04-09T12:34:56+03:00")

        self.assertTrue(result.success)
        run_mock.assert_called_once()

    def test_system_clock_setter_reports_missing_command(self) -> None:
        setter = SystemClockSetter(command="")

        result = setter.apply("2026-04-09T12:34:56+03:00")

        self.assertFalse(result.success)
        self.assertIn("not configured", str(result.message))


if __name__ == "__main__":
    unittest.main()
