from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from .config import AppConfig


_XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_MASTERDATA_CACHE: dict[str, Any] = {"key": None, "value": None}


DEFAULT_OPERATORS = [
    {"operator_id": "1", "operator_code": "OP-001", "operator_name": "Atanmadi"},
]
DEFAULT_FAULT_OPTIONS = [
    {
        "fault_type_id": "1",
        "fault_type_code": "robot_arm_jam",
        "fault_category": "MEKANIK",
        "fault_reason_tr": "Robot Kol Sıkışması",
        "default_station_id": "3",
    },
    {
        "fault_type_id": "2",
        "fault_type_code": "conveyor_motor_pwm_step",
        "fault_category": "MEKANIK",
        "fault_reason_tr": "Konveyor Motor Hatasi",
        "default_station_id": "5",
    },
]
DEFAULT_STATIONS = [
    {"station_id": "4", "station_code": "KSK-01", "station_name_tr": "Tablet Kiosk", "line_id": "1"},
]
DEFAULT_OPENING_STEPS = [
    {"step_code": "opening_safety", "step_label": "Guvenlik kontrolu", "required": True},
    {"step_code": "opening_sensor", "step_label": "Sensor ve hat temizligi", "required": True},
    {"step_code": "opening_ready", "step_label": "Hat calismaya hazir", "required": True},
]
DEFAULT_CLOSING_STEPS = [
    {"step_code": "closing_clean", "step_label": "Hat ve cevre temizligi", "required": True},
    {"step_code": "closing_stock", "step_label": "Kalan urun ve malzeme kontrolu", "required": True},
    {"step_code": "closing_safe_stop", "step_label": "Hat guvenli kapama", "required": True},
]


def _normalize_fault_reason_text(value: Any, fault_type_code: Any = "") -> str:
    text = str(value or "").strip()
    normalized_text = "".join(char.lower() for char in text if char.isalnum())
    normalized_code = str(fault_type_code or "").strip().lower()
    if normalized_code == "robot_arm_jam":
        return "Robot Kol Sıkışması"
    if normalized_text in {
        "robotkolsikismasi",
        "robotkolsikismasi",
        "robotkolsikismasi",
        "robotkolsikismasi",
        "sikis masi".replace(" ", ""),
        "sikismasi",
    }:
        return "Robot Kol Sıkışması"
    if normalized_text == "robotkolsikismasi":
        return "Robot Kol Sıkışması"
    return text


for _fault_option in DEFAULT_FAULT_OPTIONS:
    _fault_option["fault_reason_tr"] = _normalize_fault_reason_text(
        _fault_option.get("fault_reason_tr") or _fault_option.get("fault_type_code") or "",
        _fault_option.get("fault_type_code") or "",
    )


def _column_index(cell_ref: str) -> int:
    letters = []
    for char in str(cell_ref or ""):
        if char.isalpha():
            letters.append(char.upper())
        else:
            break
    index = 0
    for char in letters:
        index = (index * 26) + (ord(char) - 64)
    return index


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iterfind(".//m:t", _XLSX_NS)).strip()
    value_node = cell.find("m:v", _XLSX_NS)
    if value_node is None or value_node.text is None:
        return ""
    text = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(text)].strip()
        except (IndexError, ValueError):
            return ""
    return str(text).strip()


