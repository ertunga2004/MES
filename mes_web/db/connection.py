from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ..config import AppConfig
from .config import DatabaseConfig, build_database_config


class DatabaseDriverMissingError(RuntimeError):
    pass


def _coerce_database_config(config: AppConfig | DatabaseConfig) -> DatabaseConfig:
    if isinstance(config, DatabaseConfig):
        return config
    return build_database_config(config)


def _import_psycopg() -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise DatabaseDriverMissingError("psycopg is not installed") from exc
    return psycopg


def open_database_connection(config: AppConfig | DatabaseConfig) -> Any | None:
    database_config = _coerce_database_config(config)
    if not database_config.enabled:
        return None
    psycopg = _import_psycopg()
    return psycopg.connect(**database_config.connection_kwargs(), autocommit=True)


@contextmanager
def database_connection(config: AppConfig | DatabaseConfig) -> Iterator[Any | None]:
    connection = open_database_connection(config)
    try:
        yield connection
    finally:
        if connection is not None:
            connection.close()
