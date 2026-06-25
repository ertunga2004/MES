# MESQL Shared Schema Karar Notu

Bu not Antigravity mimari review sonrasi iki data exchange dokumaninda kapanan kararlari ozetler. Kod, migration veya runtime degisikligi degildir.

## Kapanan Kararlar

| Karar | Hukum |
|---|---|
| Release status | Kabul edilen liste: `DRAFT`, `IN_REVIEW`, `APPROVED`, `RELEASED`, `ARCHIVED`, `REJECTED`, `PENDING`. ERP/MES'e sadece `RELEASED` veri gider. |
| Revision unique modeli | Product master `product_code` unique; product revision `UNIQUE(product_id, revision_code)`; MBOM/BOP/Package BOM icin product revision + revision + plant temelli unique model. |
| Aktif release | Ayni product revision + plant icin ayni anda birden fazla aktif `RELEASED` MBOM/BOP olmamalidir. Eski release `ARCHIVED` veya `valid_to` ile kapatilmalidir. |
| Operation/station mapping otoritesi | Canonical kaynak MESQL manufacturing domainidir. BOM/BOP release eder, MES MESQL'den okur. `mes.station_queue` gunluk siradir, master data degildir. |
| Station mapping eksigi | `DRAFT` / `IN_REVIEW`: WARN; `APPROVED`: HOLD; `RELEASED`: FAIL. MES'e mapping'siz operasyon dagitilamaz. |
| ERP stok karti davranisi | Var olan `lblMTM00_CODE` sessiz overwrite edilmez; uyumluysa map/skip, celiskiliyse manual review. |
| Component label ailesi | Component icin bilinen stok label ailesi kullanilir: `lblMTM00_CODE`, `lblMTM00_NAME`, `lblMTMT0_CODE`, `lblMUNT0_CODE`. |

## Acik Kalan Bloklar

| Acik alan | Blokladigi is |
|---|---|
| BOM/BOP gercek release JSON alan adlari | Production importer |
| MESQL Backend API endpoint isimleri | API servis/client entegrasyonu |
| MESQL -> ERP hazirlik aktarim mekanizmasi | Faz 2 servis/entegrasyon katmani |
| F-ERP stok hareket quantity label eksikligi | Resmi stok hareket import kesinlestirme |
| WARN/FAIL hata kod sozlugu | Validation testleri ve response standardi |

## DB Sema Sprintine Gecis Hukmu

Shared schema draft sprintine gecilebilir. Release status, revision unique modeli ve operation/station mapping otoritesi DB taslak semasi icin yeterince kapanmistir.

Faz 2 ERP hazirlik aktarim mekanizmasi henuz aciktir; bu durum ERP entegrasyon servisinin uygulanmasini bloklar, ancak ortak DB taslak semasinin yazilmasini bloklamaz.
