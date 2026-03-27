from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
import math
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
OUTPUT_FILE = ROOT / "MES_Konveyor_Veritabani_Sablonu.xlsx"

TARGET_COUNTS = {
    "MAVI_S": 5,
    "MAVI_R": 0,
    "MAVI_H": 0,
    "SARI_S": 4,
    "SARI_R": 0,
    "SARI_H": 0,
    "KIRMIZI_S": 5,
    "KIRMIZI_R": 0,
    "KIRMIZI_H": 0,
}

COLOR_ROWS = [
    {"color_id": 1, "color_code": "red", "color_code_raw": "KIRMIZI", "color_name_tr": "Kirmizi", "is_sortable": 1},
    {"color_id": 2, "color_code": "yellow", "color_code_raw": "SARI", "color_name_tr": "Sari", "is_sortable": 1},
    {"color_id": 3, "color_code": "blue", "color_code_raw": "MAVI", "color_name_tr": "Mavi", "is_sortable": 1},
    {"color_id": 4, "color_code": "empty", "color_code_raw": "BOS", "color_name_tr": "Bos", "is_sortable": 0},
    {"color_id": 5, "color_code": "uncertain", "color_code_raw": "BELIRSIZ", "color_name_tr": "Belirsiz", "is_sortable": 0},
]
COLOR_MAP = {row["color_code_raw"]: row["color_code"] for row in COLOR_ROWS}
COLOR_ID_MAP = {row["color_code"]: row["color_id"] for row in COLOR_ROWS}

SOURCE_ROWS = [
    {"source_id": 1, "source_code": "mega", "source_name_tr": "Mega", "source_role": "Saha kontrol ve ana olay kaynagi"},
    {"source_id": 2, "source_code": "tablet", "source_name_tr": "Tablet", "source_role": "Kiosk, operator ve OEE kaynagi"},
    {"source_id": 3, "source_code": "vision", "source_name_tr": "Vision", "source_role": "Goruntu isleme ve capraz kontrol"},
]
SOURCE_ID_MAP = {row["source_code"]: row["source_id"] for row in SOURCE_ROWS}

DECISION_SOURCE_ROWS = [
    {"decision_source_id": 1, "decision_source_code": "CORE_STABLE", "description_tr": "Ana cekirdek karari stabil"},
    {"decision_source_id": 2, "decision_source_code": "MEDIAN_STABLE", "description_tr": "Median karar akisi stabil"},
    {"decision_source_id": 3, "decision_source_code": "CORE_VOTE_MATCH", "description_tr": "Cekirdek oy eslesmesi ile karar"},
    {"decision_source_id": 4, "decision_source_code": "VISION", "description_tr": "Vision yardimci karar kaynagi"},
    {"decision_source_id": 5, "decision_source_code": "TABLET", "description_tr": "Tablet veya operator kaynagi"},
    {"decision_source_id": 6, "decision_source_code": "SYSTEM", "description_tr": "Sistem veya ornek kayit"},
]
DECISION_SOURCE_ID_MAP = {row["decision_source_code"]: row["decision_source_id"] for row in DECISION_SOURCE_ROWS}

EVENT_TYPE_ROWS = [
    {"event_type_id": 1, "event_type_code": "measurement_started", "event_name_tr": "Olcum basladi", "detail_sheet": "2_Olcumler"},
    {"event_type_id": 2, "event_type_code": "measurement_decision", "event_name_tr": "Olcum karari verildi", "detail_sheet": "2_Olcumler"},
    {"event_type_id": 3, "event_type_code": "queue_enq", "event_name_tr": "Urun kuyruga alindi", "detail_sheet": "4_Uretim_Tamamlanan"},
    {"event_type_id": 4, "event_type_code": "arm_position_reached", "event_name_tr": "Robot kol hedefe ulasti", "detail_sheet": "1_Olay_Logu"},
    {"event_type_id": 5, "event_type_code": "pickplace_done", "event_name_tr": "Pick and place tamamlandi", "detail_sheet": "4_Uretim_Tamamlanan"},
    {"event_type_id": 6, "event_type_code": "fault_reported", "event_name_tr": "Ariza bildirildi", "detail_sheet": "3_Arizalar"},
    {"event_type_id": 7, "event_type_code": "conveyor_stopped", "event_name_tr": "Konveyor durdu", "detail_sheet": "3_Arizalar"},
    {"event_type_id": 8, "event_type_code": "fault_resolved", "event_name_tr": "Ariza kapatildi", "detail_sheet": "3_Arizalar"},
    {"event_type_id": 9, "event_type_code": "conveyor_started", "event_name_tr": "Konveyor yeniden basladi", "detail_sheet": "3_Arizalar"},
    {"event_type_id": 10, "event_type_code": "oee_snapshot", "event_name_tr": "OEE anligi alindi", "detail_sheet": "5_OEE_Anliklari"},
    {"event_type_id": 11, "event_type_code": "vision_event", "event_name_tr": "Vision ornek olayi", "detail_sheet": "6_Vision"},
]
EVENT_TYPE_ID_MAP = {row["event_type_code"]: row["event_type_id"] for row in EVENT_TYPE_ROWS}

MEGA_STATE_ROWS = [
    {"mega_state_id": 1, "mega_state_code": "SEARCH", "mega_state_tr": "Arama"},
    {"mega_state_id": 2, "mega_state_code": "SEARCHING", "mega_state_tr": "Arama"},
    {"mega_state_id": 3, "mega_state_code": "MEASURING", "mega_state_tr": "Olcum"},
    {"mega_state_id": 4, "mega_state_code": "WAIT_ARM", "mega_state_tr": "Robot bekleniyor"},
    {"mega_state_id": 5, "mega_state_code": "PAUSED", "mega_state_tr": "Duraklatildi"},
    {"mega_state_id": 6, "mega_state_code": "STOPPED", "mega_state_tr": "Durdu"},
    {"mega_state_id": 7, "mega_state_code": "QUEUE", "mega_state_tr": "Kuyrukta"},
]
MEGA_STATE_ID_MAP = {row["mega_state_code"]: row["mega_state_id"] for row in MEGA_STATE_ROWS}

FAULT_TYPE_ROWS = [
    {
        "fault_type_id": 1,
        "fault_type_code": "robot_arm_jam",
        "fault_category": "MEKANIK",
        "fault_reason_tr": "Robot Kol Sikis masi",
        "default_station_id": 3,
    },
    {
        "fault_type_id": 2,
        "fault_type_code": "conveyor_motor_pwm_step",
        "fault_category": "MEKANIK",
        "fault_reason_tr": "Konveyor Motor Hatasi (PWM/Step)",
        "default_station_id": 5,
    },
]
FAULT_TYPE_MAP = {
    "Robot Kol Sıkışması": FAULT_TYPE_ROWS[0],
    "Robot Kol Sikis masi": FAULT_TYPE_ROWS[0],
    "Konveyör Motor Hatası (PWM/Step)": FAULT_TYPE_ROWS[1],
    "Konveyor Motor Hatası (PWM/Step)": FAULT_TYPE_ROWS[1],
    "Konveyor Motor Hatasi (PWM/Step)": FAULT_TYPE_ROWS[1],
}

