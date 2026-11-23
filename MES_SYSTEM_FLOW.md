# SYSTEM_FLOW - Web Tabanli MES Sistem Akisi

## Kisa Sistem Ozeti

Bu repo icindeki web tabanli MES sistemi, konveyor tabanli bir mini uretim hattini tarayicidan izlemek ve yonetmek icin kurulmus bir FastAPI + statik web arayuzu uygulamasidir. Sistem; MQTT uzerinden Mega/ESP32, vision ve tablet/kiosk olaylarini alir, operator ve teknisyen ekranlarindan gelen islemleri isler, vardiya/OEE/is emri/kalite/ariza/stok durumunu bellekte ve JSON runtime dosyasinda tutar, gunluk Excel workbook dosyasina operasyonel kayit yazar.

Sistemde klasik SQL veritabani veya ORM bulunmuyor. "Veritabani" rolu, runtime JSON dosyasi ve gunluk Excel workbook dosyalari tarafindan karsilaniyor. Web ekranlari dogrudan MQTT'ye baglanmiyor; tum is akisi backend API'leri ve WebSocket snapshot'lari uzerinden ilerliyor.

## Proje Yapisi ve Katmanlar

| Katman | Klasor / Dosya | Sistemdeki rol |
| --- | --- | --- |
| Calistirma | `Baslaticilar/MES Web.cmd`, `mes_web/__main__.py` | Web MES uygulamasini baslatir, `python -m mes_web` ile FastAPI/uvicorn server acilir. |
| Backend API | `mes_web/app.py` | HTTP endpointleri, WebSocket yayinlari, statik ekran servisleri, kiosk/teknisyen/dashboard snapshot hazirlama. |
| Runtime servis | `mes_web/runtime.py` | Startup/shutdown, MQTT baslatma, Excel sink baslatma, watchdog dongusu, is emri yukleme. |
| MQTT servisi | `mes_web/mqtt_runtime.py` | MQTT topic abonelikleri, donanim/vision/tablet olaylarini backend durumuna cevirme, komut yayinlama. |
| Anlik dashboard store | `mes_web/store.py` | Baglanti durumlari, son olaylar, komutlar, dashboard operasyon snapshot'i. |
| OEE/is akisi modeli | `mes_web/oee_state.py` | Vardiya, OEE, is emirleri, istasyon 1/2, paketleme, ariza, bakim, teknisyen cagrisi, kalite override, stok. |
| Excel kalicilik | `mes_web/excel_runtime.py` | Gunluk workbook'a olay, olcum, ariza, uretim, OEE, vision, is emri, stok, bakim ve raw log yazar. |
| Master data | `mes_web/masterdata.py` | Operatorler, ariza nedenleri, istasyonlar, bakim adimlari gibi tanimlari workbook/template'den okur. |
| Konfigurasyon | `mes_web/config.py` | Host, port, MQTT root topic, dosya yollari, runtime state ve workbook ayarlari. |
| Parser | `mes_web/parsers.py` | Mega/status/tablet/vision mesajlarini normalize eder. |
| FERP entegrasyonu | `mes_web/ferp_export.py`, `mes_web/ferp_xls_export.py`, `mes_web/ferp_labels.py` | FERP etiketli is emri import/export ve XLS cikti hazirligi. |
| Frontend dashboard | `mes_web/static/index.html`, `mes_web/static/app.js`, `mes_web/static/styles.css` | Operasyon, Is Emirleri ve OEE sekmelerinden olusan ana web paneli. |
| Operator kiosk | `mes_web/static/kiosk.html`, `mes_web/static/kiosk.js` | Operator tablet/kiosk ekrani; vardiya, bakim, is emri, paketleme, ariza, yardim ve kalite islemleri. |
| Teknisyen kiosk | `mes_web/static/technician.html`, `mes_web/static/technician.js` | Teknisyen cagrilarini gorur, cevaplar ve cozer. |
| Is emri kaynaklari | `mes_web/work_orders/*.json`, `mes_web/ferp_import/*.json` | Ornek/canli is emri listeleri. Startup veya reload ile sisteme alinir. |
| Dokumantasyon | `docs/*.md`, `mes_web/README.md`, `README.md` | Mimari, veri modeli, MQTT topicleri, FERP sozlesmesi, tablet plani. |
| Testler | `tests/test_mes_web_*.py` | Backend is akislarinin beklenen davranislarini dogrulayan unittest dosyalari. |

