from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from .ferp_export import safe_export_timestamp, sanitize_filename_token


SPREADSHEET_NS = "urn:schemas-microsoft-com:office:spreadsheet"
NS = {"ss": SPREADSHEET_NS}

DEFAULT_WORK_CENTER_CODE = "KNV-01"
DEFAULT_WORK_CENTER_NAME = "Mini konveyör iş merkezi"
DEFAULT_DEPOT_CODE = "0001"
DEFAULT_LOCATION_CODE = "0001"

FERP_STOCK_ROWS = [
    {
        "Stok ID": "900001",
        "Stok Kodu": "BOX-RED",
        "Stok Adi": "Kırmızı Kutu",
        "SKU": "BOX-RED",
        "Stok Grubu": "MM",
        "Birim": "ADET",
        "Uretiliyormu?": "1",
    },
    {
        "Stok ID": "900002",
        "Stok Kodu": "BOX-BLUE",
        "Stok Adi": "Mavi Kutu",
        "SKU": "BOX-BLUE",
        "Stok Grubu": "MM",
        "Birim": "ADET",
        "Uretiliyormu?": "1",
    },
    {
        "Stok ID": "900003",
        "Stok Kodu": "BOX-YEL",
        "Stok Adi": "Sarı Kutu",
        "SKU": "BOX-YEL",
        "Stok Grubu": "MM",
        "Birim": "ADET",
        "Uretiliyormu?": "1",
    },
]

FERP_WORK_CENTER_ROWS = [
    {
        "Kodu": DEFAULT_WORK_CENTER_CODE,
        "Adi": DEFAULT_WORK_CENTER_NAME,
        "Depo Kodu": DEFAULT_DEPOT_CODE,
        "Lokasyon Kodu": DEFAULT_LOCATION_CODE,
    }
]

FERP_WORK_STATION_ROWS = [
    {
        "Is Merkezi Kodu": DEFAULT_WORK_CENTER_CODE,
        "Is Istasyonu": "SNS-01",
        "Adi": "Sensör ölçüm istasyonu",
        "Sira": 10,
        "Varsayilan Operasyon Adi": "Sensör ölçümü",
    },
    {
        "Is Merkezi Kodu": DEFAULT_WORK_CENTER_CODE,
        "Is Istasyonu": "ROB-01",
        "Adi": "Robot kol istasyonu",
        "Sira": 20,
        "Varsayilan Operasyon Adi": "Robot kol taşıması",
    },
]

FERP_OPERATION_ROWS = [
    {
        "Kodu": "SNS-MSR",
        "Adi": "Sensör ölçümü",
        "Sirasi": 10,
        "Aciklamasi": "Kutu renginin sensör ile ölçülmesi",
    },
    {
        "Kodu": "ROB-MOV",
        "Adi": "Robot kol taşıması",
        "Sirasi": 20,
        "Aciklamasi": "Kutunun robot kol ile hedef alana taşınması",
    },
]

WORK_ORDER_OPERATION_ROWS = (
    {"station": "SNS-01", "operation": "SNS-MSR", "name": "Sensör ölçümü", "sequence": 10},
    {"station": "ROB-01", "operation": "ROB-MOV", "name": "Robot kol taşıması", "sequence": 20},
)

TEMPLATE_PATTERNS = {
    "stock": "FERP_STOK_KARTI.xls",
    "work_center": "*MERKEZ*.xls",
    "work_station": "*STASYONU.xls",
    "operation": "FERP_OPERASYON_TANIMLARI.xls",
    "work_order": "FERP_IS_EMR*.xls",
}


@dataclass(frozen=True, slots=True)
class FerpXlsExportResult:
    export_id: str
    directory: Path
    files: list[Path]
    warnings: list[str]


class FerpXlsTemplateError(RuntimeError):
    pass


def _cell_text(cell: ET.Element) -> str:
    data = cell.find("ss:Data", NS)
    return "" if data is None or data.text is None else str(data.text).strip()


def _parse_spreadsheet_rows(path: Path) -> list[list[str]]:
    tree = ET.parse(path)
    rows: list[list[str]] = []
    for row in tree.findall(".//ss:Worksheet/ss:Table/ss:Row", NS):
        values: list[str] = []
        position = 1
        for cell in row.findall("ss:Cell", NS):
            index_text = cell.attrib.get(f"{{{SPREADSHEET_NS}}}Index")
            if index_text:
                while position < int(index_text):
                    values.append("")
                    position += 1
            values.append(_cell_text(cell))
            position += 1
        if any(values):
            rows.append(values)
    return rows


