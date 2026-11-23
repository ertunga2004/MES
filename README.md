# MES

Bu repo, mini konveyor hattinin kontrol, izleme, OEE, operator kiosk ve workbook tabanli audit akisini ayni kod tabaninda toplar. Aktif uygulama omurgasi `mes_web/` altindaki FastAPI + WebSocket + Excel runtime katmanidir.

## Bugunku Sistem Ozeti

- fiziksel karar ve hareket otoritesi `mega.cpp`
- seri <-> MQTT bridge `esp32.cpp`
- dashboard, operator kiosk, teknisyen kiosk, OEE runtime ve workbook yazimi `mes_web/`
- vision observer `raspberry/` altinda pasif capraz kontrol
- `picktolight/` ayri bir modul olarak yasiyor
- birincil kalici veri siniri CSV degil, tarihli workbook + runtime state

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

Ana adresler:

- dashboard: `http://127.0.0.1:8080`
- kiosk ornegi: `http://127.0.0.1:8080/kiosk/kiosk-test-1`
- teknisyen ekrani: `http://127.0.0.1:8080/technician/tech-1`
- ayni agdaki cihazdan: `http://<PC_IP>:8080/kiosk/kiosk-test-1`

`Baslaticilar\MES Web.cmd`, server hazir oldugunda dashboard, kiosk ve teknisyen ekranlarini varsayilan tarayicida otomatik acar; linkler CMD ekraninda da yazilir.

## Onemli Operasyon Notlari

- kiosk browser tabanlidir; MQTT'ye dogrudan baglanmaz
- dahili sure hesaplari ms-first tutulur
- `openingChecklistDurationMs` OEE/availability disidir
- `closingChecklistDurationMs` planned stop / planned maintenance olarak sayilir
- `manualFaultDurationMs` unplanned stop olarak sayilir
- hurda urun depoya dusmez
- `Broker Offline` goruluyorsa once launcher'in kullandigi Python ortaminda `paho-mqtt` kurulu mu kontrol edilmelidir
- MQTT client id varsayilan olarak benzersiz uretilir; ayni id ile iki MES Web acilmasi broker baglantisini titretir

## MES Network Control v3.5

Admin PowerShell oturumunda once sadece rapor alin:

    Set-ExecutionPolicy Bypass -Scope Process -Force
    .\MES_Network_Control.ps1 -Mode Report

Ilk fazda sadece MES Web 8080 erisimi icin uygulanir:

    .\MES_Network_Control.ps1 -Mode Apply -Scope MesOnly

Geri alma sadece ilgili backup JSON ile yapilir:

    .\MES_Network_Control.ps1 -Mode Rollback -BackupPath ".\network_backups\network-backup-YYYYMMDD-HHMMSS.json"

Ilk fazda `MesAndSunshine`, `MqttBroker` ve `DisableBroadRules` kullanilmaz.

## Dokuman Haritasi

- [Genel Mimari](README/architecture.md)
- [Veri Modeli](README/data-model.md)
- [MQTT Topicleri](README/mqtt-topics.md)
- [Tablet ve Teknisyen Kiosk Durumu](README/tablet_plan.md)
- [MES Web](mes_web/README.md)
- [Baslaticilar](Baslaticilar/README.md)
- [AI Guide](README/AI_GUIDE.md)

## Temiz Transfer Notu

### Proje adi
MES

### Ne ise yarar
Mini konveyor MES, kiosk, OEE ve kontrol yazilimlari.

### Teknoloji
Python FastAPI + PlatformIO/Arduino

### Kurulum

``powershell
cd mes_web
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
``

### Calistirma

``powershell
cd mes_web; python -m mes_web
``

### Eksik / kontrol edilecek noktalar
- logs ve export dosyalari kopyalanmaz.
- Excel/CSV/DB/JSONL dosyalari manuel kontrol gerektirir.
- Bagimlilik durumu: Giyotin_kontrol\platformio.ini, Giyotin_kontrol\pc_app\requirements.txt, mes_web\requirements.txt, picktolight\requirements.txt, picktolight\esp32\picktolight_nokia5110\platformio.ini, raspberry\requirements.txt