## Kullanicinin Sisteme Girdigi Yerler

1. Kullanici Windows baslaticisi ile sistemi acar.
   - `Baslaticilar/MES Web.cmd` uygulamayi baslatir.
   - Varsayilan web adresi `http://127.0.0.1:8080` olarak geciyor.

2. Ana dashboard ekrani:
   - URL: `/`
   - Dosya: `mes_web/static/index.html`
   - Kullanici operasyon, is emri ve OEE durumunu izler; yetkili aksiyonlari buradan verir.

3. Operator kiosk ekrani:
   - URL: `/kiosk/{device_id}`
   - Dosya: `mes_web/static/kiosk.html`
   - Operator vardiya baslatma, bakim checklist, is emri baslatma, paketleme, ariza ve yardim islemlerini yapar.

4. Teknisyen kiosk ekrani:
   - URL: `/technician/{device_id}`
   - Dosya: `mes_web/static/technician.html`
   - Teknisyen aktif cagrilari alir, cevaplar ve tamamlar.

## Modul Modul Akis

### 1. Baslatma ve Runtime Akisi

Program calistiginda `mes_web/__main__.py` uvicorn server'i baslatir. FastAPI startup asamasinda `RuntimeService.start()` calisir. Runtime once eski proseslerden kalmis aktif vardiyayi pasife alir, bellekte is emri yoksa `mes_web/ferp_import` veya `mes_web/work_orders` icindeki en yeni JSON dosyasini yukler, dashboard store'u gunceller, Excel yazma kuyrugunu baslatir, MQTT client'i baslatir ve watchdog dongusunu acik tutar.

Bu akisin urettigi temel cikti; web ekranlarinin okuyacagi canli snapshot, MQTT'den gelen olaylarin islenmesi, runtime JSON dosyasinin guncellenmesi ve gunluk Excel workbook'a kayit yazilmasidir.

### 2. Dashboard - Operasyon Sekmesi

Kullanici ana dashboard'da operasyon sekmesine girdiginde sistem `/api/modules/{module_id}/dashboard` endpointinden ilk snapshot'i alir ve `/ws/modules/{module_id}` WebSocket'i ile canli guncellemeleri izler.

Bu ekranda kullanici genel baglanti durumunu, MQTT durumunu, Mega heartbeat bilgisini, bridge durumunu, kuyruk/olcum/renk/sayac bilgilerini, son donanim loglarini, vision durumunu ve komut gecmisini gorur. Kullanici preset veya manuel komut gonderebilir. Backend komutu `store.py` icindeki komut politikasi ve `command_policy.py` ile kontrol eder; uygunsa `mqtt_runtime.py` komutu MQTT `cmd` topic'ine yayinlar. `__reset_counts__` gibi lokal komutlar MQTT'ye gitmeden backend durumunu sifirlar.

Bu sekme daha cok hattin anlik sagligini, donanimdan gelen mesajlari ve manuel komutlari yonetir.

### 3. Dashboard - Is Emirleri Sekmesi

Is Emirleri sekmesi is emri kuyrugunu, aktif emri, tamamlanan emirleri, operator kodu/adini, tolerans ayarini, is emri reload/reset islemlerini, sira degistirme ve is emri baslatma aksiyonlarini gosterir.

