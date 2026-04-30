from __future__ import annotations

import os
import shutil
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    import mes_web.app as app_module
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - optional test dependency
    TestClient = None
    app_module = None

from mes_web.config import AppConfig
from mes_web.ferp_export import build_ferp_export_package, write_ferp_export_package
from mes_web.ferp_labels import (
    default_ferp_labels_path,
    get_labels_for_object,
    validate_label_payload,
)
from mes_web.ferp_xls_export import (
    read_ferp_xls_rows,
    write_seeded_ferp_examples,
    write_work_order_xls_export,
)
from mes_web.oee_state import OeeRuntimeStateManager, default_runtime_state
from mes_web.runtime import SnapshotHub
from mes_web.store import DashboardStore


@contextmanager
def _temporary_directory():
    root = Path(__file__).resolve().parents[1] / ".tmp-tests"
    root.mkdir(exist_ok=True)
    path = root / f"ferp-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _FakeExcelSink:
    def record_work_order_state(self, state, received_at: str) -> None:
        return

    def record_kiosk_event(self, event_type: str, payload: dict[str, object], received_at: str) -> None:
        return

    def record_quality_override(self, item_id: str, classification: str, received_at: str) -> None:
        return

    def record_system_oee_log(self, raw_line: str, received_at: str) -> None:
        return

    def record_local_counts_reset(self, received_at: str) -> None:
        return


class _FakeRuntimeService:
    def __init__(self, manager: OeeRuntimeStateManager) -> None:
        self.oee_manager = manager
        self.excel_sink = _FakeExcelSink()

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return


class FerpLabelRegistryTests(unittest.TestCase):
    def test_excel_registry_reads_required_labels(self) -> None:
        path = default_ferp_labels_path()
        self.assertTrue(path.exists(), f"FERP label workbook is missing: {path}")

        self.assertIn("lblMMFB0_NUMBER", get_labels_for_object("mym4004", path))
        self.assertIn("lblMMFB0_QTY", get_labels_for_object("mym4008", path))
        self.assertIn("lblMMV00_DATE", get_labels_for_object("mym2008", path))
        self.assertIn("lblMWR00_CODE", get_labels_for_object("mym2010", path))
        transfer_labels = get_labels_for_object("mym2056", path)
        self.assertIn("lblMWR00_CODE_O", transfer_labels)
        self.assertIn("lblMWR00_CODE_I", transfer_labels)

    def test_validate_label_payload_returns_warning_shape(self) -> None:
        validation = validate_label_payload(
            "mym4004",
            {
                "lblMMFB0_NUMBER": "WO-FERP-001",
                "lblMMFB0_QTY": 3,
                "lblUNKNOWN": "x",
            },
        )

        self.assertFalse(validation["valid"])
        self.assertIn("lblMMFB0_NUMBER", validation["known_labels"])
        self.assertIn("lblUNKNOWN", validation["unknown_labels"])
        self.assertEqual(validation["missing_required_labels"], [])
        self.assertTrue(validation["warnings"])

    def test_missing_registry_returns_controlled_validation_error(self) -> None:
        validation = validate_label_payload(
            "mym4004",
            {"lblMMFB0_NUMBER": "WO-FERP-001"},
            Path("missing-ferp-labels.xlsx"),
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(validation["warnings"][0].startswith("FERP_LABELS_XLSX_NOT_FOUND"))


class FerpImportTests(unittest.TestCase):
    def test_ferp_import_folder_sample_file_contains_visible_test_order(self) -> None:
        source_path = Path(__file__).resolve().parents[1] / "mes_web" / "ferp_import" / "ferp_work_orders.json"
        self.assertTrue(source_path.exists(), f"FERP import sample is missing: {source_path}")
        with _temporary_directory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")

            result = manager.import_work_orders_from_file(
                source_path,
                now=datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc),
            )

            order = result["state"]["workOrders"]["ordersById"]["TEST-FERP-001"]
            self.assertEqual(order["status"], "queued")
            self.assertEqual(order["quantity"], 1)
            self.assertEqual(order["cycleTimeSec"], 15.0)
            self.assertEqual(order["ferpObject"], "mym4004")

    def test_label_first_work_order_import_normalizes_runtime_state(self) -> None:
        with _temporary_directory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            result = manager.import_work_orders(
                [
                    {
                        "ferp_object": "mym4004",
                        "ferp_screen": "Is Emirleri",
                        "ferp_labels": {
                            "lblMMFB0_NUMBER": "WO-FERP-001",
                            "lblMMFB0_QTY": 3,
                            "lblMMFB0_DATE": "2026-04-27",
                            "lblMTM00_CODE": "FIN-RED",
                            "lblMTM00_NAME": "Finished Red",
                            "lblMUNT0_CODE": "AD",
                            "lblMMFB4_TIME": 15,
                            "lblUNKNOWN": "kept-as-warning",
                        },
                    }
                ],
                now=datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc),
            )

            order = result["state"]["workOrders"]["ordersById"]["WO-FERP-001"]
            self.assertEqual(order["orderId"], "WO-FERP-001")
            self.assertEqual(order["quantity"], 3)
            self.assertEqual(order["cycleTimeSec"], 15.0)
            self.assertEqual(order["ferpObject"], "mym4004")
            self.assertEqual(order["ferpLabels"]["lblMMFB0_NUMBER"], "WO-FERP-001")
            self.assertIn("lblUNKNOWN", result["warnings"][0]["unknown_labels"])

    def test_clean_label_import_clears_previous_ferp_warnings(self) -> None:
        with _temporary_directory() as temp_dir:
            manager = OeeRuntimeStateManager(Path(temp_dir) / "oee_runtime_state.json")
            manager.import_work_orders(
                [
                    {
                        "ferp_object": "mym4004",
                        "ferp_screen": "Is Emirleri",
                        "ferp_labels": {
                            "lblMMFB0_NUMBER": "WO-FERP-WARN",
                            "lblMMFB0_QTY": 2,
                            "lblUNKNOWN": "x",
                        },
                    }
                ],
                now=datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc),
            )

            result = manager.import_work_orders(
                [
                    {
                        "ferp_object": "mym4004",
                        "ferp_screen": "Is Emirleri",
                        "ferp_labels": {
                            "lblMMFB0_NUMBER": "WO-FERP-WARN",
                            "lblMMFB0_QTY": 2,
                        },
                    }
                ],
                now=datetime(2026, 4, 27, 9, 5, tzinfo=timezone.utc),
            )

            order = result["state"]["workOrders"]["ordersById"]["WO-FERP-WARN"]
            self.assertEqual(order["ferpWarnings"], [])
            self.assertEqual(result["warnings"], [])


