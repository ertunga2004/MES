from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mes_web.config import AppConfig
from mes_web.runtime import RuntimeService, SnapshotHub
from mes_web.store import DashboardStore


class RuntimeServiceTests(unittest.TestCase):
    def test_startup_records_work_order_state_without_name_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "oee_runtime_state.json"
            work_orders_dir = Path(temp_dir) / "work_orders"
            state_path.write_text("{}", encoding="utf-8")
            work_orders_dir.mkdir(parents=True, exist_ok=True)

            with patch.dict(
                os.environ,
                {
                    "MES_WEB_OEE_RUNTIME_STATE_PATH": str(state_path),
                    "MES_WEB_WORK_ORDERS_DIR": str(work_orders_dir),
                },
                clear=False,
            ):
                config = AppConfig.from_env()
                store = DashboardStore(config)
                hub = SnapshotHub(store, coalesce_ms=config.ws_coalesce_ms)
                service = RuntimeService(config, store, hub)
                calls: list[tuple[dict[str, object], str]] = []
                service.excel_sink.start = lambda: None
                service.excel_sink.stop = lambda: None
                service.excel_sink.record_work_order_state = lambda state, stamp: calls.append((state, stamp))
                service.mqtt_client.start = lambda: True
                service.mqtt_client.stop = lambda: None

                async def run() -> None:
                    await service.start()
                    await service.stop()

                asyncio.run(run())

            self.assertEqual(len(calls), 1)
            self.assertIsInstance(calls[0][0], dict)
            self.assertTrue(calls[0][1])


if __name__ == "__main__":
    unittest.main()
