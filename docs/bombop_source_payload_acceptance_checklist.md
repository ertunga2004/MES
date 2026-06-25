# BOM/BOP Source Payload Acceptance Checklist

Bu checklist, kaynak payload paketinin 3G review sprintine alinmaya uygun olup olmadigini kontrol eder.

## Paket Bilgisi

| Alan | Deger |
| --- | --- |
| Kaynak sahibi |  |
| Teslim tarihi |  |
| Format |  |
| Dosya sayisi |  |
| Masking uygulandi mi? |  |
| README var mi? |  |

## Format ve Field Koruma

| Kontrol | Durum |
| --- | --- |
| Dosyalar acilabiliyor veya parse edilebiliyor. |  |
| Kaynak field adlari korunmus. |  |
| Tablo/sheet/root nesne anlamlari aciklanmis. |  |
| Dosyalar arasi anahtar iliskileri anlasiliyor. |  |
| MESQL canonical field adlarina manuel rename yapilmamis. |  |

## Product ve Revision

| Kontrol | Durum |
| --- | --- |
| Product code kaynagi goruluyor. |  |
| Product name kaynagi goruluyor. |  |
| Item/product type kaynagi goruluyor. |  |
| Base unit kaynagi goruluyor. |  |
| Product revision/version kaynagi goruluyor. |  |
| Revision ile product iliskisi goruluyor. |  |

## Component ve MBOM

| Kontrol | Durum |
| --- | --- |
| Component item kaynagi goruluyor. |  |
| Component quantity kaynagi goruluyor. |  |
| Component unit kaynagi goruluyor. |  |
| MBOM header kaydi goruluyor. |  |
| MBOM revision veya esdeger alan goruluyor. |  |
| MBOM line iliskisi goruluyor. |  |
| Plant/fabrika alani varsa goruluyor. |  |

## BOP ve Operation

| Kontrol | Durum |
| --- | --- |
| BOP/route header kaydi goruluyor. |  |
| BOP revision veya esdeger alan goruluyor. |  |
| Operation listesi goruluyor. |  |
| Operation sequence/sira alani goruluyor. |  |
| Operation code kaynagi goruluyor. |  |
| Operation name kaynagi goruluyor. |  |
| Setup/run time alanlari varsa goruluyor. |  |

## Mapping

| Kontrol | Durum |
| --- | --- |
| Operation-station veya operation-work center iliskisi goruluyor. |  |
| Station/work center master kaynagi aciklanmis. |  |
| Eksik mapping ornegi varsa paylasilmis. |  |
| Mapping'siz operasyonun release davranisi aciklanmis. |  |

## Package BOM

| Kontrol | Durum |
| --- | --- |
| Package BOM kaynakta varsa header ornegi var. |  |
| Package BOM kaynakta varsa line ornegi var. |  |
| Package product revision veya esdeger iliski goruluyor. |  |
| Package BOM yoksa kaynak sahibi bunu acikca belirtmis. |  |

## Release Lifecycle

| Kontrol | Durum |
| --- | --- |
| Kaynak status kodlari goruluyor. |  |
| Release edilebilir status aciklanmis. |  |
| Release edilemez status ornegi var. |  |
| Pending/staging benzeri durum varsa aciklanmis. |  |
| Archive/reject/cancel benzeri durum varsa aciklanmis. |  |
| Eski release'in nasil kapandigi aciklanmis. |  |

## Validation / Warning / Error

| Kontrol | Durum |
| --- | --- |
| Kaynak validation mesaji varsa orneklenmis. |  |
| Warning/hold/error ayrimi varsa aciklanmis. |  |
| Eksik mapping validation davranisi aciklanmis. |  |
| Duplicate sequence veya benzeri problem ornegi varsa paylasilmis. |  |
| Validation yoksa kaynak sahibi yoklugunu belirtmis. |  |

## Guvenlik ve Masking

| Kontrol | Durum |
| --- | --- |
| Token, sifre, API key veya connection string yok. |  |
| Kisisel veri yok veya maskelenmis. |  |
| Ticari/gizli degerler maskelenirken iliski anahtarlari korunmus. |  |
| Ayni kodlar tum dosyalarda tutarli maskelenmis. |  |

## Kabul Karari

| Karar | Anlam |
| --- | --- |
| ACCEPT | 3G source payload review baslayabilir. |
| ACCEPT_WITH_GAPS | Review baslayabilir; eksik alanlar ayrica kaynak sahibine geri sorulur. |
| REJECT_NEEDS_MORE_SOURCE_DATA | Field/status/revision/mapping dogrulanamadigi icin yeni paket gerekir. |

Secilen karar:

```text

```

Acik kalan eksikler:

```text

```
