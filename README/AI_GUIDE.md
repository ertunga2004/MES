# AI Guide

Bu belge, repo uzerinde calisan ekip uyelerinin ChatGPT, Codex veya benzeri araclara daha dogru baglam vermesini saglar. Amac, AI'nin eski CSV merkezli varsayimlara veya sadece Node-RED tabanli bir zihniyete kaymasini engellemektir.

## Repo Icin Kisa Baglam

- ana uygulama katmani `mes_web/` altindadir
- fiziksel kontrol otoritesi `mega.cpp` tarafindadir
- MQTT bridge `esp32.cpp` tarafindadir
- workbook ve OEE runtime backend tarafinda uretilir
- Node-RED repo disi yerel arsiv olarak dusunulmelidir; yeni ana gelistirme hedefi degildir

## AI'ye Verilmesi Gereken Temel Gercekler

- MQTT root'u `sau/iot/mega/konveyor/` olarak kalir
- `PICKPLACE_DONE` tamamlanan urun anlamina gelir
- tamamlanan urun varsayilan olarak `good` kabul edilir
- kalite override dashboard ve kiosk uzerinde aktif olarak vardir
- kiosk sadece son 5 tamamlanan urun icin quality override yapar
- `__reset_counts__` artik Mega'ya gitmez, backend icinde yerel calisir
- OEE aktif vardiya olmadan baslamaz
- sistem acildiginda onceki vardiya otomatik acik gelmez
- dahili sure alani birincil olarak ms tutulur
- birincil kalici veri siniri CSV degil, workbook'tur

## AI'den Beklenen Varsayimlar

- yeni ekran veya veri akisi onerirken `mes_web` hedeflenmelidir
- dashboard kontrati bozulmamali, mevcut snapshot alanlari korunmalidir
- Mega tarafina yeni karar otoritesi yuklenmemelidir
- vision verisi yardimci ve pasif katman olarak ele alinmalidir
- workbook sheet yapisi entegrasyon siniri oldugu icin keyfi degistirilmemelidir

## AI'nin Yapmamasi Gerekenler

- MQTT root'unu degistirmek
- Mega tarafina keyfi yeni komut eklemek
- yerel Node-RED arsivini yeni ana ekran gibi ele almak
- workbook'u gecici bir CSV turevi gibi yorumlamak
- OEE hesabini aktif vardiya disinda baslatmak

## Faydali Prompt Ornekleri

- "`mes_web` icinde yeni kiosk davranisi ekle, mevcut dashboard snapshot kontratini bozma."
- "Workbook sheet yapisini koruyarak yeni alanlari projector tarafinda doldur."
- "OEE hesabini `PICKPLACE_DONE`, maintenance ve fault olaylarina gore backend tarafinda guncelle."
- "Yerel Node-RED arsivini sadece parity referansi olarak kullan."

## Yanlis Prompt Ornekleri

- "Node-RED yeni ana ekran olsun."
- "CSV uretelim, sonra belki Excel'e doneriz."
- "Vision karari Mega kararinin yerini alsin."
- "Vardiya acik olmasa da OEE sayimi baslasin."

## Dokuman Onceligi

Bir AI aracina repo baglami verilirken su belgeler once okunmalidir:

1. [README.md](README.md)
2. [architecture.md](architecture.md)
3. [data-model.md](data-model.md)
4. [mes_web/README.md](../mes_web/README.md)
5. [mqtt-topics.md](mqtt-topics.md)