Kullanici JSON kaynaklardan is emri reload edebilir, kuyrugu yeniden siralayabilir, belirli bir is emrini baslatabilir, aktif is emrini kabul ederek tamamlayabilir, rollback yapabilir veya operasyonel stoktan manuel miktar dusumu yapabilir. Backend bu istekleri `oee_state.py` icindeki is emri yoneticisine aktarir. Is emri baslatilirken once operasyonel stoktan uygun malzeme tuketimi denenir. Is emri hedef miktara ulasinca durum `pending_approval` olur; kullanici kabul ettiginde durum `completed` olur ve FERP export hazirligi tetiklenir.

Bu sekme, uretim akisini is emri perspektifinden yonetir.

### 4. Dashboard - OEE Sekmesi

OEE sekmesi vardiya secimi, performans modu, hedef miktar, ideal cevrim suresi, planli durus butcesi, vardiya baslat/durdur, anlik KPI, kalite/uretim/ariza/color trend ve kalite override islemlerini gosterir.

Kullanici OEE parametrelerini ayarladiginda veya vardiya kontrolu yaptiginda backend `/api/modules/{module_id}/oee/control` endpointinden `oee_state.py` icindeki vardiya ve OEE hesaplarini gunceller. Son urunler icin kalite override yapildiginda GOOD/REWORK/SCRAP siniflamasi degisebilir; bu degisim OEE kalite orani, trend, is emri ilerlemesi ve stok uygunlugunu etkileyebilir.

OEE hesaplari basit olarak availability, performance ve quality carpimina dayanir. Opening checklist suresi OEE disinda tutulur; closing checklist suresi planli durus olarak ele alinir; manuel ariza suresi plansiz durus olarak hesaplanir.

### 5. Operator Kiosk Akisi

Operator kiosk `/kiosk/{device_id}` adresinden acilir. Frontend once modul listesini alir, kiosk bootstrap verisini ceker, cihaz/operator/station bilgisini register eder ve WebSocket'e baglanir. Operator secimi, istasyon ve cihaz bilgileri tarayici localStorage tarafinda da tutulur.

Kiosk ekraninda operator:

- Vardiya baslatma akisini tetikler.
- Acilis bakim checklist adimlarini tamamlar.
- Aktif/sonraki is emrini gorur.
- Gerekirse is emri baslatir.
- Paketleme is emri varsa Station 2 paketleme dongusunu baslatir ve bitirir.
- Paketleme kalite sonucunu GOOD/REWORK/SCRAP olarak girer.
- Son urunlerde kalite override yapabilir.
- Ariza bildirir veya yardim cagirir.
- Kapanis bakim checklist adimlarini tamamlayarak vardiya kapatma akisini bitirir.

Kiosk'taki ana buton, sistem durumuna gore anlam degistirir. Vardiya yoksa acilis checklist baslatilir; checklist tamamlaninca vardiya aktif olur. Ariza bildirildiginde backend once `stop` komutunu MQTT'ye gondermeye calisir, sonra manuel ariza ve teknisyen cagrisi olusturur.

### 6. Teknisyen Kiosk Akisi

Teknisyen kiosk `/technician/{device_id}` adresinden acilir. Teknisyen adini girer, aktif cagrilari gorur ve WebSocket ile canli guncelleme alir.

Operator yardim veya ariza cagrisi actiginda `oee_state.py` bir help request olusturur. Teknisyen `Cevapla` dediginde cagrinin kabul zamani ve cevap suresi kaydedilir. `Tamamla` dediginde cozum zamani, tamir suresi ve toplam sure kaydedilir. Eger cagri bir kiosk arizasina bagliysa ilgili manuel ariza da kapatilabilir.

Bu ekranin ana rolu, ariza/yardim cagrilarinin durumunu ve surelerini takip etmektir.

### 7. MQTT ve Donanim Akisi

Backend MQTT root topic altindaki status, logs, heartbeat, bridge/status, tablet/log ve vision topiclerini dinler. Varsayilan root `sau/iot/mega/konveyor` olarak tanimli.

Mega veya donanimdan gelen mesajlar parser ile normalize edilir. Olcum, kuyruk, robot pick/place, release, sensor renk, heartbeat ve durum mesajlari dashboard store'a, OEE durumuna ve Excel kayit kuyruguna aktarilir.

