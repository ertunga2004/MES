# BOM/BOP Release Importer Contract

Bu dokuman BOM/BOP programindan MESQL'e gelecek release paketinin is nesnesi seviyesinde importer contract'ini tarif eder.

Onemli: BOM/BOP uygulamasinin gercek JSON alan adlari henuz bilinmiyor. Bu dokumandaki alanlar "onerilen canonical alan" olarak okunmalidir; gercek BOM/BOP field mapping sonraki fazda ayrica kapanacaktir.

## Amac

BOM/BOP hazirlik paketini MESQL tarafinda parse, normalize, validate, stage ve release edilebilir hale getirmek.

## Kapsam Disi

| Kapsam disi | Not |
|---|---|
| Production importer kodu | Bu dokuman kod yazmaz |
| DB migration | Draft contract'tir |
| Runtime MES davranisi | Kiosk/dashboard akisi degismez |
| Gercek BOM/BOP JSON field isimleri | Bilinmedigi icin uydurulmaz |
| MESQL API endpoint adlari | Henuz acik |

## Release Package Genel Yapisi

| Onerilen canonical alan | Is nesnesi anlami | Zorunluluk |
|---|---|---|
| `release_id` | Release paket kimligi | Onerilir |
| `source_system` | BOM/BOP kaynak sistem adi | Onerilir |
| `released_at` | Kaynak sistemde release zamani | Onerilir |
| `release_status` | `DRAFT`, `IN_REVIEW`, `APPROVED`, `RELEASED`, `ARCHIVED`, `REJECTED`, `PENDING` | Zorunlu |
| `product` | Product master candidate | Zorunlu |
| `product_revision` | Product revision candidate | Zorunlu |
| `components` | Component master candidate listesi | MBOM/package varsa zorunlu |
| `mbom` | MBOM header ve line bilgisi | Uretim hazirlik icin beklenir |
| `bop` | BOP header ve operation bilgisi | MES yurutme icin beklenir |
| `operation_station_mapping` | Operation -> station/work center eslesmesi | MES dagitim icin zorunlu |
| `package_bom` | Package BOM header ve line bilgisi | Paketleme varsa zorunlu |
| `validation` | Kaynak validation ozeti | Onerilir |

## Product Candidate Canonical Alanlari

| Onerilen canonical alan | Anlam | F-ERP label baglami |
|---|---|---|
| `product_code` | Urun/stok kodu | `lblMTM00_CODE` |
| `product_name` | Urun/stok adi | `lblMTM00_NAME` |
| `product_type` | Stok tipi | `lblMTMT0_CODE` |
| `unit_code` | Birim | `lblMUNT0_CODE` |
| `source_system` | Kaynak sistem | Yok |

## Component Candidate Canonical Alanlari

| Onerilen canonical alan | Anlam | F-ERP label baglami |
|---|---|---|
| `component_code` | Komponent/stok kodu | `lblMTM00_CODE` |
| `component_name` | Komponent/stok adi | `lblMTM00_NAME` |
| `component_type` | Stok tipi | `lblMTMT0_CODE` |
| `unit_code` | Birim | `lblMUNT0_CODE` |
| `source_system` | Kaynak sistem | Yok |

Component'e ozel bilinmeyen F-ERP label uydurulmaz.

## MBOM Canonical Alanlari

| Onerilen canonical alan | Anlam | Validation |
|---|---|---|
| `product_revision_ref` | MBOM'un ait oldugu product revision | Zorunlu |
| `mbom_revision` | MBOM revision kodu | Zorunlu |
| `plant_code` | Plant/tesis ayrimi | Zorunlu |
| `release_status` | MBOM release durumu | Bilinen listeden olmali |
| `lines` | Component ihtiyac satirlari | Bos olmamali |
| `line_no` | Satir numarasi | Pozitif olmali |
| `component_ref` | Component referansi | Zorunlu |
| `required_quantity` | Gerekli miktar | Pozitif olmali |
| `unit_code` | Tuketim birimi | Uyum kontrolu gerekir |

