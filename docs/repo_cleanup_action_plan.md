# Repo Docs Cleanup Action Plan

Bu plan sadece sonraki cleanup sprintleri icin oneridir. Bu sprintte dosya silme, tasima, yeniden adlandirma, migration, runtime, Docker veya test degisikligi yapilmadi.

## Onerilen Docs Yapisi

```text
docs/
  README.md
  INDEX.md
  architecture/
  mesql/
  contracts/
  erp/
  bombop/
  runtime/
  examples/
  archive/
    legacy/
    superseded/
    agent_memory/
    postgres/
  raw/
    db_pre_plan/
    ferp/
```

## Faz 1: Guvenli Tasima

Amac: Aktif dokumanlari domain klasorlerine ayirmak.

Onerilen tasima gruplari:

- `docs/bombop_*.md` -> `docs/bombop/`
- `docs/mesql_*.md` -> `docs/mesql/`
- ERP/F-ERP markdownlari -> `docs/erp/`
- Runtime/hardware/MQTT/runbook dokumanlari -> `docs/runtime/`
- `docs/architecture.md` -> `docs/architecture/overview.md`

Kosul:

- Tasima oncesi mevcut dokuman linkleri `rg` ile bulunmali.
- Tasima ayni commit icinde link guncellemesiyle yapilmali.
- BOM/BOP source owner bloklu oldugu icin yeni importer, adapter veya mapping uretilmemeli.

## Faz 2: INDEX ve README

Amac: Belgelerin yeni yerini kullanici ve agent icin tek giristen okunur yapmak.

Onerilen dosyalar:

- `docs/INDEX.md`: tum aktif dokuman haritasi
- `docs/architecture/README.md`
- `docs/mesql/README.md`
- `docs/erp/README.md`
- `docs/bombop/README.md`
- `docs/runtime/README.md`
- `docs/raw/README.md`

Kural:

- `docs/README.md` sade kalmali.
- `docs/INDEX.md` kanonik navigation olmali.
- Archive ve raw klasorleri aktif sprint talimatlari gibi sunulmamali.

## Faz 3: Archive Tasima

Amac: tarihsel checkpoint ve tamamlanmis gecis planlarini aktif akistan ayirmak.

Onerilen tasima:

- `docs/agent_memory/*` checkpoint dosyalari -> `docs/archive/agent_memory/`
- `docs/postgres/*` -> `docs/archive/postgres/`
- Mevcut `docs/archive/legacy_plans/roadmap.md` yerinde kalabilir.

Kosul:

- `docs/agent_memory/README.md` ya yerinde kalmali ya da yeni archive konumunu aciklamali.
- Agent memory icindeki ana kararlar once aktif dokumana merge edilmeli.
- Archive tasimasi silme degildir; dosya gecmisi korunur.

## Faz 4: Duplicate / Merge Cleanup

Amac: ayni kararin farkli checkpoint dosyalarinda tekrar etmesini azaltmak.

Merge adaylari:

- `docs/data-model.md` + `docs/mes_mvp_db_inventory.md` + agent memory DB inventory notlari -> `docs/mesql/data_model.md` ve `docs/mesql/db_inventory.md`
- `docs/agent_memory/07_workflow_for_future_agents.md` -> `docs/INDEX.md` veya `docs/AI_GUIDE.md`
- `docs/agent_memory/08_guardrails_and_do_not_touch.md` -> `docs/AI_GUIDE.md`
- `docs/agent_memory/18_feature_flag_matrix.md` -> `docs/runtime/feature_flags.md`
- `docs/agent_memory/19_schema_natural_key_inventory.md` -> `docs/mesql/natural_key_inventory.md`

Kosul:

- Merge yapildiktan sonra kaynak dosya hemen silinmemeli.
- Once archive veya superseded altina alinmali.
- Silme karari ayrica kullanici onayi gerektirir.

## Silme Onayi Gerektiren Dosyalar

Bu audit'te yalniz su dosya DELETE_CANDIDATE olarak isaretlendi:

- `Giyotin_kontrol/pc_app/readme.md`

Sebep: Dosya 0 byte gorunuyor. Yine de silme icin acik kullanici onayi gerekir.

## Rollback Stratejisi

1. Her faz ayri commit olmalidir.
2. Tasima fazinda `git mv` kullanilmali, kopyala/sil yapilmamali.
3. Her fazdan sonra `git status --short --untracked-files=all` kontrol edilmeli.
4. Link guncellemeleri icin `rg "eski_dosya_adi|eski_klasor"` calistirilmali.
5. Sorun cikarsa ilgili faz commit'i revert edilmeli; migration/runtime koduna dokunulmamali.

## MESQL DB Duzenlemesi Oncesi Cleanup Gate

DB schema sprintine gecmeden once en az su cleanup adimlari kapanmali:

- MESQL karar dokumanlari `docs/mesql/` altinda toplanmali.
- DB pre-plan ham kaynaklari `docs/raw/db_pre_plan/` altinda ayrilmali.
- `docs/mesql/shared_schema_draft.md`, `docs/mesql/shared_schema_migration_review.md` ve `db/drafts/mesql_shared_schema_draft.sql` arasindaki kanonik kaynak iliskisi `docs/INDEX.md` icinde belirtilmeli.
- Agent memory DB notlari aktif MESQL dokumanlarina merge edilmeden archive edilmemeli.
