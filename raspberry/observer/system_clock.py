from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any


def should_apply_system_clock(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    value = payload.get("set_system_clock")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SystemClockApplyResult:
    requested: bool
    attempted: bool
    success: bool
    command: str | None = None
    message: str | None = None


class SystemClockSetter:
    def __init__(self, command: str | None = None) -> None:
        configured = command if command is not None else os.environ.get("MES_OBSERVER_SET_CLOCK_CMD", "")
        self.command = str(configured or "").strip()

    def apply(self, timestamp: str) -> SystemClockApplyResult:
        if not self.command:
            return SystemClockApplyResult(
                requested=True,
                attempted=False,
                success=False,
                message="MES_OBSERVER_SET_CLOCK_CMD is not configured",
            )

        try:
            command_parts = shlex.split(self.command)
        except ValueError as exc:
            return SystemClockApplyResult(
                requested=True,
                attempted=False,
                success=False,
                command=self.command,
                message=f"invalid clock command: {exc}",
            )

        if not command_parts:
            return SystemClockApplyResult(
                requested=True,
                attempted=False,
                success=False,
                command=self.command,
                message="clock command is empty",
            )

        try:
            completed = subprocess.run(
                [*command_parts, timestamp],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            return SystemClockApplyResult(
                requested=True,
                attempted=True,
                success=False,
                command=self.command,
                message=str(exc),
            )

        message = (completed.stdout or completed.stderr or "").strip() or "system clock updated"
        return SystemClockApplyResult(
            requested=True,
            attempted=True,
            success=True,
            command=self.command,
            message=message,
        )
