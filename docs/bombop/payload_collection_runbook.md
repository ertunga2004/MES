# BOM/BOP Payload Collection Runbook

Bu runbook, kaynak BOM/BOP payload paketi geldikten sonra uygulanacak dokuman inceleme adimlarini tanimlar. Bu sprintte kod, migration, runtime veya importer degisikligi yapilmaz.

## 1. Paketi Kaydet

- Gelen dosyalari orijinal haliyle sakla.
- Dosya isimlerini, teslim tarihini ve kaynak sahibini not et.
- Orijinal dosyalar uzerinde alan adi duzeltmesi, format temizligi veya manuel rename yapma.
- Token, sifre, connection string veya kisisel veri varsa review'e baslamadan once kaynak sahibinden temiz paket iste.

## 2. Format Kontrolu

| Kontrol | Beklenti |
| --- | --- |
| JSON | Parse edilebilir olmali; root nesneler aciklanmali. |
| CSV/XLSX | Sheet/table anlamlari README'de belirtilmeli. |
| DB dump | Schema ve ornek satir birlikte bulunmali. |
| Mixed package | Dosyalar arasi anahtar iliskisi aciklanmali. |

## 3. Field Adlarini Koru

- Kaynak field adlarini aynen listele.
- MESQL canonical alan adina ceviri yapma.
- Alanin kaynakta gercekten var oldugu ornek satir veya schema ile dogrulanirsa `CONFIRMED` adayi yap.
- Kaynakta dogrudan yoksa `CANDIDATE`, `TBD` veya `BLOCKED` olarak birak.

## 4. Nesne Kapsamini Kontrol Et

| Nesne | Kontrol |
| --- | --- |
| Product master | Urun kodu, ad, tip ve birim bilgisi var mi? |
| Product revision | Revision/version field'i ve product iliskisi var mi? |
| Component | Component kodu, miktar ve birim izlenebiliyor mu? |
| MBOM | Header, revision, plant ve line iliskisi goruluyor mu? |
| BOP | Header, operation listesi, sequence ve operation code goruluyor mu? |
| Mapping | Operation-station veya operation-work center iliskisi var mi? |
| Package BOM | Varsa header/line yapisi; yoksa kaynak sahibi yoklugunu belirtmis mi? |
| Release lifecycle | Release edilebilir ve edilemez durumlar ayirt ediliyor mu? |
| Validation | Warning/hold/error mesaji veya yokluk beyanı var mi? |

## 5. Status ve Revision Davranisini Ayir

- Kaynak status kodlarini MESQL status listesine dogrudan map etmeden once anlamlarini not et.
- Uretime yayinlanabilir status kaynak sahibi tarafindan acikca belirtilmelidir.
- Eski release'in nasil kapandigi veya arsivlendigi anlasilmalidir.
- Ayni product revision + plant icin birden fazla aktif release ihtimali kontrol edilmelidir.

## 6. Mapping ve Validation Incelemesi

- Operasyon mapping'siz uretime dagitilabiliyor mu sorusuna kaynak verisiyle cevap ara.
- Eksik mapping varsa kaynak sistem warning, hold veya error uretiyor mu not et.
- Duplicate operation sequence, eksik component, eksik sure veya invalid unit gibi kaynak validation sinyalleri ayrica listelenir.

## 7. Readiness Dokumanlarini Guncelle

Payload review tamamlaninca asagidaki dokumanlarin sonraki sprintte guncellenmesi beklenir:

- `docs/bombop/source_field_discovery_report.md`
- `docs/bombop/source_field_mapping_readiness.md`
- `docs/bombop/v1_importer_contract_readiness.md`
- Gerekirse source-to-canonical mapping ek dokumani

Bu runbook tek basina v1 contract onayi vermez; sadece review akisini tanimlar.

## 8. Go / No-Go Karari

| Karar | Kosul |
| --- | --- |
| GO_FOR_MAPPING | Product, revision, MBOM, BOP, mapping ve release status alanlari CONFIRMED seviyesine gelir. |
| GO_WITH_GAPS | Ana akış gorulur, ancak package BOM veya validation gibi sinirli alanlar eksiktir. |
| NO_GO | Gercek field adlari, status veya revision modeli dogrulanamaz. |

## 9. Cikti

Review sonunda kisa bir karar notu uretilmelidir:

- CONFIRMED source fields
- CANDIDATE fields
- TBD/BLOCKED fields
- Status mapping onerisi
- Revision/unique model etkisi
- v1 importer icin go/no-go
- Eksik payload veya kaynak sahibi aksiyonlari
