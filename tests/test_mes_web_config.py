from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

from mes_web.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_live_defaults_are_enabled(self) -> None:
        config = AppConfig()

        self.assertEqual(config.ui_phase, "live_ops")
        self.assertEqual(config.command_mode, "full_live")
        self.assertTrue(config.vision_ui_visible)

    def test_default_mqtt_client_id_is_unique_to_process(self) -> None:
        config = AppConfig()

        self.assertRegex(config.mqtt_client_id, r"^mes-web-live-[A-Za-z0-9_-]+-\d+$")
        self.assertEqual(config.mqtt_offline_grace_sec, 5)

    def test_env_can_override_mqtt_client_id_and_offline_grace(self) -> None:
        with patch.dict(
            os.environ,
            {"MES_WEB_MQTT_CLIENT_ID": "fixed-test-client", "MES_WEB_MQTT_OFFLINE_GRACE_SEC": "9"},
            clear=False,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.mqtt_client_id, "fixed-test-client")
        self.assertEqual(config.mqtt_offline_grace_sec, 9)

    def test_default_excel_workbook_path_targets_logs_directory_with_dated_name(self) -> None:
        config = AppConfig()
        path = config.excel_workbook_path

        self.assertEqual(path.parent.name, "logs")
        self.assertRegex(path.name, r"^MES_Konveyor_Veritabani_\d{2}-\d{2}-\d{4}\.xlsx$")

    def test_default_work_order_source_prefers_ferp_import_folder(self) -> None:
        config = AppConfig()

        self.assertEqual(config.ferp_import_dir.name, "ferp_import")
        self.assertEqual(config.work_orders_dir, config.ferp_import_dir)

    def test_work_order_source_env_override_wins_over_ferp_import_default(self) -> None:
        with patch.dict(os.environ, {"MES_WEB_WORK_ORDERS_DIR": "C:/tmp/mes-work-orders"}, clear=False):
            config = AppConfig.from_env()
            self.assertEqual(str(config.work_orders_dir).replace("\\", "/"), "C:/tmp/mes-work-orders")


if __name__ == "__main__":
    unittest.main()
