# MES

Bu repo, mini konveyor hattinin kontrol, izleme, OEE, operator kiosk, teknisyen cagri ekrani ve workbook tabanli audit akisini ayni kod tabaninda toplar. Ana aktif gelistirme ekseni `mes_web/` altindaki FastAPI + WebSocket + Excel runtime yapisidir.

## Bugunku Durum

- fiziksel karar ve hareket otoritesi `mega.cpp`
- seri <-> MQTT bridge `esp32.cpp`
- dashboard, operator kiosk, teknisyen kiosk, OEE runtime ve workbook yazimi `mes_web/`
- vision observer `raspberry/` altinda pasif gozlemci
- pick-to-light `picktolight/` altinda ayri modul
- birincil kalici veri siniri CSV degil, tarihli workbook ve runtime state dosyalaridir

## Su Anda Sistem Nasil Calisiyor

1. Mega; olcum, queue ve robot olaylarini text log ve status satiri olarak uretir.
2. ESP32 bu satirlari MQTT topiclerine tasir.
3. `mes_web` topicleri dinler, dashboard, kiosk ve teknisyen snapshot'larini uretir.
4. Browser dashboard REST + WebSocket ile; kiosk ve teknisyen ekranlari ayri route, bootstrap ve WebSocket akislari ile beslenir.
5. `mes_web` ayni olaylardan workbook'a kayit yazar.
6. OEE runtime `logs/oee_runtime_state.json` icinde tutulur ve backend tarafinda hesaplanir.
7. Dahili sure alanlari milisaniye birincil olacak sekilde tutulur.

## Hizli Baslangic

Launcher ile:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
Baslaticilar\MES Web.cmd
```

Manuel:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m pip install -r mes_web\requirements.txt
$env:MES_WEB_HOST = "0.0.0.0"
$env:MES_WEB_PORT = "8080"
python -m mes_web
```

Adresler:

- dashboard: `http://127.0.0.1:8080`
- kiosk ornegi: `http://127.0.0.1:8080/kiosk/kiosk-test-1`
- teknisyen ekrani: `http://127.0.0.1:8080/technician/tech-1`
- ayni agdaki cihazdan: `http://<PC_IP>:8080/kiosk/kiosk-test-1`

`Baslaticilar\MES Web.cmd`, server hazir oldugunda dashboard, kiosk ve teknisyen ekranlarini varsayilan tarayicida otomatik acar; linkler CMD ekraninda da yazilir.

## Operasyonel Notlar

- sistem acildiginda acik kalan vardiya otomatik devam ettirilmez
- `__reset_counts__` Mega'ya gitmez; backend icinde yerel sifirlama yapar
- kiosk browser tabanlidir; MQTT bilgisi bilmez
- teknisyen ekrani browser tabanlidir; MQTT bilgisi bilmez
- kioskta son 5 tamamlanan urun icin kalite duzeltme vardir
- `Ariza Bildir`, manuel fault ile birlikte teknisyen cagrisi acar
- teknisyen `Cevapla` ve `Tamamla` aksiyonlariyla cevap, giderme ve toplam sureleri sabitler
- hurda urun depoya dusmez
- `Broker Offline` goruluyorsa once launcher'in kullandigi interpreter'da `paho-mqtt` kurulu mu kontrol edilmelidir

## Dokuman Haritasi

- [Genel Mimari](architecture.md)
- [Veri Modeli](data-model.md)
- [MQTT Topicleri](mqtt-topics.md)
- [Tablet ve Teknisyen Kiosk Durumu](tablet_plan.md)
- [MES Web](../mes_web/README.md)
- [Baslaticilar](../Baslaticilar/README.md)
- [Raspberry](../raspberry/README.md)
- [Pick To Light](../picktolight/README.md)
- [AI Guide](AI_GUIDE.md)
