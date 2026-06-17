from __future__ import annotations

import logging
from typing import Any

from ..config import AppConfig
from .connection import database_connection
from .safe_write import DatabaseWriteResult, safe_db_write


JsonObject = dict[str, Any]
logger = logging.getLogger(__name__)

OPERATION = "package_sessions_shadow_write"
SOURCE = "mes_web_package_session_shadow"
PACKAGING_STATION_CODE = "PACKAGING_01"

UPSERT_PACKAGE_SESSION_SQL = """
INSERT INTO mes.package_sessions (
    session_id,
    package_order_id,
    station_code,
    status,
    started_at,
    finished_at,
    duration_seconds,
    source,
    payload,
    updated_at
) VALUES (
    %(session_id)s,
    %(package_order_id)s,
    %(station_code)s,
    %(status)s,
    %(started_at)s,
    %(finished_at)s,
    %(duration_seconds)s,
    %(source)s,
    %(payload)s,
    now()
)
ON CONFLICT (session_id) DO UPDATE SET
    package_order_id = EXCLUDED.package_order_id,
    station_code = EXCLUDED.station_code,
    status = EXCLUDED.status,
    started_at = COALESCE(EXCLUDED.started_at, mes.package_sessions.started_at),
    finished_at = COALESCE(EXCLUDED.finished_at, mes.package_sessions.finished_at),
    duration_seconds = COALESCE(EXCLUDED.duration_seconds, mes.package_sessions.duration_seconds),
    source = EXCLUDED.source,
    payload = EXCLUDED.payload,
    updated_at = now()
"""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _numeric_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError:
        return value
    return Jsonb(value)


def _session_params(session: JsonObject, *, status: str, payload: JsonObject | None = None) -> JsonObject:
    row_payload = {
        "session": dict(session),
        **(dict(payload) if isinstance(payload, dict) else {}),
    }
    return {
        "session_id": _text(session.get("session_id") or session.get("sessionId")),
        "package_order_id": _text(session.get("package_order_id") or session.get("packageOrderId")),
        "station_code": (_text(session.get("station_code") or session.get("stationCode")) or PACKAGING_STATION_CODE).upper(),
        "status": status,
        "started_at": _nullable_text(session.get("started_at") or session.get("startedAt")),
        "finished_at": _nullable_text(
            session.get("finished_at")
            or session.get("finishedAt")
            or session.get("cancelled_at")
            or session.get("cancelledAt")
        ),
        "duration_seconds": _numeric_or_none(session.get("duration_seconds") or session.get("durationSeconds")),
        "source": SOURCE,
        "payload": _jsonb(row_payload),
    }


def _upsert(config: AppConfig, params: JsonObject) -> DatabaseWriteResult:
    if not params["session_id"] or not params["package_order_id"] or not params["station_code"]:
        return DatabaseWriteResult(False, False, True, "missing_required_fields", OPERATION)

    def writer() -> None:
        with database_connection(config) as connection:
            if connection is None:
                raise RuntimeError("Database connection is disabled")
            with connection.cursor() as cursor:
                cursor.execute(UPSERT_PACKAGE_SESSION_SQL, params)
            commit = getattr(connection, "commit", None)
            if callable(commit):
                commit()

    return safe_db_write(config, OPERATION, writer, fail_open=True, logger=logger)


def upsert_package_session_started(
    config: AppConfig,
    session: JsonObject,
    *,
    payload: JsonObject | None = None,
) -> DatabaseWriteResult:
    return _upsert(config, _session_params(session, status="in_progress", payload=payload))


def upsert_package_session_finished(
    config: AppConfig,
    session: JsonObject,
    *,
    payload: JsonObject | None = None,
) -> DatabaseWriteResult:
    return _upsert(config, _session_params(session, status="finished", payload=payload))


def upsert_package_session_cancelled(
    config: AppConfig,
    session: JsonObject,
    *,
    payload: JsonObject | None = None,
) -> DatabaseWriteResult:
    return _upsert(config, _session_params(session, status="cancelled", payload=payload))