LINE_ROWS = [{"line_id": 1, "line_code": "KNV-01", "line_name_tr": "Mini Konveyor Hatti", "erp_ready": 1}]

STATION_ROWS = [
    {"station_id": 1, "station_code": "SENS-01", "station_name_tr": "Renk Sensor Istasyonu", "line_id": 1},
    {"station_id": 2, "station_code": "BUF-01", "station_name_tr": "Robot Kuyruk Bufferi", "line_id": 1},
    {"station_id": 3, "station_code": "ARM-01", "station_name_tr": "Robot Kol Istasyonu", "line_id": 1},
    {"station_id": 4, "station_code": "KSK-01", "station_name_tr": "Tablet Kiosk", "line_id": 1},
    {"station_id": 5, "station_code": "CNV-01", "station_name_tr": "Ana Konveyor", "line_id": 1},
    {"station_id": 6, "station_code": "VIS-01", "station_name_tr": "Vision Kamera", "line_id": 1},
]

PRODUCT_ROWS = [
    {"product_id": 1, "product_code": "BOX-RED", "product_name_tr": "Kirmizi Kutu", "color_id": 1},
    {"product_id": 2, "product_code": "BOX-YEL", "product_name_tr": "Sari Kutu", "color_id": 2},
    {"product_id": 3, "product_code": "BOX-BLU", "product_name_tr": "Mavi Kutu", "color_id": 3},
]

OPERATOR_ROWS = [{"operator_id": 1, "operator_code": "OP-001", "operator_name": "Atanmadi", "source_note": "Tablet kaydinda operator bilgisi yok"}]

SHIFT_ROWS = [
    {"shift_id": 1, "shift_code": "SHIFT-A", "shift_name_tr": "A Vardiyasi", "is_default": 1},
    {"shift_id": 2, "shift_code": "SHIFT-B", "shift_name_tr": "B Vardiyasi", "is_default": 0},
    {"shift_id": 3, "shift_code": "SHIFT-C", "shift_name_tr": "C Vardiyasi", "is_default": 0},
]


@dataclass
class ParsedLine:
    written_dt: datetime
    actual_dt: datetime
    body: str
    raw_line: str
    source_file: str


