# Raspberry observer yapisi

`kamera.py` dosyasi mevcut tek dosyalik HSV denemesi olarak kalabilir. Bunun yanina, masaustunde test edilip daha sonra Raspberry Pi 3 uzerine alinabilecek ayri bir gozlemci yapisi eklendi.

## Dosya yapisi

- `run_observer.py`: ana giris noktasi
- `calibrate_hsv.py`: HSV ve LAB profili cikarmak icin yardimci arac
- `config/observer.example.json`: kamera, ROI, tracker, MQTT ayarlari
- `config/boxes.example.json`: tanimlanacak kutu profilleri ve HSV araliklari
- `observer/`: algilama, takip, MQTT ve uygulama modulleri

## Ne yapiyor

- Kutulari JSON ile tanimlamanizi saglar.
- Her kutu profili icin HSV maske uretir, istenirse LAB ile daraltir.
- Kontur alanina gore aday kutulari bulur.
- Overlap bastirma ile ayni kutunun iki renk olarak sayilmasini azaltir.
- Hareket toleransli tracker ile ayni kutuya sabit `track_id` verir.
- Istenirse bir dikey sayim cizgisini gecen kutulari sayar.
- MQTT uzerinden `status`, `heartbeat`, `tracks` ve `events` yayinlar.
- Ilk demo asamasinda yalnizca pasif gozlemci olarak calisir; sorting kararini etkilemez.

Varsayilan MQTT root topic:

- `sau/iot/mega/konveyor/vision/status`
- `sau/iot/mega/konveyor/vision/heartbeat`
- `sau/iot/mega/konveyor/vision/tracks`
- `sau/iot/mega/konveyor/vision/events`

Bu secim mevcut projedeki `sau/iot/mega/konveyor/...` yapisiyla uyumlu ama mevcut `status/logs/cmd` topicleriyle cakismayacak sekilde yapildi.

## Kurulum

`raspberry` klasorunde:

```bash
python -m pip install -r requirements.txt
```

## Ilk calistirma

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json
```

GUI istemiyorsaniz:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --no-gui
```

Varsayilan `observer.example.json` MQTT acik gelir. Demo akisinda bu servis yalnizca `vision/...` topiclerine yayin yapar.

Video dosyasi ile denemek icin:

```bash
cd raspberry
python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --source sample.mp4
```

## Kutu tanitma akisi

1. `python calibrate_hsv.py --source 0 --profile-id red_box --label "Red Box" --color-name red --overlay-bgr 0,0,255` ile araci acin.
2. Kutuyu ekrandaki sari merkez ROI'nin icine getirin.
3. `c` tusuna basin. Arac size dogrudan profile uygun `ranges` ve `lab_ranges` JSON'u uretecek.
4. Gerekirse trackbar ile manuel HSV denemesi yapip `s` ile anlik HSV araligini alin.
5. Uretilen JSON'u `config/boxes.example.json` icinde ilgili profile koyun.
6. Gerekirse `min_area`, `max_area` ve `aspect_ratio` degerlerini ayarlayin.

Bu projedeki mevcut renk seti:

- `red_box`
- `yellow_box`
- `blue_box`

## Saha notlari

- Sari kutu icin en az iki farkli isik kosulunda kalibrasyon alin ve profili sahada tekrar dogrulayin.
- Demo suresince vision verisi Mega kararini override etmez; Node-RED tarafinda sadece sayim ve sapma karsilastirmasi icin kullanilir.
- `line_crossed` olaylari, Mega `QUEUE=ENQ` sayaclariyla karsilastirilacak ana vision olayi olarak kabul edilir.

## Notlar

- Su anki siniflandirma renk + alan + oran tabanlidir. Ayni renkte farkli kutular varsa ek ozellik gerekir.
- `priority` alani, ayni nesne birden fazla profile takildiginda hangi rengin kazanacagini belirler.
- `tracker.min_confirmed_frames`, yeni bir kutunun kac frame gorulmeden gercek kutu sayilmayacagini belirler.
- `tracker.expected_direction`, konveyor yonunun tersine giden yalanci eslesmeleri azaltir.
- Pi 3 uzerinde daha stabil calisma icin ROI'yi dar tutun ve cozunurlugu dusurun.
- Raspberry tarafinda masaustu gosterimi gerekmiyorsa `--no-gui` ile calistirin.
