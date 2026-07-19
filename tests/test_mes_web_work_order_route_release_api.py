from __future__ import annotations

import asyncio
import copy
import http.client
import io
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import mes_web.__main__ as main_module
from mes_web.config import AppConfig


class _FakeStreamingRequest:
    def __init__(
        self,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
        *,
        fail_on_chunk_index: int | None = None,
    ) -> None:
        self._chunks = chunks
        self.headers = headers or {}
        self.fail_on_chunk_index = fail_on_chunk_index
        self.consumed_chunks = 0

    async def stream(self):
        for index, chunk in enumerate(self._chunks):
            if index == self.fail_on_chunk_index:
                raise AssertionError("unread sentinel chunk was requested")
            self.consumed_chunks += 1
            yield chunk


class _ExplodingBodyRequest:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.header_accesses = 0
        self.body_accesses = 0
        self.stream_accesses = 0

    @property
    def headers(self):
        self.header_accesses += 1
        raise AssertionError("disabled endpoint accessed request headers")

    async def body(self):
        self.body_accesses += 1
        raise AssertionError("disabled endpoint accessed request body")

    def stream(self):
        self.stream_accesses += 1
        raise AssertionError("disabled endpoint accessed request stream")


class WorkOrderRouteReleaseApiTests(unittest.TestCase):
    PATH = "/api/v2/work-orders/WO-API-001/route-release"
    STRUCTURED_LOG_FIELDS = {
        "event",
        "work_order_id",
        "release_id",
        "route_code",
        "route_version",
        "released_by",
        "released",
        "error_code",
        "duration_ms",
    }
    VALID_REQUEST = {
        "release_id": "RELEASE-API-001",
        "route_code": "ROUTE_BOX_PACKAGING_V2",
        "route_version": 2,
        "released_by": "LOCAL_PLANNER",
        "metadata": {"purpose": "offline_api_test"},
    }

    def setUp(self) -> None:
        self.config = AppConfig(db_enabled=True)
        self.app = FastAPI()
        main_module.register_work_order_route_release_routes(self.app, self.config)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.logger_patcher = patch.object(main_module, "logger")
        self.logger_patcher.start()
        self.addCleanup(self.logger_patcher.stop)

    def _helper_result(self, *, released: bool = True) -> dict:
        return {
            "released": released,
            "release": {"release_id": "RELEASE-API-001", "metadata": {"persisted": True}},
            "work_order": {"order_id": "WO-API-001", "status": "queued"},
            "operations": [{"work_order_operation_id": "00000000-0000-0000-0000-000000000001"}],
            "bindings": [{"binding_id": "BINDING-001"}],
            "initial_queue": {"station_queue_pk": 1},
        }

    def _body(self, request: dict | None = None) -> bytes:
        return json.dumps(request or self.VALID_REQUEST, separators=(",", ":")).encode("utf-8")

    def _body_at_size(self, size: int) -> bytes:
        body = self._body()
        self.assertLessEqual(len(body), size)
        return body + (b" " * (size - len(body)))

    def _post(
        self,
        *,
        body: bytes | None = None,
        flag: str | None = "true",
        headers: dict[str, str] | None = None,
        result: dict | None = None,
        side_effect: Exception | None = None,
        path: str | None = None,
    ):
        with patch.dict(os.environ, {}, clear=False):
            if flag is None:
                os.environ.pop(main_module.WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG, None)
            else:
                os.environ[main_module.WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG] = flag
            with patch.object(
                main_module.mesql_v2,
                "release_work_order_to_route",
                return_value=result or self._helper_result(),
                side_effect=side_effect,
            ) as helper:
                response = self.client.post(
                    path or self.PATH,
                    content=self._body() if body is None else body,
                    headers={"content-type": "application/json", **(headers or {})},
                )
        return response, helper

    def _assert_invalid_body(self, body: bytes) -> None:
        response, helper = self._post(body=body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID"})
        helper.assert_not_called()

    def _assert_field_error(self, request: dict, detail: str) -> None:
        response, helper = self._post(body=self._body(request))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": detail})
        helper.assert_not_called()

    def _assert_structured_log(
        self,
        logged,
        *,
        error_code: str | None,
        released: bool | None,
        secret: str | None = None,
    ) -> dict:
        logged.assert_called_once()
        self.assertEqual(logged.call_args.args, ("work_order_route_release_request",))
        extra = logged.call_args.kwargs["extra"]
        self.assertEqual(set(extra), self.STRUCTURED_LOG_FIELDS)
        self.assertEqual(extra["event"], "work_order_route_release_request")
        self.assertEqual(extra["error_code"], error_code)
        self.assertIs(extra["released"], released)
        self.assertIsInstance(extra["duration_ms"], (int, float))
        self.assertGreaterEqual(extra["duration_ms"], 0)
        self.assertNotIn("body", extra)
        self.assertNotIn("metadata", extra)
        if secret is not None:
            self.assertNotIn(secret, repr(extra))
        for field in ("work_order_id", "release_id", "route_code", "released_by"):
            if extra[field] is None:
                continue
            for control_character in ("\n", "\r", "\t"):
                self.assertNotIn(control_character, extra[field])
        return extra

    # Registration and feature flag.

    def test_route_is_registered_once_for_post(self) -> None:
        routes = [
            route
            for route in self.app.routes
            if getattr(route, "path", None) == "/api/v2/work-orders/{work_order_id}/route-release"
        ]
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].methods, {"POST"})

    def test_missing_flag_is_disabled(self) -> None:
        response, helper = self._post(flag=None)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_ROUTE_RELEASE_DISABLED"})
        helper.assert_not_called()

    def test_false_flag_is_disabled(self) -> None:
        response, helper = self._post(flag="false")
        self.assertEqual(response.status_code, 503)
        helper.assert_not_called()

    def test_true_flag_is_enabled(self) -> None:
        response, helper = self._post(flag="true")
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()

    def test_uppercase_true_flag_is_enabled(self) -> None:
        response, helper = self._post(flag=" TRUE ")
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()

    def test_one_flag_is_enabled(self) -> None:
        response, helper = self._post(flag="1")
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()

    def test_yes_flag_is_enabled(self) -> None:
        response, helper = self._post(flag="yes")
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()

    def test_on_flag_is_enabled(self) -> None:
        response, helper = self._post(flag="On")
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()

    def test_unsupported_flag_value_is_disabled(self) -> None:
        response, helper = self._post(flag="enabled")
        self.assertEqual(response.status_code, 503)
        helper.assert_not_called()

    def test_disabled_request_never_calls_helper(self) -> None:
        response, helper = self._post(flag="0")
        self.assertEqual(response.status_code, 503)
        helper.assert_not_called()

    def test_disabled_request_never_calls_body_reader(self) -> None:
        with patch.object(main_module, "_read_work_order_route_release_body") as reader:
            response, helper = self._post(flag="false", body=b"not-json")
        self.assertEqual(response.status_code, 503)
        reader.assert_not_called()
        helper.assert_not_called()

    def test_disabled_request_logs_one_sanitized_outcome_without_body_access(self) -> None:
        secret = "DISABLED-BODY-SECRET"
        body = json.dumps({"metadata": {"secret": secret}}).encode("utf-8")
        with (
            patch.object(main_module, "_read_work_order_route_release_body") as reader,
            patch.object(main_module, "_parse_work_order_route_release_json") as parser,
            patch.object(main_module.logger, "info") as logged,
        ):
            response, helper = self._post(
                flag="false",
                body=body,
                headers={"content-length": "999999"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_ROUTE_RELEASE_DISABLED"})
        reader.assert_not_called()
        parser.assert_not_called()
        helper.assert_not_called()
        extra = self._assert_structured_log(
            logged,
            error_code="WORK_ORDER_ROUTE_RELEASE_DISABLED",
            released=None,
            secret=secret,
        )
        self.assertEqual(extra["work_order_id"], "WO-API-001")
        self.assertIsNone(extra["release_id"])
        self.assertIsNone(extra["route_code"])
        self.assertIsNone(extra["route_version"])
        self.assertIsNone(extra["released_by"])

    def test_disabled_endpoint_does_not_access_headers_body_or_stream(self) -> None:
        secret = "EXPLODING-DISABLED-BODY-SECRET"
        request = _ExplodingBodyRequest(secret)
        route = next(
            route
            for route in self.app.routes
            if getattr(route, "path", None) == "/api/v2/work-orders/{work_order_id}/route-release"
        )
        with (
            patch.dict(
                os.environ,
                {main_module.WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG: "false"},
                clear=False,
            ),
            patch.object(main_module.mesql_v2, "release_work_order_to_route") as helper,
            patch.object(main_module.logger, "info") as logged,
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(route.endpoint(work_order_id="WO-API-001", request=request))
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail, "WORK_ORDER_ROUTE_RELEASE_DISABLED")
        self.assertEqual(request.header_accesses, 0)
        self.assertEqual(request.body_accesses, 0)
        self.assertEqual(request.stream_accesses, 0)
        helper.assert_not_called()
        self._assert_structured_log(
            logged,
            error_code="WORK_ORDER_ROUTE_RELEASE_DISABLED",
            released=None,
            secret=secret,
        )

    def test_env_example_declares_default_false_flag(self) -> None:
        text = Path("docker/mes/.env.example").read_text(encoding="utf-8")
        self.assertIn("MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED=false", text)

    def test_development_compose_passes_default_false_flag(self) -> None:
        text = Path("docker/mes/compose.yaml").read_text(encoding="utf-8")
        self.assertIn(
            "MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED: ${MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED:-false}",
            text,
        )

    def test_portable_compose_passes_default_false_flag(self) -> None:
        text = Path("docker/mes/compose.portable.yaml").read_text(encoding="utf-8")
        self.assertIn(
            "MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED: ${MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED:-false}",
            text,
        )

    # Bounded raw body.

    def test_declared_length_over_limit_returns_413_early(self) -> None:
        response, helper = self._post(headers={"content-length": "65537"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE"})
        helper.assert_not_called()

    def test_exact_65536_actual_bytes_pass_size_gate(self) -> None:
        request = _FakeStreamingRequest([b"a" * 32_768, b"b" * 32_768])
        result = asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(len(result), 65_536)

    def test_exact_65537_actual_bytes_returns_413(self) -> None:
        body = b"a" * 65_537
        self.assertEqual(len(body), 65_537)
        request = _FakeStreamingRequest(
            [body[:65_536], body[65_536:], b"unread-sentinel"],
            fail_on_chunk_index=2,
        )
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(error.exception.status_code, 413)
        self.assertEqual(error.exception.detail, "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE")
        self.assertEqual(request.consumed_chunks, 2)

    def test_registered_app_stops_asgi_receive_before_unread_sentinel(self) -> None:
        chunk_1 = b"a" * 65_535
        chunk_2 = b"bb"
        sentinel_chunk = b"unread-sentinel"
        self.assertEqual(len(chunk_1), 65_535)
        self.assertEqual(len(chunk_2), 2)
        self.assertEqual(len(chunk_1) + len(chunk_2), 65_537)

        request_messages = [
            {"type": "http.request", "body": chunk_1, "more_body": True},
            {"type": "http.request", "body": chunk_2, "more_body": True},
            {"type": "http.request", "body": sentinel_chunk, "more_body": False},
        ]
        receive_call_count = 0
        sent_messages: list[dict] = []

        async def receive() -> dict:
            nonlocal receive_call_count
            receive_call_count += 1
            if receive_call_count > 2:
                raise AssertionError(
                    "ASGI receive was called after the body exceeded 65,536 bytes"
                )
            return request_messages[receive_call_count - 1]

        async def send(message: dict) -> None:
            sent_messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v2/work-orders/WO-API-001/route-release",
            "raw_path": b"/api/v2/work-orders/WO-API-001/route-release",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", b"10"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        async def invoke_registered_app() -> None:
            await self.app(scope, receive, send)

        with (
            patch.dict(
                os.environ,
                {main_module.WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG: "true"},
                clear=False,
            ),
            patch.object(main_module.mesql_v2, "release_work_order_to_route") as helper,
            patch.object(main_module, "_parse_work_order_route_release_json") as parser,
            patch.object(main_module.json, "loads") as json_loads,
            patch.object(main_module.mesql_v2, "database_connection") as database,
            patch.object(main_module.mesql_v2, "get_work_order_route_release") as by_order,
            patch.object(main_module.mesql_v2, "get_work_order_route_release_by_id") as by_id,
            patch.object(main_module.mesql_v2, "get_work_order_release_snapshot") as snapshot,
        ):
            asyncio.run(invoke_registered_app())

        self.assertEqual(receive_call_count, 2)
        helper.assert_not_called()
        parser.assert_not_called()
        json_loads.assert_not_called()
        database.assert_not_called()
        by_order.assert_not_called()
        by_id.assert_not_called()
        snapshot.assert_not_called()

        response_starts = [
            message
            for message in sent_messages
            if message["type"] == "http.response.start"
        ]
        self.assertEqual(len(response_starts), 1)
        self.assertEqual(response_starts[0]["status"], 413)
        response_bodies = [
            message
            for message in sent_messages
            if message["type"] == "http.response.body"
        ]
        self.assertGreaterEqual(len(response_bodies), 1)
        self.assertFalse(response_bodies[-1].get("more_body", False))
        response_body = b"".join(
            message.get("body", b"")
            for message in response_bodies
        )
        self.assertEqual(
            json.loads(response_body.decode("utf-8")),
            {"detail": "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE"},
        )

    def test_missing_content_length_cannot_bypass_actual_limit(self) -> None:
        request = _FakeStreamingRequest([b"a" * 65_537])
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(error.exception.status_code, 413)

    def test_misleading_small_content_length_cannot_bypass_actual_limit(self) -> None:
        request = _FakeStreamingRequest([b"a" * 65_537], {"content-length": "1"})
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(error.exception.status_code, 413)

    def test_malformed_content_length_cannot_bypass_actual_limit(self) -> None:
        request = _FakeStreamingRequest([b"a" * 65_537], {"content-length": "invalid"})
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(error.exception.status_code, 413)

    def test_negative_content_length_cannot_bypass_actual_limit(self) -> None:
        request = _FakeStreamingRequest([b"a" * 65_537], {"content-length": "-1"})
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(error.exception.status_code, 413)

    def test_very_large_valid_decimal_content_length_returns_413(self) -> None:
        request = _FakeStreamingRequest([b"ok"], {"content-length": "9" * 5_000})
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main_module._read_work_order_route_release_body(request))
        self.assertEqual(error.exception.status_code, 413)

    def test_actual_oversize_http_request_never_calls_helper(self) -> None:
        body = b" " * 65_537
        self.assertEqual(len(body), 65_537)
        response, helper = self._post(body=body, headers={"content-length": "1"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_ROUTE_RELEASE_REQUEST_TOO_LARGE"})
        helper.assert_not_called()

    def test_valid_json_at_exact_size_reaches_helper(self) -> None:
        body = self._body_at_size(65_536)
        self.assertEqual(len(body), 65_536)
        response, helper = self._post(body=body)
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()

    # Strict JSON parser.

    def test_empty_body_is_400(self) -> None:
        self._assert_invalid_body(b"")

    def test_invalid_utf8_is_400(self) -> None:
        self._assert_invalid_body(b"\xff")

    def test_malformed_json_is_400(self) -> None:
        self._assert_invalid_body(b'{"release_id":')

    def test_top_level_array_is_400(self) -> None:
        self._assert_invalid_body(b"[]")

    def test_top_level_string_is_400(self) -> None:
        self._assert_invalid_body(b'"value"')

    def test_top_level_number_is_400(self) -> None:
        self._assert_invalid_body(b"12")

    def test_top_level_boolean_is_400(self) -> None:
        self._assert_invalid_body(b"true")

    def test_top_level_null_is_400(self) -> None:
        self._assert_invalid_body(b"null")

    def test_nan_is_400(self) -> None:
        self._assert_invalid_body(b'{"metadata":{"value":NaN}}')

    def test_infinity_is_400(self) -> None:
        self._assert_invalid_body(b'{"metadata":{"value":Infinity}}')

    def test_negative_infinity_is_400(self) -> None:
        self._assert_invalid_body(b'{"metadata":{"value":-Infinity}}')

    def test_duplicate_top_level_key_is_400(self) -> None:
        self._assert_invalid_body(
            b'{"release_id":"A","release_id":"B","route_code":"R","route_version":1,"released_by":"A"}'
        )

    def test_duplicate_metadata_key_is_400(self) -> None:
        self._assert_invalid_body(
            b'{"release_id":"A","route_code":"R","route_version":1,"released_by":"A","metadata":{"purpose":"A","purpose":"B"}}'
        )

    def test_deeply_nested_duplicate_key_is_400(self) -> None:
        self._assert_invalid_body(
            b'{"release_id":"A","route_code":"R","route_version":1,"released_by":"A","metadata":{"outer":{"x":1,"x":2}}}'
        )

    def test_duplicate_key_in_object_inside_metadata_list_is_400(self) -> None:
        self._assert_invalid_body(
            b'{"release_id":"A","route_code":"R","route_version":1,"released_by":"A","metadata":{"items":[{"purpose":"first","purpose":"second"}]}}'
        )

    def test_object_pairs_hook_validation_failure_is_400(self) -> None:
        with patch.object(main_module, "_route_release_json_object", side_effect=ValueError("hook")):
            self._assert_invalid_body(self._body())

    def test_recursion_error_is_400(self) -> None:
        with patch.object(main_module.json, "loads", side_effect=RecursionError("deep")):
            response, helper = self._post(body=self._body())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_ROUTE_RELEASE_REQUEST_INVALID"})
        helper.assert_not_called()

    def test_excessive_actual_json_nesting_is_400(self) -> None:
        body = (b"[" * 2_000) + b"0" + (b"]" * 2_000)
        self._assert_invalid_body(body)

    def test_invalid_body_cases_never_return_422(self) -> None:
        for body in (b"", b"[]", b'{"x":', b"\xff"):
            with self.subTest(body=body):
                response, helper = self._post(body=body)
                self.assertEqual(response.status_code, 400)
                self.assertNotEqual(response.status_code, 422)
                helper.assert_not_called()

    # Field policy and scalar validation.

    def test_release_source_client_field_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "release_source": "local_planning"}, "WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED")

    def test_mode_client_field_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "mode": "route_generated"}, "WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED")

    def test_operation_bindings_client_field_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "operation_bindings": None}, "WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED")

    def test_multiple_server_controlled_fields_are_rejected(self) -> None:
        request = {
            **self.VALID_REQUEST,
            "mode": "route_generated",
            "release_source": "local_planning",
            "operation_bindings": None,
        }
        self._assert_field_error(request, "WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED")

    def test_server_field_error_has_priority_over_unknown_field(self) -> None:
        request = {**self.VALID_REQUEST, "mode": "route_generated", "extra": True}
        self._assert_field_error(request, "WORK_ORDER_ROUTE_RELEASE_SERVER_FIELD_NOT_ALLOWED")

    def test_unknown_field_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "extra": True}, "WORK_ORDER_ROUTE_RELEASE_UNKNOWN_FIELD")

    def test_missing_release_id_uses_helper_invalid_code(self) -> None:
        request = {key: value for key, value in self.VALID_REQUEST.items() if key != "release_id"}
        self._assert_field_error(request, "RELEASE_ID_INVALID")

    def test_missing_route_code_uses_helper_invalid_code(self) -> None:
        request = {key: value for key, value in self.VALID_REQUEST.items() if key != "route_code"}
        self._assert_field_error(request, "ROUTE_CODE_INVALID")

    def test_missing_route_version_uses_required_code(self) -> None:
        request = {key: value for key, value in self.VALID_REQUEST.items() if key != "route_version"}
        self._assert_field_error(request, "ROUTE_VERSION_REQUIRED")

    def test_missing_released_by_uses_helper_invalid_code(self) -> None:
        request = {key: value for key, value in self.VALID_REQUEST.items() if key != "released_by"}
        self._assert_field_error(request, "RELEASED_BY_INVALID")

    def test_blank_release_id_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "release_id": "  "}, "RELEASE_ID_REQUIRED")

    def test_blank_route_code_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_code": "  "}, "ROUTE_CODE_REQUIRED")

    def test_blank_released_by_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "released_by": "  "}, "RELEASED_BY_REQUIRED")

    def test_wrong_release_id_type_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "release_id": 7}, "RELEASE_ID_INVALID")

    def test_wrong_route_code_type_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_code": 7}, "ROUTE_CODE_INVALID")

    def test_wrong_released_by_type_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "released_by": ["actor"]}, "RELEASED_BY_INVALID")

    def test_boolean_text_fields_are_rejected(self) -> None:
        expected_details = {
            "release_id": "RELEASE_ID_INVALID",
            "route_code": "ROUTE_CODE_INVALID",
            "released_by": "RELEASED_BY_INVALID",
        }
        for field, expected_detail in expected_details.items():
            with self.subTest(field=field):
                self._assert_field_error(
                    {**self.VALID_REQUEST, field: True},
                    expected_detail,
                )

    def test_object_text_fields_are_rejected(self) -> None:
        expected_details = {
            "release_id": "RELEASE_ID_INVALID",
            "route_code": "ROUTE_CODE_INVALID",
            "released_by": "RELEASED_BY_INVALID",
        }
        for field, expected_detail in expected_details.items():
            with self.subTest(field=field):
                self._assert_field_error(
                    {**self.VALID_REQUEST, field: {"value": "X"}},
                    expected_detail,
                )

    def test_wrong_work_order_id_type_is_rejected_by_normalizer(self) -> None:
        with self.assertRaises(HTTPException) as error:
            main_module._normalize_work_order_route_release_http_request(None, self.VALID_REQUEST)
        self.assertEqual(error.exception.detail, "WORK_ORDER_ID_INVALID")

    def test_route_version_bool_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_version": True}, "ROUTE_VERSION_INVALID")

    def test_route_version_zero_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_version": 0}, "ROUTE_VERSION_INVALID")

    def test_route_version_negative_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_version": -1}, "ROUTE_VERSION_INVALID")

    def test_route_version_string_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_version": "2"}, "ROUTE_VERSION_INVALID")

    def test_route_version_float_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "route_version": 2.0}, "ROUTE_VERSION_INVALID")

    def test_metadata_wrong_type_is_rejected(self) -> None:
        self._assert_field_error({**self.VALID_REQUEST, "metadata": []}, "RELEASE_METADATA_INVALID")

    def test_omitted_metadata_becomes_empty_object(self) -> None:
        request = {key: value for key, value in self.VALID_REQUEST.items() if key != "metadata"}
        response, helper = self._post(body=self._body(request))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_args.kwargs["metadata"], {})

    # Normalization and one-call delegation.

    def test_work_order_path_is_trimmed_and_case_preserved(self) -> None:
        response, helper = self._post(path="/api/v2/work-orders/%20Wo-Case-01%20/route-release")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_args.kwargs["work_order_id"], "Wo-Case-01")

    def test_release_id_is_trimmed_and_case_preserved(self) -> None:
        response, helper = self._post(body=self._body({**self.VALID_REQUEST, "release_id": "  Release-Case  "}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_args.kwargs["release_id"], "Release-Case")

    def test_route_code_is_trimmed_and_uppercased(self) -> None:
        response, helper = self._post(body=self._body({**self.VALID_REQUEST, "route_code": "  route_case  "}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_args.kwargs["route_code"], "ROUTE_CASE")

    def test_released_by_is_trimmed_and_case_preserved(self) -> None:
        response, helper = self._post(body=self._body({**self.VALID_REQUEST, "released_by": "  Actor-Case  "}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_args.kwargs["released_by"], "Actor-Case")

    def test_metadata_structure_is_preserved(self) -> None:
        metadata = {"nested": {"values": [1, "x", False]}, "empty": {}}
        response, helper = self._post(body=self._body({**self.VALID_REQUEST, "metadata": metadata}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_args.kwargs["metadata"], metadata)

    def test_server_controlled_helper_values_are_exact(self) -> None:
        response, helper = self._post()
        self.assertEqual(response.status_code, 200)
        kwargs = helper.call_args.kwargs
        self.assertEqual(kwargs["release_source"], "local_planning")
        self.assertEqual(kwargs["mode"], "route_generated")
        self.assertIsNone(kwargs["operation_bindings"])

    def test_helper_is_called_exactly_once(self) -> None:
        response, helper = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(helper.call_count, 1)

    def test_normalizer_does_not_mutate_request_object(self) -> None:
        request = copy.deepcopy(self.VALID_REQUEST)
        before = copy.deepcopy(request)
        normalized = main_module._normalize_work_order_route_release_http_request(" WO ", request)
        self.assertEqual(request, before)
        self.assertIs(normalized["metadata"], request["metadata"])

    def test_api_calls_no_release_pre_read_helper(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "get_work_order_route_release") as by_order,
            patch.object(main_module.mesql_v2, "get_work_order_route_release_by_id") as by_id,
            patch.object(main_module.mesql_v2, "get_work_order_release_snapshot") as snapshot,
        ):
            response, helper = self._post()
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()
        by_order.assert_not_called()
        by_id.assert_not_called()
        snapshot.assert_not_called()

    # Success envelope.

    def test_first_release_returns_200(self) -> None:
        response, _ = self._post(result=self._helper_result(released=True))
        self.assertEqual(response.status_code, 200)

    def test_first_release_adds_ok_true(self) -> None:
        response, _ = self._post(result=self._helper_result(released=True))
        self.assertIs(response.json()["ok"], True)

    def test_first_release_preserves_released_true(self) -> None:
        response, _ = self._post(result=self._helper_result(released=True))
        self.assertIs(response.json()["released"], True)

    def test_replay_returns_200(self) -> None:
        response, _ = self._post(result=self._helper_result(released=False))
        self.assertEqual(response.status_code, 200)

    def test_replay_preserves_released_false(self) -> None:
        response, _ = self._post(result=self._helper_result(released=False))
        self.assertIs(response.json()["released"], False)

    def test_success_response_key_set_is_exact(self) -> None:
        response, _ = self._post()
        self.assertEqual(
            set(response.json()),
            {"ok", "released", "release", "work_order", "operations", "bindings", "initial_queue"},
        )

    def test_success_response_has_no_data_wrapper(self) -> None:
        response, _ = self._post()
        self.assertNotIn("data", response.json())

    def test_nested_helper_snapshots_pass_through_unchanged(self) -> None:
        result = self._helper_result()
        response, _ = self._post(result=result)
        body = response.json()
        for key in ("release", "work_order", "operations", "bindings", "initial_queue"):
            self.assertEqual(body[key], result[key])

    # Error mapping.

    def test_helper_400_passes_through(self) -> None:
        error = main_module.mesql_v2.MesqlV2Error("RELEASE_ID_REQUIRED", status_code=400)
        response, helper = self._post(side_effect=error)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "RELEASE_ID_REQUIRED"})
        helper.assert_called_once()

    def test_helper_404_passes_through(self) -> None:
        error = main_module.mesql_v2.MesqlV2Error("WORK_ORDER_NOT_FOUND", status_code=404)
        response, _ = self._post(side_effect=error)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_NOT_FOUND"})

    def test_helper_409_passes_through(self) -> None:
        error = main_module.mesql_v2.MesqlV2Error("WORK_ORDER_RELEASE_QUEUE_CONFLICT", status_code=409)
        response, _ = self._post(side_effect=error)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_RELEASE_QUEUE_CONFLICT"})

    def test_helper_503_passes_through(self) -> None:
        error = main_module.mesql_v2.MesqlV2Error("DATABASE_DISABLED", status_code=503)
        response, _ = self._post(side_effect=error)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "DATABASE_DISABLED"})

    def test_generic_exception_returns_500_internal_error(self) -> None:
        response, helper = self._post(side_effect=RuntimeError("database secret"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "INTERNAL_ERROR"})
        helper.assert_called_once()

    def test_error_wire_shape_contains_only_detail(self) -> None:
        response, _ = self._post(side_effect=main_module.mesql_v2.MesqlV2Error("WORK_ORDER_NOT_FOUND", status_code=404))
        self.assertEqual(set(response.json()), {"detail"})

    def test_error_response_has_no_ok_false(self) -> None:
        response, _ = self._post(side_effect=RuntimeError("boom"))
        self.assertNotIn("ok", response.json())

    def test_error_response_has_no_error_code_envelope(self) -> None:
        response, _ = self._post(side_effect=RuntimeError("boom"))
        self.assertNotIn("error_code", response.json())

    def test_domain_failure_logs_one_sanitized_structured_outcome(self) -> None:
        secret = "DOMAIN-FAILURE-METADATA-SECRET"
        request = {
            **self.VALID_REQUEST,
            "release_id": "REL\nID",
            "route_code": "route\r code",
            "released_by": "actor\tid",
            "metadata": {"secret": secret},
        }
        error = main_module.mesql_v2.MesqlV2Error(
            "WORK_ORDER_RELEASE_QUEUE_CONFLICT",
            status_code=409,
        )
        with patch.object(main_module.logger, "info") as logged:
            response, helper = self._post(
                body=self._body(request),
                path="/api/v2/work-orders/WO%0A%0D%09ID/route-release",
                side_effect=error,
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "WORK_ORDER_RELEASE_QUEUE_CONFLICT"})
        helper.assert_called_once()
        extra = self._assert_structured_log(
            logged,
            error_code="WORK_ORDER_RELEASE_QUEUE_CONFLICT",
            released=None,
            secret=secret,
        )
        self.assertNotIn("database", repr(extra).lower())

    def test_generic_exception_uses_internal_exception_log(self) -> None:
        secret = "GENERIC-FAILURE-METADATA-SECRET"
        request = {**self.VALID_REQUEST, "metadata": {"secret": secret}}
        with patch.object(main_module.logger, "exception") as logged:
            response, helper = self._post(
                body=self._body(request),
                side_effect=RuntimeError("boom"),
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "INTERNAL_ERROR"})
        helper.assert_called_once()
        self._assert_structured_log(
            logged,
            error_code="INTERNAL_ERROR",
            released=None,
            secret=secret,
        )

    def test_metadata_and_body_values_are_absent_from_log_fields(self) -> None:
        secret = "DO-NOT-LOG-THIS-METADATA"
        request = {**self.VALID_REQUEST, "metadata": {"secret": secret}}
        with patch.object(main_module.logger, "info") as logged:
            response, _ = self._post(body=self._body(request))
        self.assertEqual(response.status_code, 200)
        self._assert_structured_log(
            logged,
            error_code=None,
            released=True,
            secret=secret,
        )

    def test_replay_logs_released_false(self) -> None:
        with patch.object(main_module.logger, "info") as logged:
            response, _ = self._post(result=self._helper_result(released=False))
        self.assertEqual(response.status_code, 200)
        self._assert_structured_log(
            logged,
            error_code=None,
            released=False,
        )

    def test_user_control_characters_are_sanitized_in_structured_log(self) -> None:
        request = {**self.VALID_REQUEST, "release_id": "REL\nID"}
        with patch.object(main_module.logger, "info") as logged:
            response, _ = self._post(body=self._body(request))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("\n", logged.call_args.kwargs["extra"]["release_id"])

    # API ownership boundaries.

    def test_progressed_replay_result_remains_released_false(self) -> None:
        result = self._helper_result(released=False)
        result["work_order"]["status"] = "completed"
        result["operations"][0]["status"] = "completed"
        result["initial_queue"]["status"] = "completed"
        response, helper = self._post(result=result)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["released"], False)
        helper.assert_called_once()

    def test_api_does_not_retry_failed_helper(self) -> None:
        response, helper = self._post(side_effect=RuntimeError("boom"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(helper.call_count, 1)

    def test_simulated_winner_and_replay_responses_remain_true_false(self) -> None:
        with patch.dict(os.environ, {main_module.WORK_ORDER_ROUTE_RELEASE_FEATURE_FLAG: "true"}, clear=False):
            with patch.object(
                main_module.mesql_v2,
                "release_work_order_to_route",
                side_effect=[self._helper_result(released=True), self._helper_result(released=False)],
            ) as helper:
                winner = self.client.post(self.PATH, content=self._body())
                replay = self.client.post(self.PATH, content=self._body())
        self.assertIs(winner.json()["released"], True)
        self.assertIs(replay.json()["released"], False)
        self.assertEqual(helper.call_count, 2)

    def test_api_adds_no_lock_or_rank_call(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "_lock_station_queue_scope_cursor") as lock,
            patch.object(main_module.mesql_v2, "_next_queue_rank") as rank,
        ):
            response, helper = self._post()
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()
        lock.assert_not_called()
        rank.assert_not_called()

    def test_api_adds_no_raw_database_or_event_outbox_call(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "database_connection") as database,
            patch.object(main_module.mesql_v2, "_insert_event") as event,
            patch.object(main_module.mesql_v2, "_insert_outbox") as outbox,
        ):
            response, helper = self._post()
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()
        database.assert_not_called()
        event.assert_not_called()
        outbox.assert_not_called()

    def test_api_adds_no_runtime_or_completion_bridge_call(self) -> None:
        with (
            patch.object(main_module.mesql_v2, "initialize_execution_state") as initialize,
            patch.object(main_module.mesql_v2, "finish_execution_step") as finish,
            patch.object(main_module.mesql_v2, "_apply_runtime_completion_bridge_cursor") as bridge,
        ):
            response, helper = self._post()
        self.assertEqual(response.status_code, 200)
        helper.assert_called_once()
        initialize.assert_not_called()
        finish.assert_not_called()
        bridge.assert_not_called()