def _sheet_blocks_from_xlsx(path: Path, sheet_name: str) -> dict[str, list[dict[str, str]]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {
            relationship.attrib["Id"]: relationship.attrib["Target"].lstrip("/")
            for relationship in relationships
        }
        sheet_target = ""
        sheets_element = workbook.find("m:sheets", _XLSX_NS)
        for sheet in ([] if sheets_element is None else list(sheets_element)):
            if str(sheet.attrib.get("name") or "").strip() != sheet_name:
                continue
            relation_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if relation_id:
                sheet_target = relationship_map.get(relation_id, "")
                break
        if not sheet_target:
            return {}

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("m:si", _XLSX_NS):
                shared_strings.append("".join(node.text or "" for node in item.iterfind(".//m:t", _XLSX_NS)).strip())

        sheet_root = ET.fromstring(archive.read(sheet_target))
        sheet_data = sheet_root.find("m:sheetData", _XLSX_NS)
        if sheet_data is None:
            return {}

        grid: dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0
        for row in sheet_data.findall("m:row", _XLSX_NS):
            row_index = int(row.attrib.get("r") or 0)
            max_row = max(max_row, row_index)
            for cell in row.findall("m:c", _XLSX_NS):
                cell_ref = str(cell.attrib.get("r") or "")
                col_index = _column_index(cell_ref)
                if col_index <= 0:
                    continue
                grid[(row_index, col_index)] = _cell_text(cell, shared_strings)
                max_col = max(max_col, col_index)

    block_starts: list[tuple[int, str]] = []
    for col_index in range(1, max_col + 1):
        title = str(grid.get((1, col_index), "") or "").strip()
        if title:
            block_starts.append((col_index, title))
    blocks: dict[str, list[dict[str, str]]] = {}
    for index, (start_col, block_name) in enumerate(block_starts):
        next_start_col = block_starts[index + 1][0] if index + 1 < len(block_starts) else max_col + 1
        headers: list[tuple[int, str]] = []
        for col_index in range(start_col, next_start_col):
            header = str(grid.get((2, col_index), "") or "").strip()
            if header:
                headers.append((col_index, header))
        if not headers:
            continue
        rows: list[dict[str, str]] = []
        for row_index in range(3, max_row + 1):
            row: dict[str, str] = {}
            has_any = False
            for col_index, header in headers:
                value = str(grid.get((row_index, col_index), "") or "").strip()
                if value:
                    has_any = True
                row[header] = value
            if has_any:
                rows.append(row)
        blocks[str(block_name).strip().lower()] = rows
    return blocks


def _normalize_required(value: Any, *, default: bool = True) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "evet", "zorunlu", "required"}


def _normalize_phase(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"opening", "open", "acilis", "açılış"}:
        return "opening"
    if text in {"closing", "close", "kapanis", "kapanış"}:
        return "closing"
    return ""


