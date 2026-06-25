# MESQL DB Pre-Plan Summary

Bu dokuman aktif MESQL karar ozetidir. Ham kaynak degildir; `docs/db_pre_plan/*` altindaki Excel/DOCX kaynaklari ve `docs/agent_memory/10_db_pre_plan_summary.md` icindeki notlar ozetlenerek hazirlanmistir.

Bu dokuman production migration degildir. DDL, runtime davranisi veya DB apply talimati olarak kullanilmamalidir.

## Ham Kaynaklar

Ham kaynaklar bu sprintte tasinmadi ve degistirilmedi:

- `docs/db_pre_plan/*`
- `docs/agent_memory/10_db_pre_plan_summary.md`

Bu dosyalar mimari kaynakca ve on analizdir. Kanonik kararlar aktif `docs/mesql/` dokumanlarinda tutulmalidir.

## MESQL Ana Domainleri

| Domain | Amac | MVP onceligi |
| --- | --- | --- |
| `engineering` | Urun, parca, EBOM, teknik dokuman, ECR/ECO gibi muhendislik master data. | Ileri faz |
| `manufacturing` | MBOM, BOP, operasyon, work center, station mapping, standart sure. | MVP icin secili alt kapsam |
| `workstudy` | Zaman etudu, standart sure, operasyon varyantlari ve kapasite varsayimlari. | Ileri faz |
| `erp_integration` | ERP/F-ERP is emri, stok karti, import/export, outbox/inbox, conflict lifecycle. | MVP icin secili alt kapsam |
| `mes` | Is emirleri, uretim eventleri, completion, downtime, maintenance, OEE runtime mirror. | MVP oncelikli |
| `quality` | Inspection, measurement, nonconformance, disposition, quality override. | MVP icin sinirli alt kapsam |
| `traceability` | Lot, seri, tuketim, operation trace, barcode/RFID iliskileri. | Ileri faz |
| `analytics` | OEE, KPI, production facts/dimensions, BI/DW martlari. | Ileri faz |
| `audit/security/ref` | Kullanici, yetki, audit trail, referans kod listeleri ve governance. | Secili referans alanlari haric ileri faz |

## MVP Icin Oncelikli Domainler

MVP seviyesinde MESQL DB calismasi once dar, kanitlanabilir ve runtime'i bozmayan alanlara odaklanmalidir:

- `mes`: work orders, production completions, vision events, OEE/downtime/quality mirror adaylari.
- `erp_integration`: F-ERP import batch, export outbox, create/map/conflict lifecycle karar destegi.
- `manufacturing`: BOM/BOP source owner gelene kadar sadece canonical hedef ve readiness dokumani; production importer yok.
- `quality`: mevcut quality override ve ileride nonconformance icin sinirli temel.
- `audit/security/ref`: sadece migration ve entegrasyon icin gerekli kod listesi/audit alanlari.

## Ileri Faz Domainleri

Asagidaki domainler MVP DB duzenlemesi icin dogrudan DDL kapsami olmamalidir:

- Engineering full master data
- Full manufacturing master data
- Workstudy detay modeli
- BI/DW yildiz sema
- Dedicated time-series database
- Search/full-text altyapisi
- Redis/cache altyapisi
- Agent memory/RAG database
- Full traceability/lot/serial modeli

Bu alanlar ancak veri hacmi, sorgu ihtiyaci ve operasyonel kullanim kanitlandiktan sonra ayrica planlanmalidir.

## Foundation Ile Ortusen Noktalar

- Work orders operasyonel MES verisinin ilk mirror hedefidir.
- JSONB `payload` ve `metadata` kullanimi, domain modeli kesinlesmeden veri sekillerini kanitlamak icin uygundur.
- Outbox/inbox ve idempotency fikirleri `ferp_export_outbox`, `ferp_import_batches` ve upsert yaklasimlariyla uyumludur.
- OEE, downtime, quality, vision ve device session tablolari MES operational, time-series, quality ve traceability yonleriyle iliskilidir.

## Ertelenen Kararlar

- Coklu database ayrimi.
- Redis, search, time-series veya BI altyapisi.
- Engineering, manufacturing ve quality master data'nin tam DDL modeli.
- ERP/F-ERP gercek outbox processing.
- Agent memory/RAG database.

## DB Sprintine Etkisi

Production DB duzenlemesine gecmeden once:

- MVP domain siniri net tutulmali.
- `db/drafts/mesql_shared_schema_draft.sql` production migration kabul edilmemeli.
- Ham `docs/db_pre_plan/*` kaynaklari karar belgesi gibi degil, kaynak kaniti gibi kullanilmali.
- BOM/BOP source owner gelmeden importer, adapter veya production mapping acilmamali.
