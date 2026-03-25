# Raspberry Observer

## Amac

`raspberry/` klasoru, konveyor uzerindeki kutulari goruntu ile gozlemleyen pasif observer servisini icerir. Bu servis ana sorting kararini degistirmez; sayim, dogrulama ve sapma takibi icin ek veri uretir.

## Dosya Haritasi

- `run_observer.py`: uygulamanin ana giris noktasi
- `calibrate_hsv.py`: HSV ve LAB profil cikarimi icin yardimci arac
- `kamera.py`: tek dosyalik eski HSV denemesi
- `config/observer.example.json`: kamera, ROI, tracker ve MQTT ayarlari
- `config/boxes.example.json`: kutu profilleri ve renk araliklari
- `observer/`: algilama, takip, MQTT ve uygulama modulleri

## Ne Yapar

- JSON ile kutu profilleri tanimlar
- HSV maske ve istege bagli LAB kisiti ile kutu tespiti yapar
- Track bazli izleme ile ayni kutuya tutarli `track_id` atar
- Dikey sayim cizgisi gecislerini sayar
- MQTT uzerinden durum, heartbeat, track ve event yayini yapar

## MQTT Yayinlari

Varsayilan root:

`sau/iot/mega/konveyor/vision`

Topicler:

- `status`
- `heartbeat`
- `tracks`
- `events`

Tipik `events` olaylari:

- `box_confirmed`
- `box_lost`
- `line_crossed`

Bu yayinlar JSON formatindadir.

## Kurulum

`raspberry/` klasorunde:

```bash
python -m pip install -r requirements.txt
```

## Ilk Calistirma

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json
```

GUI olmadan:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --no-gui
```

Video dosyasi ile test:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --source sample.mp4
```

## Kalibrasyon Akisi

1. `python calibrate_hsv.py --source 0 --profile-id red_box --label "Red Box" --color-name red --overlay-bgr 0,0,255` ile araci acin.
2. Kutuyu merkez ROI icine getirin.
3. `c` ile profil cikartin.
4. Gerekirse trackbar ile deneme yapip `s` ile HSV araligini alin.
5. Uretilen JSON parcasini `config/boxes.example.json` icine tasiyin.
6. `min_area`, `max_area` ve `aspect_ratio` alanlarini sahaya gore ince ayarlayin.

## Dikkat Edilecek Sinirlar

- Observer pasif calisir; Mega kararini override etmez.
- Track kimligi `item_id` yerine gecmez.
- Isik kosulu degistiginde sari ve benzeri renkler tekrar kalibre edilmelidir.
- Pi 3 gibi sinirli cihazlarda ROI'yi dar tutmak ve cozunurlugu dusurmek daha stabildir.

## AI Icin Notlar

- Vision ile ilgili bir gorev verirken mutlaka `config/observer.example.json` ve `config/boxes.example.json` da paylasilmalidir.
- "Tespiti iyilestir" gibi genel ifadeler yerine hangi renk, hangi isik kosulu ve hangi hata tipi oldugu yazilmalidir.
- MQTT topic veya event degisikligi oneriliyorsa `mqtt-topics.md` ile uyum kontrol edilmelidir.
