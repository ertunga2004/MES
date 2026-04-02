from __future__ import annotations

import unittest

from mes_web.command_policy import is_local_only_command


class CommandPolicyTests(unittest.TestCase):
    def test_reset_counts_is_local_only(self) -> None:
        self.assertTrue(is_local_only_command("preset", "__reset_counts__"))

    def test_other_preset_is_not_local_only(self) -> None:
        self.assertFalse(is_local_only_command("preset", "start"))

    def test_manual_command_is_not_local_only(self) -> None:
        self.assertFalse(is_local_only_command("manual", "__reset_counts__"))


if __name__ == "__main__":
    unittest.main()
