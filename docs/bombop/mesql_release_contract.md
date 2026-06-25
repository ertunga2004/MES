# BOM/BOP -> MESQL Release Kontrati

Bu dokuman BOM/BOP programinin MESQL'e hangi uretim hazirlik verisini release edecegini is nesnesi seviyesinde tanimlar. Kod, migration veya runtime degisikligi icermez.

## 1. Amac

BOM/BOP programi, ERP/F-ERP sifira yakin veya bos baslarken uretim hazirlik verisinin ilk kaynagi olabilir. Bu kontrat, BOM/BOP tarafindan hazirlanan urun, komponent, MBOM, BOP, operasyon-istasyon eslesmesi ve paket BOM bilgisinin MESQL tarafina nasil anlamlandirilacagini tarif eder.

## 2. Kapsam

| Kapsamda | Kapsam disi |
|---|---|
| Is nesnesi seviyesinde release paketi | Kod degisikligi |
| MESQL validation beklentisi | DB migration |
| ERP hazirlik aktarimina etkisi | Runtime / Docker degisikligi |
| MES yurutmeye etkisi | BOM/BOP local DB semasini kesinlestirme |

## 3. Release Paket Mantigi

Bir BOM/BOP release paketi su is nesnelerini icerebilir:

| Parca | Anlam | Durum |
|---|---|---|
| `release_id` | Release paketini izlemek icin kimlik | Kararlastirilacak alan adi |
| `product` | Uretilecek urun master adayi | Kesin is nesnesi |
| `components` | Kullanilacak komponent/parca master adaylari | Kesin is nesnesi |
| `mbom` | Urun-komponent ihtiyac iliskisi | Kesin is nesnesi |
| `bop` | Operasyon sirasi ve rota bilgisi | Kesin is nesnesi |
| `operation_station_mapping` | Operasyon ile is merkezi/istasyon eslesmesi | Kesin is nesnesi |
| `package_bom` | Paket urunu ve paket komponent ihtiyaclari | Kesin is nesnesi |
| `revision` | Urun/hazirlik revizyonu | Unique model karari kapandi |
| `release_status` | Taslak, onayli veya uretime acik ayrimi | Deger listesi kapandi |
| `warnings/errors` | Dogrulama uyarilari ve hatalari | Format acik |

Alan adlari yukarida is paketi anlatimi icin kullanilmistir; BOM/BOP uygulamasinin nihai JSON alan adlari henuz kesin degildir.

## 4. Release Status Karari

Kabul edilen release status deger listesi:

| Status | Anlam | ERP/MES'e dagitim |
|---|---|---|
| `DRAFT` | Taslak | Hayir |
| `IN_REVIEW` | Incelemede | Hayir |
| `APPROVED` | Onaylandi ama uretime acilmadi | Hayir |
| `RELEASED` | Uretime acik release | Evet |
| `ARCHIVED` | Eski veya kapatilmis release | Hayir |
| `REJECTED` | Reddedildi | Hayir |
| `PENDING` | Staging/import bekleyen durum | Hayir |

Kural: ERP ve MES'e sadece `RELEASED` veri gider. `APPROVED` uretime cikmak icin yeterli degildir. `ARCHIVED` ve `REJECTED` uretime cikamaz.

## 5. Revision Unique Modeli

Bu model DB migration degildir; sonraki schema sprinti icin karar notudur.

| Nesne | Unique karari / onerisi |
|---|---|
| Product master | `product_code` product master seviyesinde unique olur |
| Product revision | `UNIQUE(product_id, revision_code)` |
| MBOM | `UNIQUE(product_revision_id, mbom_revision, plant_code)` |
| BOP | `UNIQUE(product_revision_id, bop_revision, plant_code)` |
| Package BOM | `UNIQUE(package_product_revision_id, package_bom_revision, plant_code)` |

Ayni `product_revision_id` + `plant_code` icin ayni anda birden fazla aktif `RELEASED` MBOM/BOP olmamalidir. Yeni release geldiginde eski release `ARCHIVED` yapilmali veya `valid_to` ile kapatilmalidir.

## 6. Bilinen Kesin Alanlar

Bu fazda kesin olan sey, alan adlarindan cok tasinacak is nesneleridir.

| Kesin bilinen | Acik / uydurulmayacak |
|---|---|
| Urun kodu, urun adi, urun tipi, birim, revizyon gibi product master anlamlari | BOM/BOP uygulamasinin gercek tablo/kolon adlari |
| Komponent kodu, komponent adi, komponent tipi, birim gibi component master anlamlari | BOM/BOP release JSON'unun nihai field adlari |
| MBOM parent/component/quantity/unit/revision/release status anlamlari | Bilinmeyen F-ERP label adlari |
| BOP operasyon sirasi, operasyon, istasyon/is merkezi, sure ve release status anlamlari | Var olmayan MESQL API endpointleri |
| Package BOM package product/component/quantity/unit/release status anlamlari | Var olmayan mevcut DB tablolarini mevcutmus gibi yazmak |

