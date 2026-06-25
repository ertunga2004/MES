# ERP Create / Map / Conflict Lifecycle

Bu dokuman ERP'de zaten stok karti veya urun/component kaydi varsa MESQL'in nasil davranacagini lifecycle seviyesinde tarif eder. Tablo, UI veya kod zorunlu kilmaz.

## Entity Matching Key

| MESQL entity | Matching key | F-ERP label baglami |
|---|---|---|
| Product | `product_code` | `lblMTM00_CODE` |
| Component | `component_code` | `lblMTM00_CODE` |

Sessiz overwrite yoktur. Var olan ERP kaydi yalniz uyumluysa map/skip edilir; celiski varsa conflict-report/manual review gerekir.

## Lifecycle Durumlari

| Durum | Aciklama | Ornek | MESQL aksiyonu | ERP aksiyonu | Manual review |
|---|---|---|---|---|---|
| `NOT_FOUND` | Matching key ERP'de yok | Yeni `product_code` ERP'de bulunamadi | Create candidate olustur | Yeni kayit adayi olarak ele al | Gerekebilir |
| `EXACT_MATCH` | Kod, ad, tip ve birim uyumlu | `lblMTM00_CODE`, ad ve birim ayni | Map/skip | Mevcut kaydi kullan | Gerekmez |
| `SOFT_MISMATCH` | Kritik olmayan fark var | Ad yazimi/kucuk fark | Warning ve review notu | Otomatik overwrite yok | Gerekebilir |
| `HARD_CONFLICT` | Kod ayni ama ad/tip/birim celiskili | Kod ayni, birim farkli | Conflict report olustur, aktarimi durdur | Update yapma | Zorunlu |
| `REVISION_REVIEW` | Kod uyumlu ama revision farki var | Product revision MESQL'de yeni | Revision review baslat | Revision politikasi bekle | Zorunlu olabilir |
| `MANUAL_REVIEW_REQUIRED` | Otomatik karar verilemeyen durum | Eksik unit, belirsiz type | Hold | Kullanici karari bekle | Zorunlu |

## Durumdan Duruma Gecis

| Baslangic | Kosul | Sonuc |
|---|---|---|
| `NOT_FOUND` | Kullanici create onaylar | Create candidate ERP aktarimina girer |
| `EXACT_MATCH` | Degerler uyumlu kalir | Map/skip tamamlanir |
| `SOFT_MISMATCH` | Kullanici farki kabul eder | Map/skip veya data cleanup |
| `HARD_CONFLICT` | Kullanici ERP veya MESQL degerini secmez | HOLD devam eder |
| `REVISION_REVIEW` | Revision karari verilir | Yeni revision, map veya reject |
| `MANUAL_REVIEW_REQUIRED` | Eksik karar kapanir | Uygun lifecycle durumuna doner |

## Conflict Report Alanlari

| Alan | Anlam |
|---|---|
| `conflict_id` | Conflict kaydi kimligi |
| `entity_type` | Product veya component |
| `mesql_code` | MESQL tarafindaki code |
| `erp_code` | ERP tarafindaki code |
| `field_name` | Celisen alan |
| `mesql_value` | MESQL degeri |
| `erp_value` | ERP degeri |
| `severity` | `WARN`, `HOLD`, `FAIL` |
| `recommended_action` | Onerilen karar |
| `created_at` | Conflict olusma zamani |

Bu alanlar contract seviyesindedir. Bu sprintte tablo veya UI zorunlu kilinmaz.

## Onerilen Severity

| Durum | Severity |
|---|---|
| `NOT_FOUND` | WARN veya HOLD; create politikasi netse WARN |
| `EXACT_MATCH` | PASS |
| `SOFT_MISMATCH` | WARN |
| `HARD_CONFLICT` | HOLD veya FAIL |
| `REVISION_REVIEW` | HOLD |
| `MANUAL_REVIEW_REQUIRED` | HOLD |

## Ilgili Validation Kodlari

| Validation code | Lifecycle iliskisi |
|---|---|
| `MESQL-VAL-0008 ERP_ITEM_CODE_CONFLICT` | `HARD_CONFLICT` |
| `MESQL-VAL-0009 UNIT_CODE_CONFLICT` | `HARD_CONFLICT` veya `MANUAL_REVIEW_REQUIRED` |
| `MESQL-VAL-0007 PRODUCT_REVISION_CONFLICT` | `REVISION_REVIEW` |
| `MESQL-VAL-0015 BOM_BOP_FIELD_MAPPING_UNKNOWN` | `MANUAL_REVIEW_REQUIRED` |

## Uygulama Siniri

Bu dokuman yalniz lifecycle/contract dokumanidir. Production tablo, API endpoint, UI ekrani veya ERP write davranisi zorunlu kilmaz. ERP'ye yazma mekanizmasi `erp_preparation_adapter_decision_note.md` kararlarina baglidir.
