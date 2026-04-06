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

Raspberry Pi icin onerilen yol:

```bash
cd raspberry
sudo apt update
sudo apt install -y python3-opencv python3-numpy
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Not:
- Pi uzerinde `opencv-python` wheel'i pip ile hata verebilir; bu yuzden OpenCV sistem paketinden alinacak sekilde ayarlandi.
- Eger `.venv` dosyasini daha once normal sekilde olusturduysan silip yeniden `--system-site-packages` ile olustur.

PC / x86 gelistirme ortami icin:

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

Pencere buyuk geliyorsa `config/observer.example.json` icinde `ui.preview_scale` degeri kullanilabilir.
Ornek:

```json
"ui": {
  "show_windows": true,
  "show_masks": false,
  "preview_scale": 0.5
}
```

`0.5` yarim boyut, `0.75` daha kucuk, `1.0` orijinal boyuttur.

GUI'de sadece kameranin gordugu ham görüntü isteniyorsa:

```json
"ui": {
  "show_windows": true,
  "show_masks": false,
  "preview_scale": 0.5,
  "show_overlay": false
}
```

SSH uzerinden gecici override icin:

```bash
DISPLAY=:0 python run_observer.py --config config/observer.pi.json --boxes config/boxes.pi.json --preview-scale 0.5 --raw-preview
```

Kamera parametreleri de SSH uzerinden override edilebilir:

```bash
DISPLAY=:0 python run_observer.py --config config/observer.pi.json --boxes config/boxes.pi.json --width 640 --height 480 --fps 10 --preview-scale 0.5 --raw-preview
```

Kamera 90 derece yan donuksa saat yonunun tersine cevirmek icin:

```bash
DISPLAY=:0 python run_observer.py --config config/observer.pi.json --boxes config/boxes.pi.json --rotate-ccw-90
```

Kalici config icin:

```json
"camera": {
  "source": 0,
  "width": 640,
  "height": 480,
  "fps": 10,
  "flip_horizontal": true,
  "rotate_ccw_90": true
}
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