def read_ferp_xls_rows(path: str | Path) -> list[list[str]]:
    return _parse_spreadsheet_rows(Path(path))


def _headers(path: Path) -> list[str]:
    rows = _parse_spreadsheet_rows(path)
    if not rows:
        raise FerpXlsTemplateError(f"FERP_XLS_TEMPLATE_EMPTY: {path}")
    return rows[0]


def _normalize_text(value: str) -> str:
    replacements = str.maketrans(
        {
            "ı": "i",
            "İ": "I",
            "ğ": "g",
            "Ğ": "G",
            "ü": "u",
            "Ü": "U",
            "ş": "s",
            "Ş": "S",
            "ö": "o",
            "Ö": "O",
            "ç": "c",
            "Ç": "C",
        }
    )
    return " ".join(str(value or "").translate(replacements).strip().split())


def _header_key(value: str) -> str:
    return _normalize_text(value).lower()


def _row_from_map(headers: list[str], values_by_header: dict[str, Any]) -> list[Any]:
    normalized = {_header_key(key): value for key, value in values_by_header.items()}
    return [normalized.get(_header_key(header), "") for header in headers]


def _cell_xml(value: Any) -> str:
    if value is None:
        text = ""
        value_type = "String"
    elif isinstance(value, bool):
        text = "1" if value else "0"
        value_type = "Number"
    elif isinstance(value, int | float) and not isinstance(value, bool):
        text = str(value)
        value_type = "Number"
    else:
        text = str(value)
        value_type = "String"
    return f'<ss:Cell><ss:Data ss:Type="{value_type}">{escape(text)}</ss:Data></ss:Cell>'


def _row_xml(values: list[Any]) -> str:
    cells = "".join(_cell_xml(value) for value in values)
    return f'<Row ss:Height="19.5">{cells}</Row>'


