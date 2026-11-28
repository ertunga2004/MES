# MES Web

`mes_web/`, konveyor hattinin aktif web katmanidir. Bu klasor; MQTT ingest, dashboard snapshot, operator kiosk UI, teknisyen cagri UI, vardiya kontrollu OEE runtime state ve workbook kaydini tek yerde toplar.

**Dijital İkiz** ekranında örnek simülasyon 20× hıza kadar oynatılır ve analizler senaryo zamanıyla ilerler. **Fiziksel hat · MES** görünümü mevcut dashboard akışından vardiya OEE’sini ve MEGA durum/ürün olaylarını okur. Enerji sayacı aynı MQTT kökünün `/logs` kanalına `{"type":"performance-telemetry","energyKwh":4.72}` biçiminde birikimli kWh okuması gönderebilir. Ekran, ürün başına duruşta bekleme süresini yalnız bant durumu bütün ürün geçişi boyunca gözlenmişse hesaplar.

## Ana Sorumluluklar

- MQTT topiclerini dinlemek
- browser icin REST + WebSocket snapshot uretmek
- dashboard, operator kiosk ve teknisyen ekranlarini servis etmek
- preset komutlari `cmd` topic'ine publish etmek
- vardiya, OEE, fault, quality ve work order state'ini backend'de yonetmek
- gunluk workbook'a normalize audit ve rapor kaydi yazmak

## Aktif Ekranlar

- `GET /`
  - ana dashboard
- `GET /kiosk/{device_id}`
  - ayni agdaki telefon, tablet veya laptop icin operator kiosk ekrani
- `GET /technician/{device_id}`
  - teknisyen icin canli ariza cagri ve gecmis ekrani

Kiosk ve teknisyen ekranlari browser tabanlidir. MQTT kullanmaz; `mes_web` ile REST + WebSocket uzerinden konusur.

### Manuel kaplama

Sunucu bilgisayarında `http://127.0.0.1:8080/kaplama` adresini aç. Mevcut MES'te adet birimli bir iş emrini etkinleştir. Operatör kendi adını ve kaplanan parça sayısını girip kaydeder. Etkin iş emri 10 adet ise 5 parçalık kayıt kaplama ilerlemesini **5 / 10** olarak gösterir. Yönetici ekranındaki aktif iş emri kartında aynı ilerleme salt okunur gösterilir.

Kaplama kayıtları mevcut çalışma durumu dosyasında iş emri, operatör adı, miktar, zaman ve istek kimliğiyle saklanır. Aynı isteğin tekrarı yeni kayıt üretmez. Kaplama kaydı konveyör komutu göndermez ve hattın üretim miktarını ya da OEE sonucunu artırmaz. Bu ilk sürümün kaplama işlemleri sunucu bilgisayarında kullanılabilir. İstasyon tabletinin eşleştirilmesi ayrıca bağlanacaktır.

### Giyotin ve doğrudan kaplama

İki istasyonlu akışı, aktif tek istasyonlu kaplama işini bitirdikten sonra sunucuyu `MES_WEB_CUTTING_WORKFLOW_ENABLED=1` ile başlatarak aç. PowerShell'de başlatma öncesinde `$env:MES_WEB_CUTTING_WORKFLOW_ENABLED = "1"` kullan. Ayar kapalıyken tek istasyonlu kaplama akışı kullanılabilir.

1. MES'te kutu adedi üzerinden bir iş emrini etkinleştir. Sunucu bilgisayarında `http://127.0.0.1:8080/giyotin` adresinden kesilen bant parçası sayısını kaydet. 10 kutuluk emir, 20 bant parçası hedefi gösterir.
2. `http://127.0.0.1:8080/kaplama` ekranında ilk iki bant hazır olduğunda bir kutu için kaplama kaydı açılır. Her yeni bant çifti bir kutuya yeter. Tek kalan bant parçası, bir sonraki kesimi bekler.
3. Kaplanan kutu sayısını kaydet. Her kutu iki hazır bant parçası kullanır. Yönetici ekranının **İş Emirleri** sekmesi kesilen bant, kaplamaya hazır kutu ve kaplanan kutu miktarlarını ayrı gösterir.

