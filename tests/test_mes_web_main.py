from __future__ import annotations

import asyncio
import builtins
from types import ModuleType, SimpleNamespace
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

    def test_main_configures_windows_event_loop_before_importing_runtime(self) -> None:
        fake_uvicorn = ModuleType("uvicorn")
        fake_app_module = ModuleType("mes_web.app")
        fake_app_module.app = object()
        fake_app_module.config = SimpleNamespace(host="127.0.0.1", port=8080)
        call_order: list[str] = []
        configured = {"done": False}
        real_import = builtins.__import__

        def fake_run(*args, **kwargs) -> None:
            call_order.append("run")

        def fake_configure() -> None:
            configured["done"] = True
            call_order.append("configure")

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "uvicorn" and level == 0:
                self.assertTrue(configured["done"])
                call_order.append("import_uvicorn")
                fake_uvicorn.run = fake_run
                return fake_uvicorn
            if name == "app" and level == 1:
                self.assertTrue(configured["done"])
                call_order.append("import_app")
                return fake_app_module
            return real_import(name, globals, locals, fromlist, level)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch("mes_web.__main__._configure_event_loop_policy", side_effect=fake_configure),
        ):
            __main__.main()

        self.assertEqual(call_order, ["configure", "import_uvicorn", "import_app", "run"])


if __name__ == "__main__":
    unittest.main()
