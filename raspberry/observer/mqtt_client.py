from __future__ import annotations

import json
from typing import Any, Callable

from .config import MqttConfig

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - handled at runtime
    mqtt = None


class ObserverMqttClient:
    def __init__(self, config: MqttConfig) -> None:
        self.config = config
        self.enabled = config.enabled
        self.client = None
        self.connected = False
        self._json_handlers: dict[str, Callable[[Any, str], None]] = {}

        if not self.enabled:
            return
        if mqtt is None:
            raise RuntimeError("paho-mqtt is not installed. Run: pip install -r requirements.txt")

        self.client = self._create_client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=5)

    def _create_client(self) -> mqtt.Client:
        callback_api = getattr(mqtt, "CallbackAPIVersion", None)
        if callback_api is not None:
            try:
                return mqtt.Client(
                    callback_api_version=callback_api.VERSION1,
                    client_id=self.config.client_id,
                )
            except TypeError:
                pass
        return mqtt.Client(client_id=self.config.client_id)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: int) -> None:
        self.connected = rc == 0
        if self.connected:
            for suffix in self._json_handlers:
                topic = self._topic(suffix)
                client.subscribe(topic, qos=self.config.qos)
            print(f"MQTT connected: {self.config.host}:{self.config.port}")
        else:
            print(f"MQTT connect failed, rc={rc}")

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        self.connected = False
        print(f"MQTT disconnected, rc={rc}")

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: Any) -> None:
        suffix = self._suffix_from_topic(str(getattr(msg, "topic", "") or ""))
        if suffix not in self._json_handlers:
            return

        try:
            payload_text = msg.payload.decode("utf-8", errors="replace")
            try:
                payload: Any = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = payload_text
            self._json_handlers[suffix](payload, str(msg.topic))
        except Exception as exc:
            print(f"MQTT handler failed for {msg.topic}: {exc}")

    def connect(self) -> bool:
        if not self.enabled or self.client is None:
            return False

        try:
            self.client.connect(self.config.host, self.config.port, self.config.keepalive)
            self.client.loop_start()
            return True
        except Exception as exc:  # pragma: no cover - depends on network
            print(f"MQTT disabled after connection error: {exc}")
            self.enabled = False
            return False

    def disconnect(self) -> None:
        if not self.enabled or self.client is None:
            return
        self.client.loop_stop()
        self.client.disconnect()

    def register_json_handler(self, suffix: str, handler: Callable[[Any, str], None]) -> None:
        clean_suffix = suffix.strip("/")
        self._json_handlers[clean_suffix] = handler
        if self.connected and self.client is not None:
            self.client.subscribe(self._topic(clean_suffix), qos=self.config.qos)

    def publish_json(self, suffix: str, payload: dict[str, Any], retain: bool = False) -> None:
        if not self.enabled or self.client is None:
            return
        self.client.publish(
            self._topic(suffix),
            json.dumps(payload, ensure_ascii=False),
            qos=self.config.qos,
            retain=retain,
        )

    def publish_text(self, suffix: str, payload: str, retain: bool = False) -> None:
        if not self.enabled or self.client is None:
            return
        self.client.publish(
            self._topic(suffix),
            payload,
            qos=self.config.qos,
            retain=retain,
        )

    def _topic(self, suffix: str) -> str:
        root = self.config.topic_root.strip("/")
        clean_suffix = suffix.strip("/")
        if not clean_suffix:
            return root
        return f"{root}/{clean_suffix}"

    def _suffix_from_topic(self, topic: str) -> str:
        root = self.config.topic_root.strip("/")
        clean_topic = topic.strip("/")
        if clean_topic == root:
            return ""
        prefix = f"{root}/"
        if clean_topic.startswith(prefix):
            return clean_topic[len(prefix) :]
        return clean_topic