Bu akış iki istasyonu yan yana kabul eder. Bant kesildiğinde kaplamaya hazır sayılır. Ayrı parti teslimi, bekleme alanı ve taşıma süresi bu sürümde kullanılmaz. İlk kesim kaydından sonra iş emrinin hedef adedi ve birimi sabitlenir. Başka bir akışla kayıt alınmış emirleri karıştırmamak için doğrudan aktarıma yeni bir iş emriyle başla. Kesim ve kaplama konveyör üretimine veya OEE'ye eklenmez. Aynı isteğin tekrarı yeni kayıt üretmez.

### Kiosk Tasarla

Sunucu bilgisayarında MES ana ekranındaki **Kiosk Tasarla** bağlantısını aç. Sunucuyu başlatmadan önce `MES_WEB_KIOSK_DESIGN_PASSWORD` ortam değişkenine seçtiğin mühendis parolasını ata. Girişte kullanıcı adı `muhendis`. Tarayıcı giriş ekranı için ASCII karakterlerden oluşan bir parola seç.

1. **Yeni kiosk** ile bir ad, adres adı ve operatör talimatı yaz. Onay, metin, sayı veya seçim adımlarını ekle. İstersen iş süresi sayacı, mevcut iş emri hedefi ve sonuç kaydını aç. **Bölüm ekle** ile operatörün okuyacağı ek metin yazabilirsin.
2. **Taslağı kaydet** ile değişikliği sakla. Operatör ekranında göstermek için **Yayınla** düğmesini kullan. Operatörün yerel adresi `http://127.0.0.1:8080/istasyon/<adres-adı>` olur.
3. Mevcut MES'te bir iş emrini etkinleştir. Operatör kendi adını girip işi başlatabilir ve adımları doldurabilir. Yeni yayın, başladıktan sonra açık işin talimatlarını veya zorunlu adımlarını değiştirmez. Bir sonraki iş güncel yayını kullanır.

Tasarım ve operatör işlemleri bu sürümde sunucu bilgisayarında yapılır. Yayınlanan kiosk, yapılandırılabilir bir operatör ekranıdır. Yeni kiosk yayınlamak üretim rotası, makine bağlantısı veya OEE hesabı oluşturmaz. İstasyon kayıtları mevcut MES iş emrine bağlı saklanır. Konveyör komutu, konveyör üretim adedi ve OEE sonucu bu kayıtlardan etkilenmez.

Yayınlar ve açık işler mevcut MES durum dosyasına yazılır. Sunucu aynı durum dosyasıyla (`MES_WEB_OEE_RUNTIME_STATE_PATH`) açıldığında operatör, iş emri, başlangıç zamanı ve kullanılan kiosk sürümü korunur. Operatörün henüz tamamlamadığı adım girişleri aynı tarayıcı sekmesinde saklanır. Mevcut Giyotin ve Manuel Kaplama ekranları iki bant parçası bir kutu kuralıyla ayrı olarak çalışmaya devam eder.

### Kaplamadan konveyöre teslim denemesi

Sunucuyu `MES_WEB_CONVEYOR_HANDOFF_ENABLED=1` ile başlat. Açık bir hat vardiyası, aktif iş emri ve kaplanmış en az bir kutuyla `/kaplama` ekranını aç.

1. **Konveyöre teslim et** düğmesi bir kutu için kayıt açar. Bu işlem makine komutu göndermez.
2. Yalnız o kutuyu hatta ver. Hat yeni `QUEUE=ENQ` olayı gönderdiğinde, kutu ve ölçüm kimliğiyle operatör doğrulaması açılır. Bu kısıt, ilk denemede o anda hatta başka kutu verilmemesini gerektirir.
3. Algılanan kutu operatörün verdiği kutuysa **Algılanan kutuyu doğrula** düğmesine bas. Hat tamamlanma olayı geldiğinde **İş Emirleri** ekranı teslim durumunu gösterir. Üretim ve OEE sayımını mevcut hat olayı yapar.

