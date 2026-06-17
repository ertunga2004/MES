from __future__ import annotations

"""Small source-of-truth boundary map for the SQL MVP cutover path.

This is intentionally descriptive. It keeps DB ownership decisions visible
without forcing a schema redesign while runtime fallback still protects MVP ops.
"""

DB_SOURCE_OF_TRUTH = frozenset(
    {
        "mes.work_orders",
        "mes.work_order_events",
        "mes.package_component_wip",
    }
)

DB_READINESS_NEXT = frozenset(
    {
        "mes.station_queue",
        "mes.package_sessions",
    }
)

RUNTIME_FALLBACK = frozenset(
    {
        "dashboard transient snapshot",
        "websocket/kiosk snapshot",
        "operator ui state",
        "shift runtime state",
    }
)

WORK_ORDER_DB_READ_FALLBACKS = frozenset(
    {
        "db_disabled",
        "read_flag_disabled",
        "db_error",
        "db_empty",
        "db_runtime_active_drift",
    }
)
