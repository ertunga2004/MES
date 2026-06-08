from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mes_web.config import AppConfig
from mes_web.db.config import build_database_config
from mes_web.db.connection import DatabaseDriverMissingError, database_connection


def _print_table_names(table_names: list[str]) -> None:
    print("mes schema tables:")
    for table_name in table_names:
        print(f"- {table_name}")


def main() -> int:
    app_config = AppConfig.from_env()
    db_config = build_database_config(app_config)

    if not db_config.enabled:
        print("DB disabled by MES_WEB_DB_ENABLED=false")
        return 0

    print(
        "Checking MES PostgreSQL connection "
        f"host={db_config.host} port={db_config.port} dbname={db_config.dbname} user={db_config.user}"
    )

    try:
        with database_connection(db_config) as connection:
            if connection is None:
                print("DB connection was not opened.", file=sys.stderr)
                return 1
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_schema()")
                current_database, current_schema = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT count(*) AS table_count
                    FROM information_schema.tables
                    WHERE table_schema = 'mes'
                    """
                )
                table_count = int(cursor.fetchone()[0])

                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'mes'
                    ORDER BY table_name
                    """
                )
                table_names = [str(row[0]) for row in cursor.fetchall()]
    except DatabaseDriverMissingError as exc:
        print(f"DB driver missing: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"DB connection check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"current_database: {current_database}")
    print(f"current_schema: {current_schema}")
    print(f"mes_table_count: {table_count}")
    _print_table_names(table_names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
