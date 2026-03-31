from __future__ import annotations

import json
import queue
from typing import Any

import paho.mqtt.client as mqtt

from .config import MQTT_CONFIG_PATH
from .storage import read_json


class MqttBridge:
    def __init__(self) -> None:
        self.config = read_json(
            MQTT_CONFIG_PATH,
            {
                "broker_host": "broker.emqx.io",
                "broker_port": 1883,
                "topic_root": "sau/iot/mega/konveyor/picktolight",
                "station_id": "assembly_01",
                "keepalive": 60,
            },
        )
        self.topic_root = self.config["topic_root"].rstrip("/")
        self.topics = {
            "state": f"{self.topic_root}/station/state",
            "display": f"{self.topic_root}/station/display",
            "button": f"{self.topic_root}/station/button",
            "command": f"{self.topic_root}/station/command",
            "event": f"{self.topic_root}/station/event",
            "python_status": f"{self.topic_root}/station/python_status",
            "esp32_status": f"{self.topic_root}/station/esp32_status",
            "heartbeat": f"{self.topic_root}/station/heartbeat",
        }
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.connected = False

        client_id = f"{self.config['station_id']}_python_gui"
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        except AttributeError:
            self.client = mqtt.Client(client_id=client_id)

        self.client.enable_logger()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.will_set(
            self.topics["python_status"],
            payload=json.dumps({"status": "offline", "station_id": self.config["station_id"]}),
            qos=0,
            retain=True,
        )

    def connect(self) -> None:
        self.client.connect_async(
            self.config["broker_host"],
            int(self.config.get("broker_port", 1883)),
            int(self.config.get("keepalive", 60)),
        )
        self.client.loop_start()

    def disconnect(self) -> None:
        try:
            if self.connected:
                self.client.publish(
                    self.topics["python_status"],
                    json.dumps({"status": "offline", "station_id": self.config["station_id"]}),
                    retain=True,
                )
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self.connected = True
        client.subscribe(self.topics["button"])
        client.subscribe(self.topics["command"])
        client.publish(
            self.topics["python_status"],
            json.dumps({"status": "online", "station_id": self.config["station_id"]}),
            retain=True,
        )
        self.events.put({"type": "connection", "connected": True})

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags=None,
        reason_code=0,
        properties=None,
    ) -> None:
        self.connected = False
        self.events.put({"type": "connection", "connected": False})

    def _on_message(self, client, userdata, message) -> None:
        payload = message.payload.decode("utf-8", errors="replace").strip()
        self.events.put(
            {
                "type": "mqtt_message",
                "topic": message.topic,
                "payload": payload,
            }
        )

    def publish_state(self, snapshot: dict[str, Any]) -> bool:
        return self._publish_json(self.topics["state"], snapshot, retain=True)

    def publish_event(self, payload: dict[str, Any]) -> bool:
        return self._publish_json(self.topics["event"], payload, retain=False)

    def publish_heartbeat(self, payload: dict[str, Any]) -> bool:
        return self._publish_json(self.topics["heartbeat"], payload, retain=False)

    def publish_display(self, lines: list[str]) -> bool:
        return self._publish_text(self.topics["display"], "~".join(lines), retain=True)

    def _publish_json(self, topic: str, payload: dict[str, Any], retain: bool) -> bool:
        return self._publish_text(topic, json.dumps(payload, ensure_ascii=False), retain=retain)

    def _publish_text(self, topic: str, payload: str, retain: bool) -> bool:
        if not self.connected:
            return False

        message_info = self.client.publish(topic, payload, qos=0, retain=retain)
        return message_info.rc == mqtt.MQTT_ERR_SUCCESS
