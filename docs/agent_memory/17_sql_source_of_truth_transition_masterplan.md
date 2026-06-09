# MES SQL Source-of-Truth Transition Masterplan v1.2

## 1. Purpose
MES PostgreSQL geçişi için detaylı ve güvenli mimari geçiş masterplanı.

## 2. E5F Validated Checkpoint
- `mes.work_orders` = 6, verify clean
- `mes.production_completions` = 8, verify clean
- `mes.vision_events` = 43, verify clean
- PostgreSQL henüz source-of-truth değil
- Runtime DB read yok
- Runtime JSON/Excel/FERP/MQTT source-of-truth olarak çalışıyor

## 3. Non-Negotiable Transition Principles
- Big bang geçiş yok
- Feature flag şart
- DB write hook ve DB read aynı fazda yok
- Migration ve runtime hook aynı fazda yok
- Verify olmadan apply yok
- `docker compose down -v` yok
- Mirror/verify scriptleri korunacak

## 4. Claude Review Corrections
- `mes.production_completions` ve `mes.vision_events` tablolarında `UNIQUE(external_ref)` yok. Bu yüzden canlı hook'lardan önce F1E compatibility report ve F1F UNIQUE migration planlanmalı.
- Current mirror scripts manual SELECT existing_refs + insert/update kullanıyor; live concurrency için yeterli değil
- `production_count` MQTT topic’i yok
- Production completion source = `oee_state.py` completion transition / completionLog / itemsById
- Vision live hook `apply_vision_event` returned payload kullanmalı. Natural key kuralı:
  - event_key varsa external_ref = event_key
  - yoksa external_ref = vision_track_id + event_type + detected_at
  - vision_track_id tek başına key değil
- Canonical runtime state path netleştirilmeli

## 5. Revised Safe Phase Sequence
- F0 masterplan v1.2 documentation
- F1A feature flag matrix documentation
- F1B config flags only
- F1C-i read-only DB connection helper
- F1C-ii safe_db_write wrapper
- F1D schema and natural-key inventory
- F1E external_ref compatibility report
- F1F UNIQUE(external_ref) migration for production_completions and vision_events
- F2A production completion event semantics analysis
- F2B production completion dry-run/no-op hook
- F2C production completion live hook after F1F
- F3A vision dry-run/no-op hook using apply_vision_event payload
- F3B vision live hook after F1F
- F4A OEE snapshot source policy
- F4B OEE dry-run
- F4C OEE migration only if needed
- F4D OEE live hook
- F5 deferred table analysis
- F6 remaining constraints/index hardening
- F7A shadow read / compare endpoint
- F7B work_orders read transition
- F8 dashboard/reporting read transition
- F9 runtime JSON role reduction
- F10 backup/restore protocol
- F11 final source-of-truth switch

## 6. First Safe Codex Phases
- Phase 1: F0 documentation only
- Phase 2: F1A feature flag matrix doc
- Phase 3: F1B config flags only
- Phase 4: F1C-i read-only DB connection helper
- Phase 5: F1D schema/natural-key inventory

## 7. Things Not To Do
- Live hook before `UNIQUE(external_ref)` yok
- `production_count` topic varsayımı yok
- Vision key yeniden icat etme yok
- Migration + hook aynı fazda yok
- DB write + DB read aynı fazda yok
- Mirror/verify script silme yok

## 8. Next Recommended Step
- F1A feature flag matrix documentation