Vision tarafindan gelen track/event/heartbeat mesajlari dashboard'da gorunur. Vision `line_crossed` gibi olaylarda sensor rengini dogrulamak veya zaman uygunsa erken pick komutu uretmek icin kullanilabilir. Ancak dokumantasyona gore son ayirma otoritesi Mega tarafindadir; vision daha cok observer/cross-check rolundedir.

### 8. Is Emri ve FERP Akisi

Is emirleri JSON dosyalarindan yuklenir. Kaynak olarak `mes_web/ferp_import` ve `mes_web/work_orders` klasorleri kullanilir. FERP label-first format veya daha kanonik is emri formati normalize edilerek runtime state'e alinir.

Is emri kuyruga girdikten sonra siralanabilir, baslatilabilir ve aktif hale gelir. Aktif is emri uretim olaylariyla ilerler. Hedef miktar tamamlandiginda is emri onay bekler. Kullanici aktif emri kabul ettiginde is emri tamamlanmis sayilir, workbook is emri sayfasina yansir ve FERP export dosyasi hazirlanmaya calisilir.

Paketleme is emirleri, urun kodu `PKT-` ile baslamasi, ekrandaki adinda paket ifadesi gecmesi, operasyonun packaging olmasi, station2 planlari veya material listesi gibi alanlarla taninir. Paketleme icin malzeme, station2 operasyonlari ve standart sure beklenir.

### 9. Vardiya, Bakim, Ariza ve OEE Akisi

Vardiya baslatma kiosk tarafinda dogrudan vardiya acmak yerine once acilis bakim checklist'i baslatir. Operator gerekli adimlari tamamlayip not girdiginde backend bakim oturumunu tamamlar ve vardiyayi baslatir. Bu acilis suresi OEE disi kabul edilir.

Vardiya durdurma akisi kapanis checklist'i baslatir. Kapanis checklist suresi planli durus olarak OEE'ye yansir. Manuel ariza aktif oldugunda bu sure plansiz durus olarak hesaplanir.

OEE runtime state; toplam uretim, iyi urun, rework, scrap, plansiz durus, planli durus, hedef miktar, ideal cevrim ve trend snapshot'larini tutar. Watchdog dongusu belirli araliklarla OEE snapshot'i uretir.

### 10. Kalite ve Stok Akisi

Kalite sonucu donanim olaylarindan, paketleme kalite seciminden veya kullanici override isleminden gelebilir. GOOD urunler iyi miktara eklenir, REWORK ve SCRAP kalite oranini etkiler. SCRAP stok icin uygun kabul edilmez.

Operasyonel stok, station1 component transferleri ve is emri tuketimleriyle guncellenir. Aktif is emri baslatilirken uygun stoktan dusme denenir. Dashboard'da manuel stok dusumu endpointi bulunur.

### 11. Workbook ve Kayit Akisi

Gunluk workbook, sistemin ana kalici denetim kaydidir. Template yoksa veya gunluk dosya yoksa sistem `MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx` seklinde gunluk dosya uretir.

Workbook sayfalari:

| Sayfa | Kaydedilen veri |
| --- | --- |
| `1_Olay_Logu` | Normalize edilmis olay kayitlari. |
| `2_Olcumler` | Olcum ve karar detaylari. |
| `3_Arizalar` | Manuel ariza ve kiosk kaynakli ariza kayitlari. |
| `4_Uretim_Tamamlanan` | Tamamlanan uretim/transfer kayitlari. Station1 component transferleri de burada izlenir. |
| `5_OEE_Anliklari` | OEE runtime/tablet snapshot'lari. |
| `6_Vision` | Vision event ve saglik bilgileri. |
| `7_Is_Emirleri` | Is emri durum, hedef, tamamlanan miktar ve metrik projeksiyonu. |
| `8_Depo_Stok` | Operasyonel stok hareketleri. |
| `9_Bakim_Kayitlari` | Bakim checklist adimlari ve oturum bilgileri. |
| `99_Raw_Logs` | Ham log izi; dokumantasyona gore gizli sayfa olarak kullaniliyor. |