Birden fazla giriş görülürse veya iş emri uyuşmazsa sistem otomatik eşleşme yapmaz. **Kutuyu vermedim** seçeneğini yalnız kutu gerçekten hatta gitmediyse kullan. Hat girişi görüldükten sonra eşleşmeden kapatılan kayıt inceleme için saklanır ve kutu yeniden teslime hazır sayılmaz. İlk doğrulama yerel, sahte hat olaylarıyla yapılır.

## Aktif API

- `GET /health`
- `GET /api/modules`
- `GET /api/modules/{module_id}/dashboard`
- `GET /api/modules/{module_id}/kiosk/bootstrap`
- `GET /api/modules/{module_id}/technician/bootstrap`
- `POST /api/modules/{module_id}/kiosk/register`
- `POST /api/modules/{module_id}/kiosk/shift/start`
- `POST /api/modules/{module_id}/kiosk/shift/stop`
- `POST /api/modules/{module_id}/kiosk/maintenance/complete`
- `POST /api/modules/{module_id}/kiosk/fault/start`
- `POST /api/modules/{module_id}/kiosk/fault/clear`
- `POST /api/modules/{module_id}/kiosk/help/request`
- `POST /api/modules/{module_id}/technician/requests/{request_id}/acknowledge`
- `POST /api/modules/{module_id}/technician/requests/{request_id}/resolve`
- `POST /api/modules/{module_id}/kiosk/system/start`
- `POST /api/modules/{module_id}/kiosk/work-orders/start`
- `POST /api/modules/{module_id}/kiosk/work-orders/accept-active`
- `POST /api/modules/{module_id}/kiosk/quality/override`
- `POST /api/modules/{module_id}/commands`
- `POST /api/modules/{module_id}/oee/control`
- `POST /api/modules/{module_id}/oee/quality-override`
- `POST /api/modules/{module_id}/work-orders/import`
- `POST /api/modules/{module_id}/work-orders/reload`
- `POST /api/modules/{module_id}/work-orders/tolerance`
- `POST /api/modules/{module_id}/work-orders/reorder`
- `POST /api/modules/{module_id}/work-orders/start`
- `POST /api/modules/{module_id}/work-orders/accept-active`
- `POST /api/modules/{module_id}/work-orders/rollback-active`
- `POST /api/modules/{module_id}/work-orders/reset`
- `POST /api/modules/{module_id}/work-orders/inventory/remove`
- `WS /ws/modules/{module_id}`
- `WS /ws/modules/{module_id}/kiosk/{device_id}`
- `WS /ws/modules/{module_id}/technician/{device_id}`

## Kiosk V1 Davranisi

- operator listesi `0_Tanimlamalar` icinden gelir
- device registry backend tarafinda tutulur:
  - `device_id`
  - `device_name`
  - `device_role`
  - `bound_station_id`
  - `last_operator_id`
  - `last_seen_at`
- kioskta aktif is emri, bekleyen is emirleri, son 5 urun, fault/help ve planli bakim akislari vardir
- bekleyen is emirlerinden herhangi biri baslatilabilir; siradaki ilk is emri atlanacaksa sebep zorunludur
- fault, help request ve system start ayri aksiyonlardir
- `Ariza Bildir`, manuel fault ile birlikte teknisyen cagrisi da acar
- kalite duzeltme sadece son 5 tamamlanan urun icin vardir
- mobil tarayicida klavye odagi bozulmasin diye serbest sebep alanlari kioskta browser `prompt` akisi ile alinir

## Teknisyen Kiosk V1 Davranisi

- teknisyen adresi: `http://127.0.0.1:8080/technician/tech-1`
- aktif `open` ve `acknowledged` cagrilari canli listede gosterilir
- `Cevapla`, cagri acilisindan kabul anina kadar olan cevap suresini sabitler
- `Tamamla`, kabulden cozum anina kadar olan giderme suresini ve toplam sureyi sabitler
- tamamlanan cagriya bagli aktif kiosk fault varsa ayni aksiyon fault'u da kapatir
- ekranda `Bugun Cozulenler` ve `Son 10 Cagri` salt okunur gecmis panelleri bulunur

