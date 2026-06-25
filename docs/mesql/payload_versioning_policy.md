# MESQL Payload Versioning Policy

Bu dokuman MESQL canonical payload ve ERP/F-ERP staging export schema versioning politikasini tanimlar.

## Temel Kural

Tum canonical payload ve staging export orneklerinde `schema` alani zorunludur.

| Schema ornegi | Anlam |
|---|---|
| `mesql.bombop_release.canonical.v0` | BOM/BOP canonical release draft/staging payload |
| `mesql.bombop_validation_response.v0` | Importer validation response draft/staging payload |
| `mesql.erp_preparation_staging.v0` | MESQL -> ERP/F-ERP hazirlik staging export |

## Version Seviyeleri

| Version | Anlam | Kullanim |
|---|---|---|
| `v0` | Draft/staging | Ornek payload, field mapping ve review icin |
| `v1` | Contract-stable | Production importer veya adapter yazilmadan once gerekir |

`docs/examples` altindaki payloadlar runtime contract degildir. Bu dosyalar dokumantasyon ve review ornegidir.

## Breaking Change Tanimi

Asagidakiler breaking change kabul edilir:

| Degisiklik | Neden breaking |
|---|---|
| Zorunlu canonical alanin kaldirilmasi | Importer ve validation bozulur |
| Alan tipinin degismesi | Parser ve downstream mapping etkilenir |
| Enum degerinin kaldirilmasi veya anlaminin degismesi | Release/validation kararlari bozulur |
| Nesne yapisinin tasinmasi | Existing importer mapping bozulur |
| `schema` degerinin ayni kalip davranisin degismesi | Contract izlenebilirligi kaybolur |

Breaking change gerekiyorsa schema version artirilmalidir.

## Backward Compatible Change Tanimi

Asagidakiler backward compatible kabul edilebilir:

| Degisiklik | Kosul |
|---|---|
| Opsiyonel alan ekleme | Eski payload parse edilmeye devam etmeli |
| Yeni warning kodu ekleme | Default davranis geriye uyumlu olmali |
| Aciklama/note alani ekleme | Importer zorunlu saymamali |
| Enum listesine yeni status ekleme | Productionda check constraint migration stratejisi ayrica yazilmali |

## v0'dan v1'e Gecis Kriterleri

Production importer yazilmadan once ilgili payloadlar `v1` contract-stable seviyesine alinmalidir.

| Kriter | Gerekce |
|---|---|
| Gercek BOM/BOP source field mapping kapandi | Production importer icin zorunlu |
| Validation error dictionary onaylandi | Response standardi icin zorunlu |
| Required/optional alanlar netlesti | Parser davranisi icin zorunlu |
| ERP/F-ERP staging format karari kapandi | Adapter davranisi icin zorunlu |
| Backward compatibility stratejisi yazildi | Sonraki degisiklikler icin gerekli |

## Dosya ve Ornek Politikasi

| Alan | Kural |
|---|---|
| `docs/examples/*.json` | Parse edilebilir olmali |
| Example payload | Gercek production data sayilmaz |
| Source field | Gercek BOM/BOP alan adi bilinmiyorsa `TBD` veya mapping dokumaninda acik not kullanilir |
| F-ERP label | Yalniz kaynaklarda bilinen label'lar kullanilir |
| Quantity movement label | Bilinmiyorsa uydurulmaz; `MESQL-VAL-0014` warning ile tasinir |
