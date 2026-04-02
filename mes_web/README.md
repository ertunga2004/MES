# MES Web

Bu klasor, Node-RED'i kapatmadan yeni operator ekranini ve canli backend'i ayni repo icinde calistirmak icin eklendi.

## Ne Yapar

- MQTT topiclerini dinler ve normalize edilmis dashboard snapshot'i uretir
- `GET /api/modules/{module_id}/dashboard` ile ilk ekran snapshot'ini verir
- `WS /ws/modules/{module_id}` ile tam snapshot tabanli canli guncelleme yayinlar
- Preset ve serbest komutlari `cmd` topic'ine publish edebilir
- Vision ve tablet topiclerini UI'da gostermeden store icinde saklar
- Normalize edilen olaylari dogrudan Excel workbook'a yazar

## Faz 1 Kapsami

- cekirdek operasyon ekrani
- responsive web istemci
- reconnect eden WebSocket istemcisi
- varsayilan `full_live` komut modu

## Kurulum

Python 3.11+ ile:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m pip install -r mes_web\requirements.txt
python -m mes_web
```

Not:

- WebSocket endpoint'inin calismasi icin `websockets` bagimliligi gerekir. `mes_web\requirements.txt` bunu kurar.
- Excel sink icin `openpyxl` gerekir. Requirements dosyasi bunu da kurar.

Varsayilan adres:

- `http://127.0.0.1:8080`
- Excel cikti dosyasi: `C:\Users\acer\Documents\.CODE\codex\MES\logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
- Bu dosya her gun icin `logs/` altina tarihli adla uretilir.
- Kaynak taslak dosya korunur; canli workbook taslaktan kopyalanarak olusturulur.

## Ortam Degiskenleri

- `MES_WEB_HOST`
- `MES_WEB_PORT`
- `MES_WEB_TOPIC_ROOT`
- `MES_WEB_MQTT_HOST`
- `MES_WEB_MQTT_PORT`
- `MES_WEB_COMMAND_MODE`
- `MES_WEB_PUBLISH_ENABLED`
- `MES_WEB_MANUAL_COMMAND_ENABLED`
- `MES_WEB_VISION_INGEST_ENABLED`
- `MES_WEB_EXCEL_ENABLED`
- `MES_WEB_EXCEL_WORKBOOK_PATH`
- `MES_WEB_EXCEL_TEMPLATE_PATH`
- `MES_WEB_EXCEL_FLUSH_INTERVAL_SEC`
- `MES_WEB_EXCEL_BATCH_SIZE`

Ornek:

```powershell
$env:MES_WEB_PUBLISH_ENABLED = "true"
$env:MES_WEB_MANUAL_COMMAND_ENABLED = "false"
python -m mes_web
```

## Test

Harici paket gerektirmeyen cekirdek testler:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m unittest discover -s tests -p "test_mes_web_*.py"
```
