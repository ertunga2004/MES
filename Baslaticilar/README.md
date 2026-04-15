# Tikla Calistir Baslaticilar

Bu klasordeki `.cmd` dosyalari Windows Explorer'dan cift tiklanarak kullanilabilir.

PowerShell yardimci scriptleri karisiklik olusmasin diye `ps1\` altina alinmistir.

Hazir baslaticilar:

- `MES Web.cmd`
- `Pick To Light.cmd`
- `Giyotin Kontrol.cmd`
- `Raspberry Saat Senkronize.cmd`
- `Raspberry Observer GUI.cmd`
- `Raspberry Observer Headless.cmd`
- `Raspberry HSV Kalibrasyon.cmd`

Ortak mantik:

- Python once uygulamanin kendi `.venv` klasorunde aranir.
- Sonra repo kokundeki `.venv` aranir.
- Bulunamazsa sirayla `py -3` ve `python` denenir.
- Her uygulama dogru calisma klasorunden acilir; bu sayede `cd` yapmadan cift tik ile baslar.

Masaustune kisayol birakmak icin:

- `Install Desktop Shortcuts.cmd`

Notlar:

- `MES Web.cmd` backend'i acar. Panel hazir olunca `http://127.0.0.1:8080` adresinden girilir.
- `Giyotin Kontrol.cmd` interaktif konsol uygulamasidir; cift tiktan sonra is kodu ve adet sorar.
- `Raspberry Observer GUI.cmd`, `Raspberry Observer Headless.cmd` ve `Raspberry HSV Kalibrasyon.cmd` uygulamayi acmadan hemen once observer + Pi saat senkronu gonderir.
- Sadece saati guncellemek icin `Raspberry Saat Senkronize.cmd` kullanilabilir.
- `Raspberry ...` baslaticilari istege baglidir; Windows gelistirme ortaminda kolay test icin eklendi.
- `Giyotin_kontrol\pc_app\requirements.txt` icindeki paketler yoksa once onlar kurulmalidir.
