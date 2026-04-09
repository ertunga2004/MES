from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .config import LineCounterConfig, TrackerConfig
from .models import Detection, TrackSnapshot


@dataclass
class TrackState:
    track_id: int
    profile_id: str
    label: str
    color_name: str
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    area: float
    confidence: float
    overlay_bgr: tuple[int, int, int]
    metadata: dict[str, object]
    previous_bbox: tuple[int, int, int, int] | None = None
    previous_centroid: tuple[int, int] | None = None
    velocity: tuple[float, float] = (0.0, 0.0)
    age: int = 1
    hits: int = 1
    streak_hits: int = 1
    confirmed: bool = False
    missed_frames: int = 0
    counted: bool = False

    def update(self, detection: Detection) -> None:
        delta_x = detection.centroid[0] - self.centroid[0]
        delta_y = detection.centroid[1] - self.centroid[1]
        self.previous_bbox = self.bbox
        self.previous_centroid = self.centroid
        self.bbox = detection.bbox
        self.centroid = detection.centroid
        self.area = detection.area
        self.confidence = detection.confidence
        self.velocity = (
            (self.velocity[0] * 0.5) + (delta_x * 0.5),
            (self.velocity[1] * 0.5) + (delta_y * 0.5),
        )
        self.missed_frames = 0
        self.hits += 1
        self.streak_hits += 1
        self.age += 1

    def predicted_centroid(self) -> tuple[float, float]:
        horizon = min(self.missed_frames + 1, 3)
        return (
            self.centroid[0] + (self.velocity[0] * horizon),
            self.centroid[1] + (self.velocity[1] * horizon),
        )

    def to_snapshot(self) -> TrackSnapshot:
        return TrackSnapshot(
            track_id=self.track_id,
            profile_id=self.profile_id,
            label=self.label,
            color_name=self.color_name,
            bbox=self.bbox,
            centroid=self.centroid,
            area=self.area,
            confidence=self.confidence,
            overlay_bgr=self.overlay_bgr,
            age=self.age,
            hits=self.hits,
            confirmed=self.confirmed,
            missed_frames=self.missed_frames,
            metadata=self.metadata,
        )


