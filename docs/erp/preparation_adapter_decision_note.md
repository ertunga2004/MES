# ERP Preparation Adapter Decision Note

Bu dokuman MESQL -> ERP/F-ERP uretim hazirlik aktarim mekanizmasi icin karar notudur. Kod, runtime veya production migration degisikligi degildir.

## Problem

ERP/F-ERP sifira yakin baslayabilir. Stok karti, MBOM, rota/metod ve paket BOM hazirlik verisi BOM/BOP tarafindan MESQL'e release edilecek; MESQL bu veriyi dogrulayip ERP/F-ERP tarafina aktarim adayi haline getirecek.

Nihai aktarim mekanizmasi henuz aciktir. Bu konu Faz 2 servis/entegrasyon katmanini bloklar, ancak ortak DB taslak semasini bloklamaz.

## Alternatifler

| Alternatif | Avantaj | Risk | Ne zaman secilmeli | MVP uygunluk |
|---|---|---|---|---|
| Manuel ERP girisi | En dusuk teknik entegrasyon riski | Cift giris, insan hatasi, izlenebilirlik zayif | Cok az veri ve erken demo | Kisa demo icin uygun, surdurulebilir degil |
| Excel/CSV import | F-ERP kaynaklari workbook/import sinirina yakin | Kolon/format drift riski | ERP import sablonu netse | MVP icin uygun |
| Label-first JSON export | Mevcut F-ERP JSON sozlesmesiyle uyumlu dusunulebilir | Hazirlik master import object'leri net degil | Label registry ve import katmani netlesirse | MVP icin uygun aday |
| REST/API entegrasyonu | Otomasyon ve hata yonetimi guclu | API erisimi, auth, lifecycle ve retry karmasikligi | ERP API olgun ve erisilebilir oldugunda | Sonraki faz icin daha uygun |

## Bilinen F-ERP Label Siniri

Bilinmeyen F-ERP label uydurulmaz.

| Is anlami | Bilinen label |
|---|---|
| Stok/urun/component kodu | `lblMTM00_CODE` |
| Stok/urun/component adi | `lblMTM00_NAME` |
| Stok tipi | `lblMTMT0_CODE` |
| Birim | `lblMUNT0_CODE` |
| Lot kodu | `lblMTML0_CODE` |
| Parti no | `lblMTML0_PRTY_NO` |
| Is merkezi | `lblMFW00_CODE` |
| Operasyon | `lblMFWO0_CODE` |
| Hazirlik suresi | `lblMMFB4_SETUP_TIME` |
| Ideal cycle/islem suresi | `lblMMFB4_TIME` |

## Stok Karti Create/Map/Conflict Lifecycle

| Durum | MESQL karari | ERP etkisi |
|---|---|---|
| Code yok | Create candidate | Yeni stok/urun/component adayi |
| Code var ve uyumlu | Map/skip | Sessiz overwrite yok; mevcut kayda map edilir |
| Code var ama ad/tip/birim celiskili | Conflict-report/manual review | Otomatik update yok |
| Revision farki var | Revision review | Revizyon karari beklenir |

Entity matching key: `product_code` / `component_code` -> `lblMTM00_CODE`.

## F-ERP Quantity Label Eksikligi

F-ERP stok hareket satiri icin net quantity label'i kaynak sozlesmede kapali degildir. Mevcut export sozlesmesinde miktar `qty` alaninda acik sekilde tasinir ve warning eklenir.

Bu durum resmi stok hareket import'u icin acik risktir. Hazirlik master aktarimi tasarlanabilir; ancak resmi stok hareket import kesinlestirmesi icin quantity label karari kapanmalidir.

## Onerilen MVP Karari

| Faz | Oneri |
|---|---|
| MVP / erken entegrasyon | Excel/CSV veya label-first JSON staging |
| Review ve conflict handling | MESQL tarafinda conflict report/manual review |
| Sonraki faz | REST/API entegrasyonu |

Gerekce: Excel/CSV veya label-first JSON staging, workbook ve label-first kaynaklarla daha uyumlu ve daha az runtime riski tasir. REST/API entegrasyonu auth, retry, idempotency ve lifecycle netlestikten sonra ele alinmalidir.

## Acik Kalanlar

| Alan | Blokladigi is |
|---|---|
| ERP hazirlik import object/format karari | Faz 2 adapter implementasyonu |
| Excel/CSV sablon kolonlari | Staging format standardi |
| Label-first JSON hazirlik master semasi | JSON export contract |
| REST/API erisim ve auth modeli | Otomatik entegrasyon |
| Quantity label karari | Resmi stok hareket import'u |
| Conflict report onay akisi | Manual review lifecycle |
