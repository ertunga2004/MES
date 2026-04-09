from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def preprocess_frame(
    frame: "np.ndarray",
    *,
    normalize_lighting: bool,
    clahe_clip_limit: float,
    clahe_tile_grid_size: int,
    cv2: object,
    np: object,
) -> "np.ndarray":
    processed = frame

    if normalize_lighting:
        processed = _gray_world_balance(processed, np)

    if clahe_clip_limit > 0:
        processed = _apply_clahe_bgr(
            processed,
            clip_limit=clahe_clip_limit,
            tile_grid_size=clahe_tile_grid_size,
            cv2=cv2,
        )

    return processed


def build_color_gate_mask(
    hsv: "np.ndarray",
    *,
    min_saturation: int,
    min_value: int,
    cv2: object,
    np: object,
) -> "np.ndarray":
    if min_saturation <= 0 and min_value <= 0:
        return np.full(hsv.shape[:2], 255, dtype=np.uint8)

    lower = np.array([0, max(0, int(min_saturation)), max(0, int(min_value))], dtype=np.uint8)
    upper = np.array([179, 255, 255], dtype=np.uint8)
    return cv2.inRange(hsv, lower, upper)


def _gray_world_balance(frame: "np.ndarray", np: object) -> "np.ndarray":
    float_frame = frame.astype(np.float32)
    channel_means = float_frame.reshape(-1, 3).mean(axis=0)
    gray_mean = float(channel_means.mean())
    safe_means = np.maximum(channel_means, 1.0)
    scales = gray_mean / safe_means
    balanced = float_frame * scales.reshape(1, 1, 3)
    return np.clip(balanced, 0, 255).astype(np.uint8)


def _apply_clahe_bgr(
    frame: "np.ndarray",
    *,
    clip_limit: float,
    tile_grid_size: int,
    cv2: object,
) -> "np.ndarray":
    safe_grid = max(1, int(tile_grid_size))
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=max(0.1, float(clip_limit)), tileGridSize=(safe_grid, safe_grid))
    enhanced = clahe.apply(lightness)
    merged = cv2.merge((enhanced, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
