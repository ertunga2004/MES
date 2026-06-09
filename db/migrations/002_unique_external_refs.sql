CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_production_completions_external_ref
ON mes.production_completions (external_ref)
WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_mes_vision_events_external_ref
ON mes.vision_events (external_ref)
WHERE external_ref IS NOT NULL AND btrim(external_ref) <> '';
