from __future__ import annotations

import json
import inspect
import os
import threading
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import mes_web.__main__ as main_module
from mes_web import station_execution
from mes_web.config import AppConfig
from mes_web.db import mesql_v2


class StationExecutionCommandApiTests(unittest.TestCase):
    PATH = "/api/v2/stations/assembly_01/execution-actions"
    OPERATION_ID = "00000000-0000-0000-0000-000000000011"
    BODY = {
        "work_order_operation_id": OPERATION_ID,
        "step_code": "process_end_observation",
        "action": "start",
        "actor": "LOCAL-KIOSK-OPERATOR",
        "external_event_id": "KIOSK-COMMAND-001",
        "metadata": {"secret_probe": "MUST_NOT_LOG"},
    }

    def setUp(self) -> None:
        self.config = AppConfig(
            db_enabled=True,
            db_station_execution_commands_enabled=True,
            kiosk_dynamic_actions_enabled=True,
        )
        self.app = FastAPI()
        main_module.register_station_execution_command_routes(self.app, self.config)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def _result(self, *, applied: bool = True) -> dict:
        return {
            "action_applied": applied,
            "event_inserted": applied,
            "implicit_started": False,
            "implicit_finished": False,
            "work_order_operation_id": self.OPERATION_ID,
            "station_code": "ASSEMBLY_01",
            "step_code": "PROCESS_END_OBSERVATION",
            "action": "start",
            "execution_state": {"execution_status": "active"},
            "step": {"status": "active"},
            "completion_bridge": None,
            "station_context": {"station_entry_state": "entered"},
        }

    def _post(self, body=None, *, result=None, side_effect=None):
        with (
            patch.object(
                main_module.station_execution,
                "dispatch_station_execution_command",
                return_value=result or self._result(),
                side_effect=side_effect,
            ) as helper,
            patch.object(main_module, "station_execution_logger") as logger,
        ):
            response = self.client.post(
                self.PATH,
                content=(
                    json.dumps(self.BODY if body is None else body, separators=(",", ":"))
                    if not isinstance(body, bytes)
                    else body
                ),
                headers={"content-type": "application/json"},
            )
        return response, helper, logger

    def test_routes_register_once(self) -> None:
        routes = {
            (route.path, tuple(sorted(route.methods or [])))
            for route in self.app.routes
            if "execution-" in route.path
        }
        self.assertIn(
            ("/api/v2/stations/{station_code}/execution-context", ("GET",)),
            routes,
        )
        self.assertIn(
            ("/api/v2/stations/{station_code}/execution-actions", ("POST",)),
            routes,
        )

    def test_context_disabled(self) -> None:
        self.config.db_station_execution_commands_enabled = False
        response = self.client.get("/api/v2/stations/ASSEMBLY_01/execution-context")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_COMMANDS_DISABLED"})

    def test_empty_context_is_success(self) -> None:
        empty = {
            "station": {"station_code": "ASSEMBLY_01"},
            "location_context": {},
            "active_operation": None,
            "next_queued_operation": None,
            "execution_state": None,
            "steps": [],
            "current_step": None,
            "allowed_manual_actions": {"can_start": False, "can_finish": False},
            "automatic_event_sources": [],
            "entered_at": None,
            "exited_at": None,
        }
        with patch.object(
            main_module.station_execution,
            "get_station_execution_context",
            return_value=empty,
        ) as helper:
            response = self.client.get("/api/v2/stations/assembly_01/execution-context")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["active_operation"])
        self.assertTrue(response.json()["dynamic_actions_enabled"])
        helper.assert_called_once_with(self.config, "assembly_01")

    def test_context_maps_domain_error(self) -> None:
        with patch.object(
            main_module.station_execution,
            "get_station_execution_context",
            side_effect=mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_CONTEXT_AMBIGUOUS",
                status_code=409,
            ),
        ):
            response = self.client.get("/api/v2/stations/X/execution-context")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_CONTEXT_AMBIGUOUS"})

    def test_post_core_disabled_does_not_read_or_call(self) -> None:
        self.config.db_station_execution_commands_enabled = False
        response, helper, logger = self._post(body=b"not-json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_COMMANDS_DISABLED"})
        helper.assert_not_called()
        logger.info.assert_called_once()

    def test_post_kiosk_flag_disabled(self) -> None:
        self.config.kiosk_dynamic_actions_enabled = False
        response, helper, _ = self._post()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "KIOSK_DYNAMIC_ACTIONS_DISABLED"})
        helper.assert_not_called()

    def test_valid_post_uses_server_controlled_source(self) -> None:
        response, helper, logger = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {
                "ok",
                "action_applied",
                "event_inserted",
                "implicit_started",
                "implicit_finished",
                "execution",
                "step",
                "completion_bridge",
                "station_context",
            },
        )
        called = helper.call_args.kwargs
        self.assertEqual(called["station_code"], "ASSEMBLY_01")
        self.assertIsNone(called["event_source"])
        self.assertEqual(called["command_source"], "kiosk")
        logger.info.assert_called_once()

    def test_exact_replay_is_200_and_not_applied(self) -> None:
        response, _, _ = self._post(result=self._result(applied=False))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["action_applied"])
        self.assertFalse(response.json()["event_inserted"])

    def test_http_preserves_both_implicit_flags(self) -> None:
        result = self._result()
        result["implicit_started"] = True
        result["implicit_finished"] = True
        response, _, _ = self._post(result=result)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["implicit_started"])
        self.assertTrue(response.json()["implicit_finished"])

    def test_domain_error_preserves_wire_contract(self) -> None:
        response, _, logger = self._post(
            side_effect=mesql_v2.MesqlV2Error(
                "STATION_EXECUTION_STEP_NOT_CURRENT",
                status_code=409,
            )
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_STEP_NOT_CURRENT"})
        logger.info.assert_called_once()

    def test_generic_exception_is_internal_error(self) -> None:
        response, _, logger = self._post(side_effect=RuntimeError("secret database row"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "INTERNAL_ERROR"})
        logger.exception.assert_called_once()

    def test_malformed_json_is_400(self) -> None:
        response, helper, _ = self._post(body=b'{"action":')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_REQUEST_INVALID"})
        helper.assert_not_called()

    def test_non_object_json_is_400(self) -> None:
        response, helper, _ = self._post(body=b"[]")
        self.assertEqual(response.status_code, 400)
        helper.assert_not_called()

    def test_duplicate_json_key_is_400(self) -> None:
        body = json.dumps(self.BODY).encode("utf-8")[:-1] + b',"action":"finish"}'
        response, helper, _ = self._post(body=body)
        self.assertEqual(response.status_code, 400)
        helper.assert_not_called()

    def test_unknown_field_is_rejected(self) -> None:
        response, helper, _ = self._post(body={**self.BODY, "unknown": True})
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_UNKNOWN_FIELD"})
        helper.assert_not_called()

    def test_server_field_is_rejected(self) -> None:
        response, helper, _ = self._post(body={**self.BODY, "event_source": "SENSOR"})
        self.assertEqual(
            response.json(),
            {"detail": "STATION_EXECUTION_SERVER_FIELD_NOT_ALLOWED"},
        )
        helper.assert_not_called()

    def test_invalid_action_is_rejected(self) -> None:
        response, helper, _ = self._post(body={**self.BODY, "action": "skip"})
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_ACTION_NOT_ALLOWED"})
        helper.assert_not_called()

    def test_metadata_must_be_object(self) -> None:
        response, helper, _ = self._post(body={**self.BODY, "metadata": []})
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_METADATA_INVALID"})
        helper.assert_not_called()

    def test_65537_raw_bytes_is_rejected(self) -> None:
        raw = json.dumps(self.BODY, separators=(",", ":")).encode("utf-8")
        raw += b" " * (65_537 - len(raw))
        response, helper, _ = self._post(body=raw)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "STATION_EXECUTION_REQUEST_TOO_LARGE"})
        helper.assert_not_called()

    def test_structured_log_excludes_metadata(self) -> None:
        response, _, logger = self._post()
        self.assertEqual(response.status_code, 200)
        extra = logger.info.call_args.kwargs["extra"]
        self.assertEqual(set(extra), set(station_execution.STATION_EXECUTION_COMMAND_LOG_FIELDS))
        self.assertNotIn("MUST_NOT_LOG", repr(extra))
        self.assertNotIn("metadata", extra)


