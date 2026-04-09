from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from mes_web import __main__


class MainModuleTests(unittest.TestCase):
    def test_windows_uses_selector_event_loop_policy(self) -> None:
        selector_policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        proactor_policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if selector_policy_cls is None:
            self.skipTest("Windows selector policy is not available")

        current_policy = proactor_policy_cls() if proactor_policy_cls is not None else object()
        with (
            patch("mes_web.__main__.sys.platform", "win32"),
            patch("mes_web.__main__.asyncio.get_event_loop_policy", return_value=current_policy),
            patch("mes_web.__main__.asyncio.set_event_loop_policy") as set_policy,
        ):
            __main__._configure_event_loop_policy()

        set_policy.assert_called_once()
        self.assertIsInstance(set_policy.call_args.args[0], selector_policy_cls)

    def test_non_windows_keeps_current_event_loop_policy(self) -> None:
        with (
            patch("mes_web.__main__.sys.platform", "linux"),
            patch("mes_web.__main__.asyncio.get_event_loop_policy") as get_policy,
            patch("mes_web.__main__.asyncio.set_event_loop_policy") as set_policy,
        ):
            __main__._configure_event_loop_policy()

        get_policy.assert_not_called()
        set_policy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
