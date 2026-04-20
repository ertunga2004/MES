from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any


def install_windows_connection_reset_filter() -> None:
    if sys.platform != "win32":
        return
    loop = asyncio.get_running_loop()
    if getattr(loop, "_mes_windows_reset_filter", False):
        return
    previous_handler = loop.get_exception_handler()

    def is_benign_windows_socket_error(exception: BaseException | None, *, message: str = "", handle_text: str = "") -> bool:
        combined = f"{message} {handle_text}".lower()
        winerror = getattr(exception, "winerror", None)
        if (
            isinstance(exception, ConnectionResetError)
            and winerror == 10054
            and "_proactorbasepipetransport._call_connection_lost" in combined
        ):
            return True
        if isinstance(exception, OSError) and winerror == 121:
            if any(token in combined for token in ("_loop_reading", "finish_socket_func", "data transfer failed", "websocket")):
                return True
        return False

    def exception_handler(active_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exception = context.get("exception")
        handle = context.get("handle")
        message = str(context.get("message") or "")
        handle_text = repr(handle) if handle is not None else ""
        if is_benign_windows_socket_error(exception, message=message, handle_text=handle_text):
            return
        if previous_handler is not None:
            previous_handler(active_loop, context)
            return
        active_loop.default_exception_handler(context)

    loop.set_exception_handler(exception_handler)
    if not getattr(loop, "_mes_windows_socket_log_filter", False):
        class _BenignWindowsSocketLogFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                exception: BaseException | None = None
                if record.exc_info and len(record.exc_info) >= 2:
                    exc_candidate = record.exc_info[1]
                    if isinstance(exc_candidate, BaseException):
                        exception = exc_candidate
                message = ""
                try:
                    message = record.getMessage()
                except Exception:
                    message = str(record.msg or "")
                return not is_benign_windows_socket_error(exception, message=message)

        socket_log_filter = _BenignWindowsSocketLogFilter()
        for logger_name in ("websockets.server", "websockets.protocol", "websockets.legacy.protocol", "uvicorn.error"):
            logging.getLogger(logger_name).addFilter(socket_log_filter)
        setattr(loop, "_mes_windows_socket_log_filter", True)
    setattr(loop, "_mes_windows_reset_filter", True)
