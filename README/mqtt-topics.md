# MQTT Topics

Ana root:

- `sau/iot/mega/konveyor/`

Bu belge, aktif topicleri ve bugunku publisher/subscriber rollerini ozetler. Legacy Node-RED akis dosyalari repo icinde bulunmaz; parity ihtiyaclari yerel arsiv uzerinden karsilanir.

## Ana Hat Topicleri

| Topic | Publisher | Subscriber | Payload | Amac |
| --- | --- | --- | --- | --- |
| `.../status` | ESP32 | `mes_web`, yerel parity araclari | text | retained hat durumu |
| `.../logs` | ESP32 | `mes_web`, workbook sink | text | olay ve operasyon log akisi |
| `.../heartbeat` | ESP32 veya cihaz katmani | `mes_web`, yerel parity araclari | text | cihaz yasam belirtisi |
| `.../bridge/status` | ESP32 | `mes_web`, yerel parity araclari | text | Wi-Fi, MQTT, queue, drop telemetry |
| `.../tablet/log` | tablet veya legacy akisi | `mes_web` | text | OEE snapshot, fault ve sistem satirlari |
| `.../cmd` | `mes_web` | ESP32 -> Mega | text | preset ve manuel komut akisi |

## Vision Topicleri

| Topic | Publisher | Subscriber | Payload | Amac |
| --- | --- | --- | --- | --- |
| `.../vision/status` | Raspberry vision observer | `mes_web` | JSON | vision servis durumu |
| `.../vision/tracks` | Raspberry vision observer | `mes_web` | JSON | aktif track ozetleri |
| `.../vision/heartbeat` | Raspberry vision observer | `mes_web` | JSON | vision yasam belirtisi |
| `.../vision/events` | Raspberry vision observer | `mes_web`, workbook sink | JSON | crossing ve renk olaylari |
| `.../vision/clock_status` | Raspberry vision observer | yerel diagnostik / operasyon araclari | JSON | saat offset'i ve time sync sonucu |
| `.../vision/time_sync` | `raspberry/tools/publish_time_sync.ps1` veya operator araci | Raspberry vision observer | JSON | observer clock sync talebi |

## Pick-to-Light Topicleri

Pick-to-light ayri moduldur. Kendi root'u altinda calisir ve ana konveyor root'u ile karistirilmamalidir.

Prefix:

- `sau/iot/mega/konveyor/picktolight/station/`

| Topic | Publisher | Subscriber | Payload | Amac |
| --- | --- | --- | --- | --- |
| `.../display` | Python GUI | ESP32 ekran | text | ekranda gosterilecek satirlar |
| `.../button` | ESP32 ekran / buton | Python GUI | text | kisa basma gecis istegi |
| `.../command` | ESP32 ekran / buton | Python GUI | JSON veya text | `undo` ve `reset` gibi aksiyonlar |
| `.../state` | Python GUI | ust sistemler / yerel izleme | JSON | retained istasyon snapshot'i |
| `.../event` | Python GUI | ust sistemler / yerel izleme | JSON | operasyon olay akisi |
| `.../python_status` | Python GUI | ESP32 ekran, yerel izleme | JSON | GUI baglanti / otorite durumu |
| `.../esp32_status` | ESP32 ekran | Python GUI, yerel izleme | JSON | ekran istemcisi baglanti durumu |
| `.../heartbeat` | Python GUI ve ESP32 ekran | yerel izleme | JSON | yasam belirtisi |

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

- `status` satiri anlik dashboard alanlarini besler
- `logs` satiri hem canli log panelini hem workbook projector'unu besler
- `tablet/log` satiri OEE, vardiya fault ve runtime trend tarafina veri saglar
- `vision/events` pasif capraz kontrol icindir, sorting karari vermez
