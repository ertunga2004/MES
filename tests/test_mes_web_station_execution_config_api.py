from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import mes_web.__main__ as main_module
from mes_web.config import AppConfig


class StationExecutionConfigApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig(db_enabled=True)
        self.app = FastAPI()
        main_module.register_station_execution_config_read_routes(self.app, self.config)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def _get(self, path: str, *, enabled: bool = True):
        flag_value = "true" if enabled else "false"
        with patch.dict(
            os.environ,
            {main_module.STATION_EXECUTION_CONFIG_READ_MODEL_FEATURE_FLAG: flag_value},
            clear=False,
        ):
            return self.client.get(path)

    def test_station_execution_config_api_disabled_returns_503_for_endpoint_groups(self) -> None:
        endpoints = [
            "/api/v2/station-execution/items",
            "/api/v2/station-execution/items/PACKAGED_PRODUCT",
            "/api/v2/station-execution/routes",
            "/api/v2/station-execution/routes/ROUTE_BOX_PACKAGING_V1",
            "/api/v2/station-execution/route-operations",
            "/api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP10",
            "/api/v2/stations/ASSEMBLY_01/execution-event-sources",
            "/api/v2/stations/ASSEMBLY_01/execution-config",
            "/api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP10/steps",
            "/api/v2/station-execution/route-operations/ROUTE_BOX_PACKAGING_V1_OP10/config",
        ]

        with patch.object(main_module.mesql_v2, "list_items", return_value=[]) as helper:
            for endpoint in endpoints:
                with self.subTest(endpoint=endpoint):
                    response = self._get(endpoint, enabled=False)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(
                        response.json()["detail"],
                        "STATION_EXECUTION_CONFIG_READ_MODEL_DISABLED",
                    )

        helper.assert_not_called()

    def test_list_items_rejects_invalid_active_only(self) -> None:
        with patch.object(main_module.mesql_v2, "list_items", return_value=[]) as helper:
            response = self._get("/api/v2/station-execution/items?active_only=maybe")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "INVALID_QUERY_PARAM")
        helper.assert_not_called()

    def test_list_items_returns_items_and_count(self) -> None:
        rows = [{"item_code": "PACKAGED_PRODUCT", "active": True}]

        with patch.object(main_module.mesql_v2, "list_items", return_value=rows) as helper:
            response = self._get("/api/v2/station-execution/items?active_only=false")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "items": rows, "count": 1})
        helper.assert_called_once_with(self.config, active_only=False)

    def test_get_item_normalizes_item_code_and_returns_item(self) -> None:
        row = {"item_code": "PACKAGED_PRODUCT", "item_name": "Packaged Product"}

        with patch.object(main_module.mesql_v2, "get_item_by_code", return_value=row) as helper:
            response = self._get("/api/v2/station-execution/items/ packaged_product ")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "item": row})
        helper.assert_called_once_with(self.config, "PACKAGED_PRODUCT")

    def test_get_missing_item_returns_404(self) -> None:
        with patch.object(main_module.mesql_v2, "get_item_by_code", return_value=None) as helper:
            response = self._get("/api/v2/station-execution/items/does_not_exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "ITEM_NOT_FOUND")
        helper.assert_called_once_with(self.config, "DOES_NOT_EXIST")

    def test_list_routes_passes_active_only_and_item_code(self) -> None:
        rows = [{"route_code": "ROUTE_BOX_PACKAGING_V1", "item_code": "PACKAGED_PRODUCT"}]

        with patch.object(main_module.mesql_v2, "list_process_routes", return_value=rows) as helper:
            response = self._get(
                "/api/v2/station-execution/routes?active_only=false&item_code= packaged_product "
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "routes": rows, "count": 1})
        helper.assert_called_once_with(self.config, active_only=False, item_code="PACKAGED_PRODUCT")

    def test_get_route_uses_version_default_1(self) -> None:
        row = {"route_code": "ROUTE_BOX_PACKAGING_V1", "version": 1}

        with patch.object(main_module.mesql_v2, "get_process_route", return_value=row) as helper:
            response = self._get("/api/v2/station-execution/routes/route_box_packaging_v1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "route": row})
        helper.assert_called_once_with(self.config, "ROUTE_BOX_PACKAGING_V1", version=1)

    def test_get_route_rejects_invalid_version(self) -> None:
        with patch.object(main_module.mesql_v2, "get_process_route", return_value=None) as helper:
            response = self._get("/api/v2/station-execution/routes/ROUTE_BOX_PACKAGING_V1?version=0")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "INVALID_QUERY_PARAM")
        helper.assert_not_called()

    def test_get_missing_route_returns_404(self) -> None:
        with patch.object(main_module.mesql_v2, "get_process_route", return_value=None) as helper:
            response = self._get("/api/v2/station-execution/routes/does_not_exist?version=2")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "PROCESS_ROUTE_NOT_FOUND")
        helper.assert_called_once_with(self.config, "DOES_NOT_EXIST", version=2)

    def test_list_route_operations_passes_route_code_station_code_and_active_only(self) -> None:
        rows = [{"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10", "station_code": "ASSEMBLY_01"}]

        with patch.object(main_module.mesql_v2, "list_route_operations", return_value=rows) as helper:
            response = self._get(
                "/api/v2/station-execution/route-operations"
                "?active_only=false&route_code=route_box_packaging_v1&station_code=assembly_01"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "route_operations": rows, "count": 1})
        helper.assert_called_once_with(
            self.config,
            route_code="ROUTE_BOX_PACKAGING_V1",
            station_code="ASSEMBLY_01",
            active_only=False,
        )

    def test_get_route_operation_returns_route_operation(self) -> None:
        row = {"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10"}

        with patch.object(main_module.mesql_v2, "get_route_operation", return_value=row) as helper:
            response = self._get("/api/v2/station-execution/route-operations/route_box_packaging_v1_op10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "route_operation": row})
        helper.assert_called_once_with(self.config, "ROUTE_BOX_PACKAGING_V1_OP10")

    def test_get_missing_route_operation_returns_404(self) -> None:
        with patch.object(main_module.mesql_v2, "get_route_operation", return_value=None) as helper:
            response = self._get("/api/v2/station-execution/route-operations/does_not_exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "ROUTE_OPERATION_NOT_FOUND")
        helper.assert_called_once_with(self.config, "DOES_NOT_EXIST")

    def test_station_event_sources_endpoint_returns_station_code_event_sources_and_count(self) -> None:
        rows = [{"station_code": "ASSEMBLY_01", "source_code": "ASSEMBLY_START_BUTTON"}]

        with patch.object(main_module.mesql_v2, "list_station_event_sources", return_value=rows) as helper:
            response = self._get("/api/v2/stations/assembly_01/execution-event-sources?active_only=false")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "station_code": "ASSEMBLY_01", "event_sources": rows, "count": 1},
        )
        helper.assert_called_once_with(self.config, "ASSEMBLY_01", active_only=False)

    def test_route_operation_steps_checks_operation_existence_and_returns_steps(self) -> None:
        route_operation = {"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10"}
        steps = [{"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10", "step_code": "START"}]

        with (
            patch.object(main_module.mesql_v2, "get_route_operation", return_value=route_operation) as get_helper,
            patch.object(main_module.mesql_v2, "list_operation_steps", return_value=steps) as list_helper,
        ):
            response = self._get(
                "/api/v2/station-execution/route-operations/route_box_packaging_v1_op10/steps"
                "?active_only=false"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10",
                "steps": steps,
                "count": 1,
            },
        )
        get_helper.assert_called_once_with(self.config, "ROUTE_BOX_PACKAGING_V1_OP10")
        list_helper.assert_called_once_with(
            self.config,
            "ROUTE_BOX_PACKAGING_V1_OP10",
            active_only=False,
        )

    def test_route_operation_steps_returns_404_when_operation_missing(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "get_route_operation", return_value=None) as get_helper,
            patch.object(main_module.mesql_v2, "list_operation_steps", return_value=[]) as list_helper,
        ):
            response = self._get("/api/v2/station-execution/route-operations/does_not_exist/steps")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "ROUTE_OPERATION_NOT_FOUND")
        get_helper.assert_called_once_with(self.config, "DOES_NOT_EXIST")
        list_helper.assert_not_called()

    def test_route_operation_config_endpoint_returns_aggregate_config(self) -> None:
        config = {"route_operation": {"route_operation_id": "ROUTE_BOX_PACKAGING_V1_OP10"}, "steps": []}

        with patch.object(main_module.mesql_v2, "get_route_operation_config", return_value=config) as helper:
            response = self._get("/api/v2/station-execution/route-operations/route_box_packaging_v1_op10/config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "config": config})
        helper.assert_called_once_with(self.config, "ROUTE_BOX_PACKAGING_V1_OP10")

    def test_route_operation_config_missing_returns_404(self) -> None:
        with patch.object(main_module.mesql_v2, "get_route_operation_config", return_value=None) as helper:
            response = self._get("/api/v2/station-execution/route-operations/does_not_exist/config")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "ROUTE_OPERATION_NOT_FOUND")
        helper.assert_called_once_with(self.config, "DOES_NOT_EXIST")

    def test_station_execution_config_endpoint_returns_aggregate_config(self) -> None:
        config = {
            "station_code": "ASSEMBLY_01",
            "route_operations": [],
            "event_sources": [],
            "validation": {},
        }

        with patch.object(main_module.mesql_v2, "get_station_execution_config", return_value=config) as helper:
            response = self._get("/api/v2/stations/assembly_01/execution-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "config": config})
        helper.assert_called_once_with(self.config, "ASSEMBLY_01")

    def test_mesql_v2_error_database_disabled_maps_to_503(self) -> None:
        error = main_module.mesql_v2.MesqlV2Error("DATABASE_DISABLED", status_code=503)

        with patch.object(main_module.mesql_v2, "list_items", side_effect=error) as helper:
            response = self._get("/api/v2/station-execution/items")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "DATABASE_DISABLED")
        helper.assert_called_once_with(self.config, active_only=True)

    def test_unexpected_exception_maps_to_500_internal_error(self) -> None:
        with patch.object(main_module.mesql_v2, "list_items", side_effect=RuntimeError("boom")) as helper:
            response = self._get("/api/v2/station-execution/items")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "INTERNAL_ERROR")
        helper.assert_called_once_with(self.config, active_only=True)

    def test_station_execution_config_api_uses_helpers_not_raw_database_connection(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "list_items", return_value=[]) as helper,
            patch.object(main_module.mesql_v2, "database_connection", side_effect=AssertionError("raw DB access")) as raw_db,
        ):
            response = self._get("/api/v2/station-execution/items")

        self.assertEqual(response.status_code, 200)
        helper.assert_called_once_with(self.config, active_only=True)
        raw_db.assert_not_called()

    def test_station_execution_config_api_does_not_call_lifecycle_or_mesql_sync_helpers(self) -> None:
        config = {
            "station_code": "ASSEMBLY_01",
            "route_operations": [],
            "event_sources": [],
            "validation": {},
        }

        with (
            patch.object(main_module.mesql_v2, "get_station_execution_config", return_value=config),
            patch.object(main_module.mesql_v2, "start_operation_v2") as start_operation,
            patch.object(main_module.mesql_v2, "complete_operation_v2") as complete_operation,
            patch.object(main_module.mesql_v2, "upsert_mesql_queue_items") as upsert_queue,
            patch("mes_web.integration.mesql_pull.pull_mesql_station_queues") as pull_mesql,
            patch("mes_web.integration.mesql_push.push_mesql_outbox") as push_mesql,
        ):
            response = self._get("/api/v2/stations/ASSEMBLY_01/execution-config")

        self.assertEqual(response.status_code, 200)
        start_operation.assert_not_called()
        complete_operation.assert_not_called()
        upsert_queue.assert_not_called()
        pull_mesql.assert_not_called()
        push_mesql.assert_not_called()


if __name__ == "__main__":
    unittest.main()