def parse_datetime_text(text: str, base_date: date | None = None) -> datetime:
    text = text.strip()
    formats = (
        "%d.%m.%Y %H:%M:%S.%f",
        "%d.%m.%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S.%f",
        "%d-%m-%Y %H:%M:%S",
        "%d:%m:%Y %H:%M:%S.%f",
        "%d:%m:%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%H:%M:%S.%f",
        "%H:%M:%S",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt.startswith("%H") and base_date is not None:
                return datetime.combine(base_date, parsed.time())
            return parsed
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {text}")


def iso_text(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="milliseconds")


def clean_int(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text or text in {"0", "-"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def clean_str(value: str | None) -> str:
    return (value or "").strip()


def normalize_color(raw_value: str | None) -> str:
    raw = clean_str(raw_value).upper()
    return COLOR_MAP.get(raw, raw.lower())


def normalize_fault_type(reason: str) -> dict[str, Any]:
    return FAULT_TYPE_MAP.get(reason, {
        "fault_type_id": 999,
        "fault_type_code": "other_fault",
        "fault_category": "DIGER",
        "fault_reason_tr": reason,
        "default_station_id": 5,
    })


def parse_prefixed_line(line: str, source_file: str) -> ParsedLine:
    outer_match = re.match(r"^\[(?P<written>[^\]]+)\]\s*(?P<body>.*)$", line)
    if not outer_match:
        raise ValueError(f"Unsupported log line: {line}")
    written_dt = parse_datetime_text(outer_match.group("written"))
    body = outer_match.group("body")
    actual_dt = written_dt
    if body.startswith("["):
        inner_match = re.match(r"^\[(?P<actual>[^\]]+)\](?P<rest>.*)$", body)
        if inner_match:
            actual_dt = parse_datetime_text(inner_match.group("actual"))
            body = inner_match.group("rest")
    return ParsedLine(
        written_dt=written_dt,
        actual_dt=actual_dt,
        body=body.strip(),
        raw_line=line.rstrip("\n"),
        source_file=source_file,
    )


def parse_mega_kv(parts: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for part in parts:
        key, sep, value = part.partition("=")
        if sep:
            data[key] = value
    return data


def parse_tablet_kv(parts: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition(":")
        if sep:
            data[key.strip()] = value.strip()
    return data


def load_mega_lines() -> list[ParsedLine]:
    parsed: list[ParsedLine] = []
    for path in sorted(LOGS_DIR.glob("log_*.txt")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "MEGA|" in line:
                parsed.append(parse_prefixed_line(line, path.name))
    return parsed


def load_tablet_lines() -> list[ParsedLine]:
    parsed: list[ParsedLine] = []
    for path in sorted(LOGS_DIR.glob("tablet_log_*.txt")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "|Tablet|" in line:
                parsed.append(parse_prefixed_line(line, path.name))
    return parsed


def parse_oee_snapshots(tablet_lines: list[ParsedLine]) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for line in tablet_lines:
        if "|Tablet|OEE|" not in line.body:
            continue
        parts = [part for part in line.body.split("|") if part]
        if len(parts) < 3:
            continue
        payload = parse_tablet_kv(parts[2:])
        snapshot = {
            "actual_dt": line.actual_dt,
            "written_dt": line.written_dt,
            "source_file": line.source_file,
            "raw_line": line.raw_line,
        }
        for key, value in payload.items():
            if key in {"OEE", "KULL", "PERF", "KALITE"} or key.endswith(("_S", "_R", "_H")):
                try:
                    snapshot[key] = float(value)
                except ValueError:
                    snapshot[key] = value
            else:
                snapshot[key] = value
        snapshots.append(snapshot)
    snapshots.sort(key=lambda item: item["actual_dt"])
    return snapshots


def all_zero_counts(snapshot: dict[str, Any]) -> bool:
    return all(float(snapshot.get(key, 0)) == 0 for key in TARGET_COUNTS)


def is_target_cycle(snapshot: dict[str, Any]) -> bool:
    for key, expected in TARGET_COUNTS.items():
        if float(snapshot.get(key, -1)) != expected:
            return False
    return True


def find_sample_window(oee_snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    target = next((row for row in oee_snapshots if row["actual_dt"].date() == date(2026, 3, 25) and is_target_cycle(row)), None)
    if target is None:
        raise RuntimeError("Target full-cycle OEE snapshot was not found in tablet logs.")
    start = None
    for snapshot in oee_snapshots:
        if snapshot["actual_dt"] >= target["actual_dt"]:
            break
        if snapshot["actual_dt"].date() == target["actual_dt"].date() and all_zero_counts(snapshot):
            start = snapshot
    if start is None:
        raise RuntimeError("Sample cycle start snapshot was not found.")
    next_snapshot = next((row for row in oee_snapshots if row["actual_dt"] > target["actual_dt"]), None)
    return start, target, next_snapshot


def parse_fault_records(tablet_lines: list[ParsedLine], window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    open_faults: dict[tuple[str, str, str], dict[str, Any]] = {}
    fault_records: list[dict[str, Any]] = []
    seen_faults: set[tuple[str, str, str]] = set()

    for line in tablet_lines:
        if "|Tablet|Ar" not in line.body and "|Tablet|Arıza|" not in line.body:
            continue
        parts = [part for part in line.body.split("|") if part]
        if len(parts) < 3:
            continue
        payload = parse_tablet_kv(parts[2:])
        category = clean_str(payload.get("KATEGORI"))
        reason = clean_str(payload.get("NEDEN"))
        status = clean_str(payload.get("DURUM")).upper()
        base_date = line.actual_dt.date()
        start_dt = parse_datetime_text(payload.get("BASLANGIC", ""), base_date)
        end_text = clean_str(payload.get("BITIS"))
        end_dt = parse_datetime_text(end_text, base_date) if end_text else None
        key = (category, reason, iso_text(start_dt))

        if status == "BASLADI":
            open_faults[key] = {
                "category": category,
                "reason": reason,
                "started_at": start_dt,
                "start_raw_line": line.raw_line,
            }
            continue
        if status != "BITTI":
            continue

        existing = open_faults.pop(key, {
            "category": category,
            "reason": reason,
            "started_at": start_dt,
            "start_raw_line": "",
        })
        actual_start = existing["started_at"]
        actual_end = end_dt or line.actual_dt
        if actual_end < window_start or actual_start >= window_end:
            continue
        dedupe_key = (reason, iso_text(actual_start), iso_text(actual_end))
        if dedupe_key in seen_faults:
            continue
        seen_faults.add(dedupe_key)

        fault_type = normalize_fault_type(reason)
        try:
            duration_minutes = float(payload.get("SURE_DK", ""))
        except ValueError:
            duration_minutes = round((actual_end - actual_start).total_seconds() / 60, 2)
        fault_records.append({
            "fault_type": fault_type,
            "category": category,
            "reason": reason,
            "started_at": actual_start,
            "ended_at": actual_end,
            "duration_minutes": duration_minutes,
            "duration_seconds": round(duration_minutes * 60, 2),
            "status": "BITTI",
            "resolved_flag": 1,
            "source_code": "tablet",
            "line_id": 1,
            "station_id": fault_type["default_station_id"],
            "operator_id": 1,
            "start_raw_line": existing["start_raw_line"],
            "end_raw_line": line.raw_line,
        })

    fault_records.sort(key=lambda item: item["started_at"])
    for index, record in enumerate(fault_records, start=1):
        record["fault_id"] = index
    return fault_records


def build_measurement_error_flag(final_color: str, confidence: Any) -> tuple[int, str]:
    conf_value = None
    try:
        conf_value = float(confidence)
    except (TypeError, ValueError):
        conf_value = None
    if final_color in {"uncertain", "empty"}:
        return 1, f"final_color={final_color}"
    if conf_value is not None and conf_value == 0:
        return 1, "confidence=0"
    return 0, ""


def station_for_event(event_type_code: str) -> int:
    if event_type_code in {"measurement_started", "measurement_decision"}:
        return 1
    if event_type_code == "queue_enq":
        return 2
    if event_type_code in {"arm_position_reached", "pickplace_done"}:
        return 3
    if event_type_code in {"fault_reported", "fault_resolved", "oee_snapshot"}:
        return 4
    if event_type_code in {"conveyor_stopped", "conveyor_started"}:
        return 5
    if event_type_code == "vision_event":
        return 6
    return 5


def sort_rank_for_event(event_type_code: str) -> int:
    order = {
        "measurement_started": 10,
        "measurement_decision": 20,
        "queue_enq": 30,
        "arm_position_reached": 40,
        "pickplace_done": 50,
        "fault_reported": 60,
        "conveyor_stopped": 61,
        "fault_resolved": 62,
        "conveyor_started": 63,
        "oee_snapshot": 70,
    }
    return order.get(event_type_code, 999)


def build_summary(event_type_code: str, data: dict[str, Any]) -> str:
    item_id = data.get("item_id")
    measure_id = data.get("measure_id")
    color_raw = clean_str(data.get("color_raw"))
    fault_id = data.get("fault_id")
    if event_type_code == "measurement_started":
        return f"Nesne algilandi, olcum basladi (measure_id={measure_id}, search_hint={data.get('search_hint', '')})"
    if event_type_code == "measurement_decision":
        return f"Olcum karari verildi: {color_raw} (item_id={item_id}, measure_id={measure_id})"
    if event_type_code == "queue_enq":
        return f"Urun robot kuyruguna alindi (item_id={item_id}, measure_id={measure_id})"
    if event_type_code == "arm_position_reached":
        return f"Robot kol hedef pozisyona ulasti (item_id={item_id}, measure_id={measure_id})"
    if event_type_code == "pickplace_done":
        return f"Robot kol kutuyu birakti, islem tamamlandi (item_id={item_id}, measure_id={measure_id})"
    if event_type_code == "fault_reported":
        return f"{data.get('fault_reason_tr')} arizasi bildirildi (fault_id={fault_id})"
    if event_type_code == "conveyor_stopped":
        return f"Konveyor durdu (fault_id={fault_id})"
    if event_type_code == "fault_resolved":
        return f"{data.get('fault_reason_tr')} arizasi kapatildi (fault_id={fault_id})"
    if event_type_code == "conveyor_started":
        return f"Konveyor yeniden basladi (fault_id={fault_id})"
    if event_type_code == "oee_snapshot":
        return (
            "OEE anligi alindi "
            f"(MAVI_S={int(data.get('MAVI_S', 0))}, "
            f"SARI_S={int(data.get('SARI_S', 0))}, "
            f"KIRMIZI_S={int(data.get('KIRMIZI_S', 0))})"
        )
    return "Vision ornek kaydi" if event_type_code == "vision_event" else event_type_code


def build_main_and_detail_rows(
    mega_lines: list[ParsedLine],
    tablet_lines: list[ParsedLine],
    oee_snapshots: list[dict[str, Any]],
    window_start_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
    next_snapshot: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    window_start = window_start_snapshot["actual_dt"]
    window_end = next_snapshot["actual_dt"] if next_snapshot else target_snapshot["actual_dt"] + timedelta(minutes=1)

    main_events: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []
    completed_rows: list[dict[str, Any]] = []
    oee_rows: list[dict[str, Any]] = []
    fault_rows = parse_fault_records(tablet_lines, window_start, window_end)
    open_production: dict[str, dict[str, Any]] = {}
    ref_counter = 0
    measurement_refs: dict[int, str] = {}

    def next_ref(prefix: str) -> str:
        nonlocal ref_counter
        ref_counter += 1
        return f"{prefix}-{ref_counter:05d}"

    for line in mega_lines:
        if not (window_start <= line.actual_dt < window_end):
            continue
        parts = line.body.split("|")
        if len(parts) < 3 or parts[0] != "MEGA":
            continue
        module = parts[1]
        payload = parse_mega_kv(parts[2:])

        if module == "AUTO" and payload.get("STATE") == "MEASURING" and payload.get("REASON") == "OBJECT_DETECTED":
            event_ref = next_ref("evt")
            main_events.append({
                "event_ref": event_ref,
                "event_time": line.actual_dt,
                "source_code": "mega",
                "event_type_code": "measurement_started",
                "item_id": clean_int(payload.get("ITEM_ID")),
                "measure_id": clean_int(payload.get("MEASURE_ID")),
                "fault_id": None,
                "oee_snapshot_id": None,
                "vision_event_id": None,
                "line_id": 1,
                "station_id": station_for_event("measurement_started"),
                "color_code": "",
                "color_raw": "",
                "decision_source_code": "",
                "mega_state_code": payload.get("STATE", ""),
                "queue_depth": clean_int(payload.get("PENDING")),
                "review_required": 0,
                "travel_ms": None,
                "notes": f"search_hint={payload.get('SEARCH_HINT', '')}",
                "raw_line": line.raw_line,
                "search_hint": payload.get("SEARCH_HINT", ""),
                "sort_rank": sort_rank_for_event("measurement_started"),
            })
            continue

        if module == "TCS3200" and payload.get("STATE") == "MEASURING":
            measure_id = clean_int(payload.get("MEASURE_ID"))
            item_id = clean_int(payload.get("ITEM_ID"))
            normalized_color = normalize_color(payload.get("FINAL"))
            error_flag, error_reason = build_measurement_error_flag(normalized_color, payload.get("CONF"))
            measurement_row_id = len(measurements) + 1
            event_ref = next_ref("evt")
            measurement_refs[measurement_row_id] = event_ref
            measurements.append({
                "measurement_row_id": measurement_row_id,
                "measure_id": measure_id,
                "item_id": item_id,
                "measured_at": iso_text(line.actual_dt),
                "measurement_log_event_id": "",
                "source_log_file": line.source_file,
                "final_color_id": COLOR_ID_MAP.get(normalized_color),
                "final_color_code": normalized_color,
                "final_color_raw": clean_str(payload.get("FINAL")),
                "decision_source_id": DECISION_SOURCE_ID_MAP.get(payload.get("FINAL_SOURCE", ""), ""),
                "decision_source_code": payload.get("FINAL_SOURCE", ""),
                "search_hint": payload.get("SEARCH_HINT", ""),
                "search_hint_win": clean_int(payload.get("SEARCH_HINT_WIN")),
                "search_hint_second": clean_int(payload.get("SEARCH_HINT_SECOND")),
                "search_hint_strong": clean_int(payload.get("SEARCH_HINT_STRONG")),
                "search_hint_fallback_allowed": clean_int(payload.get("SEARCH_HINT_FALLBACK_ALLOWED")),
                "review_required": clean_int(payload.get("REVIEW")) or 0,
                "core_used": clean_int(payload.get("CORE_USED")),
                "core_n": clean_int(payload.get("CORE_N")),
                "obj_n": clean_int(payload.get("OBJ_N")),
                "median_nearest": payload.get("MEDIAN_NEAREST", ""),
                "score_nearest": payload.get("SCORE_NEAREST", ""),
                "med_r": clean_int(payload.get("MED_R")),
                "med_g": clean_int(payload.get("MED_G")),
                "med_b": clean_int(payload.get("MED_B")),
                "med_d_r": clean_int(payload.get("MED_D_R")),
                "med_d_y": clean_int(payload.get("MED_D_Y")),
                "med_d_b": clean_int(payload.get("MED_D_B")),
                "med_d_x": clean_int(payload.get("MED_D_X")),
                "x_r": clean_int(payload.get("X_R")),
                "x_g": clean_int(payload.get("X_G")),
                "x_b": clean_int(payload.get("X_B")),
                "med_obj": clean_int(payload.get("MED_OBJ")),
                "confidence": float(payload.get("CONF", "0")) if clean_str(payload.get("CONF")) else "",
                "core_str_min": clean_int(payload.get("CORE_STR_MIN")),
                "core_str_max": clean_int(payload.get("CORE_STR_MAX")),
                "vote_win": clean_int(payload.get("VOTE_WIN")),
                "vote_second": clean_int(payload.get("VOTE_SECOND")),
                "vote_classified": clean_int(payload.get("VOTE_CLASSIFIED")),
                "vote_x": clean_int(payload.get("VOTE_BOS")),
                "vote_r": clean_int(payload.get("VOTE_R")),
                "vote_y": clean_int(payload.get("VOTE_Y")),
                "vote_b": clean_int(payload.get("VOTE_B")),
                "vote_cal": clean_int(payload.get("VOTE_CAL")),
                "tot_r": clean_int(payload.get("TOT_R")),
                "tot_y": clean_int(payload.get("TOT_Y")),
                "tot_b": clean_int(payload.get("TOT_B")),
                "tot_x": clean_int(payload.get("TOT_BOS")),
                "tot_cal": clean_int(payload.get("TOT_CAL")),
                "measurement_error_flag": error_flag,
                "measurement_error_reason": error_reason,
                "raw_line": line.raw_line,
            })
            main_events.append({
                "event_ref": event_ref,
                "event_time": line.actual_dt,
                "source_code": "mega",
                "event_type_code": "measurement_decision",
                "item_id": item_id,
                "measure_id": measure_id,
                "fault_id": None,
                "oee_snapshot_id": None,
                "vision_event_id": None,
                "line_id": 1,
                "station_id": station_for_event("measurement_decision"),
                "color_code": normalized_color,
                "color_raw": clean_str(payload.get("FINAL")),
                "decision_source_code": payload.get("FINAL_SOURCE", ""),
                "mega_state_code": payload.get("STATE", ""),
                "queue_depth": clean_int(payload.get("PENDING")),
                "review_required": clean_int(payload.get("REVIEW")) or 0,
                "travel_ms": None,
                "notes": f"search_hint={payload.get('SEARCH_HINT', '')};conf={payload.get('CONF', '')}",
                "raw_line": line.raw_line,
                "sort_rank": sort_rank_for_event("measurement_decision"),
            })
            continue

        if module == "AUTO" and payload.get("QUEUE") == "ENQ":
            event_ref = next_ref("evt")
            item_id = clean_int(payload.get("ITEM_ID"))
            measure_id = clean_int(payload.get("MEASURE_ID"))
            key = str(item_id or f"measure:{measure_id}")
            open_production[key] = {
                "item_id": item_id,
                "measure_id": measure_id,
                "detected_at": line.actual_dt,
                "color_code": normalize_color(payload.get("COLOR")),
                "color_raw": clean_str(payload.get("COLOR")),
                "decision_source_code": payload.get("DECISION_SOURCE", ""),
                "travel_ms": clean_int(payload.get("TRAVEL_MS")),
                "review_required": clean_int(payload.get("REVIEW")) or 0,
                "queue_event_ref": event_ref,
            }
            main_events.append({
                "event_ref": event_ref,
                "event_time": line.actual_dt,
                "source_code": "mega",
                "event_type_code": "queue_enq",
                "item_id": item_id,
                "measure_id": measure_id,
                "fault_id": None,
                "oee_snapshot_id": None,
                "vision_event_id": None,
                "line_id": 1,
                "station_id": station_for_event("queue_enq"),
                "color_code": normalize_color(payload.get("COLOR")),
                "color_raw": clean_str(payload.get("COLOR")),
                "decision_source_code": payload.get("DECISION_SOURCE", ""),
                "mega_state_code": "QUEUE",
                "queue_depth": clean_int(payload.get("PENDING")),
                "review_required": clean_int(payload.get("REVIEW")) or 0,
                "travel_ms": clean_int(payload.get("TRAVEL_MS")),
                "notes": "",
                "raw_line": line.raw_line,
                "sort_rank": sort_rank_for_event("queue_enq"),
            })
            continue

        if module == "AUTO" and payload.get("EVENT") == "ARM_POSITION_REACHED":
            event_ref = next_ref("evt")
            main_events.append({
                "event_ref": event_ref,
                "event_time": line.actual_dt,
                "source_code": "mega",
                "event_type_code": "arm_position_reached",
                "item_id": clean_int(payload.get("ITEM_ID")),
                "measure_id": clean_int(payload.get("MEASURE_ID")),
                "fault_id": None,
                "oee_snapshot_id": None,
                "vision_event_id": None,
                "line_id": 1,
                "station_id": station_for_event("arm_position_reached"),
                "color_code": normalize_color(payload.get("COLOR")),
                "color_raw": clean_str(payload.get("COLOR")),
                "decision_source_code": payload.get("DECISION_SOURCE", ""),
                "mega_state_code": payload.get("STATE", ""),
                "queue_depth": clean_int(payload.get("PENDING")),
                "review_required": clean_int(payload.get("REVIEW")) or 0,
                "travel_ms": None,
                "notes": "",
                "raw_line": line.raw_line,
                "sort_rank": sort_rank_for_event("arm_position_reached"),
            })
            continue

        if module == "AUTO" and payload.get("EVENT") == "PICKPLACE_DONE":
            event_ref = next_ref("evt")
            item_id = clean_int(payload.get("ITEM_ID"))
            measure_id = clean_int(payload.get("MEASURE_ID"))
            key = str(item_id or f"measure:{measure_id}")
            open_row = open_production.get(key)
            if open_row:
                cycle_ms = round((line.actual_dt - open_row["detected_at"]).total_seconds() * 1000)
                completed_rows.append({
                    "production_record_id": len(completed_rows) + 1,
                    "item_id": open_row["item_id"],
                    "measure_id": open_row["measure_id"],
                    "queue_event_log_id": "",
                    "completion_event_log_id": "",
                    "detected_at": iso_text(open_row["detected_at"]),
                    "completed_at": iso_text(line.actual_dt),
                    "color_id": COLOR_ID_MAP.get(open_row["color_code"], ""),
                    "color_code": open_row["color_code"],
                    "color_raw": open_row["color_raw"],
                    "status_code": "COMPLETED_REVIEW" if open_row["review_required"] else "COMPLETED",
                    "status_tr": "Inceleme gerekli" if open_row["review_required"] else "Tamamlandi",
                    "travel_ms": open_row["travel_ms"],
                    "cycle_ms": cycle_ms,
                    "decision_source_id": DECISION_SOURCE_ID_MAP.get(open_row["decision_source_code"], ""),
                    "decision_source_code": open_row["decision_source_code"],
                    "review_required": open_row["review_required"],
                    "queue_event_ref": open_row["queue_event_ref"],
                    "completion_event_ref": event_ref,
                })
                del open_production[key]

            main_events.append({
                "event_ref": event_ref,
                "event_time": line.actual_dt,
                "source_code": "mega",
                "event_type_code": "pickplace_done",
                "item_id": item_id,
                "measure_id": measure_id,
                "fault_id": None,
                "oee_snapshot_id": None,
                "vision_event_id": None,
                "line_id": 1,
                "station_id": station_for_event("pickplace_done"),
                "color_code": normalize_color(payload.get("COLOR")),
                "color_raw": clean_str(payload.get("COLOR")),
                "decision_source_code": payload.get("DECISION_SOURCE", ""),
                "mega_state_code": payload.get("STATE", ""),
                "queue_depth": clean_int(payload.get("PENDING") or payload.get("QUEUE")),
                "review_required": clean_int(payload.get("REVIEW")) or 0,
                "travel_ms": None,
                "notes": "",
                "raw_line": line.raw_line,
                "sort_rank": sort_rank_for_event("pickplace_done"),
            })

    oee_index = 0
    for snapshot in oee_snapshots:
        if not (window_start <= snapshot["actual_dt"] <= target_snapshot["actual_dt"]):
            continue
        oee_index += 1
        oee_event_ref = next_ref("evt")
        oee_rows.append({
            "oee_snapshot_id": oee_index,
            "snapshot_time": iso_text(snapshot["actual_dt"]),
            "event_log_id": "",
            "sample_cycle_tag": "2026-03-25_full_cycle_reference",
            "oee": snapshot.get("OEE", ""),
            "availability": snapshot.get("KULL", ""),
            "performance": snapshot.get("PERF", ""),
            "quality": snapshot.get("KALITE", ""),
            "mavi_s": snapshot.get("MAVI_S", 0),
            "mavi_r": snapshot.get("MAVI_R", 0),
            "mavi_h": snapshot.get("MAVI_H", 0),
            "sari_s": snapshot.get("SARI_S", 0),
            "sari_r": snapshot.get("SARI_R", 0),
            "sari_h": snapshot.get("SARI_H", 0),
            "kirmizi_s": snapshot.get("KIRMIZI_S", 0),
            "kirmizi_r": snapshot.get("KIRMIZI_R", 0),
            "kirmizi_h": snapshot.get("KIRMIZI_H", 0),
            "is_full_cycle_reference": 1 if snapshot["actual_dt"] == target_snapshot["actual_dt"] else 0,
            "notes": "Kullanici tarafindan isaretlenen hatasiz tam cevrim" if snapshot["actual_dt"] == target_snapshot["actual_dt"] else "",
            "raw_line": snapshot["raw_line"],
            "event_ref": oee_event_ref,
        })
        main_events.append({
            "event_ref": oee_event_ref,
            "event_time": snapshot["actual_dt"],
            "source_code": "tablet",
            "event_type_code": "oee_snapshot",
            "item_id": None,
            "measure_id": None,
            "fault_id": None,
            "oee_snapshot_id": oee_index,
            "vision_event_id": None,
            "line_id": 1,
            "station_id": station_for_event("oee_snapshot"),
            "color_code": "",
            "color_raw": "",
            "decision_source_code": "TABLET",
            "mega_state_code": "",
            "queue_depth": None,
            "review_required": 0,
            "travel_ms": None,
            "notes": "",
            "raw_line": snapshot["raw_line"],
            "MAVI_S": snapshot.get("MAVI_S", 0),
            "SARI_S": snapshot.get("SARI_S", 0),
            "KIRMIZI_S": snapshot.get("KIRMIZI_S", 0),
            "sort_rank": sort_rank_for_event("oee_snapshot"),
        })

    for fault in fault_rows:
        start_ref = next_ref("evt")
        stop_ref = next_ref("evt")
        resolve_ref = next_ref("evt")
        restart_ref = next_ref("evt")
        fault["fault_reported_ref"] = start_ref
        fault["fault_resolved_ref"] = resolve_ref
        reason = fault["reason"]
        main_events.extend([
            {"event_ref": start_ref, "event_time": fault["started_at"], "source_code": "tablet", "event_type_code": "fault_reported", "item_id": None, "measure_id": None, "fault_id": fault["fault_id"], "oee_snapshot_id": None, "vision_event_id": None, "line_id": 1, "station_id": 4, "color_code": "", "color_raw": "", "decision_source_code": "TABLET", "mega_state_code": "STOPPED", "queue_depth": None, "review_required": 0, "travel_ms": None, "notes": fault["category"], "raw_line": fault["start_raw_line"], "fault_reason_tr": reason, "sort_rank": sort_rank_for_event("fault_reported")},
            {"event_ref": stop_ref, "event_time": fault["started_at"], "source_code": "tablet", "event_type_code": "conveyor_stopped", "item_id": None, "measure_id": None, "fault_id": fault["fault_id"], "oee_snapshot_id": None, "vision_event_id": None, "line_id": 1, "station_id": 5, "color_code": "", "color_raw": "", "decision_source_code": "TABLET", "mega_state_code": "STOPPED", "queue_depth": None, "review_required": 0, "travel_ms": None, "notes": reason, "raw_line": fault["start_raw_line"], "fault_reason_tr": reason, "sort_rank": sort_rank_for_event("conveyor_stopped")},
            {"event_ref": resolve_ref, "event_time": fault["ended_at"], "source_code": "tablet", "event_type_code": "fault_resolved", "item_id": None, "measure_id": None, "fault_id": fault["fault_id"], "oee_snapshot_id": None, "vision_event_id": None, "line_id": 1, "station_id": 4, "color_code": "", "color_raw": "", "decision_source_code": "TABLET", "mega_state_code": "SEARCHING", "queue_depth": None, "review_required": 0, "travel_ms": None, "notes": reason, "raw_line": fault["end_raw_line"], "fault_reason_tr": reason, "sort_rank": sort_rank_for_event("fault_resolved")},
            {"event_ref": restart_ref, "event_time": fault["ended_at"], "source_code": "tablet", "event_type_code": "conveyor_started", "item_id": None, "measure_id": None, "fault_id": fault["fault_id"], "oee_snapshot_id": None, "vision_event_id": None, "line_id": 1, "station_id": 5, "color_code": "", "color_raw": "", "decision_source_code": "TABLET", "mega_state_code": "SEARCHING", "queue_depth": None, "review_required": 0, "travel_ms": None, "notes": reason, "raw_line": fault["end_raw_line"], "fault_reason_tr": reason, "sort_rank": sort_rank_for_event("conveyor_started")},
        ])

    main_events.sort(key=lambda row: (row["event_time"], row["sort_rank"], row["event_ref"]))
    event_id_map: dict[str, int] = {}
    for index, event in enumerate(main_events, start=1):
        event["log_event_id"] = index
        event_id_map[event["event_ref"]] = index
        event["source_id"] = SOURCE_ID_MAP[event["source_code"]]
        event["event_type_id"] = EVENT_TYPE_ID_MAP[event["event_type_code"]]
        event["color_id"] = COLOR_ID_MAP.get(event["color_code"], "")
        event["decision_source_id"] = DECISION_SOURCE_ID_MAP.get(event["decision_source_code"], "")
        event["mega_state_id"] = MEGA_STATE_ID_MAP.get(event["mega_state_code"], "")
        event["event_time_text"] = iso_text(event["event_time"])
        event["event_summary_tr"] = build_summary(event["event_type_code"], event)

    for measurement in measurements:
        measurement["measurement_log_event_id"] = event_id_map[measurement_refs[measurement["measurement_row_id"]]]
    for oee_row in oee_rows:
        oee_row["event_log_id"] = event_id_map[oee_row["event_ref"]]
        del oee_row["event_ref"]
    for completed in completed_rows:
        completed["queue_event_log_id"] = event_id_map.get(completed["queue_event_ref"], "")
        completed["completion_event_log_id"] = event_id_map.get(completed["completion_event_ref"], "")
        del completed["queue_event_ref"]
        del completed["completion_event_ref"]
    for fault in fault_rows:
        fault["fault_report_log_event_id"] = event_id_map.get(fault["fault_reported_ref"], "")
        fault["fault_resolve_log_event_id"] = event_id_map.get(fault["fault_resolved_ref"], "")
        del fault["fault_reported_ref"]
        del fault["fault_resolved_ref"]

    vision_rows = [{
        "vision_event_id": 1, "event_time": "", "source_code": "vision", "vision_track_id": "sample-track-001", "event_type": "line_crossed",
        "color_id": 3, "color_code": "blue", "item_id": "", "measure_id": "", "confidence": 0.98, "line_id": 1, "station_id": 6,
        "bbox_x1": 140, "bbox_y1": 80, "bbox_x2": 240, "bbox_y2": 180, "direction": "left_to_right", "is_placeholder": 1,
        "notes": "Ornek placeholder satiri. Gercek vision verisi sau/iot/mega/konveyor/vision/events altindan beklenir.",
    }]
    return main_events, measurements, fault_rows, completed_rows, oee_rows, vision_rows


def col_letter(index: int) -> str:
    result = []
    while index > 0:
        index, rem = divmod(index - 1, 26)
        result.append(chr(65 + rem))
    return "".join(reversed(result))


def xml_cell(row_idx: int, col_idx: int, value: Any, style_id: int | None = None) -> str:
    ref = f"{col_letter(col_idx)}{row_idx}"
    attrs = [f'r="{ref}"']
    if style_id is not None:
        attrs.append(f's="{style_id}"')
    if value is None or value == "":
        return f"<c {' '.join(attrs)}/>"
    if isinstance(value, bool):
        return f"<c {' '.join(attrs)} t=\"b\"><v>{1 if value else 0}</v></c>"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return f"<c {' '.join(attrs)}/>"
        return f"<c {' '.join(attrs)}><v>{value:.15g}</v></c>"
    text = escape(str(value))
    return f"<c {' '.join(attrs)} t=\"inlineStr\"><is><t xml:space=\"preserve\">{text}</t></is></c>"


def compute_widths(rows: list[list[Any]]) -> list[float]:
    max_cols = max((len(row) for row in rows), default=0)
    widths: list[float] = []
    for col_idx in range(max_cols):
        longest = 8
        for row in rows:
            text = "" if col_idx >= len(row) or row[col_idx] is None else str(row[col_idx])
            longest = max(longest, len(text))
        widths.append(float(min(max(longest + 2, 10), 60)))
    return widths


def build_sheet_xml(
    rows: list[list[Any]],
    header_rows: set[int] | None = None,
    title_rows: set[int] | None = None,
    placeholder_rows: set[int] | None = None,
    freeze_top_row: bool = False,
    apply_filter: bool = False,
    default_style_id: int = 3,
) -> str:
    header_rows = header_rows or set()
    title_rows = title_rows or set()
    placeholder_rows = placeholder_rows or set()
    max_cols = max((len(row) for row in rows), default=1)
    max_rows = max(len(rows), 1)
    dimension = f"A1:{col_letter(max_cols)}{max_rows}"
    widths = compute_widths(rows)

    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    ]
    parts.append(f"<dimension ref=\"{dimension}\"/>")
    if freeze_top_row:
        parts.append(
            "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/>"
            "<selection pane=\"bottomLeft\" activeCell=\"A2\" sqref=\"A2\"/></sheetView></sheetViews>"
        )
    else:
        parts.append("<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>")
    parts.append("<sheetFormatPr defaultRowHeight=\"15\"/>")
    if widths:
        parts.append("<cols>" + "".join(
            f"<col min=\"{idx}\" max=\"{idx}\" width=\"{width}\" customWidth=\"1\"/>"
            for idx, width in enumerate(widths, start=1)
        ) + "</cols>")
    parts.append("<sheetData>")
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            style_id = 2 if row_idx in title_rows else 1 if row_idx in header_rows else 4 if row_idx in placeholder_rows else default_style_id
            if value in {None, ""} and row_idx not in title_rows:
                continue
            cells.append(xml_cell(row_idx, col_idx, value, style_id))
        parts.append(f"<row r=\"{row_idx}\">{''.join(cells)}</row>")
    parts.append("</sheetData>")
    if apply_filter and rows:
        parts.append(f"<autoFilter ref=\"A1:{col_letter(max_cols)}1\"/>")
    parts.append("</worksheet>")
    return "".join(parts)


def build_styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><i/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF6B26B"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9EAD3"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/><xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def render_definition_sheet() -> list[list[Any]]:
    tables = [
        ("renkler", ["color_id", "color_code", "color_code_raw", "color_name_tr", "is_sortable"], COLOR_ROWS),
        ("olay_tipleri", ["event_type_id", "event_type_code", "event_name_tr", "detail_sheet"], EVENT_TYPE_ROWS),
        ("ariza_tipleri", ["fault_type_id", "fault_type_code", "fault_category", "fault_reason_tr", "default_station_id"], FAULT_TYPE_ROWS),
        ("karar_kaynaklari", ["decision_source_id", "decision_source_code", "description_tr"], DECISION_SOURCE_ROWS),
        ("kaynaklar", ["source_id", "source_code", "source_name_tr", "source_role"], SOURCE_ROWS),
        ("mega_durumlari", ["mega_state_id", "mega_state_code", "mega_state_tr"], MEGA_STATE_ROWS),
        ("hatlar", ["line_id", "line_code", "line_name_tr", "erp_ready"], LINE_ROWS),
        ("istasyonlar", ["station_id", "station_code", "station_name_tr", "line_id"], STATION_ROWS),
        ("urunler", ["product_id", "product_code", "product_name_tr", "color_id"], PRODUCT_ROWS),
        ("operatorler", ["operator_id", "operator_code", "operator_name", "source_note"], OPERATOR_ROWS),
        ("vardiyalar", ["shift_id", "shift_code", "shift_name_tr", "is_default"], SHIFT_ROWS),
    ]
    cell_map: dict[tuple[int, int], Any] = {}
    start_col = 1
    max_row = 0
    max_col = 0
    for title, headers, rows in tables:
        cell_map[(1, start_col)] = title
        for offset, header in enumerate(headers):
            cell_map[(2, start_col + offset)] = header
        for row_offset, row in enumerate(rows, start=3):
            for col_offset, header in enumerate(headers):
                cell_map[(row_offset, start_col + col_offset)] = row.get(header, "")
            max_row = max(max_row, row_offset)
        max_col = max(max_col, start_col + len(headers) - 1)
        start_col += len(headers) + 2
    return [[cell_map.get((row_idx, col_idx), "") for col_idx in range(1, max_col + 1)] for row_idx in range(1, max_row + 1)]


def rows_from_dicts(columns: list[str], data_rows: list[dict[str, Any]]) -> list[list[Any]]:
    return [columns] + [[row.get(column, "") for column in columns] for row in data_rows]


def write_workbook(sheets: list[tuple[str, str]]) -> None:
    workbook_xml = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="12000"/></bookViews>',
        "<sheets>",
    ]
    rels_xml = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for index, (sheet_name, _) in enumerate(sheets, start=1):
        workbook_xml.append(f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>')
        rels_xml.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    rels_xml.append(f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    workbook_xml.append("</sheets></workbook>")
    rels_xml.append("</Relationships>")
    content_types.append("</Types>")

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:creator>Codex</dc:creator><cp:lastModifiedBy>Codex</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        '<dc:title>MES Konveyor Veritabani Sablonu</dc:title></cp:coreProperties>'
    )
    titles = "".join(f'<vt:lpstr>{escape(sheet_name)}</vt:lpstr>' for sheet_name, _ in sheets)
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Codex</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>'
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>'
        f'<vt:variant><vt:i4>{len(sheets)}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        f'<TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts></Properties>'
    )
    with zipfile.ZipFile(OUTPUT_FILE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(content_types))
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("xl/workbook.xml", "".join(workbook_xml))
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(rels_xml))
        archive.writestr("xl/styles.xml", build_styles_xml())
        for index, (_, sheet_xml) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet_xml)


def main() -> None:
    mega_lines = load_mega_lines()
    tablet_lines = load_tablet_lines()
    oee_snapshots = parse_oee_snapshots(tablet_lines)
    window_start_snapshot, target_snapshot, next_snapshot = find_sample_window(oee_snapshots)
    main_events, measurements, faults, completed_rows, oee_rows, vision_rows = build_main_and_detail_rows(
        mega_lines=mega_lines,
        tablet_lines=tablet_lines,
        oee_snapshots=oee_snapshots,
        window_start_snapshot=window_start_snapshot,
        target_snapshot=target_snapshot,
        next_snapshot=next_snapshot,
    )

    definition_rows = render_definition_sheet()
    main_event_columns = ["log_event_id", "event_time_text", "source_id", "source_code", "event_type_id", "event_type_code", "event_summary_tr", "item_id", "measure_id", "fault_id", "oee_snapshot_id", "vision_event_id", "line_id", "station_id", "color_id", "color_code", "decision_source_id", "decision_source_code", "mega_state_id", "mega_state_code", "queue_depth", "review_required", "travel_ms", "notes", "raw_line"]
    measurement_columns = ["measurement_row_id", "measure_id", "item_id", "measured_at", "measurement_log_event_id", "source_log_file", "final_color_id", "final_color_code", "final_color_raw", "decision_source_id", "decision_source_code", "search_hint", "search_hint_win", "search_hint_second", "search_hint_strong", "search_hint_fallback_allowed", "review_required", "core_used", "core_n", "obj_n", "median_nearest", "score_nearest", "med_r", "med_g", "med_b", "med_d_r", "med_d_y", "med_d_b", "med_d_x", "x_r", "x_g", "x_b", "med_obj", "confidence", "core_str_min", "core_str_max", "vote_win", "vote_second", "vote_classified", "vote_x", "vote_r", "vote_y", "vote_b", "vote_cal", "tot_r", "tot_y", "tot_b", "tot_x", "tot_cal", "measurement_error_flag", "measurement_error_reason", "raw_line"]
    fault_columns = ["fault_id", "fault_report_log_event_id", "fault_resolve_log_event_id", "line_id", "station_id", "operator_id", "source_code", "fault_type_id", "fault_type_code", "category", "reason", "started_at", "ended_at", "duration_minutes", "duration_seconds", "status", "resolved_flag", "start_raw_line", "end_raw_line"]
    completed_columns = ["production_record_id", "item_id", "measure_id", "queue_event_log_id", "completion_event_log_id", "detected_at", "completed_at", "color_id", "color_code", "color_raw", "status_code", "status_tr", "travel_ms", "cycle_ms", "decision_source_id", "decision_source_code", "review_required"]
    oee_columns = ["oee_snapshot_id", "snapshot_time", "event_log_id", "sample_cycle_tag", "oee", "availability", "performance", "quality", "mavi_s", "mavi_r", "mavi_h", "sari_s", "sari_r", "sari_h", "kirmizi_s", "kirmizi_r", "kirmizi_h", "is_full_cycle_reference", "notes", "raw_line"]
    vision_columns = ["vision_event_id", "event_time", "source_code", "vision_track_id", "event_type", "color_id", "color_code", "item_id", "measure_id", "confidence", "line_id", "station_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "direction", "is_placeholder", "notes"]

    fault_export_rows = [{
        "fault_id": row["fault_id"], "fault_report_log_event_id": row["fault_report_log_event_id"], "fault_resolve_log_event_id": row["fault_resolve_log_event_id"],
        "line_id": row["line_id"], "station_id": row["station_id"], "operator_id": row["operator_id"], "source_code": row["source_code"],
        "fault_type_id": row["fault_type"]["fault_type_id"], "fault_type_code": row["fault_type"]["fault_type_code"], "category": row["category"], "reason": row["reason"],
        "started_at": iso_text(row["started_at"]), "ended_at": iso_text(row["ended_at"]), "duration_minutes": row["duration_minutes"], "duration_seconds": row["duration_seconds"],
        "status": row["status"], "resolved_flag": row["resolved_flag"], "start_raw_line": row["start_raw_line"], "end_raw_line": row["end_raw_line"],
    } for row in faults]

    sheets = [
        ("0_Tanimlamalar", build_sheet_xml(definition_rows, header_rows={2}, title_rows={1})),
        ("1_Olay_Logu", build_sheet_xml(rows_from_dicts(main_event_columns, main_events), header_rows={1}, freeze_top_row=True, apply_filter=True)),
        ("2_Olcumler", build_sheet_xml(rows_from_dicts(measurement_columns, measurements), header_rows={1}, freeze_top_row=True, apply_filter=True)),
        ("3_Arizalar", build_sheet_xml(rows_from_dicts(fault_columns, fault_export_rows), header_rows={1}, freeze_top_row=True, apply_filter=True)),
        ("4_Uretim_Tamamlanan", build_sheet_xml(rows_from_dicts(completed_columns, completed_rows), header_rows={1}, freeze_top_row=True, apply_filter=True)),
        ("5_OEE_Anliklari", build_sheet_xml(rows_from_dicts(oee_columns, oee_rows), header_rows={1}, freeze_top_row=True, apply_filter=True)),
        ("6_Vision", build_sheet_xml(rows_from_dicts(vision_columns, vision_rows), header_rows={1}, placeholder_rows={2}, freeze_top_row=True, apply_filter=True)),
    ]
    write_workbook(sheets)

    print(f"Created {OUTPUT_FILE}")
    print(f"Main log rows: {len(main_events)}")
    print(f"Measurements: {len(measurements)}")
    print(f"Faults: {len(faults)}")
    print(f"Completed rows: {len(completed_rows)}")
    print(f"OEE snapshots: {len(oee_rows)}")


if __name__ == "__main__":
    main()
