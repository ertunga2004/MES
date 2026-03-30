from __future__ import annotations

import tkinter as tk
from datetime import datetime
from queue import Empty
from tkinter import messagebox, ttk

from .mqtt_service import MqttBridge
from .station import PHASE_COMPLETED_WAIT, PHASE_PICK, StationService


class PickToLightApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Pick To Light Assembly")
        self.root.geometry("1260x760")
        self.root.minsize(1120, 680)

        self.station = StationService()
        self.bridge = MqttBridge()
        self.recent_events = self.station.get_recent_events(limit=12)

        self.product_name_to_id: dict[str, str] = {}
        self.product_var = tk.StringVar()
        self.mqtt_status_var = tk.StringVar(value="MQTT: baglaniyor")
        self.phase_var = tk.StringVar()
        self.current_step_var = tk.StringVar()
        self.instruction_var = tk.StringVar()
        self.completed_var = tk.StringVar()
        self.total_completed_var = tk.StringVar()
        self.button_label_var = tk.StringVar(value="Istasyon Butonu")
        self.box_var = tk.StringVar(value="1")
        self.part_id_var = tk.StringVar()
        self.part_name_var = tk.StringVar()
        self.quantity_var = tk.StringVar(value="0")
        self.delta_var = tk.StringVar(value="1")
        self.min_var = tk.StringVar(value="0")

        self._build_layout()
        self._load_products_into_combobox()
        self.refresh_ui()

        self.root.bind("<space>", self._on_space_press)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.bridge.connect()
        self.root.after(250, self._poll_mqtt_events)
        self.root.after(15000, self._send_heartbeat)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(self.root, padding=14)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        top_frame.columnconfigure(0, weight=3)
        top_frame.columnconfigure(1, weight=1)
        top_frame.columnconfigure(2, weight=1)

        ttk.Label(top_frame, text="Urun Secimi").grid(row=0, column=0, sticky="w")
        self.product_combo = ttk.Combobox(top_frame, textvariable=self.product_var, state="readonly")
        self.product_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(top_frame, text="Urunu Yukle", command=self.select_product).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 10),
        )
        ttk.Label(top_frame, textvariable=self.mqtt_status_var, foreground="#1d4ed8").grid(
            row=1,
            column=2,
            sticky="e",
        )

        left_frame = ttk.Frame(self.root, padding=(14, 0, 7, 14))
        left_frame.grid(row=1, column=0, sticky="nsew")
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(2, weight=1)
        left_frame.rowconfigure(3, weight=1)

        status_frame = ttk.LabelFrame(left_frame, text="Istasyon Durumu", padding=14)
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)

        ttk.Label(status_frame, textvariable=self.phase_var, font=("Segoe UI", 12, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(status_frame, textvariable=self.current_step_var).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        ttk.Label(
            status_frame,
            textvariable=self.instruction_var,
            wraplength=700,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(status_frame, textvariable=self.completed_var).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Label(status_frame, textvariable=self.total_completed_var).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(4, 0),
        )

        action_frame = ttk.Frame(left_frame, padding=(0, 12, 0, 12))
        action_frame.grid(row=1, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)

        tk.Button(
            action_frame,
            textvariable=self.button_label_var,
            command=self.simulate_station_button,
            font=("Segoe UI", 14, "bold"),
            bg="#f59e0b",
            fg="black",
            relief="raised",
            padx=12,
            pady=12,
        ).grid(row=0, column=0, sticky="ew")

        recipe_frame = ttk.LabelFrame(left_frame, text="Montaj Sirasi", padding=8)
        recipe_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        recipe_frame.columnconfigure(0, weight=1)
        recipe_frame.rowconfigure(0, weight=1)

        self.recipe_tree = ttk.Treeview(
            recipe_frame,
            columns=("sequence", "box", "part", "qty"),
            show="headings",
            height=8,
        )
        self.recipe_tree.heading("sequence", text="Sira")
        self.recipe_tree.heading("box", text="Kutu")
        self.recipe_tree.heading("part", text="Parca")
        self.recipe_tree.heading("qty", text="Adet")
        self.recipe_tree.column("sequence", width=60, anchor="center")
        self.recipe_tree.column("box", width=70, anchor="center")
        self.recipe_tree.column("part", width=260)
        self.recipe_tree.column("qty", width=70, anchor="center")
        self.recipe_tree.tag_configure("current", background="#fef3c7")
        self.recipe_tree.grid(row=0, column=0, sticky="nsew")

        recipe_scroll = ttk.Scrollbar(recipe_frame, orient="vertical", command=self.recipe_tree.yview)
        recipe_scroll.grid(row=0, column=1, sticky="ns")
        self.recipe_tree.configure(yscrollcommand=recipe_scroll.set)

        event_frame = ttk.LabelFrame(left_frame, text="Son Olaylar", padding=8)
        event_frame.grid(row=3, column=0, sticky="nsew")
        event_frame.columnconfigure(0, weight=1)
        event_frame.rowconfigure(0, weight=1)

        self.event_list = tk.Listbox(event_frame, height=10)
        self.event_list.grid(row=0, column=0, sticky="nsew")
        event_scroll = ttk.Scrollbar(event_frame, orient="vertical", command=self.event_list.yview)
        event_scroll.grid(row=0, column=1, sticky="ns")
        self.event_list.configure(yscrollcommand=event_scroll.set)

        right_frame = ttk.Frame(self.root, padding=(7, 0, 14, 14))
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        inventory_frame = ttk.LabelFrame(right_frame, text="Kutu Stoklari", padding=8)
        inventory_frame.grid(row=0, column=0, sticky="nsew")
        inventory_frame.columnconfigure(0, weight=1)
        inventory_frame.rowconfigure(0, weight=1)

        self.inventory_tree = ttk.Treeview(
            inventory_frame,
            columns=("box", "part_id", "part_name", "qty", "min"),
            show="headings",
            height=10,
        )
        self.inventory_tree.heading("box", text="Kutu")
        self.inventory_tree.heading("part_id", text="Parca ID")
        self.inventory_tree.heading("part_name", text="Parca Adi")
        self.inventory_tree.heading("qty", text="Stok")
        self.inventory_tree.heading("min", text="Min")
        self.inventory_tree.column("box", width=60, anchor="center")
        self.inventory_tree.column("part_id", width=120)
        self.inventory_tree.column("part_name", width=180)
        self.inventory_tree.column("qty", width=70, anchor="center")
        self.inventory_tree.column("min", width=70, anchor="center")
        self.inventory_tree.grid(row=0, column=0, sticky="nsew")
        self.inventory_tree.bind("<<TreeviewSelect>>", self._on_inventory_select)

        inventory_scroll = ttk.Scrollbar(
            inventory_frame,
            orient="vertical",
            command=self.inventory_tree.yview,
        )
        inventory_scroll.grid(row=0, column=1, sticky="ns")
        self.inventory_tree.configure(yscrollcommand=inventory_scroll.set)

        form = ttk.Frame(inventory_frame, padding=(0, 10, 0, 0))
        form.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            form.columnconfigure(column, weight=1)

        ttk.Label(form, text="Kutu").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="Parca ID").grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Parca Adi").grid(row=0, column=2, sticky="w")
        ttk.Label(form, text="Min").grid(row=0, column=3, sticky="w")

        ttk.Entry(form, textvariable=self.box_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Entry(form, textvariable=self.part_id_var).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Entry(form, textvariable=self.part_name_var).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Entry(form, textvariable=self.min_var).grid(row=1, column=3, sticky="ew")

        ttk.Label(form, text="Delta").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(form, text="Set stok").grid(row=2, column=1, sticky="w", pady=(10, 0))
        ttk.Entry(form, textvariable=self.delta_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Entry(form, textvariable=self.quantity_var).grid(row=3, column=1, sticky="ew", padx=(0, 8))

        ttk.Button(form, text="Stok Ekle", command=self.increase_stock).grid(
            row=3,
            column=2,
            sticky="ew",
            padx=(0, 8),
        )
        ttk.Button(form, text="Stok Dus", command=self.decrease_stock).grid(
            row=3,
            column=3,
            sticky="ew",
        )
        ttk.Button(form, text="Stok Set", command=self.set_stock).grid(
            row=4,
            column=2,
            sticky="ew",
            padx=(0, 8),
            pady=(8, 0),
        )
        ttk.Button(form, text="Secimi Temizle", command=self.clear_form).grid(
            row=4,
            column=3,
            sticky="ew",
            pady=(8, 0),
        )

    def _load_products_into_combobox(self) -> None:
        choices = self.station.get_product_choices()
        self.product_name_to_id = {item["product_name"]: item["product_id"] for item in choices}
        product_names = [item["product_name"] for item in choices]
        self.product_combo["values"] = product_names

        snapshot = self.station.build_snapshot(include_catalog=False)
        self.product_var.set(snapshot["selected_product_name"])

    def refresh_ui(self) -> None:
        snapshot = self.station.build_snapshot(include_catalog=False)
        current_step = snapshot["current_step"]
        phase = snapshot["phase"]

        phase_label = {
            PHASE_PICK: "Asama: Parca Alma",
            PHASE_COMPLETED_WAIT: "Asama: Urun Tamamlandi",
        }.get(phase, "Asama: Montaj")

        self.phase_var.set(phase_label)
        self.instruction_var.set(snapshot["instruction"])
        self.completed_var.set(
            f"{snapshot['selected_product_name']} tamamlanan adet: "
            f"{snapshot['completed_current_product']}"
        )
        self.total_completed_var.set(f"Toplam tamamlanan urun: {snapshot['completed_total']}")

        if phase == PHASE_COMPLETED_WAIT:
            self.current_step_var.set("Tum adimlar tamamlandi. Sonraki urun bekleniyor.")
            self.button_label_var.set("Sonraki Urune Gec")
        elif current_step:
            self.current_step_var.set(
                f"Adim {current_step['sequence']}/{snapshot['step_count']} - "
                f"Kutu {current_step['box_number']} - {current_step['part_name']} - "
                f"Adet {current_step['quantity']}"
            )
            if phase == PHASE_PICK:
                self.button_label_var.set("Parca Alindi - Buton")
            else:
                self.button_label_var.set("Montaj Tamam - Buton")
        else:
            self.current_step_var.set("Adim bilgisi yok.")
            self.button_label_var.set("Istasyon Butonu")

        self._refresh_recipe_tree(snapshot)
        self._refresh_inventory_tree(snapshot)
        self._refresh_event_list()
        self._refresh_mqtt_status()

    def _refresh_recipe_tree(self, snapshot: dict) -> None:
        for item_id in self.recipe_tree.get_children():
            self.recipe_tree.delete(item_id)

        phase = snapshot["phase"]
        current_index = snapshot["current_step_index"]

        for index, step in enumerate(snapshot["recipe_steps"]):
            tags = ()
            if index == current_index and phase != PHASE_COMPLETED_WAIT:
                tags = ("current",)

            self.recipe_tree.insert(
                "",
                "end",
                iid=f"step_{step['sequence']}",
                values=(
                    step["sequence"],
                    step["box_number"],
                    step["part_name"],
                    step["quantity"],
                ),
                tags=tags,
            )

        if phase == PHASE_COMPLETED_WAIT:
            current_item = f"step_{snapshot['recipe_steps'][-1]['sequence']}"
        else:
            current_item = f"step_{snapshot['current_step']['sequence']}"

        if self.recipe_tree.exists(current_item):
            self.recipe_tree.selection_set(current_item)
            self.recipe_tree.focus(current_item)

    def _refresh_inventory_tree(self, snapshot: dict) -> None:
        for item_id in self.inventory_tree.get_children():
            self.inventory_tree.delete(item_id)

        for row in snapshot["box_inventory"]:
            self.inventory_tree.insert(
                "",
                "end",
                values=(
                    row["box_number"],
                    row["part_id"],
                    row["part_name"],
                    row["quantity"],
                    row["min_quantity"],
                ),
            )

    def _refresh_event_list(self) -> None:
        self.event_list.delete(0, tk.END)
        for event in reversed(self.recent_events):
            event_time = event.get("event_time", "")
            event_type = event.get("event_type", "")
            details = event.get("details", {})
            self.event_list.insert(tk.END, self._event_text(event_time, event_type, details))

    def _event_text(self, event_time: str, event_type: str, details: dict) -> str:
        time_label = event_time[-8:] if len(event_time) >= 8 else event_time

        if event_type == "part_picked":
            return (
                f"{time_label} | Kutu {details.get('box_number')} | "
                f"{details.get('part_name')} x{details.get('quantity')} alindi"
            )
        if event_type == "assembly_confirmed":
            return f"{time_label} | Montaj onaylandi"
        if event_type == "product_completed":
            return (
                f"{time_label} | {details.get('product_name')} tamamlandi "
                f"({details.get('completed_count_for_product')})"
            )
        if event_type == "inventory_adjusted":
            return (
                f"{time_label} | Kutu {details.get('box_number')} | "
                f"{details.get('part_name')} stok {details.get('quantity')}"
            )
        if event_type == "next_cycle_started":
            return f"{time_label} | Sonraki urun baslatildi"
        if event_type == "product_selected":
            return f"{time_label} | Urun secildi: {details.get('selected_product_name')}"
        return f"{time_label} | {event_type}"

    def _refresh_mqtt_status(self) -> None:
        self.mqtt_status_var.set("MQTT: bagli" if self.bridge.connected else "MQTT: kopuk")

    def select_product(self) -> None:
        product_name = self.product_var.get().strip()
        product_id = self.product_name_to_id.get(product_name)
        if not product_id:
            messagebox.showerror("Urun secimi", "Gecerli bir urun secin.")
            return

        try:
            event = self.station.select_product(product_id, source="gui")
        except ValueError as exc:
            messagebox.showerror("Urun secimi", str(exc))
            return

        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui()

    def simulate_station_button(self) -> None:
        self._process_station_button(source="gui")

    def _process_station_button(self, source: str) -> None:
        try:
            event = self.station.button_press(source=source)
        except ValueError as exc:
            messagebox.showwarning("Istasyon butonu", str(exc))
            return

        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui()

    def publish_station_state(self, event: dict | None = None) -> None:
        snapshot = self.station.build_snapshot(include_catalog=False)
        self.bridge.publish_state(snapshot)
        self.bridge.publish_display(snapshot["display_lines"])
        if event is not None:
            self.bridge.publish_event(event)

    def _send_heartbeat(self) -> None:
        snapshot = self.station.build_snapshot(include_catalog=False)
        self.bridge.publish_heartbeat(
            {
                "source": "python_gui",
                "sent_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "selected_product_id": snapshot["selected_product_id"],
                "phase": snapshot["phase"],
                "completed_total": snapshot["completed_total"],
            }
        )
        self.root.after(15000, self._send_heartbeat)

    def increase_stock(self) -> None:
        self._adjust_stock(delta_sign=1)

    def decrease_stock(self) -> None:
        self._adjust_stock(delta_sign=-1)

    def _adjust_stock(self, delta_sign: int) -> None:
        try:
            box_number = self._parse_int(self.box_var.get(), "Kutu")
            delta = self._parse_int(self.delta_var.get(), "Delta")
            min_quantity = self._parse_int(self.min_var.get(), "Min")
            event = self.station.adjust_stock(
                box_number=box_number,
                part_id=self.part_id_var.get(),
                part_name=self.part_name_var.get(),
                delta=delta_sign * delta,
                min_quantity=min_quantity,
                source="gui",
            )
        except ValueError as exc:
            messagebox.showerror("Stok isleme", str(exc))
            return

        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui()

    def set_stock(self) -> None:
        try:
            box_number = self._parse_int(self.box_var.get(), "Kutu")
            quantity = self._parse_int(self.quantity_var.get(), "Set stok")
            min_quantity = self._parse_int(self.min_var.get(), "Min")
            event = self.station.adjust_stock(
                box_number=box_number,
                part_id=self.part_id_var.get(),
                part_name=self.part_name_var.get(),
                set_quantity=quantity,
                min_quantity=min_quantity,
                source="gui",
            )
        except ValueError as exc:
            messagebox.showerror("Stok isleme", str(exc))
            return

        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui()

    def clear_form(self) -> None:
        self.box_var.set("1")
        self.part_id_var.set("")
        self.part_name_var.set("")
        self.quantity_var.set("0")
        self.delta_var.set("1")
        self.min_var.set("0")
        self.inventory_tree.selection_remove(self.inventory_tree.selection())

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{label} sayi olmali.") from exc

    def _on_inventory_select(self, event) -> None:
        selection = self.inventory_tree.selection()
        if not selection:
            return

        values = self.inventory_tree.item(selection[0], "values")
        self.box_var.set(str(values[0]))
        self.part_id_var.set(str(values[1]))
        self.part_name_var.set(str(values[2]))
        self.quantity_var.set(str(values[3]))
        self.min_var.set(str(values[4]))

    def _on_space_press(self, event) -> None:
        self.simulate_station_button()

    def _poll_mqtt_events(self) -> None:
        while True:
            try:
                payload = self.bridge.events.get_nowait()
            except Empty:
                break

            if payload["type"] == "connection":
                if payload["connected"]:
                    self.publish_station_state()
            elif payload["type"] == "mqtt_message":
                if payload["topic"] == self.bridge.topics["button"] and payload["payload"].lower() == "press":
                    self._process_station_button(source="esp32")

        self.refresh_ui()
        self.root.after(250, self._poll_mqtt_events)

    def _push_recent_event(self, event: dict) -> None:
        self.recent_events.append(event)
        self.recent_events = self.recent_events[-12:]

    def on_close(self) -> None:
        self.bridge.disconnect()
        self.root.destroy()


def launch() -> None:
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    PickToLightApp(root)
    root.mainloop()