Component master icin bilinen stok label ailesi kullanilabilir: `lblMTM00_CODE`, `lblMTM00_NAME`, `lblMTMT0_CODE`, `lblMUNT0_CODE`. Component'e ozel bilinmeyen F-ERP label uydurulmaz.

## 7. Product Master Candidate

| Is alani | Anlam | MESQL validation beklentisi |
|---|---|---|
| Urun kodu | Mamul veya yari mamul aday kodu | Bos olamaz |
| Urun adi | Operator/ERP gorunumu icin ad | Bos kalirsa warning uretilebilir |
| Urun tipi | Mamul, yari mamul vb. ayrim | Deger listesi kararlastirilacak |
| Birim | Uretim ve stok birimi | Bos kalirsa ERP aktarimi riskli |
| Revizyon | Ayni urunun farkli hazirlik setlerini ayirir | `UNIQUE(product_id, revision_code)` modeline baglanir |

## 8. Component Master Candidate

| Is alani | Anlam | MESQL validation beklentisi |
|---|---|---|
| Komponent kodu | MBOM veya package BOM satirinda kullanilacak parca kodu | Bos olamaz |
| Komponent adi | Parca adi | Bos kalirsa warning uretilebilir |
| Komponent tipi | Hammadde, yari mamul, sarf vb. ayrim | Deger listesi kararlastirilacak |
| Birim | Tuketim birimi | Quantity ile uyumlu olmali |

## 9. MBOM Release

| Is alani | Anlam | Kural |
|---|---|---|
| Parent product | MBOM'un ait oldugu urun | Urun kodu ile baglanmali |
| Component | Tuketilecek komponent | Komponent kodu bos olamaz |
| Required quantity | Bir parent icin gereken miktar | Pozitif olmali |
| Unit | Tuketim birimi | Component birimiyle uyum kontrolu gerekir |
| Revision | MBOM revizyonu | `UNIQUE(product_revision_id, mbom_revision, plant_code)` onerisine uymali |
| Release status | MES/ERP aktarimina acik olup olmadigi | Sadece `RELEASED` MES/ERP'ye gider |

## 10. BOP Release

| Is alani | Anlam | Kural |
|---|---|---|
| Product | BOP'un ait oldugu urun | Product release ile uyumlu olmali |
| Operation sequence | Operasyon sirasi | Ayni urun/revizyon icinde cakismamali |
| Operation | Yapilacak is adimi | F-ERP aktariminda bilinen label `lblMFWO0_CODE` ile eslesebilir |
| Work center / station mapping | Operasyonun calisacagi is merkezi veya MES istasyonu | Canonical kaynak MESQL manufacturing domainidir |
| Setup time | Hazirlik suresi | F-ERP label `lblMMFB4_SETUP_TIME` ile aktarim adayi |
| Cycle time | Ideal islem/dongu suresi | F-ERP label `lblMMFB4_TIME` ile aktarim adayi |
| Release status | BOP'un yurutmeye acikligi | Sadece `RELEASED` MES/ERP'ye gider |

Operation/station mapping icin sahiplik karari:

| Sistem | Sorumluluk |
|---|---|
| BOM/BOP | Mapping'i MESQL'e release eder |
| MESQL manufacturing domain | Canonical mapping kaynagidir |
| MES | Mapping'i MESQL'den okur |
| `mes.station_queue` | Gunluk operasyonel siralamadir; master data otoritesi degildir |
| ERP/F-ERP | Is merkezi/operasyon bilgisini bilinen label karsiliklariyla alir: `lblMFW00_CODE`, `lblMFWO0_CODE`, `lblMMFB4_SETUP_TIME`, `lblMMFB4_TIME` |

## 11. Package BOM Release

| Is alani | Anlam | Kural |
|---|---|---|
| Package product | Paketlenecek nihai urun veya paket is emri baglami | Product release ile uyumlu olmali |
| Component code | Paket icin gereken komponent | Bos olamaz |
| Required quantity | Paket basina gereken miktar | Pozitif olmali |
| Unit | Paket komponent birimi | Quantity ile uyumlu olmali |
| Release status | Paket BOM'un yurutmeye acikligi | Sadece `RELEASED` MES/ERP'ye gider |

## 12. MESQL Validation Kurallari

| Kural | Sonuc |
|---|---|
| Urun kodu bos olamaz | FAIL |
| Komponent kodu bos olamaz | FAIL |
| Quantity pozitif olmali | FAIL |
| Operasyon sirasi cakismamali | FAIL |
| `release_status` `RELEASED` degilse MES/ERP'ye dagitilmamali | HOLD |
| Ayni urun/revizyon icin celiskili MBOM/BOP release olmamali | FAIL |
| Ayni product revision + plant icin birden fazla aktif `RELEASED` MBOM/BOP olmamali | FAIL |
| Station mapping yoksa status'a gore karar verilmeli | WARN/HOLD/FAIL |