class StationExecutionApplicationServiceTests(unittest.TestCase):
    def test_defaults_are_disabled(self) -> None:
        config = AppConfig()
        self.assertFalse(config.db_station_execution_commands_enabled)
        self.assertFalse(config.mqtt_station_execution_adapter_enabled)
        self.assertFalse(config.kiosk_dynamic_actions_enabled)
        self.assertEqual(
            config.mqtt_station_execution_client_id,
            "mes-web-station-execution",
        )
        self.assertEqual(config.mqtt_station_execution_enqueue_timeout_seconds, 5.0)

    def test_enqueue_timeout_env_is_bounded_and_positive(self) -> None:
        with patch.dict(
            os.environ,
            {"MES_WEB_MQTT_STATION_EXECUTION_ENQUEUE_TIMEOUT_SECONDS": "2.5"},
            clear=False,
        ):
            self.assertEqual(
                AppConfig.from_env().mqtt_station_execution_enqueue_timeout_seconds,
                2.5,
            )
        for value in ("0", "-1", "nan", "inf", "60.1"):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {"MES_WEB_MQTT_STATION_EXECUTION_ENQUEUE_TIMEOUT_SECONDS": value},
                clear=False,
            ), self.assertRaises(ValueError):
                AppConfig.from_env()

    def test_station_execution_client_id_is_stable_and_configurable(self) -> None:
        with patch.dict(
            os.environ,
            {"MES_WEB_MQTT_STATION_EXECUTION_CLIENT_ID": "station-runtime-a"},
            clear=False,
        ):
            self.assertEqual(
                AppConfig.from_env().mqtt_station_execution_client_id,
                "station-runtime-a",
            )

    def test_kiosk_actor_and_identity_are_normalized(self) -> None:
        config = AppConfig(db_enabled=True)
        with patch.object(
            station_execution.mesql_v2,
            "dispatch_station_execution_action",
            return_value={"status": "ok"},
        ) as primitive:
            station_execution.dispatch_station_execution_command(
                config,
                command_source="kiosk",
                station_code=" generic_station ",
                event_source="CLIENT_VALUE",
                external_event_id=" CMD-1 ",
                work_order_operation_id="00000000-0000-0000-0000-000000000099",
                step_code=" manual_step ",
                action=" START ",
                actor=" operator-1 ",
                metadata={},
            )
        values = primitive.call_args.kwargs
        self.assertEqual(values["station_code"], "GENERIC_STATION")
        self.assertIsNone(values["event_source"])
        self.assertEqual(values["step_code"], "MANUAL_STEP")
        self.assertEqual(values["actor_id"], "operator-1")
        self.assertNotIn(
            "KIOSK_OPERATOR",
            inspect.getsource(station_execution.dispatch_station_execution_command),
        )

    def test_noncanonical_lifecycle_uuid_is_rejected_before_db(self) -> None:
        with patch.object(
            station_execution.mesql_v2,
            "dispatch_station_execution_action",
        ) as primitive:
            with self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_OPERATION_NOT_FOUND",
            ):
                station_execution.dispatch_station_execution_command(
                    AppConfig(),
                    command_source="kiosk",
                    station_code="STATION_X",
                    event_source="KIOSK_OPERATOR",
                    external_event_id="CMD",
                    work_order_operation_id="00000000-0000-0000-0000-0000000000AA",
                    step_code="STEP",
                    action="start",
                    actor="actor",
                    metadata={},
                )
        primitive.assert_not_called()

    def test_mqtt_requires_explicit_lifecycle_and_publisher_event_ids_before_db(self) -> None:
        base = {
            "command_source": "mqtt",
            "station_code": "STATION_X",
            "event_source": "SENSOR_X",
            "external_event_id": "EVENT-1",
            "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
            "metadata": {},
        }
        with patch.object(
            station_execution.mesql_v2,
            "dispatch_station_execution_action",
        ) as primitive:
            for changes, expected in (
                ({"work_order_operation_id": None}, "STATION_EXECUTION_OPERATION_ID_REQUIRED"),
                ({"work_order_operation_id": ""}, "STATION_EXECUTION_OPERATION_ID_REQUIRED"),
                ({"external_event_id": None}, "STATION_EXECUTION_EXTERNAL_EVENT_ID_REQUIRED"),
                ({"external_event_id": 7}, "STATION_EXECUTION_EXTERNAL_EVENT_ID_REQUIRED"),
            ):
                with self.subTest(changes=changes), self.assertRaisesRegex(
                    mesql_v2.MesqlV2Error,
                    expected,
                ):
                    station_execution.dispatch_station_execution_command(
                        AppConfig(),
                        **{**base, **changes},
                    )
        primitive.assert_not_called()


