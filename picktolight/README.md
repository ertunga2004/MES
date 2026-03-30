# Pick To Light Assembly

Bu klasor, 4 kutulu bir pick-to-light montaj istasyonu icin Python tabanli masaustu arayuzu ile Nokia 5110 ekran kullanan ESP32 istemcisini birlikte icerir.

## Mimari

- Python GUI, sistemin ana durum yoneticisidir.
- Tum urun receteleri, kutu stoklari ve ERP anlik gorunumu JSON dosyalarinda tutulur.
- Python uygulamasi MQTT uzerinden iki ana cikti uretir:
  - tam istasyon durumu: `sau/iot/mega/konveyor/picktolight/station/state`
  - Nokia 5110 icin sade 6 satirlik ekran verisi: `sau/iot/mega/konveyor/picktolight/station/display`
- ESP32 ekrani sadece `display` topic'ini dinler.
- Fiziksel buton varsa ESP32 `.../station/button` topic'ine `press` gonderir.
- Fiziksel buton yoksa Python GUI icindeki buyuk turuncu buton ayni gorevi gorur.

## MQTT Topicleri

- `sau/iot/mega/konveyor/picktolight/station/state`
  - retained JSON
  - Python GUI -> diger istemciler
- `sau/iot/mega/konveyor/picktolight/station/display`
  - retained text
  - Python GUI -> ESP32 ekran
  - format: `satir1~satir2~satir3~satir4~satir5~satir6`
- `sau/iot/mega/konveyor/picktolight/station/button`
  - text payload: `press`
  - ESP32 butonu -> Python GUI
- `sau/iot/mega/konveyor/picktolight/station/event`
  - non-retained JSON
  - parca alma, montaj onayi, urun tamamlama, stok degisimi olaylari
- `sau/iot/mega/konveyor/picktolight/station/python_status`
  - retained JSON
- `sau/iot/mega/konveyor/picktolight/station/esp32_status`
  - retained JSON
- `sau/iot/mega/konveyor/picktolight/station/heartbeat`
  - non-retained JSON

## Dosya Yapisi

- `app.py`: Python GUI giris noktasi
- `picktolight/station.py`: durum makinesi, stok dusumu, urun akisi, JSON export
- `picktolight/gui.py`: Tkinter tabanli operator ve stok arayuzu
- `picktolight/mqtt_service.py`: MQTT baglanti ve topic yayinlari
- `data/products.json`: urun receteleri ve montaj siralari
- `data/inventory.json`: kutu bazli stoklar
- `data/station_state.json`: aktif urun ve anlik asama
- `data/erp_snapshot.json`: ERP tarafina uygun tekil JSON gorunumu
- `logs/assembly_events.jsonl`: olay kaydi
- `esp32/picktolight_nokia5110/platformio.ini`: PlatformIO proje ayarlari
- `esp32/picktolight_nokia5110/src/main.cpp`: ESP32 ekran ve buton kodu
- `docs/wiring.md`: baglanti semasi

## Kurulum

1. Python bagimliligini yukle:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES\picktolight
python -m pip install -r requirements.txt
```

2. Python arayuzunu baslat:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES\picktolight
python app.py
```

3. PlatformIO ile ESP32 kodunu derleyip yukle:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES\picktolight\esp32\picktolight_nokia5110
pio run
pio run -t upload
```

4. `src/main.cpp` icindeki `ssid` ve `password` alanlarini kendi Wi-Fi bilgine gore duzenle.

## Is Akisi

1. GUI icinden urunu sec.
2. Gerekirse kutu stoklarini guncelle.
3. Istasyondaki operator parca aldiginda tek butona basar.
4. Sistem stoktan dusum yapar ve ekrani `montaj yap` moduna alir.
5. Montaj tamamlaninca ayni butona tekrar basilir.
6. Son adimdan sonra ekranda `URUN TAMAM` gorunur.
7. Bir sonraki tiklama yeni urunu baslatir.

## JSON Tarafi

- Recete sirasi ve adetleri `data/products.json` icinde tanimlidir.
- Hangi kutuda hangi parcanin kac adet oldugu `data/inventory.json` icinde tutulur.
- ERP'nin tek dosyadan cekebilmesi icin guncel toplu gorunum `data/erp_snapshot.json` dosyasina her islemde yeniden yazilir.

## Gecici Buton Cozumu

Breadboard olmadigi icin iki yol hazir:

- Hemen kullanmak icin Python arayuzundeki buyuk turuncu `Istasyon Butonu`.
- Fiziksel buton eklemek istersen bir adet anlik push button'un bir ucunu `GPIO25`, diger ucunu `GND`'ye bagla. Kod `INPUT_PULLUP` kullandigi icin harici direnc gerekmez.

## Onemli Notlar

- Nokia 5110 ve ESP32 baglantisinda sadece `3V3` kullan.
- `BL` pinini modulde seri direnc oldugundan eminsen bagla; emin degilsen bos birak.
- Box 4 altinda iki farkli parca tutuldugu icin stok modeli kutu + parca kombinasyonu uzerinden tasarlandi.
