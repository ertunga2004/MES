# Baglanti Semasi

## ESP32 -> Nokia 5110

ESP32 karti powerbank veya USB uzerinden beslenecekse, Nokia 5110 modulu yalnizca `3V3` hattindan beslenmelidir.

| Nokia 5110 | ESP32 38 pin devkit | Not |
| --- | --- | --- |
| GND | GND | ortak toprak |
| VCC | 3V3 | 5V kullanma |
| CLK | GPIO18 | SPI clock |
| DIN | GPIO23 | SPI MOSI |
| DC | GPIO27 | data / command |
| CE | GPIO26 | chip enable |
| RST | GPIO33 | LCD reset |
| BL | opsiyonel | modulde seri direnc varsa 3V3, emin degilsen bos birak |

## Opsiyonel Fiziksel Buton

| Buton ucu | ESP32 |
| --- | --- |
| Uc 1 | GPIO25 |
| Uc 2 | GND |

Kod `INPUT_PULLUP` kullandigi icin harici direnç gerekmez.

Buton davranislari:

- kisa basma: normal ilerletme
- hizli cift basma: son operasyonu geri alma
- 3 saniye uzun basma: reset komutu

## ASCII Semasi

```text
Powerbank USB
    |
    +--> ESP32 USB

ESP32 3V3  ----> Nokia VCC
ESP32 GND  ----> Nokia GND
ESP32 GPIO18 --> Nokia CLK
ESP32 GPIO23 --> Nokia DIN
ESP32 GPIO27 --> Nokia DC
ESP32 GPIO26 --> Nokia CE
ESP32 GPIO33 --> Nokia RST

ESP32 GPIO25 --> Buton
ESP32 GND    --> Buton
```

## Breadboard Yoksa

- Gecici test icin fiziksel buton yerine GUI butonunu kullan.
- Fiziksel buton baglayacaksan iki jumper ile dogrudan karta veya saglam bir ara baglantiya git.
- 4 bacakli tactile butonda ayni taraftaki iki bacak zaten kisa devredir; karsilikli cift kullan.

## Guvenlik Notu

- Nokia 5110 ekranini 5V ile besleme.
- BL pinini dogrudan baglamadan once modul uzerinde direnç olup olmadigini kontrol et.
- GND ortaklanmadan ekran kararsiz calisabilir.