## OEE ve Sure Kurallari

Ic runtime state milisaniye birincil olacak sekilde tutulur. Legacy `sec/min` alanlari sadece geriye uyum icin turetilir.

Temel alanlar:

- `idealCycleMs`
- `plannedStopMs`
- `runtimeMs`
- `unplannedDowntimeMs`
- `manualFaultDurationMs`
- `openingChecklistDurationMs`
- `closingChecklistDurationMs`
- `toleranceMs`

Siniflandirma:

- `openingChecklistDurationMs`
  - OEE disi
  - availability hesabina girmez
- `closingChecklistDurationMs`
  - planned stop / planned maintenance
  - availability tarafinda planli durus olarak ele alinir
- `manualFaultDurationMs`
  - unplanned stop
  - availability tarafinda plansiz durus olarak ele alinir

Formuller:

- `Availability = runtime / planned_production_elapsed`
- `planned_production_elapsed = elapsed - planned_stop_budget`
- `runtime = planned_production_elapsed - unplanned_downtime`
- `Performance = completed / expected_by_shift_rate` veya `completed / expected_by_cycle`
- `expected_by_shift_rate = targetQty * planned_production_elapsed / planned_production_total`
- `Quality = good / total`
- `OEE = Availability * Performance * Quality`

## Workbook ve Kayit

Template:

- `MES_Konveyor_Veritabani_Sablonu.xlsx`

Gunluk canli dosya:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`

Aktif sheet'ler:

- `1_Olay_Logu`
- `2_Olcumler`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `5_OEE_Anliklari`
- `6_Vision`
- `7_Is_Emirleri`
- `8_Depo_Stok`
- `9_Bakim_Kayitlari`
- `99_Raw_Logs`

Bakim detail kaydi `9_Bakim_Kayitlari` sheet'ine, audit ozeti ise `1_Olay_Logu` sheet'ine duser.

Hurda kurali:

- `SCRAP` olarak isaretli tamamlanmis urun depoya dusmez
- inventory'de duran bir urun sonradan `SCRAP` olursa inventory listesinden cikarilir

## Kurulum

En rahat yol:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
Baslaticilar\MES Web.cmd
```

Manuel calistirma:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m pip install -r mes_web\requirements.txt
$env:MES_WEB_HOST = "0.0.0.0"
$env:MES_WEB_PORT = "8080"
python -m mes_web
```

Varsayilan adresler:

- dashboard: `http://127.0.0.1:8080`
- kiosk ornegi: `http://127.0.0.1:8080/kiosk/kiosk-test-1`
- teknisyen ekrani: `http://127.0.0.1:8080/technician/tech-1`
- ayni agdan erisim: `http://<PC_IP>:8080/kiosk/kiosk-test-1`

`Baslaticilar\MES Web.cmd`, server hazir oldugunda dashboard, kiosk ve teknisyen ekranlarini varsayilan tarayicida otomatik acar; linkleri CMD ekraninda da yazar.

## MQTT Notlari

Varsayilan broker ayarlari:

- host: `broker.emqx.io`
- port: `1883`
- topic root: `sau/iot/mega/konveyor`

Onemli:

- `paho-mqtt`, uygulamayi gercekten calistiran ayni Python ortaminda kurulu olmalidir
- launcher hangi Python'u kullaniyorsa paketler de o Python'a kurulmalidir
- `Broker Offline` goruluyorsa once ayni interpreter'da `paho-mqtt` var mi kontrol edilmelidir
- varsayilan MQTT client id bilgisayar + proses bazli benzersiz uretilir; ayni id ile iki istemci baglanirsa broker eski baglantiyi dusurur
- kisa MQTT kopuslari panelde once `Baglaniyor` olarak gosterilir, sure uzarsa `Offline` olur
- kampus veya kurumsal aglarda `1883` cikisi engelleniyorsa broker baglantisi kurulamaz

## Ortam Degiskenleri

Ag ve servis:

