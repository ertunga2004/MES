from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


JsonObject = dict[str, Any]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class MesqlError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 0, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class MesqlUnavailableError(MesqlError):
    def __init__(self, message: str = "MESQL servisine ulasilamiyor.", *, detail: Any = None) -> None:
        super().__init__("MESQL_UNAVAILABLE", message, status_code=503, detail=detail)


class MesqlConflictError(MesqlError):
    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__("MESQL_CONFLICT", message, status_code=409, detail=detail)


@dataclass(frozen=True, slots=True)
class MesqlQueuePlan:
    order_id: str
    station_code: str
    queue_rank: int
    product_code: str
    product_name: str
    revision_code: str
    planned_quantity: float | None
    uom_code: str
    operation_no: int | None
    operation_code: str
    operation_name: str
    sequence_no: int | None
    work_center_code: str
    remote_order_status: str
    remote_queue_status: str
    work_order_operation_id: str
    operation_id: str
    remote_good_quantity: float | None
    remote_scrap_quantity: float | None

    def runtime_plan(self) -> JsonObject:
        mesql = {
            "remote_status": self.remote_order_status,
            "remote_queue_status": self.remote_queue_status,
            "work_order_operation_id": self.work_order_operation_id,
            "operation_id": self.operation_id,
            "good_quantity": self.remote_good_quantity,
            "scrap_quantity": self.remote_scrap_quantity,
        }
        return {
            "orderId": self.order_id,
            "productCode": self.product_code,
            "stockCode": self.product_code,
            "stockName": self.product_name,
            "revisionCode": self.revision_code,
            "quantity": self.planned_quantity or 0,
            "targetQuantity": self.planned_quantity or 0,
            "unit": self.uom_code,
            "stationCode": self.station_code,
            "workStationCode": self.station_code,
            "workCenterCode": self.work_center_code,
            "operationNo": self.operation_no,
            "operationCode": self.operation_code,
            "operationName": self.operation_name,
            "sequenceNo": self.sequence_no or 0,
            "_mesql": mesql,
        }


def queue_plans(payload: JsonObject, *, station_code: str = "") -> list[MesqlQueuePlan]:
    raw_queue = payload.get("queue")
    if not isinstance(raw_queue, list):
        raise MesqlError("MESQL_INVALID_RESPONSE", "MESQL queue cevabi gecersiz.", status_code=502, detail=payload)
    fallback_station = _text(station_code or payload.get("station_code")).upper()
    plans: list[MesqlQueuePlan] = []
    for index, raw in enumerate(raw_queue):
        if not isinstance(raw, dict):
            continue
        operation = raw.get("operation") if isinstance(raw.get("operation"), dict) else {}
        order_id = _text(raw.get("order_id"))
        resolved_station = _text(operation.get("station_code") or raw.get("station_code") or fallback_station).upper()
        if not order_id or not resolved_station:
            continue
        operation_no_value = _number(operation.get("operation_no"))
        sequence_value = _number(operation.get("sequence_no"))
        rank_value = _number(raw.get("queue_rank"))
        plans.append(
            MesqlQueuePlan(
                order_id=order_id,
                station_code=resolved_station,
                queue_rank=max(0, int(rank_value if rank_value is not None else index)),
                product_code=_text(raw.get("product_code")),
                product_name=_text(raw.get("product_name")),
                revision_code=_text(raw.get("revision_code")),
                planned_quantity=_number(raw.get("planned_quantity") if raw.get("planned_quantity") is not None else operation.get("planned_quantity")),
                uom_code=_text(raw.get("uom_code") or operation.get("uom_code")),
                operation_no=int(operation_no_value) if operation_no_value is not None else None,
                operation_code=_text(operation.get("operation_code")),
                operation_name=_text(operation.get("operation_name")),
                sequence_no=int(sequence_value) if sequence_value is not None else None,
                work_center_code=_text(operation.get("work_center_code")),
                remote_order_status=_text(raw.get("order_status")),
                remote_queue_status=_text(raw.get("queue_status")),
                work_order_operation_id=_text(operation.get("work_order_operation_id")),
                operation_id=_text(operation.get("operation_id")),
                remote_good_quantity=_number(operation.get("good_quantity") if operation.get("good_quantity") is not None else raw.get("good_quantity")),
                remote_scrap_quantity=_number(operation.get("scrap_quantity") if operation.get("scrap_quantity") is not None else raw.get("scrap_quantity")),
            )
        )
    return plans


class MesqlClient:
    def __init__(self, base_url: str, *, timeout_sec: float = 3.0) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = max(0.1, float(timeout_sec))

    async def _request(self, method: str, path: str, *, params: JsonObject | None = None, json: JsonObject | None = None) -> JsonObject:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, params=params, json=json)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise MesqlUnavailableError(detail=type(exc).__name__) from exc

        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text}
        if not isinstance(body, dict):
            body = {"data": body}
        if 200 <= response.status_code < 300:
            return body
        detail = body.get("detail", body)
        message = _text(detail.get("message") if isinstance(detail, dict) else detail) or f"MESQL HTTP {response.status_code}"
        if response.status_code == 409:
            raise MesqlConflictError(message, detail=detail)
        if response.status_code >= 500:
            raise MesqlUnavailableError(message, detail=detail)
        raise MesqlError("MESQL_REJECTED", message, status_code=response.status_code, detail=detail)

    async def get_station_queue(self, station_code: str, *, include_done: bool = False) -> JsonObject:
        return await self._request(
            "GET",
            f"/api/v1/mes/stations/{_text(station_code).upper()}/queue",
            params={"include_done": "true"} if include_done else None,
        )

    async def start_operation(
        self,
        *,
        order_id: str,
        operation_no: int,
        operator_id: str,
        station_code: str,
        started_at: str,
    ) -> JsonObject:
        return await self._request(
            "POST",
            "/api/v1/mes/operations/start",
            json={
                "order_id": order_id,
                "operation_no": operation_no,
                "operator_id": operator_id,
                "station_code": station_code,
                "started_at": started_at,
            },
        )

    async def complete_operation(
        self,
        *,
        order_id: str,
        operation_no: int,
        operator_id: str,
        station_code: str,
        good_quantity: float,
        scrap_quantity: float,
        uom_code: str,
        completed_at: str,
    ) -> JsonObject:
        return await self._request(
            "POST",
            "/api/v1/mes/operations/complete",
            json={
                "order_id": order_id,
                "operation_no": operation_no,
                "operator_id": operator_id,
                "station_code": station_code,
                "good_quantity": good_quantity,
                "scrap_quantity": scrap_quantity,
                "uom_code": uom_code,
                "completed_at": completed_at,
            },
        )
