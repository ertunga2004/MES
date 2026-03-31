# Pick To Light Assembly

Bu klasor, 4 kutulu bir pick-to-light montaj istasyonu icin Python tabanli masaustu arayuzu ile Nokia 5110 ekran kullanan ESP32 istemcisini birlikte icerir. Sistem artik operator secimi, operasyon bazli akis, sure takibi ve performans gorunumu de destekler.

## Mimari

- Python GUI, sistemin ana durum yoneticisidir.
- Tum urun receteleri, operator listesi, kutu stoklari ve ERP anlik gorunumu JSON dosyalarinda tutulur.
- Her montaj adimi bir veya daha fazla operasyondan olusabilir. Ornek: `Tornavida al -> Vida al -> Montaj yap`.
- Python uygulamasi MQTT uzerinden iki ana cikti uretir:
  - tam istasyon durumu: `sau/iot/mega/konveyor/picktolight/station/state`
  - Nokia 5110 icin sade 6 satirlik ekran verisi: `sau/iot/mega/konveyor/picktolight/station/display`
- ESP32 ekrani sadece `display` topic'ini dinler.
- Fiziksel buton varsa ESP32 `.../station/button` topic'ine `press` gonderir.
- Reset ve geri al icin MQTT `.../station/command` topic'i `reset` ve `undo` komutlarini kabul eder.
- Fiziksel buton yoksa Python GUI icindeki buyuk turuncu buton ayni gorevi gorur.
- Her buton gecisinde operasyon suresi kaydedilir ve performans ekraninda operator bazli ozetlenir.

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
- `sau/iot/mega/konveyor/picktolight/station/command`
  - text veya JSON payload
  - ornek: `reset`, `undo`, `{"action":"reset"}`, `{"action":"undo"}`
  - reset ve geri al komutlari icin kullanilir
- `sau/iot/mega/konveyor/picktolight/station/event`
  - non-retained JSON
  - operasyon tamamlama, operator degisimi, stok degisimi ve reset olaylari
- `sau/iot/mega/konveyor/picktolight/station/python_status`
  - retained JSON
- `sau/iot/mega/konveyor/picktolight/station/esp32_status`
  - retained JSON
- `sau/iot/mega/konveyor/picktolight/station/heartbeat`
  - non-retained JSON

## Dosya Yapisi

- `app.py`: Python GUI giris noktasi
- `picktolight/station.py`: operator secimi, operasyon akisi, stok dusumu, sure takibi ve JSON export
- `picktolight/gui.py`: Tkinter tabanli operator, performans ve stok arayuzu
- `picktolight/mqtt_service.py`: MQTT baglanti ve topic yayinlari
- `data/products.json`: urun receteleri ve montaj siralari
- `data/operators.json`: operator listesi
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

1. GUI icinden urunu ve operatoru sec.
2. Gerekirse kutu stoklarini guncelle.
3. Gerekirse montaj sirasindan secili adimin kutusunu GUI uzerinden degistir.
4. Istasyondaki operator aktif operasyona gore tek butona basarak ilerler.
5. Standart adimlarda akis `Parcayi al -> Montaj yap` seklindedir.
6. Ozel adimlarda akis `Tornavida al -> Vida al -> Montaj yap` gibi birden fazla operasyondan olusabilir.
7. Her geciste sure tutulur ve performans ekraninda operator bazli goruntulenir.
8. Son adimdan sonra ekranda `URUN TAMAM` gorunur.
9. Bir sonraki tiklama yeni urunu baslatir.
10. Reset gerekiyorsa GUI'deki `Isi Resetle` butonunu kullan veya fiziksel butona 3 saniye basili tut.
11. Fiziksel butona hizli art arda iki kez basmak son operasyonu geri alir.

## JSON Tarafi

- Recete sirasi, adetler ve operasyon dizileri `data/products.json` icinde tanimlidir.
- Operator listesi `data/operators.json` icinde tutulur.
- Hangi kutuda hangi parcanin kac adet oldugu `data/inventory.json` icinde tutulur.
- ERP'nin tek dosyadan cekebilmesi icin guncel toplu gorunum `data/erp_snapshot.json` dosyasina her islemde yeniden yazilir.
- Sure ve olay kayitlari `logs/assembly_events.jsonl` icinde JSONL formatinda tutulur.

## Gecici Buton Cozumu

Breadboard olmadigi icin iki yol hazir:

- Hemen kullanmak icin Python arayuzundeki buyuk turuncu `Istasyon Butonu`.
- Fiziksel buton eklemek istersen bir adet anlik push button'un bir ucunu `GPIO25`, diger ucunu `GND`'ye bagla. Kod `INPUT_PULLUP` kullandigi icin harici direnc gerekmez.
- Fiziksel butonda tek kisa basma `ilerlet`, hizli cift basma `geri al`, 3 saniye uzun basma `reset` komutu yollar.

## Onemli Notlar

- Nokia 5110 ve ESP32 baglantisinda sadece `3V3` kullan.
- `BL` pinini modulde seri direnc oldugundan eminsen bagla; emin degilsen bos birak.
- Kutu modeli `kutu + parca` kombinasyonu uzerinden calisir; ayni kutuda birden fazla farkli parca tutulabilir.
- `Enter` ve `Space`, yalnizca bir yazi giris alani secili degilse istasyon butonu gibi calisir.
- Ornek operator destekli aletli urun olarak `Lego Vidali Vagon` eklenmistir.
