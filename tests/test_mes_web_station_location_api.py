from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import mes_web.__main__ as main_module
from mes_web.config import AppConfig


class StationLocationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig(db_enabled=True)
        self.app = FastAPI()
        main_module.register_station_location_read_routes(self.app, self.config)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def _get(self, path: str, *, enabled: bool = True):
        flag_value = "true" if enabled else "false"
        with patch.dict(
            os.environ,
            {main_module.STATION_LOCATION_READ_MODEL_FEATURE_FLAG: flag_value},
            clear=False,
        ):
            return self.client.get(path)

    def test_station_location_api_disabled_returns_503(self) -> None:
        with patch.object(main_module.mesql_v2, "list_locations", return_value=[]) as helper:
            response = self._get("/api/v2/locations", enabled=False)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "STATION_LOCATION_READ_MODEL_DISABLED")
        helper.assert_not_called()

    def test_get_locations_endpoint_returns_active_locations(self) -> None:
        rows = [{"location_code": "RAW_MATERIAL", "location_type": "raw_material"}]

        with patch.object(main_module.mesql_v2, "list_locations", return_value=rows) as helper:
            response = self._get("/api/v2/locations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "data": rows, "count": 1})
        helper.assert_called_once_with(self.config, active_only=True, location_type=None)

    def test_get_locations_endpoint_filters_by_location_type(self) -> None:
        rows = [{"location_code": "BETWEEN_ASSEMBLY_PACKAGING", "location_type": "buffer"}]

        with patch.object(main_module.mesql_v2, "list_locations", return_value=rows) as helper:
            response = self._get("/api/v2/locations?active_only=false&location_type=BUFFER")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        helper.assert_called_once_with(self.config, active_only=False, location_type="buffer")

    def test_get_locations_endpoint_rejects_invalid_location_type(self) -> None:
        with patch.object(main_module.mesql_v2, "list_locations", return_value=[]) as helper:
            response = self._get("/api/v2/locations?location_type=unknown")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "INVALID_LOCATION_TYPE")
        helper.assert_not_called()

    def test_get_locations_endpoint_rejects_invalid_active_only(self) -> None:
        with patch.object(main_module.mesql_v2, "list_locations", return_value=[]) as helper:
            response = self._get("/api/v2/locations?active_only=maybe")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "INVALID_QUERY_PARAM")
        helper.assert_not_called()

    def test_get_location_endpoint_returns_location(self) -> None:
        row = {"location_code": "BETWEEN_ASSEMBLY_PACKAGING", "location_type": "buffer"}

        with patch.object(main_module.mesql_v2, "get_location_by_code", return_value=row) as helper:
            response = self._get("/api/v2/locations/between_assembly_packaging")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "data": row})
        helper.assert_called_once_with(self.config, "BETWEEN_ASSEMBLY_PACKAGING")

    def test_get_location_endpoint_returns_404_when_missing(self) -> None:
        with patch.object(main_module.mesql_v2, "get_location_by_code", return_value=None) as helper:
            response = self._get("/api/v2/locations/does_not_exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "LOCATION_NOT_FOUND")
        helper.assert_called_once_with(self.config, "DOES_NOT_EXIST")

    def test_get_station_locations_endpoint_returns_bindings(self) -> None:
        rows = [
            {
                "station_code": "PACKAGING_01",
                "role": "input",
                "location_code": "BETWEEN_ASSEMBLY_PACKAGING",
                "location": {"location_code": "BETWEEN_ASSEMBLY_PACKAGING"},
            }
        ]

        with patch.object(main_module.mesql_v2, "list_station_location_bindings", return_value=rows) as helper:
            response = self._get("/api/v2/stations/packaging_01/locations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["station_code"], "PACKAGING_01")
        self.assertEqual(response.json()["data"], rows)
        self.assertEqual(response.json()["count"], 1)
        helper.assert_called_once_with(self.config, "PACKAGING_01", active_only=True, role=None)

    def test_get_station_locations_endpoint_filters_by_role(self) -> None:
        rows = [{"station_code": "PACKAGING_01", "role": "output_good", "location_code": "FINISHED_GOODS"}]

        with patch.object(main_module.mesql_v2, "list_station_location_bindings", return_value=rows) as helper:
            response = self._get("/api/v2/stations/packaging_01/locations?active_only=false&role=OUTPUT_GOOD")

        self.assertEqual(response.status_code, 200)
        helper.assert_called_once_with(self.config, "PACKAGING_01", active_only=False, role="output_good")

    def test_get_station_locations_endpoint_rejects_invalid_role(self) -> None:
        with patch.object(main_module.mesql_v2, "list_station_location_bindings", return_value=[]) as helper:
            response = self._get("/api/v2/stations/PACKAGING_01/locations?role=unknown")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "INVALID_BINDING_ROLE")
        helper.assert_not_called()

    def test_get_station_location_context_endpoint_returns_context(self) -> None:
        context = {
            "station_code": "PACKAGING_01",
            "input_location": {"location_code": "BETWEEN_ASSEMBLY_PACKAGING"},
            "active_wip_location": {"location_code": "PACKAGING_WIP"},
            "output_good_location": {"location_code": "FINISHED_GOODS"},
            "output_scrap_location": {"location_code": "SCRAP_AREA"},
            "output_buffer_location": None,
            "missing_roles": [],
            "inactive_or_missing_locations": [],
        }

        with patch.object(main_module.mesql_v2, "get_station_location_context", return_value=context) as helper:
            response = self._get("/api/v2/stations/packaging_01/location-context")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "station_code": "PACKAGING_01", "data": context})
        helper.assert_called_once_with(self.config, "PACKAGING_01")

    def test_get_station_location_context_allows_missing_output_buffer(self) -> None:
        context = {
            "station_code": "PACKAGING_01",
            "input_location": {"location_code": "BETWEEN_ASSEMBLY_PACKAGING"},
            "active_wip_location": {"location_code": "PACKAGING_WIP"},
            "output_good_location": {"location_code": "FINISHED_GOODS"},
            "output_scrap_location": {"location_code": "SCRAP_AREA"},
            "output_buffer_location": None,
            "missing_roles": ["output_buffer"],
            "inactive_or_missing_locations": [],
        }

        with patch.object(main_module.mesql_v2, "get_station_location_context", return_value=context):
            response = self._get("/api/v2/stations/PACKAGING_01/location-context")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"]["output_buffer_location"])

    def test_station_location_api_uses_helpers_not_raw_sql(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "list_locations", return_value=[]) as helper,
            patch.object(main_module.mesql_v2, "database_connection", side_effect=AssertionError("raw DB access")) as raw_db,
        ):
            response = self._get("/api/v2/locations")

        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()
        raw_db.assert_not_called()

    def test_station_location_api_does_not_call_operation_lifecycle_helpers(self) -> None:
        context = {
            "station_code": "ASSEMBLY_01",
            "input_location": {"location_code": "RAW_MATERIAL"},
            "active_wip_location": {"location_code": "ASSEMBLY_WIP"},
            "output_good_location": {"location_code": "BETWEEN_ASSEMBLY_PACKAGING"},
            "output_scrap_location": {"location_code": "SCRAP_AREA"},
            "output_buffer_location": {"location_code": "BETWEEN_ASSEMBLY_PACKAGING"},
            "missing_roles": [],
            "inactive_or_missing_locations": [],
        }

        with (
            patch.object(main_module.mesql_v2, "get_station_location_context", return_value=context),
            patch.object(main_module.mesql_v2, "start_operation_v2") as start_operation,
            patch.object(main_module.mesql_v2, "complete_operation_v2") as complete_operation,
            patch.object(main_module.mesql_v2, "read_station_queue_v2") as read_queue,
        ):
            response = self._get("/api/v2/stations/ASSEMBLY_01/location-context")

        self.assertEqual(response.status_code, 200)
        start_operation.assert_not_called()
        complete_operation.assert_not_called()
        read_queue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
