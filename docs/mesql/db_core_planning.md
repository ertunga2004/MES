# MESQL DB Core Planning

Bu dokuman MESQL DB cekirdegi icin planlama ve kapsam daraltma notudur. Production migration degildir; DB'ye uygulanacak DDL, runtime kodu, Docker ayari veya importer gelistirmesi icermez.

## Amac ve Kapsam

Amac, mevcut runtime `mes` schema ile MESQL shared schema arasindaki siniri netlestirmek ve MVP migration adaylarini kontrollu bicimde ayirmaktir.

Bu sprintte:

- DB migration yazilmaz.
- DB'ye migration uygulanmaz.
- Runtime, Docker, `mes_web`, test veya raw kaynak dosyalari degistirilmez.
- BOM/BOP importer, adapter veya v1 payload gelistirilmez.

## MESQL DB MVP Hedefi

MVP hedefi, mevcut MES runtime'i bozmadan ortak operasyonel hafiza ve entegrasyon cekirdegi icin dar bir DB planidir.

MVP ilkeleri:

- Runtime `mes` schema korunur.
- MESQL shared schema production migration'a donmeden once compatibility ve source payload kaniti ister.
- Migration, runtime hook ve DB read gecisi ayri fazlarda ele alinir.
- Backup ve read-only rapor olmadan hedef PC'de migration uygulanmaz.

## Runtime `mes` Schema ve Shared MESQL Schema Ayrimi

| Katman | Amac | Bu sprintte karar |
| --- | --- | --- |
| Runtime `mes` schema | MES Web runtime mirror/foundation, work orders, completions, station queue, package sessions gibi operasyonel kayitlar. | Mevcut migration zinciri korunur; redesign edilmez. |
| MESQL shared schema | ERP, BOM/BOP ve MES arasinda paylasilacak master/manufacturing sozlesme modeli. | Draft/planlama seviyesinde; source owner ve compatibility gate ister. |

Bu iki katman ayni sey degildir. Runtime `mes` schema uygulamanin mevcut calismasini destekler; shared MESQL schema ortak master/manufacturing veri sozlesmesi hedefidir.

## MVP Domain Siniri

| Domain | MVP kapsami | Not |
| --- | --- | --- |
| `mes` | Work orders, production completions, vision events, station queue, package sessions ve sinirli runtime mirror. | Mevcut migration zinciri uzerinden ilerler. |
| `erp_integration` | FERP import/export metadata, outbox ve create/map/conflict karar destegi. | Servis entegrasyonu sonraki faz; label uydurulmaz. |
| Sinirli `manufacturing` | BOM/BOP canonical hedef, operation/station mapping kararlari. | Source owner gelmeden production migration/importer yok. |
| Sinirli `quality` | Quality override ve ileride quality event cekirdegi. | Full QMS degil. |
| Audit/ref minimum | Audit, status, validation, referans kod listeleri. | Sadece migration guvenligi icin gerekli alanlar. |

## Ileri Faz Domainleri

Asagidaki alanlar MVP DB core migration kapsami olmamalidir:

- Full engineering master data.
- Full manufacturing master data.
- Workstudy detay modeli.
- Analytics/BI yildiz sema.
- Full traceability/lot/serial modeli.
- Search, time-series, cache veya agent memory DB.

## BOM/BOP Source Owner Bekleyen Alanlar

Su alanlar gercek BOM/BOP source payload gelmeden production migration veya importer adayi olmamalidir:

- Product/revision source field mapping.
- MBOM header/line source field mapping.
- BOP header/operation source field mapping.
- Operation/station veya operation/work center mapping source.
- Package BOM header/line source field mapping.
- Source release status ve validation/error formatlari.

Canonical draft korunur; source field adi uydurulmaz.

## F-ERP No-Invention Kurali

F-ERP alanlari sadece bilinen label kaynaklarina dayandirilmali:

- `lblMTM00_CODE`
- `lblMTM00_NAME`
- `lblMTMT0_CODE`
- `lblMUNT0_CODE`
- `lblMFW00_CODE`
- `lblMFWO0_CODE`
- `lblMMFB4_SETUP_TIME`
- `lblMMFB4_TIME`

Bilinmeyen stok hareket quantity label'i, BOM/BOP source field'i veya MESQL endpoint adi uydurulmaz.

## Sonuc

MESQL DB core planning icin ilk production adimi migration yazmak degil, migration candidate matrix ve compatibility report planini kapatmaktir. Hedef PC'ye uygulanacak her DB degisikligi backup, read-only rapor, izole migration ve post-verify sirasindan gecmelidir.
