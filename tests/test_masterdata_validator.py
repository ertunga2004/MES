from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.excel_runtime import COLOR_IDS, DECISION_SOURCE_IDS, EVENT_TYPE_IDS, MEGA_STATE_IDS, SOURCE_IDS
from mes_web.masterdata import (
    _MASTERDATA_VALIDATION_LOG_CACHE,
    DEFAULT_OPERATORS,
    load_kiosk_masterdata,
)
from mes_web.masterdata_validator import (
    STATUS_ERROR_CANDIDATE,
    STATUS_OK,
    STATUS_SKIPPED,
    STATUS_WARNING,
    validate_masterdata_source,
)


class MasterdataValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        _MASTERDATA_VALIDATION_LOG_CACHE["key"] = None

    def _require_workbook(self):
        try:
            from openpyxl import Workbook
        except ModuleNotFoundError:
            self.skipTest("openpyxl is not installed")
        return Workbook

    def _write_masterdata_workbook(
        self,
        path: Path,
        *,
        blocks: dict[str, tuple[list[str], list[dict[str, str]]]] | None = None,
        sheet_name: str = "0_Tanimlamalar",
    ) -> None:
        Workbook = self._require_workbook()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        current_col = 1
        for block_name, (headers, rows) in (blocks or self._full_blocks()).items():
            sheet.cell(1, current_col, block_name)
            for offset, header in enumerate(headers):
                sheet.cell(2, current_col + offset, header)
            for row_index, row in enumerate(rows, start=3):
                for offset, header in enumerate(headers):
                    sheet.cell(row_index, current_col + offset, row.get(header, ""))
            current_col += len(headers) + 1
        workbook.save(path)
        if hasattr(workbook, "close"):
            workbook.close()

    def _config_for_path(self, workbook_path: Path, template_path: Path | None = None) -> AppConfig:
        env = {"MES_WEB_EXCEL_WORKBOOK_PATH": str(workbook_path)}
        if template_path is not None:
            env["MES_WEB_EXCEL_TEMPLATE_PATH"] = str(template_path)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, env, clear=False).start()
        return AppConfig()

    def _full_blocks(self) -> dict[str, tuple[list[str], list[dict[str, str]]]]:
        return {
            "operatorler": (
                ["operator_id", "operator_code", "operator_name"],
                [{"operator_id": "1", "operator_code": "OP-001", "operator_name": "Atanmadi"}],
            ),
            "istasyonlar": (
                ["station_id", "station_code", "station_name_tr", "line_id"],
                [{"station_id": "4", "station_code": "KSK-01", "station_name_tr": "Tablet Kiosk", "line_id": "1"}],
            ),
            "hatlar": (
                ["line_id", "line_code", "line_name_tr"],
                [{"line_id": "1", "line_code": "LINE-1", "line_name_tr": "Konveyor"}],
            ),
            "urunler": (
                ["product_id", "product_code", "product_name_tr"],
                [{"product_id": "P-1", "product_code": "BOX-RED", "product_name_tr": "Kirmizi Kutu"}],
            ),
            "ariza_tipleri": (
                ["fault_type_id", "fault_type_code", "fault_category", "fault_reason_tr"],
                [{"fault_type_id": "1", "fault_type_code": "robot_arm_jam", "fault_category": "MEKANIK", "fault_reason_tr": "Robot Kol Sikismasi"}],
            ),
            "vardiyalar": (
                ["shift_id", "shift_code", "shift_name_tr"],
                [{"shift_id": "1", "shift_code": "SHIFT-A", "shift_name_tr": "Gunduz"}],
            ),
            "renkler": (
                ["color_code"],
                [{"color_code": code} for code in sorted(COLOR_IDS)],
            ),
            "kaynaklar": (
                ["source_code"],
                [{"source_code": code} for code in sorted(SOURCE_IDS)],
            ),
            "olay_tipleri": (
                ["event_type_code"],
                [{"event_type_code": code} for code in sorted(EVENT_TYPE_IDS)],
            ),
            "karar_kaynaklari": (
                ["decision_source_code"],
                [{"decision_source_code": code} for code in sorted(DECISION_SOURCE_IDS)],
            ),
            "mega_durumlari": (
                ["mega_state_code"],
                [{"mega_state_code": code} for code in sorted(MEGA_STATE_IDS)],
            ),
            "bakim_adimlari": (
                ["phase_code", "step_code", "step_label", "required_flag"],
                [{"phase_code": "opening", "step_code": "opening_safety", "step_label": "Guvenlik", "required_flag": "1"}],
            ),
        }

    def test_full_masterdata_workbook_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_masterdata_workbook(workbook_path)
            config = self._config_for_path(workbook_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_OK)
        self.assertEqual(report["missing_blocks"], [])
        self.assertEqual(report["missing_columns_by_block"], {})
        self.assertEqual(report["empty_blocks"], [])
        self.assertEqual(report["fallback_used"], [])

    def test_missing_masterdata_sheet_warns_and_keeps_fallback_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_masterdata_workbook(workbook_path, sheet_name="Other")
            config = self._config_for_path(workbook_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertIn("MISSING_SHEET: 0_Tanimlamalar", report["warnings"])
        self.assertIn("operators", report["fallback_used"])
        self.assertIn("operatorler", report["missing_blocks"])

    def test_missing_block_warns_without_blocking(self) -> None:
        blocks = self._full_blocks()
        blocks.pop("operatorler")
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_masterdata_workbook(workbook_path, blocks=blocks)
            config = self._config_for_path(workbook_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertIn("operatorler", report["missing_blocks"])
        self.assertIn("operators", report["fallback_used"])
        self.assertTrue(any("MISSING_MASTERDATA_BLOCK: operatorler" in warning for warning in report["warnings"]))

    def test_empty_block_warns_and_reports_fallback(self) -> None:
        blocks = self._full_blocks()
        blocks["operatorler"] = (["operator_id", "operator_code", "operator_name"], [])
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_masterdata_workbook(workbook_path, blocks=blocks)
            config = self._config_for_path(workbook_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertIn("operatorler", report["empty_blocks"])
        self.assertIn("operators", report["fallback_used"])
        self.assertTrue(any("EMPTY_MASTERDATA_BLOCK: operatorler" in warning for warning in report["warnings"]))

    def test_lookup_diff_is_reported_as_warning(self) -> None:
        blocks = self._full_blocks()
        blocks["renkler"] = (["color_code"], [{"color_code": "red"}])
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_masterdata_workbook(workbook_path, blocks=blocks)
            config = self._config_for_path(workbook_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertTrue(any("LOOKUP_MISSING_IN_MASTERDATA: renkler" in warning for warning in report["lookup_diff_warnings"]))

    def test_missing_masterdata_source_returns_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "missing.xlsx"
            template_path = Path(temp_dir) / "missing-template.xlsx"
            config = self._config_for_path(workbook_path, template_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_SKIPPED)
        self.assertIn("MASTERDATA_SOURCE_NOT_FOUND", report["warnings"])
        self.assertIn("operators", report["fallback_used"])

    def test_invalid_workbook_returns_error_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "broken.xlsx"
            workbook_path.write_text("not-a-real-xlsx", encoding="utf-8")
            config = self._config_for_path(workbook_path)

            report = validate_masterdata_source(config)

        self.assertEqual(report["status"], STATUS_ERROR_CANDIDATE)
        self.assertTrue(report["errors"])
        self.assertIn("MASTERDATA_INVALID_OR_CORRUPT", report["errors"][0])

    def test_masterdata_validation_flag_defaults_disabled(self) -> None:
        self.assertFalse(AppConfig().masterdata_validation_enabled)
        with patch.dict(os.environ, {"MES_MASTERDATA_VALIDATION_ENABLED": "true"}, clear=False):
            self.assertTrue(AppConfig.from_env().masterdata_validation_enabled)

    def test_load_kiosk_masterdata_does_not_call_validator_when_flag_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "missing.xlsx"
            config = AppConfig(masterdata_validation_enabled=False)
            with (
                patch.dict(os.environ, {"MES_WEB_EXCEL_WORKBOOK_PATH": str(workbook_path), "MES_WEB_EXCEL_TEMPLATE_PATH": str(Path(temp_dir) / "missing-template.xlsx")}, clear=False),
                patch("mes_web.masterdata_validator.validate_masterdata_source") as validator,
            ):
                catalog = load_kiosk_masterdata(config)

        validator.assert_not_called()
        self.assertEqual(catalog["operators"], DEFAULT_OPERATORS)

    def test_load_kiosk_masterdata_logs_validator_report_when_flag_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "missing.xlsx"
            config = AppConfig(masterdata_validation_enabled=True)
            with (
                patch.dict(os.environ, {"MES_WEB_EXCEL_WORKBOOK_PATH": str(workbook_path), "MES_WEB_EXCEL_TEMPLATE_PATH": str(Path(temp_dir) / "missing-template.xlsx")}, clear=False),
                patch("mes_web.masterdata_validator.validate_masterdata_source") as validator,
                patch("builtins.print") as print_mock,
            ):
                validator.return_value = {
                    "status": "warning",
                    "summary": "Masterdata validation completed with 1 warnings.",
                    "fallback_used": ["operators"],
                    "warnings": ["MISSING_MASTERDATA_BLOCK: operatorler"],
                    "errors": [],
                }
                catalog = load_kiosk_masterdata(config)

        validator.assert_called_once_with(config)
        self.assertEqual(catalog["operators"], DEFAULT_OPERATORS)
        printed = "\n".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("masterdata validation status=warning", printed)
        self.assertIn("fallback_used: operators", printed)
        self.assertIn("MISSING_MASTERDATA_BLOCK: operatorler", printed)

    def test_load_kiosk_masterdata_continues_when_validator_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "missing.xlsx"
            config = AppConfig(masterdata_validation_enabled=True)
            with (
                patch.dict(os.environ, {"MES_WEB_EXCEL_WORKBOOK_PATH": str(workbook_path), "MES_WEB_EXCEL_TEMPLATE_PATH": str(Path(temp_dir) / "missing-template.xlsx")}, clear=False),
                patch("mes_web.masterdata_validator.validate_masterdata_source", side_effect=RuntimeError("boom")),
                patch("builtins.print") as print_mock,
            ):
                catalog = load_kiosk_masterdata(config)

        self.assertEqual(catalog["operators"], DEFAULT_OPERATORS)
        printed = "\n".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertIn("masterdata validation warning: RuntimeError: boom", printed)


if __name__ == "__main__":
    unittest.main()
