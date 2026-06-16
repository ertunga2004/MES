from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.mqtt_runtime import MqttIngestClient


class _Store:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def set_mqtt_connection(self, _connected: bool) -> None:
        return None

    def apply_log_line(self, *_args, **_kwargs) -> None:
        self.calls.append("log")

    def refresh_oee_runtime_state(self, *_args, **_kwargs) -> bool:
        self.calls.append("refresh")
        return True

    def append_system_log(self, *_args, **_kwargs) -> None:
        return None


class _ExcelSink:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def record_mega_log(self, *_args, **_kwargs) -> None:
        self.calls.append("excel_log")

    def record_work_order_state(self, *_args, **_kwargs) -> None:
        self.calls.append("excel_work_orders")


class _OeeManager:
    def __init__(self, state: dict) -> None:
        self.state = state

    def apply_mega_log(self, *_args, **_kwargs) -> bool:
        return True

    def read_state(self) -> dict:
        return self.state


class MqttRuntimeWorkOrderTransitionTests(unittest.TestCase):
    def test_mega_log_syncs_work_order_transition_before_store_refresh(self) -> None:
        calls: list[str] = []
        state = {
            "workOrders": {
                "activeOrderId": "WO-1",
                "ordersById": {"WO-1": {"orderId": "WO-1", "status": "pending_approval"}},
            }
        }
        config = AppConfig(db_enabled=True, db_hook_work_order_transitions=True)
        client = MqttIngestClient(
            config,
            _Store(calls),
            excel_sink=_ExcelSink(calls),
            oee_state_manager=_OeeManager(state),
        )
        message = SimpleNamespace(topic=config.topics["logs"], payload=b"ITEM_DONE")

        def fake_writer(_config, _state, **kwargs):
            calls.append(f"db:{kwargs.get('event_type')}")
            return SimpleNamespace(reason="written")

        with patch("mes_web.mqtt_runtime.mirror_work_order_transition_from_state", side_effect=fake_writer):
            client._on_message(None, None, message)

        self.assertIn("db:runtime_state_changed", calls)
        self.assertLess(calls.index("db:runtime_state_changed"), calls.index("refresh"))
        self.assertIn("excel_work_orders", calls)


if __name__ == "__main__":
    unittest.main()
