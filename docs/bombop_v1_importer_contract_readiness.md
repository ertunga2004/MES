# BOM/BOP v1 Importer Contract Readiness

Bu dokuman `mesql.bombop_release.canonical.v0` payload'indan `v1` importer contract seviyesine gecmek icin kapanmasi gereken kosullari listeler.

## v0 Mevcut Durum

| Alan | Durum |
|---|---|
| Canonical payload ornegi | Var: `docs/examples/bombop_release_payload.canonical.example.json` |
| Validation response ornegi | Var: `docs/examples/bombop_validation_response.example.json` |
| ERP staging ornegi | Var: `docs/examples/erp_preparation_staging_export.example.json` |
| Source field mapping | `TBD`; gercek BOM/BOP source field yok |
| Version policy | Var: `docs/mesql_payload_versioning_policy.md` |
| Production importer | Yok; bu sprintte yazilmadi |

## v1'e Gecis Icin Zorunlu Kararlar

| Karar | Durum | Neden gerekli |
|---|---|---|
| Gercek BOM/BOP source payload ornegi | Acik | `source_field` mapping icin zorunlu |
| Release status crosswalk | Acik | BOM/BOP status -> MESQL status mapping gerekir |
| Revision/version field mapping | Acik | Unique model ve active release kontrolu icin zorunlu |
| MBOM/BOP/package nested structure | Acik | Parser ve validation icin zorunlu |
| Operation/station mapping source | Acik | MES dagitim validation icin zorunlu |
| Setup/cycle time source fields | Acik | ERP/F-ERP label staging icin gerekli |
| Source validation/error format | Acik | Validation response enrich icin gerekli |

## Source Field Mapping Kapanis Kriterleri

| Kriter | Go kosulu |
|---|---|
| Her required canonical alan icin source field | CONFIRMED olmali |
| CANDIDATE alanlar | Gercek source payload ile dogrulanmali |
| `TBD` required alanlar | Kalmamali |
| BLOCKED alanlar | Kapanmali veya v1 kapsam disi karar notu olmali |
| Source examples | En az bir valid release, bir HOLD, bir FAIL ornegi olmali |

## Validation Response Kapanis Kriterleri

| Kriter | Go kosulu |
|---|---|
| `errors` / `warnings` / `holds` ayrimi | Severity dictionary ile uyumlu |
| Hata kodlari | Sadece `docs/mesql_validation_error_dictionary.md` icindeki kodlar |
| Entity references | Product, revision, MBOM, BOP, mapping, package BOM icin standart |
| Recommended actions | Her HOLD/FAIL icin zorunlu |
| Source validation mapping | BOM/BOP kaynak warning/error formatindan MESQL kodlarina mapping |

## ERP Staging Kapanis Kriterleri

| Kriter | Go kosulu |
|---|---|
| Bilinen F-ERP labels | Sadece kaynaklarda bilinen label'lar kullanilmali |
| Quantity movement label | Karar kapanmadan production stok hareket import'u v1 kapsaminda olmamali |
| Create/map/conflict lifecycle | ERP tarafindan onaylanmali |
| Excel/CSV vs label-first JSON | MVP adapter karari kapanmali |
| Conflict report | Alanlari ve review sorumlusu belirlenmeli |

## Test Fixture Ihtiyaci

| Fixture | Amac |
|---|---|
| Valid RELEASED payload | PASS happy path |
| Missing mapping RELEASED payload | `MESQL-VAL-0005` FAIL |
| APPROVED missing mapping payload | `MESQL-VAL-0006` HOLD |
| Duplicate operation sequence payload | `MESQL-VAL-0004` FAIL |
| Multiple active RELEASED MBOM/BOP payload | `MESQL-VAL-0011` / `MESQL-VAL-0012` |
| ERP item code conflict payload | `MESQL-VAL-0008` HOLD |
| Unknown source field mapping payload | `MESQL-VAL-0015` HOLD |

## Gercek BOM/BOP Ornek Payload Ihtiyaci

Gercek source payload su nesneleri icermelidir:

- product
- product revision/version
- components
- MBOM header/lines
- BOP header/operations
- operation/station veya operation/work center mapping
- package BOM header/lines
- release status ve release timestamp
- source validation warnings/errors varsa onlar

## Go / No-Go Checklist

| Kontrol | Durum |
|---|---|
| Gercek BOM/BOP source payload alindi | NO-GO |
| Required source fields CONFIRMED | NO-GO |
| Release status crosswalk kapandi | NO-GO |
| Revision field mapping kapandi | NO-GO |
| Validation response v1 fixture'lari hazir | NO-GO |
| ERP staging adapter karari kapandi | NO-GO |
| Payload schema `v1` yapilabilir | NO-GO |

## Sonuc

Bugun `v1` importer contract'a gecilmemelidir. `v0` canonical payload ve source discovery raporlari korunmali; gercek BOM/BOP source payload gelince mapping tekrar degerlendirilmelidir.
