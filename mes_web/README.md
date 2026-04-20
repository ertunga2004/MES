# MES Web

`mes_web/`, konveyor hattinin aktif web katmanidir. Bu klasor; MQTT ingest, dashboard snapshot, kiosk UI, vardiya kontrollu OEE runtime state ve workbook kaydini tek yerde toplar.

## Ana Sorumluluklar

- MQTT topiclerini dinlemek
- browser icin REST + WebSocket snapshot uretmek
- dashboard ve kiosk ekranlarini servis etmek
- preset komutlari `cmd` topic'ine publish etmek
- vardiya, OEE, fault, quality ve work order state'ini backend'de yonetmek
- gunluk workbook'a normalize audit ve rapor kaydi yazmak

## Aktif Ekranlar

- `GET /`
  - ana dashboard
- `GET /kiosk/{device_id}`
  - ayni agdaki telefon, tablet veya laptop icin operator kiosk ekrani

Kiosk browser tabanlidir. MQTT kullanmaz; `mes_web` ile REST + WebSocket uzerinden konusur.

## Aktif API

- `GET /health`
- `GET /api/modules`
- `GET /api/modules/{module_id}/dashboard`
- `GET /api/modules/{module_id}/kiosk/bootstrap`
- `POST /api/modules/{module_id}/kiosk/register`
- `POST /api/modules/{module_id}/kiosk/shift/start`
- `POST /api/modules/{module_id}/kiosk/shift/stop`
- `POST /api/modules/{module_id}/kiosk/maintenance/complete`
- `POST /api/modules/{module_id}/kiosk/fault/start`
- `POST /api/modules/{module_id}/kiosk/fault/clear`
- `POST /api/modules/{module_id}/kiosk/help/request`
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
- kalite duzeltme sadece son 5 tamamlanan urun icin vardir
- mobil tarayicida klavye odagi bozulmasin diye serbest sebep alanlari kioskta browser `prompt` akisi ile alinir

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
- ayni agdan erisim: `http://<PC_IP>:8080/kiosk/kiosk-test-1`

## MQTT Notlari

Varsayilan broker ayarlari:

- host: `broker.emqx.io`
- port: `1883`
- topic root: `sau/iot/mega/konveyor`

Onemli:

- `paho-mqtt`, uygulamayi gercekten calistiran ayni Python ortaminda kurulu olmalidir
- launcher hangi Python'u kullaniyorsa paketler de o Python'a kurulmalidir
- `Broker Offline` goruluyorsa once ayni interpreter'da `paho-mqtt` var mi kontrol edilmelidir
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
