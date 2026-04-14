# MES Web

`mes_web/`, konveyor hattinin yeni web tabanli operator ve OEE katmanidir. Bu klasor; MQTT ingest, normalize dashboard snapshot, WebSocket canli yayin, vardiya kontrollu OEE runtime ve workbook tabanli kayit yazimi islerini tek yerde toplar.

## Ana Hedef

Legacy Node-RED akislarini repo disi tutarken, ayni topic kontrati uzerinde yeni ekran ve veri katmanini olgunlastirmak.

## Bu Katmanin Sorumluluklari

- MQTT topiclerini dinlemek
- dashboard icin normalize snapshot uretmek
- browser'a REST + WebSocket ile veri vermek
- preset ve serbest komutlari `cmd` topic'ine publish etmek
- vardiya / hedef / ideal cycle / planned stop ayarlarini yonetmek
- OEE hesabini backend tarafinda yapmak
- gunluk workbook'a kayit yazmak

## Calisan Parcalar

### API

- `GET /health`
- `GET /api/modules`
- `GET /api/modules/{module_id}/dashboard`
- `POST /api/modules/{module_id}/commands`
- `POST /api/modules/{module_id}/oee/control`
- `WS /ws/modules/{module_id}`

### Frontend

- operasyon sekmesi
- OEE sekmesi
- reconnect eden WebSocket istemcisi
- komut paneli
- vardiya ayarlari paneli

### Persistence

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
- `logs\oee_runtime_state.json`

## OEE Davranisi

### Vardiya Kurali

- sistem acildiginda daha once acik kalmis vardiya otomatik surdurulmez
- operator `Vardiya Baslat` butonuna basmadan OEE sayimi baslamaz

### Tamamlanan Urun Kurali

- aktif vardiyada `PICKPLACE_DONE` geldiginde urun tamamlanmis kabul edilir
- tamamlanan urun varsayilan olarak `Saglam` sayilir
- manuel `Rework/Hurda` duzeltme UI'si henuz gelismektedir

### OEE Formulu

- `Availability = runtime / planned_production_elapsed`
- `planned_production_elapsed = elapsed - prorated_planned_stop_budget`
- `runtime = planned_production_elapsed - unplanned_downtime`
- `Performance = completed / expected_by_shift_rate` veya `completed / expected_by_cycle`
- `TARGET` modunda beklenen adet `runtime / (planlanan_uretim_suresi)` oranina gore akar; planli durus availability kaybi sayilmaz
- `Quality = good / total`
- `OEE = Availability * Performance * Quality`

### Fault Kaynagi

- `tablet/log` icindeki fault satirlari runtime state'e islenir

## Workbook Yazimi

Template:

- `MES_Konveyor_Veritabani_Sablonu.xlsx`

Gunluk canli dosya:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`

Doldurulan sheet'ler:

- `1_Olay_Logu`
- `2_Olcumler`
- `4_Uretim_Tamamlanan`
- `6_Vision`
- `7_Raw_Logs`

Template dosya korunur. Runtime, template'in uzerine yazmaz; gunluk kopya uzerinde calisir.

## Ana Dosyalar

- `app.py`
  - FastAPI route'lari
- `runtime.py`
  - MQTT + Excel sink + watchdog koordinasyonu
- `mqtt_runtime.py`
  - broker baglantisi ve topic dispatch
- `store.py`
  - dashboard snapshot store'u
- `oee_state.py`
  - vardiya, sayac, fault ve OEE runtime state mantigi
- `excel_runtime.py`
  - workbook projector ve sink
- `parsers.py`
  - Mega, tablet ve vision parser'lari
- `static/app.js`
  - browser tarafi istemci mantigi
- `static/index.html`
  - panel iskeleti
- `static/styles.css`
  - responsive stil

## Kurulum

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m pip install -r mes_web\requirements.txt
python -m mes_web
```

Varsayilan adres:

- `http://127.0.0.1:8080`

## Ortam Degiskenleri

### Ag ve servis

- `MES_WEB_HOST`
- `MES_WEB_PORT`
- `MES_WEB_TOPIC_ROOT`
- `MES_WEB_MQTT_HOST`
- `MES_WEB_MQTT_PORT`
- `MES_WEB_MQTT_KEEPALIVE`
- `MES_WEB_MQTT_CLIENT_ID`

### UI ve komut

- `MES_WEB_UI_PHASE`
- `MES_WEB_COMMAND_MODE`
- `MES_WEB_PUBLISH_ENABLED`
- `MES_WEB_MANUAL_COMMAND_ENABLED`
- `MES_WEB_VISION_INGEST_ENABLED`
- `MES_WEB_VISION_UI_VISIBLE`
- `MES_WEB_OEE_UI_VISIBLE`

### WebSocket ve store

- `MES_WEB_WS_COALESCE_MS`
- `MES_WEB_HEARTBEAT_TIMEOUT_SEC`
- `MES_WEB_BRIDGE_STALE_AFTER_SEC`
- `MES_WEB_LOG_STORE_SIZE`
- `MES_WEB_LOG_RESPONSE_SIZE`
- `MES_WEB_VISION_EVENT_STORE_SIZE`

### Dosya Ciktilari

- `MES_WEB_EXCEL_ENABLED`
- `MES_WEB_EXCEL_WORKBOOK_PATH`
- `MES_WEB_EXCEL_TEMPLATE_PATH`
- `MES_WEB_EXCEL_FLUSH_INTERVAL_SEC`
- `MES_WEB_EXCEL_BATCH_SIZE`
- `MES_WEB_OEE_RUNTIME_STATE_PATH`

## WebSocket Davranisi

- sayfa ilk once REST snapshot alir
- sonra WebSocket baglanir
- her baglantida tam snapshot gonderilir
- baglanti koparsa son snapshot ekranda kalir
- istemci otomatik reconnect dener

## Sinirlar

- manuel kalite override ekrani henuz eksik
- workbook rebuild / replay araci henuz yok
- resmi FERP JSON cikti kontrati henuz eklenmedi
- coklu modullu ayni anda canli kullanim sonraki fazdir

## Test

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m unittest discover -s tests -p "test_mes_web_*.py"
```
