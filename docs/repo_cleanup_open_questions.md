# Repo Cleanup Open Questions

Bu dosya audit sonrasi kullanici karari gerektiren noktalari listeler. Bu sprintte hicbir dosya silinmedi, tasinmadi veya yeniden adlandirilmadi.

## Kullanici Karari Gerekenler

1. `docs/postgres/**` aktif kullaniliyor mu?
   - Oneri: Artik stabil ana akis icin gerekli degilse `docs/archive/postgres/` altina alinabilir.
   - Risk: PostgreSQL gecis planlari hala referans aliniyorsa archive karari erken olur.

2. `docs/agent_memory/**` dosyalari nasil ele alinmali?
   - Oneri: DB ve runtime icin kanonik bilgisi olanlar ana dokumanlara merge edilsin, kalan checkpointler archive edilsin.
   - Risk: Agent handoff akisi bazi checkpoint dosyalarina dogrudan bagli olabilir.

3. `docs/db_pre_plan/**` ham kaynak mi, aktif karar dokumani mi?
   - Oneri: `docs/raw/db_pre_plan/` altina alinsin; ozetlenmis kararlar `docs/mesql/` altinda kalsin.
   - Risk: Shared schema sprintinde bu dosyalar kaynak olarak kullaniliyor; linkler guncellenmeden tasinmamali.

4. `docs/FERP_XLS/**` icin raw klasor karari.
   - Oneri: `docs/raw/ferp/` altina alinsin.
   - Risk: F-ERP label ve import CSV kaynaklari kritik; dosya adlari ve ham icerik korunmali.

5. `Giyotin_kontrol/pc_app/readme.md` silinsin mi?
   - Oneri: 0 byte oldugu icin DELETE_CANDIDATE.
   - Risk: Kullanici onayi olmadan silinmemeli.

## En Riskli 10 Karar

| File / group | Risk |
| --- | --- |
| `db/migrations/*.sql` | Kesinlikle tasinmamali; migration zinciri ve tooling bozulabilir. |
| `db/drafts/mesql_shared_schema_draft.sql` | DB sprinti icin draft kaynak; yer degistirme referanslari kirabilir. |
| `docs/db_pre_plan/Manufacturing_Master_Data_Database_Detayli_Tasarim.xlsx` | BOM/BOP candidate field kaynaklarindan biri; raw olarak korunmali. |
| `docs/db_pre_plan/MES_Operational_Database_Detayli_Tasarim.xlsx` | MESQL schema kararlarina girdi olabilir. |
| `docs/FERP_XLS/ferp_labels.xlsx` | F-ERP label uydurmamak icin kritik kaynak. |
| `docs/FERP_XLS/FERP_TÜM_LABEL_VE_ZORUNLULAR.xlsx` | Label/zorunlu alan dogrulamasi icin kritik kaynak olabilir. |
| `docs/bombop_*` | BOM/BOP source owner bloklu; tasima disinda yeni contract gelistirmesi yapilmamali. |
| `docs/mesql_shared_schema_migration_review.md` | DB migration sprintine gate dokumani olabilir. |
| `docs/agent_memory/19_schema_natural_key_inventory.md` | Unique/revision modeline girdi; archive edilmeden once merge edilmeli. |
| `docs/postgres/**` | Tarihsel mi aktif mi kullanici onayi gerektirir. |

## MESQL DB Duzenlemesi Oncesi Kapanmasi Gerekenler

- `docs/mesql/` klasoru olusturulup MESQL karar dokumanlari burada toplanmali.
- `docs/raw/db_pre_plan/` altina ham DB pre-plan dosyalari alinmali veya mevcut konum icin karar netlesmeli.
- `docs/mesql/shared_schema_draft.md` ile `db/drafts/mesql_shared_schema_draft.sql` arasindaki kaynak/oncelik iliskisi yazilmali.
- `docs/agent_memory/10_db_pre_plan_summary.md`, `17_sql_source_of_truth_transition_masterplan.md` ve `19_schema_natural_key_inventory.md` aktif MESQL dokumanlarina merge edilmeli.
- BOM/BOP tarafinda source owner gelmeden yeni importer, adapter, payload veya mapping gelistirmesi yapilmamali.

## Silme / Merge / Rename Riski

- Silme icin yalniz `Giyotin_kontrol/pc_app/readme.md` adaydir; acik kullanici onayi gerekir.
- Merge adaylari once yeni hedef dokumana ozetlenmeli, sonra kaynak dosya `archive/superseded/` altina alinmali.
- Rename/tasima yapilacaksa `git mv` kullanilmali ve ayni fazda linkler guncellenmeli.
- Bu audit ciktisi tek basina tasima veya silme onayi degildir.