def _project_maintenance_steps(blocks: dict[str, list[dict[str, str]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    opening_steps: list[dict[str, Any]] = []
    closing_steps: list[dict[str, Any]] = []
    generic_steps: list[dict[str, Any]] = []
    for block_name, rows in blocks.items():
        if "bakim" not in block_name and "maintenance" not in block_name:
            continue
        phase_hint = _normalize_phase(block_name)
        for index, row in enumerate(rows, start=1):
            phase = _normalize_phase(
                row.get("phase")
                or row.get("phase_code")
                or row.get("phase_tr")
                or row.get("maintenance_phase")
                or phase_hint
            )
            step_code = str(
                row.get("step_code")
                or row.get("maintenance_step_code")
                or row.get("bakim_adim_kodu")
                or f"{phase or 'maintenance'}_step_{index}"
            ).strip()
            step_label = str(
                row.get("step_label")
                or row.get("step_name_tr")
                or row.get("maintenance_step_name_tr")
                or row.get("bakim_adim_adi")
                or step_code
            ).strip()
            projected = {
                "step_code": step_code,
                "step_label": step_label,
                "required": _normalize_required(
                    row.get("required")
                    or row.get("is_required")
                    or row.get("zorunlu")
                    or row.get("required_flag"),
                    default=True,
                ),
            }
            if phase == "opening":
                opening_steps.append(projected)
            elif phase == "closing":
                closing_steps.append(projected)
            else:
                generic_steps.append(projected)
    if generic_steps:
        if not opening_steps:
            opening_steps = [dict(row) for row in generic_steps]
        if not closing_steps:
            closing_steps = [dict(row) for row in generic_steps]
    if not opening_steps:
        opening_steps = [dict(row) for row in DEFAULT_OPENING_STEPS]
    if not closing_steps:
        closing_steps = [dict(row) for row in DEFAULT_CLOSING_STEPS]
    return opening_steps, closing_steps


def _kiosk_fault_reason_text(value: Any, fault_type_code: Any = "") -> str:
    text = str(value or "").strip()
    normalized_text = "".join(char.lower() for char in text if char.isalnum())
    normalized_code = str(fault_type_code or "").strip().lower()
    corrected = "Robot Kol S\u0131k\u0131\u015fmas\u0131"
    if normalized_code == "robot_arm_jam":
        return corrected
    if normalized_text in {"robotkolsikismasi", "robotkolsikmasi", "sikismasi", "sikismasi"}:
        return corrected
    if "sikis" in normalized_text and "masi" in normalized_text:
        return corrected
    return text


for _fault_option in DEFAULT_FAULT_OPTIONS:
    _fault_option["fault_reason_tr"] = _kiosk_fault_reason_text(
        _fault_option.get("fault_reason_tr") or _fault_option.get("fault_type_code") or "",
        _fault_option.get("fault_type_code") or "",
    )


def _normalize_catalog(blocks: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    operators = [
        {
            "operator_id": str(row.get("operator_id") or "").strip(),
            "operator_code": str(row.get("operator_code") or "").strip(),
            "operator_name": str(row.get("operator_name") or "").strip(),
        }
        for row in blocks.get("operatorler", [])
        if str(row.get("operator_id") or row.get("operator_code") or row.get("operator_name") or "").strip()
    ] or copy.deepcopy(DEFAULT_OPERATORS)

    fault_options = [
        {
            "fault_type_id": str(row.get("fault_type_id") or "").strip(),
            "fault_type_code": str(row.get("fault_type_code") or "").strip(),
            "fault_category": str(row.get("fault_category") or "").strip(),
            "fault_reason_tr": _kiosk_fault_reason_text(
                row.get("fault_reason_tr") or row.get("fault_type_code") or "",
                row.get("fault_type_code") or "",
            ),
            "default_station_id": str(row.get("default_station_id") or "").strip(),
        }
        for row in blocks.get("ariza_tipleri", [])
        if str(row.get("fault_type_code") or row.get("fault_reason_tr") or "").strip()
    ] or copy.deepcopy(DEFAULT_FAULT_OPTIONS)

    stations = [
        {
            "station_id": str(row.get("station_id") or "").strip(),
            "station_code": str(row.get("station_code") or "").strip(),
            "station_name_tr": str(row.get("station_name_tr") or "").strip(),
            "line_id": str(row.get("line_id") or "").strip(),
        }
        for row in blocks.get("istasyonlar", [])
        if str(row.get("station_id") or row.get("station_code") or row.get("station_name_tr") or "").strip()
    ] or copy.deepcopy(DEFAULT_STATIONS)

    opening_steps, closing_steps = _project_maintenance_steps(blocks)
    default_station = next(
        (
            station
            for station in stations
            if "ksk" in str(station.get("station_code") or "").strip().lower()
            or "kiosk" in str(station.get("station_name_tr") or "").strip().lower()
        ),
        stations[0] if stations else copy.deepcopy(DEFAULT_STATIONS[0]),
    )
    return {
        "operators": operators,
        "fault_options": fault_options,
        "stations": stations,
        "maintenance": {
            "opening_steps": opening_steps,
            "closing_steps": closing_steps,
        },
        "defaults": {
            "bound_station_id": str(default_station.get("station_id") or ""),
        },
    }


def _masterdata_source_path(config: AppConfig) -> Path | None:
    workbook_path = config.excel_workbook_path
    if workbook_path.exists():
        return workbook_path
    template_path = config.excel_template_path
    if template_path is not None and template_path.exists():
        return template_path
    return None


def load_kiosk_masterdata(config: AppConfig) -> dict[str, Any]:
    path = _masterdata_source_path(config)
    if path is None:
        return _normalize_catalog({})
    try:
        cache_key = (str(path.resolve()), path.stat().st_mtime)
    except OSError:
        return _normalize_catalog({})
    if _MASTERDATA_CACHE.get("key") == cache_key and isinstance(_MASTERDATA_CACHE.get("value"), dict):
        return copy.deepcopy(_MASTERDATA_CACHE["value"])
    try:
        blocks = _sheet_blocks_from_xlsx(path, "0_Tanimlamalar")
    except (BadZipFile, ET.ParseError, KeyError, OSError):
        blocks = {}
    catalog = _normalize_catalog(blocks)
    _MASTERDATA_CACHE["key"] = cache_key
    _MASTERDATA_CACHE["value"] = copy.deepcopy(catalog)
    return catalog
