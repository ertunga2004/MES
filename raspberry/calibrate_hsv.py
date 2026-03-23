from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HSV and LAB calibration helper.")
    parser.add_argument(
        "--source",
        default="0",
        help="Camera index, video path, or stream URI.",
    )
    parser.add_argument(
        "--flip-horizontal",
        action="store_true",
        help="Mirror the incoming frame.",
    )
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
    parser.add_argument("--min-saturation", type=int, default=50, help="Minimum S for ROI filtering.")
    parser.add_argument("--min-value", type=int, default=50, help="Minimum V for ROI filtering.")
    parser.add_argument("--boxes-file", default="config/boxes.example.json", help="Box config file to update.")
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

    if existing_index is None:
        profiles.append(profile)
    else:
        profiles[existing_index] = profile

    config["profiles"] = profiles
    with boxes_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return profile


def _build_profile_from_roi(roi: Any, args: argparse.Namespace, cv2: Any, np: Any) -> dict[str, Any]:
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lab_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)

    hsv_pixels = hsv_roi.reshape(-1, 3)
    lab_pixels = lab_roi.reshape(-1, 3)
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
            "notes": "Auto-generated from center ROI",
        },
        "ranges": hsv_ranges,
        "lab_ranges": [
            {
                "lower": [l_low, a_low, b_low],
                "upper": [l_high, a_high, b_high],
            }
        ],
    }


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


def main() -> int:
    args = build_parser().parse_args()

    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "opencv-python and numpy are not installed. Run: pip install -r requirements.txt"
        ) from exc

    source = int(args.source) if args.source.isdigit() else args.source
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"Video source could not be opened: {args.source}")

    cv2.namedWindow("Settings", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Settings", 420, 260)

    cv2.createTrackbar("H_Min", "Settings", 0, 179, nothing)
    cv2.createTrackbar("S_Min", "Settings", 0, 255, nothing)
    cv2.createTrackbar("V_Min", "Settings", 0, 255, nothing)
    cv2.createTrackbar("H_Max", "Settings", 179, 179, nothing)
    cv2.createTrackbar("S_Max", "Settings", 255, 255, nothing)
    cv2.createTrackbar("V_Max", "Settings", 255, 255, nothing)

    boxes_path = _resolve_boxes_path(args.boxes_file)
    print("Press 's' for manual HSV, 'r/y/b' to save manual HSV, 'R/Y/B' to append a range, 'c' for auto preview, 'q' to quit.")
    auto_profile: dict[str, Any] | None = None

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Frame read failed, calibration is stopping.")
                break

            if args.flip_horizontal:
                frame = cv2.flip(frame, 1)

            roi, roi_box = _extract_center_roi(frame, args.roi_width, args.roi_height)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
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

            mask = cv2.inRange(hsv, lower, upper)
            filtered = cv2.bitwise_and(frame, frame, mask=mask)
            display_frame = frame.copy()
            left, top, roi_width, roi_height = roi_box
            cv2.rectangle(display_frame, (left, top), (left + roi_width, top + roi_height), (0, 255, 255), 2)
            cv2.putText(
                display_frame,
                "s=print  r/y/b=save  R/Y/B=append  c=auto-preview",
                (left, max(20, top - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                2,
            )

            cv2.imshow("Camera", display_frame)
            cv2.imshow("Manual Mask", mask)
            cv2.imshow("Manual Filtered", filtered)
            if auto_profile is not None:
                auto_mask = _build_mask_from_profile(frame, auto_profile, cv2, np)
                auto_filtered = cv2.bitwise_and(frame, frame, mask=auto_mask)
                cv2.imshow("Auto Mask", auto_mask)
                cv2.imshow("Auto Filtered", auto_filtered)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                print(
                    json.dumps(
                        {"lower": lower.tolist(), "upper": upper.tolist()},
                        ensure_ascii=False,
                    )
                )
            if key in (ord("r"), ord("y"), ord("b"), ord("R"), ord("Y"), ord("B")):
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
            if key == ord("c"):
                auto_profile = _build_profile_from_roi(roi, args, cv2, np)
                first_range = auto_profile["ranges"][0]
                cv2.setTrackbarPos("H_Min", "Settings", int(first_range["lower"][0]))
                cv2.setTrackbarPos("S_Min", "Settings", int(first_range["lower"][1]))
                cv2.setTrackbarPos("V_Min", "Settings", int(first_range["lower"][2]))
                cv2.setTrackbarPos("H_Max", "Settings", int(first_range["upper"][0]))
                cv2.setTrackbarPos("S_Max", "Settings", int(first_range["upper"][1]))
                cv2.setTrackbarPos("V_Max", "Settings", int(first_range["upper"][2]))
                print(json.dumps(auto_profile, indent=2, ensure_ascii=False))
            if key == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
