-- Roll back the duplicate-safe work order transition event key.
-- The table is not dropped because it may have been created by 001_initial_mes_schema.sql.

DROP INDEX IF EXISTS mes.ux_mes_work_order_events_external_ref;
