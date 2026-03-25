# MQTT Topics

## Ana Root

`sau/iot/mega/konveyor/`

Bu root, Mega ve ESP32 tarafindaki ana haberlesme icin sabit kabul edilmelidir.

## Ana Topicler

### `sau/iot/mega/konveyor/cmd`

- Yon: uygulama veya operator -> ESP32 -> Mega
- Amac: komut iletimi
- Payload tipi: text

### `sau/iot/mega/konveyor/status`

- Publisher: ESP32
- Kaynak: Mega tarafindan uretilen `MEGA|STATUS|...` satirlari
- Amac: mevcut durumun retained olarak yayinlanmasi
- Payload tipi: text

### `sau/iot/mega/konveyor/logs`

- Publisher: ESP32
- Kaynak: Mega log satirlari
- Amac: operasyonel log akisinin yayinlanmasi
- Payload tipi: text

### `sau/iot/mega/konveyor/heartbeat`

- Publisher: bridge veya cihaz katmani
- Amac: yasam belirtisi
- Payload tipi: text

### `sau/iot/mega/konveyor/bridge/status`

- Publisher: ESP32
- Amac: queue uzunlugu, dusen satir sayisi, Wi-Fi ve MQTT durumu
- Payload tipi: text

## Vision Topicleri

Vision observer kendi alt root'unu kullanir:

`sau/iot/mega/konveyor/vision`

Bu root altinda beklenen topicler:

- `.../status`: retained durum bilgisi, JSON
- `.../heartbeat`: periyodik heartbeat, JSON
- `.../tracks`: aktif track snapshot'lari, JSON
- `.../events`: `box_confirmed`, `box_lost`, `line_crossed` gibi olaylar, JSON

## Topic Kurallari

- Mevcut root yapisi korunmalidir.
- Ana kontrol topicleri text payload kullanirken vision topicleri JSON kullanir.
- Yeni topic gerekiyorsa mevcut root altinda anlamli bir suffix ile eklenmelidir.
- Mevcut topic adlari kod ve dashboard tarafinda sabit kabul edildigi icin keyfi olarak degistirilmemelidir.

## AI Icin Notlar

- Yeni bir topic onerirken publisher, subscriber ve payload tipini birlikte yazin.
- `status` ile `logs` topiclerini birlestirmeyin; farkli kullanim amaclari vardir.
- Vision topiclerini ana root ile karistirmayin; `vision` alt agaci ayri bir moduldur.
