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
        return self.package_dir / "work_orders"

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
        )
