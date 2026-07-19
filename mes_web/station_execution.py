from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .config import AppConfig
from .db import mesql_v2


JsonObject = dict[str, Any]
STATION_EXECUTION_MAX_BODY_BYTES = 65_536
STATION_EXECUTION_COMMAND_LOG_FIELDS = (
    "event",
    "command_source",
    "station_code",
    "work_order_operation_id",
    "step_code",
    "action",
    "event_source",
    "external_event_id",
    "action_applied",
    "event_inserted",
    "error_code",
    "duration_ms",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _canonical_uuid(value: Any) -> str:
    text = _text(value)
    try:
        parsed = uuid.UUID(text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_OPERATION_NOT_FOUND",
            status_code=400,
        ) from exc
    canonical = str(parsed)
    if text != canonical:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_OPERATION_NOT_FOUND",
            status_code=400,
        )
    return canonical


def get_station_execution_context(
    config: AppConfig,
    station_code: Any,
) -> JsonObject:
    normalized_station_code = _upper(station_code)
    if not normalized_station_code:
        raise mesql_v2.MesqlV2Error("STATION_CODE_REQUIRED", status_code=400)
    return mesql_v2.get_station_execution_context(config, normalized_station_code)


def dispatch_station_execution_command(
    config: AppConfig,
    *,
    command_source: Any,
    station_code: Any,
    event_source: Any,
    external_event_id: Any,
    work_order_operation_id: Any = None,
    step_code: Any = None,
    action: Any = None,
    actor: Any = None,
    metadata: Any = None,
) -> JsonObject:
    normalized_source = _text(command_source).lower()
    normalized_station = _upper(station_code)
    normalized_event_source = _upper(event_source)
    normalized_external_id = _text(external_event_id)
    normalized_step = _upper(step_code) or None
    normalized_action = _text(action).lower() or None
    normalized_actor = _text(actor) or None
    normalized_operation = None
    if normalized_source not in {"kiosk", "mqtt"}:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_ACTION_NOT_ALLOWED",
            status_code=400,
        )
    if not normalized_station:
        raise mesql_v2.MesqlV2Error("STATION_CODE_REQUIRED", status_code=400)
    if normalized_source == "mqtt":
        if not isinstance(work_order_operation_id, str) or not work_order_operation_id.strip():
            raise mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_OPERATION_ID_REQUIRED",
                status_code=400,
            )
        if not isinstance(external_event_id, str) or not external_event_id.strip():
            raise mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_EXTERNAL_EVENT_ID_REQUIRED",
                status_code=400,
            )
    if work_order_operation_id is not None:
        normalized_operation = _canonical_uuid(work_order_operation_id)
    if not normalized_external_id:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_EXTERNAL_EVENT_ID_REQUIRED",
            status_code=400,
        )
    if not isinstance(metadata, (dict, type(None))):
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_METADATA_INVALID",
            status_code=400,
        )
    if normalized_source == "kiosk":
        if normalized_operation is None:
            raise mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_OPERATION_NOT_FOUND",
                status_code=400,
            )
        if not normalized_step:
            raise mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_STEP_NOT_FOUND",
                status_code=400,
            )
        if normalized_action not in {"start", "finish"}:
            raise mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_ACTION_NOT_ALLOWED",
                status_code=400,
            )
        if not normalized_actor:
            raise mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_ACTOR_REQUIRED",
                status_code=400,
            )
        normalized_event_source = None
    elif not normalized_event_source:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_EVENT_SOURCE_NOT_ALLOWED",
            status_code=400,
        )

    return mesql_v2.dispatch_station_execution_action(
        config,
        station_code=normalized_station,
        command_source=normalized_source,
        event_source=normalized_event_source,
        external_event_id=normalized_external_id,
        work_order_operation_id=normalized_operation,
        step_code=normalized_step,
        action=normalized_action,
        actor_id=normalized_actor,
        payload={"metadata": dict(metadata or {})},
    )


def dispatch_internal_station_execution_transition(
    config: AppConfig,
    *,
    station_code: Any,
    work_order_operation_id: Any,
    actor: Any = None,
) -> JsonObject:
    normalized_station = _upper(station_code)
    if not normalized_station:
        raise mesql_v2.MesqlV2Error("STATION_CODE_REQUIRED", status_code=400)
    normalized_operation = _canonical_uuid(work_order_operation_id)
    return mesql_v2.dispatch_internal_station_execution_transition(
        config,
        station_code=normalized_station,
        work_order_operation_id=normalized_operation,
        actor_id=_text(actor) or None,
    )


class _DuplicateJsonKeyError(ValueError):
    pass