## Uctan Uca Ana Senaryo

1. Kullanici `MES Web.cmd` ile sistemi baslatir.
2. Backend FastAPI server'i acar, runtime state'i okur, varsa en yeni is emri JSON dosyasini yukler, Excel sink ve MQTT client'i baslatir.
3. Operator kiosk ekranina girer, operator bilgisini secer ve cihaz kaydi yapilir.
4. Operator vardiya baslatmak ister; sistem acilis bakim checklist'ini acar.
5. Operator bakim adimlarini tamamlar; backend bakim kaydini tutar ve vardiyayi aktif hale getirir.
6. Dashboard veya kiosk uzerinden uygun is emri baslatilir. Gerekirse operator sira disi baslatma nedeni girer.
7. Donanimdan MQTT ile olcum, kuyruk, robot ve release olaylari gelir. Backend bu olaylari normalize eder.
8. Station1 tarafindaki component transferleri aktif component is emrini ilerletir ve stok/uretim kayitlarina yazilir.
9. Paketleme is emri aktifse operator Station2 paketleme dongusunu baslatir, bitirir ve kalite sonucunu girer.
10. Kalite sonucu GOOD/REWORK/SCRAP olarak OEE, is emri ilerlemesi, stok uygunlugu ve rapor kayitlarini etkiler.
11. Is emri hedef miktara ulasinca onay bekleyen duruma gecer.
12. Kullanici aktif is emrini kabul eder; sistem tamamlanan is emrini kaydeder ve FERP export hazirlamaya calisir.
13. Ariza olursa operator kiosk'tan ariza bildirir; sistem stop komutu gonderir, ariza kaydi ve teknisyen cagrisi acar.
14. Teknisyen cagria cevap verir ve cozer; sistem cevap, tamir ve toplam sureleri kaydeder.
15. Vardiya sonunda operator kapanis checklist'ini tamamlar; vardiya kapatilir, OEE ve workbook kayitlari son durumla guncellenir.

## Veri Akisi Tablosu

| Veri / Girdi | Nereden alinir | Backend ne yapar | Nereye kaydedilir | Nerede kullanilir |
| --- | --- | --- | --- | --- |
| Operator secimi | Kiosk localStorage ve register API | Cihaz/operator kaydini runtime state'e yazar | Runtime JSON, kiosk snapshot | Kiosk aksiyonlari, is emri ve bakim kayitlari |
| Teknisyen adi | Teknisyen kiosk | Teknisyen aksiyonlarina isim baglar | Runtime JSON, help request kayitlari | Teknisyen ekranlari, ariza sure raporlari |
| Vardiya parametreleri | Dashboard OEE veya kiosk akisi | Shift config ve OEE state gunceller | Runtime JSON, OEE workbook sayfasi | OEE kartlari, trendler, raporlar |
| Bakim checklist adimlari | Operator kiosk | Maintenance session'i tamamlar, vardiya baslat/durdur tetikler | Runtime JSON, `9_Bakim_Kayitlari` | Kiosk durumlari, OEE planli/OEE disi sureler |
| Is emri listesi | JSON import/reload klasorleri | Is emirlerini normalize eder ve kuyruga alir | Runtime JSON, `7_Is_Emirleri` | Dashboard, kiosk, OEE, stok/uretim akisi |
| Is emri baslatma nedeni | Dashboard/kiosk | Tolerans veya sira disi baslatma kuralini gecerli kilar | Runtime JSON, is emri projeksiyonu | Is emri denetim izi |
| Donanim olcumleri | MQTT logs/status | Parser ile normalize eder, sayac ve karar durumunu gunceller | Workbook olay/olcum/raw sayfalari, runtime snapshot | Dashboard operasyon, uretim ve kalite akisi |
| Robot/release olaylari | MQTT logs | Station1 transfer veya uretim tamamlama kaydi uretir | `4_Uretim_Tamamlanan`, runtime JSON | Is emri ilerlemesi, stok, dashboard |
| Paketleme baslat/bitir | Operator kiosk | Station2 cycle acar/kapatir | Runtime JSON, uretim/OEE kayitlari | Paketleme OEE, is emri tamamlanma |
| Paket kalite sonucu | Operator kiosk | GOOD/REWORK/SCRAP olarak sayar | Runtime JSON, `4_Uretim_Tamamlanan`, OEE snapshot | OEE quality, is emri ilerlemesi, stok |
| Kalite override | Dashboard veya kiosk | Son urunun kalite sinifini degistirir | Runtime JSON, override log, workbook projeksiyonlari | OEE quality, is emri/stok hesaplari |
| Ariza nedeni | Operator kiosk | Stop komutu gonderir, manuel ariza ve help request acar | Runtime JSON, `3_Arizalar` | Teknisyen kiosk, OEE plansiz durus |
| Teknisyen cevap/cozum | Teknisyen kiosk | Acknowledge/resolve surelerini hesaplar | Runtime JSON, ariza/help request kayitlari | Teknisyen raporlari, ariza sureleri |
| Vision eventleri | MQTT vision topicleri | Vision saglik ve event durumunu gunceller; uygun durumda komut onerebilir/yayinlayabilir | `6_Vision`, runtime/dashboard snapshot | Dashboard vision paneli, sensor cross-check |
| Manuel komut | Dashboard | Komut politikasi uygunsa MQTT cmd topic'ine yayinlar | Command history, workbook/raw log | Donanim kontrolu, dashboard gecmisi |

