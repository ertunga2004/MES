from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from .config import AppConfig
from .excel_runtime import COLOR_IDS, DECISION_SOURCE_IDS, EVENT_TYPE_IDS, MEGA_STATE_IDS, SOURCE_IDS
from .masterdata import _masterdata_source_path, _sheet_blocks_from_xlsx


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_SKIPPED = "skipped"
STATUS_ERROR_CANDIDATE = "error_candidate"
MASTERDATA_SHEET_NAME = "0_Tanimlamalar"

EXPECTED_BLOCKS = [
    "operatorler",
    "istasyonlar",
    "hatlar",
    "urunler",
    "ariza_tipleri",
    "vardiyalar",
    "renkler",
    "kaynaklar",
    "olay_tipleri",
    "karar_kaynaklari",
    "mega_durumlari",
    "bakim*",
]

REQUIRED_COLUMNS_BY_BLOCK = {
    "operatorler": ["operator_id", "operator_code", "operator_name"],
    "istasyonlar": ["station_id", "station_code", "station_name_tr", "line_id"],
    "hatlar": ["line_id", "line_code", "line_name_tr"],
    "urunler": ["product_id", "product_code", "product_name_tr"],
    "ariza_tipleri": ["fault_type_id", "fault_type_code", "fault_category", "fault_reason_tr"],
    "vardiyalar": ["shift_id", "shift_code", "shift_name_tr"],
    "renkler": ["color_code"],
    "kaynaklar": ["source_code"],
    "olay_tipleri": ["event_type_code"],
    "karar_kaynaklari": ["decision_source_code"],
    "mega_durumlari": ["mega_state_code"],
}

MAINTENANCE_COLUMN_GROUPS = [
    ("step_code", "maintenance_step_code", "bakim_adim_kodu"),
    ("step_label", "step_name_tr", "maintenance_step_name_tr", "bakim_adim_adi"),
]

FALLBACK_BLOCKS = {
    "operatorler": "operators",
    "istasyonlar": "stations",
    "ariza_tipleri": "fault_options",
    "bakim*": "maintenance_steps",
}


def validate_masterdata_source(config: AppConfig, *, checked_at: datetime | None = None) -> dict[str, Any]:
    report = _new_report(checked_at=checked_at)
    path = _masterdata_source_path(config)
    if path is None:
        report["status"] = STATUS_SKIPPED
        report["fallback_used"] = sorted(set(FALLBACK_BLOCKS.values()))
        report["warnings"].append("MASTERDATA_SOURCE_NOT_FOUND")
        report["summary"] = "Masterdata source not found; existing fallback catalog remains in use."
        return report

    report["workbook_path"] = str(path)
    try:
        if MASTERDATA_SHEET_NAME not in _xlsx_sheet_names(path):
            report["status"] = STATUS_WARNING
            report["missing_blocks"] = list(EXPECTED_BLOCKS)
            report["fallback_used"] = sorted(set(FALLBACK_BLOCKS.values()))
            report["warnings"].append(f"MISSING_SHEET: {MASTERDATA_SHEET_NAME}")
            report["summary"] = "Masterdata sheet is missing; existing fallback catalog remains in use."
            return report

        blocks = _sheet_blocks_from_xlsx(path, MASTERDATA_SHEET_NAME)
    except (BadZipFile, ET.ParseError, KeyError, OSError) as exc:
        report["status"] = STATUS_ERROR_CANDIDATE
        report["fallback_used"] = sorted(set(FALLBACK_BLOCKS.values()))
        report["errors"].append(f"MASTERDATA_INVALID_OR_CORRUPT: {type(exc).__name__}: {exc}")
        report["summary"] = "Masterdata source could not be read; existing fallback catalog remains in use."
        return report
    except Exception as exc:  # pragma: no cover - defensive guard for runtime safety
        report["status"] = STATUS_WARNING
        report["warnings"].append(f"MASTERDATA_VALIDATOR_INTERNAL_FAILURE: {type(exc).__name__}: {exc}")
        report["summary"] = "Masterdata validation failed internally; existing load flow should continue."
        return report

    _validate_blocks(blocks, report)
    _validate_lookup_diffs(blocks, report)
    _finalize_report(report)
    return report


def _new_report(*, checked_at: datetime | None) -> dict[str, Any]:
    stamp = checked_at or datetime.now(timezone.utc)
    return {
        "status": STATUS_OK,
        "checked_at": _isoformat(stamp),
        "workbook_path": "",
        "sheet_name": MASTERDATA_SHEET_NAME,
        "found_blocks": [],
        "missing_blocks": [],
        "missing_columns_by_block": {},
        "empty_blocks": [],
        "fallback_used": [],
        "lookup_diff_warnings": [],
        "warnings": [],
        "errors": [],
        "summary": "",
    }


def _validate_blocks(blocks: dict[str, list[dict[str, str]]], report: dict[str, Any]) -> None:
    found_blocks = sorted(blocks)
    report["found_blocks"] = found_blocks

    for expected_block in EXPECTED_BLOCKS:
        actual_block = _find_block_name(blocks, expected_block)
        if actual_block is None:
            report["missing_blocks"].append(expected_block)
            fallback_name = FALLBACK_BLOCKS.get(expected_block)
            if fallback_name:
                report["fallback_used"].append(fallback_name)
            continue
        rows = blocks.get(actual_block, [])
        if not rows:
            report["empty_blocks"].append(actual_block)
            fallback_name = FALLBACK_BLOCKS.get(expected_block)
            if fallback_name:
                report["fallback_used"].append(fallback_name)

    for block_name, required_columns in REQUIRED_COLUMNS_BY_BLOCK.items():
        actual_block = _find_block_name(blocks, block_name)
        if actual_block is None:
            continue
        headers = _block_headers(blocks.get(actual_block, []))
        missing_columns = [column for column in required_columns if column not in headers]
        if missing_columns:
            report["missing_columns_by_block"][actual_block] = missing_columns

    maintenance_blocks = _maintenance_blocks(blocks)
    for block_name in maintenance_blocks:
        headers = _block_headers(blocks.get(block_name, []))
        missing_groups = []
        for group in MAINTENANCE_COLUMN_GROUPS:
            if not any(column in headers for column in group):
                missing_groups.append("one_of(" + ",".join(group) + ")")
        if missing_groups:
            report["missing_columns_by_block"][block_name] = missing_groups