- `MES_WEB_HOST`
- `MES_WEB_PORT`
- `MES_WEB_TOPIC_ROOT`
- `MES_WEB_MQTT_HOST`
- `MES_WEB_MQTT_PORT`
- `MES_WEB_MQTT_KEEPALIVE`
- `MES_WEB_MQTT_CLIENT_ID`
- `MES_WEB_MQTT_OFFLINE_GRACE_SEC`

UI ve komut:

- `MES_WEB_UI_PHASE`
- `MES_WEB_COMMAND_MODE`
- `MES_WEB_PUBLISH_ENABLED`
- `MES_WEB_MANUAL_COMMAND_ENABLED`
- `MES_WEB_VISION_INGEST_ENABLED`
- `MES_WEB_VISION_UI_VISIBLE`
- `MES_WEB_OEE_UI_VISIBLE`

WebSocket ve store:

- `MES_WEB_WS_COALESCE_MS`
- `MES_WEB_HEARTBEAT_TIMEOUT_SEC`
- `MES_WEB_BRIDGE_STALE_AFTER_SEC`
- `MES_WEB_LOG_STORE_SIZE`
- `MES_WEB_LOG_RESPONSE_SIZE`
- `MES_WEB_VISION_EVENT_STORE_SIZE`

Dosya ciktilari:

- `MES_WEB_EXCEL_ENABLED`
- `MES_WEB_EXCEL_WORKBOOK_PATH`
- `MES_WEB_EXCEL_TEMPLATE_PATH`
- `MES_WEB_EXCEL_FLUSH_INTERVAL_SEC`
- `MES_WEB_EXCEL_BATCH_SIZE`
- `MES_WEB_OEE_RUNTIME_STATE_PATH`

## Troubleshooting

`Broker Offline`:

1. Uygulamanin gercekte acik oldugunu kontrol et.
2. Launcher'in kullandigi interpreter'i `Start-MesApp.ps1 -App mes_web -PrintCommand` ile gor.
3. Ayni interpreter'da `paho-mqtt` kurulu mu kontrol et.
4. `Test-NetConnection broker.emqx.io -Port 1883` calistir.

`ESP32 Offline` ve `Bridge Offline`:

- broker baglantisi saglansa bile ilgili cihazlar publish etmiyorsa offline gorunur
- `heartbeat` ve `bridge/status` topicleri gelmiyorsa bu iki kart offline kalir

Windows loglarinda `WinError 121`:

- mobil tarayicinin kopan WebSocket baglantisindan gelen benign timeout'lar filtrelenir
- tekil gorulmesi fatal degildir; surekli veri kaybi varsa ag kararliligi ayri kontrol edilmelidir