## Ekran / API / Veritabani Eslestirme Tablosu

| Kullanici adimi / ekran | Frontend dosyasi | API / WebSocket | Backend is akisi | Kalici veri |
| --- | --- | --- | --- | --- |
| Ana dashboard acma | `static/index.html`, `static/app.js` | `GET /`, `GET /api/modules`, `GET /api/modules/{module_id}/dashboard`, `WS /ws/modules/{module_id}` | Dashboard snapshot hazirlanir, canli durum yayinlanir | Dogrudan yeni kayit zorunlu degil; snapshot runtime'dan gelir |
| Komut gonderme | `static/app.js` | `POST /api/modules/{module_id}/commands` | Komut dogrulanir, MQTT'ye veya lokal store'a uygulanir | Command history, raw/event log |
| OEE kontrolu | `static/app.js` | `POST /api/modules/{module_id}/oee/control` | Shift/OEE parametreleri guncellenir | Runtime JSON, `5_OEE_Anliklari` |
| Dashboard kalite override | `static/app.js` | `POST /api/modules/{module_id}/oee/quality-override` | Recent item kalite sinifi degistirilir | Runtime JSON, override log, workbook projeksiyonlari |
| Is emri import | Dashboard/API | `POST /api/modules/{module_id}/work-orders/import` | Gelen JSON is emri listesi normalize edilir | Runtime JSON, `7_Is_Emirleri` |
| Is emri reload | `static/app.js` | `POST /api/modules/{module_id}/work-orders/reload` | Klasorden en yeni is emri dosyasi yuklenir | Runtime JSON, `7_Is_Emirleri` |
| Is emri siralama | `static/app.js` | `POST /api/modules/{module_id}/work-orders/reorder` | Queue sirasini degistirir | Runtime JSON, `7_Is_Emirleri` |
| Is emri baslatma | `static/app.js`, `static/kiosk.js` | `POST /api/modules/{module_id}/work-orders/start`, `POST /api/modules/{module_id}/kiosk/work-orders/start` | Aktif is emri atanir, gerekirse stoktan dusulur | Runtime JSON, is emri/stok workbook sayfalari |
| Aktif is emri kabul | `static/app.js`, `static/kiosk.js` | `POST /api/modules/{module_id}/work-orders/accept-active`, kiosk karsiligi | Pending approval is emri completed olur, FERP export denenir | Runtime JSON, `7_Is_Emirleri`, FERP export dosyasi |
| Is emri rollback | `static/app.js` | `POST /api/modules/{module_id}/work-orders/rollback-active` | Aktif is emri geri alinir, miktarlar/stok duzeltilir | Runtime JSON, workbook projeksiyonlari |
| Operator kiosk acma | `static/kiosk.html`, `static/kiosk.js` | `GET /kiosk/{device_id}`, `GET /api/modules/{module_id}/kiosk/bootstrap`, `WS /ws/modules/{module_id}/kiosk/{device_id}` | Kiosk snapshot ve cihaz kaydi hazirlanir | Runtime JSON device registry |
| Kiosk register | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/register` | Device/operator/station kaydi guncellenir | Runtime JSON |
| Kiosk vardiya baslat | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/shift/start` | Acilis bakim session'i baslatilir veya vardiya akisi tetiklenir | Runtime JSON, bakim/OEE kayitlari |
| Bakim adimi tamamlama | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/maintenance/complete` | Checklist adimi/session tamamlanir; gerekirse shift start/stop olur | Runtime JSON, `9_Bakim_Kayitlari`, `5_OEE_Anliklari` |
| Kiosk sistem baslat | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/system/start` | Donanima start komutu gonderilir | Command history, raw/event log |
| Kiosk ariza bildir | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/fault/start` | Stop komutu, manuel ariza, help request olusturulur | Runtime JSON, `3_Arizalar` |
| Kiosk ariza kapat | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/fault/clear` | Aktif manuel ariza kapanir | Runtime JSON, `3_Arizalar` |
| Kiosk yardim cagir | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/help/request` | Help request acilir veya yinelenir | Runtime JSON, teknisyen snapshot |
| Paketleme baslat | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/packages/start` | Station2 package cycle baslatilir | Runtime JSON |
| Paketleme bitir | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/packages/finish` | Cycle kalite bekleyen duruma gelir | Runtime JSON |
| Paket kalite girisi | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/packages/quality` | Cycle final olur, OEE ve is emri ilerler | Runtime JSON, `4_Uretim_Tamamlanan`, `5_OEE_Anliklari` |
| Kiosk kalite override | `static/kiosk.js` | `POST /api/modules/{module_id}/kiosk/quality/override` | Son 5 gorunen urunden biri duzeltilir | Runtime JSON, override log |
| Teknisyen ekran acma | `static/technician.html`, `static/technician.js` | `GET /technician/{device_id}`, `GET /api/modules/{module_id}/technician/bootstrap`, `WS /ws/modules/{module_id}/technician/{device_id}` | Aktif/cozulmus cagrilar listelenir | Runtime JSON |
| Teknisyen cevap | `static/technician.js` | `POST /api/modules/{module_id}/technician/requests/{request_id}/acknowledge` | Cagri acknowledged olur, cevap suresi hesaplanir | Runtime JSON |
| Teknisyen cozum | `static/technician.js` | `POST /api/modules/{module_id}/technician/requests/{request_id}/resolve` | Cagri resolved olur, tamir/toplam sure hesaplanir | Runtime JSON, ariza kayitlari |
| MQTT donanim olayi | Backend servisi | MQTT subscribe topicleri | Mesaj parse edilir, store/OEE/Excel guncellenir | Runtime JSON, workbook sayfalari |

