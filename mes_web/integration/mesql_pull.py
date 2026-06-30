from __future__ import annotations

from typing import Any

from ..config import AppConfig
from ..db.mesql_v2 import JsonObject, MesqlPullResult, upsert_mesql_queue_items
from .mesql_client import MesqlClient


def _queue_items(payload: JsonObject) -> list[JsonObject]:
    queue = payload.get("queue")
    if not isinstance(queue, list):
        return []
    return [dict(item) for item in queue if isinstance(item, dict)]


def pull_mesql_station_queues(
    config: AppConfig,
    *,
    stations: list[str] | tuple[str, ...] | None = None,
    dry_run: bool = False,
    client: MesqlClient | None = None,
) -> JsonObject:
    station_codes = [str(station or "").strip().upper() for station in (stations or config.mesql_stations)]
    station_codes = [station for station in station_codes if station]
    mesql_client = client or MesqlClient.from_config(config)
    station_payloads: dict[str, list[JsonObject]] = {}
    errors: list[JsonObject] = []

    for station_code in station_codes:
        try:
            station_payloads[station_code] = _queue_items(mesql_client.get_station_queue(station_code))
        except Exception as exc:
            errors.append({"station_code": station_code, "reason": type(exc).__name__, "message": str(exc)})

    result: MesqlPullResult = upsert_mesql_queue_items(config, station_payloads, dry_run=dry_run)
    result.errors.extend(errors)
    return result.to_dict()