## BOP Canonical Alanlari

| Onerilen canonical alan | Anlam | F-ERP label baglami |
|---|---|---|
| `product_revision_ref` | BOP'un ait oldugu product revision | Yok |
| `bop_revision` | BOP revision kodu | Yok |
| `plant_code` | Plant/tesis ayrimi | Yok |
| `release_status` | BOP release durumu | Yok |
| `operation_sequence` | Operasyon sirasi | Yok |
| `operation_code` | Operasyon kodu | `lblMFWO0_CODE` |
| `operation_name` | Operasyon adi | Yok |
| `setup_time_seconds` | Hazirlik suresi | `lblMMFB4_SETUP_TIME` |
| `cycle_time_seconds` | Ideal cycle/islem suresi | `lblMMFB4_TIME` |

## Operation/Station Mapping Canonical Alanlari

| Onerilen canonical alan | Anlam | F-ERP label baglami |
|---|---|---|
| `operation_ref` | BOP operation referansi | Yok |
| `station_code` | MES istasyon kodu | Yok |
| `work_center_code` | ERP/F-ERP is merkezi | `lblMFW00_CODE` |
| `mapping_status` | Mapping release durumu | Yok |
| `validation_level` | `PASS`, `WARN`, `HOLD`, `FAIL` | Yok |

Canonical kaynak MESQL manufacturing domainidir. `mes.station_queue` gunluk operasyonel queue'dur, master data degildir.

## Package BOM Canonical Alanlari

| Onerilen canonical alan | Anlam | Validation |
|---|---|---|
| `package_product_revision_ref` | Package product revision referansi | Zorunlu |
| `package_bom_revision` | Package BOM revision kodu | Zorunlu |
| `plant_code` | Plant/tesis ayrimi | Zorunlu |
| `release_status` | Package BOM release durumu | Bilinen listeden olmali |
| `lines` | Paket komponent satirlari | Bos olmamali |
| `component_ref` | Component referansi | Zorunlu |
| `required_quantity` | Paket basina gerekli miktar | Pozitif olmali |
| `unit_code` | Birim | Uyum kontrolu gerekir |
| `line_no` | Satir numarasi | Pozitif olmali |

## Validation Akisi

| Asama | Amac | Cikti |
|---|---|---|
| Parse | Kaynak paketi okunabilir hale getirmek | Parse sonucu veya format hatasi |
| Normalize | Kaynak alanlari canonical alanlara eslemek | Canonical is nesneleri |
| Validate | Kural, unique ve mapping kontrolleri | `PASS`, `WARN`, `HOLD`, `FAIL` |
| Stage | Gecerli/inceleme bekleyen veriyi staging'e almak | Review edilebilir paket |
| Release | Sadece uygun `RELEASED` veriyi dagitim adayina almak | MES/ERP dagitim adayi |
| Reject/Hold | Hata veya karar bekleyen paketi durdurmak | Hata sozlugu ve review aksiyonu |

## Mapping Eksikligi Defaultlari

| Release status | Mapping eksikse |
|---|---|
| `DRAFT` / `IN_REVIEW` | WARN |
| `APPROVED` | HOLD |
| `RELEASED` | FAIL |

MES'e sadece `RELEASED` ve validation `PASS` olan veri gider. ERP'ye sadece `RELEASED` veri gider.

## Acik Kalan Gercek BOM/BOP Field Mapping

| Acik konu | Blokladigi is |
|---|---|
| Gercek release package field isimleri | Production importer |
| Product/component field mapping | Normalize asamasi |
| MBOM/BOP/package nested structure | Parser ve validation |
| Operation/station mapping kaynak yapisi | MES dagitim validation |
| Kaynak warning/error formatlari | Validation sozlugu entegrasyonu |
