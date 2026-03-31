from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from queue import Empty
from tkinter import messagebox, ttk

from .mqtt_service import MqttBridge
from .station import PHASE_ACTIVE, PHASE_COMPLETED_WAIT, StationService


TEXT_INPUT_CLASSES = {"Entry", "TEntry", "Text", "Spinbox", "TSpinbox", "TCombobox"}


class PickToLightApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Pick To Light Assembly")
        self.root.geometry("1400x860")
        self.root.minsize(1220, 760)

        self.station = StationService()
        self.bridge = MqttBridge()
        self.recent_events = self.station.get_recent_events(limit=12)
        self.selected_recipe_sequence: int | None = None
        self.loaded_product_name = ""
        self.loaded_operator_name = ""

        self.product_name_to_id: dict[str, str] = {}
        self.operator_name_to_id: dict[str, str] = {}
        self.product_var = tk.StringVar()
        self.operator_var = tk.StringVar()
        self.mqtt_status_var = tk.StringVar(value="MQTT: baglaniyor")
        self.phase_var = tk.StringVar()
        self.current_step_var = tk.StringVar()
        self.operation_var = tk.StringVar()
        self.instruction_var = tk.StringVar()
        self.completed_var = tk.StringVar()
        self.total_completed_var = tk.StringVar()
        self.operation_timer_var = tk.StringVar()
        self.cycle_timer_var = tk.StringVar()
        self.last_operation_var = tk.StringVar()
        self.last_cycle_var = tk.StringVar()
        self.button_label_var = tk.StringVar(value="Istasyon Butonu")
        self.performance_title_var = tk.StringVar()
        self.performance_summary_var = tk.StringVar()
        self.box_var = tk.StringVar(value="1")
        self.part_id_var = tk.StringVar()
        self.part_name_var = tk.StringVar()
        self.quantity_var = tk.StringVar(value="0")
        self.delta_var = tk.StringVar(value="1")
        self.min_var = tk.StringVar(value="0")
        self.recipe_sequence_var = tk.StringVar()
        self.recipe_part_var = tk.StringVar()
        self.recipe_box_var = tk.StringVar(value="1")

        self._build_layout()
        self._load_products_into_combobox()
        self._load_operators_into_combobox()
        self.refresh_ui(full=True)

        self.root.bind_all("<KeyPress-space>", self._on_global_trigger_press, add="+")
        self.root.bind_all("<KeyPress-Return>", self._on_global_trigger_press, add="+")
        self.root.bind_all("<KeyPress-KP_Enter>", self._on_global_trigger_press, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.bridge.connect()
        self.root.after(250, self._poll_mqtt_events)
        self.root.after(1000, self._tick_live_status)
        self.root.after(15000, self._send_heartbeat)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(self.root, padding=14)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        for column in range(7):
            top_frame.columnconfigure(column, weight=1 if column else 2)

        ttk.Label(top_frame, text="Urun Secimi").grid(row=0, column=0, sticky="w")
        self.product_combo = ttk.Combobox(top_frame, textvariable=self.product_var, state="readonly")
        self.product_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(top_frame, text="Urunu Yukle", command=self.select_product).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 10),
        )

        ttk.Label(top_frame, text="Operator").grid(row=0, column=2, sticky="w")
        self.operator_combo = ttk.Combobox(top_frame, textvariable=self.operator_var, state="readonly")
        self.operator_combo.grid(row=1, column=2, sticky="ew", padx=(0, 10))
        ttk.Button(top_frame, text="Operatoru Ata", command=self.select_operator).grid(
            row=1,
            column=3,
            sticky="ew",
            padx=(0, 10),
        )
        ttk.Button(top_frame, text="Isi Resetle", command=self.reset_cycle).grid(
            row=1,
            column=4,
            sticky="ew",
            padx=(0, 10),
        )
        ttk.Label(top_frame, textvariable=self.mqtt_status_var, foreground="#1d4ed8").grid(
            row=1,
            column=6,
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
        status_frame.columnconfigure(1, weight=1)

        ttk.Label(status_frame, textvariable=self.phase_var, font=("Segoe UI", 12, "bold")).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
        )
        ttk.Label(status_frame, textvariable=self.current_step_var).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )
        ttk.Label(status_frame, textvariable=self.operation_var).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Label(
            status_frame,
            textvariable=self.instruction_var,
            wraplength=760,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(status_frame, textvariable=self.completed_var).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Label(status_frame, textvariable=self.total_completed_var).grid(
            row=4,
            column=1,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Label(status_frame, textvariable=self.operation_timer_var).grid(
            row=5,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Label(status_frame, textvariable=self.cycle_timer_var).grid(
            row=5,
            column=1,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Label(status_frame, textvariable=self.last_operation_var).grid(
            row=6,
            column=0,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Label(status_frame, textvariable=self.last_cycle_var).grid(
            row=6,
            column=1,
            sticky="w",
            pady=(4, 0),
        )

        action_frame = ttk.Frame(left_frame, padding=(0, 12, 0, 12))
        action_frame.grid(row=1, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=4)
        action_frame.columnconfigure(1, weight=2)

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
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(action_frame, text="Cycle Reset", command=self.reset_cycle).grid(
            row=0,
            column=1,
            sticky="ew",
        )

        recipe_frame = ttk.LabelFrame(left_frame, text="Montaj Sirasi", padding=8)
        recipe_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        recipe_frame.columnconfigure(0, weight=1)
        recipe_frame.rowconfigure(0, weight=1)

        self.recipe_tree = ttk.Treeview(
            recipe_frame,
            columns=("sequence", "box", "part", "qty", "ops"),
            show="headings",
            height=8,
        )
        self.recipe_tree.heading("sequence", text="Sira")
        self.recipe_tree.heading("box", text="Kutu")
        self.recipe_tree.heading("part", text="Parca")
        self.recipe_tree.heading("qty", text="Adet")
        self.recipe_tree.heading("ops", text="Operasyon Akisi")
        self.recipe_tree.column("sequence", width=60, anchor="center")
        self.recipe_tree.column("box", width=70, anchor="center")
        self.recipe_tree.column("part", width=180)
        self.recipe_tree.column("qty", width=70, anchor="center")
        self.recipe_tree.column("ops", width=280)
        self.recipe_tree.tag_configure("current", background="#fef3c7")
        self.recipe_tree.grid(row=0, column=0, sticky="nsew")
        self.recipe_tree.bind("<<TreeviewSelect>>", self._on_recipe_select)

        recipe_scroll = ttk.Scrollbar(recipe_frame, orient="vertical", command=self.recipe_tree.yview)
        recipe_scroll.grid(row=0, column=1, sticky="ns")
        self.recipe_tree.configure(yscrollcommand=recipe_scroll.set)

        recipe_editor = ttk.Frame(recipe_frame, padding=(0, 10, 0, 0))
        recipe_editor.grid(row=1, column=0, columnspan=2, sticky="ew")
        recipe_editor.columnconfigure(1, weight=1)
        recipe_editor.columnconfigure(3, weight=1)
        recipe_editor.columnconfigure(5, weight=1)

        ttk.Label(recipe_editor, text="Secili Sira").grid(row=0, column=0, sticky="w")
        ttk.Entry(recipe_editor, textvariable=self.recipe_sequence_var, state="readonly").grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 8),
        )
        ttk.Label(recipe_editor, text="Parca").grid(row=0, column=2, sticky="w")
        ttk.Entry(recipe_editor, textvariable=self.recipe_part_var, state="readonly").grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(0, 8),
        )
        ttk.Label(recipe_editor, text="Yeni Kutu").grid(row=0, column=4, sticky="w")
        ttk.Entry(recipe_editor, textvariable=self.recipe_box_var).grid(
            row=0,
            column=5,
            sticky="ew",
            padx=(0, 8),
        )
        ttk.Button(recipe_editor, text="Secili Adimi Tasi", command=self.apply_recipe_box_update).grid(
            row=0,
            column=6,
            sticky="ew",
        )

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

        self.side_notebook = ttk.Notebook(right_frame)
        self.side_notebook.grid(row=0, column=0, sticky="nsew")

        inventory_tab = ttk.Frame(self.side_notebook, padding=8)
        performance_tab = ttk.Frame(self.side_notebook, padding=8)
        self.side_notebook.add(inventory_tab, text="Stok")
        self.side_notebook.add(performance_tab, text="Performans")

        inventory_tab.columnconfigure(0, weight=1)
        inventory_tab.rowconfigure(0, weight=1)

        self.inventory_tree = ttk.Treeview(
            inventory_tab,
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
            inventory_tab,
            orient="vertical",
            command=self.inventory_tree.yview,
        )
        inventory_scroll.grid(row=0, column=1, sticky="ns")
        self.inventory_tree.configure(yscrollcommand=inventory_scroll.set)

        form = ttk.Frame(inventory_tab, padding=(0, 10, 0, 0))
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

        performance_tab.columnconfigure(0, weight=1)
        performance_tab.rowconfigure(2, weight=1)
        performance_tab.rowconfigure(4, weight=1)

        perf_header = ttk.LabelFrame(performance_tab, text="Secili Operator Performansi", padding=10)
        perf_header.grid(row=0, column=0, sticky="ew")
        perf_header.columnconfigure(0, weight=1)

        ttk.Label(perf_header, textvariable=self.performance_title_var, font=("Segoe UI", 11, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Label(
            perf_header,
            textvariable=self.performance_summary_var,
            justify="left",
            wraplength=460,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        operator_frame = ttk.LabelFrame(performance_tab, text="Operator Ozeti", padding=8)
        operator_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        operator_frame.columnconfigure(0, weight=1)
        operator_frame.rowconfigure(0, weight=1)

        self.operator_perf_tree = ttk.Treeview(
            operator_frame,
            columns=("operator", "completed", "operations", "undo", "avg_cycle"),
            show="headings",
            height=6,
        )
        self.operator_perf_tree.heading("operator", text="Operator")
        self.operator_perf_tree.heading("completed", text="Tamamlanan")
        self.operator_perf_tree.heading("operations", text="Operasyon")
        self.operator_perf_tree.heading("undo", text="Geri Al")
        self.operator_perf_tree.heading("avg_cycle", text="Ort. Cevrim")
        self.operator_perf_tree.column("operator", width=120)
        self.operator_perf_tree.column("completed", width=90, anchor="center")
        self.operator_perf_tree.column("operations", width=90, anchor="center")
        self.operator_perf_tree.column("undo", width=80, anchor="center")
        self.operator_perf_tree.column("avg_cycle", width=100, anchor="center")
        self.operator_perf_tree.grid(row=0, column=0, sticky="nsew")

        operator_scroll = ttk.Scrollbar(
            operator_frame,
            orient="vertical",
            command=self.operator_perf_tree.yview,
        )
        operator_scroll.grid(row=0, column=1, sticky="ns")
        self.operator_perf_tree.configure(yscrollcommand=operator_scroll.set)

        action_frame = ttk.LabelFrame(performance_tab, text="Montaj Sirasi Bazli Ortalama", padding=8)
        action_frame.grid(row=2, column=0, sticky="nsew")
        action_frame.columnconfigure(0, weight=1)
        action_frame.rowconfigure(0, weight=1)

        self.action_perf_tree = ttk.Treeview(
            action_frame,
            columns=("step", "operation", "part", "count", "avg"),
            show="headings",
            height=5,
        )
        self.action_perf_tree.heading("step", text="Sira")
        self.action_perf_tree.heading("operation", text="Operasyon")
        self.action_perf_tree.heading("part", text="Parca")
        self.action_perf_tree.heading("count", text="Adet")
        self.action_perf_tree.heading("avg", text="Ort. Sure")
        self.action_perf_tree.column("step", width=60, anchor="center")
        self.action_perf_tree.column("operation", width=150)
        self.action_perf_tree.column("part", width=120)
        self.action_perf_tree.column("count", width=70, anchor="center")
        self.action_perf_tree.column("avg", width=100, anchor="center")
        self.action_perf_tree.grid(row=0, column=0, sticky="nsew")

        action_scroll = ttk.Scrollbar(action_frame, orient="vertical", command=self.action_perf_tree.yview)
        action_scroll.grid(row=0, column=1, sticky="ns")
        self.action_perf_tree.configure(yscrollcommand=action_scroll.set)

        recent_frame = ttk.LabelFrame(performance_tab, text="Son Zamanlanan Operasyonlar", padding=8)
        recent_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        recent_frame.columnconfigure(0, weight=1)
        recent_frame.rowconfigure(0, weight=1)

        self.performance_recent_tree = ttk.Treeview(
            recent_frame,
            columns=("time", "operator", "action", "product", "step", "duration"),
            show="headings",
            height=8,
        )
        self.performance_recent_tree.heading("time", text="Saat")
        self.performance_recent_tree.heading("operator", text="Operator")
        self.performance_recent_tree.heading("action", text="Aksiyon")
        self.performance_recent_tree.heading("product", text="Urun")
        self.performance_recent_tree.heading("step", text="Sira")
        self.performance_recent_tree.heading("duration", text="Sure")
        self.performance_recent_tree.column("time", width=80, anchor="center")
        self.performance_recent_tree.column("operator", width=90)
        self.performance_recent_tree.column("action", width=120)
        self.performance_recent_tree.column("product", width=120)
        self.performance_recent_tree.column("step", width=60, anchor="center")
        self.performance_recent_tree.column("duration", width=90, anchor="center")
        self.performance_recent_tree.grid(row=0, column=0, sticky="nsew")

        recent_scroll = ttk.Scrollbar(
            recent_frame,
            orient="vertical",
            command=self.performance_recent_tree.yview,
        )
        recent_scroll.grid(row=0, column=1, sticky="ns")
        self.performance_recent_tree.configure(yscrollcommand=recent_scroll.set)

    def _load_products_into_combobox(self) -> None:
        choices = self.station.get_product_choices()
        self.product_name_to_id = {item["product_name"]: item["product_id"] for item in choices}
        self.product_combo["values"] = [item["product_name"] for item in choices]
        snapshot = self.station.build_snapshot(include_catalog=False)
        self.loaded_product_name = snapshot["selected_product_name"]
        self.product_var.set(snapshot["selected_product_name"])

    def _load_operators_into_combobox(self) -> None:
        choices = self.station.get_operator_choices()
        self.operator_name_to_id = {item["operator_name"]: item["operator_id"] for item in choices}
        self.operator_combo["values"] = [item["operator_name"] for item in choices]
        snapshot = self.station.build_snapshot(include_catalog=False)
        self.loaded_operator_name = snapshot["selected_operator_name"]
        self.operator_var.set(snapshot["selected_operator_name"])

    def _sync_selection_fields(self, snapshot: dict, *, force: bool = False) -> None:
        active_product_name = snapshot["selected_product_name"]
        active_operator_name = snapshot["selected_operator_name"]

        current_product = self.product_var.get().strip()
        current_operator = self.operator_var.get().strip()

        if force or current_product in {"", self.loaded_product_name}:
            self.product_var.set(active_product_name)
        if force or current_operator in {"", self.loaded_operator_name}:
            self.operator_var.set(active_operator_name)

        self.loaded_product_name = active_product_name
        self.loaded_operator_name = active_operator_name

    def refresh_ui(self, *, full: bool) -> None:
        snapshot = self.station.build_snapshot(include_catalog=False)
        self._sync_selection_fields(snapshot)
        self._apply_snapshot(snapshot)
        if full:
            self._refresh_recipe_tree(snapshot)
            self._refresh_inventory_tree(snapshot)
            self._refresh_event_list()
            self._refresh_performance(snapshot)
        self._refresh_mqtt_status()

    def _apply_snapshot(self, snapshot: dict) -> None:
        phase = snapshot["phase"]
        current_step = snapshot["current_step"]
        current_operation = snapshot["current_operation"]

        phase_label = {
            PHASE_ACTIVE: "Asama: Aktif Operasyon",
            PHASE_COMPLETED_WAIT: "Asama: Urun Tamamlandi",
        }.get(phase, f"Asama: {phase}")
        self.phase_var.set(phase_label)
        self.instruction_var.set(snapshot["instruction"])
        self.completed_var.set(
            f"{snapshot['selected_product_name']} tamamlanan adet: "
            f"{snapshot['completed_current_product']}"
        )
        self.total_completed_var.set(f"Toplam tamamlanan urun: {snapshot['completed_total']}")
        self.operation_timer_var.set(
            f"Aktif adim suresi: {self._format_ms(snapshot.get('current_operation_elapsed_ms'))}"
        )
        self.cycle_timer_var.set(
            f"Aktif cevrim suresi: {self._format_ms(snapshot.get('current_cycle_elapsed_ms'))}"
        )
        self.last_operation_var.set(
            f"Son adim suresi: {self._format_ms(snapshot.get('last_operation_duration_ms'))}"
        )
        self.last_cycle_var.set(
            f"Son cevrim suresi: {self._format_ms(snapshot.get('last_cycle_duration_ms'))}"
        )

        if phase == PHASE_COMPLETED_WAIT:
            self.current_step_var.set("Tum operasyonlar tamamlandi. Sonraki urun icin butona basin.")
            self.operation_var.set(f"Operator: {snapshot['selected_operator_name']}")
            self.button_label_var.set("Sonraki Urune Gec")
            return

        op_count = len(current_step.get("operations", []))
        self.current_step_var.set(
            f"Adim {current_step['sequence']}/{snapshot['step_count']} | "
            f"Kutu {current_step['box_number']} | {current_step['part_name']}"
        )
        self.operation_var.set(
            f"Operasyon {snapshot['current_operation_index'] + 1}/{op_count}: "
            f"{current_operation['label']} | Operator: {snapshot['selected_operator_name']}"
        )
        self.button_label_var.set(f"{current_operation['label']} - Buton")

    def _refresh_recipe_tree(self, snapshot: dict) -> None:
        for item_id in self.recipe_tree.get_children():
            self.recipe_tree.delete(item_id)

        current_index = snapshot["current_step_index"]
        for index, step in enumerate(snapshot["recipe_steps"]):
            tags = ("current",) if index == current_index and snapshot["phase"] != PHASE_COMPLETED_WAIT else ()
            op_text = " -> ".join(operation["label"] for operation in step.get("operations", []))
            self.recipe_tree.insert(
                "",
                "end",
                iid=f"step_{step['sequence']}",
                values=(
                    step["sequence"],
                    step["box_number"],
                    step["part_name"],
                    step["quantity"],
                    op_text,
                ),
                tags=tags,
            )

        selected_sequence = self.selected_recipe_sequence
        if selected_sequence is None and snapshot["current_step"]:
            selected_sequence = int(snapshot["current_step"]["sequence"])

        if selected_sequence is not None:
            item_id = f"step_{selected_sequence}"
            if self.recipe_tree.exists(item_id):
                self.recipe_tree.selection_set(item_id)
                self.recipe_tree.focus(item_id)
                self._set_recipe_selection_from_step(snapshot, selected_sequence)

    def _refresh_inventory_tree(self, snapshot: dict) -> None:
        selected_values = None
        selection = self.inventory_tree.selection()
        if selection:
            selected_values = self.inventory_tree.item(selection[0], "values")

        for item_id in self.inventory_tree.get_children():
            self.inventory_tree.delete(item_id)

        restore_item = None
        for row in snapshot["box_inventory"]:
            item_id = self.inventory_tree.insert(
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
            if selected_values and list(selected_values[:2]) == [str(row["box_number"]), row["part_id"]]:
                restore_item = item_id

        if restore_item:
            self.inventory_tree.selection_set(restore_item)

    def _refresh_event_list(self) -> None:
        self.event_list.delete(0, tk.END)
        for event in reversed(self.recent_events):
            self.event_list.insert(
                tk.END,
                self._event_text(event.get("event_time", ""), event.get("event_type", ""), event.get("details", {})),
            )

    def _refresh_performance(self, snapshot: dict) -> None:
        performance = snapshot["performance"]
        selected = performance["selected_operator"]
        self.performance_title_var.set(
            f"{selected['operator_name']} | {selected['completed_products']} urun | "
            f"{selected['operation_count']} operasyon"
        )
        self.performance_summary_var.set(
            "Geri al: "
            f"{selected.get('undo_count', 0)} | "
            "Ort. cevrim: "
            f"{self._format_ms(selected.get('avg_cycle_ms'))}"
        )

        for tree in (self.operator_perf_tree, self.action_perf_tree, self.performance_recent_tree):
            for item_id in tree.get_children():
                tree.delete(item_id)

        for row in performance["operators"]:
            self.operator_perf_tree.insert(
                "",
                "end",
                values=(
                    row["operator_name"],
                    row["completed_products"],
                    row["operation_count"],
                    row.get("undo_count", 0),
                    self._format_ms(row.get("avg_cycle_ms")),
                ),
            )

        for row in performance.get("sequence_breakdown", []):
            self.action_perf_tree.insert(
                "",
                "end",
                values=(
                    row["step_sequence"],
                    f"{row['operation_index']}. {row['label']}",
                    row.get("part_name") or "-",
                    row["count"],
                    self._format_ms(row.get("avg_duration_ms")),
                ),
            )

        for row in performance["recent_operations"]:
            self.performance_recent_tree.insert(
                "",
                "end",
                values=(
                    self._time_label(row.get("event_time", "")),
                    row.get("operator_name"),
                    row.get("label") or row.get("action"),
                    row.get("product_name"),
                    row.get("step_sequence"),
                    self._format_ms(row.get("duration_ms")),
                ),
            )

    def _event_text(self, event_time: str, event_type: str, details: dict) -> str:
        time_label = self._time_label(event_time)
        if event_type == "operation_completed":
            suffix = " | URUN TAMAM" if details.get("product_completed") else ""
            return (
                f"{time_label} | {details.get('operator_name')} | "
                f"{details.get('label')} | {self._format_ms(details.get('duration_ms'))}{suffix}"
            )
        if event_type == "operator_selected":
            return f"{time_label} | Operator secildi: {details.get('selected_operator_name')}"
        if event_type == "operation_undone":
            return (
                f"{time_label} | {details.get('operator_name')} | "
                f"geri alindi: {details.get('label')}"
            )
        if event_type == "inventory_adjusted":
            return (
                f"{time_label} | Kutu {details.get('box_number')} | "
                f"{details.get('part_name')} stok {details.get('quantity')}"
            )
        if event_type == "recipe_box_updated":
            return (
                f"{time_label} | Sira {details.get('step_sequence')} | "
                f"kutu {details.get('old_box_number')} -> {details.get('new_box_number')}"
            )
        if event_type == "cycle_reset":
            return f"{time_label} | Aktif is sifirlandi"
        if event_type == "next_cycle_started":
            return f"{time_label} | Sonraki urun baslatildi"
        if event_type == "product_selected":
            return f"{time_label} | Urun secildi: {details.get('selected_product_name')}"
        return f"{time_label} | {event_type}"

    def _format_ms(self, value: int | None) -> str:
        if value is None:
            return "-"
        total_seconds = max(0, int(round(value / 1000)))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _time_label(self, value: str) -> str:
        if "T" in value and len(value) >= 19:
            return value[11:19]
        return value

    def _refresh_mqtt_status(self) -> None:
        self.mqtt_status_var.set("MQTT: bagli" if self.bridge.connected else "MQTT: kopuk")

    def select_product(self) -> None:
        product_id = self.product_name_to_id.get(self.product_var.get().strip())
        if not product_id:
            messagebox.showerror("Urun secimi", "Gecerli bir urun secin.")
            return
        try:
            event = self.station.select_product(product_id, source="gui")
        except ValueError as exc:
            messagebox.showerror("Urun secimi", str(exc))
            return
        self.selected_recipe_sequence = None
        self.loaded_product_name = self.product_var.get().strip()
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

    def select_operator(self) -> None:
        operator_id = self.operator_name_to_id.get(self.operator_var.get().strip())
        if not operator_id:
            messagebox.showerror("Operator secimi", "Gecerli bir operator secin.")
            return
        try:
            event = self.station.select_operator(operator_id, source="gui")
        except ValueError as exc:
            messagebox.showerror("Operator secimi", str(exc))
            return
        self.loaded_operator_name = self.operator_var.get().strip()
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

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
        self.refresh_ui(full=True)

    def reset_cycle(self, source: str = "gui") -> None:
        try:
            event = self.station.reset_current_cycle(source=source)
        except ValueError as exc:
            messagebox.showerror("Cycle reset", str(exc))
            return
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

    def undo_last_operation(self, source: str = "gui") -> None:
        try:
            event = self.station.undo_last_operation(source=source)
        except ValueError as exc:
            messagebox.showwarning("Geri al", str(exc))
            return
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

    def apply_recipe_box_update(self) -> None:
        try:
            sequence = self._parse_int(self.recipe_sequence_var.get(), "Secili sira")
            new_box_number = self._parse_int(self.recipe_box_var.get(), "Yeni kutu")
            event = self.station.update_recipe_box(
                sequence=sequence,
                new_box_number=new_box_number,
                source="gui",
            )
        except ValueError as exc:
            messagebox.showerror("Kutu atama", str(exc))
            return
        self.selected_recipe_sequence = sequence
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

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
                "selected_operator_id": snapshot["selected_operator_id"],
                "phase": snapshot["phase"],
                "completed_total": snapshot["completed_total"],
            }
        )
        self.root.after(15000, self._send_heartbeat)

    def _tick_live_status(self) -> None:
        self.refresh_ui(full=False)
        self.root.after(1000, self._tick_live_status)

    def increase_stock(self) -> None:
        self._adjust_stock(delta_sign=1)

    def decrease_stock(self) -> None:
        self._adjust_stock(delta_sign=-1)

    def _adjust_stock(self, delta_sign: int) -> None:
        try:
            event = self.station.adjust_stock(
                box_number=self._parse_int(self.box_var.get(), "Kutu"),
                part_id=self.part_id_var.get(),
                part_name=self.part_name_var.get(),
                delta=delta_sign * self._parse_int(self.delta_var.get(), "Delta"),
                min_quantity=self._parse_int(self.min_var.get(), "Min"),
                source="gui",
            )
        except ValueError as exc:
            messagebox.showerror("Stok isleme", str(exc))
            return
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

    def set_stock(self) -> None:
        try:
            event = self.station.adjust_stock(
                box_number=self._parse_int(self.box_var.get(), "Kutu"),
                part_id=self.part_id_var.get(),
                part_name=self.part_name_var.get(),
                set_quantity=self._parse_int(self.quantity_var.get(), "Set stok"),
                min_quantity=self._parse_int(self.min_var.get(), "Min"),
                source="gui",
            )
        except ValueError as exc:
            messagebox.showerror("Stok isleme", str(exc))
            return
        self._push_recent_event(event)
        self.publish_station_state(event)
        self.refresh_ui(full=True)

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

    def _on_recipe_select(self, event) -> None:
        selection = self.recipe_tree.selection()
        if not selection:
            return
        values = self.recipe_tree.item(selection[0], "values")
        self.selected_recipe_sequence = int(values[0])
        self.recipe_sequence_var.set(str(values[0]))
        self.recipe_part_var.set(str(values[2]))
        self.recipe_box_var.set(str(values[1]))

    def _set_recipe_selection_from_step(self, snapshot: dict, sequence: int) -> None:
        for step in snapshot["recipe_steps"]:
            if int(step["sequence"]) == int(sequence):
                self.recipe_sequence_var.set(str(step["sequence"]))
                self.recipe_part_var.set(str(step["part_name"]))
                if not self.recipe_box_var.get().strip() or self.selected_recipe_sequence != int(sequence):
                    self.recipe_box_var.set(str(step["box_number"]))
                self.selected_recipe_sequence = int(sequence)
                break

    def _focus_allows_text_input(self) -> bool:
        widget = self.root.focus_get()
        return widget is not None and widget.winfo_class() in TEXT_INPUT_CLASSES

    def _on_global_trigger_press(self, event) -> str | None:
        if self._focus_allows_text_input():
            return None
        self.simulate_station_button()
        return "break"

    def _handle_mqtt_command(self, payload: str) -> None:
        action = payload.strip().lower()
        if payload.startswith("{"):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = {}
            action = str(parsed.get("action", action)).strip().lower()
        if action == "reset":
            self.reset_cycle(source="mqtt_command")
        elif action == "undo":
            self.undo_last_operation(source="mqtt_command")

    def _poll_mqtt_events(self) -> None:
        ui_dirty = False
        while True:
            try:
                payload = self.bridge.events.get_nowait()
            except Empty:
                break

            if payload["type"] == "connection":
                ui_dirty = True
                if payload["connected"]:
                    self.publish_station_state()
            elif payload["type"] == "mqtt_message":
                if payload["topic"] == self.bridge.topics["button"]:
                    button_action = payload["payload"].lower()
                    if button_action == "press":
                        self._process_station_button(source="esp32")
                        ui_dirty = True
                    elif button_action == "double":
                        self.undo_last_operation(source="esp32")
                        ui_dirty = True
                elif payload["topic"] == self.bridge.topics["command"]:
                    self._handle_mqtt_command(payload["payload"])
                    ui_dirty = True

        if ui_dirty:
            self.refresh_ui(full=True)
        else:
            self._refresh_mqtt_status()
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
