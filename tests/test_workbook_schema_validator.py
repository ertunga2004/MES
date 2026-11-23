from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mes_web.excel_runtime import EVENT_LOG_COLUMNS, SHEET_COLUMNS
from mes_web.workbook_schema_validator import (
    EXPECTED_SHEETS,
    STATUS_ERROR_CANDIDATE,
    STATUS_OK,
    STATUS_SKIPPED,
    STATUS_WARNING,
    validate_workbook_schema,
)


class WorkbookSchemaValidatorTests(unittest.TestCase):
    def _require_workbook(self):
        try:
            from openpyxl import Workbook
        except ModuleNotFoundError:
            self.skipTest("openpyxl is not installed")
        return Workbook

    def _write_workbook(
        self,
        path: Path,
        *,
        skip_sheet: str | None = None,
        headers_by_sheet: dict[str, list[str]] | None = None,
    ) -> None:
        Workbook = self._require_workbook()
        workbook = Workbook()
        active_sheet = workbook.active
        active_sheet.title = EXPECTED_SHEETS[0]
        active_sheet.cell(1, 1, "masterdata_block")

        for sheet_name in EXPECTED_SHEETS[1:]:
            if sheet_name == skip_sheet:
                continue
            sheet = workbook.create_sheet(sheet_name)
            headers = list((headers_by_sheet or {}).get(sheet_name, SHEET_COLUMNS.get(sheet_name, [])))
            for col_index, header in enumerate(headers, start=1):
                sheet.cell(1, col_index, header)

        workbook.save(path)
        if hasattr(workbook, "close"):
            workbook.close()

    def test_full_matching_workbook_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_workbook(workbook_path)

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_OK)
        self.assertEqual(report["missing_sheets"], [])
        self.assertEqual(report["missing_columns_by_sheet"], {})
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["errors"], [])

    def test_missing_sheet_returns_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_workbook(workbook_path, skip_sheet="6_Vision")

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertIn("6_Vision", report["missing_sheets"])
        self.assertTrue(any("MISSING_SHEET: 6_Vision" in warning for warning in report["warnings"]))

    def test_missing_column_returns_warning(self) -> None:
        headers = [header for header in EVENT_LOG_COLUMNS if header != "notes"]
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_workbook(workbook_path, headers_by_sheet={"1_Olay_Logu": headers})

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertEqual(report["missing_columns_by_sheet"]["1_Olay_Logu"], ["notes"])
        self.assertTrue(any("MISSING_COLUMNS: 1_Olay_Logu: notes" in warning for warning in report["warnings"]))

    def test_extra_column_is_reported_without_warning_status(self) -> None:
        headers = list(EVENT_LOG_COLUMNS) + ["manual_extra"]
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_workbook(workbook_path, headers_by_sheet={"1_Olay_Logu": headers})

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_OK)
        self.assertEqual(report["extra_columns_by_sheet"]["1_Olay_Logu"], ["manual_extra"])
        self.assertEqual(report["warnings"], [])

    def test_column_order_mismatch_is_reported_without_blocking(self) -> None:
        headers = list(EVENT_LOG_COLUMNS)
        headers[0], headers[1] = headers[1], headers[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "mes.xlsx"
            self._write_workbook(workbook_path, headers_by_sheet={"1_Olay_Logu": headers})

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_OK)
        self.assertIn("1_Olay_Logu", report["column_order_notes"])
        self.assertEqual(report["warnings"], [])

    def test_empty_workbook_returns_warning(self) -> None:
        Workbook = self._require_workbook()
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "empty.xlsx"
            workbook = Workbook()
            workbook.save(workbook_path)
            if hasattr(workbook, "close"):
                workbook.close()

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_WARNING)
        self.assertIn("WORKBOOK_EMPTY", report["warnings"])
        self.assertIn("0_Tanimlamalar", report["missing_sheets"])

    def test_missing_file_returns_skipped_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "missing.xlsx"

            report = validate_workbook_schema(workbook_path)

        self.assertEqual(report["status"], STATUS_SKIPPED)
        self.assertIn("WORKBOOK_FILE_NOT_FOUND", report["warnings"][0])
        self.assertEqual(report["errors"], [])

    def test_invalid_workbook_returns_error_candidate_without_modifying_file(self) -> None:
        self._require_workbook()
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "broken.xlsx"
            workbook_path.write_text("not-a-real-xlsx", encoding="utf-8")

            report = validate_workbook_schema(workbook_path)

            self.assertTrue(workbook_path.exists())
            self.assertEqual(workbook_path.read_text(encoding="utf-8"), "not-a-real-xlsx")

        self.assertEqual(report["status"], STATUS_ERROR_CANDIDATE)
        self.assertTrue(report["errors"])
        self.assertIn("WORKBOOK_INVALID_OR_CORRUPT", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