class StationExecutionContextClassificationTests(unittest.TestCase):
    def _row(self, operation_id: str, *, rank: int, execution_status=None, **changes):
        row = {
            "station_queue_pk": rank,
            "station_code": "GENERIC_STATION",
            "queue_rank": rank,
            "work_order_id": f"WO-{rank}",
            "queue_status": "queued",
            "work_order_operation_id": operation_id,
            "operation_status": "queued",
            "binding_id": f"BINDING-{rank}",
            "route_operation_id": f"ROUTE_OPERATION_{rank}",
            "execution_status": execution_status,
        }
        row.update(changes)
        return row

    def test_empty_station_has_no_candidate(self) -> None:
        result = mesql_v2._classify_station_execution_context_rows([])
        self.assertIsNone(result["active_operation"])
        self.assertIsNone(result["next_queued_operation"])

    def test_smallest_queue_rank_is_selected(self) -> None:
        result = mesql_v2._classify_station_execution_context_rows([
            self._row("00000000-0000-0000-0000-000000000002", rank=20),
            self._row("00000000-0000-0000-0000-000000000001", rank=10),
        ])
        self.assertEqual(
            result["next_queued_operation"]["work_order_operation_id"],
            "00000000-0000-0000-0000-000000000001",
        )

    def test_active_operation_precedes_next_queue(self) -> None:
        active = self._row(
            "00000000-0000-0000-0000-000000000001",
            rank=10,
            execution_status="active",
        )
        queued = self._row(
            "00000000-0000-0000-0000-000000000002",
            rank=20,
        )
        result = mesql_v2._classify_station_execution_context_rows([active, queued])
        self.assertEqual(result["active_operation"], active)
        self.assertEqual(result["next_queued_operation"], queued)

    def test_two_active_operations_are_ambiguous(self) -> None:
        rows = [
            self._row("00000000-0000-0000-0000-000000000001", rank=10, execution_status="ready"),
            self._row("00000000-0000-0000-0000-000000000002", rank=20, execution_status="active"),
        ]
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_CONTEXT_AMBIGUOUS",
        ):
            mesql_v2._classify_station_execution_context_rows(rows)

    def test_tied_minimum_rank_is_ambiguous(self) -> None:
        rows = [
            self._row("00000000-0000-0000-0000-000000000001", rank=10),
            self._row(
                "00000000-0000-0000-0000-000000000002",
                rank=10,
                station_queue_pk=11,
            ),
        ]
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_CONTEXT_AMBIGUOUS",
        ):
            mesql_v2._classify_station_execution_context_rows(rows)

    def test_completed_context_is_only_last_closed(self) -> None:
        closed = self._row(
            "00000000-0000-0000-0000-000000000001",
            rank=10,
            execution_status="closed",
            queue_status="completed",
            operation_status="completed",
        )
        result = mesql_v2._classify_station_execution_context_rows([closed])
        self.assertIsNone(result["active_operation"])
        self.assertEqual(result["last_closed_operation"], closed)

    def test_live_candidate_requires_immutable_binding(self) -> None:
        row = self._row(
            "00000000-0000-0000-0000-000000000001",
            rank=10,
            binding_id=None,
        )
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED",
        ):
            mesql_v2._classify_station_execution_context_rows([row])

    def test_unbound_rank_one_blocks_bound_rank_two(self) -> None:
        rows = [
            self._row(
                "00000000-0000-0000-0000-000000000001",
                rank=1,
                binding_id=None,
                route_operation_id=None,
            ),
            self._row(
                "00000000-0000-0000-0000-000000000002",
                rank=2,
            ),
        ]
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "WORK_ORDER_OPERATION_ROUTE_BINDING_REQUIRED",
        ):
            mesql_v2._classify_station_execution_context_rows(rows)

    def test_station_context_sql_keeps_unbound_candidates_and_locks_identity_rows(self) -> None:
        self.assertIn(
            "left join mes.work_order_operation_route_bindings",
            mesql_v2.SELECT_STATION_EXECUTION_CONTEXT_SQL.lower(),
        )
        self.assertIn(
            "left join mes.work_order_operation_route_bindings",
            mesql_v2.SELECT_STATION_EXECUTION_CONTEXT_FOR_UPDATE_SQL.lower(),
        )
        self.assertIn(
            "for update",
            mesql_v2.SELECT_RUNTIME_WORK_ORDER_OPERATION_FOR_UPDATE_SQL.lower(),
        )
        self.assertIn(
            "for update",
            mesql_v2.SELECT_WORK_ORDER_OPERATION_ROUTE_BINDING_FOR_UPDATE_SQL.lower(),
        )

    def test_completion_advisory_scope_precedes_station_queue_lock(self) -> None:
        source = inspect.getsource(mesql_v2._dispatch_station_execution_action)
        self.assertLess(
            source.index("_lock_completion_bridge_station_scopes_cursor"),
            source.index("locked_rows = _select_station_execution_context_rows_cursor"),
        )

    def test_external_event_identity_lock_is_cross_source_and_precedes_work_order_lock(
        self,
    ) -> None:
        sql = mesql_v2.LOCK_STATION_EXECUTION_EVENT_IDENTITY_SQL.lower()
        self.assertIn("pg_advisory_xact_lock", sql)
        self.assertIn("%(station_code)s", sql)
        self.assertIn("%(external_event_id)s", sql)
        self.assertNotIn("event_source", sql)
        source = inspect.getsource(mesql_v2._dispatch_station_execution_action)
        self.assertLess(
            source.index("_lock_station_execution_event_identity_cursor"),
            source.index("_select_completion_bridge_work_order_for_update_cursor"),
        )

    def test_external_event_identity_lock_uses_only_normalized_identity(self) -> None:
        cursor = Mock()
        mesql_v2._lock_station_execution_event_identity_cursor(
            cursor,
            station_code="STATION_X",
            external_event_id="EVENT-1",
        )
        cursor.execute.assert_called_once_with(
            mesql_v2.LOCK_STATION_EXECUTION_EVENT_IDENTITY_SQL,
            {
                "station_code": "STATION_X",
                "external_event_id": "EVENT-1",
            },
        )

    def test_synchronized_duplicate_rechecks_event_after_work_order_lock(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        external_event_id = "SYNCHRONIZED-EVENT-1"
        lifecycle = {
            "work_order_operation_id": operation_id,
            "order_id": "WO-SYNCHRONIZED",
            "operation_code": "GENERIC_OPERATION",
            "station_code": "GENERIC_STATION",
        }
        target = self._row(
            operation_id,
            rank=1,
            work_order_id="WO-SYNCHRONIZED",
            route_operation_id="ROUTE_GENERIC",
            binding_id="BINDING-GENERIC",
        )
        configured_step = {
            "step_code": "GENERIC_STEP",
            "start_mode": "auto_start",
            "finish_mode": "auto_finish",
            "start_event_source_code": "SENSOR_X",
            "finish_event_source_code": "SENSOR_X",
        }
        operation_config = {
            "route_operation": {"station_code": "GENERIC_STATION"},
            "steps": [configured_step],
        }
        runtime_step = {"step_code": "GENERIC_STEP", "status": "pending"}
        binding = {
            "binding_id": "BINDING-GENERIC",
            "work_order_operation_id": operation_id,
            "route_operation_id": "ROUTE_GENERIC",
        }
        pre_read_barrier = threading.Barrier(2)
        pre_read_guard = threading.Lock()
        pre_read_count = 0
        work_order_lock = threading.Lock()
        event_guard = threading.Lock()
        persisted: dict[str, dict] = {}
        results: list[dict] = []
        failures: list[BaseException] = []

        class _Cursor:
            def __init__(self, connection):
                self.connection = connection
                self.sql = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, _params=None):
                self.sql = sql

            def fetchone(self):
                if self.sql in {
                    mesql_v2.SELECT_RUNTIME_WORK_ORDER_OPERATION_SQL,
                    mesql_v2.SELECT_RUNTIME_WORK_ORDER_OPERATION_FOR_UPDATE_SQL,
                }:
                    return lifecycle
                raise AssertionError(f"unexpected fetchone SQL: {self.sql!r}")

            def fetchall(self):
                if self.sql == mesql_v2.SELECT_EXECUTION_STEPS_SQL:
                    return []
                raise AssertionError(f"unexpected fetchall SQL: {self.sql!r}")

        class _Connection:
            def __init__(self):
                self.locked = False
                self.commit = Mock()

            def cursor(self):
                return _Cursor(self)

        class _Transaction:
            def __init__(self, connection):
                self.connection = connection

            def __enter__(self):
                return None

            def __exit__(self, *_args):
                if self.connection.locked:
                    self.connection.locked = False
                    work_order_lock.release()
                return False

        def _pre_read(*_args, **_kwargs):
            nonlocal pre_read_count
            with pre_read_guard:
                pre_read_count += 1
                is_initial_read = pre_read_count <= 2
            if is_initial_read:
                pre_read_barrier.wait(timeout=5)
                return None
            return _post_lock_read()

        def _lock_work_order(cursor, order_id):
            self.assertEqual(order_id, "WO-SYNCHRONIZED")
            work_order_lock.acquire(timeout=5)
            cursor.connection.locked = True
            return {"order_id": order_id}

        def _post_lock_read(*_args, **_kwargs):
            with event_guard:
                event = persisted.get("event")
                return dict(event) if event else None

        def _apply_once(*_args, **_kwargs):
            event = {
                "station_code": "GENERIC_STATION",
                "event_source": "SENSOR_X",
                "work_order_operation_id": operation_id,
                "step_code": "GENERIC_STEP",
                "event_type": "step_finish",
                "external_event_id": external_event_id,
                "payload": {"command_source": "mqtt"},
            }
            with event_guard:
                self.assertNotIn("event", persisted)
                persisted["event"] = event
            return {
                "action_applied": True,
                "event_inserted": True,
                "event": event,
            }

        def _replay(_cursor, event, *, station_code):
            self.assertEqual(station_code, "GENERIC_STATION")
            return {
                "action_applied": False,
                "event_inserted": False,
                "event": event,
            }

        def _run() -> None:
            try:
                result = mesql_v2.dispatch_station_execution_action(
                    AppConfig(db_enabled=True),
                    station_code="GENERIC_STATION",
                    command_source="mqtt",
                    event_source="SENSOR_X",
                    external_event_id=external_event_id,
                    work_order_operation_id=operation_id,
                )
                results.append(result)
            except BaseException as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        with (
            patch.object(
                mesql_v2,
                "database_connection",
                side_effect=lambda _config: nullcontext(_Connection()),
            ),
            patch.object(
                mesql_v2,
                "_transaction",
                side_effect=lambda connection: _Transaction(connection),
            ),
            patch.object(
                mesql_v2,
                "_get_operation_event_for_command_replay_cursor",
                side_effect=_pre_read,
            ),
            patch.object(
                mesql_v2,
                "_select_station_execution_context_rows_cursor",
                return_value=[target],
            ),
            patch.object(
                mesql_v2,
                "_select_completion_bridge_work_order_for_update_cursor",
                side_effect=_lock_work_order,
            ),
            patch.object(
                mesql_v2,
                "_get_route_operation_config_with_cursor",
                return_value=operation_config,
            ),
            patch.object(mesql_v2, "_assert_route_operation_config_valid"),
            patch.object(
                mesql_v2,
                "_select_completion_bridge_applicability_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2,
                "_get_work_order_operation_route_binding_with_cursor",
                return_value=binding,
            ),
            patch.object(
                mesql_v2,
                "_get_operation_event_by_external_event_with_cursor",
                side_effect=_post_lock_read,
            ),
            patch.object(
                mesql_v2,
                "_initialize_execution_state_cursor",
                return_value={"steps": [runtime_step]},
            ),
            patch.object(
                mesql_v2,
                "_station_execution_action_cursor",
                side_effect=_apply_once,
            ) as action_cursor,
            patch.object(
                mesql_v2,
                "_station_execution_replay_result_cursor",
                side_effect=_replay,
            ),
            patch.object(
                mesql_v2,
                "_station_execution_context_snapshot_cursor",
                return_value={},
            ),
        ):
            threads = [threading.Thread(target=_run) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(
            sorted(
                (result["action_applied"], result["event_inserted"])
                for result in results
            ),
            [(False, False), (True, True)],
        )
        action_cursor.assert_called_once()
        self.assertEqual(set(persisted), {"event"})

    def test_generic_transition_policy_supports_implicit_start_and_finish(self) -> None:
        implicit_start = {
            "start_mode": "implicit_start",
            "finish_mode": "manual_finish",
            "finish_event_source_code": "OPERATOR_X",
        }
        self.assertEqual(
            mesql_v2._resolve_station_execution_transition(
                implicit_start,
                runtime_status="pending",
                command_source="kiosk",
                event_source="OPERATOR_X",
                requested_action="finish",
            ),
            "finish",
        )
        implicit_finish = {
            "start_mode": "manual_start",
            "finish_mode": "implicit_finish",
            "start_event_source_code": "OPERATOR_X",
        }
        self.assertEqual(
            mesql_v2._resolve_station_execution_transition(
                implicit_finish,
                runtime_status="pending",
                command_source="kiosk",
                event_source="OPERATOR_X",
                requested_action="start",
            ),
            "start",
        )

    def test_transition_planner_covers_all_mode_pairs_and_flags(self) -> None:
        cases = (
            ("manual_start", "manual_finish", "pending", "start", False, False),
            ("manual_start", "manual_finish", "active", "finish", False, False),
            ("implicit_start", "manual_finish", "pending", "finish", True, False),
            ("manual_start", "implicit_finish", "pending", "start", False, True),
        )
        for start_mode, finish_mode, status, action, implicit_started, implicit_finished in cases:
            with self.subTest(start_mode=start_mode, finish_mode=finish_mode, status=status):
                step = {
                    "start_mode": start_mode,
                    "finish_mode": finish_mode,
                    "start_event_source_code": "PANEL_ACTION_ALPHA",
                    "finish_event_source_code": "PANEL_ACTION_ALPHA",
                }
                plan = mesql_v2._plan_station_execution_transition(
                    step,
                    runtime_status=status,
                    command_source="kiosk",
                    event_source="PANEL_ACTION_ALPHA",
                    requested_action=action,
                )
                self.assertEqual(plan["action"], action)
                self.assertEqual(plan["implicit_started"], implicit_started)
                self.assertEqual(plan["implicit_finished"], implicit_finished)

    def test_active_implicit_finish_is_inconsistent_not_repaired(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_POLICY_INCONSISTENT",
        ):
            mesql_v2._plan_station_execution_transition(
                {
                    "start_mode": "manual_start",
                    "finish_mode": "implicit_finish",
                    "start_event_source_code": "PANEL_ACTION_ALPHA",
                },
                runtime_status="active",
                command_source="kiosk",
                event_source="PANEL_ACTION_ALPHA",
                requested_action="finish",
            )

    def test_explicit_mqtt_start_disambiguates_shared_auto_source(self) -> None:
        plan = mesql_v2._plan_station_execution_transition(
            {
                "start_mode": "auto_start",
                "finish_mode": "auto_finish",
                "start_event_source_code": "SENSOR_X",
                "finish_event_source_code": "SENSOR_X",
            },
            runtime_status="pending",
            command_source="mqtt",
            event_source="SENSOR_X",
            requested_action="start",
        )
        self.assertEqual(plan["action"], "start")
        self.assertFalse(plan["implicit_started"])
        self.assertFalse(plan["implicit_finished"])

    def test_source_less_implicit_policy_requires_internal_transition(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_INTERNAL_ACTION_REQUIRED",
        ):
            mesql_v2._plan_station_execution_transition(
                {
                    "start_mode": "implicit_start",
                    "finish_mode": "implicit_finish",
                    "start_event_source_code": None,
                    "finish_event_source_code": None,
                },
                runtime_status="pending",
                command_source="kiosk",
                event_source="SOURCE_A",
                requested_action="start",
            )

    def test_configured_source_implicit_policy_remains_application_triggered(self) -> None:
        plan = mesql_v2._plan_station_execution_transition(
            {
                "start_mode": "implicit_start",
                "finish_mode": "implicit_finish",
                "start_event_source_code": "SOURCE_A",
                "finish_event_source_code": "SOURCE_A",
            },
            runtime_status="pending",
            command_source="kiosk",
            event_source="SOURCE_A",
            requested_action="start",
        )
        self.assertEqual(plan["action"], "start")
        self.assertTrue(plan["implicit_started"])
        self.assertTrue(plan["implicit_finished"])

    def test_source_less_implicit_policy_has_internal_mode_derived_plan(self) -> None:
        plan = mesql_v2._plan_station_execution_transition(
            {
                "start_mode": "implicit_start",
                "finish_mode": "implicit_finish",
                "start_event_source_code": None,
                "finish_event_source_code": None,
            },
            runtime_status="pending",
            command_source="internal",
            event_source=mesql_v2.STATION_EXECUTION_INTERNAL_EVENT_SOURCE,
            requested_action=None,
        )
        self.assertEqual(plan["action"], "finish")
        self.assertTrue(plan["implicit_started"])
        self.assertTrue(plan["implicit_finished"])
        self.assertTrue(plan["internal_transition"])

    def test_pending_requested_action_cannot_override_configured_transition(self) -> None:
        cases = (
            (
                {
                    "start_mode": "manual_start",
                    "finish_mode": "implicit_finish",
                    "start_event_source_code": "PANEL_ACTION_ALPHA",
                },
                "kiosk",
                "PANEL_ACTION_ALPHA",
                "finish",
            ),
            (
                {
                    "start_mode": "implicit_start",
                    "finish_mode": "manual_finish",
                    "finish_event_source_code": "PANEL_ACTION_ALPHA",
                },
                "kiosk",
                "PANEL_ACTION_ALPHA",
                "start",
            ),
            (
                {
                    "start_mode": "auto_start",
                    "finish_mode": "implicit_finish",
                    "start_event_source_code": "SENSOR_X",
                },
                "mqtt",
                "SENSOR_X",
                "finish",
            ),
        )
        for step, command_source, event_source, action in cases:
            with self.subTest(step=step, action=action), self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_ACTION_NOT_ALLOWED",
            ):
                mesql_v2._plan_station_execution_transition(
                    step,
                    runtime_status="pending",
                    command_source=command_source,
                    event_source=event_source,
                    requested_action=action,
                )

    def test_transition_policy_rejects_manual_automatic_channel_bypass(self) -> None:
        automatic = {
            "start_mode": "auto_start",
            "finish_mode": "auto_finish",
            "start_event_source_code": "SENSOR_X",
            "finish_event_source_code": "SENSOR_X",
        }
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_AUTOMATIC_ACTION_REQUIRED",
        ):
            mesql_v2._resolve_station_execution_transition(
                automatic,
                runtime_status="pending",
                command_source="kiosk",
                event_source="KIOSK_OPERATOR",
                requested_action="start",
            )

    def test_manual_start_with_implicit_finish_completes_atomically(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        state = {
            "work_order_operation_id": operation_id,
            "work_order_id": "WO-GENERIC",
            "station_code": "GENERIC_STATION",
            "operation_code": "GENERIC_OPERATION",
            "execution_status": "ready",
            "operation_completion_policy": "auto_close_on_required_steps",
            "metadata": {"route_operation_id": "ROUTE_GENERIC"},
        }
        pending_step = {
            "work_order_operation_step_id": "STEP-ID",
            "work_order_operation_id": operation_id,
            "work_order_id": "WO-GENERIC",
            "operation_code": "GENERIC_OPERATION",
            "step_code": "GENERIC_STEP",
            "step_no": 1,
            "station_code": "GENERIC_STATION",
            "status": "pending",
            "required_for_completion": True,
        }
        completed_step = {**pending_step, "status": "completed"}
        closed_state = {
            **state,
            "execution_status": "closed",
            "closed_at": "2026-07-19T00:00:00Z",
        }
        cursor = Mock()
        fetchone_rows = iter([state, completed_step, closed_state])
        cursor.fetchone.side_effect = lambda: next(fetchone_rows)
        cursor.fetchall.return_value = [pending_step]
        inserted_event = {
            "event_id": "EVENT-ROW-1",
            "event_time": "2026-07-19T00:00:00Z",
            "event_type": "step_start",
        }
        with (
            patch.object(
                mesql_v2,
                "_get_operation_step_with_cursor",
                return_value={
                    "start_mode": "manual_start",
                    "finish_mode": "implicit_finish",
                    "start_event_source_code": "PANEL_ACTION_ALPHA",
                },
            ),
            patch.object(
                mesql_v2,
                "_resolve_station_event_source_with_cursor",
                return_value={"active": True, "event_channel": "kiosk"},
            ),
            patch.object(
                mesql_v2,
                "_select_completion_bridge_applicability_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2,
                "_get_work_order_operation_route_binding_with_cursor",
                return_value={"route_operation_id": "ROUTE_GENERIC"},
            ),
            patch.object(
                mesql_v2,
                "_get_operation_event_by_idempotency_key_with_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2,
                "_get_operation_event_by_external_event_with_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2,
                "_record_operation_event_with_cursor",
                return_value=inserted_event,
            ) as recorder,
        ):
            result = mesql_v2._station_execution_action_cursor(
                cursor,
                work_order_operation_id=operation_id,
                route_operation_id="ROUTE_GENERIC",
                station_code="GENERIC_STATION",
                step_code="GENERIC_STEP",
                action="start",
                command_source="kiosk",
                event_source="PANEL_ACTION_ALPHA",
                external_event_id="PUBLISHER-EVENT-1",
                actor_id="OPERATOR",
                payload={},
            )
        self.assertFalse(result["implicit_started"])
        self.assertTrue(result["implicit_finished"])
        self.assertEqual(result["step"]["status"], "completed")
        self.assertEqual(result["execution_state"]["execution_status"], "closed")
        self.assertEqual(recorder.call_args.kwargs["event_type"], "step_start")
        self.assertEqual(
            recorder.call_args.kwargs["payload"]["command_source"],
            "kiosk",
        )
        self.assertFalse(
            recorder.call_args.kwargs["payload"]["implicit_started"]
        )
        self.assertTrue(
            recorder.call_args.kwargs["payload"]["implicit_finished"]
        )

    def test_replay_restores_persisted_transition_flags(self) -> None:
        cursor = Mock()
        cursor.fetchone.return_value = {
            "execution_status": "active",
            "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
        }
        cursor.fetchall.return_value = []
        result = mesql_v2._station_execution_replay_result_cursor(
            cursor,
            {
                "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
                "step_code": "STEP_X",
                "event_type": "step_start",
                "payload": {
                    "implicit_started": True,
                    "implicit_finished": True,
                },
            },
            station_code="GENERIC_STATION",
        )
        self.assertFalse(result["action_applied"])
        self.assertFalse(result["event_inserted"])
        self.assertTrue(result["implicit_started"])
        self.assertTrue(result["implicit_finished"])

    def test_closed_runtime_replay_never_repairs_unbridged_lifecycle(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        cursor = Mock()
        cursor.fetchone.return_value = {
            "execution_status": "closed",
            "closed_at": "2026-07-19T00:00:00Z",
            "work_order_operation_id": operation_id,
        }
        cursor.fetchall.return_value = []
        applicability = {
            "work_order_operation_id": operation_id,
            "order_id": "WO-1",
            "station_code": "GENERIC_STATION",
            "status": "active",
            "completed_at": None,
            "metadata": {
                "source": "work_order_release",
                "release_id": "RELEASE-1",
            },
        }
        with (
            patch.object(
                mesql_v2,
                "_select_completion_bridge_applicability_cursor",
                return_value=applicability,
            ),
            patch.object(
                mesql_v2,
                "_prepare_runtime_completion_bridge_cursor",
            ) as prepare,
            patch.object(
                mesql_v2,
                "_apply_runtime_completion_bridge_cursor",
            ) as apply_bridge,
        ):
            with self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "RUNTIME_COMPLETION_BRIDGE_OPERATION_STATE_CONFLICT",
            ):
                mesql_v2._station_execution_replay_result_cursor(
                    cursor,
                    {
                        "work_order_operation_id": operation_id,
                        "step_code": "STEP_X",
                        "event_source": "PANEL_ACTION_ALPHA",
                        "event_type": "step_finish",
                        "payload": {},
                    },
                    station_code="GENERIC_STATION",
                )
        prepare.assert_not_called()
        apply_bridge.assert_not_called()

    def test_kiosk_replay_uses_persisted_source_without_current_source_lookup(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        event = {
            "work_order_operation_id": operation_id,
            "station_code": "GENERIC_STATION",
            "step_code": "STEP_X",
            "event_source": "PANEL_ACTION_ALPHA",
            "event_type": "step_start",
            "external_event_id": "KIOSK-REPLAY-1",
            "payload": {
                "command_source": "kiosk",
                "implicit_started": False,
                "implicit_finished": False,
            },
        }
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        with (
            patch.object(
                mesql_v2,
                "database_connection",
                return_value=nullcontext(connection),
            ),
            patch.object(mesql_v2, "_transaction", return_value=nullcontext()),
            patch.object(
                mesql_v2,
                "_get_operation_event_for_command_replay_cursor",
                return_value=event,
            ),
            patch.object(
                mesql_v2,
                "_station_execution_replay_result_cursor",
                return_value={
                    "action_applied": False,
                    "event_inserted": False,
                    "event_source": "PANEL_ACTION_ALPHA",
                },
            ),
            patch.object(
                mesql_v2,
                "_station_execution_context_snapshot_cursor",
                return_value={},
            ),
            patch.object(
                mesql_v2,
                "_resolve_station_event_source_with_cursor",
            ) as source_lookup,
        ):
            result = mesql_v2.dispatch_station_execution_action(
                AppConfig(db_enabled=True),
                station_code="GENERIC_STATION",
                command_source="kiosk",
                event_source=None,
                external_event_id="KIOSK-REPLAY-1",
                work_order_operation_id=operation_id,
                step_code="STEP_X",
                action="start",
                actor_id="OPERATOR",
            )
        self.assertEqual(result["event_source"], "PANEL_ACTION_ALPHA")
        source_lookup.assert_not_called()
        connection.commit.assert_not_called()

    def test_kiosk_replay_rejects_mqtt_event_with_same_external_identity(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        event = {
            "work_order_operation_id": operation_id,
            "station_code": "GENERIC_STATION",
            "step_code": "STEP_X",
            "event_source": "SENSOR_X",
            "event_type": "step_start",
            "external_event_id": "CROSS-CHANNEL-1",
            "payload": {"command_source": "mqtt"},
        }
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        with (
            patch.object(
                mesql_v2,
                "database_connection",
                return_value=nullcontext(connection),
            ),
            patch.object(mesql_v2, "_transaction", return_value=nullcontext()),
            patch.object(
                mesql_v2,
                "_get_operation_event_for_command_replay_cursor",
                return_value=event,
            ),
            patch.object(
                mesql_v2,
                "_record_operation_event_with_cursor",
            ) as recorder,
        ):
            with self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_EXTERNAL_EVENT_ID_CONFLICT",
            ):
                mesql_v2.dispatch_station_execution_action(
                    AppConfig(db_enabled=True),
                    station_code="GENERIC_STATION",
                    command_source="kiosk",
                    event_source=None,
                    external_event_id="CROSS-CHANNEL-1",
                    work_order_operation_id=operation_id,
                    step_code="STEP_X",
                    action="start",
                    actor_id="OPERATOR",
                )
        recorder.assert_not_called()
        connection.commit.assert_not_called()

    def test_completion_lock_set_contains_current_and_successor_station(self) -> None:
        cursor = Mock()
        cursor.fetchall.return_value = [
            {
                "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
                "order_id": "WO-1",
                "sequence_no": 10,
                "station_code": "STATION_B",
            },
            {
                "work_order_operation_id": "00000000-0000-0000-0000-000000000002",
                "order_id": "WO-1",
                "sequence_no": 20,
                "station_code": "STATION_A",
            },
        ]
        self.assertEqual(
            mesql_v2._station_execution_completion_station_codes_cursor(
                cursor,
                work_order_id="WO-1",
                work_order_operation_id=(
                    "00000000-0000-0000-0000-000000000001"
                ),
            ),
            ["STATION_A", "STATION_B"],
        )
        self.assertEqual(
            cursor.execute.call_args.args[0],
            mesql_v2.SELECT_WORK_ORDER_RELEASE_OPERATIONS_SQL,
        )

    def test_queue_lifecycle_mismatch_locks_lifecycle_work_order_and_writes_nothing(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        lifecycle_row = {
            "work_order_operation_id": operation_id,
            "order_id": "ORDER-A",
            "operation_code": "OP-X",
            "station_code": "GENERIC_STATION",
        }
        queue_target = {
            "work_order_operation_id": operation_id,
            "work_order_id": "ORDER-B",
            "station_code": "GENERIC_STATION",
            "queue_status": "queued",
            "operation_status": "queued",
            "queue_rank": 1,
            "route_operation_id": "ROUTE-X",
            "binding_id": "BINDING-X",
            "execution_status": None,
        }
        cursor = Mock()
        cursor.fetchone.side_effect = [lifecycle_row, lifecycle_row]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        work_order_lock = Mock(return_value={"order_id": "ORDER-A"})
        recorder = Mock()
        with (
            patch.object(mesql_v2, "database_connection", return_value=nullcontext(connection)),
            patch.object(mesql_v2, "_transaction", return_value=nullcontext()),
            patch.object(
                mesql_v2,
                "_get_operation_event_for_command_replay_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2,
                "_select_station_execution_context_rows_cursor",
                side_effect=[[queue_target], [queue_target]],
            ),
            patch.object(
                mesql_v2,
                "_select_completion_bridge_work_order_for_update_cursor",
                work_order_lock,
            ),
            patch.object(mesql_v2, "_record_operation_event_with_cursor", recorder),
        ):
            with self.assertRaisesRegex(
                mesql_v2.MesqlV2Error,
                "STATION_EXECUTION_QUEUE_OPERATION_IDENTITY_CONFLICT",
            ):
                mesql_v2.dispatch_station_execution_action(
                    AppConfig(db_enabled=True),
                    station_code="GENERIC_STATION",
                    command_source="mqtt",
                    event_source="SENSOR_X",
                    external_event_id="EVENT-X",
                    work_order_operation_id=operation_id,
                )
        work_order_lock.assert_called_once_with(cursor, "ORDER-A")
        recorder.assert_not_called()
        connection.commit.assert_not_called()

    def test_event_replay_requires_exact_operation_step_and_action(self) -> None:
        event = {
            "station_code": "GENERIC_STATION",
            "event_source": "KIOSK_OPERATOR",
            "work_order_operation_id": "00000000-0000-0000-0000-000000000001",
            "step_code": "STEP_A",
            "event_type": "step_start",
            "payload": {"command_source": "kiosk"},
        }
        self.assertTrue(
            mesql_v2._station_execution_event_matches_command(
                event,
                work_order_operation_id=event["work_order_operation_id"],
                step_code="STEP_A",
                action="start",
                station_code="GENERIC_STATION",
                event_source="KIOSK_OPERATOR",
                command_source="kiosk",
            )
        )
        self.assertFalse(
            mesql_v2._station_execution_event_matches_command(
                event,
                work_order_operation_id=event["work_order_operation_id"],
                step_code="STEP_B",
                action="finish",
                station_code="GENERIC_STATION",
                event_source="KIOSK_OPERATOR",
                command_source="kiosk",
            )
        )
        self.assertFalse(
            mesql_v2._station_execution_event_matches_command(
                event,
                work_order_operation_id=event["work_order_operation_id"],
                step_code="STEP_A",
                action="start",
                station_code="GENERIC_STATION",
                event_source="KIOSK_OPERATOR",
                command_source="mqtt",
            )
        )

    def test_cross_channel_external_id_lookup_conflicts_in_both_directions(self) -> None:
        for persisted_source, requested_source in (
            ("SENSOR_X", None),
            ("PANEL_ACTION_ALPHA", "SENSOR_X"),
        ):
            with self.subTest(
                persisted_source=persisted_source,
                requested_source=requested_source,
            ):
                cursor = Mock()
                cursor.fetchall.return_value = [
                    {
                        "station_code": "GENERIC_STATION",
                        "event_source": persisted_source,
                        "external_event_id": "SHARED-ID-1",
                    }
                ]
                if requested_source is None:
                    event = mesql_v2._get_operation_event_for_command_replay_cursor(
                        cursor,
                        station_code="GENERIC_STATION",
                        event_source=None,
                        external_event_id="SHARED-ID-1",
                    )
                    self.assertEqual(event["event_source"], persisted_source)
                    self.assertFalse(
                        mesql_v2._station_execution_event_matches_command(
                            {**event, "payload": {"command_source": "mqtt"}},
                            work_order_operation_id=None,
                            step_code=None,
                            action=None,
                            station_code="GENERIC_STATION",
                            event_source="",
                            command_source="kiosk",
                        )
                    )
                else:
                    with self.assertRaisesRegex(
                        mesql_v2.MesqlV2Error,
                        "STATION_EXECUTION_EXTERNAL_EVENT_ID_CONFLICT",
                    ):
                        mesql_v2._get_operation_event_for_command_replay_cursor(
                            cursor,
                            station_code="GENERIC_STATION",
                            event_source=requested_source,
                            external_event_id="SHARED-ID-1",
                        )

    def test_internal_transition_namespace_and_fixed_event_identities(self) -> None:
        self.assertEqual(
            mesql_v2.STATION_EXECUTION_INTERNAL_TRANSITION_NAMESPACE,
            mesql_v2.uuid.uuid5(
                mesql_v2.uuid.NAMESPACE_URL,
                mesql_v2.STATION_EXECUTION_INTERNAL_TRANSITION_NAMESPACE_LABEL,
            ),
        )
        common = {
            "work_order_operation_id": (
                "00000000-0000-0000-0000-000000000001"
            ),
            "route_operation_id": "ROUTE-OP-1",
            "step_code": "STEP-1",
            "predecessor_identity": "release:RELEASE-1",
            "release_id": "RELEASE-1",
        }
        self.assertEqual(
            mesql_v2._derive_internal_station_execution_event_identity(
                **common,
                transition_phase="start",
                action_identity="step_start",
            ),
            "c89f3cf5-d3dd-5b79-989b-d004a18c1322",
        )
        self.assertEqual(
            mesql_v2._derive_internal_station_execution_event_identity(
                **common,
                transition_phase="finish",
                action_identity="step_finish",
            ),
            "919ea551-e3b6-5f0c-804c-388bc2022545",
        )

    def test_source_less_internal_transition_records_start_then_finish_atomically(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        pending_step = {
            "work_order_operation_step_id": "STEP-ID",
            "step_code": "STEP-1",
            "status": "pending",
            "required_for_completion": True,
        }
        completed_step = {**pending_step, "status": "completed"}
        state = {
            "work_order_id": "WO-1",
            "operation_code": "OP-1",
            "execution_status": "ready",
            "operation_completion_policy": "auto_close_on_required_steps",
        }
        closed_state = {
            **state,
            "execution_status": "closed",
            "closed_at": "2026-07-19T00:00:00Z",
        }
        bridge_context = {
            "release": {"release_id": "RELEASE-1"},
            "lifecycle_operations": [
                {"work_order_operation_id": operation_id}
            ],
        }
        cursor = Mock()
        cursor.fetchone.side_effect = [completed_step, closed_state]

        def _event(**kwargs):
            phase = kwargs["phase"]
            return {
                "event_id": f"EVENT-{phase.upper()}",
                "event_time": f"2026-07-19T00:00:0{phase == 'finish'}Z",
                "event_type": f"step_{phase}",
            }

        with (
            patch.object(
                mesql_v2,
                "_get_operation_event_by_idempotency_key_with_cursor",
                return_value=None,
            ),
            patch.object(
                mesql_v2,
                "_record_internal_station_execution_phase_event_cursor",
                side_effect=lambda _cursor, **kwargs: _event(**kwargs),
            ) as recorder,
            patch.object(
                mesql_v2,
                "_apply_runtime_completion_bridge_cursor",
                return_value={"bridged": True},
            ) as bridge,
        ):
            result = mesql_v2._internal_station_execution_action_cursor(
                cursor,
                work_order_operation_id=operation_id,
                route_operation_id="ROUTE-OP-1",
                station_code="GENERIC_STATION",
                step_code="STEP-1",
                operation_step={
                    "start_mode": "implicit_start",
                    "finish_mode": "implicit_finish",
                },
                execution_state=state,
                execution_steps=[pending_step],
                binding={"metadata": {"release_id": "RELEASE-1"}},
                bridge_context=bridge_context,
                actor_id=None,
            )
        self.assertEqual(
            [item.kwargs["phase"] for item in recorder.call_args_list],
            ["start", "finish"],
        )
        self.assertEqual([event["event_type"] for event in result["events"]], [
            "step_start",
            "step_finish",
        ])
        self.assertTrue(result["implicit_started"])
        self.assertTrue(result["implicit_finished"])
        self.assertTrue(result["completion_bridge"]["bridged"])
        bridge.assert_called_once()

    def test_internal_transition_partial_event_set_is_conflict_without_write(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        cursor = Mock()
        with patch.object(
            mesql_v2,
            "_get_operation_event_by_idempotency_key_with_cursor",
            side_effect=[{"event_id": "START"}, None],
        ), self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_INTERNAL_IDENTITY_CONFLICT",
        ):
            mesql_v2._internal_station_execution_action_cursor(
                cursor,
                work_order_operation_id=operation_id,
                route_operation_id="ROUTE-OP-1",
                station_code="GENERIC_STATION",
                step_code="STEP-1",
                operation_step={
                    "start_mode": "implicit_start",
                    "finish_mode": "implicit_finish",
                },
                execution_state={"execution_status": "closed"},
                execution_steps=[],
                binding={"metadata": {"release_id": "RELEASE-1"}},
                bridge_context={
                    "release": {"release_id": "RELEASE-1"},
                    "lifecycle_operations": [
                        {"work_order_operation_id": operation_id}
                    ],
                },
                actor_id=None,
            )
        cursor.execute.assert_not_called()

    def test_internal_transition_exact_retry_uses_two_event_replay_without_write(self) -> None:
        operation_id = "00000000-0000-0000-0000-000000000001"
        cursor = Mock()
        start_event = {"event_id": "START"}
        finish_event = {"event_id": "FINISH"}
        with (
            patch.object(
                mesql_v2,
                "_get_operation_event_by_idempotency_key_with_cursor",
                side_effect=[start_event, finish_event],
            ),
            patch.object(
                mesql_v2,
                "_internal_station_execution_event_matches",
                return_value=True,
            ),
            patch.object(
                mesql_v2,
                "_internal_station_execution_replay_result_cursor",
                return_value={
                    "action_applied": False,
                    "event_inserted": False,
                    "events": [start_event, finish_event],
                },
            ),
        ):
            result = mesql_v2._internal_station_execution_action_cursor(
                cursor,
                work_order_operation_id=operation_id,
                route_operation_id="ROUTE-OP-1",
                station_code="GENERIC_STATION",
                step_code="STEP-1",
                operation_step={
                    "start_mode": "implicit_start",
                    "finish_mode": "implicit_finish",
                },
                execution_state={"execution_status": "closed"},
                execution_steps=[],
                binding={"metadata": {"release_id": "RELEASE-1"}},
                bridge_context={
                    "release": {"release_id": "RELEASE-1"},
                    "lifecycle_operations": [
                        {"work_order_operation_id": operation_id}
                    ],
                },
                actor_id=None,
            )
        self.assertFalse(result["action_applied"])
        self.assertFalse(result["event_inserted"])
        cursor.execute.assert_not_called()

    def test_external_dispatch_cannot_claim_internal_command_source(self) -> None:
        with self.assertRaisesRegex(
            mesql_v2.MesqlV2Error,
            "STATION_EXECUTION_ACTION_NOT_ALLOWED",
        ):
            mesql_v2.dispatch_station_execution_action(
                AppConfig(db_enabled=True),
                station_code="GENERIC_STATION",
                command_source="internal",
                event_source=mesql_v2.STATION_EXECUTION_INTERNAL_EVENT_SOURCE,
                external_event_id="",
                work_order_operation_id=(
                    "00000000-0000-0000-0000-000000000001"
                ),
            )


if __name__ == "__main__":
    unittest.main()
