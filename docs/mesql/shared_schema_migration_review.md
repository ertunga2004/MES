# MESQL Shared Schema Migration Review

Bu dokuman 3B draft SQL'in production migration'a donusturulmeden once gozden gecirilmesi gereken noktalarini listeler.

Onemli uyari: `db/drafts/mesql_shared_schema_draft.sql` production migration degildir. Runtime DB'ye uygulanmamalidir. Bu sprintte DB migration, runtime, Docker veya MES Web davranisi degistirilmez.

## Schema Naming Review

| Alan | Mevcut draft | Review notu |
|---|---|---|
| Master domain | `mesql_master` | Urun, revision ve component adaylari icin uygun gorunuyor |
| Manufacturing domain | `mesql_manufacturing` | MBOM, BOP, mapping ve package BOM icin uygun gorunuyor |
| Operational MES domain | `mes` | Mevcut runtime/mirror schema olarak kalmali; redesign edilmemeli |
| Table naming | `*_headers`, `*_lines` | Header-line modeli okunur; migration oncesi ekip standardi ile teyit edilmeli |

## Primary Key / Surrogate Key Review

| Konu | Draft karar | Review ihtiyaci |
|---|---|---|
| Surrogate key tipi | `text` | Production migration oncesi `uuid`, `text`, veya DB-generated id karari kapanmali |
| Business key korunumu | Natural unique constraint'ler var | Surrogate key olsa bile business key constraint'leri korunmali |
| ID uretim sahibi | Acik | Importer mi DB mi id uretecek kararlastirilmali |

## Natural Key / Unique Constraint Review

| Nesne | Draft unique constraint | Review notu |
|---|---|---|
| Product | `UNIQUE(product_code)` | ERP/F-ERP `lblMTM00_CODE` ile mapping icin kritik |
| Product revision | `UNIQUE(product_id, revision_code)` | Revision lifecycle icin temel kabul |
| MBOM | `UNIQUE(product_revision_id, mbom_revision, plant_code)` | Plant ayrimi dogrulanmali |
| BOP | `UNIQUE(product_revision_id, bop_revision, plant_code)` | Plant ayrimi dogrulanmali |
| Package BOM | `UNIQUE(package_product_revision_id, package_bom_revision, plant_code)` | Package product revision sahipligi dogrulanmali |
| BOP operation | `UNIQUE(bop_id, operation_sequence)` | Duplicate operation sequence engellenmeli |

## `release_status` Constraint Review

Kabul edilen degerler:

| Status | Dagitim etkisi |
|---|---|
| `DRAFT` | ERP/MES'e gitmez |
| `IN_REVIEW` | ERP/MES'e gitmez |
| `APPROVED` | ERP/MES'e gitmez; uretime cikmak icin yeterli degildir |
| `RELEASED` | ERP/MES'e gidebilir |
| `ARCHIVED` | Uretime cikamaz |
| `REJECTED` | Uretime cikamaz |
| `PENDING` | Staging/import bekler |

Production migration oncesi bu listenin degismeyecegi onaylanmali. Sonradan yeni status eklenecekse check constraint migration stratejisi ayrica yazilmali.

## `validation_level` Constraint Review

| Level | Anlam | Dagitim etkisi |
|---|---|---|
| `PASS` | Kural gecildi | Dagitim icin uygun olabilir |
| `WARN` | Uyari var, erken fazda ilerlenebilir | MES dagitimi icin ek kontrol gerekir |
| `HOLD` | Karar bekliyor | Dagitim durmali |
| `FAIL` | Kural ihlali | Dagitim engellenmeli |

`validation_level` tek basina release karari degildir. MES'e gidecek veri hem `RELEASED` hem validation `PASS` olmalidir.

## Partial Unique Index Review

| Index | Amac | Review notu |
|---|---|---|
| Active `RELEASED` MBOM | Ayni product revision + plant icin tek aktif MBOM | `release_status = 'RELEASED' AND valid_to IS NULL` kosulu uygun; valid window politikasi teyit edilmeli |
| Active `RELEASED` BOP | Ayni product revision + plant icin tek aktif BOP | Eski release `ARCHIVED` veya `valid_to` ile kapatilacak karar netlesmeli |
| Active `RELEASED` package BOM | Ayni package product revision + plant icin tek aktif package BOM | Package revision sahipligi teyit edilmeli |

