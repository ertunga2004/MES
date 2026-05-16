# Field Test Plan

Bu dokuman, fiziksel hat uzerinde `mega + esp32 + raspberry + mes_web + workbook` zincirini tekrar edilebilir sekilde dogrulamak icin kullanilir.

Amac iki seyi ayirmaktir:

1. saha operatorunun hangi senaryoyu nasil calistiracagi
2. test gozlemcisinin sistemde nerelere bakip neyi dogrulayacagi

## 1. Testin Ciktisi

Her saha testinin sonunda su sorular net cevaplanmis olmalidir:

- fiziksel olay beklenen sekilde oldu mu
- dashboard beklenen durumu gosterdi mi
- kiosk beklenen aksiyonu verdi mi
- teknisyen ekrani gerekiyorsa dogru cagriyi gosterdi mi
- `logs/oee_runtime_state.json` beklenen state'i tuttu mu
- gunluk workbook beklenen sheet'lere dogru kaydi atti mi

Bu test plani kod testi degil, operasyon parity testidir.

## 2. Roller

En az iki kisiyle test yapin.

- `operator`
  - kutu koyar
  - kiosk aksiyonlarini verir
  - fault ve maintenance senaryolarini tetikler
- `gozlemci`
  - dashboard'u izler
  - runtime state ve workbook kontrol eder
  - sonuc formunu doldurur

Mumkunse ucuncu kisi de olsun:

- `teknisyen`
  - technician ekranindan `acknowledge` ve `resolve` aksiyonlarini verir

## 3. Test Ortami Hazirlik Checklist'i

Testten once su checklist tamamlanmis olmali:

- Mega guncel firmware ile calisiyor
- ESP32 MQTT'ye bagli
- Raspberry observer kullanilacaksa kamera acisi ve ROI sabit
- `mes_web` acik
- dashboard acik: `http://127.0.0.1:8080`
- kiosk acik: `http://127.0.0.1:8080/kiosk/kiosk-test-1`
- technician ekran acik: `http://127.0.0.1:8080/technician/tech-1`
- `logs/oee_runtime_state.json` yaziliyor
- bugunun workbook dosyasi olusuyor
- fiziksel hattan gecirilecek test kutulari hazir
- test kutularinin beklenen rengi ve adedi kagit ustunde yazili

## 4. Test Delili

Her senaryoda asgari su delilleri toplayin:

- test saati
- senaryo kodu
- fiziksel beklenen sonuc
- dashboard sonucu
- kiosk sonucu
- technician sonucu gerekiyorsa
- runtime state sonucu
- workbook sonucu
- `PASS`, `FAIL` veya `INVESTIGATE`

Mumkunse her `FAIL` icin:

- ekran goruntusu
- ilgili log satiri
- workbook satir numarasi

## 5. Kontrol Noktalari

Her senaryoda ayni sirayla bakilacak yerler bunlar:

### A. Fiziksel katman

- konveyor hareket etti mi
- kutu tekil algilandi mi
- robot dogru anda calisti mi
- dogru yuvaya birakti mi
- takilma, tekrar sayma, kacirma oldu mu

### B. Dashboard

- `connection` durumu normal mi
- `hardware_status` dogru mu
- `counts` beklenen artis yapti mi
- `recent_logs` ilgili olayi gosterdi mi
- `oee` alanlari anlamli guncellendi mi
- vision aciksa `vision_ingest` beklenen akista mi

### C. Kiosk

- vardiya durumu dogru mu
- aktif is emri dogru mu
- son 5 urun listesi guncellendi mi
- quality override gerekiyorsa dogru item geldi mi
- fault/help/maintenance buton aksiyonu yansidi mi

### D. Technician

- cagri acildi mi
- `acknowledge` sonrasi cevap suresi sabitlendi mi
- `resolve` sonrasi giderme ve toplam sure sabitlendi mi
- tamamlanan cagri gecmis panellerine dustu mu

### E. Runtime state

Dosya: `logs/oee_runtime_state.json`

Bakilacak alanlar:

- `operationalState`
- `shift`
- `counts`
- `recentItemIds`
- `itemsById`
- `maintenance`
- `helpRequest`
- `activeFault`
- `faultHistory`
- `trend`
- `lastEventSummary`

### F. Workbook

Gunluk dosya: `logs/MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`

Bakilacak sheet'ler:

- `1_Olay_Logu`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `5_OEE_Anliklari`
- `6_Vision`
- `7_Is_Emirleri`
- `8_Depo_Stok`
- `9_Bakim_Kayitlari`
- `99_Raw_Logs`

## 6. Test Akisi

Testleri bu sirayla yapin. Sirayi bozmayin; her senaryo oncekine dayanir.

### T00 - Baslangic Saglik Kontrolu

Amac: sistem calismaya hazir mi.

Adimlar:

1. `mes_web` baslatin.
2. Dashboard, kiosk ve technician ekranlarini acin.
3. MQTT baglantisini kontrol edin.
4. Workbook dosyasinin bugun icin olustugunu kontrol edin.
5. Runtime state dosyasinin guncellendigini kontrol edin.

