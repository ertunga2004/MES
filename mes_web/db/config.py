from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import AppConfig


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    enabled: bool
    host: str
    port: int
    dbname: str
    user: str
    password: str
    sslmode: str
    connect_timeout_sec: int

    @classmethod
    def from_app_config(cls, config: AppConfig) -> "DatabaseConfig":
        return cls(
            enabled=bool(config.db_enabled),
            host=str(config.db_host or "mes_postgres"),
            port=int(config.db_port),
            dbname=str(config.db_name or "mes"),
            user=str(config.db_user or "mes"),
            password=str(config.db_password or ""),
            sslmode=str(config.db_sslmode or "disable"),
            connect_timeout_sec=max(int(config.db_connect_timeout_sec), 1),
        )

    def connection_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout_sec,
        }
        if self.password:
            kwargs["password"] = self.password
        return kwargs

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": "<set>" if self.password else "",
            "sslmode": self.sslmode,
            "connect_timeout_sec": self.connect_timeout_sec,
        }


def build_database_config(config: AppConfig) -> DatabaseConfig:
    return DatabaseConfig.from_app_config(config)
