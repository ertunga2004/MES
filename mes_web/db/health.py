from __future__ import annotations

from typing import Any

from ..config import AppConfig
from .config import DatabaseConfig, build_database_config
from .connection import DatabaseDriverMissingError, database_connection


def _coerce_database_config(config: AppConfig | DatabaseConfig) -> DatabaseConfig:
    if isinstance(config, DatabaseConfig):
        return config
    return build_database_config(config)


def check_database_health(config: AppConfig | DatabaseConfig) -> dict[str, Any]:
    database_config = _coerce_database_config(config)
    base = database_config.redacted_dict()
    if not database_config.enabled:
        return {
            "status": "disabled",
            "database": base,
        }

    try:
        with database_connection(database_config) as connection:
            if connection is None:
                return {
                    "status": "disabled",
                    "database": base,
                }
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except DatabaseDriverMissingError:
        return {
            "status": "driver_missing",
            "database": base,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "database": base,
            "error_type": type(exc).__name__,
        }

    return {
        "status": "ok",
        "database": base,
    }
