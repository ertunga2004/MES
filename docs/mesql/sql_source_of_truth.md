# MESQL SQL Source of Truth

Bu dokuman MESQL DB source-of-truth kararlarini aktif MESQL dokumanina konsolide eder. Kaynak notlar: `docs/agent_memory/17_sql_source_of_truth_transition_masterplan.md`, `docs/agent_memory/00_masterplan.md` ve `docs/agent_memory/08_guardrails_and_do_not_touch.md`.

Bu dokuman production migration degildir ve runtime davranisi degistirmez.

## Temel Karar

MESQL ortak DB, ortak operasyonel hafiza ve merkezi gerceklik kaynagi hedefidir. Ancak gecis kademeli yapilmalidir; mevcut runtime akislari kanitlanmadan DB read veya DB write zorunlulugu eklenmemelidir.

## Local DB Siniri

- Uygulama local DB'leri yalniz workspace, cache, draft veya offline staging icin kullanilabilir.
- Uygulamalar birbirlerinin local DB'sine dogrudan baglanmaz.
- Uygulamalar arasi veri alisverisi MESQL backend/API ve MESQL ortak DB uzerinden tasarlanir.

Hedef model:

```text
Application Local DB / cache / draft
  <-> MESQL Backend API
  <-> MESQL DB
```

## Otorite Ayrimi

| Alan | Otorite |
| --- | --- |
| ERP is emri | ERP/F-ERP is emri otoritesidir. |
| MES uretim yurutme | MES runtime uretim yurutme otoritesidir. |
| MESQL ortak hafiza | MESQL ortak operasyonel hafiza ve entegrasyon verisi merkezidir. |
| BOM/BOP source | Source owner gelene kadar production importer/v1 acilmaz. |

## Runtime `mes` Schema ve MESQL Shared Schema Ayrimi

| Katman | Amac | Durum |
| --- | --- | --- |
| Runtime `mes` schema | Mevcut MES Web runtime mirror/foundation tablolari. | Kademeli ve feature-flag kontrollu. |
| MESQL shared schema | ERP, BOM/BOP ve MES arasinda paylasilacak ortak master/manufacturing veri modeli. | Draft/contract asamasinda. |

Runtime `mes` schema ile MESQL shared schema ayni sey gibi ele alinmamalidir. Runtime mirror tablolari mevcut uygulamayi guvenli sekilde gozlemlemek icindir; shared schema ise ortak veri sozlesmesi hedefidir.

## Draft SQL ve Production Migration Ayrimi

- `db/drafts/mesql_shared_schema_draft.sql` production migration degildir.
- `db/migrations/*` aktif migration zinciridir ve docs cleanup ile tasinmaz.
- Migration ve runtime hook ayni fazda yapilmamalidir.
- Verify olmadan apply yoktur.
- Backup olmadan migration yoktur.

## Gecis Prensipleri

- Big bang gecis yok.
- Feature flag sart.
- DB write hook ve DB read ayni fazda yok.
- Migration ve runtime hook ayni fazda yok.
- Mirror/verify scriptleri korunur.
- DB hatasi runtime'i cokertmemelidir.
- `docker compose down -v` kullanilmaz.
- `MES_WEB_DB_ENABLED` ve mirror flag defaultlari guvenli kalmalidir.

## Deployment Yaklasimi

Hedef PC yaklasimi:

- Gelistirme bu PC ve Git uzerinden ilerler.
- Deploy/test hedef PC'ye SSH ile yapilir.
- DB backup almadan migration yoktur.
- Docker runtime/deployment klasoru kaynak repo ile karistirilmamalidir.
- PostgreSQL host PC'ye kurulmaz; Docker container/volume yaklasimi korunur.

## Source-of-Truth Gecis Sirasi

1. Dokuman ve karar konsolidasyonu.
2. Feature flag ve read-only DB connection yardimcilari.
3. Schema/natural-key inventory.
4. Read-only compatibility report.
5. Temiz rapor + backup sonrasi izole UNIQUE migration.
6. Dry-run/no-op hook.
7. Live hook.
8. Shadow read/compare.
9. Flag-gated read gecisi.
10. JSON/Excel runtime rolunun kademeli azaltilmasi.
11. Final source-of-truth switch.

## Yapilmamasi Gerekenler

- Plan olmadan runtime DB read ekleme.
- Live hook'u UNIQUE/natural-key karari kapanmadan acma.
- Migration ile hook'u ayni sprintte birlestirme.
- Var olmayan MQTT topic veya source field varsayma.
- BOM/BOP source owner gelmeden importer, adapter veya payload gelistirme.
- DB volume'u silme veya production benzeri DB'de kontrolsuz `DROP`, `TRUNCATE`, `DELETE`, `ALTER` calistirma.
