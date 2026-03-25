# Hardware

## Kontrol Kartlari

- Arduino Mega 2560: ana kontrol katmani
- ESP32 DevKit: Wi-Fi ve MQTT baglantisi
- Raspberry Pi 3 veya benzeri: vision observer calisma ortami

## Hareket Bilesenleri

- DC motor: konveyor hareketi
- NEMA17 step motor: lineer veya eksen hareketi
- Servo motorlar:
  - MG996R
  - MG995
  - SG90 gripper

## Sensorler

- TCS3200: renk algilama
- 2 adet limit switch: alma ve birakma konumu

## Vision Tarafi

- Kamera + Raspberry Pi kombinasyonu
- Beklenen gorevler:
  - kutu tespiti
  - renk dogrulama
  - sayim
  - sapma takibi

## Guc

- 5V SMPS
- 12V SMPS

## Pratik Notlar

- Servo beslemesi Mega uzerinden verilmemelidir; harici guc kullanilmalidir.
- Limit switch mantigi kodda `INPUT_PULLUP` ile dusunulmustur; elektriksel baglanti buna gore degerlendirilmelidir.
- Vision tarafinda sahaya cikmadan once isik, ROI ve kamera sabitlemesi ayrica dogrulanmalidir.

## AI Icin Notlar

- Donanimla ilgili oneriler verirken hangi karta veya hatta dokundugunuzu acik yazin.
- Pin veya guc varsayimi yapmayin; `mega.cpp` icindeki mevcut tanimlari referans alin.
- Vision donanimi ile ana kontrol devresini ayni karar zinciri gibi ele almayin.
