from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .models import BoxProfile, HSVRange, LABRange


@dataclass(frozen=True)
class ROI:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class CameraConfig:
    source: int | str
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    flip_horizontal: bool = False
    rotate_ccw_90: bool = False


@dataclass(frozen=True)
class ProcessingConfig:
    roi: ROI | None = None
    blur_kernel: int = 5
    morph_kernel: int = 5
    open_iterations: int = 1
    close_iterations: int = 2
    min_contour_area: int = 1000
    normalize_lighting: bool = False
    clahe_clip_limit: float = 0.0
    clahe_tile_grid_size: int = 8
    min_saturation: int = 0
    min_value: int = 0


@dataclass(frozen=True)
class TrackerConfig:
    max_distance: int = 90
    max_missed_frames: int = 10
    min_confirmed_frames: int = 2
    max_unconfirmed_missed_frames: int = 2
    expected_direction: str = "any"
    direction_slack: int = 25
    min_area_ratio: float = 0.45
    max_area_ratio: float = 2.2


@dataclass(frozen=True)
class LineCounterConfig:
    enabled: bool = False
    x: int = 0
    direction: str = "left_to_right"


@dataclass(frozen=True)
class MqttConfig:
    enabled: bool = False
    host: str = "broker.emqx.io"
    port: int = 1883
    client_id: str = "mes-observer"
    topic_root: str = "sau/iot/mega/konveyor/vision"
    keepalive: int = 60
    heartbeat_interval_sec: float = 10.0
    publish_interval_sec: float = 0.5
    qos: int = 0


@dataclass(frozen=True)
class UiConfig:
    show_windows: bool = True
    show_masks: bool = False
    show_pending_tracks: bool = False
    preview_scale: float = 1.0
    show_overlay: bool = True


@dataclass(frozen=True)
class ObserverConfig:
    device_name: str
    camera: CameraConfig
    processing: ProcessingConfig
    tracker: TrackerConfig
    line_counter: LineCounterConfig
    mqtt: MqttConfig
    ui: UiConfig


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _as_triplet(values: Any, field_name: str) -> tuple[int, int, int]:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError(f"{field_name} must be a list of 3 integers.")
    return tuple(int(item) for item in values)


def _as_ratio(values: Any) -> tuple[float, float] | None:
    if values is None:
        return None
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("aspect_ratio must be a list with [min, max].")
    return (float(values[0]), float(values[1]))


def _as_size(values: Any) -> tuple[int, int]:
    if values is None:
        return (24, 24)
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("min_size must be a list with [width, height].")
    return (int(values[0]), int(values[1]))


def _normalize_kernel(value: Any, default: int) -> int:
    kernel = int(value if value is not None else default)
    if kernel < 1:
        return 1
    if kernel % 2 == 0:
        return kernel + 1
    return kernel


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except Exception:
        return default
    return max(1, parsed)


def _parse_source(raw_source: Any, base_dir: Path) -> int | str:
    if isinstance(raw_source, int):
        return raw_source

    source = str(raw_source).strip()
    if source.isdigit():
        return int(source)
    if source.lower() in {"picamera2", "picam", "rpi-camera", "libcamera"}:
        return source
    if "://" in source:
        return source

    source_path = Path(source)
    if source_path.is_absolute():
        return str(source_path)
    return str((base_dir / source_path).resolve())


def load_box_profiles(path: str | Path) -> list[BoxProfile]:
    config_path = Path(path).resolve()
    data = _load_json(config_path)
    profiles: list[BoxProfile] = []

    for index, item in enumerate(data.get("profiles", []), start=1):
        ranges = tuple(
            HSVRange(
                lower=_as_triplet(range_item["lower"], f"profiles[{index}].ranges.lower"),
                upper=_as_triplet(range_item["upper"], f"profiles[{index}].ranges.upper"),
            )
            for range_item in item["ranges"]
        )
        lab_ranges = tuple(
            LABRange(
                lower=_as_triplet(range_item["lower"], f"profiles[{index}].lab_ranges.lower"),
                upper=_as_triplet(range_item["upper"], f"profiles[{index}].lab_ranges.upper"),
            )
            for range_item in item.get("lab_ranges", [])
        )
        if not ranges:
            raise ValueError(f"profiles[{index}] must define at least one HSV range.")

        profiles.append(
            BoxProfile(
                profile_id=str(item["id"]),
                label=str(item.get("label", item["id"])),
                color_name=str(item.get("color_name", item.get("label", item["id"]))),
                ranges=ranges,
                lab_ranges=lab_ranges,
                overlay_bgr=_as_triplet(item.get("overlay_bgr", [0, 255, 0]), f"profiles[{index}].overlay_bgr"),
                min_area=int(item.get("min_area", 1000)),
                max_area=int(item["max_area"]) if item.get("max_area") is not None else None,
                aspect_ratio=_as_ratio(item.get("aspect_ratio")),
                min_fill_ratio=float(item.get("min_fill_ratio", 0.45)),
                min_solidity=float(item.get("min_solidity", 0.8)),
                min_size=_as_size(item.get("min_size")),
                priority=int(item.get("priority", 0)),
                metadata=dict(item.get("metadata", {})),
            )
        )

    if not profiles:
        raise ValueError("No box profiles were found in the config file.")

    return profiles