class FerpExportTests(unittest.TestCase):
    def _sample_order_and_items(self) -> tuple[dict[str, object], list[dict[str, object]]]:
        order = {
            "orderId": "WO/FERP:EXPORT",
            "date": "2026-04-27",
            "completedAt": "2026-04-27T09:05:00+00:00",
            "quantity": 3,
            "stockCode": "FIN-RED",
            "stockName": "Finished Red",
            "unit": "AD",
            "cycleTimeSec": 15.0,
            "ferpObject": "mym4004",
            "ferpScreen": "Is Emirleri",
        }
        items = [
            {
                "item_id": "ITEM-1",
                "work_order_id": "WO/FERP:EXPORT",
                "sensor_at": "2026-04-27T09:00:01+00:00",
                "vision_observed_at": "2026-04-27T09:00:02+00:00",
                "completed_at": "2026-04-27T09:00:03+00:00",
                "classification": "GOOD",
                "stock_code": "FIN-RED",
            },
            {
                "item_id": "ITEM-2",
                "work_order_id": "WO/FERP:EXPORT",
                "sensor_at": "2026-04-27T09:00:04+00:00",
                "vision_observed_at": "2026-04-27T09:00:05+00:00",
                "completed_at": "2026-04-27T09:00:06+00:00",
                "classification": "REWORK",
                "stock_code": "FIN-RED",
            },
            {
                "item_id": "ITEM-3",
                "work_order_id": "WO/FERP:EXPORT",
                "sensor_at": "2026-04-27T09:00:07+00:00",
                "vision_observed_at": "2026-04-27T09:00:08+00:00",
                "completed_at": "2026-04-27T09:00:09+00:00",
                "classification": "SCRAP",
                "stock_code": "FIN-RED",
            },
        ]
        return order, items

    def test_export_package_contains_station_flow_and_quality_lines(self) -> None:
        order, items = self._sample_order_and_items()

        package = build_ferp_export_package(
            {"itemsById": {str(item["item_id"]): item for item in items}},
            order,
            items,
            module_id="konveyor_main",
            created_at=datetime(2026, 4, 27, 9, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(package["schema"], "ferp_mes_export.v1")
        self.assertEqual(package["quality_summary"]["GOOD"], 1)
        self.assertEqual(package["quality_summary"]["REWORK"], 1)
        self.assertEqual(package["quality_summary"]["SCRAP"], 1)
        station_ids = {row["station_id"] for row in package["station_flow"]}
        self.assertEqual(station_ids, {"SENSOR-01", "VISION-01", "ROBOT-01"})
        document_objects = {row["ferp_object"] for row in package["ferp_documents"]}
        self.assertEqual(document_objects, {"mym2008", "mym2010", "mym2056"})
        entry_doc = next(row for row in package["ferp_documents"] if row["ferp_object"] == "mym2008")
        line_classes = {row["classification"] for row in entry_doc["lines"]}
        self.assertIn("GOOD", line_classes)
        self.assertIn("REWORK", line_classes)
        self.assertIn("SCRAP", line_classes)
        movement_codes = {
            line["ferp_labels"]["lblMTM00_CODE"]
            for document in package["ferp_documents"]
            for line in document["lines"]
        }
        self.assertEqual(movement_codes, {"FIN-RED"})
        self.assertFalse(any(warning.startswith("FERP_UNKNOWN_LABELS") for warning in package["warnings"]))

    def test_export_material_lines_use_order_stock_code_instead_of_detected_color(self) -> None:
        order, items = self._sample_order_and_items()
        for item in items:
            item.pop("stock_code", None)
            item["color"] = "red"
            item["final_color"] = "red"

        package = build_ferp_export_package(
            {},
            order,
            items,
            created_at=datetime(2026, 4, 27, 9, 10, tzinfo=timezone.utc),
        )

        movement_codes = [
            line["ferp_labels"]["lblMTM00_CODE"]
            for document in package["ferp_documents"]
            for line in document["lines"]
        ]
        self.assertTrue(movement_codes)
        self.assertTrue(all(code == "FIN-RED" for code in movement_codes))

    def test_export_write_does_not_overwrite_existing_file(self) -> None:
        order, items = self._sample_order_and_items()
        package = build_ferp_export_package(
            {},
            order,
            items,
            created_at=datetime(2026, 4, 27, 9, 10, tzinfo=timezone.utc),
        )

        with _temporary_directory() as temp_dir:
            first_path = write_ferp_export_package(package, temp_dir)
            second_path = write_ferp_export_package(package, temp_dir)

            self.assertTrue(first_path.exists())
            self.assertTrue(second_path.exists())
            self.assertNotEqual(first_path, second_path)
            self.assertNotIn(":", first_path.name)
            self.assertNotIn("/", first_path.name)

    def test_export_accepts_item_list_without_work_order_ids(self) -> None:
        order, items = self._sample_order_and_items()
        item_list = [{key: value for key, value in item.items() if key != "work_order_id"} for item in items]

        package = build_ferp_export_package(
            {},
            order,
            item_list,
            created_at=datetime(2026, 4, 27, 9, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(package["quality_summary"]["TOTAL"], 3)
        self.assertEqual(len(package["station_flow"]), 9)

    def test_export_uses_order_quantity_when_item_details_are_missing(self) -> None:
        order, _items = self._sample_order_and_items()
        order["completedQty"] = 3

        package = build_ferp_export_package(
            {},
            order,
            [],
            created_at=datetime(2026, 4, 27, 9, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(package["quality_summary"]["GOOD"], 3)
        entry_doc = next(row for row in package["ferp_documents"] if row["ferp_object"] == "mym2008")
        good_line = next(row for row in entry_doc["lines"] if row["classification"] == "GOOD")
        self.assertEqual(good_line["qty"], 3)


class FerpXlsExportTests(unittest.TestCase):
    def _ferp_xls_dir(self) -> Path:
        return Path(__file__).resolve().parents[1] / "FERP_XLS"

    def test_seeded_examples_include_conveyor_master_data_without_touching_sources(self) -> None:
        source_dir = self._ferp_xls_dir()
        source_bytes = {path.name: path.read_bytes() for path in source_dir.glob("*.xls")}

        with _temporary_directory() as temp_dir:
            output_dir = Path(temp_dir) / "examples"
            files = write_seeded_ferp_examples(source_dir, output_dir)

            self.assertEqual(len(files), 4)
            stock_rows = read_ferp_xls_rows(output_dir / "FERP_STOK_KARTI.xls")
            stock_codes = {row[1] for row in stock_rows[1:] if len(row) > 2}
            stock_names = {row[2] for row in stock_rows[1:] if len(row) > 2}
            self.assertIn("BOX-RED", stock_codes)
            self.assertIn("BOX-BLUE", stock_codes)
            self.assertIn("BOX-YEL", stock_codes)
            self.assertIn("Kırmızı Kutu", stock_names)
            self.assertIn("Sarı Kutu", stock_names)

            work_center_file = next(path for path in files if "MERKEZ" in path.name)
            work_center_rows = read_ferp_xls_rows(work_center_file)
            self.assertTrue(any(row[:2] == ["KNV-01", "Mini konveyör iş merkezi"] for row in work_center_rows[1:]))

            work_station_file = next(path for path in files if "STASYONU" in path.name)
            work_station_rows = read_ferp_xls_rows(work_station_file)
            self.assertTrue(any(row[:3] == ["KNV-01", "SNS-01", "Sensör ölçüm istasyonu"] for row in work_station_rows[1:]))
            self.assertTrue(any(row[:3] == ["KNV-01", "ROB-01", "Robot kol istasyonu"] for row in work_station_rows[1:]))

            operation_rows = read_ferp_xls_rows(output_dir / "FERP_OPERASYON_TANIMLARI.xls")
            operation_codes = {row[0] for row in operation_rows[1:] if row}
            self.assertIn("SNS-MSR", operation_codes)
            self.assertIn("ROB-MOV", operation_codes)

        for path in source_dir.glob("*.xls"):
            self.assertEqual(path.read_bytes(), source_bytes[path.name], path.name)

    def test_work_order_xls_export_writes_sensor_and_robot_rows(self) -> None:
        order = {
            "orderId": "WO-XLS-001",
            "date": "2026-04-29",
            "completedAt": "2026-04-29T10:05:00+03:00",
            "quantity": 3,
            "completedQty": 3,
            "stockCode": "BOX-RED",
            "stockName": "Kırmızı Kutu",
            "unit": "ADET",
            "cycleTimeSec": 15,
            "description": "Kırmızı kutu test üretimi",
        }

        with _temporary_directory() as temp_dir:
            export = write_work_order_xls_export(
                order,
                source_dir=self._ferp_xls_dir(),
                pending_dir=Path(temp_dir) / "pending",
                created_at=datetime(2026, 4, 29, 7, 5, tzinfo=timezone.utc),
            )

            self.assertTrue(export.directory.exists())
            self.assertEqual(len(export.files), 1)
            rows = read_ferp_xls_rows(export.files[0])
            headers = rows[0]
            data_rows = rows[1:]
            self.assertEqual(len(data_rows), 2)
            order_no_idx = headers.index("İş Emri No")
            stock_code_idx = headers.index("Ürün Kodu")
            station_idx = headers.index("İş İstasyonu")
            method_idx = headers.index("Metod Kodu")
            status_idx = headers.index("Statü")
            completed_idx = headers.index("Kapanan Miktar")

            self.assertEqual([row[order_no_idx] for row in data_rows], ["WO-XLS-001", "WO-XLS-001"])
            self.assertEqual([row[stock_code_idx] for row in data_rows], ["BOX-RED", "BOX-RED"])
            self.assertEqual([row[station_idx] for row in data_rows], ["SNS-01", "ROB-01"])
            self.assertEqual([row[method_idx] for row in data_rows], ["SNS-MSR", "ROB-MOV"])
            self.assertEqual([row[status_idx] for row in data_rows], ["TAMAMLANDI", "TAMAMLANDI"])
            self.assertEqual([row[completed_idx] for row in data_rows], ["3", "3"])


class FerpAcceptActiveEndpointTests(unittest.TestCase):
    def _build_client(self):
        if TestClient is None or app_module is None:
            self.skipTest("fastapi is not installed")
        temp_context = _temporary_directory()
        temp_dir = temp_context.__enter__()
        self.addCleanup(temp_context.__exit__, None, None, None)
        root_dir = Path(__file__).resolve().parents[1]
        state_path = Path(temp_dir) / "oee_runtime_state.json"
        export_dir = Path(temp_dir) / "ferp_exports" / "pending"
        with patch.dict(
            os.environ,
            {
                "MES_WEB_OEE_RUNTIME_STATE_PATH": str(state_path),
                "MES_WEB_FERP_EXPORT_PENDING_DIR": str(export_dir),
                "MES_WEB_FERP_EXPORT_EXAMPLES_DIR": str(Path(temp_dir) / "ferp_exports" / "examples"),
                "MES_WEB_FERP_XLS_DIR": str(root_dir / "FERP_XLS"),
                "MES_WEB_FERP_LABELS_PATH": str(default_ferp_labels_path(root_dir)),
                "MES_WEB_EXCEL_WORKBOOK_PATH": str(Path(temp_dir) / "mes.xlsx"),
            },
            clear=False,
        ):
            config = AppConfig.from_env()
        manager = OeeRuntimeStateManager(config.oee_runtime_state_path)
        manager.write_state(default_runtime_state())
        store = DashboardStore(config)
        store.refresh_oee_runtime_state(config.module_id, force=True)
        hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
        runtime_service = _FakeRuntimeService(manager)
        patches = [
            patch.object(app_module, "config", config),
            patch.object(app_module, "store", store),
            patch.object(app_module, "hub", hub),
            patch.object(app_module, "runtime_service", runtime_service),
            patch.object(app_module, "oee_state_manager", manager),
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        client = TestClient(app_module.create_app())
        self.addCleanup(client.close)
        return client, config, manager

    def test_accept_active_response_adds_pending_ferp_export(self) -> None:
        client, config, manager = self._build_client()
        order_id = "WO-FERP-ENDPOINT"
        manager.import_work_orders(
            [
                {
                    "order_id": order_id,
                    "qty": 1,
                    "stock_code": "BOX-RED",
                    "stock_name": "Kırmızı Kutu",
                    "product_color": "red",
                    "unit": "ADET",
                    "cycleTimeSec": 15,
                }
            ],
            now=datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc),
        )
        manager.start_work_order(order_id, operator_code="OP-001", now=datetime(2026, 4, 27, 9, 1, tzinfo=timezone.utc))
        manager.apply_mega_log(
            "MEGA|AUTO|QUEUE=ENQ|ITEM_ID=ITEM-1|MEASURE_ID=1|COLOR=KIRMIZI|DECISION_SOURCE=CORE_STABLE|TRAVEL_MS=4500|PENDING=1",
            "2026-04-27T09:02:00Z",
        )
        manager.apply_mega_log(
            "MEGA|ROBOT|EVENT=RELEASED|ITEM_ID=ITEM-1|MEASURE_ID=1|TRIGGER=TIMER",
            "2026-04-27T09:02:10Z",
        )
        prepared_state = manager.read_state()
        self.assertEqual(prepared_state["workOrders"]["ordersById"][order_id]["status"], "pending_approval")

        response = client.post(f"/api/modules/{config.module_id}/work-orders/accept-active")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["order_id"], order_id)
        self.assertEqual(payload["ferp_export"]["status"], "pending")
        self.assertNotIn("file", payload["ferp_export"])
        export_files = [Path(path) for path in payload["ferp_export"]["files"]]
        self.assertTrue(export_files)
        self.assertTrue(all(path.exists() for path in export_files))
        self.assertTrue(all(path.suffix == ".xls" for path in export_files))
        self.assertTrue(all(Path(path).exists() for path in payload["ferp_export"]["example_files"]))


if __name__ == "__main__":
    unittest.main()
