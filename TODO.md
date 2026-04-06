# TODO

Bu dosya, repo genelindeki tum acik isleri tek yerde toplar. Her madde, en cok hangi klasoru veya alani ilgilendiriyorsa onun etiketiyle baslar.

## P0 - Hemen Yapilacaklar

- [ ] [mes_web] Manuel kalite override ekrani ekle.
  Hedef: operator tamamlanan urunu sonradan `GOOD`, `REWORK` veya `SCRAP` olarak duzeltebilsin.

- [ ] [mes_web] Kalite override sonucunu OEE hesabina bagla.
  Hedef: urun sonradan `rework` veya `scrap` olarak isaretlenince `quality`, renk bazli dagilim ve trendler yeniden hesaplansin.

- [ ] [mes_web] Kalite override sonucunu workbook'a yaz.
  Hedef: `4_Uretim_Tamamlanan` sheet'i sadece `COMPLETED` degil, son kalite kararini da tutsun.

- [ ] [mes_web] `planned stop` alanini availability hesabina dahil et.
  Hedef: planli durus, plansiz durus gibi OEE'yi bozmasin; availability hesabinda dogru ele alinsin.

- [ ] [mes_web] `TARGET` performans modunu sureye bagli hale getir.
  Hedef: performans sadece `total / targetQty` olmasin; vardiya icinde gecen sureye gore hedef sapmasi hesaplanabilsin.

- [ ] [mes_web] Tablet, OEE control ve vardiya loglarini workbook'a yaz.
  Hedef: sadece Mega ve vision degil; `tablet/log`, `shift_start`, `shift_stop`, `set_target`, `set_cycle`, `set_planned_stop` gibi olaylar da kalici izlensin.

## P1 - Sonraki Faz

- [ ] [raspberry] Kamera konumunu saha yerlesimine gore sabitle.
  Hedef: pick zone goruntusu fiziksel olarak netlessin; kalibrasyon ve line crossing ayarlari degismeyen kamera acisi uzerinden yapilsin.

- [ ] [raspberry] ROI alanini saha yerlesimine gore daralt.
  Hedef: yalnizca robotun alma bolgesi ve kisa yaklasim alani gorulsun; Pi 3 performansi korunurken false positive azaltılsin.

- [ ] [raspberry] `line_counter.x` alma cizgisine gore ayarla.
  Hedef: kutu pick zone cizgisini gectiginde tek ve dogru zamanda `line_crossed` olayi uretilebilsin.

- [ ] [raspberry] Tekli gecis crossing testlerini tamamla.
  Hedef: kirmizi, sari ve mavi kutular icin crossing olayinin bir kez, dogru renkle ve dogru zamanda uretildigi dogrulansin.

- [ ] [mes_web] Raspberry vision -> `mes_web` entegrasyon testini saha akisi ile dogrula.
  Hedef: vision health, son item, mismatch ve final_color akislarinin dashboard ve runtime state tarafinda dogru aktigi gorulsun.

- [ ] [mes_web] Vision tabanli early pick akisini saha uzerinde test et.
  Hedef: deadline, health state, reject reason ve timer fallback kurallari fiziksel hat uzerinde kontrollu olarak dogrulansin.

- [ ] [tests] OEE ekrani icin saha parity testi tamamla.
  Hedef: fault, hedef gap, vardiya ozetleri ve KPI'lar saha akisiyla birebir dogrulansin.

- [ ] [tools] Workbook replay / rebuild araci ekle.
  Hedef: `7_Raw_Logs` uzerinden gunluk workbook yeniden uretilebilsin; gecmis eksik satirlar sonradan toparlanabilsin.

- [ ] [README] FERP icin resmi JSON kontratini tanimla.
  Hedef: workbook'tan hangi alanlarin hangi JSON yapisina donusecegi sabitlensin.

- [ ] [mes_web] Workbook -> FERP JSON donusum katmani ekle.
  Hedef: FERP'e verilecek normalize JSON cikisi backend tarafinda uretilsin.

