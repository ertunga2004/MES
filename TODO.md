# TODO

Bu dosya, repo genelindeki tum acik isleri tek yerde toplar. Her madde, en cok hangi klasoru veya alani ilgilendiriyorsa onun etiketiyle baslar.

## Yarin - 2026-04-10

- [x] [mes_web] `web_mes` ve veritabani katmanini is emri odakli JSON giris/cikis ile calisir hale getir.
  Hedef: sistem ERP entegrasyonuna hazir olsun; is emri verisi normalize JSON kontratiyla alinip yine JSON cikisi uretebilsin.
  Sonuc: `work-orders/import`, `work-orders/reload`, siralama/baslatma/onay/rollback/reset API'leri ve dashboard/kiosk JSON snapshot akisi mevcut.

- [x] [mega] Mega kodunu cihaza yukle.
  Hedef: saha akisinda kullanilacak guncel firmware fiziksel karta basilsin.
  Sonuc: guncel Mega firmware'i sahada denendi; sensor/robot cakismasi icin kutu araligi standardi oturdu.

- [ ] [tests] Sistemi uctan uca calistirip tam saha testi yap.
  Hedef: `mega + raspberry + mes_web + workbook/database` zinciri birlikte dogrulansin.

## Tamamlanan - 2026-04-14

- [x] [mes_web] Manuel kalite override ekrani ekle.
  Sonuc: OEE tabinda son tamamlanan urunler icin tek tik `GOOD / REWORK / SCRAP` override akisi eklendi.

- [x] [mes_web] Kalite override sonucunu OEE hesabina bagla.
  Sonuc: override sonrasi kalite, renk dagilimi ve OEE runtime sayaclari yeniden hesaplaniyor.

- [x] [mes_web] Kalite override sonucunu workbook'a yaz.
  Sonuc: `4_Uretim_Tamamlanan` sheet'indeki kalite ve override alanlari backend tarafinda geri yaziliyor.

## Tamamlanan - 2026-04-21

- [x] [mes_web] Veritabani/workbook hata dayanimi kontrol edildi.
  Sonuc: runtime state yaziminda transient `PermissionError` retry, bozuk workbook arsivleme ve startup work-order state testleri mevcut; `mes_web` test paketi 122 test OK.

- [x] [mes_web] `planned stop` alanini availability hesabina dahil et.
  Sonuc: planli durus butcesi availability paydasindan dusuluyor; kapanis checklist suresi planned stop olarak sayiliyor.

- [x] [mes_web] `TARGET` performans modunu sureye bagli hale getir.
  Sonuc: `TARGET` modunda beklenen adet artik `targetQty * planned_production_elapsed / planned_production_total` ile hesaplaniyor ve dashboard beklenen/gap bilgisini gosteriyor.

- [x] [mes_web] Tablet, OEE control ve vardiya loglarini workbook'a yaz.
  Sonuc: `tablet/log`, `shift_start`, `shift_stop`, `set_target`, `set_cycle`, `set_planned_stop` olaylari raw log ve olay logu satirlarina projekte ediliyor.

- [x] [mes_web] MQTT broker offline/pir pir durumunu azalt.
  Sonuc: MES Web varsayilan MQTT client id bilgisayar + proses bazli benzersiz uretiliyor; kisa kopmalarda `reconnecting` grace penceresi kullaniliyor.

- [x] [mega] TCS3200 sensor akis ve rearm mantigini stabilize et.
  Sonuc: bugunku deneme `ARM_RESUME`, `CENTER_CREDIT`, `sensorObjectConsumed` katmani kaldirildi; dunku calisan 3 ardisk algi + 100 ms merkezleme + 1 bosluk rearm akisi geri alindi.

- [x] [mega] Sensor Q testini ve olcum loglarini renk teshisine uygun hale getir.
  Sonuc: `q` testi 7 ornek median/oy/score logluyor; olcum loglarinda `CORE_SCORE_GAP`, vote ve score ayrimi takip ediliyor.

- [x] [mega] Kirmizi/sari renk kararini iyilestir.
  Sonuc: `SEARCH_HINT_OVERRIDE` devreden cikarildi; kirmiziyi sari yapan agresif red/yellow tie-break daraltildi.

- [x] [tests] Bugunku repo regresyon testlerini calistir.
  Sonuc: `python -m unittest discover -s tests` 135 test OK.

## P0 - Hemen Yapilacaklar

- [x] [mes_web] Veritabani hatalarini tespit et ve gider.
  Hedef: `mes_web` veritabani katmanindaki baglanti, sorgu, schema ve veri esleme kaynakli hatalar tekrar uretilebilir sekilde toplanip operasyon akisini bozan DB bug'lari kapatilsin.

- [x] [mes_web] `planned stop` alanini availability hesabina dahil et.
  Hedef: planli durus, plansiz durus gibi OEE'yi bozmasin; availability hesabinda dogru ele alinsin.

- [x] [mes_web] `TARGET` performans modunu sureye bagli hale getir.
  Hedef: performans sadece `total / targetQty` olmasin; vardiya icinde gecen sureye gore hedef sapmasi hesaplanabilsin.

