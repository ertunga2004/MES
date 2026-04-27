# FERP Integration

## Mevcut Durum

FERP entegrasyonu icin bugunku birincil veri siniri gunluk Excel workbook'tur. Sistem artik CSV merkezli dusunulmez. Backend, operasyon ve OEE olaylarini workbook sheet'lerine yazar; sonraki FERP katmani bu workbook'tan veya workbook'tan turetilen normalize JSON cikisindan beslenecektir.

## Neden Workbook Merkezli

- saha operasyonu zaten Excel tabanli veritabani beklentisine kaymistir
- workbook, operator ve muhendis tarafinda dogrudan acilip kontrol edilebilir
- tek dosya icinde olay, olcum, tamamlanan urun ve vision akisini bir arada tutar
- FERP'e gidecek alanlari sheet bazli ve kontrollu sekilde tasimaya izin verir

## Aktif Veri Sinirlari

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
- `logs\oee_runtime_state.json`

Yardimci legacy referanslar:

- `logs\log_YYYY-MM-DD.txt`
- `logs\tablet_log_YYYY-MM-DD.txt`
- eski Node-RED akisini yerel arsivden anlamak

## Onerilen Entegrasyon Akisi

1. `mes_web` workbook'u gunluk olarak doldurur.
2. Workbook icindeki ilgili sheet ve kolonlar normalize veri siniri olarak kabul edilir.
3. Ayrica gerekiyorsa workbook'tan FERP icin JSON cikti uretilir.
4. FERP import katmani bu JSON veya workbook uzerinden calisir.

## Sheet Bazli Roller

- `1_Olay_Logu`
  - operasyon olaylarinin normalize edilmis akisi
- `2_Olcumler`
  - olcum ve siniflandirma metrikleri
- `4_Uretim_Tamamlanan`
  - tamamlanan urun kayitlari
- `5_OEE_Anliklari`
  - OEE snapshot ve tablet ozetleri
- `6_Vision`
  - pasif vision capraz kontrolu
- `99_Raw_Logs`
  - ham satirlarin denetim izi

## FERP Icın Hazirlik Kurallari

- workbook sheet adlari keyfi degistirilmemelidir
- kolonlar eklenebilir ama mevcut anlami bozulmamalidir
- tarih ve saat alanlari tek formatta tutulmalidir
- bir urun kaydi tamamlanmis urun sheet'i ile olay logu arasinda izlenebilir olmalidir

## FERP Uretim / Is Emri JSON Siniri

`C:\Users\acer\Downloads\GÜNCEL ERP 1.xlsx` dosyasinda is emri alanlari `ÜRETİM YÖNETİMİ` sheet'i altinda geciyor. MES tarafinda import icin canonical JSON anahtarlari korunur; FERP'ten gelen `lbl...` kodlari ayni alanlarin alias'i olarak kabul edilir.

Ilgili FERP bloklari:

- `Planlama Is Emirleri` / `mym4104`
- `Is Emirleri` / `mym4004`
- `Mamul Is Emirleri` / `mym4008`
- `Yari Mamul Is Emirleri` / `mym4009`
- `Stok Degisim Is Emirleri` / `mym4043`
- `Tamirat Is Emirleri` / `mym4086`
- celik yapi, assembly, fason ve tekstil is emri bloklari; ayni `MMFB0`, `MTM`, `MFW`, `MFWO`, `MMFB4` label ailesini kullanir.

Canonical MES JSON alanlari:

| MES JSON | FERP label | FERP ekran etiketi | Not |
| --- | --- | --- | --- |
| `date` | `lblMMFB0_DATE` | Tarih | Is emri tarihi |
| `order_id` / `orderId` | `lblMMFB0_NUMBER` | Sistem No | MES tarafinda is emri id'si olarak kullanilir |
| `system_no` / `systemNo` | `lblMMFB0_NUMBER` | Sistem No | FERP sistem numarasi |
| `sequence_no` / `sequenceNo` | `lblMMFB0_PRNT_ORDER` | Sira | Siralama icin |
| `locked` | `lblPRNT_ORDER_UPD` | Kilit | `e/evet/true/1` true kabul edilir |
| `stock_type` / `stockType` | `lblMTMT0_CODE` | Stok/Servis | Mamul, yari mamul vb. |
| `stock_code` / `stockCode` | `lblMTM00_CODE` | Stok Kodu | MES match/product fallback'i |
| `unit` | `lblMUNT0_CODE` | Birim | Ornek: ADET |
| `stock_name` / `stockName` | `lblMTM00_NAME` | Stok Adi | Operator gorunumu |
| `method_code` / `methodCode` | `lblMTMM0_CODE` | Metod Kodu | Uretim metodu |
| `qty` / `quantity` | `lblMMFB0_QTY` | Miktar | Hedef adet |
| `project_code` / `projectCode` | `lblFPJ00_ID` | Proje | Opsiyonel |
| `description` | `lblMMFB0_DESC` | Aciklama | Opsiyonel |
| `lot_code` / `lotCode` | `lblMTML0_CODE` | Lot Kodu | Bazi is emri tiplerinde var |
| `cut_code` / `cutCode` | `lblFPJ09_CODE` | Kesim Kodu | Celik yapi bloklarinda var |
| `party_no` / `partyNo` | `lblMTML0_PRTY_NO` | Parti No | Tamirat vb. bloklarda var |
| `work_center_code` / `workCenterCode` | `lblMFW00_CODE` | Is Merkezi | OEE/operasyon kirilimi |
| `work_station_code` / `workStationCode` | `lblMFW01_CODE` | Is Istasyonu | Opsiyonel |
| `operation_code` / `operationCode` | `lblMFWO0_CODE` | Operasyon | Operasyon kodu |
| `setup_time_sec` / `setupTimeSec` | `lblMMFB4_SETUP_TIME` | Hazirlik Suresi (Saniye) | MES icinde ms'e cevrilir |
| `worker_count` / `workerCount` | `lblMMFB4_WORKER_COUNT` | Isci Sayisi | Opsiyonel |
| `cycle_time_sec` / `cycleTimeSec` | `lblMMFB4_TIME` | Sure (Saniye) | Is emri bazli ideal cycle |
| `shift_code` / `shiftCode` | `lblMMFB4_SHIFT_TYPE` | Vardiya | Opsiyonel |
| `startedBy` | `lblFCR00_ACC_CODE_PR` | Isi Yapan | FERP operator/cari personel kodu |
| `startedByName` | `lblFCR00_NAME_PR` | Adi | FERP operator/cari personel adi |

Ornek kabul edilen FERP label JSON:

```json
{
  "erp_type": "Is Emirleri",
  "lblMMFB0_DATE": "2026-04-27",
  "lblMMFB0_NUMBER": "41040001",
  "lblMMFB0_PRNT_ORDER": 10,
  "lblMTMT0_CODE": "Mamul",
  "lblMTM00_CODE": "BOX-RED",
  "lblMUNT0_CODE": "ADET",
  "lblMTM00_NAME": "Kirmizi Kutu",
  "lblMTMM0_CODE": "STD-RED",
  "lblMMFB0_QTY": 2,
  "lblMFW00_CODE": "KNV-01",
  "lblMFWO0_CODE": "SORT",
  "lblMMFB4_SETUP_TIME": 30,
  "lblMMFB4_WORKER_COUNT": 1,
  "lblMMFB4_TIME": 15,
  "lblMMFB4_SHIFT_TYPE": "SHIFT-A"
}
```

## Tamamlanan Urun ve Stok Siniri

MES tarafinda tutulacak stok resmi ERP stoku degil, operasyonel oturum stokudur. Bu nedenle sistem acilinca eldeki kutu sayisi biliniyorsa MES bunu operator ve OEE akisi icin kullanabilir; sistem/vardiya kapanisinda bu sayacin sifirlanmasi kabul edilebilir. Bu sifirlama ERP'deki hammadde stokunu etkilememelidir.

Onerilen sahiplik:

- MES, sensor okumasindan sonra urunu `yari mamul / isleniyor` gibi operasyonel durumda izler.
- MES, robot kol isi bitirdiginde urunu `tamamlandi` olarak isaretler ve iz kaydini `4_Uretim_Tamamlanan` / olay logu tarafinda saklar.
- ERP, resmi hammadde cikisi, yari mamul transferi ve mamul girisi muhasebesini yapar.
- MES -> FERP aktarimi, resmi stok hareketini dogrudan mutlak stok olarak degil, islenebilir hareket adayi olarak uretmelidir.

FERP dosyasinda stok hareketleri `MALZEME YONETIMI` sheet'i altinda ayriliyor:

| Akis | FERP blok | Nesne | Kullanilacak yer |
| --- | --- | --- | --- |
| Mamul girisi | `Giris Hareketleri` | `mym2008` | Robot kol sonunda kabul edilen/tamamlanan urun |
| Hammadde cikisi | `Cikis Hareketleri` | `mym2010` | Is emri icin tuketilen kutu/adet |
| Depo/lokasyon transferi | `Onayli Depo Transferleri` | `mym2056` | ERP yari mamul stokunu ayri depo/lokasyonla takip edecekse |

Bu kararla varsayilan entegrasyon su sekilde kalir: sensor okuma MES icinde yari mamul izidir; ERP'ye zorunlu stok hareketi olarak gitmez. Robot kol tamamlamasi ise FERP'e mamul girisi/hammadde cikisi icin aktarilacak ana olaydir. Eger FERP tarafinda her ara adim icin WIP muhasebesi istenirse, `mym2056` veya ayri yari mamul giris/cikis akisi ikinci fazda eklenir.

## Sonraki Adimlar

- workbook -> FERP JSON kontratini tanimlamak
- hangi sheet/kolonlarin FERP import'a gidecegini sabitlemek
- replay veya rebuild araciyla workbook tutarliligini yeniden uretebilmek
