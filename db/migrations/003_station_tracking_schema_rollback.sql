-- Rollback for F-STA-B Station Tracking Migration Preparation.
--
-- This rollback removes the station event schema artifacts from
-- 003_station_tracking_schema.sql. It intentionally does not drop mes.stations
-- because that table is part of 001_initial_mes_schema.sql and may contain
-- existing master data.

DROP TABLE IF EXISTS mes.item_station_events;

DELETE FROM mes.stations
WHERE station_code IN ('ASSEMBLY_01', 'PACKAGING_01')
  AND source_file = '003_station_tracking_schema'
  AND external_ref IN ('station:ASSEMBLY_01', 'station:PACKAGING_01');

ALTER TABLE mes.stations
    DROP CONSTRAINT IF EXISTS uq_mes_stations_station_code;
