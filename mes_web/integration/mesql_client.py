from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..config import AppConfig


JsonObject = dict[str, Any]


class MesqlClientError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MesqlClient:
    base_url: str
    pull_timeout_sec: float = 10.0
    push_timeout_sec: float = 10.0

    @classmethod
    def from_config(cls, config: AppConfig) -> "MesqlClient":
        return cls(
            base_url=str(config.mesql_api_base_url or "http://ferptop:8090").rstrip("/"),
            pull_timeout_sec=float(config.mesql_pull_timeout_sec),
            push_timeout_sec=float(config.mesql_push_timeout_sec),
        )

    def _request(self, method: str, path: str, *, timeout: float, json: JsonObject | None = None) -> JsonObject:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.request(method, url, json=json, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise MesqlClientError(f"MESQL_HTTP_{exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.HTTPError as exc:
            raise MesqlClientError(f"MESQL_HTTP_ERROR: {exc}") from exc
        except ValueError as exc:
            raise MesqlClientError(f"MESQL_INVALID_JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise MesqlClientError("MESQL_INVALID_RESPONSE")
        return payload

    def get_station_queue(self, station_code: str) -> JsonObject:
        return self._request(
            "GET",
            f"/api/v1/mes/stations/{station_code}/queue",
            timeout=self.pull_timeout_sec,
        )

    def start_operation(self, payload: JsonObject) -> JsonObject:
        return self._request(
            "POST",
            "/api/v1/mes/operations/start",
            timeout=self.push_timeout_sec,
            json=payload,
        )

    def complete_operation(self, payload: JsonObject) -> JsonObject:
        return self._request(
            "POST",
            "/api/v1/mes/operations/complete",
            timeout=self.push_timeout_sec,
            json=payload,
        )

    def get_openapi(self) -> JsonObject:
        return self._request("GET", "/openapi.json", timeout=self.pull_timeout_sec)
