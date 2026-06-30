from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


ALLOWED_PRESET_COMMANDS = (
    "start",
    "stop",
    "rev",
    "status",
    "q",
    "pickplace",
    "__reset_counts__",
    "cal x",
    "cal k",
    "cal s",
    "cal m",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_mqtt_client_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    token = token.strip("-_")
    return token or "host"


def _default_mqtt_client_id() -> str:
    host = _safe_mqtt_client_token(socket.gethostname())
    return f"mes-web-live-{host}-{os.getpid()}"


@dataclass(slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    module_id: str = "konveyor_main"
    module_type: str = "conveyor"
    module_title: str = "Konveyor Ana Hat"
    ui_phase: str = "live_ops"
    topic_root: str = "sau/iot/mega/konveyor"
    mqtt_host: str = "broker.emqx.io"
    mqtt_port: int = 1883
    mqtt_keepalive: int = 60
    mqtt_client_id: str = field(default_factory=_default_mqtt_client_id)
    mqtt_offline_grace_sec: int = 5
    command_mode: str = "full_live"
    publish_enabled: bool = True
    manual_command_enabled: bool = True
    vision_ingest_enabled: bool = True
    vision_ui_visible: bool = True
    analytics_ui_visible: bool = False
    oee_ui_visible: bool = True
    ws_coalesce_ms: int = 250
    heartbeat_timeout_sec: int = 10
    bridge_stale_after_sec: int = 30
    log_store_size: int = 200
    log_response_size: int = 50
    vision_event_store_size: int = 50
    vision_decision_deadline_ms: int = 300
    min_remaining_travel_ms_for_early_pick: int = 400
    vision_degraded_fps: float = 8.0
    vision_degraded_latency_ratio: float = 0.5
    vision_bad_window_threshold: int = 2
    vision_recovery_window_threshold: int = 3
    excel_enabled: bool = True
    excel_flush_interval_sec: float = 1.0
    excel_batch_size: int = 25
    db_enabled: bool = False
    db_host: str = "mes_postgres"
    db_port: int = 5432
    db_name: str = "mes"
    db_user: str = "mes"
    db_password: str = ""
    db_sslmode: str = "disable"
    db_connect_timeout_sec: int = 2
    db_mirror_work_orders: bool = False
    db_fail_open: bool = False
    db_log_failures: bool = False
    db_hook_production_completions: bool = False
    db_hook_vision_events: bool = False
    db_hook_oee_snapshots: bool = False
    db_hook_downtime_events: bool = False
    db_hook_maintenance_records: bool = False
    db_hook_quality_overrides: bool = False
    db_hook_station_events: bool = False
    db_hook_work_order_transitions: bool = False
    db_hook_production_completions_dry_run: bool = False
    db_hook_vision_events_dry_run: bool = False
    db_hook_oee_snapshots_dry_run: bool = False
    db_hook_station_events_dry_run: bool = False
    db_hook_work_order_transitions_dry_run: bool = False
    db_shadow_read_work_orders: bool = False
    db_read_work_orders: bool = False
    db_shadow_read_dashboard: bool = False
    db_read_dashboard: bool = False
    db_strict_timestamp_guard: bool = False
    mesql_api_base_url: str = "http://ferptop:8090"
    mesql_stations: tuple[str, ...] = ("ASSEMBLY_01", "PACKAGING_01")
    mesql_pull_timeout_sec: float = 10.0
    mesql_push_timeout_sec: float = 10.0
    allowed_presets: tuple[str, ...] = field(default_factory=lambda: ALLOWED_PRESET_COMMANDS)

    @property
    def package_dir(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def static_dir(self) -> Path:
        return self.package_dir / "static"

    @property
    def root_dir(self) -> Path:
        return self.package_dir.parent

    @property
    def logs_dir(self) -> Path:
        return self.root_dir / "logs"

    @property
    def default_excel_template_path(self) -> Path | None:
        for name in ("MES_Konveyor_Veritabani_Sablonu_v2.xlsx", "MES_Konveyor_Veritabani_Sablonu.xlsx"):
            candidate = self.root_dir / name
            if candidate.exists():
                return candidate
        return None

    @property
    def oee_runtime_state_path(self) -> Path:
        raw = os.getenv("MES_WEB_OEE_RUNTIME_STATE_PATH")
        if raw:
            return Path(raw)
        return self.logs_dir / "oee_runtime_state.json"

    @property
    def work_orders_dir(self) -> Path:
        raw = os.getenv("MES_WEB_WORK_ORDERS_DIR")
        if raw:
            return Path(raw)
        ferp_import_dir = self.ferp_import_dir
        if ferp_import_dir.exists():
            return ferp_import_dir
        return self.package_dir / "work_orders"

    @property
    def ferp_import_dir(self) -> Path:
        raw = os.getenv("MES_WEB_FERP_IMPORT_DIR")
        if raw:
            return Path(raw)
        return self.package_dir / "ferp_import"

    @property
    def ferp_labels_path(self) -> Path:
        raw = os.getenv("MES_WEB_FERP_LABELS_PATH")
        if raw:
            return Path(raw)
        return self.root_dir / "README" / "ferp_labels.xlsx"

    @property
    def ferp_export_pending_dir(self) -> Path:
        raw = os.getenv("MES_WEB_FERP_EXPORT_PENDING_DIR")
        if raw:
            return Path(raw)
        return self.logs_dir / "ferp_exports" / "pending"

    @property
    def ferp_export_examples_dir(self) -> Path:
        raw = os.getenv("MES_WEB_FERP_EXPORT_EXAMPLES_DIR")
        if raw:
            return Path(raw)
        return self.logs_dir / "ferp_exports" / "examples" / "ferp_xls_seeded"

    @property
    def ferp_xls_dir(self) -> Path:
        raw = os.getenv("MES_WEB_FERP_XLS_DIR")
        if raw:
            return Path(raw)
        return self.root_dir / "FERP_XLS"

    @property
    def excel_workbook_path(self) -> Path:
        raw = os.getenv("MES_WEB_EXCEL_WORKBOOK_PATH")
        if raw:
            return Path(raw)
        stamp = datetime.now().strftime("%d-%m-%Y")
        return self.logs_dir / f"MES_Konveyor_Veritabani_{stamp}.xlsx"

    @property
    def excel_template_path(self) -> Path | None:
        raw = os.getenv("MES_WEB_EXCEL_TEMPLATE_PATH")
        if raw:
            return Path(raw)
        return self.default_excel_template_path

    @property
    def topics(self) -> dict[str, str]:
        root = self.topic_root.rstrip("/")
        return {
            "status": f"{root}/status",
            "logs": f"{root}/logs",
            "heartbeat": f"{root}/heartbeat",
            "bridge_status": f"{root}/bridge/status",
            "tablet_log": f"{root}/tablet/log",
            "command": f"{root}/cmd",
            "vision_status": f"{root}/vision/status",
            "vision_tracks": f"{root}/vision/tracks",
            "vision_heartbeat": f"{root}/vision/heartbeat",
            "vision_events": f"{root}/vision/events",
        }

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            host=os.getenv("MES_WEB_HOST", "127.0.0.1"),
            port=int(os.getenv("MES_WEB_PORT", "8080")),
            module_id=os.getenv("MES_WEB_MODULE_ID", "konveyor_main"),
            module_type=os.getenv("MES_WEB_MODULE_TYPE", "conveyor"),
            module_title=os.getenv("MES_WEB_MODULE_TITLE", "Konveyor Ana Hat"),
            ui_phase=os.getenv("MES_WEB_UI_PHASE", "live_ops"),
            topic_root=os.getenv("MES_WEB_TOPIC_ROOT", "sau/iot/mega/konveyor"),
            mqtt_host=os.getenv("MES_WEB_MQTT_HOST", "broker.emqx.io"),
            mqtt_port=int(os.getenv("MES_WEB_MQTT_PORT", "1883")),
            mqtt_keepalive=int(os.getenv("MES_WEB_MQTT_KEEPALIVE", "60")),
            mqtt_client_id=os.getenv("MES_WEB_MQTT_CLIENT_ID") or _default_mqtt_client_id(),
            mqtt_offline_grace_sec=int(os.getenv("MES_WEB_MQTT_OFFLINE_GRACE_SEC", "5")),
            command_mode=os.getenv("MES_WEB_COMMAND_MODE", "full_live"),
            publish_enabled=_env_bool("MES_WEB_PUBLISH_ENABLED", True),
            manual_command_enabled=_env_bool("MES_WEB_MANUAL_COMMAND_ENABLED", True),
            vision_ingest_enabled=_env_bool("MES_WEB_VISION_INGEST_ENABLED", True),
            vision_ui_visible=_env_bool("MES_WEB_VISION_UI_VISIBLE", True),
            analytics_ui_visible=_env_bool("MES_WEB_ANALYTICS_UI_VISIBLE", False),
            oee_ui_visible=_env_bool("MES_WEB_OEE_UI_VISIBLE", True),
            ws_coalesce_ms=int(os.getenv("MES_WEB_WS_COALESCE_MS", "250")),
            heartbeat_timeout_sec=int(os.getenv("MES_WEB_HEARTBEAT_TIMEOUT_SEC", "10")),
            bridge_stale_after_sec=int(os.getenv("MES_WEB_BRIDGE_STALE_AFTER_SEC", "30")),
            log_store_size=int(os.getenv("MES_WEB_LOG_STORE_SIZE", "200")),
            log_response_size=int(os.getenv("MES_WEB_LOG_RESPONSE_SIZE", "50")),
            vision_event_store_size=int(os.getenv("MES_WEB_VISION_EVENT_STORE_SIZE", "50")),
            vision_decision_deadline_ms=int(os.getenv("MES_WEB_VISION_DECISION_DEADLINE_MS", "300")),
            min_remaining_travel_ms_for_early_pick=int(os.getenv("MES_WEB_MIN_REMAINING_TRAVEL_MS_FOR_EARLY_PICK", "400")),
            vision_degraded_fps=float(os.getenv("MES_WEB_VISION_DEGRADED_FPS", "8.0")),
            vision_degraded_latency_ratio=float(os.getenv("MES_WEB_VISION_DEGRADED_LATENCY_RATIO", "0.5")),
            vision_bad_window_threshold=int(os.getenv("MES_WEB_VISION_BAD_WINDOW_THRESHOLD", "2")),
            vision_recovery_window_threshold=int(os.getenv("MES_WEB_VISION_RECOVERY_WINDOW_THRESHOLD", "3")),
            excel_enabled=_env_bool("MES_WEB_EXCEL_ENABLED", True),
            excel_flush_interval_sec=float(os.getenv("MES_WEB_EXCEL_FLUSH_INTERVAL_SEC", "1.0")),
            excel_batch_size=int(os.getenv("MES_WEB_EXCEL_BATCH_SIZE", "25")),
            db_enabled=_env_bool("MES_WEB_DB_ENABLED", False),
            db_host=os.getenv("MES_WEB_DB_HOST", "mes_postgres"),
            db_port=int(os.getenv("MES_WEB_DB_PORT", "5432")),
            db_name=os.getenv("MES_WEB_DB_NAME", "mes"),
            db_user=os.getenv("MES_WEB_DB_USER", "mes"),
            db_password=os.getenv("MES_WEB_DB_PASSWORD", ""),
            db_sslmode=os.getenv("MES_WEB_DB_SSLMODE", "disable"),
            db_connect_timeout_sec=int(os.getenv("MES_WEB_DB_CONNECT_TIMEOUT_SEC", "2")),
            db_mirror_work_orders=_env_bool("MES_WEB_DB_MIRROR_WORK_ORDERS", False),
            db_fail_open=_env_bool("MES_WEB_DB_FAIL_OPEN", False),
            db_log_failures=_env_bool("MES_WEB_DB_LOG_FAILURES", False),
            db_hook_production_completions=_env_bool("MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS", False),
            db_hook_vision_events=_env_bool("MES_WEB_DB_HOOK_VISION_EVENTS", False),
            db_hook_oee_snapshots=_env_bool("MES_WEB_DB_HOOK_OEE_SNAPSHOTS", False),
            db_hook_downtime_events=_env_bool("MES_WEB_DB_HOOK_DOWNTIME_EVENTS", False),
            db_hook_maintenance_records=_env_bool("MES_WEB_DB_HOOK_MAINTENANCE_RECORDS", False),
            db_hook_quality_overrides=_env_bool("MES_WEB_DB_HOOK_QUALITY_OVERRIDES", False),
            db_hook_station_events=_env_bool("MES_WEB_DB_HOOK_STATION_EVENTS", False),
            db_hook_work_order_transitions=_env_bool("MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS", False),
            db_hook_production_completions_dry_run=_env_bool("MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN", False),
            db_hook_vision_events_dry_run=_env_bool("MES_WEB_DB_HOOK_VISION_EVENTS_DRY_RUN", False),
            db_hook_oee_snapshots_dry_run=_env_bool("MES_WEB_DB_HOOK_OEE_SNAPSHOTS_DRY_RUN", False),
            db_hook_station_events_dry_run=_env_bool("MES_WEB_DB_HOOK_STATION_EVENTS_DRY_RUN", False),
            db_hook_work_order_transitions_dry_run=_env_bool("MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS_DRY_RUN", False),
            db_shadow_read_work_orders=_env_bool("MES_WEB_DB_SHADOW_READ_WORK_ORDERS", False),
            db_read_work_orders=_env_bool("MES_WEB_DB_READ_WORK_ORDERS", False),
            db_shadow_read_dashboard=_env_bool("MES_WEB_DB_SHADOW_READ_DASHBOARD", False),
            db_read_dashboard=_env_bool("MES_WEB_DB_READ_DASHBOARD", False),
            db_strict_timestamp_guard=_env_bool("MES_WEB_DB_STRICT_TIMESTAMP_GUARD", False),
            mesql_api_base_url=os.getenv("MESQL_API_BASE_URL", "http://ferptop:8090"),
            mesql_stations=tuple(
                station.strip().upper()
                for station in os.getenv("MESQL_STATIONS", "ASSEMBLY_01,PACKAGING_01").split(",")
                if station.strip()
            ),
            mesql_pull_timeout_sec=float(os.getenv("MESQL_PULL_TIMEOUT_SEC", "10")),
            mesql_push_timeout_sec=float(os.getenv("MESQL_PUSH_TIMEOUT_SEC", "10")),
        )
