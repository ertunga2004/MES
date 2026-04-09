from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
RASPBERRY_ROOT = REPO_ROOT / "raspberry"
if str(RASPBERRY_ROOT) not in sys.path:
    sys.path.insert(0, str(RASPBERRY_ROOT))

from observer.capture import is_picamera2_source
from observer.config import (
    CameraConfig,
    LineCounterConfig,
    ObserverConfig,
    ProcessingConfig,
    ROI,
    load_observer_config,
    save_observer_config,
)


class RaspberryConfigTests(unittest.TestCase):
    def test_load_observer_config_reads_preprocess_fields(self) -> None:
        payload = {
            "device_name": "observer-pi",
            "camera": {
                "source": "picamera2",
                "width": 640,
                "height": 480,
                "fps": 15,
            },
            "processing": {
                "normalize_lighting": True,
                "clahe_clip_limit": 2.2,
                "clahe_tile_grid_size": 6,
                "min_saturation": 45,
                "min_value": 50,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "observer.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            config = load_observer_config(config_path)

        self.assertEqual(config.camera.source, "picamera2")
        self.assertTrue(config.processing.normalize_lighting)
        self.assertEqual(config.processing.clahe_clip_limit, 2.2)
        self.assertEqual(config.processing.clahe_tile_grid_size, 6)
        self.assertEqual(config.processing.min_saturation, 45)
        self.assertEqual(config.processing.min_value, 50)

    def test_picamera2_source_aliases(self) -> None:
        self.assertTrue(is_picamera2_source("picamera2"))
        self.assertTrue(is_picamera2_source("PICAM"))
        self.assertTrue(is_picamera2_source("libcamera"))
        self.assertFalse(is_picamera2_source(0))
        self.assertFalse(is_picamera2_source("0"))

    def test_save_observer_config_persists_runtime_adjustments(self) -> None:
        payload = {
            "device_name": "observer-pi",
            "camera": {"source": 0, "width": 640, "height": 480, "fps": 15, "rotate_ccw_90": False},
            "processing": {"roi": {"x": 10, "y": 20, "width": 300, "height": 150}},
            "line_counter": {"enabled": True, "x": 320, "direction": "left_to_right"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "observer.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_observer_config(config_path)

            updated = ObserverConfig(
                device_name=loaded.device_name,
                camera=CameraConfig(
                    source=loaded.camera.source,
                    width=loaded.camera.width,
                    height=loaded.camera.height,
                    fps=loaded.camera.fps,
                    flip_horizontal=loaded.camera.flip_horizontal,
                    rotate_ccw_90=True,
                ),
                processing=ProcessingConfig(
                    roi=ROI(x=55, y=65, width=210, height=120),
                    blur_kernel=loaded.processing.blur_kernel,
                    morph_kernel=loaded.processing.morph_kernel,
                    open_iterations=loaded.processing.open_iterations,
                    close_iterations=loaded.processing.close_iterations,
                    min_contour_area=loaded.processing.min_contour_area,
                    normalize_lighting=loaded.processing.normalize_lighting,
                    clahe_clip_limit=loaded.processing.clahe_clip_limit,
                    clahe_tile_grid_size=loaded.processing.clahe_tile_grid_size,
                    min_saturation=loaded.processing.min_saturation,
                    min_value=loaded.processing.min_value,
                ),
                tracker=loaded.tracker,
                line_counter=LineCounterConfig(enabled=True, x=140, direction="left_to_right"),
                mqtt=loaded.mqtt,
                ui=loaded.ui,
            )

            save_observer_config(config_path, updated)
            reloaded = load_observer_config(config_path)

        self.assertTrue(reloaded.camera.rotate_ccw_90)
        assert reloaded.processing.roi is not None
        self.assertEqual(reloaded.processing.roi.x, 55)
        self.assertEqual(reloaded.processing.roi.y, 65)
        self.assertEqual(reloaded.processing.roi.width, 210)
        self.assertEqual(reloaded.processing.roi.height, 120)
        self.assertEqual(reloaded.line_counter.x, 140)


if __name__ == "__main__":
    unittest.main()
