# BOM/BOP Source Owner Questionnaire

Bu soru seti BOM/BOP kaynak sistem sahibinden gercek veri yapisini ogrenmek icindir. Cevaplarda MESQL canonical alan adlari degil, kaynak sistemdeki gercek tablo/field/status adlari kullanilmalidir.

## 1. Kaynak Sistem ve Veri Saklama

| Soru | Cevap |
| --- | --- |
| BOM/BOP verisi hangi uygulama veya modulde tutuluyor? |  |
| Veri tabani tipi veya export formati nedir? |  |
| Ham export almak icin tercih edilen yol nedir? |  |
| Field adlari export sirasinda degisiyor mu? |  |
| Bir urun/revizyon/BOM/BOP kaydi icin benzersiz kaynak anahtarlar nelerdir? |  |

## 2. Product Master

| Soru | Cevap |
| --- | --- |
| Urun kodu hangi field ile temsil edilir? |  |
| Urun adi hangi field ile temsil edilir? |  |
| Urun tipi veya stok tipi hangi field ile temsil edilir? |  |
| Temel birim hangi field ile temsil edilir? |  |
| Product master seviyesinde kod unique midir? |  |

## 3. Revision / Version

| Soru | Cevap |
| --- | --- |
| Urun revizyonu veya versiyonu hangi field ile temsil edilir? |  |
| Revizyon product master'dan ayri bir nesne midir? |  |
| Ayni urun icin birden fazla aktif revizyon olabilir mi? |  |
| Eski revizyonlar nasil kapatilir veya arsivlenir? |  |
| valid_from / valid_to benzeri alanlar var mi? |  |

## 4. MBOM

| Soru | Cevap |
| --- | --- |
| MBOM baslik kaydi hangi tablo/nesnede tutulur? |  |
| MBOM revizyonu hangi field ile temsil edilir? |  |
| Plant/fabrika bilgisi hangi field ile temsil edilir? |  |
| MBOM satirlari hangi tablo/nesnede tutulur? |  |
| Parent item ve component item kaynak field adlari nelerdir? |  |
| Component miktar ve birim field adlari nelerdir? |  |
| Satir sirasi veya pozisyon numarasi var mi? |  |

## 5. BOP / Route / Operation

| Soru | Cevap |
| --- | --- |
| BOP veya rota baslik kaydi hangi tablo/nesnede tutulur? |  |
| BOP revizyonu hangi field ile temsil edilir? |  |
| Operasyon satirlari hangi tablo/nesnede tutulur? |  |
| Operasyon sirasi hangi field ile temsil edilir? |  |
| Operasyon kodu ve adi hangi field'lar ile temsil edilir? |  |
| Setup time ve run/process time alanlari var mi? |  |
| Operasyonlar MBOM satirlariyla iliskili mi, yoksa urun revizyonuna mi bagli? |  |

## 6. Istasyon / Work Center Mapping

| Soru | Cevap |
| --- | --- |
| Operasyonun istasyon veya work center baglantisi hangi field ile kurulur? |  |
| Istasyon master data nerede tutulur? |  |
| Work center master data nerede tutulur? |  |
| Bir operasyon birden fazla istasyonda calisabilir mi? |  |
| Eksik mapping kaynak sistemde nasil raporlanir? |  |

## 7. Package BOM

| Soru | Cevap |
| --- | --- |
| Paket BOM kaynak sistemde ayri bir nesne mi? |  |
| Package product revision hangi field ile temsil edilir? |  |
| Package BOM revizyonu hangi field ile temsil edilir? |  |
| Paket satirlarindaki component kodu, miktar ve birim field adlari nelerdir? |  |
| Package BOM yoksa bu durum kaynak sistemde nasil anlasilir? |  |

## 8. Release Lifecycle / Status

| Soru | Cevap |
| --- | --- |
| Kaynak sistemde tum status kodlari nelerdir? |  |
| Hangi status uretime yayinlanabilir kabul edilir? |  |
| Hangi status staging/import bekleyen durumdur? |  |
| Arsiv veya iptal/red durumlari nasil temsil edilir? |  |
| Release tarihi ve release eden kullanici field'lari var mi? |  |
| Yeni release geldiginde eski release nasil kapanir? |  |

## 9. Validation / Warning / Error

| Soru | Cevap |
| --- | --- |
| Kaynak sistem validation mesaji uretiyor mu? |  |
| Warning, hold ve error ayrimi var mi? |  |
| Eksik operasyon mapping'i hangi severity ile raporlanir? |  |
| Duplicate operation sequence nasil yakalanir? |  |
| Validation mesajlarinin kodu, metni ve hedef field bilgisi var mi? |  |

## 10. ERP / F-ERP Aktarimi

| Soru | Cevap |
| --- | --- |
| BOM/BOP kaynak sistemi ERP'ye hazirlik export'u uretiyor mu? |  |
| Export manuel mi, Excel mi, JSON mu, API mi? |  |
| ERP stok karti zaten varsa kaynak sistem nasil davranir? |  |
| Work center/operation aktarimi icin mevcut field veya label eslesmesi var mi? |  |
| ERP aktarimi kaynak payload ile ayni veri modelinden mi uretilir? |  |

## 11. Kod Listeleri ve Sozlukler

| Soru | Cevap |
| --- | --- |
| Item type kod listesi nedir? |  |
| Unit of measure kod listesi nedir? |  |
| Plant kod listesi nedir? |  |
| Operation type veya route type kod listesi var mi? |  |
| Status kodlarinin insan okunur aciklamalari var mi? |  |

## 12. Turetilen Alanlar

| Soru | Cevap |
| --- | --- |
| Hangi alanlar kullanici tarafindan girilir? |  |
| Hangi alanlar sistem tarafindan hesaplanir? |  |
| Hangi alanlar baska tablodan lookup ile gelir? |  |
| Export sirasinda eklenen ama kaynakta saklanmayan alan var mi? |  |