class CentroidTracker:
    def __init__(self, config: TrackerConfig, line_counter: LineCounterConfig) -> None:
        self.config = config
        self.line_counter = line_counter
        self.next_track_id = 1
        self.total_crossings = 0
        self._tracks: dict[int, TrackState] = {}

    def update(
        self,
        detections: Iterable[Detection],
        frame_index: int,
        timestamp_iso: str,
    ) -> tuple[list[TrackSnapshot], list[dict[str, object]]]:
        detection_list = list(detections)
        events: list[dict[str, object]] = []
        matches = self._match_detections(detection_list)
        matched_track_ids = {track_id for track_id, _ in matches}
        matched_detection_indexes = {index for _, index in matches}

        for track_id, detection_index in matches:
            track = self._tracks[track_id]
            track.update(detection_list[detection_index])
            if not track.confirmed and track.streak_hits >= self.config.min_confirmed_frames:
                track.confirmed = True
                events.append(self._build_track_event("box_confirmed", track, frame_index, timestamp_iso))

        for track_id in list(self._tracks):
            if track_id in matched_track_ids:
                continue
            track = self._tracks[track_id]
            track.missed_frames += 1
            track.streak_hits = 0
            max_missed_frames = (
                self.config.max_missed_frames
                if track.confirmed
                else self.config.max_unconfirmed_missed_frames
            )
            if track.missed_frames > max_missed_frames:
                if track.confirmed:
                    events.append(self._build_track_event("box_lost", track, frame_index, timestamp_iso))
                del self._tracks[track_id]

        for detection_index, detection in enumerate(detection_list):
            if detection_index in matched_detection_indexes:
                continue
            track = TrackState(
                track_id=self.next_track_id,
                profile_id=detection.profile_id,
                label=detection.label,
                color_name=detection.color_name,
                bbox=detection.bbox,
                centroid=detection.centroid,
                area=detection.area,
                confidence=detection.confidence,
                overlay_bgr=detection.overlay_bgr,
                metadata=detection.metadata,
            )
            if self.config.min_confirmed_frames <= 1:
                track.confirmed = True
                events.append(self._build_track_event("box_confirmed", track, frame_index, timestamp_iso))
            self._tracks[self.next_track_id] = track
            self.next_track_id += 1

        snapshots: list[TrackSnapshot] = []

        for track in self._tracks.values():
            if (
                self.line_counter.enabled
                and track.confirmed
                and not track.counted
                and track.previous_bbox is not None
            ):
                if self._has_crossed_line(track.previous_bbox, track.bbox):
                    track.counted = True
                    self.total_crossings += 1
                    confidence, confidence_components = self._crossing_confidence(track)
                    leading_edge_x = self._leading_edge_x(track.bbox, self.line_counter.direction)
                    events.append(
                        {
                            "event": "line_crossed",
                            "frame_index": frame_index,
                            "timestamp": timestamp_iso,
                            "track_id": track.track_id,
                            "profile_id": track.profile_id,
                            "label": track.label,
                            "color_name": track.color_name,
                            "centroid": {"x": track.centroid[0], "y": track.centroid[1]},
                            "bbox": {
                                "x": track.bbox[0],
                                "y": track.bbox[1],
                                "w": track.bbox[2],
                                "h": track.bbox[3],
                            },
                            "leading_edge_x": leading_edge_x,
                            "line_x": self.line_counter.x,
                            "direction": self.line_counter.direction,
                            "total_crossings": self.total_crossings,
                            "confidence": round(confidence, 3),
                            "confidence_components": confidence_components,
                            "metadata": track.metadata,
                        }
                    )
            snapshots.append(track.to_snapshot())

        snapshots.sort(key=lambda item: item.track_id)
        return snapshots, events

    def _match_detections(self, detections: list[Detection]) -> list[tuple[int, int]]:
        candidates: list[tuple[float, int, int]] = []

        for track_id, track in self._tracks.items():
            for detection_index, detection in enumerate(detections):
                if detection.profile_id != track.profile_id:
                    continue
                if not self._direction_is_valid(track, detection):
                    continue
                if track.confirmed and not self._area_is_valid(track, detection):
                    continue
                max_distance = self.config.max_distance * (1.0 + min(track.missed_frames, 3) * 0.25)
                predicted_centroid = track.predicted_centroid()
                distance = self._centroid_distance(predicted_centroid, detection.centroid)
                if distance > max_distance:
                    continue

                iou = self._bbox_iou(track.bbox, detection.bbox)
                area_ratio = detection.area / max(1.0, track.area)
                area_penalty = abs(1.0 - area_ratio) * 0.15
                score = (distance / max_distance) - (iou * 0.35) - (detection.confidence * 0.1) + area_penalty
                candidates.append((score, track_id, detection_index))

        candidates.sort(key=lambda item: item[0])
        assigned_tracks: set[int] = set()
        assigned_detections: set[int] = set()
        matches: list[tuple[int, int]] = []

        for _, track_id, detection_index in candidates:
            if track_id in assigned_tracks or detection_index in assigned_detections:
                continue
            assigned_tracks.add(track_id)
            assigned_detections.add(detection_index)
            matches.append((track_id, detection_index))

        return matches

    def _centroid_distance(
        self,
        first: tuple[float, float],
        second: tuple[int, int] | tuple[float, float],
    ) -> float:
        delta_x = float(first[0]) - float(second[0])
        delta_y = float(first[1]) - float(second[1])
        return math.sqrt((delta_x * delta_x) + (delta_y * delta_y))

    def _direction_is_valid(self, track: TrackState, detection: Detection) -> bool:
        direction = self.config.expected_direction
        if direction == "any":
            return True

        delta_x = detection.centroid[0] - track.centroid[0]
        slack = self.config.direction_slack

        if direction == "left_to_right":
            return delta_x >= -slack
        if direction == "right_to_left":
            return delta_x <= slack
        return True

    def _area_is_valid(self, track: TrackState, detection: Detection) -> bool:
        area_ratio = detection.area / max(1.0, track.area)
        return self.config.min_area_ratio <= area_ratio <= self.config.max_area_ratio

    def _bbox_iou(
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
        union = float(max(1, first_w * first_h) + max(1, second_w * second_h)) - intersection
        if union <= 0:
            return 0.0
        return intersection / union

    def _build_track_event(
        self,
        event_name: str,
        track: TrackState,
        frame_index: int,
        timestamp_iso: str,
    ) -> dict[str, object]:
        return {
            "event": event_name,
            "frame_index": frame_index,
            "timestamp": timestamp_iso,
            "track_id": track.track_id,
            "profile_id": track.profile_id,
            "label": track.label,
            "color_name": track.color_name,
            "centroid": {"x": track.centroid[0], "y": track.centroid[1]},
            "bbox": {
                "x": track.bbox[0],
                "y": track.bbox[1],
                "w": track.bbox[2],
                "h": track.bbox[3],
            },
            "hits": track.hits,
            "age": track.age,
            "metadata": track.metadata,
        }

    def _crossing_confidence(self, track: TrackState) -> tuple[float, dict[str, float]]:
        contour_confidence = max(0.0, min(1.0, float(track.confidence)))
        track_continuity = max(0.0, min(1.0, track.hits / max(3.0, float(self.config.min_confirmed_frames + 2))))
        crossing_consistency = 1.0
        if track.previous_bbox is not None:
            previous_x = self._leading_edge_x(track.previous_bbox, self.line_counter.direction)
            current_x = self._leading_edge_x(track.bbox, self.line_counter.direction)
            delta_x = abs(current_x - previous_x)
            crossing_consistency = max(0.0, min(1.0, delta_x / max(1.0, self.config.direction_slack * 2.0)))

        combined = (contour_confidence * 0.45) + (track_continuity * 0.35) + (crossing_consistency * 0.20)
        return (
            max(0.0, min(1.0, combined)),
            {
                "color_contour": round(contour_confidence, 3),
                "track_continuity": round(track_continuity, 3),
                "crossing_consistency": round(crossing_consistency, 3),
            },
        )

    def _has_crossed_line(
        self,
        previous_bbox: tuple[int, int, int, int],
        current_bbox: tuple[int, int, int, int],
    ) -> bool:
        line_x = self.line_counter.x
        direction = self.line_counter.direction
        previous_left = previous_bbox[0]
        previous_right = previous_bbox[0] + previous_bbox[2]
        current_left = current_bbox[0]
        current_right = current_bbox[0] + current_bbox[2]

        if direction == "left_to_right":
            return previous_right < line_x <= current_right
        if direction == "right_to_left":
            return previous_left > line_x >= current_left
        return (
            previous_right < line_x <= current_right
            or previous_left > line_x >= current_left
        )

    def _leading_edge_x(
        self,
        bbox: tuple[int, int, int, int],
        direction: str,
    ) -> int:
        left = bbox[0]
        right = bbox[0] + bbox[2]
        if direction == "right_to_left":
            return left
        return right