Station mapping default karari:

| Release status | Mapping eksikse sonuc |
|---|---|
| `DRAFT` / `IN_REVIEW` | WARN |
| `APPROVED` | HOLD |
| `RELEASED` | FAIL |

MES'e dagitilacak operasyon mapping'siz olamaz.

## 13. MESQL -> ERP Hazirlik Aktarimina Etkisi

BOM/BOP release edildikten ve MESQL tarafindan dogrulandiktan sonra MESQL su hazirlik verilerini ERP/F-ERP tarafina aktarim adayi olarak hazirlayabilir:

| MESQL hazirlik verisi | ERP/F-ERP etkisi | Bilinen label / not |
|---|---|---|
| Product master candidate | Stok/urun karti adayi | `lblMTM00_CODE`, `lblMTM00_NAME`, `lblMTMT0_CODE`, `lblMUNT0_CODE` |
| Component master candidate | Stok/komponent karti adayi | `lblMTM00_CODE`, `lblMTM00_NAME`, `lblMTMT0_CODE`, `lblMUNT0_CODE`; component'e ozel bilinmeyen label uydurulmaz |
| MBOM | MRP veya uretim hazirlik girdisi | Nihai F-ERP import formati acik |
| BOP / rota / metod | Operasyon ve is merkezi hazirligi | `lblMFW00_CODE`, `lblMFWO0_CODE`, `lblMMFB4_SETUP_TIME`, `lblMMFB4_TIME` |
| Package BOM | Paketleme hazirligi | Nihai ERP aktarim detayi acik |

ERP'de stok karti zaten varsa:

| Durum | Karar |
|---|---|
| `lblMTM00_CODE` ERP'de yok | Create candidate |
| Kod var, ad/tip/birim uyumlu | Map/skip |
| Kod var, ad/tip/birim celiskili | Conflict report / manual review |
| Revizyon farki var | Revision review |

Hazirlik aktarim mekanizmasi henuz aciktir. Olasi yollar: manuel ERP girisi, Excel import, label-first JSON, REST/API entegrasyonu. Bu karar kapanana kadar Faz 2 planning block sayilir. Bu blok servis/entegrasyon katmani icindir; ortak DB taslak semasini bloklamaz.

## 14. MESQL -> MES Yurutmeye Etkisi

MES sadece release edilmis ve MESQL tarafindan dogrulanmis BOM/BOP verisini kullanmalidir.

| Yurutme etkisi | Beklenen davranis |
|---|---|
| Gunluk is emirleri | ERP'den MESQL'e gelen is emirleri, release edilmis product/BOP baglamiyla zenginlestirilir |
| Station queue | MES istasyon bazli sirayi `mes.station_queue` cekirdegi uzerinden kullanir |
| WIP uygunlugu | Paketleme komponent uygunlugu `mes.package_component_wip` ile kontrol edilir |
| Package session | `mes.package_sessions` sonraki hazirlik alanidir; start/finish eventleriyle iliskilenir |
| Release olmayan hazirlik | MES'e dagitilmaz veya kiosk yurutmede kullanilmaz |
| Mapping eksik operasyon | `RELEASED` olamaz ve MES'e dagitilamaz |

## 15. Acik Kalanlar

| Alan | Durum | Bagimlilik / blokaj |
|---|---|---|
| BOM/BOP uygulamasinin gercek local DB semasi | Acik | Importer mapping tasarimini bloklar |
| Release JSON'unun nihai alan adlari | Acik | Production importer yazimini bloklar |
| EBOM -> MBOM donusum kurali | Acik | Engineering -> manufacturing donusum surecini bloklar |
| MESQL -> ERP hazirlik aktarim mekanizmasi | Acik / Faz 2 planning block | ERP hazirlik servis entegrasyonunu bloklar; ortak DB taslak semasini bloklamaz |
| ERP kalite/OEE detay seviyesi | Kararlastirilacak | ERP export kapsam genisletmesini bloklar |
| WARN/FAIL hata kod sozlugu | Kararlastirilacak | Validation testleri ve API response standardini bloklar |

## 16. Sonraki Faz Onerisi: 3B - Shared Schema Draft

Asagidaki sema/tablo adlari bu dokumanin mevcut tablo iddiasi degildir; sonraki sprintte taslak olarak ele alinacak oneridir.

| Onerilen alan | Amac |
|---|---|
| `mesql_master.products` | Product master candidate |
| `mesql_master.components` | Component master candidate |
| `mesql_manufacturing.mbom` | MBOM release satirlari |
| `mesql_manufacturing.bop` | BOP / rota release satirlari |
| `mesql_manufacturing.operation_station_mapping` | Operasyon - is merkezi / MES istasyon eslesmesi |
| `mesql_manufacturing.package_bom` | Paket BOM release satirlari |
