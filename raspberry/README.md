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
  - genel observer config
- `config/observer.pi.example.json`
  - Raspberry Pi icin optimize ornek config
- `config/observer.pi.legacy.example.json`
  - Python 3.7 / legacy stack icin ornek config
- `config/boxes.example.json`
  - kutu profilleri
- `observer/`
  - detection, tracking, preprocessing, capture ve mqtt modulleri
- `scripts/`
  - GUI / headless baslatma, durdurma ve opsiyonel saat ayarlama yardimcilari
- `desktop/`
  - Raspberry Pi desktop icin tiklanabilir `.desktop` launcher dosyalari
- `tools/publish_time_sync.ps1`
  - Windows tarafindan mevcut saati MQTT ile gonderme yardimcisi
- `systemd/mes-observer.service.example`
  - servis olarak calistirma sablonu

## MQTT Yayinlari

Varsayilan root:

`sau/iot/mega/konveyor/vision`

Topicler:

- `status`
- `heartbeat`
- `tracks`
- `events`
- `clock_status`

Tipik event tipleri:

- `box_confirmed`
- `box_lost`
- `line_crossed`

Payload tipi JSON'dir.

Not:

- `line_crossed`, artik kutu merkezine gore degil hareket yonundeki on kenarin `line_x` cizgisine degmesiyle uretilir.
- Observer, MQTT uzerinden proses-ici saat offset'i de alabilir.

Saat senkronizasyon topic'i:

- `time_sync`

Ornek:

```bash
mosquitto_pub -h broker.emqx.io -p 1883 -t 'sau/iot/mega/konveyor/vision/time_sync' -m '{"timestamp":"2026-04-09T14:30:00+03:00"}'
```

Bu islem Pi sistem saatini degistirmez; observer'in yayinladigi `timestamp`, `observed_at` ve `published_at` alanlarini MQTT uzerinden verilen zamana hizalar.

Pi sistem saatini de guncellemek istersen payload'a `set_system_clock` ekle:

```bash
mosquitto_pub -h broker.emqx.io -p 1883 -t 'sau/iot/mega/konveyor/vision/time_sync' -m '{"timestamp":"2026-04-09T14:30:00+03:00","set_system_clock":true}'
```

Bu mod icin:

1. `scripts/set_system_time.sh` dosyasini calisabilir yap
2. `systemd/mes-observer-time-sync.sudoers.example` icerigini `visudo` ile kur
3. observer'i `MES_OBSERVER_SET_CLOCK_CMD=/usr/bin/sudo -n /home/pi/Documents/vision/scripts/set_system_time.sh` ortam degiskeni ile baslat

Windows tarafindan mevcut saati otomatik publish etmek icin:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\publish_time_sync.ps1
```

Pi sistem saatini de ayarlatmak icin:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\publish_time_sync.ps1 -ApplySystemClock
```

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

CSI kamera modulu kullaniyorsan ek olarak:

```bash
sudo apt install -y python3-picamera2
```

Not:

- `python3-picamera2` paketi Python 3.7 tabanli eski Raspberry Pi OS kurulumlarinda bulunmaz.
- Traceback icinde `/usr/lib/python3.7/...` goruyorsan buyuk ihtimalle Buster veya legacy image kullaniyorsun.
- Bu durumda Picamera2 yerine `source=0` ile OpenCV / V4L2 yolu kullanilmalidir.

- Pi uzerinde `opencv-python` wheel'i pip ile hata verebilir; bu yuzden OpenCV sistem paketinden alinacak sekilde ayarlandi.
- Eger `.venv` dosyasini daha once normal sekilde olusturduysan silip yeniden `--system-site-packages` ile olustur.

PC / x86 gelistirme ortami icin:

```bash
cd raspberry
python -m pip install -r requirements.txt
```

## Uzaktan Erisim

Minimum temas icin onerilen akis:

1. `SSH` ile terminal erisimi
2. `RealVNC` ile GUI gerektiginde masaustu erisimi
3. observer'i `systemd` servisi olarak arka planda calistirma

Raspberry Pi tarafinda ilk ayarlar:

```bash
sudo raspi-config nonint do_ssh 0
sudo raspi-config nonint do_vnc 0
sudo raspi-config nonint do_vnc_resolution 1280x720
```

Raspberry Pi OS'in guncel surumlerinde RealVNC icin `X11` moduna gecmek gerekebilir:

1. `sudo raspi-config`
2. `Advanced Options`
3. `Wayland`
4. `X11`
5. reboot

VNC servisini kalici ac:

```bash
sudo apt install -y realvnc-vnc-server
sudo systemctl enable vncserver-x11-serviced --now
```

Pi monitorsuz calisacaksa ve RealVNC lisansin virtual mode destekliyorsa sanal desktop acmak icin:

```bash
vncserver-virtual -RandR=1280x720
```

Kapatmak icin:

```bash
vncserver-virtual -kill :1
```

Viewer tarafinda baglanti hedefi:

- normal desktop icin `pi-ip-adresi`
- virtual desktop icin `pi-ip-adresi:1`

Servis sablonu:

- `systemd/mes-observer.service.example`

## Calistirma