## Otomatik Surecler ve Durum Degisimleri

- Runtime startup, eski aktif vardiyayi otomatik pasife alir.
- Startup'ta bellekte is emri yoksa en yeni JSON is emri dosyasi otomatik yuklenir.
- MQTT callbackleri donanim, vision ve tablet mesajlarini surekli isler.
- Watchdog dongusu yaklasik her saniye OEE state tick, store refresh ve WebSocket bildirimleri yapar.
- Is emri durumu degistiginde Excel is emri projeksiyonu guncellenir.
- OEE trend snapshot'lari vardiya aktifken veya onemli olaylarda uretilir.
- Vision heartbeat/FPS/latency durumuna gore vision sagligi degrade/recover olur.
- Paketleme veya uretim hedefi tamamlaninca is emri `pending_approval` durumuna gecebilir.
- Teknisyen cagrisinda acknowledge ve resolve sureleri otomatik hesaplanir.
- Ariza aktifken gecen sure OEE plansiz durus hesaplarina yansir.
- Kapanis checklist suresi planli durus olarak degerlendirilir.

## Belirsiz / Dogrulanmali Noktalar

- FERP cikti akisi icin hem JSON kontrat dokumani hem XLS export kodu bulunuyor. Aktif kabul akisi XLS export tarafini kullaniyor gorunuyor; FERP tarafinda beklenen nihai format gercek entegrasyonla dogrulanmali.
- Operator kiosk kodunda station bilgisi okunuyor ve backend station destekliyor; mevcut HTML'de acik bir station secici gorulmedi. Istasyon degistirme ihtiyaci varsa UI akisi dogrulanmali.
- Kiosk dokumantasyonu rollback'in tablet ekraninda olmadigini soyluyor; dashboard'da rollback endpointi ve akisi var. Operatorun sahada rollback yapmasi gerekiyorsa eksik kabul edilmeli.
- Sistemde kullanici yetkilendirme, PIN veya login akisi gorulmedi. Bu, dokumantasyonda gelecek is olarak geciyor.
- Klasik SQL veritabani yok. Kullanici "veritabani" derken iliskisel DB bekliyorsa mevcut sistemde bu rol runtime JSON + Excel workbook ile karsilaniyor.
- Workbook ana denetim kaydi olarak kullaniliyor; Excel'den runtime state'i tamamen yeniden kuran ayri bir replay araci gorulmedi.
- FERP etiket/export dosyalarinda Turkce karakterlerin bozulmus gorundugu yerler var. Gercek FERP dosyalariyla encoding etkisi kontrol edilmeli.
- Vision akisi observer/cross-check olarak tasarlanmis. Erken pick komutu ve sensor duzeltme davranisi sahadaki zamanlama ile test edilmeli.
- `picktolight`, `Giyotin_kontrol`, `raspberry`, `CPP` klasorleri web MES cekirdegine komsu donanim/yardimci alanlar gibi duruyor. Web ekran akisi icinde aktif sayfa olarak ele alinmadi.
- `/work-orders/import` endpointi var; mevcut dashboard UI'da dosya yukleme gibi acik bir import formu gorulmedi. Pratik import akisi daha cok klasorden reload seklinde.
- Startup'ta aktif vardiyanin otomatik pasife alinmasi akademik/prototip icin mantikli olabilir; gercek uretim ortaminda vardiya devamiyeti beklentisiyle dogrulanmali.

