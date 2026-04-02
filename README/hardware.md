# Hardware Notes

## Ana Bilesenler

- Mega tabanli kontrol karti
- ESP32 bridge karti
- renk sensori
- limit switch'ler
- konveyor surucu ve motoru
- robot kol
- `mes_web` calistiran operator bilgisayari
- opsiyonel Raspberry vision observer

## Rol Dagilimi

### Mega

- fiziksel karar ve hareket otoritesi
- queue ve sorting mantigi
- log ve status satirlarinin ana kaynagi

### ESP32

- seri -> MQTT bridge
- komut geri tasima
- baglanti telemetry'si

### Operator Bilgisayari

- `mes_web` backend ve web UI
- workbook yazimi
- OEE runtime state tutma

### Raspberry

- pasif vision gozlem
- crossing ve renk capraz kontrolu

## Saha Notlari

- OEE icin vardiya operator tarafindan baslatilmalidir
- sistem acilinca acik vardiya otomatik surdurulmez
- `__reset_counts__` backend yerel aksiyonudur
- gecis doneminde yerel legacy Node-RED ekranina erisim ihtiyaci olabilir

## Bakim ve Dikkat Noktalari

- Mega reset veya serial kopmasi, dashboard'da durum dususu olarak gorulmelidir
- ESP32 offline ise komut hattina guvenilmemelidir
- workbook yazimi operator PC disk erisimi gerektirir
- vision offline olsa bile ana hat calismaya devam eder
