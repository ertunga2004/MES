# MES Roadmap

Bu dokuman agent memory masterplan ve handoff notlarini aktif, okunabilir roadmap olarak konsolide eder. Production talimati, migration planı veya runtime apply listesi degildir.

## Mevcut Sistem Durumu

- Ana uygulama `mes_web/` altindaki FastAPI tabanli MES Web runtime'dir.
- Fiziksel kontrol otoritesi Mega tarafindadir.
- ESP32 seri <-> MQTT bridge olarak calisir.
- Dashboard, operator kiosk, teknisyen ekrani, OEE runtime ve workbook yazimi MES Web tarafindadir.
- PostgreSQL/MESQL kademeli DB foundation ve ortak hafiza hedefidir.
- Excel, JSON, FERP ve MQTT yollari audit/fallback/import/export olarak korunur.
- Work order DB read overlay MVP seviyesinde flag ile vardir; bu full SQL-only source-of-truth anlamina gelmez.

## Tamamlanan Buyuk Checkpointler

- Docker portable setup tamamlandi.
- PostgreSQL container ve Adminer altyapisi kuruldu.
- `mes` schema ve baslangic migration zinciri olustu.
- Work orders, production completions ve vision events icin kontrollu DB population/verify checkpointleri yapildi.
- Production completions live hook ve station event writer guarded runtime rollout ile dogrulandi.
- Work order DB read overlay flag ile calisir hale geldi.
- Docs cleanup phase 1 ile aktif docs domain klasorlerine ayrildi.
- MESQL memory consolidation ile DB pre-plan, source-of-truth ve natural key kararları aktif `docs/mesql/` altina alindi.

## Cleanup Sonrasi Dokuman Duzeni

- `docs/INDEX.md`: aktif dokuman haritasi.
- `docs/architecture/`: mimari overview ve roadmap.
- `docs/runtime/`: runtime guardrails, feature flags, MQTT, hardware ve runbook.
- `docs/mesql/`: DB source-of-truth, shared schema, natural key ve validation kararları.
- `docs/erp/`: ERP/F-ERP integration ve label-first kararları.
- `docs/bombop/`: BOM/BOP release, source payload ve readiness dokumanlari.
- `docs/agent_memory/`: tarihsel checkpoint; aktif dokumanlarin yerine gecmez.

## BOM/BOP Durumu

BOM/BOP gelistirme source owner bekliyor. Gercek BOM/BOP source payload, field adlari, status/revision modeli ve validation sinyalleri gelmeden:

- Importer gelistirilmez.
- Adapter gelistirilmez.
- Production payload veya v1 contract acilmaz.
- Source field veya F-ERP label uydurulmaz.

## MESQL DB Gecisi Icin Onerilen Sira

1. Docs cleanup.
2. MESQL DB memory consolidation.
3. Runtime/guardrail consolidation.
4. MESQL DB core planning.
5. Read-only compatibility report.
6. Backup.
7. Isolated migration.
8. Dry-run hook.
9. Live hook.
10. Shadow read.
11. Source-of-truth switch.

Bu sira her domain icin yeniden gate edilmelidir. Bir tabloda live hook tamamlanmis olmasi baska tablo veya full runtime read icin otomatik onay degildir.

## MESQL DB Core Planning Gate

Core planning'e gecmeden once:

- Runtime guardrails ve feature flag dokumanlari okunmus olmali.
- `docs/mesql/sql_source_of_truth.md` source-of-truth ayrimini netlestirmeli.
- `docs/mesql/natural_key_inventory.md` unique/natural key risklerini belirtmeli.
- `db/migrations/*` ve `db/drafts/*` ayrimi korunmali.
- Backup/verify/rollback planı olmayan migration sprinti acilmamali.

## Yapilmamasi Gerekenler

- Bu roadmap'i production apply talimati gibi kullanma.
- Docker volume veya runtime data silme.
- Plan olmadan DB read, DB write veya migration ekleme.
- Agent memory checkpointlerini aktif dokuman yerine kullanma.
- BOM/BOP source owner gelmeden BOM/BOP development baslatma.
