from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HSVRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]

    def __post_init__(self) -> None:
        if len(self.lower) != 3 or len(self.upper) != 3:
            raise ValueError("HSV ranges must have exactly 3 items.")


@dataclass(frozen=True)
class LABRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]

    def __post_init__(self) -> None:
        if len(self.lower) != 3 or len(self.upper) != 3:
            raise ValueError("LAB ranges must have exactly 3 items.")


@dataclass(frozen=True)
class BoxProfile:
    profile_id: str
    label: str
    color_name: str
    ranges: tuple[HSVRange, ...]
    overlay_bgr: tuple[int, int, int]
    min_area: int
    max_area: int | None = None
    aspect_ratio: tuple[float, float] | None = None
    min_fill_ratio: float = 0.45
    min_solidity: float = 0.8
    min_size: tuple[int, int] = (24, 24)
    priority: int = 0
    lab_ranges: tuple[LABRange, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Detection:
    profile_id: str
    label: str
    color_name: str
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    area: float
    confidence: float
    overlay_bgr: tuple[int, int, int]
    priority: int = 0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        x, y, w, h = self.bbox
        cx, cy = self.centroid
        return {
            "profile_id": self.profile_id,
            "label": self.label,
            "color_name": self.color_name,
            "bbox": {"x": x, "y": y, "w": w, "h": h},
            "centroid": {"x": cx, "y": cy},
            "area": round(self.area, 2),
            "confidence": round(self.confidence, 3),
            "priority": self.priority,
            "score": round(self.score, 3),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class TrackSnapshot:
    track_id: int
    profile_id: str
    label: str
    color_name: str
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    area: float
    confidence: float
    overlay_bgr: tuple[int, int, int]
    age: int
    hits: int
    confirmed: bool
    missed_frames: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        x, y, w, h = self.bbox
        cx, cy = self.centroid
        return {
            "track_id": self.track_id,
            "profile_id": self.profile_id,
            "label": self.label,
            "color_name": self.color_name,
            "bbox": {"x": x, "y": y, "w": w, "h": h},
            "centroid": {"x": cx, "y": cy},
            "area": round(self.area, 2),
            "confidence": round(self.confidence, 3),
            "age": self.age,
            "hits": self.hits,
            "confirmed": self.confirmed,
            "missed_frames": self.missed_frames,
            "metadata": self.metadata,
        }
