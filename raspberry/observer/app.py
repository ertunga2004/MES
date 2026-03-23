from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import time
from typing import TYPE_CHECKING, Iterable

from .config import CameraConfig, ObserverConfig, ROI, UiConfig, load_box_profiles, load_observer_config
from .models import Detection, TrackSnapshot
from .mqtt_client import ObserverMqttClient
from .tracker import CentroidTracker
from .vision import ColorBoxDetector

if TYPE_CHECKING:
    import numpy as np


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MQTT connected conveyor observer.")
    parser.add_argument(
        "--config",
        default="config/observer.example.json",
        help="Observer config JSON path.",
    )
    parser.add_argument(
        "--boxes",
        default="config/boxes.example.json",
        help="Box profile config JSON path.",
    )
    parser.add_argument(
        "--source",
        help="Optional camera index, video path, or stream URI override.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Disable OpenCV windows and run headless.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python is not installed. Run: pip install -r requirements.txt") from exc

    config = load_observer_config(args.config)

    if args.source is not None:
        source = int(args.source) if args.source.isdigit() else args.source
        config = ObserverConfig(
            device_name=config.device_name,
            camera=CameraConfig(
                source=source,
                width=config.camera.width,
                height=config.camera.height,
                fps=config.camera.fps,
                flip_horizontal=config.camera.flip_horizontal,
            ),
            processing=config.processing,
            tracker=config.tracker,
            line_counter=config.line_counter,
            mqtt=config.mqtt,
            ui=UiConfig(
                show_windows=False if args.no_gui else config.ui.show_windows,
                show_masks=False if args.no_gui else config.ui.show_masks,
                show_pending_tracks=False if args.no_gui else config.ui.show_pending_tracks,
            ),
        )
    elif args.no_gui:
        config = ObserverConfig(
            device_name=config.device_name,
            camera=config.camera,
            processing=config.processing,
            tracker=config.tracker,
            line_counter=config.line_counter,
            mqtt=config.mqtt,
            ui=UiConfig(show_windows=False, show_masks=False, show_pending_tracks=False),
        )

    profiles = load_box_profiles(args.boxes)
    detector = ColorBoxDetector(profiles, config.processing)
    tracker = CentroidTracker(config.tracker, config.line_counter)
    mqtt_client = ObserverMqttClient(config.mqtt)
    mqtt_client.connect()

    capture = cv2.VideoCapture(config.camera.source)
    if not capture.isOpened():
        raise RuntimeError(f"Video source could not be opened: {config.camera.source}")

    if config.camera.width:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera.width)
    if config.camera.height:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera.height)
    if config.camera.fps:
        capture.set(cv2.CAP_PROP_FPS, config.camera.fps)

    frame_times: deque[float] = deque(maxlen=20)
    last_publish_at = 0.0
    last_heartbeat_at = 0.0
    frame_index = 0

    mqtt_client.publish_json(
        "status",
        {
            "device_name": config.device_name,
            "state": "starting",
            "timestamp": _utc_now(),
            "source": str(config.camera.source),
        },
        retain=True,
    )

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Frame read failed, observer is stopping.")
                break

            started_at = time.perf_counter()
            if config.camera.flip_horizontal:
                frame = cv2.flip(frame, 1)

            roi_frame, roi_offset = _apply_roi(frame, config.processing.roi)
            detections, masks = detector.detect(roi_frame)
            detections = _translate_detections(detections, roi_offset)

            frame_index += 1
            timestamp_iso = _utc_now()
            tracks, events = tracker.update(detections, frame_index, timestamp_iso)
            frame_times.append(time.perf_counter() - started_at)
            fps = _fps_from_samples(frame_times)
            confirmed_count = sum(1 for track in tracks if track.confirmed)
            pending_count = len(tracks) - confirmed_count

            now = time.monotonic()
            if now - last_publish_at >= config.mqtt.publish_interval_sec:
                mqtt_client.publish_json(
                    "tracks",
                    {
                        "device_name": config.device_name,
                        "timestamp": timestamp_iso,
                        "frame_index": frame_index,
                        "active_tracks": confirmed_count,
                        "pending_tracks": pending_count,
                        "total_crossings": tracker.total_crossings,
                        "tracks": [track.to_dict() for track in tracks],
                    },
                )
                mqtt_client.publish_json(
                    "status",
                    {
                        "device_name": config.device_name,
                        "state": "running",
                        "timestamp": timestamp_iso,
                        "frame_index": frame_index,
                        "fps": round(fps, 2),
                        "active_tracks": confirmed_count,
                        "pending_tracks": pending_count,
                        "total_crossings": tracker.total_crossings,
                        "roi": _roi_to_dict(config.processing.roi),
                    },
                    retain=True,
                )
                last_publish_at = now

            if now - last_heartbeat_at >= config.mqtt.heartbeat_interval_sec:
                mqtt_client.publish_json(
                    "heartbeat",
                    {
                        "device_name": config.device_name,
                        "timestamp": timestamp_iso,
                        "frame_index": frame_index,
                    },
                )
                last_heartbeat_at = now

            for event in events:
                mqtt_client.publish_json("events", event)

            if config.ui.show_windows:
                display_frame = _draw_overlay(frame.copy(), tracks, config, fps, tracker.total_crossings)
                cv2.imshow("Observer", display_frame)
                if config.ui.show_masks:
                    mask_preview = _compose_mask_preview(masks)
                    if mask_preview is not None:
                        cv2.imshow("Masks", mask_preview)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
            elif frame_index % 30 == 0:
                print(
                    f"[{timestamp_iso}] frame={frame_index} active={confirmed_count} pending={pending_count} "
                    f"crossings={tracker.total_crossings} fps={fps:.2f}"
                )

    finally:
        mqtt_client.publish_json(
            "status",
            {
                "device_name": config.device_name,
                "state": "stopped",
                "timestamp": _utc_now(),
                "frame_index": frame_index,
                "total_crossings": tracker.total_crossings,
            },
            retain=True,
        )
        capture.release()
        mqtt_client.disconnect()
        cv2.destroyAllWindows()

    return 0


