from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from mes_web.mesql_client import (
    MesqlClient,
    MesqlConflictError,
    MesqlUnavailableError,
    queue_plans,
)


QUEUE_PAYLOAD = {
    "station_code": "ASSEMBLY_01",
    "queue": [
        {
            "order_id": "WO-MVP-002",
            "product_code": "PRD-MVP-002",
            "product_name": "Test Urunu",
            "revision_code": "R2",
            "queue_rank": 1,
            "order_status": "queued",
            "queue_status": "queued",
            "planned_quantity": 3,
            "uom_code": "ea",
            "operation": {
                "operation_no": 10,
                "operation_code": "OP-ASM",
                "operation_name": "Montaj",
                "sequence_no": 1,
                "work_center_code": "WC-01",
                "station_code": "ASSEMBLY_01",
                "good_quantity": 2,
                "scrap_quantity": 1,
            },
        }
    ],
}


class MesqlClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_accepts_any_2xx_without_retry(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(202, json={"status": "started"})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        with patch("mes_web.mesql_client.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            result = await MesqlClient("http://mesql", timeout_sec=1).start_operation(
                order_id="WO-MVP-002",
                operation_no=10,
                operator_id="OP-1",
                station_code="ASSEMBLY_01",
                started_at="2026-06-19T10:00:00+03:00",
            )

        self.assertEqual(result["status"], "started")
        self.assertEqual(len(requests), 1)

    async def test_conflict_and_network_failures_are_typed(self) -> None:
        real_client = httpx.AsyncClient
        conflict_transport = httpx.MockTransport(lambda _request: httpx.Response(409, json={"detail": {"status": "already_completed"}}))
        with patch("mes_web.mesql_client.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=conflict_transport, **kwargs)):
            with self.assertRaises(MesqlConflictError):
                await MesqlClient("http://mesql").get_station_queue("ASSEMBLY_01")

        def unavailable(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        unavailable_transport = httpx.MockTransport(unavailable)
        with patch("mes_web.mesql_client.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=unavailable_transport, **kwargs)):
            with self.assertRaises(MesqlUnavailableError):
                await MesqlClient("http://mesql").get_station_queue("ASSEMBLY_01")

    def test_queue_projection_keeps_remote_status_in_mesql_metadata(self) -> None:
        plan = queue_plans(QUEUE_PAYLOAD)[0]
        runtime = plan.runtime_plan()

        self.assertNotIn("status", runtime)
        self.assertEqual(runtime["_mesql"]["remote_status"], "queued")
        self.assertEqual(plan.remote_good_quantity, 2)
        self.assertEqual(plan.remote_scrap_quantity, 1)


if __name__ == "__main__":
    unittest.main()
