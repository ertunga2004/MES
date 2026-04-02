# Roadmap

## Mevcut Faz

Proje, Node-RED'den kademeli ayrisma fazindadir. Yeni calisan katman `mes_web/` altinda bulunur. Fiziksel hat, MQTT bridge ve legacy akislar yerel arsivde korunurken yeni web ekran, OEE runtime ve workbook kaydi paralel olarak olgunlastirilmaktadir.

## Tamamlanan Ana Isler

- FastAPI + WebSocket tabanli canli operator paneli kuruldu.
- REST bootstrap ve reconnect eden WebSocket modeli devreye alindi.
- MQTT ingest ve normalize dashboard snapshot yapisi olusturuldu.
- Vision verisi pasif ingest olarak backend'e alindi.
- Komut paneli `cmd` topic'ine baglandi.
- `__reset_counts__` komutu backend icinde yerel hale getirildi.
- Gunluk workbook yazimi template uzerinden `logs/` altina tasindi.
- OEE vardiya kontrolu, hedef/cycle/planned stop ayarlari ve runtime state backend'e alindi.
- `PICKPLACE_DONE` olayi tamamlanan urun ve varsayilan `good` kalite mantigina baglandi.

## Kisa Vade

- operator icin manuel kalite duzeltme ekrani eklemek
- `good -> rework / scrap` duzeltmesini OEE ve workbook'a yansitmak
- OEE ekraninda fault, hedef gap ve vardiya ozetini saha testi ile parity etmek
- workbook replay / rebuild araci eklemek
- yerel Node-RED arsivi ile alan bazli son parity kontrollerini tamamlamak

## Orta Vade

- FERP icin resmi JSON kontratini netlestirmek
- workbook -> FERP JSON donusum katmani eklemek
- operasyon ve OEE ekranlarina rapor/export ihtiyaclarini eklemek
- modul bazli genisleme ile `picktolight` benzeri ikinci istasyonlari ayni omurgaya almak

## Uzun Vade

- yerel Node-RED operator ekranini emekli etmek
- Node-RED bagimliligini sadece arastirma / arsiv seviyesine dusurmek
- workbook yanina kurumsal veritabani veya resmi raporlama katmani eklemek
- FERP ile cift yonlu is emri ve geri bildirim entegrasyonuna gecmek

## Acik Kararlar

- manuel kalite override ekraninin tam UI akisi nasil olacak
- FERP tarafinda ana import nesnesi workbook mu olacak yoksa workbook'tan turetilen JSON mu
- aktif/arsiv workbook yonetimi gunluk dosya bazli mi yoksa aylik paket bazli mi ilerleyecek
- pick-to-light modulu mevcut `mes_web` omurgasina ne zaman alinacak

## Ekip Bazli Odaklar

### Hat ve Kontrol

- `mega.cpp`
- `esp32.cpp`
- fiziksel akis ve MQTT bridge

### Web ve OEE

- `mes_web/`
- OEE runtime
- operator ekranlari
- workbook yazimi

### Vision

- `raspberry/`
- capraz kontrol ve saha kalibrasyonu

### Entegrasyon

- workbook alanlari
- FERP JSON siniri
- veri dogrulama ve reconciliation kurallari
