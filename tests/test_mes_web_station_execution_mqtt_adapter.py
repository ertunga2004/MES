from __future__ import annotations

import json
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import paho.mqtt.client as paho_mqtt

from mes_web import station_execution
from mes_web.config import AppConfig
from mes_web.db import mesql_v2
from mes_web.mqtt_runtime import MqttIngestClient, _StationExecutionDelivery


class _Store:
    def set_mqtt_connection(self, _connected: bool) -> None:
        return None

    def apply_log_line(self, *_args, **_kwargs) -> None:
        return None


class StationExecutionMqttMappingTests(unittest.TestCase):
    TOPIC = "mes/stations/STATION_X/sources/SENSOR_X/events"
    OPERATION_ID = "00000000-0000-0000-0000-000000000123"
    TOPIC_MAP = {
        TOPIC: {"station_code": "STATION_X", "event_source": "SENSOR_X"}
    }

    def _payload(self, **changes) -> bytes:
        payload = {
            "schema_version": "mes.station-execution.mqtt.v1",
            "station_code": "STATION_X",
            "source_code": "SENSOR_X",
            "external_event_id": "DEVICE-X:BOOT-7:EVENT-12",
            "work_order_operation_id": self.OPERATION_ID,
            "device_id": "DEVICE-X",
            "metadata": {"secret_probe": "MUST_NOT_LOG"},
        }
        payload.update(changes)
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def test_known_topic_maps_station_and_source(self) -> None:
        command = station_execution.map_station_execution_mqtt_message(
            self.TOPIC,
            self._payload(),
            self.TOPIC_MAP,
        )
        self.assertEqual(command["station_code"], "STATION_X")
        self.assertEqual(command["event_source"], "SENSOR_X")
        self.assertEqual(command["external_event_id"], "DEVICE-X:BOOT-7:EVENT-12")

    def test_exact_operation_identity_is_preserved(self) -> None:
        command = station_execution.map_station_execution_mqtt_message(
            self.TOPIC,
            self._payload(),
            self.TOPIC_MAP,
        )
        self.assertEqual(command["work_order_operation_id"], self.OPERATION_ID)

    def test_operation_identity_is_required_without_queue_head_fallback(self) -> None:
        for value in (None, "", 123):
            with self.subTest(value=value), self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_OPERATION_ID_REQUIRED",
            ):
                station_execution.map_station_execution_mqtt_message(
                    self.TOPIC,
                    self._payload(work_order_operation_id=value),
                    self.TOPIC_MAP,
                )

    def test_unknown_topic_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_MQTT_TOPIC_UNKNOWN",
        ):
            station_execution.map_station_execution_mqtt_message(
                "mes/stations/OTHER/sources/X/events",
                self._payload(),
                self.TOPIC_MAP,
            )

    def test_topic_body_station_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_OPERATION_STATION_MISMATCH",
        ):
            station_execution.map_station_execution_mqtt_message(
                self.TOPIC,
                self._payload(station_code="OTHER"),
                self.TOPIC_MAP,
            )

    def test_topic_body_source_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_EVENT_SOURCE_NOT_ALLOWED",
        ):
            station_execution.map_station_execution_mqtt_message(
                self.TOPIC,
                self._payload(source_code="OTHER"),
                self.TOPIC_MAP,
            )

    def test_malformed_payload_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_MQTT_PAYLOAD_INVALID",
        ):
            station_execution.map_station_execution_mqtt_message(
                self.TOPIC,
                b"{",
                self.TOPIC_MAP,
            )

    def test_duplicate_json_key_is_rejected(self) -> None:
        raw = b'{"external_event_id":"A","external_event_id":"B"}'
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_MQTT_PAYLOAD_INVALID",
        ):
            station_execution.map_station_execution_mqtt_message(
                self.TOPIC,
                raw,
                self.TOPIC_MAP,
            )

    def test_publisher_external_event_identity_is_required_without_fallback(self) -> None:
        for value in (None, "", 123):
            with self.subTest(value=value), self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_EXTERNAL_EVENT_ID_REQUIRED",
            ):
                station_execution.map_station_execution_mqtt_message(
                    self.TOPIC,
                    self._payload(external_event_id=value),
                    self.TOPIC_MAP,
                )

    def test_topic_loader_is_generic_and_rejects_duplicates(self) -> None:
        config = AppConfig(mesql_stations=("STATION_X", "STATION_Y"))
        duplicate = {
            "station_code": "STATION_X",
            "source_code": "SOURCE",
            "event_channel": "mqtt",
            "mqtt_topic": self.TOPIC,
        }
        with patch.object(
            station_execution.mesql_v2,
            "list_station_event_sources",
            side_effect=[[duplicate], [{**duplicate, "station_code": "STATION_Y"}]],
        ):
            with self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_MQTT_TOPIC_CONFLICT",
            ):
                station_execution.load_station_execution_mqtt_topics(config)


