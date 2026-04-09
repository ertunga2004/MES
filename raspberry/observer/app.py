from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import TYPE_CHECKING, Iterable

from .capture import CaptureRuntimeInfo, open_capture
from .config import (
    CameraConfig,
    LineCounterConfig,
    ObserverConfig,
    ProcessingConfig,
    ROI,
    UiConfig,
    load_box_profiles,
    load_observer_config,
    save_observer_config,
)
from .models import Detection, TrackSnapshot
from .mqtt_client import ObserverMqttClient
from .system_clock import SystemClockSetter, should_apply_system_clock
from .time_sync import TimestampOffsetClock
from .tracker import CentroidTracker
from .vision import ColorBoxDetector

if TYPE_CHECKING:
    import numpy as np


_MIN_ROI_SIZE = 40
_ROI_HANDLE_SIZE = 18
_LINE_HITBOX = 12


@dataclass
class RuntimeAdjustments:
    roi: ROI | None
    line_x: int
    rotate_ccw_90: bool


@dataclass
class PreviewEditor:
    runtime: RuntimeAdjustments
    line_enabled: bool
    preview_scale: float = 1.0
    frame_size: tuple[int, int] = (0, 0)
    drag_mode: str | None = None
    drag_anchor: tuple[int, int] | None = None
    roi_drag_offset: tuple[int, int] = (0, 0)
    status_text: str = ""
    status_expires_at: float = 0.0

    def set_frame(self, frame: "np.ndarray") -> None:
        self.frame_size = (int(frame.shape[1]), int(frame.shape[0]))

    def set_preview_scale(self, scale: float) -> None:
        self.preview_scale = max(0.1, float(scale or 1.0))

    def set_status(self, text: str, duration_sec: float = 3.0) -> None:
        self.status_text = text
        self.status_expires_at = time.monotonic() + max(0.1, duration_sec)

    def active_status(self) -> str:
        if self.status_text and time.monotonic() <= self.status_expires_at:
            return self.status_text
        return ""

    def handle_mouse(self, event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if self.frame_size[0] <= 0 or self.frame_size[1] <= 0:
            return

        source_x, source_y = self._to_source(x, y)
        roi = self.runtime.roi

        if event == 1:
            self.drag_anchor = (source_x, source_y)
            if self.line_enabled and abs(source_x - self.runtime.line_x) <= _LINE_HITBOX:
                self.drag_mode = "move_line"
                return
            if roi is not None and self._near_roi_handle(source_x, source_y, roi):
                self.drag_mode = "resize_roi"
                return
            if roi is not None and self._point_in_roi(source_x, source_y, roi):
                self.drag_mode = "move_roi"
                self.roi_drag_offset = (source_x - roi.x, source_y - roi.y)
                return
            self.drag_mode = "draw_roi"
            self.runtime.roi = ROI(source_x, source_y, _MIN_ROI_SIZE, _MIN_ROI_SIZE)
            return

        if event == 0 and self.drag_mode:
            frame_width, frame_height = self.frame_size
            if self.drag_mode == "move_line":
                self.runtime.line_x = _clamp_line_x(source_x, frame_width)
                return

            if self.drag_mode == "move_roi" and roi is not None:
                next_x = _clamp_int(source_x - self.roi_drag_offset[0], 0, max(0, frame_width - roi.width))
                next_y = _clamp_int(source_y - self.roi_drag_offset[1], 0, max(0, frame_height - roi.height))
                self.runtime.roi = ROI(next_x, next_y, roi.width, roi.height)
                return

            if self.drag_mode == "resize_roi" and roi is not None:
                next_width = _clamp_int(source_x - roi.x, _MIN_ROI_SIZE, max(_MIN_ROI_SIZE, frame_width - roi.x))
                next_height = _clamp_int(source_y - roi.y, _MIN_ROI_SIZE, max(_MIN_ROI_SIZE, frame_height - roi.y))
                self.runtime.roi = ROI(roi.x, roi.y, next_width, next_height)
                return

            if self.drag_mode == "draw_roi" and self.drag_anchor is not None:
                anchor_x, anchor_y = self.drag_anchor
                left = min(anchor_x, source_x)
                top = min(anchor_y, source_y)
                width = max(_MIN_ROI_SIZE, abs(source_x - anchor_x))
                height = max(_MIN_ROI_SIZE, abs(source_y - anchor_y))
                self.runtime.roi = _fit_roi_to_bounds(
                    ROI(left, top, width, height),
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
                return

        if event == 4:
            if self.drag_mode == "move_line":
                self.set_status(f"Line x updated: {self.runtime.line_x}")
            elif self.drag_mode in {"move_roi", "resize_roi", "draw_roi"} and self.runtime.roi is not None:
                self.set_status(
                    (
                        f"ROI updated: x={self.runtime.roi.x} y={self.runtime.roi.y} "
                        f"w={self.runtime.roi.width} h={self.runtime.roi.height}"
                    )
                )
            self.drag_mode = None
            self.drag_anchor = None

    def _to_source(self, x: int, y: int) -> tuple[int, int]:
        frame_width, frame_height = self.frame_size
        source_x = _clamp_int(int(round(x / self.preview_scale)), 0, max(0, frame_width - 1))
        source_y = _clamp_int(int(round(y / self.preview_scale)), 0, max(0, frame_height - 1))
        return source_x, source_y

    def _point_in_roi(self, x: int, y: int, roi: ROI) -> bool:
        return roi.x <= x <= roi.x + roi.width and roi.y <= y <= roi.y + roi.height

    def _near_roi_handle(self, x: int, y: int, roi: ROI) -> bool:
        return (
            abs(x - (roi.x + roi.width)) <= _ROI_HANDLE_SIZE
            and abs(y - (roi.y + roi.height)) <= _ROI_HANDLE_SIZE
        )


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
    parser.add_argument("--width", type=int, help="Override camera width.")
    parser.add_argument("--height", type=int, help="Override camera height.")
    parser.add_argument("--fps", type=int, help="Override camera fps.")
    parser.add_argument(
        "--rotate-ccw-90",
        action="store_true",
        help="Rotate incoming camera frames 90 degrees counterclockwise.",
    )
    parser.add_argument(
        "--flip-horizontal",
        action="store_true",
        help="Force horizontal flip on preview/capture.",
    )
    parser.add_argument(
        "--preview-scale",
        type=float,
        help="Scale GUI preview window independently from camera resolution.",
    )
    parser.add_argument(
        "--raw-preview",
        action="store_true",
        help="Show only camera view in GUI, without ROI/track overlays.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is not installed. On Raspberry Pi use: "
            "sudo apt install -y python3-opencv python3-numpy && "
            "python3 -m venv --system-site-packages .venv && "
            "python -m pip install -r requirements.txt"
        ) from exc

    config = load_observer_config(args.config)

    override_width = args.width if args.width is not None else config.camera.width
    override_height = args.height if args.height is not None else config.camera.height
    override_fps = args.fps if args.fps is not None else config.camera.fps
    override_flip = True if args.flip_horizontal else config.camera.flip_horizontal
    override_rotate_ccw_90 = True if args.rotate_ccw_90 else config.camera.rotate_ccw_90
    override_preview_scale = (
        max(0.1, float(args.preview_scale)) if args.preview_scale is not None else config.ui.preview_scale
    )
    override_show_overlay = False if args.raw_preview else config.ui.show_overlay

    if args.source is not None:
        source = int(args.source) if args.source.isdigit() else args.source
        config = ObserverConfig(
            device_name=config.device_name,
            camera=CameraConfig(
                source=source,
                width=override_width,
                height=override_height,
                fps=override_fps,
                flip_horizontal=override_flip,
                rotate_ccw_90=override_rotate_ccw_90,
            ),
            processing=config.processing,
            tracker=config.tracker,
            line_counter=config.line_counter,
            mqtt=config.mqtt,
            ui=UiConfig(
                show_windows=False if args.no_gui else config.ui.show_windows,
                show_masks=False if args.no_gui else config.ui.show_masks,
                show_pending_tracks=False if args.no_gui else config.ui.show_pending_tracks,
                preview_scale=override_preview_scale,
                show_overlay=override_show_overlay,
            ),
        )
    elif (
        args.no_gui
        or args.width is not None
        or args.height is not None
        or args.fps is not None
        or args.rotate_ccw_90
        or args.flip_horizontal
        or args.preview_scale is not None
        or args.raw_preview
    ):
        config = ObserverConfig(
            device_name=config.device_name,
            camera=CameraConfig(
                source=config.camera.source,
                width=override_width,
                height=override_height,
                fps=override_fps,
                flip_horizontal=override_flip,
                rotate_ccw_90=override_rotate_ccw_90,
            ),
            processing=config.processing,
            tracker=config.tracker,
            line_counter=config.line_counter,
            mqtt=config.mqtt,
            ui=UiConfig(
                show_windows=False if args.no_gui else config.ui.show_windows,
                show_masks=False if args.no_gui else config.ui.show_masks,
                show_pending_tracks=False if args.no_gui else config.ui.show_pending_tracks,
                preview_scale=override_preview_scale,
                show_overlay=override_show_overlay,
            ),
        )

    runtime = RuntimeAdjustments(
        roi=config.processing.roi,
        line_x=config.line_counter.x,
        rotate_ccw_90=config.camera.rotate_ccw_90,
    )

    profiles = load_box_profiles(args.boxes)
    detector = ColorBoxDetector(profiles, config.processing)
    tracker = CentroidTracker(config.tracker, config.line_counter)
    clock = TimestampOffsetClock()
    system_clock = SystemClockSetter()
    mqtt_client = ObserverMqttClient(config.mqtt)
    editor: PreviewEditor | None = None

    def handle_time_sync(payload: object, topic: str) -> None:
        try:
            sync_result = clock.sync_from_payload(payload, source=topic)
            system_clock_result = system_clock.apply(sync_result.target_timestamp) if should_apply_system_clock(payload) else None
            print(
                "Clock synchronized via MQTT:"
                f" target={sync_result.target_timestamp}"
                f" offset_sec={sync_result.offset_seconds:.3f}"
            )
            mqtt_client.publish_json(
                "clock_status",
                {
                    "device_name": config.device_name,
                    "timestamp": clock.iso_now(),
                    **clock.status(),
                    "system_clock_requested": bool(system_clock_result and system_clock_result.requested),
                    "system_clock_attempted": bool(system_clock_result and system_clock_result.attempted),
                    "system_clock_applied": bool(system_clock_result and system_clock_result.success),
                    "system_clock_command": system_clock_result.command if system_clock_result is not None else None,
                    "system_clock_message": system_clock_result.message if system_clock_result is not None else None,
                },
                retain=True,
            )
            if editor is not None:
                editor.set_status(
                    f"clock synced ({sync_result.offset_seconds:.1f}s)",
                    duration_sec=4.0,
                )
        except Exception as exc:
            print(f"Clock sync failed for {topic}: {exc}")
            mqtt_client.publish_json(
                "clock_status",
                {
                    "device_name": config.device_name,
                    "timestamp": clock.iso_now(),
                    **clock.status(),
                    "clock_sync_error": str(exc),
                    "system_clock_requested": should_apply_system_clock(payload),
                    "system_clock_attempted": False,
                    "system_clock_applied": False,
                },
                retain=True,
            )

    mqtt_client.register_json_handler("time_sync", handle_time_sync)
    mqtt_client.connect()
    show_masks = bool(config.ui.show_masks)
    mask_focus_profile_id: str | None = None
    mask_profile_order = [profile.profile_id for profile in profiles]

    capture = open_capture(config.camera, cv2=cv2)
    _print_camera_runtime(capture.runtime_info(), config)

    if config.ui.show_windows:
        cv2.namedWindow("Observer", cv2.WINDOW_NORMAL)
        if show_masks:
            cv2.namedWindow("Masks", cv2.WINDOW_NORMAL)
        editor = PreviewEditor(runtime=runtime, line_enabled=config.line_counter.enabled)
        editor.set_preview_scale(config.ui.preview_scale)
        editor.set_status(
            "Mouse: drag ROI/line | t: rotate 90 | s: save | r: reload boxes | m: masks",
            duration_sec=7.0,
        )
        cv2.setMouseCallback("Observer", editor.handle_mouse)

    frame_times: deque[float] = deque(maxlen=20)
    last_publish_at = 0.0
    last_heartbeat_at = 0.0
    frame_index = 0

    mqtt_client.publish_json(
        "status",
        {
            "device_name": config.device_name,
            "state": "starting",
            "timestamp": clock.iso_now(),
            "source": str(config.camera.source),
            **clock.status(),
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
            if runtime.rotate_ccw_90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            if config.camera.flip_horizontal:
                frame = cv2.flip(frame, 1)

            runtime.roi = _fit_roi_to_frame(runtime.roi, frame)
            runtime.line_x = _clamp_line_x(runtime.line_x, frame.shape[1])
            active_config = _build_runtime_config(
                config,
                roi=runtime.roi,
                line_x=runtime.line_x,
                rotate_ccw_90=runtime.rotate_ccw_90,
            )

            if editor is not None:
                editor.set_frame(frame)
                editor.set_preview_scale(active_config.ui.preview_scale)

            roi_frame, roi_offset = _apply_roi(frame, active_config.processing.roi)
            detections, masks = detector.detect(roi_frame)
            detections = _translate_detections(detections, roi_offset)
            mask_debug_lines = _mask_debug_lines(
                masks,
                profile_order=mask_profile_order,
                focus_profile_id=mask_focus_profile_id,
            )

            frame_index += 1
            timestamp_iso = clock.iso_now()
            tracker.line_counter = active_config.line_counter
            tracks, events = tracker.update(detections, frame_index, timestamp_iso)
            frame_times.append(time.perf_counter() - started_at)
            fps = _fps_from_samples(frame_times)
            confirmed_count = sum(1 for track in tracks if track.confirmed)
            pending_count = len(tracks) - confirmed_count

            now = time.monotonic()
            if now - last_publish_at >= active_config.mqtt.publish_interval_sec:
                mqtt_client.publish_json(
                    "tracks",
                    {
                        "device_name": active_config.device_name,
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
                        "device_name": active_config.device_name,
                        "state": "running",
                        "timestamp": timestamp_iso,
                        "frame_index": frame_index,
                        "fps": round(fps, 2),
                        "active_tracks": confirmed_count,
                        "pending_tracks": pending_count,
                        "total_crossings": tracker.total_crossings,
                        "roi": _roi_to_dict(active_config.processing.roi),
                        "rotate_ccw_90": active_config.camera.rotate_ccw_90,
                        "line_x": active_config.line_counter.x,
                        **clock.status(),
                    },
                    retain=True,
                )
                last_publish_at = now

            if now - last_heartbeat_at >= active_config.mqtt.heartbeat_interval_sec:
                mqtt_client.publish_json(
                    "heartbeat",
                    {
                        "device_name": active_config.device_name,
                        "timestamp": timestamp_iso,
                        "frame_index": frame_index,
                        **clock.status(),
                    },
                )
                last_heartbeat_at = now

            for event in events:
                event_payload = dict(event)
                event_payload.setdefault("observed_at", str(event.get("timestamp") or timestamp_iso))
                event_payload["published_at"] = clock.iso_now()
                mqtt_client.publish_json("events", event_payload)

            if active_config.ui.show_windows:
                display_frame = frame.copy()
                if active_config.ui.show_overlay:
                    display_frame = _draw_overlay(
                        display_frame,
                        tracks,
                        active_config,
                        fps,
                        tracker.total_crossings,
                        editor=editor,
                        mask_debug_lines=mask_debug_lines,
                        mask_focus_profile_id=mask_focus_profile_id,
                    )
                cv2.imshow("Observer", _scale_preview(display_frame, active_config.ui.preview_scale))
                if show_masks:
                    mask_preview = _compose_mask_preview(
                        masks,
                        focus_profile_id=mask_focus_profile_id,
                    )
                    if mask_preview is not None:
                        cv2.imshow("Masks", _scale_preview(mask_preview, active_config.ui.preview_scale))

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("m"):
                    show_masks = not show_masks
                    if show_masks:
                        cv2.namedWindow("Masks", cv2.WINDOW_NORMAL)
                    else:
                        try:
                            cv2.destroyWindow("Masks")
                        except Exception:
                            pass
                    if editor is not None:
                        editor.set_status(f"show_masks={'on' if show_masks else 'off'}")
                if key == ord("r"):
                    try:
                        profiles = load_box_profiles(args.boxes)
                        detector = ColorBoxDetector(profiles, active_config.processing)
                        mask_profile_order = [profile.profile_id for profile in profiles]
                        if mask_focus_profile_id not in mask_profile_order:
                            mask_focus_profile_id = None
                        if editor is not None:
                            editor.set_status(
                                f"Reloaded boxes: {', '.join(mask_profile_order)}",
                                duration_sec=4.0,
                            )
                        print(f"Reloaded box profiles from {args.boxes}")
                    except Exception as exc:
                        if editor is not None:
                            editor.set_status(f"Reload failed: {exc}", duration_sec=5.0)
                        print(f"Reload failed: {exc}")
                if key == ord("t"):
                    runtime.rotate_ccw_90 = not runtime.rotate_ccw_90
                    if editor is not None:
                        editor.set_status(
                            f"rotate_ccw_90={'on' if runtime.rotate_ccw_90 else 'off'}",
                        )
                if key == ord("s"):
                    current_config = _build_runtime_config(
                        config,
                        roi=runtime.roi,
                        line_x=runtime.line_x,
                        rotate_ccw_90=runtime.rotate_ccw_90,
                    )
                    save_observer_config(args.config, current_config)
                    config = current_config
                    print(f"Observer config saved to {args.config}")
                    if editor is not None:
                        editor.set_status(f"Saved config: {args.config}", duration_sec=4.0)
                if key == ord("0"):
                    mask_focus_profile_id = None
                    if editor is not None:
                        editor.set_status("Mask focus cleared")
                if ord("1") <= key <= ord("9"):
                    profile_index = key - ord("1")
                    if 0 <= profile_index < len(mask_profile_order):
                        mask_focus_profile_id = mask_profile_order[profile_index]
                        if editor is not None:
                            editor.set_status(f"Mask focus: {mask_focus_profile_id}")
            elif frame_index % 30 == 0:
                print(
                    f"[{timestamp_iso}] frame={frame_index} active={confirmed_count} pending={pending_count} "
                    f"crossings={tracker.total_crossings} fps={fps:.2f}"
                )

    finally:
        final_config = _build_runtime_config(
            config,
            roi=runtime.roi,
            line_x=runtime.line_x,
            rotate_ccw_90=runtime.rotate_ccw_90,
        )
        mqtt_client.publish_json(
            "status",
            {
                "device_name": final_config.device_name,
                "state": "stopped",
                "timestamp": clock.iso_now(),
                "frame_index": frame_index,
                "total_crossings": tracker.total_crossings,
                **clock.status(),
            },
            retain=True,
        )
        capture.release()
        mqtt_client.disconnect()
        cv2.destroyAllWindows()

    return 0


def _build_runtime_config(
    base_config: ObserverConfig,
    *,
    roi: ROI | None,
    line_x: int,
    rotate_ccw_90: bool,
) -> ObserverConfig:
    return ObserverConfig(
        device_name=base_config.device_name,
        camera=CameraConfig(
            source=base_config.camera.source,
            width=base_config.camera.width,
            height=base_config.camera.height,
            fps=base_config.camera.fps,
            flip_horizontal=base_config.camera.flip_horizontal,
            rotate_ccw_90=rotate_ccw_90,
        ),
        processing=ProcessingConfig(
            roi=roi,
            blur_kernel=base_config.processing.blur_kernel,
            morph_kernel=base_config.processing.morph_kernel,
            open_iterations=base_config.processing.open_iterations,
            close_iterations=base_config.processing.close_iterations,
            min_contour_area=base_config.processing.min_contour_area,
            normalize_lighting=base_config.processing.normalize_lighting,
            clahe_clip_limit=base_config.processing.clahe_clip_limit,
            clahe_tile_grid_size=base_config.processing.clahe_tile_grid_size,
            min_saturation=base_config.processing.min_saturation,
            min_value=base_config.processing.min_value,
        ),
        tracker=base_config.tracker,
        line_counter=LineCounterConfig(
            enabled=base_config.line_counter.enabled,
            x=line_x,
            direction=base_config.line_counter.direction,
        ),
        mqtt=base_config.mqtt,
        ui=base_config.ui,
    )


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
    *,
    editor: PreviewEditor | None = None,
    mask_debug_lines: list[str] | None = None,
    mask_focus_profile_id: str | None = None,
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
        cv2.rectangle(
            frame,
            (roi.x + roi.width - 10, roi.y + roi.height - 10),
            (roi.x + roi.width + 10, roi.y + roi.height + 10),
            (255, 255, 0),
            -1,
        )

    if config.line_counter.enabled:
        line_x = config.line_counter.x
        cv2.line(frame, (line_x, 0), (line_x, frame.shape[0]), (0, 255, 255), 2)
        cv2.circle(frame, (line_x, 22), 8, (0, 255, 255), -1)

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
    cv2.putText(
        frame,
        (
            f"ROI={_roi_summary(config.processing.roi)} | line_x={config.line_counter.x} "
            f"| rotate90={'on' if config.camera.rotate_ccw_90 else 'off'}"
        ),
        (10, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2,
    )
    if mask_focus_profile_id is not None:
        cv2.putText(
            frame,
            f"mask_focus={mask_focus_profile_id}",
            (10, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
        )
    if mask_debug_lines:
        for index, line in enumerate(mask_debug_lines, start=1):
            cv2.putText(
                frame,
                line,
                (10, 75 + (index * 22)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (160, 255, 160),
                1,
            )
    cv2.putText(
        frame,
        "Mouse: drag ROI/line | m: masks | r: reload boxes | 1-9: focus mask | 0: clear",
        (10, max(70, frame.shape[0] - 18)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 255, 255),
        1,
    )
    if editor is not None and editor.active_status():
        cv2.putText(
            frame,
            editor.active_status(),
            (10, min(frame.shape[0] - 42, 118)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
        )
    return frame


def _compose_mask_preview(
    masks: dict[str, "np.ndarray"],
    *,
    focus_profile_id: str | None = None,
) -> "np.ndarray" | None:
    import cv2

    if not masks:
        return None

    tiles: list[np.ndarray] = []
    mask_items = (
        [(focus_profile_id, masks[focus_profile_id])]
        if focus_profile_id is not None and focus_profile_id in masks
        else list(masks.items())
    )
    for label, mask in mask_items:
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


def _mask_debug_lines(
    masks: dict[str, "np.ndarray"],
    *,
    profile_order: list[str],
    focus_profile_id: str | None,
) -> list[str]:
    if not masks:
        return []

    if focus_profile_id is not None and focus_profile_id in masks:
        ordered_ids = [focus_profile_id]
    else:
        ordered_ids = [profile_id for profile_id in profile_order if profile_id in masks]

    if not ordered_ids:
        ordered_ids = list(masks.keys())

    first_mask = masks[ordered_ids[0]]
    total_pixels = max(1, int(first_mask.shape[0] * first_mask.shape[1]))
    lines: list[str] = []
    max_lines = 1 if focus_profile_id is not None else 3

    for profile_id in ordered_ids[:max_lines]:
        mask = masks[profile_id]
        active_pixels = int((mask > 0).sum())
        ratio = active_pixels / float(total_pixels)
        lines.append(f"mask[{profile_id}]={active_pixels} ({ratio:.1%})")

    return lines


def _scale_preview(frame: "np.ndarray", scale: float) -> "np.ndarray":
    import cv2

    safe_scale = max(0.1, float(scale or 1.0))
    if abs(safe_scale - 1.0) < 1e-6:
        return frame
    return cv2.resize(frame, None, fx=safe_scale, fy=safe_scale, interpolation=cv2.INTER_AREA)


def _print_camera_runtime(runtime: CaptureRuntimeInfo, config: ObserverConfig) -> None:
    width = runtime.actual_width or 0
    height = runtime.actual_height or 0
    fps = runtime.actual_fps or 0.0
    print(
        "Camera runtime:"
        f" backend={runtime.backend}"
        f" source={runtime.source}"
        f" requested={config.camera.width or '-'}x{config.camera.height or '-'}@{config.camera.fps or '-'}"
        f" actual={width or '-'}x{height or '-'}@{fps:.2f}"
        f" rotate_ccw_90={'on' if config.camera.rotate_ccw_90 else 'off'}"
        f" preview_scale={config.ui.preview_scale:.2f}"
        f" overlay={'on' if config.ui.show_overlay else 'off'}"
    )


def _roi_to_dict(roi: ROI | None) -> dict[str, int] | None:
    if roi is None:
        return None
    return {"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height}


def _fit_roi_to_frame(roi: ROI | None, frame: "np.ndarray") -> ROI | None:
    if roi is None:
        return None
    return _fit_roi_to_bounds(roi, frame_width=int(frame.shape[1]), frame_height=int(frame.shape[0]))


def _fit_roi_to_bounds(roi: ROI, *, frame_width: int, frame_height: int) -> ROI:
    x = _clamp_int(int(roi.x), 0, max(0, frame_width - 1))
    y = _clamp_int(int(roi.y), 0, max(0, frame_height - 1))
    width = _clamp_int(int(roi.width), _MIN_ROI_SIZE, max(_MIN_ROI_SIZE, frame_width - x))
    height = _clamp_int(int(roi.height), _MIN_ROI_SIZE, max(_MIN_ROI_SIZE, frame_height - y))
    return ROI(x=x, y=y, width=width, height=height)


def _clamp_line_x(value: int, frame_width: int) -> int:
    return _clamp_int(int(value), 0, max(0, frame_width - 1))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _roi_summary(roi: ROI | None) -> str:
    if roi is None:
        return "full-frame"
    return f"{roi.x},{roi.y},{roi.width},{roi.height}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
