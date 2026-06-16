from __future__ import annotations

from mes_web.config import AppConfig
from mes_web.db.config import build_database_config
from mes_web.db.health import check_database_health


DB_ENV_NAMES = (
    "MES_WEB_DB_ENABLED",
    "MES_WEB_DB_HOST",
    "MES_WEB_DB_PORT",
    "MES_WEB_DB_NAME",
    "MES_WEB_DB_USER",
    "MES_WEB_DB_PASSWORD",
    "MES_WEB_DB_SSLMODE",
    "MES_WEB_DB_CONNECT_TIMEOUT_SEC",
    "MES_WEB_DB_MIRROR_WORK_ORDERS",
    "MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS",
    "MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS_DRY_RUN",
)


def test_db_is_disabled_by_default(monkeypatch) -> None:
    for name in DB_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    config = AppConfig.from_env()
    database_config = build_database_config(config)

    assert config.db_enabled is False
    assert database_config.enabled is False
    assert database_config.host == "mes_postgres"
    assert database_config.port == 5432
    assert database_config.dbname == "mes"
    assert database_config.user == "mes"
    assert database_config.password == ""
    assert database_config.sslmode == "disable"
    assert database_config.connect_timeout_sec == 2
    assert config.db_mirror_work_orders is False
    assert config.db_hook_work_order_transitions is False
    assert config.db_hook_work_order_transitions_dry_run is False


def test_db_env_values_are_parsed_without_connecting(monkeypatch) -> None:
    monkeypatch.setenv("MES_WEB_DB_ENABLED", "true")
    monkeypatch.setenv("MES_WEB_DB_HOST", "localhost")
    monkeypatch.setenv("MES_WEB_DB_PORT", "5433")
    monkeypatch.setenv("MES_WEB_DB_NAME", "mes_test")
    monkeypatch.setenv("MES_WEB_DB_USER", "mes_user")
    monkeypatch.setenv("MES_WEB_DB_PASSWORD", "secret")
    monkeypatch.setenv("MES_WEB_DB_SSLMODE", "prefer")
    monkeypatch.setenv("MES_WEB_DB_CONNECT_TIMEOUT_SEC", "7")
    monkeypatch.setenv("MES_WEB_DB_MIRROR_WORK_ORDERS", "true")
    monkeypatch.setenv("MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS", "true")
    monkeypatch.setenv("MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS_DRY_RUN", "true")

    config = AppConfig.from_env()
    database_config = build_database_config(config)
    kwargs = database_config.connection_kwargs()

    assert database_config.enabled is True
    assert kwargs == {
        "host": "localhost",
        "port": 5433,
        "dbname": "mes_test",
        "user": "mes_user",
        "sslmode": "prefer",
        "connect_timeout": 7,
        "password": "secret",
    }
    assert database_config.redacted_dict()["password"] == "<set>"
    assert config.db_mirror_work_orders is True
    assert config.db_hook_work_order_transitions is True
    assert config.db_hook_work_order_transitions_dry_run is True


def test_db_health_disabled_does_not_require_driver_or_connection(monkeypatch) -> None:
    monkeypatch.setenv("MES_WEB_DB_ENABLED", "false")

    result = check_database_health(AppConfig.from_env())

    assert result["status"] == "disabled"
    assert result["database"]["enabled"] is False