- [ ] [mes_web] Operasyon ve OEE ekranlarina rapor/export isleri ekle.
  Hedef: gunluk ozet, trend export veya indirilebilir rapor akisi olsun.

- [ ] [picktolight] Performans ekranina tarih araligi filtresi ekle.

- [ ] [picktolight] Operator girisini barkod veya kart okutma ile otomatiklestir.

- [ ] [picktolight] ERP aktarimina siparis, vardiya ve istasyon alanlari ekle.

- [ ] [picktolight] Ana `mes_web` modul mimarisi ile ortaklasabilecek veri kontratlarini netlestir.

## P2 - Mimari ve Genisleme

- [ ] [mes_web] Coklu modul omurgasini gercek hale getir.
  Hedef: sistem tek `konveyor_main` ile sinirli kalmasin; modul listesi config ve runtime tarafinda cogaltilabilsin.

- [ ] [picktolight] `picktolight` modulunu `mes_web` omurgasina bagla.
  Hedef: ayri uygulama yerine ayni kontrol paneli altinda ikinci istasyon olarak alinabilsin.

- [ ] [mes_web] Analytics / report UI katmanini baslat.
  Hedef: capability var ama ekran yok; trend, kayip, throughput gibi ikincil analiz kartlari eklensin.

- [ ] [raspberry] Vision parity ve capraz kontrol kurallarini netlestir.
  Hedef: vision paneli sadece sayisal ozet degil, hangi alarm/diff durumunda ne yapilacagi ile birlikte tanimlansin.

## P3 - Test ve Operasyonel Dayaniklilik

- [ ] [tests] API ve WebSocket entegrasyon testleri ekle.
  Hedef: `app.py`, `runtime.py`, `mqtt_runtime.py` sadece unit degil, route ve snapshot seviyesinde de dogrulansin.

- [ ] [tests] Frontend davranis testleri ekle.
  Hedef: tab gecisi, reconnect, komut paneli, OEE kontrol paneli ve kalite override akislarinin tarayici testi olsun.

- [ ] [mes_web] MQTT baglanti hatalari ve Excel yazim hatalari icin daha acik operator geri bildirimi ekle.
  Hedef: broker offline, workbook kilitli, template bulunamadi gibi durumlar sadece terminalde kalmasin.

- [ ] [mes_web] Runtime state ve workbook tutarlilik kontrolu ekle.
  Hedef: sayaclar, tamamlanan urunler ve workbook kayitlari arasinda uyumsuzluk varsa tespit edilebilsin.

- [ ] [picktolight] Fiziksel buton ve GUI butonu ayni anda aktifken cakisma var mi dogrula.
  Hedef: saha tarafinda cift tetikleme veya kilitlenme riski varsa yakalansin.

## Karar Bekleyenler

- [ ] [mes_web] Kalite override UI akisini kesinlestir.
  Karar: operator tamamlanan urunu nasil bulacak, nasil duzeltecek, geri alma olacak mi.

- [ ] [README] FERP'in ana import nesnesini kesinlestir.
  Karar: workbook dogrudan mi gidecek, yoksa workbook'tan turetilen JSON mu esas olacak.

- [ ] [repo] Workbook arsiv stratejisini netlestir.
  Karar: gunluk dosya yapisi aynen mi kalacak, aylik arsiv/paketleme olacak mi.

- [ ] [repo] Yerel legacy Node-RED parity ihtiyacinin ne zaman bitecegini netlestir.
  Karar: hangi parity checklist tamamlaninca Node-RED tamamen devreden cikarilmis sayilacak.

- [ ] [picktolight] Performans ekraninin kalici rapor ciktisinin JSON mu, workbook mu olacagini netlestir.

- [ ] [picktolight] Istasyon olaylarinin ana MES workbook'una ne zaman baglanacagini netlestir.

## Teknik Borc ve Repo Temizligi

- [ ] [repo] Runtime output, arsiv ve generated dosyalar icin repo hijyenini koru.
  Hedef: `logs/`, yerel workbook'lar, `desktop.ini` benzeri dosyalar repoya tekrar girmesin.
