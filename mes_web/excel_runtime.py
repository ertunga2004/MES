from __future__ import annotations

import json
import queue
import shutil
import threading
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .parsers import normalize_color, parse_mega_event_from_log, parse_vision_event


EVENT_LOG_COLUMNS = [
    "log_event_id", "event_time_text", "source_id", "source_code", "event_type_id", "event_type_code", "event_summary_tr",
    "item_id", "measure_id", "fault_id", "oee_snapshot_id", "vision_event_id", "line_id", "station_id", "color_id",
    "color_code", "decision_source_id", "decision_source_code", "mega_state_id", "mega_state_code", "queue_depth",
    "review_required", "travel_ms", "notes", "raw_line",
]
MEASUREMENT_COLUMNS = [
    "measurement_row_id", "measure_id", "item_id", "measured_at", "measurement_log_event_id", "source_log_file",
    "final_color_id", "final_color_code", "final_color_raw", "decision_source_id", "decision_source_code",
    "search_hint", "search_hint_win", "search_hint_second", "search_hint_strong", "search_hint_fallback_allowed",
    "review_required", "core_used", "core_n", "obj_n", "median_nearest", "score_nearest", "med_r", "med_g", "med_b",
    "med_d_r", "med_d_y", "med_d_b", "med_d_x", "x_r", "x_g", "x_b", "med_obj", "confidence", "core_str_min",
    "core_str_max", "vote_win", "vote_second", "vote_classified", "vote_x", "vote_r", "vote_y", "vote_b", "vote_cal",
    "tot_r", "tot_y", "tot_b", "tot_x", "tot_cal", "measurement_error_flag", "measurement_error_reason", "raw_line",
]
COMPLETED_COLUMNS = [
    "production_record_id", "item_id", "measure_id", "queue_event_log_id", "completion_event_log_id", "detected_at",
    "completed_at", "color_id", "color_code", "color_raw", "status_code", "status_tr", "travel_ms", "cycle_ms",
    "decision_source_id", "decision_source_code", "review_required",
]
VISION_COLUMNS = [
    "vision_event_id", "event_time", "source_code", "vision_track_id", "event_type", "color_id", "color_code", "item_id",
    "measure_id", "confidence", "line_id", "station_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "direction",
    "is_placeholder", "notes",
]
RAW_LOG_COLUMNS = [
    "raw_log_id", "logged_at", "source_topic", "source_code", "parsed_flag", "event_type_code", "item_id", "measure_id",
    "color_code", "notes", "raw_payload",
]

SHEET_COLUMNS = {
    "1_Olay_Logu": EVENT_LOG_COLUMNS,
    "2_Olcumler": MEASUREMENT_COLUMNS,
    "4_Uretim_Tamamlanan": COMPLETED_COLUMNS,
    "6_Vision": VISION_COLUMNS,
    "7_Raw_Logs": RAW_LOG_COLUMNS,
}

SOURCE_IDS = {"mega": 1, "tablet": 2, "vision": 3, "system": 4}
COLOR_IDS = {"red": 1, "yellow": 2, "blue": 3, "empty": 4, "uncertain": 5}
EVENT_TYPE_IDS = {"measurement_decision": 2, "queue_enq": 3, "arm_position_reached": 4, "pickplace_done": 5, "vision_event": 11}
DECISION_SOURCE_IDS = {"CORE_STABLE": 1, "MEDIAN_STABLE": 2, "CORE_VOTE_MATCH": 3, "VISION": 4, "TABLET": 5, "SYSTEM": 6}
MEGA_STATE_IDS = {"SEARCH": 1, "SEARCHING": 2, "MEASURING": 3, "WAIT_ARM": 4, "PAUSED": 5, "STOPPED": 6, "QUEUE": 7}


def _station_for_event(event_type_code: str) -> int:
    if event_type_code in {"measurement_decision"}:
        return 1
    if event_type_code == "queue_enq":
        return 2
    if event_type_code in {"arm_position_reached", "pickplace_done"}:
        return 3
    return 6 if event_type_code == "vision_event" else 5


def _decision_source_id(value: str | None) -> int | str:
    code = str(value or "").strip().upper()
    return DECISION_SOURCE_IDS.get(code, "")


