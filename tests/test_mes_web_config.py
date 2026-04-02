from __future__ import annotations

import re
import unittest

from mes_web.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_live_defaults_are_enabled(self) -> None:
        config = AppConfig()

        self.assertEqual(config.ui_phase, "live_ops")
        self.assertEqual(config.command_mode, "full_live")
        self.assertTrue(config.vision_ui_visible)

    def test_default_excel_workbook_path_targets_logs_directory_with_dated_name(self) -> None:
        config = AppConfig()
        path = config.excel_workbook_path

        self.assertEqual(path.parent.name, "logs")
        self.assertRegex(path.name, r"^MES_Konveyor_Veritabani_\d{2}-\d{2}-\d{4}\.xlsx$")


if __name__ == "__main__":
    unittest.main()
