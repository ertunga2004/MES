# Roadmap

## Mevcut Faz

Proje, Node-RED'den kademeli ayrisma fazindadir. Yeni calisan katman `mes_web/` altinda bulunur. Fiziksel hat, MQTT bridge ve legacy akislar yerel arsivde korunurken yeni web ekran, operator kiosk, teknisyen kiosk, OEE runtime ve workbook kaydi paralel olarak olgunlastirilmaktadir.

## Tamamlanan Ana Isler

- FastAPI + WebSocket tabanli canli dashboard kuruldu.
- REST bootstrap ve reconnect eden WebSocket modeli devreye alindi.
- MQTT ingest ve normalize dashboard snapshot yapisi olusturuldu.
- operator kiosk route'u ve cihaz bazli registry eklendi.
- teknisyen cagri ekrani, `acknowledge/resolve` akisi ve bugun/son 10 gecmis panelleri eklendi.
- kalite override dashboard ve kiosk tarafinda devreye alindi.
- `good -> rework / scrap` duzeltmesi OEE ve workbook'a baglandi.
- hurda urunlerin depoya dusmemesi kural olarak uygulandi.
- komut paneli `cmd` topic'ine baglandi.
- `__reset_counts__` komutu backend icinde yerel hale getirildi.
- gunluk workbook yazimi template uzerinden `logs/` altina tasindi.
- OEE vardiya kontrolu, hedef/cycle/planned stop ayarlari ve runtime state backend'e alindi.
- OEE sure alanlari ms-first olacak sekilde toplandi.
- maintenance ve fault sure siniflandirmasi availability hesabina uygun hale getirildi.
- `MES Web.cmd`, dashboard, operator kiosk ve teknisyen ekranini server hazir olunca otomatik acacak hale getirildi.

## Kisa Vade

- teknisyen cagri ekranini saha akisi ile dogrulamak
- help request surelerini workbook ve operasyon raporlarinda sahada kontrol etmek
- workbook replay / rebuild araci eklemek
- OEE ekraninda fault, hedef gap ve vardiya ozetini saha testi ile parity etmek
- launcher tarafinda interpreter / dependency tanisini daha otomatik hale getirmek

## Orta Vade

- FERP icin resmi JSON kontratini netlestirmek
- workbook -> FERP JSON donusum katmani eklemek
- operasyon ve OEE ekranlarina rapor/export ihtiyaclarini eklemek
- modul bazli genisleme ile `picktolight` benzeri ikinci istasyonlari ayni omurgaya almak
- gerekirse yerel broker veya kampus-agi uyumlu MQTT seceneklerini eklemek

## Uzun Vade

- yerel Node-RED operator ekranini emekli etmek
- Node-RED bagimliligini sadece arastirma / arsiv seviyesine dusurmek
- workbook yanina kurumsal veritabani veya resmi raporlama katmani eklemek
- FERP ile cift yonlu is emri ve geri bildirim entegrasyonuna gecmek

## Acik Kararlar

- FERP tarafinda ana import nesnesi workbook mu olacak yoksa workbook'tan turetilen JSON mu
- aktif/arsiv workbook yonetimi gunluk dosya bazli mi yoksa aylik paket bazli mi ilerleyecek
- pick-to-light modulu mevcut `mes_web` omurgasina ne zaman alinacak
- kiosk auth / PIN katmani ne zaman zorunlu hale getirilecek

## Ekip Bazli Odaklar

### Hat ve Kontrol

- `mega.cpp`
- `esp32.cpp`
- fiziksel akis ve MQTT bridge

### Web ve OEE

- `mes_web/`
- OEE runtime
- dashboard, operator kiosk ve teknisyen ekranlari
- workbook yazimi

### Vision

- `raspberry/`
- capraz kontrol ve saha kalibrasyonu

### Entegrasyon

- workbook alanlari
- FERP JSON siniri
- veri dogrulama ve reconciliation kurallari