def _color_id(value: str | None) -> int | str:
    return COLOR_IDS.get(str(value or "").strip().lower(), "")


def _mega_state_id(value: str | None) -> int | str:
    code = str(value or "").strip().upper()
    return MEGA_STATE_IDS.get(code, "")


def _json_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _safe_int(value: Any) -> int | str:
    if value in (None, ""):
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return ""


def _measurement_error_info(final_color: str, confidence: Any) -> tuple[int, str]:
    if final_color in {"empty", "uncertain"}:
        return 1, "final_color_invalid"
    text = str(confidence or "").strip()
    if text in {"0", "0.0", "false", "False"}:
        return 1, "confidence=0"
    return 0, ""


@dataclass(slots=True)
class SinkEnvelope:
    kind: str
    received_at: str
    payload: Any


class WorkbookProjector:
    def __init__(self) -> None:
        self.counters = {
            "log_event_id": 1,
            "measurement_row_id": 1,
            "production_record_id": 1,
            "vision_event_id": 1,
            "raw_log_id": 1,
        }
        self.completed_state: dict[str, dict[str, Any]] = {}

    def prime(self, counters: dict[str, int]) -> None:
        self.counters.update(counters)

    def _next(self, key: str) -> int:
        value = self.counters[key]
        self.counters[key] += 1
        return value

    def _completed_key(self, item_id: str | None, measure_id: str | None) -> str:
        return str(item_id or "").strip() or f"measure:{str(measure_id or '').strip()}"

    def _raw_row(self, *, received_at: str, source_topic: str, source_code: str, raw_payload: Any, parsed_flag: int, event_type_code: str = "", item_id: str = "", measure_id: str = "", color_code: str = "", notes: str = "") -> dict[str, Any]:
        return {
            "raw_log_id": self._next("raw_log_id"),
            "logged_at": received_at,
            "source_topic": source_topic,
            "source_code": source_code,
            "parsed_flag": parsed_flag,
            "event_type_code": event_type_code,
            "item_id": item_id,
            "measure_id": measure_id,
            "color_code": color_code,
            "notes": notes,
            "raw_payload": _json_text(raw_payload),
        }

    def _event_row(self, *, log_event_id: int, received_at: str, source_code: str, event_type_code: str, item_id: str = "", measure_id: str = "", color_code: str = "", decision_source_code: str = "", mega_state_code: str = "", queue_depth: Any = "", review_required: Any = "", travel_ms: Any = "", notes: str = "", raw_line: str = "", event_summary_tr: str = "", vision_event_id: Any = "") -> dict[str, Any]:
        normalized_color = normalize_color(color_code)
        event_id_key = "vision_event" if event_type_code == "vision_event" else event_type_code
        return {
            "log_event_id": log_event_id,
            "event_time_text": received_at,
            "source_id": SOURCE_IDS.get(source_code, ""),
            "source_code": source_code,
            "event_type_id": EVENT_TYPE_IDS.get(event_id_key, ""),
            "event_type_code": event_type_code,
            "event_summary_tr": event_summary_tr,
            "item_id": item_id,
            "measure_id": measure_id,
            "fault_id": "",
            "oee_snapshot_id": "",
            "vision_event_id": vision_event_id,
            "line_id": 1,
            "station_id": _station_for_event(event_id_key),
            "color_id": _color_id(normalized_color),
            "color_code": normalized_color if normalized_color != "unknown" else "",
            "decision_source_id": _decision_source_id(decision_source_code),
            "decision_source_code": str(decision_source_code or "").strip().upper(),
            "mega_state_id": _mega_state_id(mega_state_code),
            "mega_state_code": mega_state_code,
            "queue_depth": _safe_int(queue_depth),
            "review_required": 1 if review_required is True else (0 if review_required is False else ""),
            "travel_ms": _safe_int(travel_ms),
            "notes": notes,
            "raw_line": raw_line,
        }

    def consume_local_counts_reset(self, received_at: str) -> dict[str, list[dict[str, Any]]]:
        return {
            "1_Olay_Logu": [self._event_row(log_event_id=self._next("log_event_id"), received_at=received_at, source_code="system", event_type_code="counts_reset", notes="UI sayac sifirlama islemi", raw_line="SYSTEM|COUNTS|RESET", event_summary_tr="UI uzerinden renk sayaclari sifirlandi")],
            "7_Raw_Logs": [self._raw_row(received_at=received_at, source_topic="local/system", source_code="system", raw_payload="SYSTEM|COUNTS|RESET", parsed_flag=1, event_type_code="counts_reset", notes="local_only")],
        }

    def consume_mega_log(self, raw_line: str, received_at: str) -> dict[str, list[dict[str, Any]]]:
        rows = {"7_Raw_Logs": [self._raw_row(received_at=received_at, source_topic="sau/iot/mega/konveyor/logs", source_code="mega", raw_payload=raw_line, parsed_flag=0)]}
        parsed = parse_mega_event_from_log(raw_line)
        if parsed is None:
            return rows
        rows["7_Raw_Logs"][0].update({"parsed_flag": 1, "event_type_code": parsed["event_type"], "item_id": parsed["item_id"], "measure_id": parsed["measure_id"], "color_code": parsed["color"]})
        log_event_id = self._next("log_event_id")
        raw = parsed["raw"]
        summary = {
            "measurement_decision": f"Olcum karari verildi: {parsed['color']}",
            "queue_enq": f"Urun kuyruga alindi: {parsed['color']}",
            "arm_position_reached": "Robot kol hedefe ulasti",
            "pickplace_done": "Pick and place tamamlandi",
        }.get(parsed["event_type"], parsed["event_type"])
        note_parts: list[str] = []
        if parsed["event_type"] == "measurement_decision" and raw.get("SEARCH_HINT"):
            note_parts.append(f"search_hint={raw.get('SEARCH_HINT')}")
        if parsed["event_type"] == "measurement_decision" and raw.get("CONF") not in (None, ""):
            note_parts.append(f"conf={raw.get('CONF')}")
        rows["1_Olay_Logu"] = [self._event_row(log_event_id=log_event_id, received_at=received_at, source_code="mega", event_type_code=parsed["event_type"], item_id=parsed["item_id"], measure_id=parsed["measure_id"], color_code=parsed["color"], decision_source_code=parsed["decision_source"], mega_state_code=parsed["mega_state"], queue_depth=parsed["queue_depth"], review_required=parsed["review_required"], travel_ms=parsed["travel_ms"], notes=";".join(note_parts), raw_line=raw_line, event_summary_tr=summary)]

        key = self._completed_key(parsed["item_id"], parsed["measure_id"])
        if parsed["event_type"] == "measurement_decision":
            error_flag, error_reason = _measurement_error_info(parsed["color"], raw.get("CONF"))
            rows["2_Olcumler"] = [{
                "measurement_row_id": self._next("measurement_row_id"),
                "measure_id": parsed["measure_id"],
                "item_id": parsed["item_id"],
                "measured_at": received_at,
                "measurement_log_event_id": log_event_id,
                "source_log_file": "mqtt/logs",
                "final_color_id": _color_id(parsed["color"]),
                "final_color_code": parsed["color"],
                "final_color_raw": raw.get("FINAL", ""),
                "decision_source_id": _decision_source_id(parsed["decision_source"]),
                "decision_source_code": str(parsed["decision_source"] or "").upper(),
                "search_hint": str(raw.get("SEARCH_HINT") or ""),
                "search_hint_win": _safe_int(raw.get("SEARCH_HINT_WIN")),
                "search_hint_second": _safe_int(raw.get("SEARCH_HINT_SECOND")),
                "search_hint_strong": _safe_int(raw.get("SEARCH_HINT_STRONG")),
                "search_hint_fallback_allowed": _safe_int(raw.get("SEARCH_HINT_FALLBACK_ALLOWED")),
                "review_required": 1 if parsed["review_required"] else 0,
                "core_used": _safe_int(raw.get("CORE_USED")),
                "core_n": _safe_int(raw.get("CORE_N")),
                "obj_n": _safe_int(raw.get("OBJ_N")),
                "median_nearest": str(raw.get("MEDIAN_NEAREST") or ""),
                "score_nearest": str(raw.get("SCORE_NEAREST") or ""),
                "med_r": _safe_int(raw.get("MED_R")),
                "med_g": _safe_int(raw.get("MED_G")),
                "med_b": _safe_int(raw.get("MED_B")),
                "med_d_r": _safe_int(raw.get("MED_D_R")),
                "med_d_y": _safe_int(raw.get("MED_D_Y")),
                "med_d_b": _safe_int(raw.get("MED_D_B")),
                "med_d_x": _safe_int(raw.get("MED_D_X")),
                "x_r": _safe_int(raw.get("X_R")),
                "x_g": _safe_int(raw.get("X_G")),
                "x_b": _safe_int(raw.get("X_B")),
                "med_obj": _safe_int(raw.get("MED_OBJ")),
                "confidence": raw.get("CONF", ""),
                "core_str_min": _safe_int(raw.get("CORE_STR_MIN")),
                "core_str_max": _safe_int(raw.get("CORE_STR_MAX")),
                "vote_win": _safe_int(raw.get("VOTE_WIN")),
                "vote_y": _safe_int(raw.get("VOTE_Y")),
                "vote_second": _safe_int(raw.get("VOTE_SECOND")),
                "vote_classified": _safe_int(raw.get("VOTE_CLASSIFIED")),
                "vote_x": _safe_int(raw.get("VOTE_BOS")),
                "vote_r": _safe_int(raw.get("VOTE_R")),
                "vote_b": _safe_int(raw.get("VOTE_B")),
                "vote_cal": _safe_int(raw.get("VOTE_CAL")),
                "tot_r": _safe_int(raw.get("TOT_R")),
                "tot_y": _safe_int(raw.get("TOT_Y")),
                "tot_b": _safe_int(raw.get("TOT_B")),
                "tot_x": _safe_int(raw.get("TOT_BOS")),
                "tot_cal": _safe_int(raw.get("TOT_CAL")),
                "measurement_error_flag": error_flag,
                "measurement_error_reason": error_reason,
                "raw_line": raw_line,
            }]
            self.completed_state.setdefault(key, {}).update({"item_id": parsed["item_id"], "measure_id": parsed["measure_id"], "color": parsed["color"], "decision_source": parsed["decision_source"], "review_required": parsed["review_required"]})
        elif parsed["event_type"] == "queue_enq":
            self.completed_state.setdefault(key, {}).update({"item_id": parsed["item_id"], "measure_id": parsed["measure_id"], "detected_at": received_at, "color": parsed["color"], "travel_ms": parsed["travel_ms"], "decision_source": parsed["decision_source"], "review_required": parsed["review_required"], "queue_event_log_id": log_event_id})
        elif parsed["event_type"] == "pickplace_done":
            state = self.completed_state.get(key, {})
            detected_at = state.get("detected_at", "")
            cycle_ms = ""
            if detected_at:
                try:
                    from datetime import datetime
                    cycle_ms = int((datetime.fromisoformat(received_at.replace("Z", "+00:00")) - datetime.fromisoformat(str(detected_at).replace("Z", "+00:00"))).total_seconds() * 1000)
                except ValueError:
                    cycle_ms = ""
            rows["4_Uretim_Tamamlanan"] = [{
                "production_record_id": self._next("production_record_id"),
                "item_id": state.get("item_id", parsed["item_id"]),
                "measure_id": state.get("measure_id", parsed["measure_id"]),
                "queue_event_log_id": state.get("queue_event_log_id", ""),
                "completion_event_log_id": log_event_id,
                "detected_at": detected_at,
                "completed_at": received_at,
                "color_id": _color_id(state.get("color", parsed["color"])),
                "color_code": state.get("color", parsed["color"]),
                "color_raw": state.get("color", parsed["color"]),
                "status_code": "COMPLETED_REVIEW" if state.get("review_required", parsed["review_required"]) else "COMPLETED",
                "status_tr": "Inceleme gerekli" if state.get("review_required", parsed["review_required"]) else "Tamamlandi",
                "travel_ms": _safe_int(state.get("travel_ms", parsed["travel_ms"])),
                "cycle_ms": cycle_ms,
                "decision_source_id": _decision_source_id(state.get("decision_source", parsed["decision_source"])),
                "decision_source_code": str(state.get("decision_source", parsed["decision_source"]) or "").upper(),
                "review_required": 1 if state.get("review_required", parsed["review_required"]) else 0,
            }]
            self.completed_state.pop(key, None)
        return rows

    def consume_vision_event(self, payload: Any, received_at: str) -> dict[str, list[dict[str, Any]]]:
        rows = {"7_Raw_Logs": [self._raw_row(received_at=received_at, source_topic="sau/iot/mega/konveyor/vision/events", source_code="vision", raw_payload=payload, parsed_flag=0)]}
        parsed = parse_vision_event(payload)
        if parsed is None:
            return rows
        vision_event_id = self._next("vision_event_id")
        log_event_id = self._next("log_event_id")
        rows["7_Raw_Logs"][0].update({"parsed_flag": 1, "event_type_code": "vision_event", "color_code": parsed["color"], "notes": parsed["event_type"]})
        rows["1_Olay_Logu"] = [self._event_row(log_event_id=log_event_id, received_at=received_at, source_code="vision", event_type_code="vision_event", color_code=parsed["color"], decision_source_code="VISION", notes=f"vision_event={parsed['event_type']};{parsed['notes']}".strip(";"), raw_line=_json_text(payload), event_summary_tr=f"Vision olayi: {parsed['event_type']}", vision_event_id=vision_event_id)]
        raw = parsed["raw"]
        bbox = raw.get("bbox") or {}
        rows["6_Vision"] = [{
            "vision_event_id": vision_event_id,
            "event_time": received_at,
            "source_code": "vision",
            "vision_track_id": parsed["track_id"] or "",
            "event_type": parsed["event_type"],
            "color_id": _color_id(parsed["color"]),
            "color_code": parsed["color"],
            "item_id": "",
            "measure_id": "",
            "confidence": raw.get("confidence", ""),
            "line_id": 1,
            "station_id": 6,
            "bbox_x1": _safe_int(bbox.get("x1")),
            "bbox_y1": _safe_int(bbox.get("y1")),
            "bbox_x2": _safe_int(bbox.get("x2")),
            "bbox_y2": _safe_int(bbox.get("y2")),
            "direction": raw.get("direction", ""),
            "is_placeholder": 0,
            "notes": parsed["notes"],
        }]
        return rows