Beklenen:

- dashboard aciliyor
- broker ve cihazlar offline degil
- runtime state yaziliyor
- workbook olusuyor

Kontrol:

- dashboard `connection`
- `logs/oee_runtime_state.json`
- bugunun workbook dosyasi

### T01 - Vardiya Baslatma / Acilis Checklist

Amac: vardiya acilisi ve OEE disi acilis bakiminin dogru islenmesi.

Adimlar:

1. Kioskta vardiya baslatin.
2. Acilis checklist adimlarini tamamlayin.
3. Checklist'i kapatin.

Beklenen:

- `operationalState` once `opening_checklist`, sonra aktif uretim durumuna gecer
- acilis checklist suresi `maintenance.openingChecklistDurationMs` icinde tutulur
- bu sure OEE'ye dahil edilmez
- workbook'ta audit ve bakim kaydi vardir

Kontrol:

- kiosk maintenance paneli
- runtime `operationalState`
- runtime `maintenance.openingChecklistDurationMs`
- workbook `1_Olay_Logu`
- workbook `9_Bakim_Kayitlari`

### T02 - Tekli Normal Urun Akisi

Amac: bir urunun uctan uca dogru akmasi.

Adimlar:

1. Tek bir kutu verin.
2. Renk tespitini gozleyin.
3. Robotun kutuyu birakmasini bekleyin.

Beklenen:

- kutu bir kez algilanir
- tek tamamlanma olayi uretilir
- sayaclar 1 artar
- son urun listesi guncellenir
- runtime `itemsById` icine item duser
- workbook `4_Uretim_Tamamlanan` sheet'ine satir eklenir
- raw log ve olay logu anlamli satirlar alir

Kontrol:

- dashboard `counts`, `recent_logs`
- kiosk `recent_items`
- runtime `counts`, `recentItemIds`, `itemsById`
- workbook `4_Uretim_Tamamlanan`
- workbook `99_Raw_Logs`

### T03 - Renk Regresyon Serisi

Amac: renk kararinin saha tekrarinda tutarli oldugunu gormek.

Adimlar:

1. 4 kirmizi kutu gecirin.
2. 4 sari kutu gecirin.
3. 4 mavi kutu gecirin.
4. Sonuclari beklenen renk listesiyle karsilastirin.

Beklenen:

- her kutu tek kez sayilir
- renk sapmasi not edilir
- dashboard renk dagilimi ve tamamlananlar mantikli ilerler
- workbook tamamlanan urunler tablosunda renkler beklenen dagilimdadir

Kontrol:

- dashboard `counts`
- runtime `itemsById`
- workbook `4_Uretim_Tamamlanan`
- gerekiyorsa Mega log satirlari

Not:

Bu senaryoda ilk hedef kodu degistirmek degil, sapma oranini olcmektir.

### T04 - Quality Override

Amac: tamamlanan urun uzerindeki kalite duzeltmesinin tum katmanlara yansimasi.

Adimlar:

1. Bir urun tamamlatin.
2. Kiosk veya dashboard uzerinden kaliteyi `SCRAP` yapin.
3. Ayrica bir baska urunde `REWORK` deneyin.

Beklenen:

- sadece son uygun item'lar override edilebilir
- quality metrikleri guncellenir
- `SCRAP` urun inventory'ye dusmez veya dusmusse cikarilir
- workbook tamamlanan urun kaydi guncellenir

Kontrol:

- kiosk `recent_items`
- dashboard `oee`
- runtime `itemsById`, `qualityOverrideLog`
- workbook `4_Uretim_Tamamlanan`
- workbook `8_Depo_Stok`

### T05 - Manuel Fault ve Teknisyen Cagrisi

Amac: ariza akisi ve teknisyen surelerinin dogrulanmasi.

Adimlar:

1. Kioskta `Ariza Bildir` verin.
2. Technician ekraninda cagriyi gorun.
3. `acknowledge` yapin.
4. Kisa bir bekleme sonrasi `resolve` yapin.

Beklenen:

- aktif fault olusur
- technician ekraninda acik cagri belirir
- cevap suresi `acknowledge` aninda sabitlenir
- giderme ve toplam sure `resolve` aninda sabitlenir
- fault kapanir
- gecmis listeleri guncellenir

Kontrol:

- kiosk `active_fault`
- technician `active_requests`, `resolved_today`, `recent_requests`
- runtime `activeFault`, `helpRequest`, `faultHistory`
- workbook `3_Arizalar`
- workbook `1_Olay_Logu`

### T06 - Planli Kapanis / Kapanis Checklist

Amac: planned stop ile kapanis bakiminin dogru siniflanmasi.

Adimlar:

1. Vardiyayi kapatmaya gecin.
2. Kapanis checklist'ini tamamlayin.
3. Vardiyayi sonlandirin.

Beklenen:

- `operationalState` `closing_checklist` olur
- checklist tamamlaninca vardiya kapanir
- sure `closingChecklistDurationMs` icine gider
- bu sure planned stop olarak ele alinir