def _validate_lookup_diffs(blocks: dict[str, list[dict[str, str]]], report: dict[str, Any]) -> None:
    _append_lookup_diff(
        report,
        block_name="renkler",
        rows=blocks.get("renkler", []),
        code_columns=("color_code", "color_code_raw"),
        expected_codes=set(COLOR_IDS),
        normalize=lambda value: str(value or "").strip().lower(),
    )
    _append_lookup_diff(
        report,
        block_name="kaynaklar",
        rows=blocks.get("kaynaklar", []),
        code_columns=("source_code",),
        expected_codes=set(SOURCE_IDS),
        normalize=lambda value: str(value or "").strip().lower(),
    )
    _append_lookup_diff(
        report,
        block_name="olay_tipleri",
        rows=blocks.get("olay_tipleri", []),
        code_columns=("event_type_code",),
        expected_codes=set(EVENT_TYPE_IDS),
        normalize=lambda value: str(value or "").strip().lower(),
    )
    _append_lookup_diff(
        report,
        block_name="karar_kaynaklari",
        rows=blocks.get("karar_kaynaklari", []),
        code_columns=("decision_source_code",),
        expected_codes=set(DECISION_SOURCE_IDS),
        normalize=lambda value: str(value or "").strip().upper(),
    )
    _append_lookup_diff(
        report,
        block_name="mega_durumlari",
        rows=blocks.get("mega_durumlari", []),
        code_columns=("mega_state_code",),
        expected_codes=set(MEGA_STATE_IDS),
        normalize=lambda value: str(value or "").strip().upper(),
    )


def _append_lookup_diff(
    report: dict[str, Any],
    *,
    block_name: str,
    rows: list[dict[str, str]],
    code_columns: tuple[str, ...],
    expected_codes: set[str],
    normalize: Any,
) -> None:
    if not rows:
        return
    actual_codes: set[str] = set()
    for row in rows:
        for column in code_columns:
            value = row.get(column)
            if value not in (None, ""):
                actual_codes.add(normalize(value))
                break
    expected_normalized = {normalize(code) for code in expected_codes}
    missing_in_sheet = sorted(expected_normalized - actual_codes)
    extra_in_sheet = sorted(actual_codes - expected_normalized)
    if missing_in_sheet:
        report["lookup_diff_warnings"].append(
            f"LOOKUP_MISSING_IN_MASTERDATA: {block_name}: {', '.join(missing_in_sheet)}"
        )
    if extra_in_sheet:
        report["lookup_diff_warnings"].append(
            f"LOOKUP_EXTRA_IN_MASTERDATA: {block_name}: {', '.join(extra_in_sheet)}"
        )


def _xlsx_sheet_names(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets_element = workbook.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
        if sheets_element is None:
            return []
        return [str(sheet.attrib.get("name") or "").strip() for sheet in list(sheets_element)]


def _find_block_name(blocks: dict[str, list[dict[str, str]]], expected_block: str) -> str | None:
    if expected_block == "bakim*":
        maintenance_blocks = _maintenance_blocks(blocks)
        return maintenance_blocks[0] if maintenance_blocks else None
    if expected_block in blocks:
        return expected_block
    return None


def _maintenance_blocks(blocks: dict[str, list[dict[str, str]]]) -> list[str]:
    return sorted(
        block_name
        for block_name in blocks
        if "bakim" in block_name.lower() or "maintenance" in block_name.lower()
    )


def _block_headers(rows: list[dict[str, str]]) -> set[str]:
    headers: set[str] = set()
    for row in rows:
        headers.update(str(key).strip() for key in row)
    return {header for header in headers if header}


def _finalize_report(report: dict[str, Any]) -> None:
    report["fallback_used"] = sorted(set(report["fallback_used"]))

    for block_name in report["missing_blocks"]:
        report["warnings"].append(f"MISSING_MASTERDATA_BLOCK: {block_name}")
    for block_name in report["empty_blocks"]:
        report["warnings"].append(f"EMPTY_MASTERDATA_BLOCK: {block_name}")
    for block_name, columns in report["missing_columns_by_block"].items():
        report["warnings"].append(f"MISSING_MASTERDATA_COLUMNS: {block_name}: {', '.join(columns)}")
    report["warnings"].extend(report["lookup_diff_warnings"])

    if report["errors"]:
        report["status"] = STATUS_ERROR_CANDIDATE
    elif report["warnings"]:
        report["status"] = STATUS_WARNING
    else:
        report["status"] = STATUS_OK

    if report["status"] == STATUS_OK:
        report["summary"] = "Masterdata validation found expected blocks and active lookup contracts."
    elif report["status"] == STATUS_WARNING:
        report["summary"] = f"Masterdata validation completed with {len(report['warnings'])} warnings."
    else:
        report["summary"] = "Masterdata validation found error candidates."


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
