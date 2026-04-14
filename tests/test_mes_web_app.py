from __future__ import annotations

import unittest
from unittest.mock import patch

from mes_web.windows_asyncio import install_windows_connection_reset_filter


class _FakeLoop:
    def __init__(self) -> None:
        self.handler = None
        self.default_context = None
        self.previous_context = None

    def get_exception_handler(self):
        def previous_handler(loop, context):
            self.previous_context = context

        return previous_handler

    def set_exception_handler(self, handler) -> None:
        self.handler = handler

    def default_exception_handler(self, context) -> None:
        self.default_context = context


class _FakeConnectionResetError(ConnectionResetError):
    pass


class AppLoopFilterTests(unittest.TestCase):
    def test_windows_connection_reset_filter_swallows_proactor_close_noise(self) -> None:
        loop = _FakeLoop()
        with (
            patch("mes_web.windows_asyncio.sys.platform", "win32"),
            patch("mes_web.windows_asyncio.asyncio.get_running_loop", return_value=loop),
        ):
            install_windows_connection_reset_filter()

        self.assertIsNotNone(loop.handler)
        error = _FakeConnectionResetError("socket reset")
        error.winerror = 10054
        loop.handler(
            loop,
            {
                "exception": error,
                "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
                "handle": object(),
            },
        )

        self.assertIsNone(loop.previous_context)
        self.assertIsNone(loop.default_context)

    def test_windows_connection_reset_filter_keeps_other_errors_visible(self) -> None:
        loop = _FakeLoop()
        with (
            patch("mes_web.windows_asyncio.sys.platform", "win32"),
            patch("mes_web.windows_asyncio.asyncio.get_running_loop", return_value=loop),
        ):
            install_windows_connection_reset_filter()

        self.assertIsNotNone(loop.handler)
        loop.handler(
            loop,
            {
                "exception": RuntimeError("boom"),
                "message": "Exception in callback something_else()",
                "handle": object(),
            },
        )

        self.assertIsNotNone(loop.previous_context)


if __name__ == "__main__":
    unittest.main()
