# Baglanti Semasi

## ESP32 -> Nokia 5110

ESP32 karti powerbank uzerinden USB ile beslenecek. Nokia 5110 modulunu ESP32'nin `3V3` cikisindan besle.

| Nokia 5110 | ESP32 38 pin devkit | Not |
| --- | --- | --- |
| GND | GND | Ortak toprak |
| VCC | 3V3 | 5V kullanma |
| CLK | GPIO18 | SPI clock |
| DIN | GPIO23 | SPI MOSI |
| DC | GPIO27 | Data/command |
| CE | GPIO26 | Chip enable |
| RST | GPIO33 | LCD reset |
| BL | Opsiyonel | Modulde direnc varsa 3V3, emin degilsen bos birak |

## Opsiyonel Buton

| Buton ucu | ESP32 |
| --- | --- |
| Uc 1 | GPIO25 |
| Uc 2 | GND |

Kod `INPUT_PULLUP` kullandigi icin ek direnc gerekmez.

## ASCII Cizim

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

## Breadboard Yoksa Pratik Oneri

- Gecici test icin fiziksel buton yerine Python arayuzundeki turuncu butonu kullan.
- Fiziksel buton kullanacaksan en saglikli yontem butonu iki jumper ile dogrudan karta lehimlemek veya krokodil kablo ile sabitlemek.
- 4 bacakli klasik tactile butonda ayni taraftaki iki bacak kisa devredir; karsilikli ayak ciftini kullan.
