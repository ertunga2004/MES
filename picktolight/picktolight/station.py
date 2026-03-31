from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from .config import (
    DISPLAY_LINE_COUNT,
    DISPLAY_LINE_WIDTH,
    ERP_SNAPSHOT_PATH,
    EVENT_LOG_PATH,
    INVENTORY_PATH,
    OPERATORS_PATH,
    PRODUCTS_PATH,
    STATE_PATH,
)
from .storage import append_jsonl, read_all_jsonl, read_json, read_recent_jsonl, write_json


PHASE_ACTIVE = "active"
PHASE_COMPLETED_WAIT = "completed_wait"
VALID_PHASES = {PHASE_ACTIVE, PHASE_COMPLETED_WAIT}
LEGACY_PHASE_PICK = "pick"
LEGACY_PHASE_ASSEMBLE = "assemble"
DEFAULT_OPERATORS = {
    "operators": [
        {"operator_id": "OP001", "operator_name": "Ali"},
        {"operator_id": "OP002", "operator_name": "Ayse"},
    ]
}
DEFAULT_STATE = {
    "station_id": "assembly_01",
    "selected_product_id": None,
    "selected_operator_id": None,
    "current_step_index": 0,
    "current_operation_index": 0,
    "phase": PHASE_ACTIVE,
    "completed_counts": {},
    "last_event_at": None,
    "last_event_type": None,
    "last_button_source": None,
    "current_cycle_started_at": None,
    "current_operation_started_at": None,
    "last_operation_duration_ms": None,
    "last_cycle_duration_ms": None,
    "undo_stack": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def elapsed_ms(start_value: str | None, end_value: datetime | None = None) -> int | None:
    start_dt = parse_iso(start_value)
    if start_dt is None:
        return None
    end_dt = end_value or datetime.now(timezone.utc).astimezone()
    return max(0, int((end_dt - start_dt).total_seconds() * 1000))


def avg_ms(total_ms: int, count: int) -> int | None:
    return round(total_ms / count) if count else None


class StationService:
    def __init__(self) -> None:
        self._lock = RLock()
        self.products_data = read_json(PRODUCTS_PATH, {"products": []})
        self.operators_data = read_json(OPERATORS_PATH, copy.deepcopy(DEFAULT_OPERATORS))
        self.inventory_data = read_json(INVENTORY_PATH, {"box_inventory": []})
        self.state_data = read_json(STATE_PATH, copy.deepcopy(DEFAULT_STATE))
        self._normalize_loaded_data()
        self._persist_products()
        self._persist_operators()
        self._persist_state_only()
        self._export_erp_snapshot()

    def _normalize_loaded_data(self) -> None:
        self.products_data["products"] = self._normalized_products(self.products_data.get("products", []))
        self.operators_data["operators"] = self._normalized_operators(
            self.operators_data.get("operators", [])
        )
        self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
            self.inventory_data.get("box_inventory", [])
        )

        product_map = self._product_map()
        operator_map = self._operator_map()
        if not product_map:
            raise RuntimeError("products.json icinde en az bir urun tanimi olmali.")
        if not operator_map:
            raise RuntimeError("operators.json icinde en az bir operator tanimi olmali.")

        state = self.state_data
        state.setdefault("station_id", "assembly_01")
        state.setdefault("last_event_at", None)
        state.setdefault("last_event_type", None)
        state.setdefault("last_button_source", None)
        state.setdefault("last_operation_duration_ms", None)
        state.setdefault("last_cycle_duration_ms", None)
        state.setdefault("current_cycle_started_at", None)
        state.setdefault("current_operation_started_at", None)
        state.setdefault("undo_stack", [])
        if not isinstance(state["undo_stack"], list):
            state["undo_stack"] = []

        if state.get("selected_product_id") not in product_map:
            state["selected_product_id"] = next(iter(product_map))
        if state.get("selected_operator_id") not in operator_map:
            state["selected_operator_id"] = next(iter(operator_map))

        completed_counts = state.setdefault("completed_counts", {})
        for product_id in product_map:
            completed_counts[product_id] = max(0, int(completed_counts.get(product_id, 0)))

        state["current_step_index"] = max(0, int(state.get("current_step_index", 0)))
        state["current_operation_index"] = max(0, int(state.get("current_operation_index", 0)))

        if state["current_step_index"] >= len(self._active_steps()):
            state["current_step_index"] = 0

        phase = str(state.get("phase", PHASE_ACTIVE))
        if phase == LEGACY_PHASE_PICK:
            state["phase"] = PHASE_ACTIVE
            state["current_operation_index"] = 0
        elif phase == LEGACY_PHASE_ASSEMBLE:
            state["phase"] = PHASE_ACTIVE
            state["current_operation_index"] = max(0, len(self._current_step()["operations"]) - 1)
        elif phase not in VALID_PHASES:
            state["phase"] = PHASE_ACTIVE

        op_count = len(self._current_step()["operations"])
        if state["current_operation_index"] >= op_count:
            state["current_operation_index"] = 0

        started_at = now_iso()
        if not parse_iso(state.get("current_cycle_started_at")):
            state["current_cycle_started_at"] = started_at
        if state["phase"] == PHASE_ACTIVE:
            if not parse_iso(state.get("current_operation_started_at")):
                state["current_operation_started_at"] = started_at
        else:
            state["current_operation_started_at"] = None

    def _product_map(self) -> dict[str, dict[str, Any]]:
        return {product["product_id"]: product for product in self.products_data.get("products", [])}

    def _operator_map(self) -> dict[str, dict[str, str]]:
        return {item["operator_id"]: item for item in self.operators_data.get("operators", [])}

    def _normalized_products(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for product in products:
            product_id = str(product["product_id"]).strip()
            if not product_id:
                continue
            steps: list[dict[str, Any]] = []
            for default_sequence, raw_step in enumerate(product.get("steps", []), start=1):
                step = {
                    "sequence": max(1, int(raw_step.get("sequence", default_sequence))),
                    "part_id": str(raw_step.get("part_id", "")).strip() or f"step_{default_sequence}",
                    "part_name": str(raw_step.get("part_name") or raw_step.get("part_id") or "").strip(),
                    "box_number": max(1, min(4, int(raw_step.get("box_number", 1)))),
                    "quantity": max(0, int(raw_step.get("quantity", 0))),
                }
                if not step["part_name"]:
                    step["part_name"] = step["part_id"]
                step["operations"] = self._normalized_operations(step, raw_step.get("operations", []))
                steps.append(step)
            steps.sort(key=lambda item: item["sequence"])
            if steps:
                normalized.append(
                    {
                        "product_id": product_id,
                        "product_name": str(product.get("product_name") or product_id).strip(),
                        "description": str(product.get("description", "")).strip(),
                        "steps": steps,
                    }
                )
        return normalized

    def _normalized_operations(
        self,
        step: dict[str, Any],
        raw_operations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not raw_operations:
            raw_operations = [
                {"action": "pick", "label": "Parcayi al", "consumes_inventory": True},
                {"action": "assemble", "label": "Montaj yap", "consumes_inventory": False},
            ]

        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_operations, start=1):
            action = str(raw.get("action") or "operation").strip().lower()
            consumes_inventory = bool(
                raw.get("consumes_inventory", action in {"pick", "fastener_pick", "material_pick"})
            )
            raw_box = raw.get("box_number", step["box_number"] if consumes_inventory else None)
            normalized.append(
                {
                    "operation_id": str(raw.get("operation_id") or f"op_{step['sequence']}_{index}"),
                    "action": action,
                    "label": str(raw.get("label") or self._default_label(action)).strip(),
                    "consumes_inventory": consumes_inventory,
                    "box_number": None if raw_box in (None, "") else max(1, min(4, int(raw_box))),
                    "part_id": str(raw.get("part_id") or step["part_id"]).strip() or step["part_id"],
                    "part_name": str(raw.get("part_name") or step["part_name"]).strip()
                    or step["part_name"],
                    "quantity": max(
                        0,
                        int(raw.get("quantity", step["quantity"] if consumes_inventory else 0)),
                    ),
                }
            )
        return normalized

    def _normalized_operators(self, operators: list[dict[str, Any]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for index, item in enumerate(operators or DEFAULT_OPERATORS["operators"], start=1):
            operator_id = str(item.get("operator_id") or f"OP{index:03d}").strip()
            operator_name = str(item.get("operator_name") or operator_id).strip()
            if operator_id:
                normalized.append({"operator_id": operator_id, "operator_name": operator_name})
        return normalized

    def _normalized_inventory_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            box_number = int(row["box_number"])
            if 1 <= box_number <= 4:
                normalized.append(
                    {
                        "box_number": box_number,
                        "part_id": str(row["part_id"]).strip(),
                        "part_name": str(row.get("part_name") or row["part_id"]).strip(),
                        "quantity": max(0, int(row.get("quantity", 0))),
                        "min_quantity": max(0, int(row.get("min_quantity", 0))),
                    }
                )
        normalized.sort(key=lambda item: (item["box_number"], item["part_name"], item["part_id"]))
        return normalized

    def _persist_state_only(self) -> None:
        write_json(STATE_PATH, self.state_data)
        write_json(INVENTORY_PATH, self.inventory_data)

    def _persist_products(self) -> None:
        write_json(PRODUCTS_PATH, self.products_data)

    def _persist_operators(self) -> None:
        write_json(OPERATORS_PATH, self.operators_data)

    def _export_erp_snapshot(self) -> dict[str, Any]:
        snapshot = self.build_snapshot(include_catalog=True)
        write_json(ERP_SNAPSHOT_PATH, snapshot)
        return snapshot

    def _set_last_event(self, event_type: str, source: str) -> None:
        self.state_data["last_event_at"] = now_iso()
        self.state_data["last_event_type"] = event_type
        self.state_data["last_button_source"] = source

    def _active_product(self) -> dict[str, Any]:
        return self._product_map()[self.state_data["selected_product_id"]]

    def _active_operator(self) -> dict[str, str]:
        return self._operator_map()[self.state_data["selected_operator_id"]]

    def _active_steps(self) -> list[dict[str, Any]]:
        return self._active_product().get("steps", [])

    def _current_step(self) -> dict[str, Any]:
        return self._active_steps()[self.state_data["current_step_index"]]

    def _current_operation(self) -> dict[str, Any] | None:
        if self.state_data["phase"] != PHASE_ACTIVE:
            return None
        return self._current_step()["operations"][self.state_data["current_operation_index"]]

    def _completed_total(self) -> int:
        return sum(int(value) for value in self.state_data["completed_counts"].values())

    def _inventory_record(self, box_number: int, part_id: str) -> dict[str, Any] | None:
        for row in self.inventory_data["box_inventory"]:
            if row["box_number"] == box_number and row["part_id"] == part_id:
                return row
        return None

    def _ensure_inventory_record(self, box_number: int, part_id: str, part_name: str) -> dict[str, Any]:
        record = self._inventory_record(box_number, part_id)
        if record is not None:
            record["part_name"] = part_name or record["part_name"]
            return record
        self.inventory_data["box_inventory"].append(
            {
                "box_number": box_number,
                "part_id": part_id,
                "part_name": part_name or part_id,
                "quantity": 0,
                "min_quantity": 0,
            }
        )
        self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
            self.inventory_data["box_inventory"]
        )
        return self._inventory_record(box_number, part_id) or {
            "box_number": box_number,
            "part_id": part_id,
            "part_name": part_name or part_id,
            "quantity": 0,
            "min_quantity": 0,
        }

    def _state_for_undo(self) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in self.state_data.items()
            if key != "undo_stack"
        }

    def _push_undo_entry(
        self,
        *,
        state_before: dict[str, Any],
        inventory_before: dict[str, Any],
        operation_event_id: str,
    ) -> None:
        undo_stack = self.state_data.setdefault("undo_stack", [])
        undo_stack.append(
            {
                "state_before": state_before,
                "inventory_before": inventory_before,
                "operation_event_id": operation_event_id,
            }
        )
        self.state_data["undo_stack"] = undo_stack[-30:]

    def _fit_text(self, value: str) -> str:
        return value.strip()[:DISPLAY_LINE_WIDTH]

    def _finalize_display_lines(self, rows: list[str]) -> list[str]:
        rows = rows[:DISPLAY_LINE_COUNT]
        while len(rows) < DISPLAY_LINE_COUNT:
            rows.append("")
        return rows

    def _default_label(self, action: str) -> str:
        return {
            "pick": "Parcayi al",
            "assemble": "Montaj yap",
            "tool_pick": "Aleti al",
            "fastener_pick": "Baglanti elemanini al",
            "inspect": "Kontrol et",
        }.get(action, "Adimi tamamla")

    def get_product_choices(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"product_id": product["product_id"], "product_name": product["product_name"]}
                for product in self.products_data.get("products", [])
            ]

    def get_operator_choices(self) -> list[dict[str, str]]:
        with self._lock:
            return copy.deepcopy(self.operators_data.get("operators", []))

    def get_recent_events(self, limit: int = 12) -> list[dict[str, Any]]:
        return read_recent_jsonl(EVENT_LOG_PATH, limit=limit)

    def select_product(self, product_id: str, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            if product_id not in self._product_map():
                raise ValueError("Bilinmeyen urun secimi.")
            started_at = now_iso()
            self.state_data["selected_product_id"] = product_id
            self.state_data["current_step_index"] = 0
            self.state_data["current_operation_index"] = 0
            self.state_data["phase"] = PHASE_ACTIVE
            self.state_data["current_cycle_started_at"] = started_at
            self.state_data["current_operation_started_at"] = started_at
            self.state_data["undo_stack"] = []
            self._set_last_event("product_selected", source)
            self._persist_state_only()
            self._export_erp_snapshot()
            product = self._active_product()
            return self._record_event(
                event_type="product_selected",
                source=source,
                details={
                    "selected_product_id": product["product_id"],
                    "selected_product_name": product["product_name"],
                },
            )

    def select_operator(self, operator_id: str, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            if operator_id not in self._operator_map():
                raise ValueError("Bilinmeyen operator secimi.")
            self.state_data["selected_operator_id"] = operator_id
            self._set_last_event("operator_selected", source)
            self._persist_state_only()
            self._export_erp_snapshot()
            operator = self._active_operator()
            return self._record_event(
                event_type="operator_selected",
                source=source,
                details={
                    "selected_operator_id": operator["operator_id"],
                    "selected_operator_name": operator["operator_name"],
                },
            )

    def reset_current_cycle(self, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            started_at = now_iso()
            self.state_data["current_step_index"] = 0
            self.state_data["current_operation_index"] = 0
            self.state_data["phase"] = PHASE_ACTIVE
            self.state_data["current_cycle_started_at"] = started_at
            self.state_data["current_operation_started_at"] = started_at
            self.state_data["undo_stack"] = []
            self._set_last_event("cycle_reset", source)
            self._persist_state_only()
            self._export_erp_snapshot()
            product = self._active_product()
            operator = self._active_operator()
            return self._record_event(
                event_type="cycle_reset",
                source=source,
                details={
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "operator_id": operator["operator_id"],
                    "operator_name": operator["operator_name"],
                    "stock_rollback": False,
                },
            )

    def update_recipe_box(
        self,
        *,
        sequence: int,
        new_box_number: int,
        source: str = "gui",
    ) -> dict[str, Any]:
        with self._lock:
            if new_box_number < 1 or new_box_number > 4:
                raise ValueError("Yeni kutu numarasi 1 ile 4 arasinda olmali.")
            product = self._active_product()
            selected_step = None
            for step in product.get("steps", []):
                if int(step["sequence"]) == int(sequence):
                    selected_step = step
                    break
            if selected_step is None:
                raise ValueError("Secili montaj adimi bulunamadi.")

            old_box_number = int(selected_step["box_number"])
            part_id = selected_step["part_id"]
            part_name = selected_step["part_name"]
            selected_step["box_number"] = new_box_number
            for operation in selected_step["operations"]:
                if operation["consumes_inventory"] and operation["part_id"] == part_id:
                    operation["box_number"] = new_box_number

            if old_box_number != new_box_number:
                old_inventory = self._inventory_record(old_box_number, part_id)
                new_inventory = self._inventory_record(new_box_number, part_id)
                if old_inventory is not None:
                    if new_inventory is not None and new_inventory is not old_inventory:
                        new_inventory["quantity"] += old_inventory["quantity"]
                        new_inventory["min_quantity"] = max(
                            new_inventory["min_quantity"],
                            old_inventory["min_quantity"],
                        )
                        self.inventory_data["box_inventory"].remove(old_inventory)
                    else:
                        old_inventory["box_number"] = new_box_number

            self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
                self.inventory_data["box_inventory"]
            )
            self._set_last_event("recipe_box_updated", source)
            self._persist_products()
            self._persist_state_only()
            self._export_erp_snapshot()
            return self._record_event(
                event_type="recipe_box_updated",
                source=source,
                details={
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "step_sequence": int(sequence),
                    "part_id": part_id,
                    "part_name": part_name,
                    "old_box_number": old_box_number,
                    "new_box_number": new_box_number,
                },
            )

    def adjust_stock(
        self,
        box_number: int,
        part_id: str,
        part_name: str,
        *,
        delta: int | None = None,
        set_quantity: int | None = None,
        min_quantity: int | None = None,
        source: str = "gui",
    ) -> dict[str, Any]:
        with self._lock:
            if box_number < 1 or box_number > 4:
                raise ValueError("Kutu numarasi 1 ile 4 arasinda olmali.")
            normalized_part_id = part_id.strip()
            if not normalized_part_id:
                raise ValueError("Parca ID bos olamaz.")
            normalized_part_name = (part_name or normalized_part_id).strip()
            record = self._ensure_inventory_record(box_number, normalized_part_id, normalized_part_name)
            if set_quantity is not None:
                record["quantity"] = max(0, int(set_quantity))
            elif delta is not None:
                record["quantity"] = max(0, int(record["quantity"]) + int(delta))
            else:
                raise ValueError("delta veya set_quantity verilmelidir.")
            if min_quantity is not None:
                record["min_quantity"] = max(0, int(min_quantity))
            self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
                self.inventory_data["box_inventory"]
            )
            self._set_last_event("inventory_adjusted", source)
            self._persist_state_only()
            self._export_erp_snapshot()
            updated = self._inventory_record(box_number, normalized_part_id)
            return self._record_event(
                event_type="inventory_adjusted",
                source=source,
                details={
                    "box_number": box_number,
                    "part_id": normalized_part_id,
                    "part_name": normalized_part_name,
                    "quantity": updated["quantity"] if updated else 0,
                },
            )

    def undo_last_operation(self, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            undo_stack = self.state_data.setdefault("undo_stack", [])
            if not undo_stack:
                raise ValueError("Geri alinacak son operasyon bulunamadi.")

            undo_entry = undo_stack.pop()
            state_before = copy.deepcopy(undo_entry["state_before"])
            inventory_before = copy.deepcopy(undo_entry["inventory_before"])
            undone_event_id = str(undo_entry.get("operation_event_id") or "")

            self.state_data = copy.deepcopy(state_before)
            self.state_data["undo_stack"] = undo_stack
            self.inventory_data = copy.deepcopy(inventory_before)
            self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
                self.inventory_data.get("box_inventory", [])
            )

            product = self._active_product()
            operator = self._active_operator()
            current_step = self._current_step()
            current_operation = self._current_operation()

            self._set_last_event("operation_undone", source)
            self._persist_state_only()
            self._export_erp_snapshot()
            return self._record_event(
                event_type="operation_undone",
                source=source,
                details={
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "operator_id": operator["operator_id"],
                    "operator_name": operator["operator_name"],
                    "step_sequence": current_step["sequence"],
                    "operation_index": int(self.state_data["current_operation_index"]) + 1,
                    "label": current_operation["label"] if current_operation else None,
                    "part_name": current_operation["part_name"] if current_operation else None,
                    "undone_event_id": undone_event_id,
                },
            )

    def button_press(self, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            product = self._active_product()
            operator = self._active_operator()
            if self.state_data["phase"] == PHASE_COMPLETED_WAIT:
                started_at = now_iso()
                self.state_data["current_step_index"] = 0
                self.state_data["current_operation_index"] = 0
                self.state_data["phase"] = PHASE_ACTIVE
                self.state_data["current_cycle_started_at"] = started_at
                self.state_data["current_operation_started_at"] = started_at
                self._set_last_event("next_cycle_started", source)
                self._persist_state_only()
                self._export_erp_snapshot()
                return self._record_event(
                    event_type="next_cycle_started",
                    source=source,
                    details={
                        "product_id": product["product_id"],
                        "product_name": product["product_name"],
                        "operator_id": operator["operator_id"],
                        "operator_name": operator["operator_name"],
                        "step_sequence": 1,
                        "operation_label": self._current_operation()["label"],
                    },
                )

            state_before = self._state_for_undo()
            inventory_before = copy.deepcopy(self.inventory_data)
            finished_at = datetime.now(timezone.utc).astimezone()
            step = copy.deepcopy(self._current_step())
            operation = copy.deepcopy(self._current_operation())
            completed_operation_index = int(self.state_data["current_operation_index"])
            duration = elapsed_ms(self.state_data.get("current_operation_started_at"), finished_at) or 0
            if operation["consumes_inventory"]:
                record = self._inventory_record(operation["box_number"], operation["part_id"])
                if record is None:
                    raise ValueError(
                        f"Kutu {operation['box_number']} icin {operation['part_name']} stogu tanimli degil."
                    )
                if record["quantity"] < operation["quantity"]:
                    raise ValueError(
                        f"Kutu {operation['box_number']} icin stok yetersiz: "
                        f"{operation['part_name']} gereken {operation['quantity']}, "
                        f"mevcut {record['quantity']}."
                    )
                record["quantity"] -= operation["quantity"]

            self.state_data["last_operation_duration_ms"] = duration
            cycle_duration = None
            product_completed = False
            next_step = None
            next_operation = None
            if self.state_data["current_operation_index"] < len(self._current_step()["operations"]) - 1:
                self.state_data["current_operation_index"] += 1
                self.state_data["current_operation_started_at"] = finished_at.isoformat(timespec="seconds")
                next_step = self._current_step()
                next_operation = self._current_operation()
            elif self.state_data["current_step_index"] < len(self._active_steps()) - 1:
                self.state_data["current_step_index"] += 1
                self.state_data["current_operation_index"] = 0
                self.state_data["current_operation_started_at"] = finished_at.isoformat(timespec="seconds")
                next_step = self._current_step()
                next_operation = self._current_operation()
            else:
                self.state_data["phase"] = PHASE_COMPLETED_WAIT
                self.state_data["current_operation_started_at"] = None
                self.state_data["completed_counts"][product["product_id"]] += 1
                cycle_duration = elapsed_ms(self.state_data.get("current_cycle_started_at"), finished_at) or 0
                self.state_data["last_cycle_duration_ms"] = cycle_duration
                product_completed = True

            self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
                self.inventory_data["box_inventory"]
            )
            self._set_last_event("operation_completed", source)
            self._persist_state_only()
            self._export_erp_snapshot()
            event = self._record_event(
                event_type="operation_completed",
                source=source,
                details={
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "operator_id": operator["operator_id"],
                    "operator_name": operator["operator_name"],
                    "step_sequence": step["sequence"],
                    "operation_index": completed_operation_index + 1,
                    "action": operation["action"],
                    "label": operation["label"],
                    "box_number": operation["box_number"],
                    "part_id": operation["part_id"],
                    "part_name": operation["part_name"],
                    "quantity": operation["quantity"],
                    "duration_ms": duration,
                    "product_completed": product_completed,
                    "cycle_duration_ms": cycle_duration,
                    "next_step_sequence": next_step["sequence"] if next_step else None,
                    "next_operation_label": next_operation["label"] if next_operation else None,
                    "completed_count_for_product": self.state_data["completed_counts"][
                        product["product_id"]
                    ],
                },
            )
            self._push_undo_entry(
                state_before=state_before,
                inventory_before=inventory_before,
                operation_event_id=event["event_id"],
            )
            self._persist_state_only()
            self._export_erp_snapshot()
            return event

    def _record_event(self, *, event_type: str, source: str, details: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.build_snapshot(include_catalog=False)
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_time": now_iso(),
            "station_id": self.state_data["station_id"],
            "event_type": event_type,
            "source": source,
            "phase": self.state_data["phase"],
            "selected_product_id": snapshot["selected_product_id"],
            "selected_product_name": snapshot["selected_product_name"],
            "selected_operator_id": snapshot["selected_operator_id"],
            "selected_operator_name": snapshot["selected_operator_name"],
            "current_step_index": snapshot["current_step_index"],
            "current_operation_index": snapshot["current_operation_index"],
            "completed_total": snapshot["completed_total"],
            "details": details,
        }
        append_jsonl(EVENT_LOG_PATH, payload)
        return payload

    def build_snapshot(self, *, include_catalog: bool = False) -> dict[str, Any]:
        with self._lock:
            product = self._active_product()
            operator = self._active_operator()
            steps = copy.deepcopy(product.get("steps", []))
            current_step = copy.deepcopy(steps[self.state_data["current_step_index"]])
            current_operation = None
            if self.state_data["phase"] == PHASE_ACTIVE:
                current_operation = copy.deepcopy(
                    current_step["operations"][self.state_data["current_operation_index"]]
                )

            snapshot = {
                "generated_at": now_iso(),
                "station": {
                    "station_id": self.state_data["station_id"],
                    "topic_role": "python_authority",
                },
                "selected_product_id": product["product_id"],
                "selected_product_name": product["product_name"],
                "selected_operator_id": operator["operator_id"],
                "selected_operator_name": operator["operator_name"],
                "phase": self.state_data["phase"],
                "current_step_index": int(self.state_data["current_step_index"]),
                "current_operation_index": int(self.state_data["current_operation_index"]),
                "current_step": current_step,
                "current_operation": current_operation,
                "step_count": len(steps),
                "instruction": self._current_instruction(current_step, current_operation),
                "completed_current_product": int(
                    self.state_data["completed_counts"].get(product["product_id"], 0)
                ),
                "completed_counts": copy.deepcopy(self.state_data["completed_counts"]),
                "completed_total": self._completed_total(),
                "current_operation_elapsed_ms": (
                    elapsed_ms(self.state_data.get("current_operation_started_at"))
                    if self.state_data["phase"] == PHASE_ACTIVE
                    else None
                ),
                "current_cycle_elapsed_ms": elapsed_ms(self.state_data.get("current_cycle_started_at")),
                "last_operation_duration_ms": self.state_data.get("last_operation_duration_ms"),
                "last_cycle_duration_ms": self.state_data.get("last_cycle_duration_ms"),
                "last_event_at": self.state_data.get("last_event_at"),
                "last_event_type": self.state_data.get("last_event_type"),
                "last_button_source": self.state_data.get("last_button_source"),
                "can_undo": bool(self.state_data.get("undo_stack")),
                "recipe_steps": steps,
                "box_inventory": copy.deepcopy(self.inventory_data["box_inventory"]),
                "performance": self._performance_summary(
                    selected_operator_id=operator["operator_id"],
                    selected_product_id=product["product_id"],
                ),
            }
            if include_catalog:
                snapshot["product_catalog"] = copy.deepcopy(self.products_data.get("products", []))
                snapshot["operator_catalog"] = copy.deepcopy(self.operators_data.get("operators", []))
            snapshot["display_lines"] = self._display_lines_for_snapshot(snapshot)
            return snapshot

    def _current_instruction(
        self,
        current_step: dict[str, Any],
        current_operation: dict[str, Any] | None,
    ) -> str:
        if self.state_data["phase"] == PHASE_COMPLETED_WAIT:
            return "Urun tamamlandi. Sonraki urune gecmek icin butona basin."
        if current_operation is None:
            return "Aktif operasyon bekleniyor."
        if current_operation["consumes_inventory"]:
            return (
                f"{current_operation['label']}: kutu {current_operation['box_number']} icinden "
                f"{current_operation['quantity']} adet {current_operation['part_name']} alin ve butona basin."
            )
        if current_operation["action"] == "assemble":
            return f"{current_step['part_name']} icin montaji tamamlayin ve butona basin."
        return f"{current_operation['label']} adimini tamamlayin ve butona basin."

    def _performance_summary(
        self,
        *,
        selected_operator_id: str,
        selected_product_id: str,
    ) -> dict[str, Any]:
        operator_map = self._operator_map()
        stats: dict[str, dict[str, Any]] = {}
        recent_operations: list[dict[str, Any]] = []
        for operator_id, operator in operator_map.items():
            stats[operator_id] = {
                "operator_id": operator_id,
                "operator_name": operator["operator_name"],
                "operation_count": 0,
                "completed_products": 0,
                "cycle_total_ms": 0,
                "undo_count": 0,
                "last_cycle_ms": None,
                "steps": {},
            }

        events = read_all_jsonl(EVENT_LOG_PATH, limit=2000)
        undone_event_ids = {
            str(event.get("details", {}).get("undone_event_id") or "").strip()
            for event in events
            if event.get("event_type") == "operation_undone"
            and str(event.get("details", {}).get("undone_event_id") or "").strip()
        }

        for event in events:
            if event.get("event_type") == "operation_undone":
                details = event.get("details", {})
                operator_id = str(details.get("operator_id") or "").strip()
                if operator_id in stats:
                    stats[operator_id]["undo_count"] += 1

        for event in events:
            if event.get("event_type") != "operation_completed":
                continue
            if event.get("event_id") in undone_event_ids:
                continue
            details = event.get("details", {})
            operator_id = str(details.get("operator_id") or "").strip()
            if operator_id not in stats:
                stats[operator_id] = {
                    "operator_id": operator_id or "unknown",
                    "operator_name": str(details.get("operator_name") or operator_id or "Belirsiz"),
                    "operation_count": 0,
                    "completed_products": 0,
                    "cycle_total_ms": 0,
                    "undo_count": 0,
                    "last_cycle_ms": None,
                    "steps": {},
                }
            duration = max(0, int(details.get("duration_ms") or 0))
            row = stats[operator_id]
            row["operation_count"] += 1
            step_key = (
                str(details.get("product_id") or event.get("selected_product_id") or ""),
                int(details.get("step_sequence") or 0),
                int(details.get("operation_index") or 0),
                str(details.get("label") or details.get("action") or "Operasyon"),
            )
            step_row = row["steps"].setdefault(
                step_key,
                {
                    "product_id": step_key[0],
                    "product_name": str(details.get("product_name") or event.get("selected_product_name") or ""),
                    "step_sequence": step_key[1],
                    "operation_index": step_key[2],
                    "label": step_key[3],
                    "part_name": str(details.get("part_name") or ""),
                    "count": 0,
                    "total_ms": 0,
                },
            )
            step_row["count"] += 1
            step_row["total_ms"] += duration
            if details.get("product_completed"):
                row["completed_products"] += 1
                cycle_ms = max(0, int(details.get("cycle_duration_ms") or 0))
                row["cycle_total_ms"] += cycle_ms
                row["last_cycle_ms"] = cycle_ms
            recent_operations.append(
                {
                    "event_id": event.get("event_id"),
                    "event_time": event.get("event_time"),
                    "operator_id": row["operator_id"],
                    "operator_name": row["operator_name"],
                    "product_name": details.get("product_name") or event.get("selected_product_name"),
                    "step_sequence": details.get("step_sequence"),
                    "operation_index": details.get("operation_index"),
                    "label": details.get("label"),
                    "part_name": details.get("part_name"),
                    "duration_ms": duration,
                }
            )

        operator_rows: list[dict[str, Any]] = []
        for row in stats.values():
            step_breakdown = [
                {
                    "product_id": step_row["product_id"],
                    "product_name": step_row["product_name"],
                    "step_sequence": step_row["step_sequence"],
                    "operation_index": step_row["operation_index"],
                    "label": step_row["label"],
                    "part_name": step_row["part_name"],
                    "count": step_row["count"],
                    "avg_duration_ms": avg_ms(step_row["total_ms"], step_row["count"]),
                }
                for step_row in row["steps"].values()
            ]
            step_breakdown.sort(
                key=lambda item: (
                    item["product_name"],
                    item["step_sequence"],
                    item["operation_index"],
                    item["label"],
                )
            )
            operator_rows.append(
                {
                    "operator_id": row["operator_id"],
                    "operator_name": row["operator_name"],
                    "operation_count": row["operation_count"],
                    "completed_products": row["completed_products"],
                    "undo_count": row["undo_count"],
                    "last_cycle_ms": row["last_cycle_ms"],
                    "avg_cycle_ms": avg_ms(row["cycle_total_ms"], row["completed_products"]),
                    "step_breakdown": step_breakdown,
                }
            )

        operator_rows.sort(key=lambda item: (-item["completed_products"], item["operator_name"]))
        selected = next(
            (item for item in operator_rows if item["operator_id"] == selected_operator_id),
            {
                "operator_id": selected_operator_id,
                "operator_name": operator_map.get(selected_operator_id, {}).get(
                    "operator_name",
                    selected_operator_id,
                ),
                "operation_count": 0,
                "completed_products": 0,
                "undo_count": 0,
                "last_cycle_ms": None,
                "avg_cycle_ms": None,
                "step_breakdown": [],
            },
        )
        return {
            "selected_operator": selected,
            "operators": operator_rows,
            "sequence_breakdown": [
                row
                for row in selected.get("step_breakdown", [])
                if row["product_id"] == selected_product_id
            ],
            "recent_operations": list(reversed(recent_operations[-12:])),
        }

    def _display_lines_for_snapshot(self, snapshot: dict[str, Any]) -> list[str]:
        product_name = snapshot.get("selected_product_name", "Bekleme")
        operator_name = snapshot.get("selected_operator_name", "-")
        if snapshot["phase"] == PHASE_COMPLETED_WAIT:
            return self._finalize_display_lines(
                [
                    self._fit_text(product_name),
                    self._fit_text(f"Op {operator_name}"),
                    self._fit_text("URUN TAMAM"),
                    self._fit_text(f"Toplam {snapshot['completed_current_product']}"),
                    self._fit_text("Yenisi icin"),
                    self._fit_text("butona bas"),
                ]
            )

        operation = snapshot["current_operation"]
        current_step = snapshot["current_step"]
        if operation and operation["box_number"]:
            location_line = f"Kutu {operation['box_number']} x{max(1, operation['quantity'])}"
        else:
            location_line = f"Sira {current_step['sequence']}"
        return self._finalize_display_lines(
            [
                self._fit_text(product_name),
                self._fit_text(f"Op {operator_name}"),
                self._fit_text(location_line),
                self._fit_text(operation["label"] if operation else ""),
                self._fit_text(operation["part_name"] if operation else current_step["part_name"]),
                self._fit_text("Butona bas"),
            ]
        )
