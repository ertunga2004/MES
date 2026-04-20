# Tablet Kiosk Durumu

Bu dosya ilk plan notu degil, mevcut kiosk v1 implementasyonunu ozetler.

## Mimari

- tablet veya telefon ayni LAN/Wi-Fi icinden browser ile baglanir
- kiosk adresi: `http://<mes_web_host>:8080/kiosk/{device_id}`
- kiosk MQTT'ye dogrudan baglanmaz
- tum state ve aksiyonlar `mes_web` uzerinden gider

## Aktif Route'lar

- `GET /kiosk/{device_id}`
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
- `WS /ws/modules/{module_id}/kiosk/{device_id}`

## UI Bloklari

Kiosk ekrani su alanlardan olusur:

- hat durumu ve KPI strip
- aktif is emri / genel akis
- fault ve yardim grubu
- bekleyen is emirleri
- son 5 urun kalite duzeltme

## Is Emri Davranisi

- operator bekleyen listedeki herhangi bir is emrini baslatabilir
- siradaki ilk is emri atlanacaksa sebep zorunludur
- aktif is emri `pending_approval` olunca operator onayi gerekir
- sistem `start` komutu kiosk uzerinden de verilebilir
- aktif ve bekleyen is emirlerinde kutu icerigi renk bazli adetleri ile gorunur

## Kalite Davranisi

- sadece son 5 tamamlanan urun gorunur
- satirda `item_id`, renk ve kalite durumu gorulur
- `GOOD / REWORK / SCRAP` secilebilir
- opsiyonel sebep girilebilir
- hurda urun depoya dusmez

## Fault ve Yardim Davranisi

Fault grubunda ayri aksiyonlar vardir:

- `Yardim Cagir`
- `Ariza Bildir`
- `Ariza Bitir`

Help request backend state'inde `open`, `acknowledged`, `resolved` yasam dongusu ile tutulur. Kiosk bugun sadece talep acabilir; ack/resolve gelecekte teknisyen ekranindan gelecek sekilde tasarlanmistir.

## Bakim ve Vardiya Davranisi

- vardiya baslatma acilis checklist'i ile acilir
- vardiya bitirme kapanis checklist'i ile kapanir
- `openingChecklistDurationMs` OEE disidir
- `closingChecklistDurationMs` planned stop / planned maintenance olarak sayilir
- `manualFaultDurationMs` unplanned stop olarak sayilir

Bu ayrim availability hesabinda backend tarafinda uygulanir.

## Mobil Tarayici Notu

Telefonlarda canli render sirasinda klavye kapanip acilmasin diye kioskta serbest metin alanlari inline textarea yerine browser `prompt` akisi ile alinir.

Kullanilan yerler:

- fault icin harici sebep
- kalite override icin opsiyonel sebep
- siradaki is emri atlanirken gecis sebebi

## Device Registry

Backend'de cihaz bazli audit tutulur:

- `device_id`
- `device_name`
- `device_role`
- `bound_station_id`
- `last_operator_id`
- `last_seen_at`

## Limitler

Su an henuz yok:

- teknisyen el terminali UI
- kiosk tarafinda eski urun arama
- rollback veya geri alma aksiyonlari
- direct MQTT JSON tablet topic kontrati

## Gelecek Adimlar

- teknisyen tablet ekraninin eklenmesi
- kiosk auth / PIN katmani
- yeni MQTT JSON domain contract'i gerekirse ayri versiyon olarak tasarlanmasi
