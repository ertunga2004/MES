# BOM/BOP Source Payload Request

Bu dokuman, BOM/BOP kaynak sistem sahibinden istenecek ham payload paketini tanimlar. Amac, MESQL v1 importer contract icin gercek kaynak alan adlarini, status/revision davranisini ve validation sinyallerini dogrulamaktir.

## Neden Gerekli?

3E discovery sonucunda gercek BOM/BOP kaynak payload alani dogrulanmamistir. Mevcut canonical ornekler MESQL hedef modelini anlatir; kaynak sistemin gercek field adlari, nesting yapisi ve release davranisi yerine gecmez.

Bu paket gelmeden:

- Production importer v1 alan mapping'i kesinlestirilemez.
- Source-to-canonical donusum kurallari yazilamaz.
- Status/revision validation DDL veya migration sprintine girdi olamaz.
- Runtime entegrasyon endpoint veya servis sozlesmesi ilan edilemez.

## Kabul Edilen Formatlar

Kaynak sahibi asagidaki formatlardan birini veya birkacini paylasabilir:

| Format | Kabul kosulu |
| --- | --- |
| JSON export | Ham field adlari, nesting ve array yapisi korunmali. |
| CSV/XLSX export | Her sheet/table adinin kaynak sistemdeki anlami belirtilmeli. |
| SQLite/PostgreSQL schema dump | Tablo/kolon adlari ve ornek satirlar birlikte verilmeli. |
| Uygulama local DB ornegi | Kaynak uygulama field adlari korunmali; sadece deger maskelenebilir. |

Field adlari MESQL'e gore yeniden adlandirilmamalidir. Kaynak sistemde ne varsa aynen paylasilmalidir.

## Minimum Veri Seti

Asagidaki nesne ve durumlari gosteren en kucuk ornek paket yeterlidir:

| Veri grubu | Minimum beklenti |
| --- | --- |
| Product master | En az 1 bitmis urun ve varsa 1 component/stok karti ornegi. |
| Product revision/version | Urunun revizyon veya versiyon bilgisini gosteren alanlar. |
| Component list | BOM satirlarinda kullanilan component kodu, miktar ve birim alanlari. |
| MBOM header/lines | Uretim BOM basligi ve satirlari; kaynak field adlari korunmali. |
| BOP/route operations | Operasyon sira, operasyon kodu/adi ve varsa sure/work center bilgileri. |
| Operation-station/work center mapping | Operasyonun istasyon veya is merkeziyle nasil baglandigini gosteren alanlar. |
| Package BOM | Paket BOM varsa baslik ve satir ornegi; yoksa "kaynakta yok" diye belirtilmeli. |
| Release status | Kaynak sistemdeki status kodlari ve yayinlanabilir/yayinlanamaz anlamlari. |
| Release timestamp/user | Varsa release tarihi, onaylayan/yayinlayan kullanici veya benzeri audit alanlari. |
| Validation mesajlari | Kaynak sistem uyari/hata/hold mesaji uretiyorsa ornek kayit. |

## Minimum Senaryo Kapsami

Paket mumkunse asagidaki senaryolari icermelidir:

| Senaryo | Beklenti |
| --- | --- |
| Gecerli release | Uretime cikabilir bir BOM/BOP revizyonu. |
| Non-release durum | DRAFT, review, pending veya kaynak sistemdeki esit olmayan durum ornegi. |
| Eksik mapping | Operasyon-istasyon veya operasyon-work center baglantisi eksik bir ornek. |
| Validation problemi | Kaynak sistemde duplicate sira, eksik component, eksik sure veya benzeri hata varsa ornegi. |

Kaynak sistemde bu senaryolardan biri yoksa paket README'sinde "yok" olarak belirtilmelidir.

## Masking ve Gizlilik

- Musteri adi, kullanici adi, fiyat, ticari aciklama ve benzeri degerler maskelenebilir.
- Field adlari, tablo adlari, status kodlari, revision kodlari ve iliski anahtarlari maskelenmemelidir.
- Kod degerleri maskelenecekse tutarli maskeleme kullanilmalidir; ayni urun/component her dosyada ayni maskeli kodla gorunmelidir.
- Token, sifre, API key, connection string, kisisel veri veya musteriye ait gizli dokuman gonderilmemelidir.

## Teslim Paketi

Tercih edilen teslim yapisi:

```text
bombop-source-payload/
  README.md
  product_master.*
  product_revision.*
  mbom_header.*
  mbom_lines.*
  bop_header.*
  bop_operations.*
  operation_station_mapping.*
  package_bom_header.*
  package_bom_lines.*
  validation_messages.*
```

Tek dosyali JSON export da kabul edilir. Bu durumda README icinde root nesnelerin neyi temsil ettigi aciklanmalidir.

## Kabul Kriterleri

Payload paketi asagidaki kosullari saglarsa 3G kaynak payload review sprintine alinabilir:

- Ham field adlari ve kaynak yapi korunmus olmalidir.
- En az product, revision, MBOM, BOP ve release status bilgisi bulunmalidir.
- Operation-station veya operation-work center mapping kaynagi aciklanmis olmalidir.
- Release edilebilir ve release edilemez en az iki durum gorulebilmelidir.
- Component ve miktar/birim alanlari izlenebilir olmalidir.
- Package BOM varsa orneklenmeli; yoksa kaynak sahibi tarafindan yoklugu belirtilmelidir.
- Validation/uyari/hata sinyalleri varsa orneklenmeli; yoksa kaynak sahibi tarafindan yoklugu belirtilmelidir.

## Sonraki Adim

Bu paket alindiktan sonra 3G sprintinde gercek kaynak field adlari CONFIRMED olarak isaretlenir, aday/TBD alanlar ayrilir ve v1 importer icin go/no-go karari verilir.