def _write_template_with_rows(template_path: Path, output_path: Path, rows: list[list[Any]]) -> Path:
    raw = template_path.read_text(encoding="utf-8")
    marker = "</Table>"
    if marker not in raw:
        raise FerpXlsTemplateError(f"FERP_XLS_TABLE_NOT_FOUND: {template_path}")
    inserted = "\n".join(_row_xml(row) for row in rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(raw.replace(marker, inserted + "\n</Table>", 1), encoding="utf-8")
    return output_path


def _find_template(source_dir: str | Path, pattern: str) -> Path:
    source = Path(source_dir)
    matches = sorted(path for path in source.glob(pattern) if path.is_file())
    if not matches:
        raise FerpXlsTemplateError(f"FERP_XLS_TEMPLATE_NOT_FOUND: {source / pattern}")
    return matches[0]


def _quantity(value: Any) -> int:
    try:
        return max(0, round(float(str(value or "0").replace(",", "."))))
    except ValueError:
        return 0


def _first_text(row: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return default


def _completed_quantity(work_order: dict[str, Any]) -> int:
    for key in ("completedQty", "completed_qty", "productionQty", "production_qty", "quantity", "targetQty", "target_qty"):
        quantity = _quantity(work_order.get(key))
        if quantity:
            return quantity
    return 0


def _target_quantity(work_order: dict[str, Any]) -> int:
    return _quantity(work_order.get("quantity") or work_order.get("targetQty") or work_order.get("target_qty"))


def _work_order_rows(headers: list[str], work_order: dict[str, Any]) -> list[list[Any]]:
    order_id = _first_text(work_order, "orderId", "order_id", "id")
    target_quantity = _target_quantity(work_order)
    completed_quantity = _completed_quantity(work_order)
    base_description = _first_text(work_order, "description", "aciklama")
    work_center = _first_text(work_order, "workCenterCode", "work_center_code", default=DEFAULT_WORK_CENTER_CODE)
    stock_code = _first_text(work_order, "stockCode", "productCode", "stock_code", "product_code")
    stock_name = _first_text(work_order, "stockName", "productName", "stock_name", "product_name", default=stock_code)
    date_text = _first_text(work_order, "date", "completedAt", "autoCompletedAt", "startedAt")
    unit = _first_text(work_order, "unit", "uom", default="ADET")
    cycle_time = work_order.get("cycleTimeSec") or work_order.get("cycle_time_sec") or ""
    project_code = _first_text(work_order, "projectCode", "project_code")
    lot_code = _first_text(work_order, "lotCode", "lot_code")

    rows: list[list[Any]] = []
    for step in WORK_ORDER_OPERATION_ROWS:
        description = base_description
        if description:
            description = f"{description} - {step['name']}"
        else:
            description = str(step["name"])
        row = []
        sira_seen = 0
        for header in headers:
            key = _header_key(header)
            value: Any = ""
            if key == "sira":
                value = step["sequence"] if sira_seen == 0 else ""
                sira_seen += 1
            elif key == "id":
                value = ""
            elif key == "is merkezi":
                value = work_center
            elif key == "is istasyonu":
                value = step["station"]
            elif key == "is emri tarihi":
                value = date_text
            elif key == "is emri no":
                value = order_id
            elif key == "urun kodu":
                value = stock_code
            elif key == "urun ismi":
                value = stock_name
            elif key == "metod kodu":
                value = step["operation"]
            elif key == "lot kodu":
                value = lot_code
            elif key == "is emri miktari":
                value = target_quantity
            elif key == "birim":
                value = unit
            elif key == "kapanan miktar":
                value = completed_quantity
            elif key == "statu":
                value = "TAMAMLANDI"
            elif key == "proje kodu":
                value = project_code
            elif key == "aciklama":
                value = description
            elif key == "sure":
                value = cycle_time
            row.append(value)
        rows.append(row)
    return rows


def write_seeded_ferp_examples(source_dir: str | Path, output_dir: str | Path) -> list[Path]:
    stock_template = _find_template(source_dir, TEMPLATE_PATTERNS["stock"])
    work_center_template = _find_template(source_dir, TEMPLATE_PATTERNS["work_center"])
    work_station_template = _find_template(source_dir, TEMPLATE_PATTERNS["work_station"])
    operation_template = _find_template(source_dir, TEMPLATE_PATTERNS["operation"])

    output = Path(output_dir)
    specs = [
        (stock_template, FERP_STOCK_ROWS),
        (work_center_template, FERP_WORK_CENTER_ROWS),
        (work_station_template, FERP_WORK_STATION_ROWS),
        (operation_template, FERP_OPERATION_ROWS),
    ]
    files: list[Path] = []
    for template, mapped_rows in specs:
        headers = _headers(template)
        rows = [_row_from_map(headers, row) for row in mapped_rows]
        files.append(_write_template_with_rows(template, output / template.name, rows))
    return files


def write_work_order_xls_export(
    work_order: dict[str, Any],
    *,
    source_dir: str | Path,
    pending_dir: str | Path,
    created_at: Any = None,
) -> FerpXlsExportResult:
    template = _find_template(source_dir, TEMPLATE_PATTERNS["work_order"])
    order_id = _first_text(work_order, "orderId", "order_id", "id", default="UNKNOWN")
    timestamp = safe_export_timestamp(created_at)
    base_export_id = f"FERP_{sanitize_filename_token(order_id)}_{timestamp}"
    target_root = Path(pending_dir)
    target_dir = target_root / base_export_id
    suffix = 2
    while target_dir.exists():
        target_dir = target_root / f"{base_export_id}_{suffix}"
        suffix += 1
    export_id = target_dir.name

    headers = _headers(template)
    rows = _work_order_rows(headers, work_order)
    output_file = _write_template_with_rows(template, target_dir / template.name, rows)
    warnings: list[str] = []
    if not _first_text(work_order, "workCenterCode", "work_center_code"):
        warnings.append(f"FERP_XLS_DEFAULT_WORK_CENTER_USED: {DEFAULT_WORK_CENTER_CODE}")
    if not _first_text(work_order, "workStationCode", "work_station_code"):
        warnings.append("FERP_XLS_OPERATION_ROUTE_USED: SNS-01/SNS-MSR, ROB-01/ROB-MOV")
    return FerpXlsExportResult(
        export_id=export_id,
        directory=target_dir,
        files=[output_file],
        warnings=warnings,
    )
