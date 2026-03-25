# Roadmap

## Kisa Vade

- MQTT bridge davranisini stabil hale getirmek
- `production_events.csv` ve `production_completed.csv` akisini netlestirmek
- Node-RED tarafinda olay ve durum gorunurlugunu iyilestirmek
- Vision tarafinda sari kutu ve saha kalibrasyonunu tekrar dogrulamak

## Orta Vade

- FERP ile resmi alan eslemesini netlestirmek
- ERP'den is emri alma akisini tanimlamak
- OEE hesaplari icin daha duzenli veri modeli kurmak
- Work order, operator ve line bilgisini veri modeline baglamak

## Uzun Vade

- Tam MES davranisi
- ERP ile cift yonlu entegrasyon
- Kalici veritabani katmani
- Saha ortamina tasinabilir mimari

## Ekip Bazli Is Akislari

### Konveyor ve Kontrol

- `mega.cpp`
- `esp32.cpp`
- fiziksel akis, robot ve MQTT bridge

### Veri ve Entegrasyon

- `production_events.csv`
- `production_completed.csv`
- `FERP_INTEGRATION.md`
- Node-RED akislari

### Vision

- `raspberry/`
- kutu tespiti, tracking ve capraz kontrol

### Ust Sistem ve Surec

- is emri, stok, BOM ve ERP beklentileri
- raporlama ve OEE ihtiyaclari

## Acik Kararlar

- FERP'nin resmi import formati ne olacak
- CSV gecisi ne zaman veritabani modeline donusecek
- Vision verisi ne seviyede operatora veya rapora yansitilacak
- Hangi metrikler anlik, hangileri batch uretilecek

## AI Icin Notlar

- AI gorevleri bu roadmap basliklarindan birine baglanarak verilmelidir.
- "Projeyi gelistir" yerine hangi is akisi icin ne sonuc beklendigi yazilmalidir.
- Yol haritasi guncellenirken teknik borc ile urun ihtiyaci ayrica belirtilmelidir.