class StationExecutionMqttCallbackTests(unittest.TestCase):
    TOPIC = "mes/stations/STATION_X/sources/SENSOR_X/events"
    OPERATION_ID = "00000000-0000-0000-0000-000000000123"

    def setUp(self) -> None:
        self.config = AppConfig(
            db_enabled=True,
            db_station_execution_commands_enabled=True,
            mqtt_station_execution_adapter_enabled=True,
        )
        self.client = MqttIngestClient(self.config, _Store())
        self.client._station_execution_topics = {
            self.TOPIC: {"station_code": "STATION_X", "event_source": "SENSOR_X"}
        }
        self.client._station_execution_accepting = True
        self.client._station_execution_state = "running"
        self.client._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)
        self.transport = Mock()
        self.transport.ack.return_value = 0

    def _message(self, *, payload=None, retain=False):
        if payload is None:
            payload = json.dumps(
                {
                    "schema_version": "mes.station-execution.mqtt.v1",
                    "external_event_id": "EVENT-1",
                    "work_order_operation_id": self.OPERATION_ID,
                },
                separators=(",", ":"),
            ).encode("utf-8")
        return SimpleNamespace(
            topic=self.TOPIC,
            payload=payload,
            retain=retain,
            mid=17,
            qos=1,
        )

    def _starting_subscription(self, mid: int):
        broker = Mock()
        broker.subscribe.return_value = (0, mid)
        broker.ack.return_value = 0
        self.client.client = broker
        self.client._station_execution_state = "starting"
        self.client._on_connect(broker, None, None, 0)
        return (
            broker,
            broker.on_subscribe,
            self.client._station_execution_active_subscription_generation,
        )

    def test_on_connect_subscribes_canonical_topics_with_qos_one(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 1)
        self.client.client = broker
        self.client._on_connect(broker, None, None, 0)
        broker.subscribe.assert_any_call(self.TOPIC, qos=1)

    def test_disconnect_closes_admission_until_suback(self) -> None:
        self.client._station_execution_pending_subscriptions.add(99)
        self.client._on_disconnect(self.transport, None)
        self.assertFalse(self.client._station_execution_accepting)
        self.assertEqual(self.client._station_execution_state, "starting")
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())

    def test_pre_suback_disconnect_discards_connection_scoped_mids(self) -> None:
        self.client._station_execution_state = "starting"
        self.client._station_execution_accepting = False
        self.client._station_execution_pending_subscriptions.update({41, 42})

        self.client._on_disconnect(self.transport, None)

        self.assertFalse(self.client._station_execution_accepting)
        self.assertEqual(self.client._station_execution_state, "starting")
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())

    def test_reconnect_generation_replaces_stale_subscription_mids(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 73)
        self.client.client = broker
        self.client._station_execution_state = "starting"
        self.client._station_execution_accepting = False
        self.client._station_execution_pending_subscriptions.add(41)

        self.client._on_connect(broker, None, None, 0)

        self.assertEqual(self.client._station_execution_pending_subscriptions, {73})
        self.assertFalse(self.client._station_execution_accepting)

    def test_late_prior_generation_suback_cannot_admit_reused_mid(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 73)
        worker = Mock()
        worker.is_alive.return_value = True
        self.client._station_execution_worker = worker
        self.client._station_execution_state = "starting"
        self.client.client = broker

        self.client._on_connect(broker, None, None, 0)
        first_generation = self.client._station_execution_active_subscription_generation
        stale_callback = broker.on_subscribe
        self.client._on_disconnect(broker, None)
        self.client._on_connect(broker, None, None, 0)
        current_generation = self.client._station_execution_active_subscription_generation
        current_callback = broker.on_subscribe

        self.assertNotEqual(first_generation, current_generation)
        self.assertEqual(self.client._station_execution_pending_subscriptions, {73})
        reason = SimpleNamespace(is_failure=False, value=1)
        stale_callback(broker, None, 73, [reason])
        self.assertEqual(self.client._station_execution_pending_subscriptions, {73})
        self.assertFalse(self.client._station_execution_accepting)
        current_callback(broker, None, 73, [reason])
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())
        self.assertTrue(self.client._station_execution_accepting)
        self.assertEqual(self.client._station_execution_state, "running")

    def test_late_prior_generation_message_cannot_enter_current_queue(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 73)
        broker.ack.return_value = 0
        worker = Mock()
        worker.is_alive.return_value = True
        self.client.client = broker
        self.client._station_execution_worker = worker
        self.client._station_execution_queue = queue.Queue(maxsize=2)
        self.client._station_execution_state = "starting"
        self.client._station_execution_accepting = False

        self.client._on_connect(broker, None, None, 0)
        stale_message_callback = broker.on_message
        current_disconnect_callback = broker.on_disconnect
        first_generation = self.client._station_execution_active_subscription_generation
        current_disconnect_callback(broker, None, None, 0)
        self.client._on_connect(broker, None, None, 0)
        current_message_callback = broker.on_message
        second_generation = self.client._station_execution_active_subscription_generation
        broker.on_subscribe(
            broker,
            None,
            73,
            [SimpleNamespace(is_failure=False, value=1)],
        )

        self.assertNotEqual(first_generation, second_generation)
        stale_message_callback(broker, None, self._message())
        self.assertTrue(self.client._station_execution_queue.empty())
        current_message_callback(broker, None, self._message())
        delivery = self.client._station_execution_queue.get_nowait()
        self.assertEqual(delivery.generation, second_generation)
        self.assertIs(delivery.client, broker)

    def test_late_retired_connect_callback_is_ignored_before_subscribe(self) -> None:
        current = Mock()
        retired = Mock()
        self.client.client = current
        self.client._station_execution_state = "stopping"
        self.client._station_execution_accepting = False

        self.client._on_connect(retired, None, None, 0)

        retired.subscribe.assert_not_called()
        self.assertEqual(self.client._station_execution_state, "stopping")
        self.assertFalse(self.client._station_execution_accepting)

    def test_current_generation_requires_every_suback_before_admission(self) -> None:
        self.client._station_execution_topics = {
            self.TOPIC: {"station_code": "STATION_X", "event_source": "SENSOR_X"},
            self.TOPIC + "/SECOND": {
                "station_code": "STATION_X",
                "event_source": "SENSOR_Y",
            },
        }
        broker = Mock()
        canonical_mids = iter((41, 42))
        broker.subscribe.side_effect = lambda _topic, qos=0: (
            (0, next(canonical_mids)) if qos == 1 else (0, 900)
        )
        worker = Mock()
        worker.is_alive.return_value = True
        self.client._station_execution_worker = worker
        self.client._station_execution_state = "starting"
        self.client.client = broker

        self.client._on_connect(broker, None, None, 0)
        callback = broker.on_subscribe
        reason = SimpleNamespace(is_failure=False, value=1)
        callback(broker, None, 41, [reason])
        self.assertEqual(self.client._station_execution_state, "starting")
        self.assertFalse(self.client._station_execution_accepting)
        callback(broker, None, 42, [reason])
        self.assertEqual(self.client._station_execution_state, "running")
        self.assertTrue(self.client._station_execution_accepting)

    def test_stop_invalidates_generation_against_late_suback(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 51)
        worker = Mock()
        worker.is_alive.return_value = True
        self.client._station_execution_worker = worker
        self.client._station_execution_state = "starting"
        self.client.client = broker
        self.client._on_connect(broker, None, None, 0)
        callback = broker.on_subscribe

        self.client._station_execution_state = "stopping"
        self.client._on_disconnect(broker, None)
        callback(
            broker,
            None,
            51,
            [SimpleNamespace(is_failure=False, value=1)],
        )

        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )
        self.assertFalse(self.client._station_execution_accepting)
        self.assertEqual(self.client._station_execution_state, "stopping")

    def test_stop_after_generation_setup_prevents_any_subscription_continuation(
        self,
    ) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 61)
        self.client.client = broker
        self.client._station_execution_state = "starting"
        subscribe_boundary_entered = threading.Event()
        release_subscribe_boundary = threading.Event()
        original_subscribe_generation = (
            self.client._subscribe_station_execution_generation
        )

        def delayed_subscribe(client, generation):
            subscribe_boundary_entered.set()
            release_subscribe_boundary.wait(timeout=1.0)
            return original_subscribe_generation(client, generation)

        with (
            patch.object(
                self.client,
                "_subscribe_station_execution_generation",
                side_effect=delayed_subscribe,
            ),
            patch.object(
                self.client,
                "_rollback_station_execution_startup",
                wraps=self.client._rollback_station_execution_startup,
            ) as rollback,
        ):
            callback = threading.Thread(
                target=self.client._on_connect,
                args=(broker, None, None, 0),
            )
            callback.start()
            self.assertTrue(subscribe_boundary_entered.wait(timeout=1.0))
            self.assertTrue(self.client.stop())
            release_subscribe_boundary.set()
            callback.join(timeout=1.0)

        self.assertFalse(callback.is_alive())
        broker.subscribe.assert_not_called()
        rollback.assert_not_called()
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())
        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )
        self.assertEqual(self.client._station_execution_state, "stopped")

    def test_generation_none_cannot_subscribe_or_change_lifecycle(self) -> None:
        broker = Mock()
        self.client.client = broker
        self.client._station_execution_state = "starting"

        self.assertFalse(
            self.client._subscribe_station_execution_generation(broker, None)
        )

        broker.subscribe.assert_not_called()
        self.assertEqual(self.client._station_execution_state, "starting")
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())

    def test_rejected_suback_after_completed_stop_is_ignored(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 71)
        self.client.client = broker
        self.client._station_execution_state = "starting"
        self.client._on_connect(broker, None, None, 0)
        rejected_suback = broker.on_subscribe

        with patch.object(
            self.client,
            "_rollback_station_execution_startup",
            wraps=self.client._rollback_station_execution_startup,
        ) as rollback:
            self.assertTrue(self.client.stop())
            rejected_suback(
                broker,
                None,
                71,
                [SimpleNamespace(is_failure=True, value=135)],
            )

        rollback.assert_not_called()
        broker.disconnect.assert_called_once()
        broker.loop_stop.assert_called_once()
        self.assertEqual(self.client._station_execution_state, "stopped")
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())
        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )

    def test_stop_wins_between_rejected_suback_validation_and_failure(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 72)
        self.client.client = broker
        self.client._station_execution_state = "starting"
        self.client._on_connect(broker, None, None, 0)
        rejected_suback = broker.on_subscribe
        failure_boundary_entered = threading.Event()
        release_failure_boundary = threading.Event()
        original_failure = self.client._fail_station_execution_startup

        def delayed_failure(error_code, *, client, generation):
            failure_boundary_entered.set()
            release_failure_boundary.wait(timeout=1.0)
            return original_failure(
                error_code,
                client=client,
                generation=generation,
            )

        with (
            patch.object(
                self.client,
                "_fail_station_execution_startup",
                side_effect=delayed_failure,
            ),
            patch.object(
                self.client,
                "_rollback_station_execution_startup",
                wraps=self.client._rollback_station_execution_startup,
            ) as rollback,
        ):
            callback = threading.Thread(
                target=rejected_suback,
                args=(
                    broker,
                    None,
                    72,
                    [SimpleNamespace(is_failure=True, value=135)],
                ),
            )
            callback.start()
            self.assertTrue(failure_boundary_entered.wait(timeout=1.0))
            self.assertTrue(self.client.stop())
            release_failure_boundary.set()
            callback.join(timeout=1.0)

        self.assertFalse(callback.is_alive())
        rollback.assert_not_called()
        self.assertEqual(self.client._station_execution_state, "stopped")
        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )

    def test_current_generation_rejected_suback_still_fails_closed(self) -> None:
        broker = Mock()
        broker.subscribe.return_value = (0, 74)
        self.client.client = broker
        self.assertTrue(
            self.client._start_station_execution_worker(accepting=False)
        )
        self.client._on_connect(broker, None, None, 0)

        broker.on_subscribe(
            broker,
            None,
            74,
            [SimpleNamespace(is_failure=True, value=135)],
        )

        self.assertEqual(self.client._station_execution_state, "failed")
        self.assertEqual(
            self.client._station_execution_startup_error,
            "STATION_EXECUTION_MQTT_SUBSCRIBE_REJECTED",
        )
        self.assertIsNone(self.client.client)
        self.assertIsNone(self.client._station_execution_worker)
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())

    def test_rejected_suback_join_allows_worker_terminal_no_ack(self) -> None:
        processing = threading.Event()
        release_processing = threading.Event()
        join_started = threading.Event()
        ack_finished = threading.Event()

        def process(_command):
            processing.set()
            release_processing.wait(timeout=1.0)
            return True

        with patch.object(
            self.client,
            "_process_station_execution_command",
            side_effect=process,
        ):
            self.assertTrue(
                self.client._start_station_execution_worker(accepting=False)
            )
            broker, rejected_suback, generation = self._starting_subscription(75)
            worker = self.client._station_execution_worker
            self.assertIsNotNone(worker)
            original_join = worker.join
            original_ack = self.client._ack_station_execution_delivery

            def observed_join(timeout=None):
                join_started.set()
                return original_join(timeout=timeout)

            def observed_ack(delivery):
                result = original_ack(delivery)
                ack_finished.set()
                return result

            delivery = _StationExecutionDelivery(
                topic=self.TOPIC,
                command={"command": "terminal"},
                client=broker,
                mid=75,
                qos=1,
                generation=generation,
            )
            self.client._station_execution_queue.put_nowait(delivery)
            self.assertTrue(processing.wait(timeout=1.0))
            with (
                patch.object(worker, "join", side_effect=observed_join),
                patch.object(
                    self.client,
                    "_ack_station_execution_delivery",
                    side_effect=observed_ack,
                ),
            ):
                failure = threading.Thread(
                    target=rejected_suback,
                    args=(
                        broker,
                        None,
                        75,
                        [SimpleNamespace(is_failure=True, value=135)],
                    ),
                )
                failure.start()
                try:
                    self.assertTrue(join_started.wait(timeout=1.0))
                    release_processing.set()
                    self.assertTrue(ack_finished.wait(timeout=1.0))
                    failure.join(timeout=1.0)
                finally:
                    release_processing.set()
                    failure.join(timeout=1.0)

        self.assertFalse(failure.is_alive())
        broker.ack.assert_not_called()
        self.assertEqual(self.client._station_execution_state, "failed")
        self.assertIsNone(self.client._station_execution_worker)
        self.assertIsNone(self.client.client)
        self.assertIsNone(
            self.client._station_execution_startup_failure_cleanup
        )

    def test_failure_cleanup_join_does_not_hold_lifecycle_lock(self) -> None:
        processing = threading.Event()
        release_processing = threading.Event()
        join_started = threading.Event()
        lock_acquired = threading.Event()

        def process(_command):
            processing.set()
            release_processing.wait(timeout=1.0)
            return False

        with patch.object(
            self.client,
            "_process_station_execution_command",
            side_effect=process,
        ):
            self.assertTrue(
                self.client._start_station_execution_worker(accepting=False)
            )
            broker, rejected_suback, generation = self._starting_subscription(76)
            worker = self.client._station_execution_worker
            self.assertIsNotNone(worker)
            original_join = worker.join

            def observed_join(timeout=None):
                join_started.set()
                return original_join(timeout=timeout)

            def acquire_lifecycle_lock():
                with self.client._station_execution_lifecycle_lock:
                    lock_acquired.set()

            delivery = _StationExecutionDelivery(
                topic=self.TOPIC,
                command={"command": "terminal"},
                client=broker,
                mid=76,
                qos=1,
                generation=generation,
            )
            self.client._station_execution_queue.put_nowait(delivery)
            self.assertTrue(processing.wait(timeout=1.0))
            with patch.object(worker, "join", side_effect=observed_join):
                failure = threading.Thread(
                    target=rejected_suback,
                    args=(
                        broker,
                        None,
                        76,
                        [SimpleNamespace(is_failure=True, value=135)],
                    ),
                )
                failure.start()
                probe = threading.Thread(target=acquire_lifecycle_lock)
                try:
                    self.assertTrue(join_started.wait(timeout=1.0))
                    probe.start()
                    self.assertTrue(lock_acquired.wait(timeout=1.0))
                    release_processing.set()
                    probe.join(timeout=1.0)
                    failure.join(timeout=1.0)
                finally:
                    release_processing.set()
                    if probe.ident is not None:
                        probe.join(timeout=1.0)
                    failure.join(timeout=1.0)

        self.assertFalse(probe.is_alive())
        self.assertFalse(failure.is_alive())

    def test_duplicate_rejected_suback_has_one_failure_owner(self) -> None:
        broker, rejected_suback, _generation = self._starting_subscription(77)
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()
        cleanup_claims = []
        original_cleanup = (
            self.client._run_station_execution_startup_failure_cleanup
        )

        def delayed_cleanup(cleanup):
            cleanup_claims.append(cleanup)
            cleanup_entered.set()
            release_cleanup.wait(timeout=1.0)
            return original_cleanup(cleanup)

        reason = [SimpleNamespace(is_failure=True, value=135)]
        with patch.object(
            self.client,
            "_run_station_execution_startup_failure_cleanup",
            side_effect=delayed_cleanup,
        ):
            first = threading.Thread(
                target=rejected_suback,
                args=(broker, None, 77, reason),
            )
            second = threading.Thread(
                target=rejected_suback,
                args=(broker, None, 77, reason),
            )
            first.start()
            self.assertTrue(cleanup_entered.wait(timeout=1.0))
            second.start()
            second.join(timeout=1.0)
            release_cleanup.set()
            first.join(timeout=1.0)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(len(cleanup_claims), 1)
        broker.disconnect.assert_called_once()
        broker.loop_stop.assert_called_once()
        self.assertEqual(self.client._station_execution_state, "failed")
        self.assertIsNone(
            self.client._station_execution_startup_failure_cleanup
        )

    def test_failure_owner_wins_stop_without_second_cleanup(self) -> None:
        broker, rejected_suback, _generation = self._starting_subscription(78)
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()
        stop_waiting = threading.Event()
        snapshot_stops = []
        original_cleanup = (
            self.client._run_station_execution_startup_failure_cleanup
        )
        original_snapshot_stop = (
            self.client._stop_station_execution_worker_snapshot
        )
        original_wait = (
            self.client._wait_for_station_execution_startup_failure_cleanup
        )

        def delayed_cleanup(cleanup):
            cleanup_entered.set()
            release_cleanup.wait(timeout=1.0)
            return original_cleanup(cleanup)

        def counted_snapshot_stop(work_queue, worker):
            snapshot_stops.append((work_queue, worker))
            return original_snapshot_stop(work_queue, worker)

        def observed_wait(cleanup):
            stop_waiting.set()
            return original_wait(cleanup)

        with (
            patch.object(
                self.client,
                "_run_station_execution_startup_failure_cleanup",
                side_effect=delayed_cleanup,
            ),
            patch.object(
                self.client,
                "_stop_station_execution_worker_snapshot",
                side_effect=counted_snapshot_stop,
            ),
            patch.object(
                self.client,
                "_wait_for_station_execution_startup_failure_cleanup",
                side_effect=observed_wait,
            ),
        ):
            failure = threading.Thread(
                target=rejected_suback,
                args=(
                    broker,
                    None,
                    78,
                    [SimpleNamespace(is_failure=True, value=135)],
                ),
            )
            stop_results = []
            stopper = threading.Thread(
                target=lambda: stop_results.append(self.client.stop())
            )
            failure.start()
            self.assertTrue(cleanup_entered.wait(timeout=1.0))
            stopper.start()
            self.assertTrue(stop_waiting.wait(timeout=1.0))
            self.assertEqual(stop_results, [])
            release_cleanup.set()
            stopper.join(timeout=1.0)
            failure.join(timeout=1.0)

        self.assertFalse(stopper.is_alive())
        self.assertFalse(failure.is_alive())
        self.assertEqual(stop_results, [True])
        self.assertEqual(len(snapshot_stops), 1)
        broker.disconnect.assert_called_once()
        broker.loop_stop.assert_called_once()
        self.assertEqual(self.client._station_execution_state, "failed")

    def test_stop_reports_incomplete_owned_failure_cleanup(self) -> None:
        broker, _rejected_suback, generation = self._starting_subscription(81)
        cleanup = self.client._claim_station_execution_startup_failure(
            "STATION_EXECUTION_MQTT_SUBSCRIBE_REJECTED",
            client=broker,
            generation=generation,
            require_current=True,
        )
        self.assertIsNotNone(cleanup)

        with patch.object(
            cleanup.completion_event,
            "wait",
            return_value=False,
        ) as waited:
            self.assertFalse(self.client.stop())

        waited.assert_called_once_with(
            timeout=self.client._station_execution_stop_timeout_seconds
        )
        self.assertIs(
            self.client._station_execution_startup_failure_cleanup,
            cleanup,
        )
        broker.disconnect.assert_not_called()
        self.client._run_station_execution_startup_failure_cleanup(cleanup)
        self.assertIsNone(
            self.client._station_execution_startup_failure_cleanup
        )

    def test_failure_retirement_rejects_late_message_and_ack(self) -> None:
        broker, rejected_suback, generation = self._starting_subscription(79)
        message_callback = broker.on_message
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()
        original_cleanup = (
            self.client._run_station_execution_startup_failure_cleanup
        )

        def delayed_cleanup(cleanup):
            cleanup_entered.set()
            release_cleanup.wait(timeout=1.0)
            return original_cleanup(cleanup)

        with (
            patch.object(
                self.client,
                "_run_station_execution_startup_failure_cleanup",
                side_effect=delayed_cleanup,
            ),
            patch.object(self.client, "_on_message") as on_message,
        ):
            failure = threading.Thread(
                target=rejected_suback,
                args=(
                    broker,
                    None,
                    79,
                    [SimpleNamespace(is_failure=True, value=135)],
                ),
            )
            failure.start()
            self.assertTrue(cleanup_entered.wait(timeout=1.0))
            message_callback(broker, None, self._message())
            delivery = _StationExecutionDelivery(
                topic=self.TOPIC,
                command={"command": "late"},
                client=broker,
                mid=79,
                qos=1,
                generation=generation,
            )
            self.assertFalse(
                self.client._ack_station_execution_delivery(delivery)
            )
            release_cleanup.set()
            failure.join(timeout=1.0)

        self.assertFalse(failure.is_alive())
        on_message.assert_not_called()
        broker.ack.assert_not_called()

    def test_failure_cleanup_blocks_restart_until_finalized(self) -> None:
        broker, rejected_suback, _generation = self._starting_subscription(80)
        cleanup_entered = threading.Event()
        release_cleanup = threading.Event()
        original_cleanup = (
            self.client._run_station_execution_startup_failure_cleanup
        )

        def delayed_cleanup(cleanup):
            cleanup_entered.set()
            release_cleanup.wait(timeout=1.0)
            return original_cleanup(cleanup)

        with patch.object(
            self.client,
            "_run_station_execution_startup_failure_cleanup",
            side_effect=delayed_cleanup,
        ):
            failure = threading.Thread(
                target=rejected_suback,
                args=(
                    broker,
                    None,
                    80,
                    [SimpleNamespace(is_failure=True, value=135)],
                ),
            )
            failure.start()
            self.assertTrue(cleanup_entered.wait(timeout=1.0))
            with self.assertRaisesRegex(
                RuntimeError,
                "STATION_EXECUTION_MQTT_LIFECYCLE_BUSY",
            ):
                self.client.start()
            release_cleanup.set()
            failure.join(timeout=1.0)

        self.assertFalse(failure.is_alive())
        self.assertEqual(self.client._station_execution_state, "failed")
        self.assertIsNone(
            self.client._station_execution_startup_failure_cleanup
        )

    def test_completed_subscribe_precedes_stop_and_late_suback_is_ignored(
        self,
    ) -> None:
        broker = Mock()
        subscribe_entered = threading.Event()
        release_subscribe = threading.Event()
        stop_called = threading.Event()
        next_mid = 0

        def subscribe(_topic, qos=0):
            nonlocal next_mid
            next_mid += 1
            if next_mid == 1:
                subscribe_entered.set()
                release_subscribe.wait(timeout=1.0)
            return (0, next_mid)

        broker.subscribe.side_effect = subscribe
        self.client.client = broker
        self.client._station_execution_state = "starting"
        original_stop_worker = self.client._stop_station_execution_worker

        def observed_stop_worker():
            stop_called.set()
            return original_stop_worker()

        with patch.object(
            self.client,
            "_stop_station_execution_worker",
            side_effect=observed_stop_worker,
        ):
            connect_thread = threading.Thread(
                target=self.client._on_connect,
                args=(broker, None, None, 0),
            )
            stop_results: list[bool] = []
            stop_thread = threading.Thread(
                target=lambda: stop_results.append(self.client.stop())
            )
            connect_thread.start()
            self.assertTrue(subscribe_entered.wait(timeout=1.0))
            stop_thread.start()
            self.assertTrue(stop_called.wait(timeout=1.0))
            release_subscribe.set()
            connect_thread.join(timeout=1.0)
            stop_thread.join(timeout=1.0)

        self.assertFalse(connect_thread.is_alive())
        self.assertFalse(stop_thread.is_alive())
        self.assertEqual(stop_results, [True])
        broker.subscribe.assert_any_call(self.TOPIC, qos=1)
        late_suback = broker.on_subscribe
        late_suback(
            broker,
            None,
            next_mid,
            [SimpleNamespace(is_failure=False, value=1)],
        )
        self.assertEqual(self.client._station_execution_state, "stopped")
        self.assertEqual(self.client._station_execution_pending_subscriptions, set())
        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )

    def test_repeated_connect_stop_race_leaks_no_generation_or_pending_mid(
        self,
    ) -> None:
        rollback_calls = 0
        original_rollback = self.client._rollback_station_execution_startup

        def counted_rollback():
            nonlocal rollback_calls
            rollback_calls += 1
            return original_rollback()

        with patch.object(
            self.client,
            "_rollback_station_execution_startup",
            side_effect=counted_rollback,
        ):
            for attempt in range(3):
                broker = Mock(name=f"broker-{attempt}")
                broker.subscribe.return_value = (0, 80 + attempt)
                self.client.client = broker
                self.client._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)
                self.client._station_execution_state = "starting"
                self.client._station_execution_stop_event = threading.Event()
                boundary_entered = threading.Event()
                release_boundary = threading.Event()
                original_subscribe_generation = (
                    self.client._subscribe_station_execution_generation
                )

                def delayed_subscribe(client, generation):
                    boundary_entered.set()
                    release_boundary.wait(timeout=1.0)
                    return original_subscribe_generation(client, generation)

                with patch.object(
                    self.client,
                    "_subscribe_station_execution_generation",
                    side_effect=delayed_subscribe,
                ):
                    callback = threading.Thread(
                        target=self.client._on_connect,
                        args=(broker, None, None, 0),
                    )
                    callback.start()
                    self.assertTrue(boundary_entered.wait(timeout=1.0))
                    self.assertTrue(self.client.stop())
                    release_boundary.set()
                    callback.join(timeout=1.0)

                self.assertFalse(callback.is_alive())
                broker.subscribe.assert_not_called()
                self.assertEqual(
                    self.client._station_execution_pending_subscriptions,
                    set(),
                )
                self.assertIsNone(
                    self.client._station_execution_active_subscription_generation
                )
                self.assertIsNone(self.client._station_execution_worker)
                self.assertIsNone(self.client.client)
                self.assertEqual(self.client._station_execution_state, "stopped")

        self.assertEqual(rollback_calls, 0)

    def test_late_connect_after_completed_stop_has_no_side_effect(self) -> None:
        broker = Mock()
        self.client.client = broker
        self.client._station_execution_state = "starting"
        self.assertTrue(self.client.stop())
        broker.reset_mock()

        self.client._on_connect(broker, None, None, 0)

        broker.subscribe.assert_not_called()
        broker.disconnect.assert_not_called()
        broker.loop_stop.assert_not_called()
        self.assertEqual(self.client._station_execution_state, "stopped")
        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )

    def test_callback_enqueues_without_dispatching_on_network_thread(self) -> None:
        work_queue: queue.Queue = queue.Queue(maxsize=1)
        self.client._station_execution_queue = work_queue
        with patch.object(
            self.client,
            "_process_station_execution_message",
        ) as processor:
            self.client._on_message(self.transport, None, self._message())
        processor.assert_not_called()
        delivery = work_queue.get_nowait()
        self.assertEqual(delivery.topic, self.TOPIC)
        self.assertEqual(
            delivery.command["work_order_operation_id"],
            self.OPERATION_ID,
        )
        self.assertFalse(hasattr(delivery, "payload"))
        self.transport.ack.assert_not_called()

    def test_retained_message_is_ignored(self) -> None:
        self.client._station_execution_queue = queue.Queue(maxsize=1)
        with patch.object(self.client, "_log_station_execution_ignored") as ignored:
            self.client._on_message(self.transport, None, self._message(retain=True))
        ignored.assert_called_once_with(
            topic=self.TOPIC,
            error_code="STATION_EXECUTION_MQTT_RETAINED_NOT_ALLOWED",
        )
        self.assertTrue(self.client._station_execution_queue.empty())
        self.transport.ack.assert_called_once_with(17, 1)

    def test_unknown_canonical_topic_is_ignored_without_crash(self) -> None:
        message = SimpleNamespace(
            topic="mes/stations/UNKNOWN/sources/X/events",
            payload=b"secret raw payload",
            retain=False,
        )
        with patch.object(self.client, "_log_station_execution_ignored") as ignored:
            self.client._on_message(None, None, message)
        ignored.assert_called_once_with(
            topic=message.topic,
            error_code="STATION_EXECUTION_MQTT_TOPIC_UNKNOWN",
        )

    def test_adapter_disabled_canonical_legacy_topic_uses_legacy_once(self) -> None:
        self.config.mqtt_station_execution_adapter_enabled = False
        self.config.topic_root = "mes/stations/STATION_X"
        legacy_topic = self.config.topics["logs"]
        self.client._station_execution_topics = {
            legacy_topic: {"station_code": "STATION_X", "event_source": "SENSOR_X"}
        }
        with (
            patch.object(self.client.store, "apply_log_line") as legacy,
            patch.object(self.client, "_enqueue_station_execution_message") as enqueue,
        ):
            self.client._on_message(
                self.transport,
                None,
                SimpleNamespace(topic=legacy_topic, payload=b"legacy", retain=False),
            )
        legacy.assert_called_once()
        enqueue.assert_not_called()

    def test_full_queue_waits_until_capacity_and_does_not_drop(self) -> None:
        work_queue: queue.Queue = queue.Queue(maxsize=1)
        work_queue.put(object())
        self.client._station_execution_queue = work_queue
        callback = threading.Thread(
            target=self.client._on_message,
            args=(self.transport, None, self._message()),
        )
        callback.start()
        time.sleep(0.05)
        self.assertTrue(callback.is_alive())
        work_queue.get_nowait()
        callback.join(timeout=1.0)
        self.assertFalse(callback.is_alive())
        self.assertEqual(work_queue.get_nowait().topic, self.TOPIC)

    def test_shutdown_interrupts_blocked_enqueue_without_drop_log(self) -> None:
        work_queue: queue.Queue = queue.Queue(maxsize=1)
        work_queue.put(object())
        self.client._station_execution_queue = work_queue
        with patch.object(self.client, "_log_station_execution_ignored") as ignored:
            callback = threading.Thread(
                target=self.client._on_message,
                args=(self.transport, None, self._message()),
            )
            callback.start()
            time.sleep(0.05)
            self.client._station_execution_accepting = False
            self.client._station_execution_stop_event.set()
            callback.join(timeout=1.0)
        self.assertFalse(callback.is_alive())
        ignored.assert_called_once_with(
            topic=self.TOPIC,
            error_code="STATION_EXECUTION_MQTT_ADAPTER_STOPPING",
        )
        self.assertEqual(work_queue.qsize(), 1)

    def test_queue_deadline_returns_without_ack(self) -> None:
        self.client._station_execution_enqueue_timeout_seconds = 0.03
        work_queue: queue.Queue = queue.Queue(maxsize=1)
        work_queue.put(object())
        self.client._station_execution_queue = work_queue
        started = time.monotonic()
        with patch.object(self.client, "_log_station_execution_ignored") as ignored:
            self.client._on_message(self.transport, None, self._message())
        self.assertLess(time.monotonic() - started, 0.25)
        self.transport.ack.assert_not_called()
        ignored.assert_called_once_with(
            topic=self.TOPIC,
            error_code="STATION_EXECUTION_MQTT_QUEUE_TIMEOUT",
        )

    def test_shutdown_rejection_does_not_ack(self) -> None:
        self.client._station_execution_accepting = False
        self.client._station_execution_stop_event.set()
        self.client._on_message(self.transport, None, self._message())
        self.transport.ack.assert_not_called()

    def test_processor_calls_single_application_service_and_logs_once(self) -> None:
        command = {
            "command_source": "mqtt",
            "station_code": "STATION_X",
            "event_source": "SENSOR_X",
            "external_event_id": "EVENT-1",
            "work_order_operation_id": None,
            "step_code": None,
            "action": None,
            "actor": None,
            "metadata": {"secret_probe": "MUST_NOT_LOG"},
        }
        result = {
            "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
            "step_code": "STEP_X",
            "action": "finish",
            "action_applied": True,
            "event_inserted": True,
        }
        with (
            patch.object(
                station_execution,
                "map_station_execution_mqtt_message",
                return_value=command,
            ),
            patch.object(
                station_execution,
                "dispatch_station_execution_command",
                return_value=result,
            ) as dispatcher,
            patch("mes_web.mqtt_runtime.logging.getLogger") as get_logger,
        ):
            self.client._process_station_execution_message(self.TOPIC, b"secret")
        dispatcher.assert_called_once_with(self.config, **command)
        get_logger.return_value.info.assert_called_once()
        extra = get_logger.return_value.info.call_args.kwargs["extra"]
        self.assertNotIn("MUST_NOT_LOG", repr(extra))
        self.assertNotIn("secret", repr(extra))

    def test_duplicate_delivery_result_is_logged_as_zero_write(self) -> None:
        command = {
            "command_source": "mqtt",
            "station_code": "STATION_X",
            "event_source": "SENSOR_X",
            "external_event_id": "EVENT-1",
        }
        with (
            patch.object(
                station_execution,
                "map_station_execution_mqtt_message",
                return_value=command,
            ),
            patch.object(
                station_execution,
                "dispatch_station_execution_command",
                return_value={"action_applied": False, "event_inserted": False},
            ),
            patch("mes_web.mqtt_runtime.logging.getLogger") as get_logger,
        ):
            self.client._process_station_execution_message(self.TOPIC, b"{}")
        extra = get_logger.return_value.info.call_args.kwargs["extra"]
        self.assertFalse(extra["action_applied"])
        self.assertFalse(extra["event_inserted"])

    def test_processor_contains_domain_exception(self) -> None:
        with (
            patch.object(
                station_execution,
                "map_station_execution_mqtt_message",
                side_effect=mesql_v2.MesqlV2Error(
                    "STATION_EXECUTION_MQTT_PAYLOAD_INVALID",
                    status_code=400,
                ),
            ),
            patch("mes_web.mqtt_runtime.logging.getLogger") as get_logger,
        ):
            should_ack = self.client._process_station_execution_message(self.TOPIC, b"secret")
        self.assertTrue(should_ack)
        get_logger.return_value.info.assert_called_once()
        extra = get_logger.return_value.info.call_args.kwargs["extra"]
        self.assertEqual(extra["error_code"], "STATION_EXECUTION_MQTT_PAYLOAD_INVALID")
        self.assertNotIn("secret", repr(extra))

    def test_transient_domain_and_internal_failures_are_not_ackable(self) -> None:
        with patch.object(
            station_execution,
            "map_station_execution_mqtt_message",
            side_effect=mesql_v2.MesqlV2Error("DATABASE_UNAVAILABLE", status_code=503),
        ):
            self.assertFalse(
                self.client._process_station_execution_message(self.TOPIC, b"{}")
            )

    def test_apply_replay_and_deterministic_reject_are_ackable(self) -> None:
        command = {
            "command_source": "mqtt",
            "station_code": "STATION_X",
            "event_source": "SENSOR_X",
            "external_event_id": "EVENT-1",
            "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
        }
        outcomes = (
            {"action_applied": True, "event_inserted": True},
            {"action_applied": False, "event_inserted": False},
            mesql_v2.MesqlV2Error("STATION_EXECUTION_ACTION_NOT_ALLOWED", status_code=409),
        )
        for outcome in outcomes:
            with (
                self.subTest(outcome=type(outcome).__name__),
                patch.object(
                    station_execution,
                    "map_station_execution_mqtt_message",
                    return_value=command,
                ),
                patch.object(
                    station_execution,
                    "dispatch_station_execution_command",
                    return_value=outcome if isinstance(outcome, dict) else None,
                    side_effect=outcome if isinstance(outcome, BaseException) else None,
                ),
            ):
                self.assertTrue(
                    self.client._process_station_execution_message(self.TOPIC, b"{}")
                )

    def test_duplicate_redelivery_replays_then_acks_each_delivery_once(self) -> None:
        command = {
            "command_source": "mqtt",
            "station_code": "STATION_X",
            "event_source": "SENSOR_X",
            "external_event_id": "EVENT-1",
        }
        with (
            patch.object(
                station_execution,
                "map_station_execution_mqtt_message",
                return_value=command,
            ),
            patch.object(
                station_execution,
                "dispatch_station_execution_command",
                side_effect=[
                    {"action_applied": True, "event_inserted": True},
                    {"action_applied": False, "event_inserted": False},
                ],
            ),
        ):
            for mid in (51, 52):
                delivery = _StationExecutionDelivery(
                    topic=self.TOPIC,
                    command=command,
                    client=self.transport,
                    mid=mid,
                    qos=1,
                )
                if self.client._process_station_execution_command(delivery.command):
                    self.client._ack_station_execution_delivery(delivery)
        self.assertEqual(
            self.transport.ack.call_args_list,
            [call(51, 1), call(52, 1)],
        )
        with patch.object(
            station_execution,
            "map_station_execution_mqtt_message",
            side_effect=RuntimeError("transient"),
        ), patch("mes_web.mqtt_runtime.logging.getLogger"):
            self.assertFalse(
                self.client._process_station_execution_message(self.TOPIC, b"{}")
            )

    def test_ack_handle_is_exactly_once(self) -> None:
        delivery = self.client._delivery_from_message(
            self.transport,
            self._message(),
            self.TOPIC,
            None,
        )
        self.assertTrue(self.client._ack_station_execution_delivery(delivery))
        self.assertTrue(self.client._ack_station_execution_delivery(delivery))
        self.transport.ack.assert_called_once_with(17, 1)

    def test_retired_generation_delivery_is_never_acked_after_reconnect(self) -> None:
        self.client.client = self.transport
        self.client._station_execution_active_subscription_generation = 11
        delivery = self.client._delivery_from_message(
            self.transport,
            self._message(),
            self.TOPIC,
            None,
            generation=11,
        )
        self.client._station_execution_active_subscription_generation = 12

        self.assertFalse(self.client._ack_station_execution_delivery(delivery))
        self.transport.ack.assert_not_called()

    def test_current_generation_terminal_delivery_acks_once(self) -> None:
        self.client.client = self.transport
        self.client._station_execution_active_subscription_generation = 12
        delivery = self.client._delivery_from_message(
            self.transport,
            self._message(),
            self.TOPIC,
            None,
            generation=12,
        )

        self.assertTrue(self.client._ack_station_execution_delivery(delivery))
        self.assertTrue(self.client._ack_station_execution_delivery(delivery))
        self.transport.ack.assert_called_once_with(17, 1)

    def test_disconnect_cannot_retire_generation_between_ack_check_and_ack(self) -> None:
        self.client.client = self.transport
        self.client._station_execution_active_subscription_generation = 12
        delivery = self.client._delivery_from_message(
            self.transport,
            self._message(),
            self.TOPIC,
            None,
            generation=12,
        )
        ack_entered = threading.Event()
        release_ack = threading.Event()
        disconnect_started = threading.Event()
        ack_result: list[bool] = []

        def acknowledge(_mid, _qos):
            ack_entered.set()
            release_ack.wait(timeout=1.0)
            return 0

        self.transport.ack.side_effect = acknowledge
        ack_thread = threading.Thread(
            target=lambda: ack_result.append(
                self.client._ack_station_execution_delivery(delivery)
            )
        )
        def disconnect() -> None:
            disconnect_started.set()
            self.client._on_disconnect(
                self.transport,
                None,
                None,
                0,
                station_execution_generation=12,
            )

        disconnect_thread = threading.Thread(target=disconnect)

        ack_thread.start()
        self.assertTrue(ack_entered.wait(timeout=1.0))
        disconnect_thread.start()
        self.assertTrue(disconnect_started.wait(timeout=1.0))
        self.assertEqual(
            self.client._station_execution_active_subscription_generation,
            12,
        )
        release_ack.set()
        ack_thread.join(timeout=1.0)
        disconnect_thread.join(timeout=1.0)

        self.assertEqual(ack_result, [True])
        self.assertIsNone(
            self.client._station_execution_active_subscription_generation
        )
        self.transport.ack.assert_called_once_with(17, 1)


class StationExecutionMqttWorkerLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MqttIngestClient(
            AppConfig(
                db_enabled=True,
                db_station_execution_commands_enabled=True,
                mqtt_station_execution_adapter_enabled=True,
            ),
            _Store(),
        )
        self.client._station_execution_queue_wait_seconds = 0.01
        self.client._station_execution_stop_timeout_seconds = 0.1
        self.client._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)
        self.transport = Mock()
        self.transport.ack.return_value = 0

    def _delivery(self, topic="topic/1", payload=b"one", *, mid=1):
        return _StationExecutionDelivery(
            topic=topic,
            command={"payload": payload},
            client=self.transport,
            mid=mid,
            qos=1,
        )

    def tearDown(self) -> None:
        worker = self.client._station_execution_worker
        if worker is not None and worker.is_alive():
            work_queue = self.client._station_execution_queue
            if work_queue is not None:
                try:
                    work_queue.put_nowait(None)
                except queue.Full:
                    pass
            worker.join(timeout=1.0)

    def test_graceful_stop_drains_messages_before_clearing_references(self) -> None:
        processed = []
        with patch.object(
            self.client,
            "_process_station_execution_command",
            side_effect=lambda command: processed.append(command["payload"]),
        ):
            self.assertTrue(self.client._start_station_execution_worker())
            work_queue = self.client._station_execution_queue
            self.assertIsNotNone(work_queue)
            work_queue.put(self._delivery("topic/1", b"one", mid=1))
            work_queue.put(self._delivery("topic/2", b"two", mid=2))
            self.assertTrue(self.client._stop_station_execution_worker())
        self.assertEqual(processed, [b"one", b"two"])
        self.assertIsNone(self.client._station_execution_queue)
        self.assertIsNone(self.client._station_execution_worker)
        self.assertFalse(self.client._station_execution_accepting)

    def test_full_queue_backpressure_processes_message_after_capacity_opens(self) -> None:
        topic = "mes/stations/STATION_X/sources/SENSOR_X/events"
        self.client._station_execution_topics = {
            topic: {"station_code": "STATION_X", "event_source": "SENSOR_X"}
        }
        self.client._station_execution_queue_maxsize = 1
        first_started = threading.Event()
        release_first = threading.Event()
        processed = []

        def process(command):
            payload = command["payload"]
            processed.append(payload)
            if payload == b"one":
                first_started.set()
                release_first.wait(timeout=1.0)

        with patch.object(
            self.client,
            "_process_station_execution_command",
            side_effect=process,
        ):
            self.assertTrue(self.client._start_station_execution_worker())
            self.assertTrue(self.client._enqueue_station_execution_message(
                self._delivery(topic, b"one", mid=1)
            ))
            self.assertTrue(first_started.wait(timeout=1.0))
            self.assertTrue(self.client._enqueue_station_execution_message(
                self._delivery(topic, b"two", mid=2)
            ))
            blocked = threading.Thread(
                target=self.client._enqueue_station_execution_message,
                args=(self._delivery(topic, b"three", mid=3),),
            )
            blocked.start()
            time.sleep(0.05)
            self.assertTrue(blocked.is_alive())
            release_first.set()
            blocked.join(timeout=1.0)
            self.assertFalse(blocked.is_alive())
            work_queue = self.client._station_execution_queue
            self.assertIsNotNone(work_queue)
            work_queue.join()
            self.assertTrue(self.client._stop_station_execution_worker())
        self.assertEqual(processed, [b"one", b"two", b"three"])

    def test_join_timeout_preserves_references_and_blocks_restart(self) -> None:
        work_queue: queue.Queue = queue.Queue(maxsize=1)
        work_queue.put(self._delivery("occupied", b"payload"))
        worker = Mock()
        worker.is_alive.return_value = True
        self.client._station_execution_queue = work_queue
        self.client._station_execution_worker = worker
        self.client._station_execution_accepting = True
        with patch.object(self.client, "_log_station_execution_ignored") as ignored:
            self.assertFalse(self.client._stop_station_execution_worker())
        self.assertIs(self.client._station_execution_queue, work_queue)
        self.assertIs(self.client._station_execution_worker, worker)
        self.assertFalse(self.client._start_station_execution_worker())
        ignored.assert_called_once_with(
            error_code="STATION_EXECUTION_MQTT_WORKER_STOP_TIMEOUT",
        )
        self.assertEqual(self.client._station_execution_state, "failed")

    def test_worker_terminal_result_precedes_ack(self) -> None:
        processing = threading.Event()
        release = threading.Event()

        def process(_command):
            processing.set()
            release.wait(timeout=1.0)
            return True

        with patch.object(
            self.client,
            "_process_station_execution_command",
            side_effect=process,
        ):
            self.assertTrue(self.client._start_station_execution_worker())
            delivery = self._delivery(mid=41)
            self.assertTrue(self.client._enqueue_station_execution_message(delivery))
            self.assertTrue(processing.wait(timeout=1.0))
            self.transport.ack.assert_not_called()
            release.set()
            self.client._station_execution_queue.join()
            self.transport.ack.assert_called_once_with(41, 1)
            self.assertTrue(self.client._stop_station_execution_worker())

    def test_public_stop_timeout_preserves_client_and_allows_later_cleanup(self) -> None:
        work_queue: queue.Queue = queue.Queue(maxsize=1)
        work_queue.put(self._delivery())
        worker = Mock()
        worker.is_alive.return_value = True
        mqtt_client = Mock()
        self.client.client = mqtt_client
        self.client._station_execution_queue = work_queue
        self.client._station_execution_worker = worker
        self.client._station_execution_accepting = True
        self.assertFalse(self.client.stop())
        self.assertIs(self.client.client, mqtt_client)
        mqtt_client.disconnect.assert_not_called()
        with patch.object(
            self.client,
            "_start_serialized",
            wraps=self.client._start_serialized,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "STATION_EXECUTION_MQTT_WORKER_STILL_RUNNING",
            ):
                self.client.start()
        worker.is_alive.return_value = False
        with self.assertRaisesRegex(
            RuntimeError,
            "STATION_EXECUTION_MQTT_CLIENT_CLEANUP_REQUIRED",
        ):
            self.client.start()
        self.assertTrue(self.client.stop())
        mqtt_client.disconnect.assert_called_once()
        self.assertEqual(self.client._station_execution_state, "stopped")


