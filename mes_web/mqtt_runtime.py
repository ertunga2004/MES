from __future__ import annotations

import logging
import math
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import AppConfig
from .db.work_order_transition_writer import mirror_work_order_transition_from_state
from .oee_state import OeeRuntimeStateManager
from .store import DashboardStore, utc_now_text
from . import station_execution
from .db import mesql_v2

if TYPE_CHECKING:
    from .excel_runtime import ExcelRuntimeSink


@dataclass(slots=True)
class _StationExecutionDelivery:
    topic: str
    command: dict[str, Any] | None
    client: Any
    mid: int
    qos: int
    generation: int | None = None
    _acknowledged: bool = False
    _ack_lock: threading.Lock = field(default_factory=threading.Lock)

    def acknowledge(self, success_code: Any) -> bool:
        if self.qos <= 0:
            return True
        with self._ack_lock:
            if self._acknowledged:
                return True
            result = self.client.ack(self.mid, self.qos)
            if result != success_code:
                return False
            self._acknowledged = True
            return True


@dataclass(frozen=True, slots=True)
class _StationExecutionStartupFailureCleanup:
    error_code: str
    generation: int | None
    client: Any | None
    mqtt: Any | None
    work_queue: queue.Queue[_StationExecutionDelivery | None] | None
    worker: threading.Thread | None
    stop_event: threading.Event
    startup_event: threading.Event
    completion_event: threading.Event


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
        self._station_execution_topics: dict[str, dict[str, Any]] = {}
        self._station_execution_queue: queue.Queue[_StationExecutionDelivery | None] | None = None
        self._station_execution_worker: threading.Thread | None = None
        self._station_execution_stop_event = threading.Event()
        self._station_execution_accepting = False
        self._station_execution_operation_lock = threading.Lock()
        self._station_execution_lifecycle_lock = threading.RLock()
        self._station_execution_state = "stopped"
        self._station_execution_queue_wait_seconds = 0.1
        self._station_execution_stop_timeout_seconds = 5.0
        self._station_execution_startup_timeout_seconds = 5.0
        self._station_execution_queue_maxsize = 128
        self._station_execution_startup_event = threading.Event()
        self._station_execution_startup_error: str | None = None
        self._station_execution_pending_subscriptions: set[int] = set()
        self._station_execution_subscription_generation = 0
        self._station_execution_active_subscription_generation: int | None = None
        self._station_execution_startup_failure_cleanup: (
            _StationExecutionStartupFailureCleanup | None
        ) = None
        enqueue_timeout = float(
            self.config.mqtt_station_execution_enqueue_timeout_seconds
        )
        if (
            not math.isfinite(enqueue_timeout)
            or enqueue_timeout <= 0
            or enqueue_timeout > 60.0
        ):
            raise ValueError(
                "MES_WEB_MQTT_STATION_EXECUTION_ENQUEUE_TIMEOUT_SECONDS "
                "must be finite and in the range (0, 60.0]"
            )
        self._station_execution_enqueue_timeout_seconds = enqueue_timeout

    def _record_work_order_state(self, received_at: str, *, event_type: str = "runtime_state_changed") -> None:
        if self.oee_state_manager is None:
            return
        state = self.oee_state_manager.read_state()
        try:
            mirror_work_order_transition_from_state(self.config, state, event_type=event_type)
        except Exception as exc:
            if self.config.db_log_failures:
                print(f"[LIVE:work_order_transitions] WARNING: Exception in MQTT work order transition hook: {exc}")
        if self.excel_sink is not None:
            self.excel_sink.record_work_order_state(state, received_at)

    def start(self) -> bool:
        with self._station_execution_operation_lock:
            return self._start_serialized()

    def _start_serialized(self) -> bool:
        station_adapter_enabled = bool(
            self.config.db_enabled
            and self.config.db_station_execution_commands_enabled
            and self.config.mqtt_station_execution_adapter_enabled
        )
        try:
            import paho.mqtt.client as mqtt
        except ModuleNotFoundError:
            self.store.set_mqtt_connection(False)
            if station_adapter_enabled:
                raise RuntimeError(
                    "STATION_EXECUTION_MQTT_MANUAL_ACK_UNAVAILABLE"
                )
            return False

        with self._station_execution_lifecycle_lock:
            if self._station_execution_state == "running":
                return True
            if self._station_execution_state in {"starting", "stopping"}:
                raise RuntimeError("STATION_EXECUTION_MQTT_LIFECYCLE_BUSY")
            worker = self._station_execution_worker
            if worker is not None and worker.is_alive():
                raise RuntimeError("STATION_EXECUTION_MQTT_WORKER_STILL_RUNNING")
            if self.client is not None:
                if not station_adapter_enabled:
                    return True
                raise RuntimeError("STATION_EXECUTION_MQTT_CLIENT_CLEANUP_REQUIRED")
            if station_adapter_enabled:
                self._station_execution_state = "starting"
                self._station_execution_startup_event = threading.Event()
                self._station_execution_startup_error = None
                self._station_execution_startup_failure_cleanup = None
                self._station_execution_pending_subscriptions.clear()
                self._station_execution_active_subscription_generation = None

        try:
            if station_adapter_enabled:
                self._station_execution_topics = (
                    station_execution.load_station_execution_mqtt_topics(self.config)
                )
                if not self._station_execution_topics:
                    raise RuntimeError("STATION_EXECUTION_MQTT_CONFIG_INVALID")
                legacy_topics = {
                    str(topic) for topic in self.config.topics.values() if topic
                }
                if legacy_topics.intersection(self._station_execution_topics):
                    raise RuntimeError("STATION_EXECUTION_MQTT_TOPIC_CONFLICT")
                if not self.config.mqtt_station_execution_client_id.strip():
                    raise RuntimeError("STATION_EXECUTION_MQTT_CLIENT_ID_REQUIRED")
                if not self._start_station_execution_worker(accepting=False):
                    raise RuntimeError("STATION_EXECUTION_MQTT_WORKER_START_FAILED")

            self._mqtt = mqtt
            callback_api = getattr(mqtt, "CallbackAPIVersion", None)
            try:
                kwargs = {
                    "client_id": (
                        self.config.mqtt_station_execution_client_id
                        if station_adapter_enabled
                        else self.config.mqtt_client_id
                    ),
                    "clean_session": not station_adapter_enabled,
                    "manual_ack": station_adapter_enabled,
                }
                if callback_api is not None:
                    self.client = mqtt.Client(callback_api.VERSION2, **kwargs)
                else:
                    self.client = mqtt.Client(**kwargs)
            except TypeError:
                self.client = mqtt.Client(
                    client_id=(
                        self.config.mqtt_station_execution_client_id
                        if station_adapter_enabled
                        else self.config.mqtt_client_id
                    ),
                    clean_session=not station_adapter_enabled,
                )
            if station_adapter_enabled:
                manual_ack_set = getattr(self.client, "manual_ack_set", None)
                ack = getattr(self.client, "ack", None)
                if not callable(manual_ack_set) or not callable(ack):
                    raise RuntimeError("STATION_EXECUTION_MQTT_MANUAL_ACK_UNAVAILABLE")
                manual_ack_set(True)

            self.client.enable_logger()
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            connect_result = self.client.connect_async(
                self.config.mqtt_host,
                self.config.mqtt_port,
                self.config.mqtt_keepalive,
            )
            success_code = getattr(mqtt, "MQTT_ERR_SUCCESS", 0)
            if connect_result not in {None, success_code}:
                raise RuntimeError("STATION_EXECUTION_MQTT_CONNECT_FAILED")
            loop_result = self.client.loop_start()
            if loop_result not in {None, success_code}:
                raise RuntimeError("STATION_EXECUTION_MQTT_LOOP_START_FAILED")
            if not station_adapter_enabled:
                return True
            if not self._station_execution_startup_event.wait(
                self._station_execution_startup_timeout_seconds
            ):
                raise RuntimeError("STATION_EXECUTION_MQTT_STARTUP_TIMEOUT")
            with self._station_execution_lifecycle_lock:
                if self._station_execution_state == "running":
                    return True
                error_code = (
                    self._station_execution_startup_error
                    or "STATION_EXECUTION_MQTT_STARTUP_FAILED"
                )
            raise RuntimeError(error_code)
        except Exception:
            self._rollback_station_execution_startup()
            raise

    def stop(self) -> bool:
        with self._station_execution_operation_lock:
            return self._stop_serialized()

    def _stop_serialized(self) -> bool:
        if not self._stop_station_execution_worker():
            return False
        with self._station_execution_lifecycle_lock:
            if self._station_execution_startup_failure_cleanup is not None:
                return True
            client = self.client
        if client is None:
            return True
        try:
            client.disconnect()
        finally:
            client.loop_stop()
            self.connected = False
            self.store.set_mqtt_connection(False)
            self.client = None
            self._mqtt = None
        return True

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        del userdata, flags, properties
        station_adapter_enabled = bool(
            self.config.db_enabled
            and self.config.db_station_execution_commands_enabled
            and self.config.mqtt_station_execution_adapter_enabled
        )
        success = getattr(reason_code, "value", reason_code) == 0
        if not station_adapter_enabled:
            self.connected = bool(success)
            self.store.set_mqtt_connection(self.connected)
            if not self.connected:
                return
            success_code = getattr(self._mqtt, "MQTT_ERR_SUCCESS", 0)
            for topic_name, topic in self.config.topics.items():
                if topic_name == "command":
                    continue
                legacy_subscription = client.subscribe(topic)
                if (
                    isinstance(legacy_subscription, tuple)
                    and legacy_subscription
                    and legacy_subscription[0] != success_code
                ):
                    return
            return

        with self._station_execution_lifecycle_lock:
            if (
                client is not self.client
                or self._station_execution_state not in {"starting", "running"}
                or self._station_execution_stop_event.is_set()
            ):
                return
            self._station_execution_accepting = False
            self._station_execution_pending_subscriptions.clear()
            self._station_execution_state = "starting"
            self._station_execution_subscription_generation += 1
            generation = self._station_execution_subscription_generation
            self._station_execution_active_subscription_generation = generation
            # Each callback closure carries the connection-attempt identity;
            # a retired callback can never borrow a reused MID or delivery.
            client.on_subscribe = self._station_execution_suback_callback(
                generation
            )
            client.on_message = self._station_execution_message_callback(
                generation,
                client,
            )
            client.on_disconnect = self._station_execution_disconnect_callback(
                generation,
                client,
            )
            self.connected = bool(success)
            self.store.set_mqtt_connection(self.connected)
        if not success:
            self._fail_station_execution_startup(
                "STATION_EXECUTION_MQTT_CONNECT_FAILED",
                client=client,
                generation=generation,
            )
            return
        try:
            self._subscribe_station_execution_generation(client, generation)
        except Exception:
            self._fail_station_execution_startup(
                "STATION_EXECUTION_MQTT_SUBSCRIBE_FAILED",
                client=client,
                generation=generation,
            )

    def _station_execution_startup_generation_is_current_locked(
        self,
        client: Any,
        generation: int | None,
    ) -> bool:
        return bool(
            generation is not None
            and client is self.client
            and self._station_execution_state == "starting"
            and generation
            == self._station_execution_active_subscription_generation
            and not self._station_execution_stop_event.is_set()
        )

    def _subscribe_station_execution_generation(
        self,
        client: Any,
        generation: int | None,
    ) -> bool:
        # The lifecycle lock intentionally spans validation, broker subscribe,
        # and MID registration. stop() uses the same lock to retire the
        # generation, so it must win either before this entire unit or after it.
        with self._station_execution_lifecycle_lock:
            if not self._station_execution_startup_generation_is_current_locked(
                client,
                generation,
            ):
                return False
            success_code = getattr(self._mqtt, "MQTT_ERR_SUCCESS", 0)
            for topic_name, topic in self.config.topics.items():
                if topic_name == "command":
                    continue
                legacy_subscription = client.subscribe(topic)
                if (
                    isinstance(legacy_subscription, tuple)
                    and legacy_subscription
                    and legacy_subscription[0] != success_code
                ):
                    raise RuntimeError("STATION_EXECUTION_MQTT_SUBSCRIBE_FAILED")
                if not self._station_execution_startup_generation_is_current_locked(
                    client,
                    generation,
                ):
                    return False
            for topic in sorted(self._station_execution_topics):
                subscription = client.subscribe(topic, qos=1)
                if (
                    not isinstance(subscription, tuple)
                    or len(subscription) < 2
                    or subscription[0] != success_code
                ):
                    raise RuntimeError("STATION_EXECUTION_MQTT_SUBSCRIBE_FAILED")
                if not self._station_execution_startup_generation_is_current_locked(
                    client,
                    generation,
                ):
                    return False
                self._station_execution_pending_subscriptions.add(
                    int(subscription[1])
                )
            return True

    def _station_execution_suback_callback(self, generation: int):
        def _callback(
            client: Any,
            userdata: Any,
            mid: int,
            reason_codes: Any,
            properties: Any = None,
        ) -> None:
            self._on_subscribe(
                generation,
                client,
                userdata,
                mid,
                reason_codes,
                properties,
            )

        return _callback

    def _station_execution_message_callback(
        self,
        generation: int,
        expected_client: Any,
    ):
        def _callback(client: Any, userdata: Any, message: Any) -> None:
            with self._station_execution_lifecycle_lock:
                if (
                    client is not expected_client
                    or generation
                    != self._station_execution_active_subscription_generation
                    or (self.client is not None and client is not self.client)
                ):
                    return
            self._on_message(
                client,
                userdata,
                message,
                station_execution_generation=generation,
            )

        return _callback

    def _station_execution_disconnect_callback(
        self,
        generation: int,
        expected_client: Any,
    ):
        def _callback(
            client: Any,
            userdata: Any,
            disconnect_flags: Any = None,
            reason_code: Any = 0,
            properties: Any = None,
        ) -> None:
            if client is not expected_client:
                return
            self._on_disconnect(
                client,
                userdata,
                disconnect_flags,
                reason_code,
                properties,
                station_execution_generation=generation,
            )

        return _callback

    def _on_subscribe(
        self,
        generation: int,
        client: Any,
        userdata: Any,
        mid: int,
        reason_codes: Any,
        properties: Any = None,
    ) -> None:
        del userdata, properties
        codes = reason_codes if isinstance(reason_codes, (list, tuple)) else [reason_codes]
        rejected = any(
            bool(getattr(code, "is_failure", False))
            or int(getattr(code, "value", code) or 0) >= 128
            for code in codes
        )
        if rejected:
            with self._station_execution_lifecycle_lock:
                if (
                    not self._station_execution_startup_generation_is_current_locked(
                        client,
                        generation,
                    )
                    or int(mid)
                    not in self._station_execution_pending_subscriptions
                ):
                    return
            self._fail_station_execution_startup(
                "STATION_EXECUTION_MQTT_SUBSCRIBE_REJECTED",
                client=client,
                generation=generation,
            )
            return
        with self._station_execution_lifecycle_lock:
            if (
                not self._station_execution_startup_generation_is_current_locked(
                    client,
                    generation,
                )
                or int(mid) not in self._station_execution_pending_subscriptions
            ):
                return
            self._station_execution_pending_subscriptions.discard(int(mid))
            worker = self._station_execution_worker
            if (
                not self._station_execution_pending_subscriptions
                and worker is not None
                and worker.is_alive()
            ):
                self._station_execution_accepting = True
                self._station_execution_state = "running"
                self._station_execution_startup_event.set()

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any = None,
        reason_code: Any = 0,
        properties: Any = None,
        *,
        station_execution_generation: int | None = None,
    ) -> None:
        del userdata, disconnect_flags, reason_code, properties
        with self._station_execution_lifecycle_lock:
            if (
                station_execution_generation is not None
                and (
                    station_execution_generation
                    != self._station_execution_active_subscription_generation
                    or (self.client is not None and client is not self.client)
                )
            ):
                return
        self.connected = False
        self.store.set_mqtt_connection(False)
        with self._station_execution_lifecycle_lock:
            self._station_execution_accepting = False
            self._station_execution_pending_subscriptions.clear()
            self._station_execution_active_subscription_generation = None
            if self._station_execution_state in {"starting", "running"}:
                self._station_execution_state = "starting"

    def _decode(self, payload: Any) -> str:
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
        return str(payload)

    def _on_message(
        self,
        client: Any,
        userdata: Any,
        message: Any,
        *,
        station_execution_generation: int | None = None,
    ) -> None:
        del userdata
        topic = str(message.topic)
        payload = self._decode(message.payload)
        stamp = utc_now_text()
        module_id = self.config.module_id
        topics = self.config.topics

        station_adapter_enabled = bool(
            self.config.db_enabled
            and self.config.db_station_execution_commands_enabled
            and self.config.mqtt_station_execution_adapter_enabled
        )
        if station_adapter_enabled and topic in self._station_execution_topics:
            with self._station_execution_lifecycle_lock:
                if station_execution_generation is not None and (
                    station_execution_generation
                    != self._station_execution_active_subscription_generation
                    or (self.client is not None and client is not self.client)
                    or not self._station_execution_accepting
                    or self._station_execution_state != "running"
                ):
                    return
            if bool(getattr(message, "retain", False)):
                self._log_station_execution_ignored(
                    topic=topic,
                    error_code="STATION_EXECUTION_MQTT_RETAINED_NOT_ALLOWED",
                )
                self._ack_station_execution_delivery(
                    self._delivery_from_message(
                        client,
                        message,
                        topic,
                        None,
                        generation=station_execution_generation,
                    ),
                )
                return
            raw_payload = message.payload
            if not isinstance(raw_payload, bytes):
                raw_payload = bytes(raw_payload) if isinstance(raw_payload, bytearray) else b""
            values = {
                "command_source": "mqtt",
                "station_code": self._station_execution_topics[topic].get(
                    "station_code"
                ),
                "event_source": self._station_execution_topics[topic].get(
                    "event_source"
                ),
            }
            started_at = time.perf_counter()
            try:
                command = station_execution.map_station_execution_mqtt_message(
                    topic,
                    raw_payload,
                    self._station_execution_topics,
                )
            except mesql_v2.MesqlV2Error as exc:
                self._log_station_execution_command(
                    values,
                    result=None,
                    error_code=exc.detail,
                    started_at=started_at,
                )
                if 400 <= exc.status_code < 500:
                    self._ack_station_execution_delivery(
                        self._delivery_from_message(
                            client,
                            message,
                            topic,
                            None,
                            generation=station_execution_generation,
                        )
                    )
                return
            except Exception:
                self._log_station_execution_command(
                    values,
                    result=None,
                    error_code="INTERNAL_ERROR",
                    started_at=started_at,
                )
                return
            delivery = self._delivery_from_message(
                client,
                message,
                topic,
                command,
                generation=station_execution_generation,
            )
            if not self._enqueue_station_execution_message(delivery):
                self._log_station_execution_ignored(
                    topic=topic,
                    error_code=(
                        "STATION_EXECUTION_MQTT_ADAPTER_STOPPING"
                        if self._station_execution_stop_event.is_set()
                        else "STATION_EXECUTION_MQTT_QUEUE_TIMEOUT"
                    ),
                )
            return

        if topic == topics["status"]:
            self.store.apply_status_line(module_id, payload, received_at=stamp)
            return
        if topic == topics["logs"]:
            self.store.apply_log_line(module_id, payload, topic=topic, received_at=stamp)
            if self.excel_sink is not None:
                self.excel_sink.record_mega_log(payload, stamp)
            if self.oee_state_manager is not None and self.oee_state_manager.apply_mega_log(payload, stamp):
                self._record_work_order_state(stamp)
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
                self._record_work_order_state(stamp, event_type="tablet_fault_state_changed")
                self.store.refresh_oee_runtime_state(module_id, force=True)
            self.store.apply_tablet_log(module_id, payload, received_at=stamp)
            if self.excel_sink is not None:
                self.excel_sink.record_tablet_log(payload, stamp)
            return
        if topic == topics["vision_status"]:
            self.store.apply_vision_status(module_id, payload, received_at=stamp)
            if self.oee_state_manager is not None and self.oee_state_manager.apply_vision_status(payload, stamp):
                self.store.refresh_oee_runtime_state(module_id, force=True)
            return
        if topic == topics["vision_tracks"]:
            self.store.apply_vision_tracks(module_id, payload, received_at=stamp)
            if self.oee_state_manager is not None and self.oee_state_manager.apply_vision_tracks(payload, stamp):
                self.store.refresh_oee_runtime_state(module_id, force=True)
            return
        if topic == topics["vision_heartbeat"]:
            self.store.apply_vision_heartbeat(module_id, payload, received_at=stamp)
            if self.oee_state_manager is not None and self.oee_state_manager.apply_vision_heartbeat(payload, stamp):
                self.store.refresh_oee_runtime_state(module_id, force=True)
            return
        if topic == topics["vision_events"]:
            vision_result = (
                self.oee_state_manager.apply_vision_event(payload, stamp)
                if self.oee_state_manager is not None
                else {"changed": False, "publish_command": None, "item_id": "", "payload": payload}
            )
            vision_payload = vision_result.get("payload") if isinstance(vision_result, dict) else payload
            self.store.apply_vision_event(module_id, vision_payload, received_at=stamp)
            if self.excel_sink is not None and self.config.vision_ingest_enabled:
                self.excel_sink.record_vision_event(vision_payload, stamp)
            if isinstance(vision_result, dict) and vision_result.get("changed"):
                self.store.refresh_oee_runtime_state(module_id, force=True)
            command = str((vision_result or {}).get("publish_command") or "").strip() if isinstance(vision_result, dict) else ""
            item_id = str((vision_result or {}).get("item_id") or "").strip() if isinstance(vision_result, dict) else ""
            if command:
                try:
                    self.publish_command(command)
                except RuntimeError as exc:
                    self.store.append_system_log(
                        module_id,
                        f"SYSTEM|VISION|EARLY_PICK_REQUEST_FAILED|ITEM_ID={item_id}|ERROR={str(exc)}",
                        topic="local/vision",
                        received_at=stamp,
                    )
                else:
                    self.store.append_system_log(
                        module_id,
                        f"SYSTEM|VISION|EARLY_PICK_REQUEST_SENT|ITEM_ID={item_id}|COMMAND={command}",
                        topic="local/vision",
                        received_at=stamp,
                    )
                    if self.oee_state_manager is not None and item_id:
                        self.oee_state_manager.apply_early_pick_request(item_id, stamp)
                        self.store.refresh_oee_runtime_state(module_id, force=True)
                    if self.excel_sink is not None and item_id:
                        self.excel_sink.record_early_pick_request(item_id, stamp)
            return

        if (
            station_adapter_enabled
            and self._station_execution_topics
            and topic.startswith("mes/stations/")
        ):
            self._log_station_execution_ignored(
                topic=topic,
                error_code="STATION_EXECUTION_MQTT_TOPIC_UNKNOWN",
            )
            self._ack_station_execution_delivery(
                self._delivery_from_message(
                    client,
                    message,
                    topic,
                    None,
                    generation=station_execution_generation,
                ),
            )
            return

    def _delivery_from_message(
        self,
        client: Any,
        message: Any,
        topic: str,
        command: dict[str, Any] | None,
        *,
        generation: int | None = None,
    ) -> _StationExecutionDelivery:
        return _StationExecutionDelivery(
            topic=topic,
            command=dict(command) if command is not None else None,
            client=client,
            mid=int(getattr(message, "mid", 0) or 0),
            qos=int(getattr(message, "qos", 0) or 0),
            generation=generation,
        )

    def _ack_station_execution_delivery(self, delivery: _StationExecutionDelivery) -> bool:
        success_code = getattr(self._mqtt, "MQTT_ERR_SUCCESS", 0)
        if delivery.generation is not None:
            with self._station_execution_lifecycle_lock:
                if (
                    delivery.generation
                    != self._station_execution_active_subscription_generation
                    or (self.client is not None and delivery.client is not self.client)
                    or self._station_execution_state not in {"running", "stopping"}
                ):
                    return False
                # Keep validation and the protocol ACK in one lifecycle critical
                # section so disconnect cannot retire/reuse the session between
                # the generation check and the ACK call.
                acknowledged = delivery.acknowledge(success_code)
        else:
            acknowledged = delivery.acknowledge(success_code)
        if not acknowledged:
            self._log_station_execution_ignored(
                topic=delivery.topic,
                error_code="STATION_EXECUTION_MQTT_ACK_FAILED",
            )
        return acknowledged

    def _enqueue_station_execution_message(
        self,
        delivery: _StationExecutionDelivery,
    ) -> bool:
        deadline = (
            time.monotonic()
            + self._station_execution_enqueue_timeout_seconds
        )
        while True:
            with self._station_execution_lifecycle_lock:
                work_queue = self._station_execution_queue
                if (
                    work_queue is None
                    or not self._station_execution_accepting
                    or self._station_execution_state != "running"
                    or self._station_execution_stop_event.is_set()
                    or (
                        delivery.generation is not None
                        and (
                            delivery.generation
                            != self._station_execution_active_subscription_generation
                            or (
                                self.client is not None
                                and delivery.client is not self.client
                            )
                        )
                    )
                ):
                    return False
                try:
                    work_queue.put_nowait(delivery)
                    return True
                except queue.Full:
                    pass
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._station_execution_stop_event.wait(
                min(self._station_execution_queue_wait_seconds, remaining)
            )

    def _start_station_execution_worker(self, *, accepting: bool = True) -> bool:
        with self._station_execution_lifecycle_lock:
            existing = self._station_execution_worker
            if existing is not None:
                if existing.is_alive():
                    return False
                self._station_execution_queue = None
                self._station_execution_worker = None
            self._station_execution_stop_event = threading.Event()
            self._station_execution_queue = queue.Queue(
                maxsize=self._station_execution_queue_maxsize
            )
            self._station_execution_worker = threading.Thread(
                target=self._station_execution_worker_loop,
                name="mes-station-execution-mqtt",
                daemon=True,
            )
            self._station_execution_accepting = accepting
            self._station_execution_state = "running" if accepting else "starting"
            self._station_execution_worker.start()
            return True

    def _stop_station_execution_worker(self) -> bool:
        with self._station_execution_lifecycle_lock:
            startup_failure_cleanup = (
                self._station_execution_startup_failure_cleanup
            )
            if startup_failure_cleanup is not None:
                work_queue = None
                worker = None
            else:
                work_queue = self._station_execution_queue
                worker = self._station_execution_worker
                self._station_execution_accepting = False
                self._station_execution_stop_event.set()
                self._station_execution_pending_subscriptions.clear()
                self._station_execution_active_subscription_generation = None
                if work_queue is not None or worker is not None:
                    self._station_execution_state = "stopping"
        if startup_failure_cleanup is not None:
            return self._wait_for_station_execution_startup_failure_cleanup(
                startup_failure_cleanup
            )
        worker_stopped = self._stop_station_execution_worker_snapshot(
            work_queue,
            worker,
        )
        if not worker_stopped:
            with self._station_execution_lifecycle_lock:
                self._station_execution_state = "failed"
            return False
        with self._station_execution_lifecycle_lock:
            self._station_execution_queue = None
            self._station_execution_worker = None
            self._station_execution_state = "stopped"
        return True

    def _stop_station_execution_worker_snapshot(
        self,
        work_queue: queue.Queue[_StationExecutionDelivery | None] | None,
        worker: threading.Thread | None,
    ) -> bool:
        if work_queue is None and worker is None:
            return True
        if work_queue is None or worker is None:
            return False
        if not worker.is_alive():
            return True

        deadline = time.monotonic() + self._station_execution_stop_timeout_seconds
        sentinel_inserted = False
        while worker.is_alive() and time.monotonic() < deadline:
            try:
                work_queue.put(
                    None,
                    timeout=self._station_execution_queue_wait_seconds,
                )
                sentinel_inserted = True
                break
            except queue.Full:
                continue
        if sentinel_inserted:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))
        if worker.is_alive():
            self._log_station_execution_ignored(
                error_code="STATION_EXECUTION_MQTT_WORKER_STOP_TIMEOUT",
            )
            return False
        return True

    def _wait_for_station_execution_startup_failure_cleanup(
        self,
        cleanup: _StationExecutionStartupFailureCleanup,
    ) -> bool:
        if not cleanup.completion_event.wait(
            timeout=self._station_execution_stop_timeout_seconds
        ):
            return False
        with self._station_execution_lifecycle_lock:
            return bool(
                self._station_execution_startup_failure_cleanup is None
                and self._station_execution_worker is None
                and self.client is None
            )

    def _rollback_station_execution_startup(self) -> None:
        with self._station_execution_lifecycle_lock:
            if self._station_execution_startup_failure_cleanup is not None:
                return
            if (
                self._station_execution_state == "failed"
                and self._station_execution_startup_event.is_set()
            ):
                return
            client = self.client
            generation = self._station_execution_active_subscription_generation
            error_code = (
                self._station_execution_startup_error
                or "STATION_EXECUTION_MQTT_STARTUP_FAILED"
            )
        cleanup = self._claim_station_execution_startup_failure(
            error_code,
            client=client,
            generation=generation,
            require_current=False,
        )
        if cleanup is not None:
            self._run_station_execution_startup_failure_cleanup(cleanup)

    def _claim_station_execution_startup_failure(
        self,
        error_code: str,
        *,
        client: Any | None,
        generation: int | None,
        require_current: bool,
    ) -> _StationExecutionStartupFailureCleanup | None:
        with self._station_execution_lifecycle_lock:
            if self._station_execution_startup_failure_cleanup is not None:
                return None
            if require_current and not (
                self._station_execution_startup_generation_is_current_locked(
                    client,
                    generation,
                )
            ):
                return None
            cleanup = _StationExecutionStartupFailureCleanup(
                error_code=error_code,
                generation=generation,
                client=client,
                mqtt=self._mqtt,
                work_queue=self._station_execution_queue,
                worker=self._station_execution_worker,
                stop_event=self._station_execution_stop_event,
                startup_event=self._station_execution_startup_event,
                completion_event=threading.Event(),
            )
            self._station_execution_startup_failure_cleanup = cleanup
            self._station_execution_startup_error = error_code
            self._station_execution_accepting = False
            cleanup.stop_event.set()
            self._station_execution_pending_subscriptions.clear()
            self._station_execution_active_subscription_generation = None
            self._station_execution_state = "stopping"
            self.connected = False
            return cleanup

    def _run_station_execution_startup_failure_cleanup(
        self,
        cleanup: _StationExecutionStartupFailureCleanup,
    ) -> None:
        self.store.set_mqtt_connection(False)
        worker_stopped = self._stop_station_execution_worker_snapshot(
            cleanup.work_queue,
            cleanup.worker,
        )
        if cleanup.client is not None:
            try:
                cleanup.client.disconnect()
            except Exception:
                pass
            try:
                cleanup.client.loop_stop()
            except Exception:
                pass
        with self._station_execution_lifecycle_lock:
            if self._station_execution_startup_failure_cleanup is not cleanup:
                cleanup.completion_event.set()
                return
            if worker_stopped:
                if self._station_execution_queue is cleanup.work_queue:
                    self._station_execution_queue = None
                if self._station_execution_worker is cleanup.worker:
                    self._station_execution_worker = None
                if self.client is cleanup.client:
                    self.client = None
                if self._mqtt is cleanup.mqtt:
                    self._mqtt = None
            self._station_execution_state = "failed"
            self._station_execution_startup_failure_cleanup = None
        cleanup.startup_event.set()
        cleanup.completion_event.set()

    def _fail_station_execution_startup(
        self,
        error_code: str,
        *,
        client: Any,
        generation: int | None,
    ) -> bool:
        cleanup = self._claim_station_execution_startup_failure(
            error_code,
            client=client,
            generation=generation,
            require_current=True,
        )
        if cleanup is None:
            return False
        self._log_station_execution_ignored(error_code=error_code)
        self._run_station_execution_startup_failure_cleanup(cleanup)
        return True

    def _station_execution_worker_loop(self) -> None:
        work_queue = self._station_execution_queue
        if work_queue is None:
            return
        while True:
            item = work_queue.get()
            try:
                if item is None:
                    return
                should_ack = (
                    self._process_station_execution_command(item.command)
                    if item.command is not None
                    else False
                )
                if should_ack:
                    self._ack_station_execution_delivery(item)
            finally:
                work_queue.task_done()

    def _process_station_execution_message(self, topic: str, payload: bytes) -> bool:
        started_at = time.perf_counter()
        values: dict[str, Any] = {
            "command_source": "mqtt",
            "station_code": (self._station_execution_topics.get(topic) or {}).get("station_code"),
            "event_source": (self._station_execution_topics.get(topic) or {}).get("event_source"),
        }
        try:
            command = station_execution.map_station_execution_mqtt_message(
                topic,
                payload,
                self._station_execution_topics,
            )
            values = command
        except mesql_v2.MesqlV2Error as exc:
            self._log_station_execution_command(
                values,
                result=None,
                error_code=exc.detail,
                started_at=started_at,
            )
            return 400 <= exc.status_code < 500
        except Exception:
            self._log_station_execution_command(
                values,
                result=None,
                error_code="INTERNAL_ERROR",
                started_at=started_at,
                include_exception=True,
            )
            return False
        return self._process_station_execution_command(command)

    def _process_station_execution_command(
        self,
        command: dict[str, Any],
    ) -> bool:
        started_at = time.perf_counter()
        try:
            result = station_execution.dispatch_station_execution_command(
                self.config,
                **command,
            )
        except mesql_v2.MesqlV2Error as exc:
            self._log_station_execution_command(
                command,
                result=None,
                error_code=exc.detail,
                started_at=started_at,
            )
            return 400 <= exc.status_code < 500
        except Exception:
            self._log_station_execution_command(
                command,
                result=None,
                error_code="INTERNAL_ERROR",
                started_at=started_at,
                include_exception=True,
            )
            return False
        self._log_station_execution_command(
            command,
            result=result,
            error_code=None,
            started_at=started_at,
        )
        return True

    def _log_station_execution_command(
        self,
        values: dict[str, Any],
        *,
        result: dict[str, Any] | None,
        error_code: str | None,
        started_at: float,
        include_exception: bool = False,
    ) -> None:
        logger = logging.getLogger("mes_web.station_execution.commands")
        method = logger.exception if include_exception else logger.info
        method(
            "station_execution_command",
            extra=station_execution.command_log_extra(
                values,
                result=result,
                error_code=error_code,
                started_at=started_at,
            ),
        )

    def _log_station_execution_ignored(
        self,
        *,
        topic: str | None = None,
        error_code: str,
    ) -> None:
        mapped = self._station_execution_topics.get(topic or "") or {}
        logging.getLogger("mes_web.station_execution.commands").info(
            "station_execution_mqtt_ignored",
            extra={
                **station_execution.command_log_extra(
                    {
                        "command_source": "mqtt",
                        "station_code": mapped.get("station_code"),
                        "event_source": mapped.get("event_source"),
                    },
                    result=None,
                    error_code=error_code,
                    started_at=time.perf_counter(),
                ),
                "event": "station_execution_mqtt_ignored",
            },
        )

    def publish_command(self, payload: str) -> None:
        if self.client is None or self._mqtt is None:
            raise RuntimeError("MQTT_UNAVAILABLE")
        if not self.connected:
            raise RuntimeError("MQTT_OFFLINE")
        message_info = self.client.publish(self.config.topics["command"], payload, qos=0, retain=False)
        if message_info.rc != self._mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT_PUBLISH_FAILED")