GUI ile:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json
```

Kolay kullanim icin launcher scriptleri:

```bash
./scripts/start_observer_gui.sh
./scripts/start_observer_headless.sh
./scripts/stop_observer.sh
```

Raspberry Pi OS masaustunde Windows'taki `.exe` yerine `.desktop` kullanilir. Hazir dosyalar:

- `desktop/Observer GUI.desktop`
- `desktop/Observer Headless.desktop`
- `desktop/Observer Stop.desktop`

Tipik kurulum:

```bash
chmod +x scripts/*.sh
cp desktop/*.desktop ~/Desktop/
chmod +x ~/Desktop/*.desktop
```

GUI acikken yeni canli ayar kisayollari:

- fare ile ROI alanini ciz / tasi / saga-alt koseden yeniden boyutlandir
- sari cizgiyi fare ile saga-sola surukle
- `t`: kamerayi 90 derece saat yonunun tersine cevir
- `s`: o anki ROI, cizgi ve rotate ayarlarini config dosyasina kaydet
- `r`: `boxes` profil dosyasini yeniden yukle
- `m`: mask penceresini ac / kapa
- `1-9`: secili profil maskesine odaklan
- `0`: maske odagini temizle
- `q`: cikis

Picamera2 backend icin `camera.source` alanina `"picamera2"` yaz. USB kamera kullaniyorsan `0` veya ilgili cihaz yolu ile devam et.

Python 3.7 / legacy kamera stack kullaniyorsan:

```json
"camera": {
  "source": 0
}
```

Bu modda gerekirse:

```bash
sudo modprobe bcm2835-v4l2
```

Kalici yapmak icin:

```bash
echo bcm2835-v4l2 | sudo tee -a /etc/modules
```

Pencere buyuk geliyorsa `ui.preview_scale` degeri kullanilabilir.

Ornek:

```json
"ui": {
  "show_windows": true,
  "show_masks": false,
  "preview_scale": 0.5
}
```

Sadece ham goruntu isteniyorsa:

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
DISPLAY=:0 python run_observer.py --config config/observer.pi.example.json --boxes config/boxes.example.json --preview-scale 0.5 --raw-preview
```

Kamera parametreleri de SSH uzerinden override edilebilir:

```bash
DISPLAY=:0 python run_observer.py --config config/observer.pi.example.json --boxes config/boxes.example.json --width 640 --height 480 --fps 10 --preview-scale 0.5 --raw-preview
```

Kamera 90 derece yan donuksa:

```bash
DISPLAY=:0 python run_observer.py --config config/observer.pi.example.json --boxes config/boxes.example.json --rotate-ccw-90
```

Kalici config icin:

```json
"camera": {
  "source": "picamera2",
  "width": 640,
  "height": 480,
  "fps": 15,
  "flip_horizontal": true,
  "rotate_ccw_90": false
}
```

GUI olmadan:

```bash
cd raspberry
python run_observer.py --config config/observer.pi.example.json --boxes config/boxes.example.json --no-gui
```

Video kaynagi ile:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --source sample.mp4
```

## Kalibrasyon Akisi

1. `calibrate_hsv.py` ile hedef kutu icin profil cikar.
2. Kutuyu merkez ROI icinde konumlandir veya goruntu uzerinden tiklayarak ornek topla.
3. HSV / LAB araliklarini dene.
4. Uretilen profili `boxes.example.json` mantigina tasi.
5. Sahada isik ve kamera acisi degisince tekrar kontrol et.

Yeni kalibrasyon iyilestirmeleri:

- merkez ROI'den otomatik HSV/LAB profil uretimi
- goruntu uzerine tiklayarak birden fazla renk ornegi toplama
- tiklama orneklerinden otomatik profil uretme
- otomatik profili dogrudan `boxes` dosyasina yazma
- isik degisimi icin opsiyonel `gray-world` ve `CLAHE` on-isleme

Ornek:

```bash
python calibrate_hsv.py --source picamera2 --width 640 --height 480 --preview-scale 0.7 --normalize-lighting --clahe-clip-limit 2.2
```

Tuslar:

- sol tik: renk ornegi ekle
- `p`: tiklama orneklerinden profil yazdir
- `w`: son otomatik profili boxes dosyasina kaydet
- `x`: tiklama orneklerini temizle
- `c`: merkez ROI'den otomatik profil cikar
- `r/y/b`: manual HSV araligini kaydet
- `R/Y/B`: mevcut renge ek bir HSV araligi ekle

## Saha Notlari

- sari gibi zor renkler isik degisiminden daha cok etkilenir
- Pi 3 gibi cihazlarda ROI dar tutulursa performans daha stabil olur
- track kaybi, item kimligi kaybi ile ayni sey degildir
- dusuk isik veya parlama varsa `processing.normalize_lighting`, `processing.clahe_clip_limit`, `processing.min_saturation`, `processing.min_value` alanlarini birlikte ayarla
- CSI kamera modulu kullaniyorsan `source=picamera2`, USB kamera kullaniyorsan `source=0` daha temiz sonuc verir

## Bu Modulu Degistirirken

- [README/mqtt-topics.md](/Users/acer/Documents/.CODE/codex/MES/README/mqtt-topics.md) ile topic uyumunu koru
- ana karar zincirini vision'a tasimaya calisma
- event isimlerini degistirirsen `mes_web/parsers.py` ve ilgili UI etkilerini birlikte dusun
