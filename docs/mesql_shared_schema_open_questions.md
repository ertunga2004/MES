# MESQL Shared Schema Acik Sorular

Bu dokuman 3B - Shared Schema Draft sonrasi kapanmasi gereken konulari listeler. Kod, migration veya runtime degisikligi degildir.

| Acik alan | Neden onemli | Blokladigi is |
|---|---|---|
| BOM/BOP gercek release JSON alan adlari | Bu sprint is nesnesi seviyesinde kaldigi icin importer alan eslesmesi henuz kesin degil | Production importer |
| MESQL Backend API endpoint isimleri | Endpoint adi uydurulmayacak; API contract ayrica kapanmali | API servis ve client entegrasyonu |
| MESQL -> ERP hazirlik aktarim mekanizmasi | Manuel ERP girisi, Excel import, label-first JSON veya REST/API arasinda karar gerekiyor | Faz 2 ERP hazirlik servis/entegrasyon katmani |
| F-ERP stok hareket quantity label eksikligi | Kaynak sozlesmede net hareket satiri quantity label'i eksik; `qty` ve warning ile tasiniyor | Resmi stok hareket import kesinlestirme |
| WARN/FAIL hata kod sozlugu | Validation seviyesi belli ama standard hata kodlari henuz yok | Validation testleri ve API response standardi |
| Operation/station master datasinin uzun vadeli sahipligi | Bugunku canonical kaynak MESQL manufacturing domain; governance ve master data lifecycle ayrintisi acik | Uzun vadeli master data yonetimi |
| EBOM -> MBOM donusum kurali | Engineering master data ile manufacturing release arasindaki donusum henuz tanimli degil | Engineering -> manufacturing sureci |
| ERP create/map/conflict lifecycle ayrintisi | Var olan ERP stok karti icin create candidate, map/skip, conflict-report ve revision review akislari detaylanmali | ERP hazirlik aktarimi ve manual review ekrani/raporu |

## Kapanmis Kabul Noktalari

| Konu | Kabul |
|---|---|
| Release status listesi | `DRAFT`, `IN_REVIEW`, `APPROVED`, `RELEASED`, `ARCHIVED`, `REJECTED`, `PENDING` |
| ERP/MES dagitimi | Sadece `RELEASED` veri gider |
| Revision unique modeli | Product, product revision, MBOM, BOP ve package BOM unique kararlari kapandi |
| Operation/station mapping canonical kaynak | MESQL manufacturing domain |
| `mes.station_queue` rolu | Master data degil; gunluk operasyonel queue |
| Mapping eksigi defaultlari | `DRAFT`/`IN_REVIEW`: WARN, `APPROVED`: HOLD, `RELEASED`: FAIL |

## 3C Oncelik Sirasi

1. BOM/BOP release JSON alan adlarini ve ornek payload'lari kesinlestir.
2. Validation hata kod sozlugunu yaz.
3. Shared schema draft SQL'i migration review'a hazirla.
4. ERP hazirlik aktarim mekanizmasi icin karar notu uret.
5. ERP conflict-report/manual-review lifecycle taslagini hazirla.
