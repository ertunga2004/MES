# Raspberry Observer

`raspberry/`, konveyor hattina yardimci pasif vision observer katmanidir. Amaci ana sorting kararini degistirmek degil, goruntu tabanli izleme ve capraz kontrol verisi uretmektir.

## Rol

- kutu tespiti
- track atama
- line crossing sayimi
- renk ve sayim capraz kontrolu
- operator ekranina ozet veri saglama

Yeni yapida bu veri `mes_web` tarafinda pasif ingest olarak okunur ve operasyon ekraninda vision ozeti olarak gosterilebilir.

## Ne Yapmaz

- Mega'nin sorting kararini override etmez
- `item_id` otoritesi gibi davranmaz
- OEE tamamlanma sayimini dogrudan belirlemez

## Dosya Haritasi

- `run_observer.py`
  - ana giris noktasi
- `calibrate_hsv.py`
  - saha kalibrasyon araci
- `config/observer.example.json`
  - kamera, ROI, tracker ve MQTT ayarlari
- `config/boxes.example.json`
  - kutu profilleri
- `observer/`
  - detection, tracking, mqtt ve uygulama modulleri

## MQTT Yayinlari

Varsayilan root:

`sau/iot/mega/konveyor/vision`

Topicler:

- `status`
- `heartbeat`
- `tracks`
- `events`

Tipik event tipleri:

- `box_confirmed`
- `box_lost`
- `line_crossed`

Payload tipi JSON'dir.

## Kurulum

```bash
cd raspberry
python -m pip install -r requirements.txt
```

## Calistirma

GUI ile:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json
```

GUI olmadan:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --no-gui
```

Video kaynagi ile:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --source sample.mp4
```

## Kalibrasyon Akisi

1. `calibrate_hsv.py` ile hedef kutu icin profil cikar.
2. Kutuyu merkez ROI icinde konumlandir.
3. HSV / LAB araliklarini dene.
4. Uretilen profili `boxes.example.json` mantigina tası.
5. Sahada isik ve kamera acisi degisince tekrar kontrol et.

## Saha Notlari

- sari gibi zor renkler isik degisiminden daha cok etkilenir
- Pi 3 gibi cihazlarda ROI dar tutulursa performans daha stabil olur
- track kaybi, item kimligi kaybi ile ayni sey degildir

## Bu Modulu Degistirirken

- [README/mqtt-topics.md](/Users/acer/Documents/.CODE/codex/MES/README/mqtt-topics.md) ile topic uyumunu koru
- ana karar zincirini vision'a tasimaya calisma
- event isimlerini degistirirsen `mes_web/parsers.py` ve ilgili UI etkilerini birlikte dusun
