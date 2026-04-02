from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config import AppConfig
from .oee_state import OeeRuntimeStateManager
from .store import DashboardStore, utc_now_text

if TYPE_CHECKING:
    from .excel_runtime import ExcelRuntimeSink


class MqttIngestClient:
    def __init__(
        self,
        config: AppConfig,
        store: DashboardStore,
        *,
        excel_sink: "ExcelRuntimeSink | None" = None,
        oee_state_manager: OeeRuntimeStateManager | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.excel_sink = excel_sink
        self.oee_state_manager = oee_state_manager
        self._mqtt: Any | None = None
        self.client: Any | None = None
        self.connected = False

    def start(self) -> bool:
        try:
            import paho.mqtt.client as mqtt
        except ModuleNotFoundError:
            self.store.set_mqtt_connection(False)
            return False

        self._mqtt = mqtt
        try:
            callback_api = getattr(mqtt, "CallbackAPIVersion", None)
            if callback_api is not None:
                self.client = mqtt.Client(callback_api.VERSION2, client_id=self.config.mqtt_client_id)
            else:
                self.client = mqtt.Client(client_id=self.config.mqtt_client_id)
        except TypeError:
            self.client = mqtt.Client(client_id=self.config.mqtt_client_id)

        self.client.enable_logger()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.connect_async(self.config.mqtt_host, self.config.mqtt_port, self.config.mqtt_keepalive)
        self.client.loop_start()
        return True

    def stop(self) -> None:
        if self.client is None:
            return
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
            self.connected = False
            self.store.set_mqtt_connection(False)

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        del userdata, flags, properties
        success = getattr(reason_code, "value", reason_code) == 0
        self.connected = bool(success)
        self.store.set_mqtt_connection(self.connected)
        if not self.connected:
            return
        for topic_name, topic in self.config.topics.items():
            if topic_name == "command":
                continue
            client.subscribe(topic)

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any = None,
        reason_code: Any = 0,
        properties: Any = None,
    ) -> None:
        del client, userdata, disconnect_flags, reason_code, properties
        self.connected = False
        self.store.set_mqtt_connection(False)

    def _decode(self, payload: Any) -> str:
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
        return str(payload)

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        del client, userdata
        topic = str(message.topic)
        payload = self._decode(message.payload)
        stamp = utc_now_text()
        module_id = self.config.module_id
        topics = self.config.topics

        if topic == topics["status"]:
            self.store.apply_status_line(module_id, payload, received_at=stamp)
            return
        if topic == topics["logs"]:
            self.store.apply_log_line(module_id, payload, topic=topic, received_at=stamp)
            if self.excel_sink is not None:
                self.excel_sink.record_mega_log(payload, stamp)
            if self.oee_state_manager is not None and self.oee_state_manager.apply_mega_log(payload, stamp):
                self.store.refresh_oee_runtime_state(module_id, force=True)
            return
        if topic == topics["heartbeat"]:
            self.store.apply_heartbeat(module_id, received_at=stamp)
            return
        if topic == topics["bridge_status"]:
            self.store.apply_bridge_status(module_id, payload, received_at=stamp)
            return
        if topic == topics["tablet_log"]:
            if self.oee_state_manager is not None and self.oee_state_manager.apply_tablet_fault_log(payload, stamp):
                self.store.refresh_oee_runtime_state(module_id, force=True)
            self.store.apply_tablet_log(module_id, payload, received_at=stamp)
            return
        if topic == topics["vision_status"]:
            self.store.apply_vision_status(module_id, payload, received_at=stamp)
            return
        if topic == topics["vision_tracks"]:
            self.store.apply_vision_tracks(module_id, payload, received_at=stamp)
            return
        if topic == topics["vision_heartbeat"]:
            self.store.apply_vision_heartbeat(module_id, payload, received_at=stamp)
            return
        if topic == topics["vision_events"]:
            self.store.apply_vision_event(module_id, payload, received_at=stamp)
            if self.excel_sink is not None and self.config.vision_ingest_enabled:
                self.excel_sink.record_vision_event(payload, stamp)

    def publish_command(self, payload: str) -> None:
        if self.client is None or self._mqtt is None:
            raise RuntimeError("MQTT_UNAVAILABLE")
        if not self.connected:
            raise RuntimeError("MQTT_OFFLINE")
        message_info = self.client.publish(self.config.topics["command"], payload, qos=0, retain=False)
        if message_info.rc != self._mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT_PUBLISH_FAILED")
