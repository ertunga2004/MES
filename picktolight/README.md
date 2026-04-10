# Pick To Light Assembly

`picktolight/`, ana konveyor hattindan ayri bir pick-to-light montaj istasyonu modulu icerir. Bu modul ayni repo icinde dursa da kendi Python GUI'si, MQTT topic agaci ve ESP32 ekran istemcisi ile calisir.

## Modulin Amaci

- operatora adim adim montaj akisi vermek
- istasyon butonu ile operasyon gecislerini yonetmek
- operasyon ve cevrim surelerini kaydetmek
- ERP veya ust sistem icin anlik JSON gorunumu saglamak

## Mimari

- Python GUI ana durum yoneticisidir.
- Receteler, operatorler ve stok durumu JSON dosyalarinda tutulur.
- Python uygulamasi MQTT ile istasyon state ve display yayini yapar.
- ESP32 + Nokia 5110 ekrani sadece sade display topic'ini dinler.
- Fiziksel buton varsa ESP32 bunu `button` topic'i ile Python GUI'ye tasir.

## MQTT Topic Agaci

Config root:

`sau/iot/mega/konveyor/picktolight`

Istasyon topic prefix'i:

`sau/iot/mega/konveyor/picktolight/station/`

Aktif topicler:

- `state`
- `display`
- `button`
- `command`
- `event`
- `python_status`
- `esp32_status`
- `heartbeat`

Bu agac ana konveyor MQTT topiclerinden mantiksal olarak ayridir.

## Dosya Yapisi

- `app.py`
  - GUI giris noktasi
- `picktolight/station.py`
  - operasyon mantigi ve istasyon state'i
- `picktolight/gui.py`
  - Tkinter arayuzu
- `picktolight/mqtt_service.py`
  - MQTT baglanti ve yayinlari
- `data/products.json`
  - urun receteleri
- `data/operators.json`
  - operator listesi
- `data/inventory.json`
  - kutu bazli stok
- `data/station_state.json`
  - aktif istasyon state'i
- `data/erp_snapshot.json`
  - ust sistem icin tekil anlik JSON
- `logs/assembly_events.jsonl`
  - olay kayitlari
- `docs/wiring.md`
  - ESP32 ve ekran baglantisi

## Kurulum

Python GUI:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES\picktolight
python -m pip install -r requirements.txt
python app.py
```

ESP32 tarafi:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES\picktolight\esp32\picktolight_nokia5110
pio run
pio run -t upload
```

## Is Akisi

1. Operator ve urun secilir.
2. Gerekirse stok ve kutu atamasi guncellenir.
3. Istasyon butonu ile operasyonlar sira sira ilerletilir.
4. Her geciste operasyon suresi kaydedilir.
5. Son adimdan sonra urun tamamlanir ve yeni urun akisi beklenir.

## Pratik Notlar

- Fiziksel buton yoksa GUI'deki buyuk istasyon butonu kullanilabilir.
- `Enter` ve `Space`, odak bir yazi alaninda degilse istasyon butonu gibi calisir.
- Uzun basma reset, cift basma geri alma olarak kullanilabilir.

## Ana Konveyor Ile Iliski

Bu modul su anda `mes_web` ana dashboard'una tasinmamis ayri bir istasyondur. Gelecekte ayni modul mimarisine alinabilir ama bugunku durumda kendi calisma alani olarak dusunulmelidir.
