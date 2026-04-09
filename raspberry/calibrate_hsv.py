from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from observer.capture import open_capture
from observer.config import CameraConfig, ProcessingConfig, load_observer_config
from observer.models import BoxProfile, HSVRange, LABRange
from observer.preprocess import preprocess_frame
from observer.vision import ColorBoxDetector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HSV and LAB calibration helper.")
    parser.add_argument(
        "--source",
        default=None,
        help="Camera index, video path, or stream URI.",
    )
    parser.add_argument(
        "--config",
        default="config/observer.example.json",
        help="Optional observer config JSON path used to align camera and processing defaults.",
    )
    parser.add_argument(
        "--flip-horizontal",
        dest="flip_horizontal",
        action="store_true",
        help="Mirror the incoming frame.",
    )
    parser.add_argument(
        "--no-flip-horizontal",
        dest="flip_horizontal",
        action="store_false",
        help="Disable horizontal mirroring even if the observer config enables it.",
    )
    parser.add_argument(
        "--rotate-ccw-90",
        dest="rotate_ccw_90",
        action="store_true",
        help="Rotate incoming camera frames 90 degrees counterclockwise.",
    )
    parser.add_argument(
        "--no-rotate-ccw-90",
        dest="rotate_ccw_90",
        action="store_false",
        help="Disable 90 degree rotation even if the observer config enables it.",
    )
    parser.add_argument("--width", type=int, help="Override camera width.")
    parser.add_argument("--height", type=int, help="Override camera height.")
    parser.add_argument("--fps", type=int, help="Override camera fps.")
    parser.add_argument("--preview-scale", type=float, help="Scale GUI preview windows.")
    parser.add_argument("--profile-id", default="new_box", help="Profile id for generated JSON.")
    parser.add_argument("--label", default="New Box", help="Label for generated JSON.")
    parser.add_argument("--color-name", default="color", help="Color name for generated JSON.")
    parser.add_argument("--overlay-bgr", default="0,255,0", help="Overlay color as B,G,R.")
    parser.add_argument("--priority", type=int, default=1, help="Priority for generated profile.")
    parser.add_argument("--min-area", type=int, default=1800, help="min_area for generated profile.")
    parser.add_argument("--max-area", type=int, default=60000, help="max_area for generated profile.")
    parser.add_argument("--roi-width", type=int, default=120, help="Center ROI width for auto sampling.")
    parser.add_argument("--roi-height", type=int, default=120, help="Center ROI height for auto sampling.")
    parser.add_argument("--h-margin", type=int, default=6, help="Hue margin for auto HSV sampling.")
    parser.add_argument("--s-margin", type=int, default=25, help="S margin for auto HSV sampling.")
    parser.add_argument("--v-margin", type=int, default=25, help="V margin for auto HSV sampling.")
    parser.add_argument("--l-margin", type=int, default=20, help="L margin for auto LAB sampling.")
    parser.add_argument("--a-margin", type=int, default=12, help="A margin for auto LAB sampling.")
    parser.add_argument("--b-margin", type=int, default=12, help="B margin for auto LAB sampling.")
    parser.add_argument("--min-saturation", type=int, help="Minimum S for ROI filtering.")
    parser.add_argument("--min-value", type=int, help="Minimum V for ROI filtering.")
    parser.add_argument(
        "--normalize-lighting",
        dest="normalize_lighting",
        action="store_true",
        help="Apply gray-world color balancing.",
    )
    parser.add_argument(
        "--no-normalize-lighting",
        dest="normalize_lighting",
        action="store_false",
        help="Disable lighting normalization even if the observer config enables it.",
    )
    parser.add_argument("--clahe-clip-limit", type=float, help="Apply CLAHE on brightness when > 0.")
    parser.add_argument("--clahe-tile-grid", type=int, help="CLAHE tile grid size.")
    parser.add_argument("--sample-radius", type=int, default=10, help="Mouse sampling radius in pixels.")
    parser.add_argument("--boxes-file", default="config/boxes.example.json", help="Box config file to update.")
    parser.set_defaults(
        flip_horizontal=None,
        rotate_ccw_90=None,
        normalize_lighting=None,
    )
    return parser


def nothing(_: int) -> None:
    return None


