from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..config import AppConfig
from .config import DatabaseConfig, build_database_config


@dataclass(slots=True)
class DatabaseWriteResult:
    attempted: bool
    success: bool
    skipped: bool
    reason: str
    operation: str
    error_type: str | None = None


def _coerce_database_config(config: AppConfig | DatabaseConfig) -> DatabaseConfig:
    if isinstance(config, DatabaseConfig):
        return config
    return build_database_config(config)


def safe_db_write(
    config: AppConfig | DatabaseConfig,
    operation: str,
    writer: Callable[[], Any],
    *,
    dry_run: bool = False,
    fail_open: bool | None = None,
    logger: logging.Logger | None = None,
) -> DatabaseWriteResult:
    is_fail_open = False
    if fail_open is not None:
        is_fail_open = fail_open
    elif isinstance(config, AppConfig):
        is_fail_open = config.db_fail_open

    database_config = _coerce_database_config(config)

    if not database_config.enabled:
        return DatabaseWriteResult(
            attempted=False,
            success=False,
            skipped=True,
            reason="db_disabled",
            operation=operation,
        )

    if dry_run:
        return DatabaseWriteResult(
            attempted=False,
            success=False,
            skipped=True,
            reason="dry_run",
            operation=operation,
        )

    try:
        writer()
        return DatabaseWriteResult(
            attempted=True,
            success=True,
            skipped=False,
            reason="success",
            operation=operation,
        )
    except Exception as exc:
        if logger:
            logger.error("DB WRITE ERROR [%s]: %s", operation, exc, exc_info=exc)
        
        if is_fail_open:
            return DatabaseWriteResult(
                attempted=True,
                success=False,
                skipped=False,
                reason="error_fail_open",
                operation=operation,
                error_type=type(exc).__name__,
            )
        raise
