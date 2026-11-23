from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .excel_runtime import SHEET_COLUMNS


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_SKIPPED = "skipped"
STATUS_ERROR_CANDIDATE = "error_candidate"

MASTERDATA_SHEET_NAME = "0_Tanimlamalar"
EXPECTED_SHEETS = [
    MASTERDATA_SHEET_NAME,
    "1_Olay_Logu",
    "2_Olcumler",
    "3_Arizalar",
    "4_Uretim_Tamamlanan",
    "5_OEE_Anliklari",
    "6_Vision",
    "7_Is_Emirleri",
    "8_Depo_Stok",
    "9_Bakim_Kayitlari",
    "99_Raw_Logs",
]


def validate_workbook_schema(workbook_path: str | Path, *, checked_at: datetime | None = None) -> dict[str, Any]:
    """Return a read-only workbook schema validation report.

    The validator is intentionally warning-only: it never repairs the workbook,
    never writes to the template, and never raises for ordinary validation
    failures.
    """
    path = Path(workbook_path)
    report = _new_report(path, checked_at=checked_at)
    workbook: Any | None = None

    try:
        if not path.exists():
            report["status"] = STATUS_SKIPPED
            report["warnings"].append(f"WORKBOOK_FILE_NOT_FOUND: {path}")
            report["summary"] = "Workbook file not found; validation skipped."
            return report

        try:
            from openpyxl import load_workbook
            from openpyxl.utils.exceptions import InvalidFileException
        except ModuleNotFoundError:
            report["status"] = STATUS_SKIPPED
            report["warnings"].append("OPENPYXL_NOT_INSTALLED")
            report["summary"] = "openpyxl is not installed; validation skipped."
            return report

        try:
            workbook = load_workbook(path, read_only=True, data_only=False)
        except (OSError, zipfile.BadZipFile, InvalidFileException) as exc:
            report["status"] = STATUS_ERROR_CANDIDATE
            report["errors"].append(f"WORKBOOK_INVALID_OR_CORRUPT: {type(exc).__name__}: {exc}")
            report["summary"] = "Workbook could not be opened; runtime write path should remain unchanged."
            return report

        _validate_loaded_workbook(workbook, report)
        _finalize_status(report)
        return report
    except Exception as exc:  # pragma: no cover - defensive guard for runtime safety
        report["status"] = STATUS_WARNING
        report["warnings"].append(f"VALIDATOR_INTERNAL_FAILURE: {type(exc).__name__}: {exc}")
        report["summary"] = "Workbook schema validation failed internally; system flow should continue."
        return report
    finally:
        if workbook is not None and hasattr(workbook, "close"):
            workbook.close()


def _new_report(path: Path, *, checked_at: datetime | None) -> dict[str, Any]:
    stamp = checked_at or datetime.now(timezone.utc)
    return {
        "status": STATUS_OK,
        "checked_at": _isoformat(stamp),
        "workbook_path": str(path),
        "missing_sheets": [],
        "missing_columns_by_sheet": {},
        "extra_columns_by_sheet": {},
        "column_order_notes": {},
        "warnings": [],
        "errors": [],
        "summary": "",
    }


def _validate_loaded_workbook(workbook: Any, report: dict[str, Any]) -> None:
    sheet_names = list(getattr(workbook, "sheetnames", []) or [])
    if not sheet_names or not any(_sheet_has_any_value(workbook[sheet_name]) for sheet_name in sheet_names):
        report["warnings"].append("WORKBOOK_EMPTY")

    for sheet_name in EXPECTED_SHEETS:
        if sheet_name not in sheet_names:
            report["missing_sheets"].append(sheet_name)

    for sheet_name, expected_columns in SHEET_COLUMNS.items():
        if sheet_name not in sheet_names:
            continue
        actual_columns = _read_header_row(workbook[sheet_name])
        _validate_sheet_columns(sheet_name, expected_columns, actual_columns, report)


def _validate_sheet_columns(
    sheet_name: str,
    expected_columns: list[str],
    actual_columns: list[str],
    report: dict[str, Any],
) -> None:
    expected_set = set(expected_columns)
    actual_set = set(actual_columns)

    missing_columns = [column for column in expected_columns if column not in actual_set]
    if missing_columns:
        report["missing_columns_by_sheet"][sheet_name] = missing_columns

    extra_columns = [column for column in actual_columns if column and column not in expected_set]
    if extra_columns:
        report["extra_columns_by_sheet"][sheet_name] = extra_columns

    actual_expected_order = [column for column in actual_columns if column in expected_set]
    expected_present_order = [column for column in expected_columns if column in actual_set]
    if actual_expected_order != expected_present_order:
        report["column_order_notes"][sheet_name] = {
            "expected_order": expected_present_order,
            "actual_order": actual_expected_order,
        }


def _read_header_row(sheet: Any) -> list[str]:
    try:
        row_iter = sheet.iter_rows(min_row=1, max_row=1, values_only=True)
        first_row = next(row_iter, ())
    except StopIteration:
        first_row = ()
    headers = [_normalize_header(value) for value in first_row]
    while headers and not headers[-1]:
        headers.pop()
    return headers


def _sheet_has_any_value(sheet: Any) -> bool:
    try:
        max_row = min(int(getattr(sheet, "max_row", 1) or 1), 10)
        max_col = min(int(getattr(sheet, "max_column", 1) or 1), 100)
        for row in sheet.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True):
            if any(value not in (None, "") for value in row):
                return True
    except Exception:
        return False
    return False


def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _finalize_status(report: dict[str, Any]) -> None:
    for sheet_name in report["missing_sheets"]:
        report["warnings"].append(f"MISSING_SHEET: {sheet_name}")
    for sheet_name, columns in report["missing_columns_by_sheet"].items():
        report["warnings"].append(f"MISSING_COLUMNS: {sheet_name}: {', '.join(columns)}")

    if report["errors"]:
        report["status"] = STATUS_ERROR_CANDIDATE
    elif report["warnings"]:
        report["status"] = STATUS_WARNING
    else:
        report["status"] = STATUS_OK

    if report["status"] == STATUS_OK:
        extra_count = sum(len(columns) for columns in report["extra_columns_by_sheet"].values())
        order_note_count = len(report["column_order_notes"])
        if extra_count or order_note_count:
            report["summary"] = f"Workbook schema is usable with {extra_count} extra columns and {order_note_count} column order notes."
        else:
            report["summary"] = "Workbook schema matches expected sheet and column contract."
    elif report["status"] == STATUS_WARNING:
        report["summary"] = f"Workbook schema validation completed with {len(report['warnings'])} warnings."
    else:
        report["summary"] = "Workbook schema validation found error candidates."


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