def load_observer_config(path: str | Path) -> ObserverConfig:
    config_path = Path(path).resolve()
    data = _load_json(config_path)
    base_dir = config_path.parent

    camera_data = dict(data.get("camera", {}))
    processing_data = dict(data.get("processing", {}))
    tracker_data = dict(data.get("tracker", {}))
    line_data = dict(data.get("line_counter", {}))
    mqtt_data = dict(data.get("mqtt", {}))
    ui_data = dict(data.get("ui", {}))

    roi_data = processing_data.get("roi")
    roi = (
        ROI(
            x=int(roi_data["x"]),
            y=int(roi_data["y"]),
            width=int(roi_data["width"]),
            height=int(roi_data["height"]),
        )
        if roi_data
        else None
    )

    return ObserverConfig(
        device_name=str(data.get("device_name", "observer-dev")),
        camera=CameraConfig(
            source=_parse_source(camera_data.get("source", 0), base_dir),
            width=int(camera_data["width"]) if camera_data.get("width") is not None else None,
            height=int(camera_data["height"]) if camera_data.get("height") is not None else None,
            fps=int(camera_data["fps"]) if camera_data.get("fps") is not None else None,
            flip_horizontal=bool(camera_data.get("flip_horizontal", False)),
            rotate_ccw_90=bool(camera_data.get("rotate_ccw_90", False)),
        ),
        processing=ProcessingConfig(
            roi=roi,
            blur_kernel=_normalize_kernel(processing_data.get("blur_kernel"), 5),
            morph_kernel=_normalize_kernel(processing_data.get("morph_kernel"), 5),
            open_iterations=int(processing_data.get("open_iterations", 1)),
            close_iterations=int(processing_data.get("close_iterations", 2)),
            min_contour_area=int(processing_data.get("min_contour_area", 1000)),
            normalize_lighting=bool(processing_data.get("normalize_lighting", False)),
            clahe_clip_limit=max(0.0, float(processing_data.get("clahe_clip_limit", 0.0))),
            clahe_tile_grid_size=_positive_int(processing_data.get("clahe_tile_grid_size", 8), 8),
            min_saturation=max(0, int(processing_data.get("min_saturation", 0))),
            min_value=max(0, int(processing_data.get("min_value", 0))),
        ),
        tracker=TrackerConfig(
            max_distance=int(tracker_data.get("max_distance", 90)),
            max_missed_frames=int(tracker_data.get("max_missed_frames", 10)),
            min_confirmed_frames=int(tracker_data.get("min_confirmed_frames", 2)),
            max_unconfirmed_missed_frames=int(tracker_data.get("max_unconfirmed_missed_frames", 2)),
            expected_direction=str(tracker_data.get("expected_direction", "any")),
            direction_slack=int(tracker_data.get("direction_slack", 25)),
            min_area_ratio=float(tracker_data.get("min_area_ratio", 0.45)),
            max_area_ratio=float(tracker_data.get("max_area_ratio", 2.2)),
        ),
        line_counter=LineCounterConfig(
            enabled=bool(line_data.get("enabled", False)),
            x=int(line_data.get("x", 0)),
            direction=str(line_data.get("direction", "left_to_right")),
        ),
        mqtt=MqttConfig(
            enabled=bool(mqtt_data.get("enabled", False)),
            host=str(mqtt_data.get("host", "broker.emqx.io")),
            port=int(mqtt_data.get("port", 1883)),
            client_id=str(mqtt_data.get("client_id", "mes-observer")),
            topic_root=str(mqtt_data.get("topic_root", "sau/iot/mega/konveyor/vision")),
            keepalive=int(mqtt_data.get("keepalive", 60)),
            heartbeat_interval_sec=float(mqtt_data.get("heartbeat_interval_sec", 10.0)),
            publish_interval_sec=float(mqtt_data.get("publish_interval_sec", 0.5)),
            qos=int(mqtt_data.get("qos", 0)),
        ),
        ui=UiConfig(
            show_windows=bool(ui_data.get("show_windows", True)),
            show_masks=bool(ui_data.get("show_masks", False)),
            show_pending_tracks=bool(ui_data.get("show_pending_tracks", False)),
            preview_scale=max(0.1, float(ui_data.get("preview_scale", 1.0))),
            show_overlay=bool(ui_data.get("show_overlay", True)),
        ),
    )


