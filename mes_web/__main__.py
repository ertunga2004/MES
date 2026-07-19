from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any

from starlette.requests import Request

from .db import mesql_v2


STATION_LOCATION_READ_MODEL_FEATURE_FLAG = "MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED"
STATION_EXECUTION_CONFIG_READ_MODEL_FEATURE_FLAG = "MES_WEB_DB_STATION_EXECUTION_CONFIG_READ_MODEL_ENABLED"
WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG = "MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED"
WORK_ORDER_ROUTE_RELEASE_MAX_BODY_BYTES = 65_536
WORK_ORDER_ROUTE_RELEASE_ALLOWED_FIELDS = frozenset({
    "release_id",
    "route_code",
    "route_version",
    "released_by",
    "metadata",
})
WORK_ORDER_ROUTE_RELEASE_SERVER_FIELDS = frozenset({
    "release_source",
    "mode",
    "operation_bindings",
})
WORK_ORDER_ROUTE_RELEASE_LOG_FIELDS = (
    "event",
    "work_order_id",
    "release_id",
    "route_code",
    "route_version",
    "released_by",
    "released",
    "error_code",
    "duration_ms",
)
WORK_ORDER_ROUTE_RELEASE_LOG_HANDLER_MARKER = "mes_web_work_order_route_release_json_v1"
logger = logging.getLogger(__name__)
ALLOWED_LOCATION_TYPES = frozenset({
    "raw_material",
    "wip",
    "buffer",
    "finished_goods",
    "scrap",
    "hold",
    "rework",
})
ALLOWED_BINDING_ROLES = frozenset({
    "input",
    "active_wip",
    "output_good",
    "output_scrap",
    "output_buffer",
})


def _configure_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    selector_policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy_cls is None:
        return
    current_policy = asyncio.get_event_loop_policy()
    if not isinstance(current_policy, selector_policy_cls):
        asyncio.set_event_loop_policy(selector_policy_cls())


class _WorkOrderRouteReleaseJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            field: getattr(record, field, None)
            for field in WORK_ORDER_ROUTE_RELEASE_LOG_FIELDS
        }
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )


def _work_order_route_release_exception_diagnostic(error: BaseException) -> dict[str, Any]:
    exception_chain: list[str] = []
    sqlstate: str | None = None
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(exception_chain) < 8:
        seen.add(id(current))
        exception_chain.append(
            _route_release_log_text(type(current).__name__, max_length=128)
            or "Exception"
        )
        if sqlstate is None:
            candidate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
            if (
                isinstance(candidate, str)
                and len(candidate) == 5
                and candidate.isascii()
                and candidate.isalnum()
                and candidate.upper() == candidate
            ):
                sqlstate = candidate
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return {
        "diagnostic": "work_order_route_release_internal_error",
        "exception_chain": exception_chain,
        "sqlstate": sqlstate,
    }


class _WorkOrderRouteReleaseJsonHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        if not record.exc_info or record.exc_info[1] is None:
            return
        try:
            diagnostic = _work_order_route_release_exception_diagnostic(
                record.exc_info[1]
            )
            self.stream.write(
                json.dumps(
                    diagnostic,
                    ensure_ascii=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + self.terminator
            )
            self.flush()
        except Exception:
            return


def _configure_work_order_route_release_logging() -> None:
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if any(
        getattr(handler, "name", None) == WORK_ORDER_ROUTE_RELEASE_LOG_HANDLER_MARKER
        for handler in logger.handlers
    ):
        return
    handler = _WorkOrderRouteReleaseJsonHandler(sys.stderr)
    handler.name = WORK_ORDER_ROUTE_RELEASE_LOG_HANDLER_MARKER
    handler.setLevel(logging.INFO)
    handler.setFormatter(_WorkOrderRouteReleaseJsonFormatter())
    logger.addHandler(handler)


def _station_location_read_model_enabled() -> bool:
    raw = os.getenv(STATION_LOCATION_READ_MODEL_FEATURE_FLAG, "")
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _station_execution_config_read_model_enabled() -> bool:
    raw = os.getenv(STATION_EXECUTION_CONFIG_READ_MODEL_FEATURE_FLAG, "")
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _work_order_route_release_enabled() -> bool:
    raw = os.getenv(WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG, "")
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _route_release_http_error(status_code: int, detail: str, *, cause: BaseException | None = None) -> None:
    from fastapi import HTTPException

    error = HTTPException(status_code=status_code, detail=detail)
    if cause is None:
        raise error
    raise error from cause


async def _read_work_order_route_release_body(request: Any) -> bytes:
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        if declared_length.isascii() and declared_length.isdigit():
            normalized_digits = declared_length.lstrip("0") or "0"
            if len(normalized_digits) > len(str(WORK_ORDER_ROUTE_RELEASE_MAX_BODY_BYTES)):
                _route_release_http_error(413, "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE")
            parsed_length = int(normalized_digits, 10)
        else:
            parsed_length = None
        if parsed_length is not None and parsed_length >= 0 and parsed_length > WORK_ORDER_ROUTE_RELEASE_MAX_BODY_BYTES:
            _route_release_http_error(413, "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE")

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > WORK_ORDER_ROUTE_RELEASE_MAX_BODY_BYTES:
            _route_release_http_error(413, "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


class _DuplicateRouteReleaseJsonKeyError(ValueError):
    pass


def _route_release_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateRouteReleaseJsonKeyError(key)
        result[key] = value
    return result


def _reject_route_release_json_constant(value: str) -> None:
    raise ValueError(value)


def _parse_work_order_route_release_json(raw_body: bytes) -> dict[str, Any]:
    try:
        decoded = raw_body.decode("utf-8", errors="strict")
        payload = json.loads(
            decoded,
            object_pairs_hook=_route_release_json_object,
            parse_constant=_reject_route_release_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        _route_release_http_error(
            400,
            "WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID",
            cause=exc,
        )
    if not isinstance(payload, dict):
        _route_release_http_error(400, "WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID")
    return payload


def _required_route_release_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        _route_release_http_error(400, f"{field_name}_INVALID")
    normalized = value.strip()
    if not normalized:
        _route_release_http_error(400, f"{field_name}_REQUIRED")
    return normalized


def _normalize_work_order_route_release_http_request(
    work_order_id: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if any(field in payload for field in WORK_ORDER_ROUTE_RELEASE_SERVER_FIELDS):
        _route_release_http_error(
            400,
            "WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED",
        )
    if any(field not in WORK_ORDER_ROUTE_RELEASE_ALLOWED_FIELDS for field in payload):
        _route_release_http_error(400, "WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD")

    normalized_work_order_id = _required_route_release_text(
        work_order_id,
        field_name="WORK_ORDER_ID",
    )
    normalized_release_id = _required_route_release_text(
        payload.get("release_id"),
        field_name="RELEASE_ID",
    )
    normalized_route_code = _required_route_release_text(
        payload.get("route_code"),
        field_name="ROUTE_CODE",
    ).upper()
    route_version = payload.get("route_version")
    if route_version is None or route_version == "":
        _route_release_http_error(400, "ROUTE_VERSION_REQUIRED")
    if isinstance(route_version, bool) or not isinstance(route_version, int) or route_version <= 0:
        _route_release_http_error(400, "ROUTE_VERSION_INVALID")
    normalized_released_by = _required_route_release_text(
        payload.get("released_by"),
        field_name="RELEASED_BY",
    )
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        _route_release_http_error(400, "RELEASE_METADATA_INVALID")

    return {
        "work_order_id": normalized_work_order_id,
        "release_id": normalized_release_id,
        "route_code": normalized_route_code,
        "route_version": route_version,
        "released_by": normalized_released_by,
        "metadata": metadata,
    }


def _route_release_log_text(value: Any, *, max_length: int = 256) -> str | None:
    if value is None:
        return None
    text = str(value)
    sanitized = "".join(
        character
        if ord(character) >= 32
        and not 127 <= ord(character) <= 159
        and not 0xD800 <= ord(character) <= 0xDFFF
        and character not in {"\u2028", "\u2029"}
        else "\ufffd"
        for character in text
    )
    return sanitized[:max_length]


def _route_release_log_extra(
    values: dict[str, Any],
    *,
    released: bool | None,
    error_code: str | None,
    started_at: float,
) -> dict[str, Any]:
    return {
        "event": "work_order_route_release_request",
        "work_order_id": _route_release_log_text(values.get("work_order_id")),
        "release_id": _route_release_log_text(values.get("release_id")),
        "route_code": _route_release_log_text(values.get("route_code")),
        "route_version": values.get("route_version") if isinstance(values.get("route_version"), int) else None,
        "released_by": _route_release_log_text(values.get("released_by")),
        "released": released,
        "error_code": error_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
    }


def register_work_order_route_release_routes(app: Any, app_config: Any) -> None:
    from fastapi import HTTPException

    @app.post("/api/v2/work-orders/{work_order_id}/route-release")
    async def api_v2_work_order_route_release(
        work_order_id: str,
        request: Request,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        log_values: dict[str, Any] = {"work_order_id": work_order_id}
        if not _work_order_route_release_enabled():
            logger.info(
                "work_order_route_release_request",
                extra=_route_release_log_extra(
                    log_values,
                    released=None,
                    error_code="WORK_ORDER_ROUTE_RELEASE_DISABLED",
                    started_at=started_at,
                ),
            )
            raise HTTPException(
                status_code=503,
                detail="WORK_ORDER_ROUTE_RELEASE_DISABLED",
            )

        try:
            raw_body = await _read_work_order_route_release_body(request)
            payload = _parse_work_order_route_release_json(raw_body)
            normalized = _normalize_work_order_route_release_http_request(
                work_order_id,
                payload,
            )
            log_values = normalized
            result = mesql_v2.release_work_order_to_route(
                app_config,
                release_id=normalized["release_id"],
                work_order_id=normalized["work_order_id"],
                route_code=normalized["route_code"],
                route_version=normalized["route_version"],
                release_source="local_planning",
                released_by=normalized["released_by"],
                mode="route_generated",
                operation_bindings=None,
                metadata=normalized["metadata"],
            )
            response = {
                "ok": True,
                "released": result["released"],
                "release": result["release"],
                "work_order": result["work_order"],
                "operations": result["operations"],
                "bindings": result["bindings"],
                "initial_queue": result["initial_queue"],
            }
            logger.info(
                "work_order_route_release_request",
                extra=_route_release_log_extra(
                    log_values,
                    released=bool(result["released"]),
                    error_code=None,
                    started_at=started_at,
                ),
            )
            return response
        except mesql_v2.MesqlV2Error as exc:
            logger.info(
                "work_order_route_release_request",
                extra=_route_release_log_extra(
                    log_values,
                    released=None,
                    error_code=exc.detail,
                    started_at=started_at,
                ),
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        except HTTPException as exc:
            logger.info(
                "work_order_route_release_request",
                extra=_route_release_log_extra(
                    log_values,
                    released=None,
                    error_code=str(exc.detail),
                    started_at=started_at,
                ),
            )
            raise
        except Exception as exc:
            logger.exception(
                "work_order_route_release_request",
                extra=_route_release_log_extra(
                    log_values,
                    released=None,
                    error_code="INTERNAL_ERROR",
                    started_at=started_at,
                ),
            )
            raise HTTPException(status_code=500, detail="INTERNAL_ERROR") from exc


def _normalize_code(value: str) -> str:
    return str(value or "").strip().upper()


def _normalize_optional_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_code(value)
    return normalized or None


def _normalize_optional_filter(value: str | None, *, allowed: frozenset[str], error_code: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized not in allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=error_code)
    return normalized


def _parse_active_only(value: str | bool | None) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return True
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail="INVALID_QUERY_PARAM")


def _parse_positive_int(value: str | int | None, *, default: int = 1) -> int:
    if value is None:
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="INVALID_QUERY_PARAM") from None
    if parsed < 1:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="INVALID_QUERY_PARAM")
    return parsed


def register_station_location_read_routes(app: Any, app_config: Any) -> None:
    from fastapi import HTTPException, Query

    def require_enabled() -> None:
        if not _station_location_read_model_enabled():
            raise HTTPException(status_code=503, detail="STATION_LOCATION_READ_MODEL_DISABLED")

    def raise_mesql_v2_error(exc: mesql_v2.MesqlV2Error) -> None:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @app.get("/api/v2/locations")
    async def api_v2_locations(
        active_only: str | None = Query(default=None),
        location_type: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        parsed_active_only = _parse_active_only(active_only)
        normalized_location_type = _normalize_optional_filter(
            location_type,
            allowed=ALLOWED_LOCATION_TYPES,
            error_code="INVALID_LOCATION_TYPE",
        )
        try:
            locations = mesql_v2.list_locations(
                app_config,
                active_only=parsed_active_only,
                location_type=normalized_location_type,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        return {"ok": True, "data": locations, "count": len(locations)}

    @app.get("/api/v2/locations/{location_code}")
    async def api_v2_location_detail(location_code: str) -> dict[str, Any]:
        require_enabled()
        normalized_location_code = _normalize_code(location_code)
        try:
            location = mesql_v2.get_location_by_code(app_config, normalized_location_code)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        if location is None:
            raise HTTPException(status_code=404, detail="LOCATION_NOT_FOUND")
        return {"ok": True, "data": location}

    @app.get("/api/v2/stations/{station_code}/locations")
    async def api_v2_station_locations(
        station_code: str,
        active_only: str | None = Query(default=None),
        role: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        normalized_station_code = _normalize_code(station_code)
        parsed_active_only = _parse_active_only(active_only)
        normalized_role = _normalize_optional_filter(
            role,
            allowed=ALLOWED_BINDING_ROLES,
            error_code="INVALID_BINDING_ROLE",
        )
        try:
            bindings = mesql_v2.list_station_location_bindings(
                app_config,
                normalized_station_code,
                active_only=parsed_active_only,
                role=normalized_role,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        return {
            "ok": True,
            "station_code": normalized_station_code,
            "data": bindings,
            "count": len(bindings),
        }

    @app.get("/api/v2/stations/{station_code}/location-context")
    async def api_v2_station_location_context(station_code: str) -> dict[str, Any]:
        require_enabled()
        normalized_station_code = _normalize_code(station_code)
        try:
            context = mesql_v2.get_station_location_context(app_config, normalized_station_code)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        return {
            "ok": True,
            "station_code": normalized_station_code,
            "data": context,
        }


def register_station_execution_config_read_routes(app: Any, app_config: Any) -> None:
    from fastapi import HTTPException, Query

    def require_enabled() -> None:
        if not _station_execution_config_read_model_enabled():
            raise HTTPException(status_code=503, detail="STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED")

    def raise_mesql_v2_error(exc: mesql_v2.MesqlV2Error) -> None:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    def raise_internal_error(exc: Exception) -> None:
        raise HTTPException(status_code=500, detail="INTERNAL_ERROR") from exc

    @app.get("/api/v2/station-execution/items")
    async def api_v2_station_execution_items(
        active_only: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        parsed_active_only = _parse_active_only(active_only)
        try:
            items = mesql_v2.list_items(app_config, active_only=parsed_active_only)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        return {"ok": True, "items": items, "count": len(items)}

    @app.get("/api/v2/station-execution/items/{item_code}")
    async def api_v2_station_execution_item_detail(item_code: str) -> dict[str, Any]:
        require_enabled()
        normalized_item_code = _normalize_code(item_code)
        try:
            item = mesql_v2.get_item_by_code(app_config, normalized_item_code)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        if item is None:
            raise HTTPException(status_code=404, detail="ITEM_NOT_FOUND")
        return {"ok": True, "item": item}

    @app.get("/api/v2/station-execution/routes")
    async def api_v2_station_execution_routes(
        active_only: str | None = Query(default=None),
        item_code: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        parsed_active_only = _parse_active_only(active_only)
        normalized_item_code = _normalize_optional_code(item_code)
        try:
            routes = mesql_v2.list_process_routes(
                app_config,
                active_only=parsed_active_only,
                item_code=normalized_item_code,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        return {"ok": True, "routes": routes, "count": len(routes)}

    @app.get("/api/v2/station-execution/routes/{route_code}")
    async def api_v2_station_execution_route_detail(
        route_code: str,
        version: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        normalized_route_code = _normalize_code(route_code)
        parsed_version = _parse_positive_int(version, default=1)
        try:
            route = mesql_v2.get_process_route(app_config, normalized_route_code, version=parsed_version)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        if route is None:
            raise HTTPException(status_code=404, detail="PROCESS_ROUTE_NOT_FOUND")
        return {"ok": True, "route": route}

    @app.get("/api/v2/station-execution/route-operations")
    async def api_v2_station_execution_route_operations(
        active_only: str | None = Query(default=None),
        route_code: str | None = Query(default=None),
        station_code: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        parsed_active_only = _parse_active_only(active_only)
        normalized_route_code = _normalize_optional_code(route_code)
        normalized_station_code = _normalize_optional_code(station_code)
        try:
            route_operations = mesql_v2.list_route_operations(
                app_config,
                route_code=normalized_route_code,
                station_code=normalized_station_code,
                active_only=parsed_active_only,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        return {"ok": True, "route_operations": route_operations, "count": len(route_operations)}

    @app.get("/api/v2/stations/{station_code}/execution-event-sources")
    async def api_v2_station_execution_event_sources(
        station_code: str,
        active_only: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        normalized_station_code = _normalize_code(station_code)
        parsed_active_only = _parse_active_only(active_only)
        try:
            event_sources = mesql_v2.list_station_event_sources(
                app_config,
                normalized_station_code,
                active_only=parsed_active_only,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        return {
            "ok": True,
            "station_code": normalized_station_code,
            "event_sources": event_sources,
            "count": len(event_sources),
        }

    @app.get("/api/v2/stations/{station_code}/execution-config")
    async def api_v2_station_execution_config(station_code: str) -> dict[str, Any]:
        require_enabled()
        normalized_station_code = _normalize_code(station_code)
        try:
            config = mesql_v2.get_station_execution_config(app_config, normalized_station_code)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        return {"ok": True, "config": config}

    @app.get("/api/v2/station-execution/route-operations/{route_operation_id}/steps")
    async def api_v2_station_execution_route_operation_steps(
        route_operation_id: str,
        active_only: str | None = Query(default=None),
    ) -> dict[str, Any]:
        require_enabled()
        normalized_route_operation_id = _normalize_code(route_operation_id)
        parsed_active_only = _parse_active_only(active_only)
        try:
            route_operation = mesql_v2.get_route_operation(app_config, normalized_route_operation_id)
            if route_operation is None:
                raise HTTPException(status_code=404, detail="ROUTE_OPERATION_NOT_FOUND")
            steps = mesql_v2.list_operation_steps(
                app_config,
                normalized_route_operation_id,
                active_only=parsed_active_only,
            )
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except HTTPException:
            raise
        except Exception as exc:
            raise_internal_error(exc)
        return {
            "ok": True,
            "route_operation_id": normalized_route_operation_id,
            "steps": steps,
            "count": len(steps),
        }

    @app.get("/api/v2/station-execution/route-operations/{route_operation_id}/config")
    async def api_v2_station_execution_route_operation_config(route_operation_id: str) -> dict[str, Any]:
        require_enabled()
        normalized_route_operation_id = _normalize_code(route_operation_id)
        try:
            config = mesql_v2.get_route_operation_config(app_config, normalized_route_operation_id)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        if config is None:
            raise HTTPException(status_code=404, detail="ROUTE_OPERATION_NOT_FOUND")
        return {"ok": True, "config": config}

    @app.get("/api/v2/station-execution/route-operations/{route_operation_id}")
    async def api_v2_station_execution_route_operation_detail(route_operation_id: str) -> dict[str, Any]:
        require_enabled()
        normalized_route_operation_id = _normalize_code(route_operation_id)
        try:
            route_operation = mesql_v2.get_route_operation(app_config, normalized_route_operation_id)
        except mesql_v2.MesqlV2Error as exc:
            raise_mesql_v2_error(exc)
        except Exception as exc:
            raise_internal_error(exc)
        if route_operation is None:
            raise HTTPException(status_code=404, detail="ROUTE_OPERATION_NOT_FOUND")
        return {"ok": True, "route_operation": route_operation}


def main() -> None:
    _configure_event_loop_policy()
    _configure_work_order_route_release_logging()
    try:
        import uvicorn
        from .app import app, config
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing dependency: {exc.name}. Install mes_web/requirements.txt first.") from exc

    register_station_location_read_routes(app, config)
    register_station_execution_config_read_routes(app, config)
    register_work_order_route_release_routes(app, config)
    uvicorn.run(app, host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    main()