## FK Davranislari

| Iliski | ON DELETE onerisi | Gerekce |
|---|---|---|
| Product -> product revisions | `RESTRICT` / default | Master data silinmemeli; archive tercih edilmeli |
| Product revision -> MBOM/BOP/package BOM headers | `RESTRICT` / default | Released hazirlik izleri kaybolmamali |
| Header -> line | Productionda `RESTRICT` veya kontrollu cascade | Draft/import staging ile production ayrimi kararlastirilmali |
| Component -> BOM lines | `RESTRICT` / default | Kullanilan component silinmemeli |
| BOP operation -> operation station mapping | `RESTRICT` / default | Mapping gecmisi korunmali |

Cascade sadece staging veya gecici import tablolarinda dusunulmelidir. Production master/manufacturing kayitlarinda silme yerine `ARCHIVED` veya `valid_to` yaklasimi tercih edilmelidir.

## Timestamp Standardi

| Alan | Review notu |
|---|---|
| `created_at` | Tum tablolarda var; default `now()` uygun |
| `updated_at` | Tum tablolarda var; productionda trigger veya application update politikasi gerekir |
| `valid_from` / `valid_to` | Release lifecycle icin kullaniliyor; timezone ve null anlami netlesmeli |
| `released_at` | Draft SQL'de yok; importer contract seviyesinde var. Production tablolarinda gerekip gerekmedigi kararlastirilmali |

## `source_system` / `metadata` / `payload` Ihtiyaci

| Alan | Draft durum | Review notu |
|---|---|---|
| `source_system` | Product/component tablolarinda var | BOM/BOP, ERP, manuel kaynak ayrimi icin gerekli olabilir |
| `metadata` | Draft SQL'de yok | Import batch, validation trace ve review notlari icin dusunulebilir |
| `payload` | Draft SQL'de yok | Bilinmeyen BOM/BOP field'lari saklamak icin cazip; source-of-truth belirsizligini artirmamali |

Oneri: Production migration oncesi `metadata jsonb` ve `source_payload jsonb` ihtiyaci ayrica tartisilsin. Ana kolonlar netken ham payload sadece izleme/staging amacli tutulmali.

## Audit Alanlari

| Alan | Karar ihtiyaci |
|---|---|
| `created_by` / `updated_by` | Manuel review ve importer ayrimi gerekiyorsa eklenebilir |
| `import_batch_id` | BOM/BOP release importer icin yararli olabilir |
| `validation_status` | Header seviyesinde aggregate validation sonucu gerekebilir |
| `archived_at` / `archived_by` | `ARCHIVED` lifecycle icin audit ihtiyaci olabilir |

## Migration Riskleri

| Risk | Etki | Azaltma |
|---|---|---|
| Draft SQL'in yanlislikla runtime DB'ye uygulanmasi | Runtime sema kirliligi | Draft dosya ayrimi ve migration klasorune almama |
| Surrogate key tipi erken kilitlenmesi | Importer ve API uyumsuzlugu | ID stratejisini migration oncesi kapat |
| Cascade delete kullanimi | Master data iz kaybi | Default `RESTRICT`, archive/valid_to yaklasimi |
| Partial unique index yanlis kosulu | Multiple active release veya release blokaji | Valid window ve release lifecycle testleri |
| Payload/metadata asiri kullanimi | Sema disiplini zayiflar | JSONB'yi staging/trace ile sinirla |

## Production Migration Oncesi Kapanmasi Gerekenler

| Karar | Neden gerekli |
|---|---|
| Surrogate key tipi ve id uretim sahibi | DDL ve importer contract etkilenir |
| BOM/BOP gercek release JSON field mapping | Production importer icin gerekli |
| Validation error dictionary | Response ve test standardi icin gerekli |
| `updated_at` update mekanizmasi | Trigger/application sorumlulugu belirlenmeli |
| FK delete davranisi | Veri kaybi riskini azaltir |
| `metadata` / `payload` / `import_batch_id` ihtiyaci | Traceability ve debug ihtiyacini belirler |
| ERP hazirlik aktarim mekanizmasi | Service layer migrationdan bagimsiz olsa da data ihtiyaclarini etkileyebilir |