Kontrol:

- kiosk maintenance paneli
- runtime `maintenance.closingChecklistDurationMs`
- runtime `shift.active`
- workbook `9_Bakim_Kayitlari`
- workbook `5_OEE_Anliklari`

### T07 - Uretim Yok / Uzun Bekleme

Amac: vardiya acikken uretim olmadiginda sistem davranisini gormek.

Adimlar:

1. Vardiya acik kalsin.
2. Belirlenen sure boyunca urun gecirmeyin.
3. Dashboard ve OEE tarafini izleyin.

Beklenen:

- sistem kilitlenmez
- counts sabit kalir
- OEE tarafinda sureye bagli beklenen/gap mantigi gozlenir
- loglarda anlamsiz patlama olmaz

Kontrol:

- dashboard `oee`
- dashboard `recent_logs`
- runtime `trend`, `lastEventSummary`
- workbook `5_OEE_Anliklari`

### T08 - MQTT / Cihaz Kopma Senaryosu

Amac: baglanti kopmalarinin gorunurlugunu ve toparlanmayi dogrulamak.

Adimlar:

1. Kontrollu olarak ESP32 veya broker baglantisini kesin.
2. Dashboard'da offline/reconnecting durumunu gozleyin.
3. Baglantiyi geri verin.

Beklenen:

- dashboard durum degisikligini gosterir
- veri akisi geri geldiginde toparlar
- sistem sessizce bozulmus gibi gorunmez

Kontrol:

- dashboard `connection`
- dashboard `hardware_status`
- runtime `lastEventSummary`
- workbook `1_Olay_Logu` ve `99_Raw_Logs`

### T09 - Vision Parity

Amac: Raspberry vision'in pasif gozlemci olarak tutarli calistigini gormek.

Adimlar:

1. Vision acikken farkli renklerde kutular gecirin.
2. Crossing olaylarini izleyin.
3. MES tarafinda vision ozetini kontrol edin.

Beklenen:

- crossing tek kez olur
- gorulen renk mantikli olur
- vision health ve son item akisinda tutarsiz patlama olmaz

Kontrol:

- dashboard `vision_ingest`
- runtime vision ile ilgili alanlar
- workbook `6_Vision`

### T10 - Restart Dayaniklilik

Amac: uygulama yeniden baslarken veri zincirinin bozulmadigini gormek.

Adimlar:

1. Vardiya acikken uygun bir anda `mes_web` yeniden baslatin.
2. Ekranlarin yeniden baglanmasini bekleyin.
3. Sonraki bir urunu gecirin.

Beklenen:

- uygulama ayağa kalkar
- ekranlar geri baglanir
- yeni urun kaydi devam eder
- beklenmeyen cift sayim veya kopuk state gozlenmez

Kontrol:

- dashboard reconnect
- runtime state devam davranisi
- workbook yeni satirlar

## 7. Her Senaryoda Sonuc Verme Kurali

### PASS

- fiziksel sonuc dogru
- UI sonucu dogru
- runtime state dogru
- workbook kaydi dogru

### FAIL

- yukaridaki katmanlardan herhangi biri beklenenle celisiyor

### INVESTIGATE

- fiziksel sonuc dogru ama veri katmanlarindan biri eksik veya gecikmeli
- ya da workbook / runtime / UI arasinda zamanlama farki var

## 8. Saha Test Kayit Formu

Her senaryo icin asagidaki tabloyu doldurun:

| Alan | Deger |
|---|---|
| Test tarihi | |
| Senaryo kodu | |
| Operator | |
| Gozlemci | |
| Beklenen fiziksel sonuc | |
| Dashboard sonucu | |
| Kiosk sonucu | |
| Technician sonucu | |
| Runtime state sonucu | |
| Workbook sonucu | |
| Karar | PASS / FAIL / INVESTIGATE |
| Not | |

## 9. Ilk Saha Gunu Icin Onerilen Minimum Paket

Tek oturumda her seyi zorlamayin. Ilk gunde su paket yeterli:

1. `T00` baslangic saglik
2. `T01` vardiya baslatma
3. `T02` tekli normal urun
4. `T03` renk regresyon
5. `T05` manuel fault ve teknisyen
6. `T06` kapanis checklist

Ikinci gunde:

1. `T04` quality override
2. `T07` uretim yok uzun bekleme
3. `T08` MQTT kopma
4. `T09` vision parity
5. `T10` restart dayanıklılık

## 10. Bu Plandan Sonra Ne Yapilacak

Saha testinden sonra cikan bug'lari uc kovaya ayirin:

- `P0`: veri kaybi, cift sayim, yanlis OEE, yanlis fault siniflama
- `P1`: UI uyumsuzlugu, gecikmeli workbook, zayif operator geri bildirimi
- `P2`: raporlama, export, ikincil iyilestirmeler

Bu dokumanin amaci daha fazla ozellik istemek degil, sistemin nerede guvenilir nerede kirilgan oldugunu olcmektir.