## Test

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m unittest discover -s tests -p "test_mes_web_*.py"
```
## İstasyona bağlı tablet ve çalışan izleme

| Adres | Erişim |
|---|---|
| `/?module=konveyor_main&tab=operations/bantlama` | Bantlama’ya eşleşmiş tablet veya admin. `bantlama` yerine diğer istasyon kodları kullanılabilir. |
| `/?module=konveyor_main&tab=monitoring` | Şef, mühendis ve admin. İstasyon bilgileri salt okunur. |
| `/atolye-onizleme` | Mühendis ve admin. İstasyon şablonları tasarlanır ve yayınlanır. |
| `/mes-oturum` | Personel girişi. |
| `/tablet-eslestir` | Tek kullanımlık kodla tabletin istasyona bağlanması. |

Ana panel `18780` üzerinde çalışırken her tablet kendi portunun `/` adresinden açılır. `MES_WEB_PORT=18780` ile `python -m mes_web` dokuz adresi tek uygulama olarak başlatır. Başka bir ana panel portu kullanılıyorsa istasyon portlarını `MES_WEB_STATION_PORTS_ENABLED=1` ile açabilirsiniz.

| Port | İstasyon |
|---|---|
| `18781` | Bantlama |
| `18782` | Paketleme |
| `18783` | Giyotin |
| `18784` | Kaplama |
| `18785` | Konveyör |
| `18786` | Tekniker |
| `18787` | Kalite |
| `18788` | Malzeme |

Admin, Kiosk Tasarımcı’dan bir istasyon için kod oluşturur. Tablette MES sunucusunun ilgili portundaki `/tablet-eslestir` adresi açılır ve kod girilir. Kod 10 dakika kullanılabilir. Eşleşme 30 günlük, HttpOnly ve istasyon kimliği imzalı bir çerezle korunur. Her istasyon portu kendi ekranını ve işlem API’sini açar. Tablete diğer istasyonlar ve yönetim yolları sunucudan `403` döndürür. Tablet bilgisayarında tam ekran tarayıcı ve işletim sistemi kilidi cihazın kiosk ayarlarıyla sağlanır.

Dağıtımda HTTPS kullanılır. `admin` için `MES_WEB_WORKSPACE_ADMIN_PASSWORD`, `sef` için `MES_WEB_WORKSPACE_SUPERVISOR_PASSWORD`, `muhendis` için mevcut `MES_WEB_KIOSK_DESIGN_PASSWORD` kullanılır. `MES_WEB_WORKSPACE_SESSION_SECRET` yeniden başlatmalar arasında oturum imzasını korur. `MES_WEB_WORKSPACE_STATE_PATH` ayrı bir SQLite dosyasını işaret ederse şablonlar ve örnek istasyon kayıtları yeniden başlatmalarda saklanır. Eşleştirme kodu, üretildiği sunucu sürecinde kullanılır.

Yeni istasyon yüzeyleri ayrı örnek veri üzerinde çalışır. İzleme sayfası ortak örnek durumu üç saniye arayla okur. OEE değeri örnek göstergedir. Kaplama ve Bantlama, örnek akışları göstermek için ayrı ekranlarla sunulur.

### Sistem Durumu ve Kamera Kayıtları

Kamera geçmişi ve sistem bağlantı olayları, OEE çalışma durumu dosyasının yanındaki `*.telemetry.sqlite3` dosyasına yazılır. Yerel önizleme kendi deneme klasöründeki depoyu kullanır. Kamera tablosu MQTT `/vision/events` kanalındaki çizgi geçişlerini ve açıkça bildirilen okuma hatalarını kaydeder. Takip başlangıcı ve kaybı kamera okuması sayılmaz. Okuma ayrıntısında ham mesaj, doğrulanmış eşleşme ve varsa ürün bilgisi bulunur. Günlük özet ve tarih/saat filtreleri Türkiye saatini kullanır.

### AnyLogic senaryoları

AnyLogic sekmesi `Excel_Test_Konveyor` modelinin yerel dışa aktarımıyla çalışır. Excel testi T01–T14 arasındaki kutu dizisini ve kamera sürelerini kullanır. Sentetik sürekli akış seçildiğinde model, Excel’den aldığı renk ve kamera sürelerine göre örnek giriş üretir. Modelin Excel testi renk depolarında biter. Her koşunun giriş ayarları, model kimliği ve CSV olay raporu yerel çalışma durumu klasöründeki `anylogic-runs` altında saklanır.

Kurulu **AnyLogic 8.9 Professional** ve referans modelle yerel dışa aktarım hazırlamak için proje kökünde `python -B -m mes_web.prepare_anylogic <Excel_Test_Konveyor.alp>` çalıştırın. `AnyLogic_Test_Plani.xlsx` referans modelle aynı klasörde bulunur. Hazırlayıcı `.local/anylogic` altında kopya ve Java köprüsü oluşturur. [AnyLogic Java dışa aktarım belgesi](https://anylogic.help/anylogic/running/export-java-application.html)

#### Masaüstü AnyLogic ve MQTT

Referans modelin ve Excel planının bulunduğu klasörden **MQTT kopyasını** hazırlayın. Hazırlayıcı orijinal dosyayı okur ve MQTT kopyasını ayrı bir derleme çalışma alanında dışa aktarır.

```powershell
python -B -m mes_web.prepare_anylogic 'C:/model/Excel_Test_Konveyor.alp' --mqtt
python -B -m pip install --target .local/mqtt-broker -r mes_web/requirements-anylogic-mqtt.txt
```

Her komutu proje kökünde ayrı terminalde çalıştırın. İlk ikisi açıkken MES'i başlatın.

1. Broker için `$env:PYTHONPATH = (Resolve-Path .local/mqtt-broker).Path` ve ardından `python -B -m mes_web.anylogic_broker` çalıştırın. Aynı bilgisayarda bir MQTT broker'ınız varsa onun yerel portunu kullanabilirsiniz.
2. Çalıştırıcı için `python -B -m mes_web.anylogic_gateway` çalıştırın.
3. Normal MES kurulumunda PowerShell'de `$env:MES_ANYLOGIC_MQTT_ENABLED = '1'` ayarını yapıp `python -B -m mes_web` çalıştırın. Bu bilgisayardaki izole önizleme için `python -B .local/start-preview.py --port 18880 --anylogic-mqtt` kullanılabilir. MQTT ayarı kapalıyken AnyLogic'in mevcut yerel çalıştırıcısı kullanılır.

**Masaüstünden başlatma.** AnyLogic Professional'da **File → Open model** ile `.local/anylogic-mqtt/runtime/model/Excel_Test_Konveyor.alp` dosyasını açın. **Projects → Simulation → Run (F5)** ile başlatın. Aynı adlı referans model açıksa kendi çalışmalarınızı kaydettikten sonra o modeli kapatın veya kopyayı ayrı bir çalışma alanıyla açın. Örneğin AnyLogic'in komut satırında `-data <ayrı-çalışma-alanı> <kopyanın-tam-yolu>` kullanabilirsiniz. Masaüstü kopyası ek Java kodu eklemenizi gerektirmez. Masaüstü varsayılanları `.local/anylogic-mqtt/desktop/uretim_modu.txt` ve `senaryo.txt` dosyalarındadır. Başlangıçta **SUREKLI** ve **T07** kullanılır.

**MES'ten izleme ve kontrol.** **MES veri kaynağı → AnyLogic simülasyonu → Dijital İkiz** yolunda başlatma, duraklatma, devam, durdurma ve sıfırlama düğmeleri vardır. Başlatma, **AnyLogic** sekmesindeki mod, senaryo ve hız seçimini kullanır. Masaüstünde açık bir MQTT koşusu varsa MES onu izler ve komutları aynı koşuya iletir. Motor kapalıysa MES, aynı modelin yerel Java dışa aktarımını başlatır. **Durdur** son görüntüyü korur. **Sıfırla** açık koşuyu kapatıp ekranı yeni koşuya hazırlar. CSV raporları `.local/anylogic-mqtt/anylogic-runs` altında bulunur.

| Ayar | Yerel varsayılan |
| --- | --- |
| `MES_ANYLOGIC_MQTT_HOST` | `127.0.0.1` |
| `MES_ANYLOGIC_MQTT_PORT` | `18883` |
| `MES_ANYLOGIC_MQTT_TOPIC` | `at-zeze/anylogic/v1` |

Broker, köprü ve MES aynı portu kullanır. Broker yalnız bu bilgisayarda dinler. MES ve köprü aynı konu kökünü kullanır.

| MQTT konusu | Yön | İçerik |
| --- | --- | --- |
| `at-zeze/anylogic/v1/command` | MES → köprü | Komut, koşu kimliği, istek kimliği, zaman, senaryo ve hız. QoS 1. |
| `at-zeze/anylogic/v1/ack` | Köprü → MES | Aynı istek kimliğiyle sonuç, motor durumu ve varsa hata. QoS 1. |
| `at-zeze/anylogic/v1/telemetry` | Köprü → MES | Köprü sıra numarası, koşu durumu, sayaçlar, robot ve kutu konumları, son model olayları. QoS 0. |

Mesajlar `schema: 1` alanlı JSON'dur. Başlatma ve kontrol komutları süre ve koşu kimliğiyle doğrulanır. Yeniden gelen aynı istek kimliği, önceden alınan sonucu döndürür. Broker yeniden bağlandığında güncel tam kare tekrar gelir. Canlı kare son 512 model olayını taşır. Daha eski olaylar koşunun CSV'sindedir. Telemetri dört saniye kesilirse MES köprü bağlantı kaybı gösterir. Fiziksel MQTT alıcısı ve üretim kayıtları ayrı akıştadır.

| AnyLogic ölçümü | MES bölümü |
| --- | --- |
| `bant_kesme` ve `kutu_kaplama` çıkış sayaçları | Operasyon → İstasyon çıkışları |
| Kamera, konveyör, robot, ara depo ve renk depoları | Operasyon, OEE, Dijital İkiz |
| `DEPOLANDI` olayındaki planlanan girişten depoya süre | OEE → Son üretim hareketleri |
| `BANT_DURDU` olayındaki neden | OEE → Arıza ve duruşlar |

Modelde kaplama ve kesme simülasyon blokları vardır. Bantlama ve paketleme iş emirleri, tekniker kayıtları, gerçek vardiya, kalite kararı ve ideal çevrim için model verisi bulunmadığından bu alanlar boş gösterilir. Fiziksel tablet kayıtları için ilgili donanım kaynağı kullanılır.

**Uygulama dosyaları**

- `prepare_anylogic.py` ve `anylogic_assets/desktop-mqtt.java.txt` masaüstü modelini ve dışa aktarımı hazırlar.
- `anylogic_mqtt.py`, `anylogic_gateway.py`, `anylogic_runner.py` ve `anylogic_broker.py` simülasyon telemetrisi, komut onayı, süreç yönetimi ve yerel broker'ı sağlar.
- `station_workspace.py` ve `app.py` mevcut AnyLogic API'sini seçilen çalıştırıcıya bağlar.
- `static/index.html`, `static/simulation-mes.mjs`, `static/anylogic-panel.mjs`, `static/anylogic-panel.css` ve `static/app.js` Dijital İkiz kontrollerini, bağlantı durumlarını ve istasyon verilerini gösterir.


### Giyotin loglarının MES’e bağlanması

Giyotin tabletinin kesim formu deneme iş emrine operatör girişi yazar. Aynı `requestId` ile aynı kayıt yeniden gelirse kesilen bant adedi bir kez artar. Kayda `manual` kaynağı ve MES kayıt zamanı eklenir. Eski ve örnek kayıtlar için kaynak ve zaman geriye dönük atanmaz.

Zehra’dan ilk örnek için bir bıçaksız test oturumunun değiştirilmemiş seri veya MQTT logunu ve gözlem notunu alın. Normal çevrim, cihaz açılışı veya yeniden başlatma, bağlantı kesilip geri gelmesi ve varsa tekrar iletilen olay aynı örnekte görülebilir. Gözlem notuna beklenen başarılı çevrim adedini, cihaz ve yazılım sürümünü, saat dilimini ve her sayacın birimini ekleyin. MQTT kullanıldıysa konu adını ve ham mesajı birlikte saklayın.

1. İlk karşılaştırmayı çevrimdışı bir örnek iş emrinde yapın. Cihaz ve oturum kimliği, tekil olay veya sıra numarası, cihaz zamanı ve MES’in alım zamanı, olay türü, miktar ve birim eşlemelerini ham kayıttan çıkarın. İş emri, renk ve kalite alanları cihazda yoksa doğrulandıkları MES veya operatör kaydını belirtin. Çevrim kaydı tek başına uygun bant miktarını kanıtlamaz.
2. Aynı dosyayı iki kez oynatın. İkinci oynatımda çıktı ve WIP değişmemeli. Sayaç sıfırlanmasını, sıra boşluklarını ve emri belirlenemeyen olayları mutabakat için kaydedin.
3. Eşleme doğrulanınca adaptörü aktif iş emri, tekrar koruması ve bant tüketimini yöneten MES kesim akışına bağlayın. Tablet de aynı MES kaydını okumalı. Tabletin deneme SQLite verisi fiziksel olay alıcısı olarak kullanılmaz. İlk entegrasyon testinde iki uygun bant bir kutuluk bant ihtiyacını karşılar, konveyör ve paket sayaçları kendi olaylarıyla ilerler.
