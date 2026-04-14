from __future__ import annotations

import asyncio
import sys
from typing import Any


def install_windows_connection_reset_filter() -> None:
    if sys.platform != "win32":
        return
    loop = asyncio.get_running_loop()
    if getattr(loop, "_mes_windows_reset_filter", False):
        return
    previous_handler = loop.get_exception_handler()

    def exception_handler(active_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exception = context.get("exception")
        handle = context.get("handle")
        message = str(context.get("message") or "")
        handle_text = repr(handle) if handle is not None else ""
        if (
            isinstance(exception, ConnectionResetError)
            and getattr(exception, "winerror", None) == 10054
            and "_ProactorBasePipeTransport._call_connection_lost" in f"{message} {handle_text}"
        ):
            return
        if previous_handler is not None:
            previous_handler(active_loop, context)
            return
        active_loop.default_exception_handler(context)

    loop.set_exception_handler(exception_handler)
    setattr(loop, "_mes_windows_reset_filter", True)