def _apply_roi(frame: "np.ndarray", roi: ROI | None) -> tuple["np.ndarray", tuple[int, int]]:
    if roi is None:
        return frame, (0, 0)

    height, width = frame.shape[:2]
    x = max(0, min(roi.x, max(0, width - 1)))
    y = max(0, min(roi.y, max(0, height - 1)))
    roi_width = max(1, min(roi.width, width - x))
    roi_height = max(1, min(roi.height, height - y))
    return frame[y : y + roi_height, x : x + roi_width], (x, y)


def _translate_detections(
    detections: Iterable[Detection],
    offset: tuple[int, int],
) -> list[Detection]:
    offset_x, offset_y = offset
    detection_list = list(detections)
    if offset_x == 0 and offset_y == 0:
        return detection_list

    translated: list[Detection] = []
    for detection in detection_list:
        x, y, w, h = detection.bbox
        cx, cy = detection.centroid
        translated.append(
            Detection(
                profile_id=detection.profile_id,
                label=detection.label,
                color_name=detection.color_name,
                bbox=(x + offset_x, y + offset_y, w, h),
                centroid=(cx + offset_x, cy + offset_y),
                area=detection.area,
                confidence=detection.confidence,
                overlay_bgr=detection.overlay_bgr,
                priority=detection.priority,
                score=detection.score,
                metadata=detection.metadata,
            )
        )
    return translated


def _fps_from_samples(samples: deque[float]) -> float:
    if not samples:
        return 0.0
    average_frame_time = sum(samples) / len(samples)
    if average_frame_time <= 0:
        return 0.0
    return 1.0 / average_frame_time


def _draw_overlay(
    frame: "np.ndarray",
    tracks: list[TrackSnapshot],
    config: ObserverConfig,
    fps: float,
    total_crossings: int,
) -> "np.ndarray":
    import cv2

    if config.processing.roi is not None:
        roi = config.processing.roi
        cv2.rectangle(
            frame,
            (roi.x, roi.y),
            (roi.x + roi.width, roi.y + roi.height),
            (255, 255, 0),
            2,
        )

    if config.line_counter.enabled:
        line_x = config.line_counter.x
        cv2.line(frame, (line_x, 0), (line_x, frame.shape[0]), (0, 255, 255), 2)

    for track in tracks:
        if not track.confirmed and not config.ui.show_pending_tracks:
            continue
        x, y, w, h = track.bbox
        color = tuple(int(item) for item in track.overlay_bgr) if track.confirmed else (160, 160, 160)
        thickness = 2 if track.confirmed else 1
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, thickness)
        cv2.circle(frame, track.centroid, 4, color, -1)
        title = f"ID:{track.track_id} {track.label}"
        if not track.confirmed:
            title += f" P{track.hits}"
        cv2.putText(
            frame,
            title,
            (x, max(20, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            thickness,
        )
        cv2.putText(
            frame,
            f"{track.centroid[0]},{track.centroid[1]}",
            (x, y + h + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
        )

    cv2.putText(
        frame,
        (
            f"{config.device_name} | active={sum(1 for track in tracks if track.confirmed)} "
            f"| pending={sum(1 for track in tracks if not track.confirmed)} "
            f"| crossed={total_crossings} | fps={fps:.2f}"
        ),
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
    )
    return frame


def _compose_mask_preview(masks: dict[str, "np.ndarray"]) -> "np.ndarray" | None:
    import cv2

    if not masks:
        return None

    tiles: list[np.ndarray] = []
    for label, mask in masks.items():
        tile = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        cv2.putText(
            tile,
            label,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
        tiles.append(tile)

    if len(tiles) == 1:
        return tiles[0]

    max_width = max(tile.shape[1] for tile in tiles)
    normalized: list[np.ndarray] = []
    for tile in tiles:
        if tile.shape[1] == max_width:
            normalized.append(tile)
            continue
        scale = max_width / float(tile.shape[1])
        normalized.append(
            cv2.resize(tile, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        )

    return cv2.vconcat(normalized)


def _roi_to_dict(roi: ROI | None) -> dict[str, int] | None:
    if roi is None:
        return None
    return {"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