- [x] [mes_web] Tablet, OEE control ve vardiya loglarini workbook'a yaz.
  Hedef: sadece Mega ve vision degil; `tablet/log`, `shift_start`, `shift_stop`, `set_target`, `set_cycle`, `set_planned_stop` gibi olaylar da kalici izlensin.

- [x] [mes_web] MQTT broker offline/pir pir durumunu azalt.
  Hedef: ayni client id veya kisa kopmalar yuzunden dashboard broker durumunu gereksiz titretmesin.

- [x] [mega] TCS3200 sensor akis ve rearm mantigini stabilize et.
  Hedef: sikisik kutu diziliminde ayni urunu tekrar okuma, boslukta durma veya sonraki urunu kacirma riski azaltilsin.

- [x] [mega] Kirmizi/sari renk kararini iyilestir.
  Hedef: kalibrasyon sonrasi kirmizi kupun sari okunmasi azaltilsin; score modeli kirmiziyi net gosterirken tie-break sonucu sari ezmesin.

## Bugun - 2026-04-21 Oncelik Sirasi

1. [x] [P0-Saha] [mega] Mega kodunu fiziksel karta yukle.
2. [x] [P0-Saha] [mega] TCS3200 sensor akis/rearm ve renk kararini saha testlerine gore stabilize et.
3. [x] [P0-Kod] [mes_web] MQTT broker offline/pir pir durumunu azalt.
4. [ ] [P0-Saha] [tests] `mega + raspberry + mes_web + workbook/database` zincirini uctan uca saha testiyle dogrula.
5. [ ] [P1-Kod] [README] FERP ana import kararini JSON cikti olarak sabitle ve resmi JSON kontratini yaz.
6. [ ] [P1-Kod] [mes_web] Workbook -> FERP JSON export katmanini ekle.
7. [ ] [P1-Kod] [tools] Workbook replay / rebuild aracini ekle.
8. [ ] [P1-Saha] [raspberry] Kamera konumu, ROI, `line_counter.x` ve tekli gecis crossing testlerini saha yerlesimine gore tamamla.
9. [ ] [P2-Kod] [mes_web] Operasyon/OEE rapor-export ve analytics UI baslangicini ekle.
10. [ ] [P2-Kod] [picktolight] Performans tarih filtresi ve barkod/kart operator girisi icin ayri faz baslat.

## Mega / Saha Acik Isler

- [ ] [mega] Yeni kirmizi/sari kararini saha regresyonu ile dogrula.
  Hedef: ayni kalibrasyonla 4 kirmizi, 4 sari, 4 mavi ve bos seri testlerinde `FINAL`, `SCORE_NEAREST`, `MEDIAN_NEAREST`, `VOTE_R/Y/B` alanlari beklenen renkle uyumlu olsun.

- [ ] [mega] TCS3200 kalibrasyon ve mekanik ayar runbook'unu yaz.
  Hedef: mat siyah ic yuzey, LED acisi, `cal x/r/y/b` sirasi, `q` test kabul kriterleri ve kutu araligi standardi tekrar uygulanabilir olsun.

- [ ] [tests] Raspberry dahil tam saha testi tamamla.
  Hedef: Mega sensor/queue/robot akisi, Raspberry vision, MES Web ve workbook kaydi ayni senaryoda birlikte dogrulansin.

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

- [ ] [mes_web] Kalite override ekraninda eski urun bulma ve geri alma akislarini kesinlestir.
  Karar: operator sadece son urunleri mi gorecek, daha eski item arama olacak mi, override geri alma veya tekrar duzeltme nasil isleyecek.

- [ ] [README] FERP'in ana import nesnesini kesinlestir.
  Karar: workbook dogrudan mi gidecek, yoksa workbook'tan turetilen JSON mu esas olacak.

- [ ] [repo] Workbook arsiv stratejisini netlestir.
  Karar: gunluk dosya yapisi aynen mi kalacak, aylik arsiv/paketleme olacak mi.

- [ ] [repo] Yerel legacy Node-RED parity ihtiyacinin ne zaman bitecegini netlestir.
  Karar: hangi parity checklist tamamlaninca Node-RED tamamen devreden cikarilmis sayilacak.

- [ ] [picktolight] Performans ekraninin kalici rapor ciktisinin JSON mu, workbook mu olacagini netlestir.

- [ ] [picktolight] Istasyon olaylarinin ana MES workbook'una ne zaman baglanacagini netlestir.

## Teknik Borc ve Repo Temizligi

- [x] [repo] Runtime output, arsiv ve generated dosyalar icin repo hijyenini koru.
  Hedef: `logs/`, yerel workbook'lar, `desktop.ini` benzeri dosyalar repoya tekrar girmesin.
  Sonuc: `.gitignore` `logs/`, `desktop.ini`, `*.bak.xlsx`, gecici dosyalar ve lokal arsivleri kapsiyor; calisma agaci temiz durumdan basladi.