COLOR_PRESETS: dict[str, dict[str, Any]] = {
    "r": {
        "id": "red_box",
        "label": "Red Box",
        "color_name": "red",
        "overlay_bgr": [0, 0, 255],
        "priority": 3,
        "sku": "BX-RED-01",
    },
    "y": {
        "id": "yellow_box",
        "label": "Yellow Box",
        "color_name": "yellow",
        "overlay_bgr": [0, 255, 255],
        "priority": 1,
        "sku": "BX-YEL-01",
    },
    "b": {
        "id": "blue_box",
        "label": "Blue Box",
        "color_name": "blue",
        "overlay_bgr": [255, 0, 0],
        "priority": 2,
        "sku": "BX-BLU-01",
    },
}


def _parse_bgr(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("--overlay-bgr must look like 0,255,255")
    return [max(0, min(255, int(part))) for part in parts]


def _bounded_range(values: Any, margin: int, maximum: int, np: Any) -> tuple[int, int]:
    lower = int(np.percentile(values, 5)) - margin
    upper = int(np.percentile(values, 95)) + margin
    return (max(0, lower), min(maximum, upper))


def _hue_segments(values: Any, margin: int, np: Any) -> list[tuple[int, int]]:
    hue_values = np.sort(np.asarray(values, dtype=int) % 180)
    if hue_values.size == 0:
        return [(0, 179)]

    extended = np.concatenate([hue_values, [hue_values[0] + 180]])
    gaps = np.diff(extended)
    largest_gap_index = int(np.argmax(gaps))
    start = int(hue_values[(largest_gap_index + 1) % hue_values.size])
    end = int(hue_values[largest_gap_index])

    start = (start - margin) % 180
    end = (end + margin) % 180

    if start <= end:
        return [(start, end)]
    return [(0, end), (start, 179)]


def _extract_center_roi(frame: Any, width: int, height: int) -> tuple[Any, tuple[int, int, int, int]]:
    frame_height, frame_width = frame.shape[:2]
    roi_width = max(20, min(width, frame_width))
    roi_height = max(20, min(height, frame_height))
    left = max(0, (frame_width - roi_width) // 2)
    top = max(0, (frame_height - roi_height) // 2)
    return frame[top : top + roi_height, left : left + roi_width], (left, top, roi_width, roi_height)


def _resolve_boxes_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(__file__).resolve().parent / path).resolve()


def _load_boxes_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"profiles": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_profile(boxes_path: Path, profile: dict[str, Any]) -> dict[str, Any]:
    boxes_path.parent.mkdir(parents=True, exist_ok=True)
    config = _load_boxes_config(boxes_path)
    profiles = list(config.get("profiles", []))
    existing_index = next(
        (index for index, current in enumerate(profiles) if current.get("id") == profile.get("id")),
        None,
    )

    if existing_index is None:
        profiles.append(profile)
    else:
        profiles[existing_index] = profile

    config["profiles"] = profiles
    with boxes_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return profile


def _manual_range(lower: Any, upper: Any) -> dict[str, list[int]]:
    return {"lower": lower.tolist(), "upper": upper.tolist()}


def _save_manual_profile(
    boxes_path: Path,
    color_key: str,
    manual_range: dict[str, list[int]],
    min_area: int,
    max_area: int,
    append: bool,
) -> dict[str, Any]:
    boxes_path.parent.mkdir(parents=True, exist_ok=True)
    config = _load_boxes_config(boxes_path)
    profiles = list(config.get("profiles", []))
    preset = COLOR_PRESETS[color_key]

    existing_index = next(
        (index for index, profile in enumerate(profiles) if profile.get("id") == preset["id"]),
        None,
    )
    existing = profiles[existing_index] if existing_index is not None else {}

    current_ranges = list(existing.get("ranges", [])) if append else []
    current_ranges.append(manual_range)

    profile = {
        "id": preset["id"],
        "label": preset["label"],
        "color_name": preset["color_name"],
        "overlay_bgr": preset["overlay_bgr"],
        "priority": preset["priority"],
        "min_area": int(existing.get("min_area", min_area)),
        "max_area": int(existing.get("max_area", max_area)),
        "aspect_ratio": existing.get("aspect_ratio", [0.5, 2.4]),
        "min_fill_ratio": float(existing.get("min_fill_ratio", 0.45)),
        "min_solidity": float(existing.get("min_solidity", 0.8)),
        "min_size": existing.get("min_size", [24, 24]),
        "metadata": {
            "sku": preset["sku"],
            "notes": "Saved from manual HSV calibration",
        },
        "ranges": current_ranges,
        "lab_ranges": [],
    }

    return _save_profile(boxes_path, profile)


def _build_profile_from_pixels(
    bgr_pixels: Any,
    args: argparse.Namespace,
    cv2: Any,
    np: Any,
    *,
    notes: str,
) -> dict[str, Any]:
    pixel_count = int(getattr(bgr_pixels, "shape", [0])[0] or 0)
    if pixel_count < 20:
        raise ValueError("Not enough sample pixels were collected.")

    hsv_pixels = cv2.cvtColor(bgr_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    lab_pixels = cv2.cvtColor(bgr_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3)
    valid_pixels = (hsv_pixels[:, 1] >= args.min_saturation) & (hsv_pixels[:, 2] >= args.min_value)
    if int(valid_pixels.sum()) < max(20, hsv_pixels.shape[0] // 8):
        valid_pixels = np.ones(hsv_pixels.shape[0], dtype=bool)

    sampled_hsv = hsv_pixels[valid_pixels]
    sampled_lab = lab_pixels[valid_pixels]

    s_low, s_high = _bounded_range(sampled_hsv[:, 1], args.s_margin, 255, np)
    v_low, v_high = _bounded_range(sampled_hsv[:, 2], args.v_margin, 255, np)
    hsv_ranges = [
        {
            "lower": [hue_low, s_low, v_low],
            "upper": [hue_high, s_high, v_high],
        }
        for hue_low, hue_high in _hue_segments(sampled_hsv[:, 0], args.h_margin, np)
    ]

    l_low, l_high = _bounded_range(sampled_lab[:, 0], args.l_margin, 255, np)
    a_low, a_high = _bounded_range(sampled_lab[:, 1], args.a_margin, 255, np)
    b_low, b_high = _bounded_range(sampled_lab[:, 2], args.b_margin, 255, np)

    return {
        "id": args.profile_id,
        "label": args.label,
        "color_name": args.color_name,
        "overlay_bgr": _parse_bgr(args.overlay_bgr),
        "priority": args.priority,
        "min_area": args.min_area,
        "max_area": args.max_area,
        "aspect_ratio": [0.5, 2.4],
        "metadata": {
            "notes": notes,
        },
        "ranges": hsv_ranges,
        "lab_ranges": [
            {
                "lower": [l_low, a_low, b_low],
                "upper": [l_high, a_high, b_high],
            }
        ],
    }


def _build_profile_from_roi(roi: Any, args: argparse.Namespace, cv2: Any, np: Any) -> dict[str, Any]:
    return _build_profile_from_pixels(
        roi.reshape(-1, 3),
        args,
        cv2,
        np,
        notes="Auto-generated from center ROI",
    )


def _build_mask_from_profile(frame: Any, profile: dict[str, Any], cv2: Any, np: Any) -> Any:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)

    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for hsv_range in profile["ranges"]:
        lower = np.array(hsv_range["lower"], dtype=np.uint8)
        upper = np.array(hsv_range["upper"], dtype=np.uint8)
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))

    for lab_range in profile.get("lab_ranges", []):
        lower = np.array(lab_range["lower"], dtype=np.uint8)
        upper = np.array(lab_range["upper"], dtype=np.uint8)
        mask = cv2.bitwise_and(mask, cv2.inRange(lab, lower, upper))

    return mask


def _box_profile_from_dict(profile: dict[str, Any]) -> BoxProfile:
    return BoxProfile(
        profile_id=str(profile["id"]),
        label=str(profile.get("label", profile["id"])),
        color_name=str(profile.get("color_name", profile.get("label", profile["id"]))),
        ranges=tuple(
            HSVRange(
                lower=tuple(int(value) for value in hsv_range["lower"]),
                upper=tuple(int(value) for value in hsv_range["upper"]),
            )
            for hsv_range in profile.get("ranges", [])
        ),
        lab_ranges=tuple(
            LABRange(
                lower=tuple(int(value) for value in lab_range["lower"]),
                upper=tuple(int(value) for value in lab_range["upper"]),
            )
            for lab_range in profile.get("lab_ranges", [])
        ),
        overlay_bgr=tuple(int(value) for value in profile.get("overlay_bgr", [0, 255, 0])),
        min_area=int(profile.get("min_area", 1000)),
        max_area=int(profile["max_area"]) if profile.get("max_area") is not None else None,
        aspect_ratio=tuple(float(value) for value in profile["aspect_ratio"])
        if profile.get("aspect_ratio") is not None
        else None,
        min_fill_ratio=float(profile.get("min_fill_ratio", 0.45)),
        min_solidity=float(profile.get("min_solidity", 0.8)),
        min_size=tuple(int(value) for value in profile.get("min_size", [24, 24])),
        priority=int(profile.get("priority", 0)),
        metadata=dict(profile.get("metadata", {})),
    )


def _preview_mask_from_profile(
    frame: Any,
    profile: dict[str, Any],
    processing: ProcessingConfig,
) -> Any:
    detector = ColorBoxDetector([_box_profile_from_dict(profile)], processing)
    _, masks = detector.detect(frame)
    return masks.get(profile["id"])


def _resolve_effective_settings(args: argparse.Namespace) -> tuple[CameraConfig, ProcessingConfig, float]:
    observer_config = None
    if args.config:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = (Path(__file__).resolve().parent / config_path).resolve()
        if config_path.exists():
            observer_config = load_observer_config(config_path)

    base_camera = observer_config.camera if observer_config is not None else CameraConfig(source=0)
    base_processing = observer_config.processing if observer_config is not None else ProcessingConfig()
    base_preview_scale = observer_config.ui.preview_scale if observer_config is not None else 1.0

    source_value = args.source if args.source is not None else base_camera.source
    source = int(source_value) if isinstance(source_value, str) and source_value.isdigit() else source_value
    camera = CameraConfig(
        source=source,
        width=args.width if args.width is not None else base_camera.width,
        height=args.height if args.height is not None else base_camera.height,
        fps=args.fps if args.fps is not None else base_camera.fps,
        flip_horizontal=(
            args.flip_horizontal if args.flip_horizontal is not None else base_camera.flip_horizontal
        ),
        rotate_ccw_90=(
            args.rotate_ccw_90 if args.rotate_ccw_90 is not None else base_camera.rotate_ccw_90
        ),
    )
    processing = ProcessingConfig(
        roi=base_processing.roi,
        blur_kernel=base_processing.blur_kernel,
        morph_kernel=base_processing.morph_kernel,
        open_iterations=base_processing.open_iterations,
        close_iterations=base_processing.close_iterations,
        min_contour_area=base_processing.min_contour_area,
        normalize_lighting=(
            args.normalize_lighting if args.normalize_lighting is not None else base_processing.normalize_lighting
        ),
        clahe_clip_limit=(
            args.clahe_clip_limit if args.clahe_clip_limit is not None else base_processing.clahe_clip_limit
        ),
        clahe_tile_grid_size=(
            args.clahe_tile_grid if args.clahe_tile_grid is not None else base_processing.clahe_tile_grid_size
        ),
        min_saturation=args.min_saturation if args.min_saturation is not None else base_processing.min_saturation,
        min_value=args.min_value if args.min_value is not None else base_processing.min_value,
    )
    preview_scale = max(
        0.1,
        float(args.preview_scale if args.preview_scale is not None else base_preview_scale),
    )
    return camera, processing, preview_scale


def _extract_patch(frame: Any, x: int, y: int, radius: int) -> Any:
    safe_radius = max(1, int(radius))
    top = max(0, y - safe_radius)
    bottom = min(frame.shape[0], y + safe_radius + 1)
    left = max(0, x - safe_radius)
    right = min(frame.shape[1], x + safe_radius + 1)
    return frame[top:bottom, left:right]


def _rebuild_profile_from_click_samples(samples: list[Any], args: argparse.Namespace, cv2: Any, np: Any) -> dict[str, Any]:
    if not samples:
        raise ValueError("No click samples collected yet.")
    pixels = np.concatenate([sample.reshape(-1, 3) for sample in samples], axis=0)
    return _build_profile_from_pixels(
        pixels,
        args,
        cv2,
        np,
        notes="Auto-generated from click samples",
    )


def main() -> int:
    args = build_parser().parse_args()

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV and numpy are not installed. On Raspberry Pi use: "
            "sudo apt install -y python3-opencv python3-numpy && "
            "python3 -m venv --system-site-packages .venv && "
            "python -m pip install -r requirements.txt"
        ) from exc

    camera_config, processing_config, preview_scale = _resolve_effective_settings(args)
    if args.min_saturation is None:
        args.min_saturation = processing_config.min_saturation
    if args.min_value is None:
        args.min_value = processing_config.min_value
    capture = open_capture(camera_config, cv2=cv2)

    cv2.namedWindow("Settings", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Settings", 420, 260)
    cv2.namedWindow("Camera", cv2.WINDOW_NORMAL)

    cv2.createTrackbar("H_Min", "Settings", 0, 179, nothing)
    cv2.createTrackbar("S_Min", "Settings", 0, 255, nothing)
    cv2.createTrackbar("V_Min", "Settings", 0, 255, nothing)
    cv2.createTrackbar("H_Max", "Settings", 179, 179, nothing)
    cv2.createTrackbar("S_Max", "Settings", 255, 255, nothing)
    cv2.createTrackbar("V_Max", "Settings", 255, 255, nothing)

    boxes_path = _resolve_boxes_path(args.boxes_file)
    print(
        "Preview matches observer camera/preprocess settings. "
        "Press 's' for manual HSV, 'r/y/b' to save manual HSV, 'R/Y/B' to append a range, "
        "'c' for center ROI preview, left click to sample, 'p' to print click profile, "
        "'w' to save auto profile, 'x' to clear click samples, 'q' to quit."
    )
    state: dict[str, Any] = {
        "auto_profile": None,
        "current_frame": None,
        "sample_points": [],
        "sample_patches": [],
    }

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: Any) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        current_frame = state.get("current_frame")
        if current_frame is None:
            return

        scale = preview_scale
        source_x = max(0, min(current_frame.shape[1] - 1, int(round(x / scale))))
        source_y = max(0, min(current_frame.shape[0] - 1, int(round(y / scale))))
        patch = _extract_patch(current_frame, source_x, source_y, args.sample_radius)
        if patch.size == 0:
            return

        state["sample_points"].append((source_x, source_y))
        state["sample_patches"].append(patch.copy())
        try:
            state["auto_profile"] = _rebuild_profile_from_click_samples(state["sample_patches"], args, cv2, np)
        except Exception:
            state["auto_profile"] = None

    cv2.setMouseCallback("Camera", on_mouse)

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Frame read failed, calibration is stopping.")
                break

            if camera_config.rotate_ccw_90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            if camera_config.flip_horizontal:
                frame = cv2.flip(frame, 1)

            processed_frame = preprocess_frame(
                frame,
                normalize_lighting=processing_config.normalize_lighting,
                clahe_clip_limit=processing_config.clahe_clip_limit,
                clahe_tile_grid_size=processing_config.clahe_tile_grid_size,
                cv2=cv2,
                np=np,
            )
            state["current_frame"] = processed_frame.copy()

            roi, roi_box = _extract_center_roi(processed_frame, args.roi_width, args.roi_height)
            lower = np.array(
                [
                    cv2.getTrackbarPos("H_Min", "Settings"),
                    cv2.getTrackbarPos("S_Min", "Settings"),
                    cv2.getTrackbarPos("V_Min", "Settings"),
                ]
            )
            upper = np.array(
                [
                    cv2.getTrackbarPos("H_Max", "Settings"),
                    cv2.getTrackbarPos("S_Max", "Settings"),
                    cv2.getTrackbarPos("V_Max", "Settings"),
                ]
            )

            manual_profile = {
                "id": args.profile_id,
                "label": args.label,
                "color_name": args.color_name,
                "overlay_bgr": _parse_bgr(args.overlay_bgr),
                "priority": args.priority,
                "min_area": args.min_area,
                "max_area": args.max_area,
                "aspect_ratio": [0.5, 2.4],
                "metadata": {"notes": "Preview profile from manual HSV"},
                "ranges": [_manual_range(lower, upper)],
                "lab_ranges": [],
            }
            mask = _preview_mask_from_profile(frame, manual_profile, processing_config)
            filtered = cv2.bitwise_and(frame, frame, mask=mask)
            display_frame = frame.copy()
            left, top, roi_width, roi_height = roi_box
            cv2.rectangle(display_frame, (left, top), (left + roi_width, top + roi_height), (0, 255, 255), 2)
            cv2.putText(
                display_frame,
                "observer-matched preview | s=print r/y/b=save R/Y/B=append c=center click=sample p=print w=save x=clear",
                (left, max(20, top - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 255),
                2,
            )

            for sample_x, sample_y in state["sample_points"]:
                cv2.circle(display_frame, (sample_x, sample_y), 6, (255, 255, 0), 2)
            cv2.putText(
                display_frame,
                f"sample_points={len(state['sample_points'])}",
                (10, max(45, top + roi_height + 25)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2,
            )

            cv2.imshow("Camera", _scale_preview(display_frame, preview_scale, cv2))
            cv2.imshow("Observer Mask", _scale_preview(mask, preview_scale, cv2))
            cv2.imshow("Observer Filtered", _scale_preview(filtered, preview_scale, cv2))
            if state["auto_profile"] is not None:
                auto_mask = _preview_mask_from_profile(frame, state["auto_profile"], processing_config)
                auto_filtered = cv2.bitwise_and(frame, frame, mask=auto_mask)
                cv2.imshow("Auto Mask", _scale_preview(auto_mask, preview_scale, cv2))
                cv2.imshow("Auto Filtered", _scale_preview(auto_filtered, preview_scale, cv2))

            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                print(
                    json.dumps(
                        {"lower": lower.tolist(), "upper": upper.tolist()},
                        ensure_ascii=False,
                    )
                )
            if key in (ord("r"), ord("y"), ord("b"), ord("R"), ord("Y"), ord("B")):
                try:
                    color_key = chr(key).lower()
                    saved_profile = _save_manual_profile(
                        boxes_path=boxes_path,
                        color_key=color_key,
                        manual_range=_manual_range(lower, upper),
                        min_area=args.min_area,
                        max_area=args.max_area,
                        append=chr(key).isupper(),
                    )
                    action = "appended" if chr(key).isupper() else "saved"
                    print(f"{saved_profile['id']} {action} to {boxes_path}")
                    print(json.dumps(saved_profile, indent=2, ensure_ascii=False))
                except Exception as exc:
                    print(f"SAVE ERROR: {exc}")
            if key == ord("c"):
                try:
                    state["auto_profile"] = _build_profile_from_roi(roi, args, cv2, np)
                    first_range = state["auto_profile"]["ranges"][0]
                    cv2.setTrackbarPos("H_Min", "Settings", int(first_range["lower"][0]))
                    cv2.setTrackbarPos("S_Min", "Settings", int(first_range["lower"][1]))
                    cv2.setTrackbarPos("V_Min", "Settings", int(first_range["lower"][2]))
                    cv2.setTrackbarPos("H_Max", "Settings", int(first_range["upper"][0]))
                    cv2.setTrackbarPos("S_Max", "Settings", int(first_range["upper"][1]))
                    cv2.setTrackbarPos("V_Max", "Settings", int(first_range["upper"][2]))
                    print(json.dumps(state["auto_profile"], indent=2, ensure_ascii=False))
                except Exception as exc:
                    print(f"AUTO SAMPLE ERROR: {exc}")
            if key == ord("p"):
                try:
                    state["auto_profile"] = _rebuild_profile_from_click_samples(state["sample_patches"], args, cv2, np)
                    print(json.dumps(state["auto_profile"], indent=2, ensure_ascii=False))
                except Exception as exc:
                    print(f"CLICK SAMPLE ERROR: {exc}")
            if key == ord("w"):
                if state["auto_profile"] is None:
                    print("SAVE ERROR: no auto profile available yet.")
                else:
                    try:
                        saved_profile = _save_profile(boxes_path, state["auto_profile"])
                        print(f"{saved_profile['id']} saved to {boxes_path}")
                        print(json.dumps(saved_profile, indent=2, ensure_ascii=False))
                    except Exception as exc:
                        print(f"SAVE ERROR: {exc}")
            if key == ord("x"):
                state["sample_points"].clear()
                state["sample_patches"].clear()
                state["auto_profile"] = None
            if key == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


def _scale_preview(frame: Any, scale: float, cv2: Any) -> Any:
    safe_scale = max(0.1, float(scale or 1.0))
    if abs(safe_scale - 1.0) < 1e-6:
        return frame
    return cv2.resize(frame, None, fx=safe_scale, fy=safe_scale, interpolation=cv2.INTER_AREA)


if __name__ == "__main__":
    raise SystemExit(main())
