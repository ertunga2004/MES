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
    PRODUCTS_PATH,
    STATE_PATH,
)
from .storage import append_jsonl, read_json, read_recent_jsonl, write_json


PHASE_PICK = "pick"
PHASE_ASSEMBLE = "assemble"
PHASE_COMPLETED_WAIT = "completed_wait"
VALID_PHASES = {PHASE_PICK, PHASE_ASSEMBLE, PHASE_COMPLETED_WAIT}
DEFAULT_STATE = {
    "station_id": "assembly_01",
    "selected_product_id": None,
    "current_step_index": 0,
    "phase": PHASE_PICK,
    "completed_counts": {},
    "last_event_at": None,
    "last_event_type": None,
    "last_button_source": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class StationService:
    def __init__(self) -> None:
        self._lock = RLock()
        self.products_data = read_json(PRODUCTS_PATH, {"products": []})
        self.inventory_data = read_json(INVENTORY_PATH, {"box_inventory": []})
        self.state_data = read_json(STATE_PATH, DEFAULT_STATE)
        self._normalize_loaded_data()
        self._persist_state_only()
        self._export_erp_snapshot()

    def _normalize_loaded_data(self) -> None:
        product_map = self._product_map()
        if not product_map:
            raise RuntimeError("products.json icinde en az bir urun tanimi olmali.")

        self.state_data.setdefault("station_id", "assembly_01")
        self.state_data.setdefault("last_event_at", None)
        self.state_data.setdefault("last_event_type", None)
        self.state_data.setdefault("last_button_source", None)

        selected_product_id = self.state_data.get("selected_product_id")
        if selected_product_id not in product_map:
            self.state_data["selected_product_id"] = next(iter(product_map))

        completed_counts = self.state_data.setdefault("completed_counts", {})
        for product_id in product_map:
            completed_counts[product_id] = int(completed_counts.get(product_id, 0))

        self.state_data["current_step_index"] = max(
            0,
            int(self.state_data.get("current_step_index", 0)),
        )

        phase = self.state_data.get("phase", PHASE_PICK)
        self.state_data["phase"] = phase if phase in VALID_PHASES else PHASE_PICK

        selected_product = product_map[self.state_data["selected_product_id"]]
        step_count = len(selected_product.get("steps", []))
        if step_count == 0:
            raise RuntimeError("Secili urun icin en az bir montaj adimi olmali.")

        if self.state_data["current_step_index"] >= step_count:
            self.state_data["current_step_index"] = 0
            self.state_data["phase"] = PHASE_PICK

        self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
            self.inventory_data.get("box_inventory", [])
        )

    def _product_map(self) -> dict[str, dict[str, Any]]:
        products = self.products_data.get("products", [])
        return {product["product_id"]: product for product in products}

    def _normalized_inventory_rows(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            box_number = int(row["box_number"])
            if box_number < 1 or box_number > 4:
                continue

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

    def _active_steps(self) -> list[dict[str, Any]]:
        return self._active_product().get("steps", [])

    def _current_step(self) -> dict[str, Any]:
        return self._active_steps()[self.state_data["current_step_index"]]

    def _completed_total(self) -> int:
        return sum(int(value) for value in self.state_data["completed_counts"].values())

    def _inventory_record(self, box_number: int, part_id: str) -> dict[str, Any] | None:
        for row in self.inventory_data["box_inventory"]:
            if row["box_number"] == box_number and row["part_id"] == part_id:
                return row
        return None

    def _ensure_inventory_record(
        self,
        box_number: int,
        part_id: str,
        part_name: str,
    ) -> dict[str, Any]:
        record = self._inventory_record(box_number, part_id)
        if record is not None:
            record["part_name"] = part_name or record["part_name"]
            return record

        record = {
            "box_number": box_number,
            "part_id": part_id,
            "part_name": part_name or part_id,
            "quantity": 0,
            "min_quantity": 0,
        }
        self.inventory_data["box_inventory"].append(record)
        self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
            self.inventory_data["box_inventory"]
        )
        return self._inventory_record(box_number, part_id) or record

    def _fit_text(self, value: str) -> str:
        return value.strip()[:DISPLAY_LINE_WIDTH]

    def _finalize_display_lines(self, rows: list[str]) -> list[str]:
        rows = rows[:DISPLAY_LINE_COUNT]
        while len(rows) < DISPLAY_LINE_COUNT:
            rows.append("")
        return rows

    def get_product_choices(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                }
                for product in self.products_data.get("products", [])
            ]

    def get_recent_events(self, limit: int = 12) -> list[dict[str, Any]]:
        return read_recent_jsonl(EVENT_LOG_PATH, limit=limit)

    def select_product(self, product_id: str, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            product_map = self._product_map()
            if product_id not in product_map:
                raise ValueError("Bilinmeyen urun secimi.")

            self.state_data["selected_product_id"] = product_id
            self.state_data["current_step_index"] = 0
            self.state_data["phase"] = PHASE_PICK
            self._set_last_event("product_selected", source)
            self._persist_state_only()
            self._export_erp_snapshot()

            return self._record_event(
                event_type="product_selected",
                source=source,
                details={
                    "selected_product_id": product_id,
                    "selected_product_name": product_map[product_id]["product_name"],
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
            if not part_id.strip():
                raise ValueError("Parca ID bos olamaz.")

            normalized_part_id = part_id.strip()
            normalized_part_name = (part_name or normalized_part_id).strip()
            record = self._ensure_inventory_record(
                box_number=box_number,
                part_id=normalized_part_id,
                part_name=normalized_part_name,
            )

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

    def button_press(self, source: str = "gui") -> dict[str, Any]:
        with self._lock:
            product = self._active_product()
            steps = self._active_steps()
            current_step = steps[self.state_data["current_step_index"]]
            phase = self.state_data["phase"]

            if phase == PHASE_PICK:
                inventory_record = self._inventory_record(
                    box_number=current_step["box_number"],
                    part_id=current_step["part_id"],
                )
                if inventory_record is None:
                    raise ValueError(
                        f"Kutu {current_step['box_number']} icin "
                        f"{current_step['part_name']} stogu tanimli degil."
                    )
                if inventory_record["quantity"] < current_step["quantity"]:
                    raise ValueError(
                        f"Kutu {current_step['box_number']} icin stok yetersiz: "
                        f"{current_step['part_name']} gereken {current_step['quantity']}, "
                        f"mevcut {inventory_record['quantity']}."
                    )

                inventory_record["quantity"] -= current_step["quantity"]
                self.state_data["phase"] = PHASE_ASSEMBLE
                event_type = "part_picked"
                details = {
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "step_sequence": current_step["sequence"],
                    "box_number": current_step["box_number"],
                    "part_id": current_step["part_id"],
                    "part_name": current_step["part_name"],
                    "quantity": current_step["quantity"],
                }
            elif phase == PHASE_ASSEMBLE:
                if self.state_data["current_step_index"] < len(steps) - 1:
                    self.state_data["current_step_index"] += 1
                    self.state_data["phase"] = PHASE_PICK
                    next_step = steps[self.state_data["current_step_index"]]
                    event_type = "assembly_confirmed"
                    details = {
                        "product_id": product["product_id"],
                        "product_name": product["product_name"],
                        "completed_step_sequence": current_step["sequence"],
                        "next_step_sequence": next_step["sequence"],
                        "next_box_number": next_step["box_number"],
                        "next_part_name": next_step["part_name"],
                    }
                else:
                    self.state_data["phase"] = PHASE_COMPLETED_WAIT
                    self.state_data["completed_counts"][product["product_id"]] += 1
                    event_type = "product_completed"
                    details = {
                        "product_id": product["product_id"],
                        "product_name": product["product_name"],
                        "completed_count_for_product": self.state_data["completed_counts"][
                            product["product_id"]
                        ],
                        "completed_total": self._completed_total(),
                    }
            else:
                self.state_data["current_step_index"] = 0
                self.state_data["phase"] = PHASE_PICK
                event_type = "next_cycle_started"
                details = {
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "step_sequence": 1,
                }

            self.inventory_data["box_inventory"] = self._normalized_inventory_rows(
                self.inventory_data["box_inventory"]
            )
            self._set_last_event(event_type, source)
            self._persist_state_only()
            self._export_erp_snapshot()
            return self._record_event(
                event_type=event_type,
                source=source,
                details=details,
            )

    def _record_event(
        self,
        *,
        event_type: str,
        source: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self.build_snapshot(include_catalog=False)
        event_payload = {
            "event_id": str(uuid.uuid4()),
            "event_time": now_iso(),
            "station_id": self.state_data["station_id"],
            "event_type": event_type,
            "source": source,
            "phase": self.state_data["phase"],
            "selected_product_id": self.state_data["selected_product_id"],
            "selected_product_name": snapshot["selected_product_name"],
            "current_step_index": snapshot["current_step_index"],
            "completed_total": snapshot["completed_total"],
            "details": details,
        }
        append_jsonl(EVENT_LOG_PATH, event_payload)
        return event_payload

    def build_snapshot(self, *, include_catalog: bool = False) -> dict[str, Any]:
        with self._lock:
            product = self._active_product()
            steps = copy.deepcopy(product.get("steps", []))

            if self.state_data["phase"] == PHASE_COMPLETED_WAIT:
                current_step = copy.deepcopy(steps[-1])
            else:
                current_step = copy.deepcopy(steps[self.state_data["current_step_index"]])

            current_product_completed = int(
                self.state_data["completed_counts"].get(product["product_id"], 0)
            )

            snapshot = {
                "generated_at": now_iso(),
                "station": {
                    "station_id": self.state_data["station_id"],
                    "topic_role": "python_authority",
                },
                "selected_product_id": product["product_id"],
                "selected_product_name": product["product_name"],
                "phase": self.state_data["phase"],
                "current_step_index": int(self.state_data["current_step_index"]),
                "current_step": current_step,
                "step_count": len(steps),
                "instruction": self._current_instruction(),
                "completed_current_product": current_product_completed,
                "completed_counts": copy.deepcopy(self.state_data["completed_counts"]),
                "completed_total": self._completed_total(),
                "last_event_at": self.state_data.get("last_event_at"),
                "last_event_type": self.state_data.get("last_event_type"),
                "last_button_source": self.state_data.get("last_button_source"),
                "recipe_steps": steps,
                "box_inventory": copy.deepcopy(self.inventory_data["box_inventory"]),
            }

            if include_catalog:
                snapshot["product_catalog"] = copy.deepcopy(self.products_data.get("products", []))

            snapshot["display_lines"] = self._display_lines_for_snapshot(snapshot)
            return snapshot

    def _display_lines_for_snapshot(self, snapshot: dict[str, Any]) -> list[str]:
        product_name = snapshot.get("selected_product_name", "Bekleme")
        completed_current = snapshot.get("completed_current_product", 0)
        line0 = self._fit_text(product_name)

        if snapshot["phase"] == PHASE_PICK and snapshot["current_step"]:
            step = snapshot["current_step"]
            return self._finalize_display_lines(
                [
                    line0,
                    self._fit_text(f"Kutu {step['box_number']} AL"),
                    self._fit_text(step["part_name"]),
                    self._fit_text(f"Adet {step['quantity']}"),
                    self._fit_text(f"Tamam {completed_current}"),
                    self._fit_text("Butona bas"),
                ]
            )

        if snapshot["phase"] == PHASE_ASSEMBLE and snapshot["current_step"]:
            step = snapshot["current_step"]
            return self._finalize_display_lines(
                [
                    line0,
                    self._fit_text(f"Kutu {step['box_number']}"),
                    self._fit_text(step["part_name"]),
                    self._fit_text("Montaj yap"),
                    self._fit_text(f"Tamam {completed_current}"),
                    self._fit_text("Butona bas"),
                ]
            )

        return self._finalize_display_lines(
            [
                line0,
                self._fit_text("URUN TAMAM"),
                self._fit_text(f"Toplam {completed_current}"),
                self._fit_text("Sonraki icin"),
                self._fit_text("butona bas"),
                "",
            ]
        )

    def _current_instruction(self) -> str:
        product = self._active_product()
        current_step = self._current_step()

        if self.state_data["phase"] == PHASE_PICK:
            return (
                f"{product['product_name']} icin kutu {current_step['box_number']} icinden "
                f"{current_step['quantity']} adet {current_step['part_name']} alin ve butona basin."
            )

        if self.state_data["phase"] == PHASE_ASSEMBLE:
            return f"{current_step['part_name']} montajini tamamlayin ve ayni butona tekrar basin."

        return "Urun tamamlandi. Sonraki urune gecmek icin butona basin."