class StationExecutionMqttStartupTests(unittest.TestCase):
    TOPIC = "mes/stations/STATION_X/sources/SENSOR_X/events"

    def _module(self, *, failure=None):
        created = []

        class FakeClient:
            def __init__(self, *_args, **kwargs):
                if failure == "creation":
                    raise RuntimeError("creation")
                self.kwargs = kwargs
                self.manual_ack_values = []
                self._next_mid = 0
                self._canonical_mids = []
                created.append(self)

            def manual_ack_set(self, value):
                self.manual_ack_values.append(value)

            def ack(self, _mid, _qos):
                return 0

            def enable_logger(self):
                if failure == "configuration":
                    raise RuntimeError("configuration")

            def connect_async(self, *_args):
                return 7 if failure == "connect" else 0

            def loop_start(self):
                if failure == "loop_start":
                    return 7

                def connect_and_subscribe():
                    self.on_connect(self, None, None, 0)
                    for mid in self._canonical_mids:
                        reason = (
                            SimpleNamespace(is_failure=True, value=135)
                            if failure == "suback"
                            else SimpleNamespace(is_failure=False, value=1)
                        )
                        self.on_subscribe(self, None, mid, [reason])

                threading.Thread(target=connect_and_subscribe).start()
                return 0

            def subscribe(self, _topic, qos=0):
                if failure == "subscribe_exception" and qos == 1:
                    raise RuntimeError("subscribe")
                self._next_mid += 1
                if failure == "subscribe" and qos == 1:
                    return (7, self._next_mid)
                if qos == 1:
                    self._canonical_mids.append(self._next_mid)
                return (0, self._next_mid)

            def disconnect(self):
                return 0

            def loop_stop(self):
                return 0

        return FakeClient, created

    def _runtime(self):
        return MqttIngestClient(
            AppConfig(
                db_enabled=True,
                db_station_execution_commands_enabled=True,
                mqtt_station_execution_adapter_enabled=True,
            ),
            _Store(),
        )

    def test_actual_runtime_enables_manual_ack_before_admission(self) -> None:
        fake_client, created = self._module()
        runtime = self._runtime()
        with (
            patch.object(paho_mqtt, "Client", fake_client),
            patch.object(
                station_execution,
                "load_station_execution_mqtt_topics",
                return_value={self.TOPIC: {"station_code": "STATION_X"}},
            ),
        ):
            self.assertTrue(runtime.start())
        self.assertEqual(created[0].kwargs["manual_ack"], True)
        self.assertEqual(created[0].kwargs["clean_session"], False)
        self.assertEqual(
            created[0].kwargs["client_id"],
            "mes-web-station-execution",
        )
        self.assertEqual(created[0].manual_ack_values, [True])
        self.assertEqual(runtime._station_execution_state, "running")
        self.assertTrue(runtime.stop())

    def test_legacy_start_remains_idempotent_without_duplicate_client(self) -> None:
        fake_client, created = self._module()
        runtime = MqttIngestClient(AppConfig(), _Store())
        with patch.object(paho_mqtt, "Client", fake_client):
            self.assertTrue(runtime.start())
            self.assertTrue(runtime.start())
        self.assertEqual(len(created), 1)
        self.assertTrue(runtime.stop())

    def test_startup_failures_rollback_worker_without_orphan(self) -> None:
        for failure in ("creation", "configuration", "connect", "loop_start"):
            with self.subTest(failure=failure):
                fake_client, _ = self._module(failure=failure)
                runtime = self._runtime()
                with (
                    patch.object(paho_mqtt, "Client", fake_client),
                    patch.object(
                        station_execution,
                        "load_station_execution_mqtt_topics",
                        return_value={self.TOPIC: {"station_code": "STATION_X"}},
                    ),
                ):
                    with self.assertRaises(RuntimeError):
                        runtime.start()
                self.assertEqual(runtime._station_execution_state, "failed")
                self.assertIsNone(runtime._station_execution_worker)
                self.assertIsNone(runtime._station_execution_queue)

    def test_subscription_failures_roll_back_worker(self) -> None:
        for failure in ("subscribe", "subscribe_exception", "suback"):
            with self.subTest(failure=failure):
                fake_client, _ = self._module(failure=failure)
                runtime = self._runtime()
                with (
                    patch.object(paho_mqtt, "Client", fake_client),
                    patch.object(
                        station_execution,
                        "load_station_execution_mqtt_topics",
                        return_value={self.TOPIC: {"station_code": "STATION_X"}},
                    ),
                ):
                    with self.assertRaises(RuntimeError):
                        runtime.start()
                self.assertEqual(runtime._station_execution_state, "failed")
                self.assertIsNone(runtime._station_execution_worker)

    def test_rejected_suback_cleanup_allows_successful_restart(self) -> None:
        runtime = self._runtime()
        rejected_client, _ = self._module(failure="suback")
        successful_client, created = self._module()
        topics = {self.TOPIC: {"station_code": "STATION_X"}}

        with (
            patch.object(paho_mqtt, "Client", rejected_client),
            patch.object(
                station_execution,
                "load_station_execution_mqtt_topics",
                return_value=topics,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "STATION_EXECUTION_MQTT_SUBSCRIBE_REJECTED",
            ):
                runtime.start()

        self.assertEqual(runtime._station_execution_state, "failed")
        self.assertIsNone(runtime._station_execution_worker)
        self.assertIsNone(runtime.client)
        self.assertIsNone(
            runtime._station_execution_startup_failure_cleanup
        )

        with (
            patch.object(paho_mqtt, "Client", successful_client),
            patch.object(
                station_execution,
                "load_station_execution_mqtt_topics",
                return_value=topics,
            ),
        ):
            self.assertTrue(runtime.start())

        self.assertEqual(len(created), 1)
        self.assertEqual(runtime._station_execution_state, "running")
        self.assertEqual(runtime._station_execution_pending_subscriptions, set())
        self.assertTrue(runtime.stop())
        self.assertIsNone(runtime._station_execution_worker)
        self.assertIsNone(runtime.client)
        self.assertIsNone(
            runtime._station_execution_startup_failure_cleanup
        )

    def test_startup_rejects_legacy_topic_overlap_before_worker_creation(self) -> None:
        runtime = self._runtime()
        overlapping_topic = runtime.config.topics["status"]
        with patch.object(
            station_execution,
            "load_station_execution_mqtt_topics",
            return_value={
                overlapping_topic: {
                    "station_code": "STATION_X",
                    "event_source": "SENSOR_X",
                }
            },
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "STATION_EXECUTION_MQTT_TOPIC_CONFLICT",
            ):
                runtime.start()
        self.assertIsNone(runtime._station_execution_worker)
        self.assertIsNone(runtime.client)

    def test_startup_timeout_rolls_back_worker_and_client(self) -> None:
        fake_client, created = self._module()
        runtime = self._runtime()
        runtime._station_execution_startup_timeout_seconds = 0.02

        def no_callbacks(_client):
            return 0

        fake_client.loop_start = no_callbacks
        with (
            patch.object(paho_mqtt, "Client", fake_client),
            patch.object(
                station_execution,
                "load_station_execution_mqtt_topics",
                return_value={self.TOPIC: {"station_code": "STATION_X"}},
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "STATION_EXECUTION_MQTT_STARTUP_TIMEOUT",
            ):
                runtime.start()
        self.assertEqual(runtime._station_execution_state, "failed")
        self.assertIsNone(runtime._station_execution_worker)
        self.assertIsNone(runtime.client)
        self.assertEqual(len(created), 1)

    def test_constructor_rejects_invalid_direct_enqueue_timeout(self) -> None:
        for value in (0.0, -1.0, float("inf"), float("nan"), 60.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MqttIngestClient(
                    AppConfig(
                        mqtt_station_execution_enqueue_timeout_seconds=value
                    ),
                    _Store(),
                )


if __name__ == "__main__":
    unittest.main()