def _json_object(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(value)


def parse_station_execution_mqtt_payload(raw_payload: Any) -> JsonObject:
    if not isinstance(raw_payload, (bytes, bytearray)):
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_MQTT_PAYLOAD_INVALID",
            status_code=400,
        )
    if len(raw_payload) > STATION_EXECUTION_MAX_BODY_BYTES:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_MQTT_PAYLOAD_TOO_LARGE",
            status_code=413,
        )
    try:
        decoded = bytes(raw_payload).decode("utf-8", errors="strict")
        payload = json.loads(
            decoded,
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_MQTT_PAYLOAD_INVALID",
            status_code=400,
        ) from exc
    if not isinstance(payload, dict):
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_MQTT_PAYLOAD_INVALID",
            status_code=400,
        )
    return payload


def load_station_execution_mqtt_topics(config: AppConfig) -> dict[str, JsonObject]:
    topics: dict[str, JsonObject] = {}
    for station_code in config.mesql_stations:
        for source in mesql_v2.list_station_event_sources(
            config,
            _upper(station_code),
            active_only=True,
        ):
            if str(source.get("event_channel") or "").lower() != "mqtt":
                continue
            topic = _text(source.get("mqtt_topic"))
            if not topic or topic in topics:
                raise mesql_v2.MesqlV2Error(
                    "STATION_EXECUTION_MQTT_TOPIC_CONFLICT",
                    status_code=409,
                )
            topics[topic] = {
                "station_code": _upper(source.get("station_code")),
                "event_source": _upper(source.get("source_code")),
            }
    return topics


def _publisher_external_event_id(payload: JsonObject) -> str:
    # The publisher owns this identity and must retain it unchanged for every
    # QoS1 redelivery.  A receiver-derived fallback cannot be reboot-stable.
    value = payload.get("external_event_id")
    if not isinstance(value, str) or not value.strip():
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_EXTERNAL_EVENT_ID_REQUIRED",
            status_code=400,
        )
    return value.strip()


def map_station_execution_mqtt_message(
    topic: Any,
    raw_payload: Any,
    topic_map: dict[str, JsonObject],
) -> JsonObject:
    normalized_topic = _text(topic)
    mapped = topic_map.get(normalized_topic)
    if mapped is None:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_MQTT_TOPIC_UNKNOWN",
            status_code=404,
        )
    payload = parse_station_execution_mqtt_payload(raw_payload)
    payload_station = _upper(payload.get("station_code"))
    payload_source = _upper(payload.get("source_code") or payload.get("event_source"))
    if payload_station and payload_station != mapped["station_code"]:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_OPERATION_STATION_MISMATCH",
            status_code=409,
        )
    if payload_source and payload_source != mapped["event_source"]:
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_EVENT_SOURCE_NOT_ALLOWED",
            status_code=409,
        )
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_METADATA_INVALID",
            status_code=400,
        )
    operation_id = payload.get("work_order_operation_id")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise mesql_v2.MesqlV2Error(
            "STATION_EXECUTION_OPERATION_ID_REQUIRED",
            status_code=400,
        )
    operation_id = _canonical_uuid(operation_id)
    return {
        "command_source": "mqtt",
        "station_code": mapped["station_code"],
        "event_source": mapped["event_source"],
        "external_event_id": _publisher_external_event_id(payload),
        "work_order_operation_id": operation_id,
        "step_code": _upper(payload.get("step_code")) or None,
        "action": _text(payload.get("transition") or payload.get("action")).lower() or None,
        "actor": _text(payload.get("device_id")) or None,
        "metadata": metadata,
    }


def log_text(value: Any, *, max_length: int = 256) -> str | None:
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


def command_log_extra(
    values: JsonObject,
    *,
    result: JsonObject | None,
    error_code: str | None,
    started_at: float,
) -> JsonObject:
    return {
        "event": "station_execution_command",
        "command_source": log_text(values.get("command_source")),
        "station_code": log_text(values.get("station_code")),
        "work_order_operation_id": log_text(
            (result or {}).get("work_order_operation_id")
            or values.get("work_order_operation_id")
        ),
        "step_code": log_text((result or {}).get("step_code") or values.get("step_code")),
        "action": log_text((result or {}).get("action") or values.get("action")),
        "event_source": log_text(
            (result or {}).get("event_source") or values.get("event_source")
        ),
        "external_event_id": log_text(values.get("external_event_id")),
        "action_applied": (result or {}).get("action_applied"),
        "event_inserted": (result or {}).get("event_inserted"),
        "error_code": error_code,
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
    }