## Analizde Bakilan Dosyalar

- `README.md`
- `mes_web/README.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/mqtt-topics.md`
- `docs/FERP_INTEGRATION.md`
- `docs/FERP_JSON_CONTRACT.md`
- `docs/tablet_plan.md`
- `Baslaticilar/README.md`
- `mes_web/__main__.py`
- `mes_web/requirements.txt`
- `mes_web/config.py`
- `mes_web/app.py`
- `mes_web/runtime.py`
- `mes_web/mqtt_runtime.py`
- `mes_web/store.py`
- `mes_web/oee_state.py`
- `mes_web/excel_runtime.py`
- `mes_web/masterdata.py`
- `mes_web/command_policy.py`
- `mes_web/ferp_export.py`
- `mes_web/ferp_xls_export.py`
- `mes_web/static/index.html`
- `mes_web/static/app.js`
- `mes_web/static/kiosk.html`
- `mes_web/static/kiosk.js`
- `mes_web/static/technician.html`
- `mes_web/static/technician.js`
- `mes_web/work_orders/sample_work_orders.json`
- `mes_web/ferp_import/ferp_work_orders.json`
- `tests/test_mes_web_kiosk_app.py`
- `tests/test_mes_web_store.py`
- `tests/test_mes_web_oee_state.py`