def save_observer_config(path: str | Path, config: ObserverConfig) -> None:
    config_path = Path(path).resolve()
    existing = _load_json(config_path) if config_path.exists() else {}

    camera_data = dict(existing.get("camera", {}))
    processing_data = dict(existing.get("processing", {}))
    tracker_data = dict(existing.get("tracker", {}))
    line_data = dict(existing.get("line_counter", {}))
    mqtt_data = dict(existing.get("mqtt", {}))
    ui_data = dict(existing.get("ui", {}))

    camera_data.update(
        {
            "source": config.camera.source,
            "width": config.camera.width,
            "height": config.camera.height,
            "fps": config.camera.fps,
            "flip_horizontal": config.camera.flip_horizontal,
            "rotate_ccw_90": config.camera.rotate_ccw_90,
        }
    )

    processing_data.update(
        {
            "blur_kernel": config.processing.blur_kernel,
            "morph_kernel": config.processing.morph_kernel,
            "open_iterations": config.processing.open_iterations,
            "close_iterations": config.processing.close_iterations,
            "min_contour_area": config.processing.min_contour_area,
            "normalize_lighting": config.processing.normalize_lighting,
            "clahe_clip_limit": config.processing.clahe_clip_limit,
            "clahe_tile_grid_size": config.processing.clahe_tile_grid_size,
            "min_saturation": config.processing.min_saturation,
            "min_value": config.processing.min_value,
        }
    )
    if config.processing.roi is None:
        processing_data.pop("roi", None)
    else:
        processing_data["roi"] = {
            "x": config.processing.roi.x,
            "y": config.processing.roi.y,
            "width": config.processing.roi.width,
            "height": config.processing.roi.height,
        }

    tracker_data.update(
        {
            "max_distance": config.tracker.max_distance,
            "max_missed_frames": config.tracker.max_missed_frames,
            "min_confirmed_frames": config.tracker.min_confirmed_frames,
            "max_unconfirmed_missed_frames": config.tracker.max_unconfirmed_missed_frames,
            "expected_direction": config.tracker.expected_direction,
            "direction_slack": config.tracker.direction_slack,
            "min_area_ratio": config.tracker.min_area_ratio,
            "max_area_ratio": config.tracker.max_area_ratio,
        }
    )

    line_data.update(
        {
            "enabled": config.line_counter.enabled,
            "x": config.line_counter.x,
            "direction": config.line_counter.direction,
        }
    )

    mqtt_data.update(
        {
            "enabled": config.mqtt.enabled,
            "host": config.mqtt.host,
            "port": config.mqtt.port,
            "client_id": config.mqtt.client_id,
            "topic_root": config.mqtt.topic_root,
            "keepalive": config.mqtt.keepalive,
            "heartbeat_interval_sec": config.mqtt.heartbeat_interval_sec,
            "publish_interval_sec": config.mqtt.publish_interval_sec,
            "qos": config.mqtt.qos,
        }
    )

    ui_data.update(
        {
            "show_windows": config.ui.show_windows,
            "show_masks": config.ui.show_masks,
            "show_pending_tracks": config.ui.show_pending_tracks,
            "preview_scale": config.ui.preview_scale,
            "show_overlay": config.ui.show_overlay,
        }
    )

    _write_json(
        config_path,
        {
            **existing,
            "device_name": config.device_name,
            "camera": camera_data,
            "processing": processing_data,
            "tracker": tracker_data,
            "line_counter": line_data,
            "mqtt": mqtt_data,
            "ui": ui_data,
        },
    )
