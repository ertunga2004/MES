# Tikla Calistir Baslaticilar

Bu klasordeki `.cmd` dosyalari Windows Explorer'dan cift tiklanarak kullanilabilir. PowerShell yardimci scriptleri `ps1\` altindadir.

Hazir baslaticilar:

- `MES Web.cmd`
- `Pick To Light.cmd`
- `Giyotin Kontrol.cmd`
- `Raspberry Saat Senkronize.cmd`
- `Raspberry Observer GUI.cmd`
- `Raspberry Observer Headless.cmd`
- `Raspberry HSV Kalibrasyon.cmd`

## Ortak Mantik

Python su sirayla aranir:

- uygulamanin kendi `.venv\Scripts\python.exe`
- repo kokundeki `.venv\Scripts\python.exe`
- parent klasordeki `.venv\Scripts\python.exe`
- `python`
- `py -3`

Bulunan ilk calisabilir interpreter kullanilir. Bu nedenle paketleri "sadece sistemde bir Python'a" degil, launcher'in gercekten kullandigi interpreter'a kurmak gerekir.

Komutu gormek icin:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Baslaticilar\ps1\Start-MesApp.ps1 -App mes_web -PrintCommand
```

## MES Web Ozel Notlari

`MES Web.cmd` su environment ile acilir:

- `MES_WEB_HOST=0.0.0.0`
- `MES_WEB_PORT=8080`

Bu sayede:

- ayni PC'de `http://127.0.0.1:8080`
- ayni agdaki cihazlarda `http://<PC_IP>:8080`
- kiosk ornegi `http://<PC_IP>:8080/kiosk/kiosk-test-1`

Kiosk icin `device_id` URL'nin son parcasidir.

## Bagimliliklar

Baslaticilar paket kurmaz. Gereken paketler once kurulmalidir.

MES Web icin:

```powershell
<launcherin_kullandigi_python> -m pip install -r C:\Users\acer\Documents\.CODE\codex\MES\mes_web\requirements.txt
```

Ozellikle:

- `paho-mqtt` eksikse `Broker Offline` gorunur
- `fastapi` veya `uvicorn` eksikse web katmani acilmaz
- `openpyxl` eksikse workbook tarafi calismaz

## Notlar

- `Giyotin Kontrol.cmd` interaktif konsol uygulamasidir
- `Raspberry Observer GUI.cmd`, `Raspberry Observer Headless.cmd` ve `Raspberry HSV Kalibrasyon.cmd` uygulamayi acmadan once observer + Pi saat senkronu gonderir
- sadece saati guncellemek icin `Raspberry Saat Senkronize.cmd` kullanilabilir
- masaustune kisayol birakmak icin `Install Desktop Shortcuts.cmd` kullanilabilir
