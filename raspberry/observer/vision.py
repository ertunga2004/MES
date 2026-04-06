from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .config import ProcessingConfig
from .models import BoxProfile, Detection

if TYPE_CHECKING:
    import numpy as np


class ColorBoxDetector:
    def __init__(self, profiles: Iterable[BoxProfile], processing: ProcessingConfig) -> None:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV and numpy are required. On Raspberry Pi use: "
                "sudo apt install -y python3-opencv python3-numpy && "
                "python3 -m venv --system-site-packages .venv && "
                "python -m pip install -r requirements.txt"
            ) from exc

        self.cv2 = cv2
        self.np = np
        self.profiles = list(profiles)
        self.processing = processing
        kernel_size = max(1, processing.morph_kernel)
        self.kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)

    def _find_contours(self, mask: "np.ndarray") -> list[object]:
        result = self.cv2.findContours(mask, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE)
        if len(result) == 2:
            contours, _ = result
        else:
            _, contours, _ = result
        return list(contours)

    def detect(self, frame: "np.ndarray") -> tuple[list[Detection], dict[str, "np.ndarray"]]:
        cv2 = self.cv2
        np = self.np
        working_frame = frame
        if self.processing.blur_kernel > 1:
            blur = self.processing.blur_kernel
            working_frame = cv2.GaussianBlur(working_frame, (blur, blur), 0)

        hsv = cv2.cvtColor(working_frame, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(working_frame, cv2.COLOR_BGR2LAB)
        detections: list[Detection] = []
        masks: dict[str, np.ndarray] = {}

        for profile in self.profiles:
            mask = self._build_mask(hsv, profile.ranges)
            if profile.lab_ranges:
                mask = cv2.bitwise_and(mask, self._build_mask(lab, profile.lab_ranges))

            if self.processing.open_iterations > 0:
                mask = cv2.morphologyEx(
                    mask,
                    cv2.MORPH_OPEN,
                    self.kernel,
                    iterations=self.processing.open_iterations,
                )
            if self.processing.close_iterations > 0:
                mask = cv2.morphologyEx(
                    mask,
                    cv2.MORPH_CLOSE,
                    self.kernel,
                    iterations=self.processing.close_iterations,
                )

            masks[profile.profile_id] = mask
            contours = self._find_contours(mask)

            for contour in contours:
                area = float(cv2.contourArea(contour))
                min_area = float(max(self.processing.min_contour_area, profile.min_area))
                if area < min_area:
                    continue
                if profile.max_area is not None and area > float(profile.max_area):
                    continue

                x, y, w, h = cv2.boundingRect(contour)
                if w <= 0 or h <= 0:
                    continue
                if w < profile.min_size[0] or h < profile.min_size[1]:
                    continue

                if profile.aspect_ratio is not None:
                    aspect = w / float(h)
                    min_ratio, max_ratio = profile.aspect_ratio
                    if aspect < min_ratio or aspect > max_ratio:
                        continue

                moments = cv2.moments(contour)
                if moments["m00"] == 0:
                    continue

                cx = int(moments["m10"] / moments["m00"])
                cy = int(moments["m01"] / moments["m00"])
                bbox_area = max(1.0, float(w * h))
                fill_ratio = min(1.0, area / bbox_area)
                if fill_ratio < profile.min_fill_ratio:
                    continue

                hull = cv2.convexHull(contour)
                hull_area = float(cv2.contourArea(hull))
                solidity = area / max(1.0, hull_area)
                if solidity < profile.min_solidity:
                    continue

                score = (fill_ratio * 0.55) + (solidity * 0.35) + (profile.priority * 0.1)

                detections.append(
                    Detection(
                        profile_id=profile.profile_id,
                        label=profile.label,
                        color_name=profile.color_name,
                        bbox=(x, y, w, h),
                        centroid=(cx, cy),
                        area=area,
                        confidence=max(0.1, min(1.0, (fill_ratio * 0.6) + (solidity * 0.4))),
                        overlay_bgr=profile.overlay_bgr,
                        priority=profile.priority,
                        score=score,
                        metadata=profile.metadata,
                    )
                )

        detections = self._suppress_overlaps(detections)
        detections.sort(key=lambda item: (item.priority, item.score, item.area), reverse=True)
        return detections, masks

    def _build_mask(self, image: "np.ndarray", ranges: Iterable[object]) -> "np.ndarray":
        np = self.np
        cv2 = self.cv2
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        for color_range in ranges:
            lower = np.array(color_range.lower, dtype=np.uint8)
            upper = np.array(color_range.upper, dtype=np.uint8)
            mask = cv2.bitwise_or(mask, cv2.inRange(image, lower, upper))
        return mask

    def _suppress_overlaps(self, detections: list[Detection]) -> list[Detection]:
        kept: list[Detection] = []

        for detection in sorted(
            detections,
            key=lambda item: (item.priority, item.score, item.area),
            reverse=True,
        ):
            if any(self._overlap_ratio(detection.bbox, current.bbox) >= 0.4 for current in kept):
                continue
            kept.append(detection)

        return kept

    def _overlap_ratio(
        self,
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> float:
        first_x, first_y, first_w, first_h = first
        second_x, second_y, second_w, second_h = second

        left = max(first_x, second_x)
        top = max(first_y, second_y)
        right = min(first_x + first_w, second_x + second_w)
        bottom = min(first_y + first_h, second_y + second_h)

        if right <= left or bottom <= top:
            return 0.0

        intersection = float((right - left) * (bottom - top))
        first_area = float(max(1, first_w * first_h))
        second_area = float(max(1, second_w * second_h))
        return intersection / min(first_area, second_area)