class ExcelRuntimeSink:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.projector = WorkbookProjector()
        self._queue: queue.Queue[SinkEnvelope | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._enabled = False

    def start(self) -> None:
        if self._enabled:
            return
        if not self.config.excel_enabled:
            return
        try:
            import openpyxl  # noqa: F401
        except ModuleNotFoundError:
            print("MES Web: Excel sink disabled because openpyxl is not installed.")
            return
        self._enabled = True
        self._thread = threading.Thread(target=self._worker, name="mes-web-excel-sink", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._enabled:
            return
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None
        self._enabled = False

    def record_mega_log(self, raw_line: str, received_at: str) -> None:
        if self._enabled:
            self._queue.put(SinkEnvelope(kind="mega_log", received_at=received_at, payload=raw_line))

    def record_vision_event(self, payload: Any, received_at: str) -> None:
        if self._enabled:
            self._queue.put(SinkEnvelope(kind="vision_event", received_at=received_at, payload=payload))

    def record_local_counts_reset(self, received_at: str) -> None:
        if self._enabled:
            self._queue.put(SinkEnvelope(kind="counts_reset", received_at=received_at, payload="SYSTEM|COUNTS|RESET"))

    def _worker(self) -> None:
        from openpyxl import Workbook, load_workbook
        from openpyxl.utils import get_column_letter

        workbook_path = self.config.excel_workbook_path
        workbook_path.parent.mkdir(parents=True, exist_ok=True)
        if not workbook_path.exists() and self.config.excel_template_path and self.config.excel_template_path.exists():
            shutil.copyfile(self.config.excel_template_path, workbook_path)
        workbook = load_workbook(workbook_path) if workbook_path.exists() else Workbook()
        if "Sheet" in workbook.sheetnames and len(workbook.sheetnames) == 1 and workbook["Sheet"].max_row == 1 and workbook["Sheet"].max_column == 1 and workbook["Sheet"]["A1"].value is None:
            workbook.remove(workbook["Sheet"])
        counters: dict[str, int] = {}
        for sheet_name, headers in SHEET_COLUMNS.items():
            sheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.create_sheet(sheet_name)
            if sheet.max_row == 1 and all(sheet.cell(1, col).value is None for col in range(1, max(2, len(headers) + 1))):
                for col_index, header in enumerate(headers, start=1):
                    sheet.cell(1, col_index, header)
            elif sheet.cell(1, 1).value is None:
                for col_index, header in enumerate(headers, start=1):
                    sheet.cell(1, col_index, header)
            self._ensure_sheet_layout(sheet, headers)
            id_header = headers[0]
            id_index = headers.index(id_header) + 1
            next_id = 1
            for row_index in range(2, sheet.max_row + 1):
                value = sheet.cell(row_index, id_index).value
                if isinstance(value, int):
                    next_id = max(next_id, value + 1)
            counters[id_header] = next_id
        self.projector.prime(counters)

        dirty = False
        while True:
            envelope = self._queue.get()
            if envelope is None:
                break
            batch = [envelope]
            while len(batch) < self.config.excel_batch_size:
                try:
                    next_envelope = self._queue.get(timeout=self.config.excel_flush_interval_sec)
                except queue.Empty:
                    break
                if next_envelope is None:
                    self._queue.put(None)
                    break
                batch.append(next_envelope)
            for item in batch:
                rows = self.projector.consume_mega_log(item.payload, item.received_at) if item.kind == "mega_log" else (
                    self.projector.consume_vision_event(item.payload, item.received_at) if item.kind == "vision_event" else self.projector.consume_local_counts_reset(item.received_at)
                )
                for sheet_name, row_dicts in rows.items():
                    sheet = workbook[sheet_name]
                    headers = [sheet.cell(1, idx).value for idx in range(1, sheet.max_column + 1)]
                    for row in row_dicts:
                        target_row = self._next_write_row(sheet, len(headers))
                        if target_row > 2:
                            self._copy_row_style(sheet, source_row=2, target_row=target_row, width=len(headers))
                        for col_index, header in enumerate(headers, start=1):
                            sheet.cell(target_row, col_index, row.get(header, ""))
                        self._update_auto_filter(sheet, len(headers), target_row, get_column_letter)
                        dirty = True
            if dirty:
                workbook.save(workbook_path)
                dirty = False
        workbook.save(workbook_path)

    def _ensure_sheet_layout(self, sheet: Any, headers: list[str]) -> None:
        if sheet.freeze_panes is None:
            sheet.freeze_panes = "A2"
        if sheet.max_row < 2:
            sheet.append(["" for _ in headers])
        self._update_auto_filter(sheet, len(headers), max(sheet.max_row, 2), None)

    def _next_write_row(self, sheet: Any, width: int) -> int:
        for row_index in range(2, max(sheet.max_row, 2) + 1):
            if all(sheet.cell(row_index, col_index).value in (None, "") for col_index in range(1, width + 1)):
                return row_index
        return sheet.max_row + 1

    def _copy_row_style(self, sheet: Any, *, source_row: int, target_row: int, width: int) -> None:
        for col_index in range(1, width + 1):
            source = sheet.cell(source_row, col_index)
            target = sheet.cell(target_row, col_index)
            if source.has_style:
                target._style = copy(source._style)
            if source.number_format:
                target.number_format = source.number_format
            if source.font:
                target.font = copy(source.font)
            if source.fill:
                target.fill = copy(source.fill)
            if source.border:
                target.border = copy(source.border)
            if source.alignment:
                target.alignment = copy(source.alignment)
            if source.protection:
                target.protection = copy(source.protection)

    def _update_auto_filter(self, sheet: Any, width: int, row_index: int, get_column_letter: Any | None) -> None:
        if get_column_letter is None:
            from openpyxl.utils import get_column_letter as local_get_column_letter

            get_column_letter = local_get_column_letter
        sheet.auto_filter.ref = f"A1:{get_column_letter(width)}{max(row_index, 2)}"
