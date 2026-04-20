# MQTT Topics

Ana root:

- `sau/iot/mega/konveyor/`

Varsayilan broker:

- `broker.emqx.io:1883`

Bu belge aktif topicleri ve bugunku publisher/subscriber rollerini ozetler.

## Onemli Mimari Not

- browser dashboard ve browser kiosk MQTT'ye dogrudan baglanmaz
- MQTT subscriber/publisher rolu backend'deki `mes_web` icindedir
- kiosk aksiyonlari REST ile gelir; gerekirse `mes_web` `cmd` topic'ine publish eder

## Ana Hat Topicleri

| Topic | Publisher | Subscriber | Payload | Amac |
| --- | --- | --- | --- | --- |
| `.../status` | ESP32 | `mes_web` | text | retained hat durumu |
| `.../logs` | ESP32 | `mes_web`, workbook sink | text | olay ve operasyon log akisi |
| `.../heartbeat` | ESP32 veya cihaz katmani | `mes_web` | text | cihaz yasam belirtisi |
| `.../bridge/status` | ESP32 | `mes_web` | text | Wi-Fi, MQTT, queue, drop telemetry |
| `.../tablet/log` | legacy tablet veya text audit akisi | `mes_web` | text | OEE snapshot, fault ve sistem satirlari |
| `.../cmd` | `mes_web` | ESP32 -> Mega | text | preset komut akisi |

## Vision Topicleri

| Topic | Publisher | Subscriber | Payload | Amac |
| --- | --- | --- | --- | --- |
| `.../vision/status` | Raspberry vision observer | `mes_web` | JSON | vision servis durumu |
| `.../vision/tracks` | Raspberry vision observer | `mes_web` | JSON | aktif track ozetleri |
| `.../vision/heartbeat` | Raspberry vision observer | `mes_web` | JSON | vision yasam belirtisi |
| `.../vision/events` | Raspberry vision observer | `mes_web`, workbook sink | JSON | crossing ve renk olaylari |
| `.../vision/clock_status` | Raspberry vision observer | yerel diagnostik araclari | JSON | saat offset ve sync sonucu |
| `.../vision/time_sync` | `raspberry/tools/publish_time_sync.ps1` | Raspberry vision observer | JSON | observer clock sync talebi |

## Pick-to-Light Topicleri

Pick-to-light ayri moduldur. Prefix:

- `sau/iot/mega/konveyor/picktolight/station/`

## Komut Payload Notlari

Bugunku desteklenen preset'ler:

- `start`
- `stop`
- `rev`
- `status`
- `q`
- `pickplace`
- `cal x`
- `cal k`
- `cal s`
- `cal m`

Ozel durum:

- `__reset_counts__`
  - MQTT uzerinden Mega'ya gitmez
  - backend icinde yerel sayac sifirlama aksiyonu olarak islenir

## Parslama Notlari

- `status` dashboard alanlarini besler
- `logs` hem canli log panelini hem workbook projector'unu besler
- `tablet/log` legacy fault ve audit kanalidir
- `vision/events` pasif capraz kontrol icindir; sorting karari vermez

## Su Anda Aktif Olmayanlar

Asagidaki aileler plan notlarinda gecse de bugun aktif MQTT kontrati degildir:

- `.../mes/state/*`
- `.../tablet/event/*`

Bugunku kiosk implementasyonu bunlar yerine `mes_web` REST + WebSocket katmanini kullanir.
