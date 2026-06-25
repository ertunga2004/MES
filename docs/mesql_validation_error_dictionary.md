# MESQL Validation Error Dictionary

Bu dokuman MESQL shared schema ve BOM/BOP release importer icin standart validation severity ve hata kodlarini tanimlar. Kod veya migration degisikligi degildir.

## Severity Tanimlari

| Severity | Anlam | Dagitim etkisi |
|---|---|---|
| `PASS` | Kural gecildi | Dagitim icin uygun olabilir |
| `WARN` | Uyari var, taslak/inceleme akisi devam edebilir | MES/ERP dagitimi icin ek kontrol gerekir |
| `HOLD` | Karar veya manual review beklenir | Dagitim durur |
| `FAIL` | Kural ihlali var | Dagitim engellenir |

MES'e sadece `RELEASED` ve validation `PASS` olan veri gider. ERP'ye sadece `RELEASED` veri gider.

## Hata Kod Formati

Format:

```text
MESQL-VAL-XXXX
```

`XXXX` dort haneli numerik siradir. Kodlar kararlastiktan sonra anlamlari geriye donuk degistirilmemelidir.

## Minimum Hata Kodlari

| Code | Name | Default severity | Aciklama | Blokladigi akis | Onerilen aksiyon |
|---|---|---|---|---|---|
| `MESQL-VAL-0001` | `PRODUCT_CODE_MISSING` | FAIL | Product candidate icin urun kodu yok | Product import, ERP/MES dagitim | Kaynak BOM/BOP product kodunu tamamla |
| `MESQL-VAL-0002` | `COMPONENT_CODE_MISSING` | FAIL | Component candidate icin komponent kodu yok | MBOM/package BOM import | Component kodunu tamamla |
| `MESQL-VAL-0003` | `QUANTITY_NOT_POSITIVE` | FAIL | Required quantity sifir veya negatif | MBOM/package BOM release | Miktari pozitif degerle duzelt |
| `MESQL-VAL-0004` | `DUPLICATE_OPERATION_SEQUENCE` | FAIL | Ayni BOP icinde operation sequence tekrar ediyor | BOP release, MES yurutme | Operasyon sirasini tekil hale getir |
| `MESQL-VAL-0005` | `RELEASED_OPERATION_MAPPING_MISSING` | FAIL | `RELEASED` operasyon icin station/work center mapping eksik | MES dagitim | Mapping ekle veya release'i geri al |
| `MESQL-VAL-0006` | `APPROVED_OPERATION_MAPPING_MISSING` | HOLD | `APPROVED` operasyon icin mapping eksik | Release onayi | Mapping ekle veya review karari ver |
| `MESQL-VAL-0007` | `PRODUCT_REVISION_CONFLICT` | FAIL | Ayni product/revision icin celiskili kayit var | Product revision import | Revision conflict review yap |
| `MESQL-VAL-0008` | `ERP_ITEM_CODE_CONFLICT` | HOLD | ERP'deki `lblMTM00_CODE` ile MESQL kaydi ad/tip/birim acisindan celisiyor | ERP hazirlik aktarimi | Conflict report ve manual review |
| `MESQL-VAL-0009` | `UNIT_CODE_CONFLICT` | HOLD | MESQL unit ile ERP/BOM/BOP unit uyumsuz | ERP aktarimi, BOM validation | Birim mapping/duzeltme yap |
| `MESQL-VAL-0010` | `UNKNOWN_RELEASE_STATUS` | FAIL | Release status kabul edilen listede degil | Import ve release | Status degerini duzelt |
| `MESQL-VAL-0011` | `MULTIPLE_ACTIVE_RELEASED_MBOM` | FAIL | Ayni product revision + plant icin birden fazla aktif `RELEASED` MBOM var | MES/ERP dagitim | Eski release'i `ARCHIVED` yap veya `valid_to` kapat |
| `MESQL-VAL-0012` | `MULTIPLE_ACTIVE_RELEASED_BOP` | FAIL | Ayni product revision + plant icin birden fazla aktif `RELEASED` BOP var | MES yurutme | Eski release'i `ARCHIVED` yap veya `valid_to` kapat |
| `MESQL-VAL-0013` | `PACKAGE_BOM_COMPONENT_MISSING` | FAIL | Package BOM satiri component referansi bulamiyor | Paket BOM release | Component master adayini ekle veya referansi duzelt |
| `MESQL-VAL-0014` | `FERP_QUANTITY_LABEL_MISSING` | WARN | F-ERP stok hareket satiri quantity label'i net degil; `qty` warning ile tasiniyor | Resmi stok hareket import kesinlestirme | F-ERP tarafinda quantity label kararini kapat |
| `MESQL-VAL-0015` | `BOM_BOP_FIELD_MAPPING_UNKNOWN` | HOLD | Gercek BOM/BOP field mapping bilinmiyor | Production importer | Kaynak field mapping dokumanini tamamla |

## Severity Override Kurali

Default severity, minimum davranistir. Importer veya review katmani daha yuksek severity'ye cikarabilir; daha dusuk severity'ye dusurmek icin explicit manual review gerekir.

| Ornek | Default | Override |
|---|---|---|
| Mapping eksigi `DRAFT` / `IN_REVIEW` | WARN | Review gerekirse HOLD |
| Mapping eksigi `APPROVED` | HOLD | Release blokajinda FAIL |
| Mapping eksigi `RELEASED` | FAIL | Dusurulemez |

## Response Icin Onerilen Alanlar

| Alan | Anlam |
|---|---|
| `code` | `MESQL-VAL-XXXX` formundaki hata kodu |
| `name` | Makine okunur hata adi |
| `severity` | `PASS`, `WARN`, `HOLD`, `FAIL` |
| `entity_type` | Product, component, MBOM, BOP, mapping, package BOM vb. |
| `entity_ref` | Kaynak veya canonical referans |
| `message` | Kisa aciklama |
| `recommended_action` | Operator/muhendis aksiyonu |
