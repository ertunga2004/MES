from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from threading import Lock
from typing import Any


def _parse_iso_timestamp(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is empty")
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_target_datetime(payload: Any) -> tuple[datetime, str]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            raise ValueError("empty time sync payload")
        if text.startswith("{"):
            payload = json.loads(text)
        else:
            try:
                seconds = float(text)
            except ValueError:
                return _parse_iso_timestamp(text), "timestamp"
            return datetime.fromtimestamp(seconds, tz=timezone.utc), "unix"

    if not isinstance(payload, dict):
        raise ValueError("time sync payload must be a JSON object, ISO timestamp, or unix time")

    for key in ("timestamp", "iso_time", "datetime", "time"):
        if payload.get(key):
            return _parse_iso_timestamp(str(payload[key])), key

    for key in ("unix_ms", "epoch_ms"):
        if payload.get(key) is not None:
            return datetime.fromtimestamp(float(payload[key]) / 1000.0, tz=timezone.utc), key

    for key in ("unix", "epoch", "unix_s", "epoch_s"):
        if payload.get(key) is not None:
            return datetime.fromtimestamp(float(payload[key]), tz=timezone.utc), key

    raise ValueError("time sync payload is missing a supported timestamp field")


@dataclass
class ClockSyncResult:
    target_timestamp: str
    offset_seconds: float
    source: str
    applied_at: str


class TimestampOffsetClock:
    def __init__(self) -> None:
        self._offset = timedelta(0)
        self._lock = Lock()
        self._last_sync_at: datetime | None = None
        self._last_sync_source: str | None = None

    def now(self) -> datetime:
        with self._lock:
            offset = self._offset
        return datetime.now(timezone.utc) + offset

    def iso_now(self) -> str:
        return self.now().isoformat()

    def offset_seconds(self) -> float:
        with self._lock:
            return self._offset.total_seconds()

    def sync_from_payload(self, payload: Any, *, source: str = "mqtt") -> ClockSyncResult:
        target_datetime, payload_source = _parse_target_datetime(payload)
        applied_at = datetime.now(timezone.utc)
        with self._lock:
            self._offset = target_datetime - applied_at
            self._last_sync_at = applied_at
            self._last_sync_source = f"{source}:{payload_source}"
            offset_seconds = self._offset.total_seconds()
        return ClockSyncResult(
            target_timestamp=target_datetime.isoformat(),
            offset_seconds=offset_seconds,
            source=self._last_sync_source,
            applied_at=applied_at.isoformat(),
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "clock_synced": self._last_sync_at is not None,
                "clock_offset_sec": round(self._offset.total_seconds(), 3),
                "clock_last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at is not None else None,
                "clock_last_sync_source": self._last_sync_source,
            }