class WorkOrderRouteReleaseRealProcessLoggingTests(unittest.TestCase):
    STRUCTURED_LOG_FIELDS = {
        "event",
        "work_order_id",
        "release_id",
        "route_code",
        "route_version",
        "released_by",
        "released",
        "error_code",
        "duration_ms",
    }

    @staticmethod
    def _reserve_loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    @staticmethod
    def _wait_for_health(process: subprocess.Popen[str], port: int) -> None:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"mes_web exited during startup: {process.returncode}")
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                connection.request("GET", "/health", headers={"Connection": "close"})
                response = connection.getresponse()
                body = json.loads(response.read().decode("utf-8"))
                connection.close()
                if response.status == 200 and body.get("status") == "ok":
                    return
            except (OSError, TimeoutError, ValueError):
                pass
            time.sleep(0.1)
        raise AssertionError("mes_web health timeout")

    @staticmethod
    def _stop_process_tree(process: subprocess.Popen[str]) -> str:
        if process.poll() is None:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                )
            else:
                process.terminate()
        try:
            return process.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate(timeout=10)[0]

    def _run_real_process_request(
        self,
        *,
        flag: str,
        order_id: str,
        body: bytes,
    ) -> tuple[int, dict, str, int, bool]:
        port = self._reserve_loopback_port()
        process: subprocess.Popen[str] | None = None
        output = ""
        temp_path_text = ""
        with tempfile.TemporaryDirectory(prefix="phase5hd2f1_route_release_") as temp_path:
            temp_path_text = temp_path
            work_orders_dir = Path(temp_path) / "work_orders"
            work_orders_dir.mkdir()
            environment = os.environ.copy()
            environment.update({
                "MES_WEB_HOST": "127.0.0.1",
                "MES_WEB_PORT": str(port),
                "MES_WEB_DB_WORK_ORDER_ROUTE_RELEASE_ENABLED": flag,
                "MES_WEB_DB_ENABLED": "false",
                "MES_WEB_DB_HOST": "127.0.0.1",
                "MES_WEB_DB_PORT": "1",
                "MES_WEB_DB_NAME": "phase5hd2f1_no_database",
                "MES_WEB_DB_USER": "phase5hd2f1",
                "MES_WEB_DB_PASSWORD": "",
                "MES_WEB_DB_MIRROR_WORK_ORDERS": "false",
                "MES_WEB_DB_FAIL_OPEN": "false",
                "MES_WEB_DB_LOG_FAILURES": "false",
                "MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS": "false",
                "MES_WEB_DB_HOOK_VISION_EVENTS": "false",
                "MES_WEB_DB_HOOK_OEE_SNAPSHOTS": "false",
                "MES_WEB_DB_HOOK_DOWNTIME_EVENTS": "false",
                "MES_WEB_DB_HOOK_MAINTENANCE_RECORDS": "false",
                "MES_WEB_DB_HOOK_QUALITY_OVERRIDES": "false",
                "MES_WEB_DB_HOOK_STATION_EVENTS": "false",
                "MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS": "false",
                "MES_WEB_DB_SHADOW_READ_WORK_ORDERS": "false",
                "MES_WEB_DB_READ_WORK_ORDERS": "false",
                "MES_WEB_DB_SHADOW_READ_DASHBOARD": "false",
                "MES_WEB_DB_READ_DASHBOARD": "false",
                "MES_WEB_EXCEL_ENABLED": "false",
                "MES_WEB_PUBLISH_ENABLED": "false",
                "MES_WEB_MANUAL_COMMAND_ENABLED": "false",
                "MES_WEB_VISION_INGEST_ENABLED": "false",
                "MES_WEB_MQTT_HOST": "127.0.0.1",
                "MES_WEB_MQTT_PORT": "9",
                "MES_WEB_MQTT_CLIENT_ID": f"phase5hd2f1-{port}",
                "MES_WEB_OEE_RUNTIME_STATE_PATH": str(Path(temp_path) / "oee.json"),
                "MES_WEB_WORK_ORDERS_DIR": str(work_orders_dir),
                "MES_WEB_FERP_IMPORT_DIR": str(work_orders_dir),
                "MES_WEB_FERP_EXPORT_PENDING_DIR": str(Path(temp_path) / "ferp_pending"),
                "MES_WEB_FERP_EXPORT_EXAMPLES_DIR": str(Path(temp_path) / "ferp_examples"),
                "MES_WEB_FERP_XLS_DIR": str(Path(temp_path) / "ferp_xls"),
                "MES_WEB_EXCEL_WORKBOOK_PATH": str(Path(temp_path) / "disabled.xlsx"),
                "PYTHONUNBUFFERED": "1",
            })
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            process = subprocess.Popen(
                [sys.executable, "-m", "mes_web"],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                start_new_session=sys.platform != "win32",
            )
            try:
                self._wait_for_health(process, port)
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request(
                    "POST",
                    f"/api/v2/work-orders/{order_id}/route-release",
                    body=body,
                    headers={"Content-Type": "application/json", "Connection": "close"},
                )
                response = connection.getresponse()
                response_body = json.loads(response.read().decode("utf-8"))
                status = response.status
                connection.close()
            finally:
                output = self._stop_process_tree(process)

            deadline = time.monotonic() + 5.0
            listener_absent = False
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        pass
                except OSError:
                    listener_absent = True
                    break
                time.sleep(0.05)
            self.assertTrue(listener_absent)
            self.assertIsNotNone(process.poll())
        return status, response_body, output, port, not Path(temp_path_text).exists()

    def _structured_events(self, output: str) -> list[dict]:
        events: list[dict] = []
        for line in output.splitlines():
            try:
                candidate = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(candidate, dict) and candidate.get("event") == "work_order_route_release_request":
                events.append(candidate)
        return events

    def test_logging_configuration_is_idempotent_and_machine_readable(self) -> None:
        logger = main_module.logger
        original = (logger.level, logger.disabled, logger.propagate, list(logger.handlers))
        try:
            logger.handlers.clear()
            main_module._configure_work_order_route_release_logging()
            main_module._configure_work_order_route_release_logging()
            marked = [
                handler
                for handler in logger.handlers
                if handler.name == main_module.WORK_ORDER_ROUTE_RELEASE_LOG_HANDLER_MARKER
            ]
            self.assertEqual(len(marked), 1)
            record = logging.LogRecord(logger.name, logging.INFO, __file__, 1, "ignored", (), None)
            for key, value in {
                "event": "work_order_route_release_request",
                "work_order_id": "WO-Ü",
                "release_id": None,
                "route_code": None,
                "route_version": None,
                "released_by": None,
                "released": None,
                "error_code": "WORK_ORDER_ROUTE_RELEASE_DISABLED",
                "duration_ms": 0.25,
            }.items():
                setattr(record, key, value)
            rendered = json.loads(marked[0].formatter.format(record))
            self.assertEqual(list(rendered), list(main_module.WORK_ORDER_ROUTE_RELEASE_LOG_FIELDS))
            self.assertEqual(rendered["work_order_id"], "WO-Ü")
            self.assertEqual(main_module._route_release_log_text("A\ud800B"), "A\ufffdB")
        finally:
            logger.handlers[:] = original[3]
            logger.setLevel(original[0])
            logger.disabled = original[1]
            logger.propagate = original[2]

    def test_exception_diagnostic_is_safe_bounded_and_not_a_duplicate_event(self) -> None:
        class _SqlStateError(RuntimeError):
            sqlstate = "23505"

        inner = _SqlStateError("INNER_SECRET")
        outer = RuntimeError("OUTER_SECRET")
        outer.__cause__ = inner
        stream = io.StringIO()
        handler = main_module._WorkOrderRouteReleaseJsonHandler(stream)
        handler.setFormatter(main_module._WorkOrderRouteReleaseJsonFormatter())
        record = logging.LogRecord(
            main_module.logger.name,
            logging.ERROR,
            __file__,
            1,
            "work_order_route_release_request",
            (),
            (type(outer), outer, None),
        )
        for key, value in {
            "event": "work_order_route_release_request",
            "work_order_id": "WO-001",
            "release_id": "REL-001",
            "route_code": "ROUTE_BOX_PACKAGING_V2",
            "route_version": 2,
            "released_by": "ACTOR",
            "released": None,
            "error_code": "INTERNAL_ERROR",
            "duration_ms": 1.0,
        }.items():
            setattr(record, key, value)
        handler.emit(record)
        lines = [json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["event"], "work_order_route_release_request")
        self.assertNotIn("event", lines[1])
        self.assertEqual(
            lines[1],
            {
                "diagnostic": "work_order_route_release_internal_error",
                "exception_chain": ["RuntimeError", "_SqlStateError"],
                "sqlstate": "23505",
            },
        )
        self.assertNotIn("INNER_SECRET", stream.getvalue())
        self.assertNotIn("OUTER_SECRET", stream.getvalue())

    def test_real_process_disabled_request_emits_one_structured_event(self) -> None:
        secret = "D2F1_DISABLED_BODY_MUST_NOT_APPEAR"
        status, response, output, _, temp_removed = self._run_real_process_request(
            flag="false",
            order_id="D2F1-LOG-WO",
            body=json.dumps({"metadata": {"secret": secret}}).encode("utf-8"),
        )
        self.assertEqual(status, 503)
        self.assertEqual(response, {"detail": "WORK_ORDER_ROUTE_RELEASE_DISABLED"})
        events = self._structured_events(output)
        self.assertEqual(len(events), 1)
        self.assertEqual(set(events[0]), self.STRUCTURED_LOG_FIELDS)
        self.assertEqual(events[0]["work_order_id"], "D2F1-LOG-WO")
        self.assertIsNone(events[0]["release_id"])
        self.assertIsNone(events[0]["route_code"])
        self.assertIsNone(events[0]["route_version"])
        self.assertIsNone(events[0]["released_by"])
        self.assertIsNone(events[0]["released"])
        self.assertEqual(events[0]["error_code"], "WORK_ORDER_ROUTE_RELEASE_DISABLED")
        self.assertGreaterEqual(events[0]["duration_ms"], 0)
        self.assertNotIn(secret, output)
        self.assertTrue(temp_removed)

    def test_real_process_enabled_db_disabled_emits_one_sanitized_event(self) -> None:
        secret_key = "secret_probe"
        secret_value = "MUST_NOT_APPEAR_IN_LOG"
        request = {
            "release_id": "D2F1-LOG-RELEASE",
            "route_code": "ROUTE_BOX_PACKAGING_V2",
            "route_version": 2,
            "released_by": "D2F1_LOCAL_PLANNER",
            "metadata": {secret_key: secret_value},
        }
        status, response, output, _, temp_removed = self._run_real_process_request(
            flag="true",
            order_id="D2F1-LOG-WO",
            body=json.dumps(request, separators=(",", ":")).encode("utf-8"),
        )
        self.assertEqual(status, 503)
        self.assertEqual(response, {"detail": "DATABASE_DISABLED"})
        events = self._structured_events(output)
        self.assertEqual(len(events), 1)
        self.assertEqual(set(events[0]), self.STRUCTURED_LOG_FIELDS)
        self.assertEqual(events[0]["work_order_id"], "D2F1-LOG-WO")
        self.assertEqual(events[0]["release_id"], "D2F1-LOG-RELEASE")
        self.assertEqual(events[0]["route_code"], "ROUTE_BOX_PACKAGING_V2")
        self.assertEqual(events[0]["route_version"], 2)
        self.assertEqual(events[0]["released_by"], "D2F1_LOCAL_PLANNER")
        self.assertIsNone(events[0]["released"])
        self.assertEqual(events[0]["error_code"], "DATABASE_DISABLED")
        self.assertGreaterEqual(events[0]["duration_ms"], 0)
        self.assertNotIn(secret_key, output)
        self.assertNotIn(secret_value, output)
        self.assertNotIn("MES_WEB_DB_PASSWORD", output)
        self.assertTrue(temp_removed)


if __name__ == "__main__":
    unittest.main()
