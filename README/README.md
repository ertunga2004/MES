# FERP_MES

FERP_MES, mini konveyor uzerinde calisan bir MES prototipidir. Bu repo; saha kontrolu, MQTT haberlesmesi, Node-RED akisi, CSV tabanli entegrasyon ciktilari ve Raspberry Pi tabanli vision observer bilesenlerini ayni yerde toplar.

## Projenin Amaci

- ERP ile uretim hatti arasinda izlenebilir veri akisi kurmak
- Uretim olaylarini kaydetmek ve FERP'ye aktarilabilir hale getirmek
- OEE ve operasyon takibi icin temel veri modelini netlestirmek
- Prototipi ileride saha ortamina tasinabilecek sekilde parcali gelistirmek

## Sistem Ozeti

1. `mega.cpp`, konveyor, robot kol, limit switch ve renk olcum akisini yonetir.
2. `esp32.cpp`, Mega tarafindan uretilen log ve durum satirlarini MQTT broker'a tasir.
3. `node-red.json`, dashboard, veri toplama ve akislari temsil eder.
4. `production_events.csv` ve `production_completed.csv`, FERP entegrasyonu icin gecici veri ciktilaridir.
5. `raspberry/` altindaki observer servisi vision tabanli sayim ve dogrulama yapar; ana sorting kararini override etmez.

## Repo Haritasi

- `mega.cpp`: Arduino Mega tarafindaki gercek zamanli kontrol, queue ve pick-place akisi
- `esp32.cpp`: Wi-Fi ve MQTT bridge
- `node-red.json`: Node-RED dashboard ve entegrasyon akisi
- `production_events.csv`: append-only olay kaydi
- `production_completed.csv`: tamamlanan urun kaydi
- `raspberry/`: vision observer, kalibrasyon araci ve ornek konfigurasyonlar

## Dokuman Haritasi

- `architecture.md`: sistem katmanlari ve veri akisinin tam resmi
- `hardware.md`: kartlar, motorlar, sensorler ve guc mimarisi
- `mqtt-topics.md`: topic yapisi, publisher/subscriber sorumluluklari
- `data-model.md`: aktif veri kaynaklari ve planlanan veri modeli
- `FERP_INTEGRATION.md`: CSV tabanli entegrasyon siniri ve alan eslemeleri
- `roadmap.md`: mevcut oncelikler ve ekip bazli is akislari
- `raspberry/README.md`: vision observer modulu
- `AI_GUIDE.md`: ekip icin yapay zeka kullanim rehberi

## Nereden Baslamali

- Saha kontrolu icin: `mega.cpp`, `esp32.cpp`, `mqtt-topics.md`
- Veri ve entegrasyon icin: `FERP_INTEGRATION.md`, `data-model.md`, CSV dosyalari
- Vision icin: `raspberry/README.md`, `raspberry/config/`
- Genel resmi anlamak icin: once `README.md`, sonra `architecture.md`

## AI ile Calisma Icin Kisa Kurallar

- MQTT root varsayilan olarak `sau/iot/mega/konveyor/` kabul edilmelidir.
- Vision topicleri `sau/iot/mega/konveyor/vision/...` altinda JSON yayini yapar.
- `production_events.csv` ve `production_completed.csv` kolonlari gereksiz yere yeniden adlandirilmamalidir.
- Hareket ve sorting karari icin ana otorite Mega tarafidir.
- Entegrasyon kontrati kesinlesene kadar CSV dosyalari tek dogruluk kaynagi gibi ele alinmalidir.

Detayli kullanim icin `AI_GUIDE.md` dosyasina bakin.
