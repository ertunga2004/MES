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

## Sonraki Adimlar

- workbook -> FERP JSON kontratini tanimlamak
- hangi sheet/kolonlarin FERP import'a gidecegini sabitlemek
- replay veya rebuild araciyla workbook tutarliligini yeniden uretebilmek
