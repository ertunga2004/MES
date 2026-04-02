# MES

Bu repo, mini konveyor hattinin kontrol, izleme, OEE, workbook tabanli veri kaydi ve yardimci vision bilesenlerini tek yerde toplar. Yeni ana gelistirme ekseni `mes_web/` altindaki FastAPI + WebSocket + Excel runtime yapisidir. Legacy Node-RED akis dosyalari ise artik repo disi yerel arsiv olarak tutulur.

## Bugunku Durum

- Fiziksel hareket ve sorting kararinin ana otoritesi `mega.cpp` tarafidir.
- MQTT bridge gorevi `esp32.cpp` tarafindadir.
- Canli web operator paneli, komut gonderimi, OEE runtime'i ve workbook yazimi `mes_web/` altindadir.
- Vision observer `raspberry/` altinda pasif gozlemci olarak calisir.
- Pick-to-light istasyonu `picktolight/` altinda ayri bir moduldur.
- Kalici veri siniri artik CSV degil, tarihli Excel workbook ve yardimci runtime state dosyalaridir.

## Su Anda Sistem Nasil Calisiyor

1. Mega; olcum, queue ve robot kol olaylarini text log ve status satiri olarak uretir.
2. ESP32 bu satirlari MQTT topiclerine tasir.
3. `mes_web` bu topicleri dinler, dashboard snapshot'i olusturur ve browser'a REST + WebSocket ile verir.
4. `mes_web` ayni olaylardan workbook'a kayit yazar.
5. OEE runtime'i `logs/oee_runtime_state.json` icinde tutulur ve backend tarafinda hesaplanir.
6. Vardiya acildiginda `PICKPLACE_DONE` olayi tamamlanmis urun kabul edilir ve varsayilan olarak `good` sayilir.
7. Vision verisi pasif ingest olarak alinir; ana sorting kararini degistirmez.

## Projede Kaynak Otoriteleri

- Hareket, queue ve sorting karari: `mega.cpp`
- MQTT tasima ve bridge telemetry: `esp32.cpp`
- Web ekran, canli snapshot ve komut akisi: `mes_web/`
- OEE runtime state ve vardiya ayarlari: `mes_web/oee_state.py`
- Kalici workbook yazimi: `mes_web/excel_runtime.py`
- Legacy dashboard akislari: repo disi yerel arsiv
- Vision observer: `raspberry/`

## Repo Haritasi

- `mega.cpp`
  - konveyor, robot kol, limit switch, renk karari ve queue akisi
- `esp32.cpp`
  - Mega log/status satirlarini MQTT'ye tasiyan bridge
- `mes_web/`
  - FastAPI backend, WebSocket snapshot, live operator paneli, OEE runtime, Excel sink
- `logs/`
  - gunluk workbook, text loglar ve `oee_runtime_state.json`
- `raspberry/`
  - vision observer, tracker ve kalibrasyon araclari
- `picktolight/`
  - ayri pick-to-light montaj istasyonu

## Dokuman Haritasi

- [architecture.md](/Users/acer/Documents/.CODE/codex/MES/README/architecture.md)
  - sistem katmanlari, sahiplikler ve veri akislari
- [mqtt-topics.md](/Users/acer/Documents/.CODE/codex/MES/README/mqtt-topics.md)
  - aktif MQTT topicleri ve publisher/subscriber sorumluluklari
- [data-model.md](/Users/acer/Documents/.CODE/codex/MES/README/data-model.md)
  - dashboard, runtime state ve workbook veri modeli
- [FERP_INTEGRATION.md](/Users/acer/Documents/.CODE/codex/MES/README/FERP_INTEGRATION.md)
  - Excel tabanli entegrasyon siniri ve sonraki JSON plani
- [hardware.md](/Users/acer/Documents/.CODE/codex/MES/README/hardware.md)
  - kartlar, sensorler, guc ve saha notlari
- [roadmap.md](/Users/acer/Documents/.CODE/codex/MES/README/roadmap.md)
  - aktif is listesi ve karar bekleyen konular
- [AI_GUIDE.md](/Users/acer/Documents/.CODE/codex/MES/README/AI_GUIDE.md)
  - ekip ici AI kullanim kurallari
- [mes_web/README.md](/Users/acer/Documents/.CODE/codex/MES/mes_web/README.md)
  - yeni web katmaninin calisma sekli ve API'leri
- [raspberry/README.md](/Users/acer/Documents/.CODE/codex/MES/raspberry/README.md)
  - vision observer dokumani
- [picktolight/README.md](/Users/acer/Documents/.CODE/codex/MES/picktolight/README.md)
  - pick-to-light istasyonu

## Hizli Baslangic

Canli web panelini acmak icin:

```powershell
cd C:\Users\acer\Documents\.CODE\codex\MES
python -m pip install -r mes_web\requirements.txt
python -m mes_web
```

Varsayilan adres:

- `http://127.0.0.1:8080`

Varsayilan veri dosyalari:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`
- `logs\oee_runtime_state.json`
- `logs\log_YYYY-MM-DD.txt`
- `logs\tablet_log_YYYY-MM-DD.txt`

## Operasyonel Notlar

- Sistem acildiginda daha once acik kalmis bir vardiya otomatik devam ettirilmez. OEE icin vardiya operator tarafindan yeniden baslatilmalidir.
- `__reset_counts__` artik Mega'ya gitmez; backend icinde yerel sayac sifirlama yapar.
- OEE tarafinda tamamlanan urun, operator duzeltmesi gelene kadar varsayilan olarak `Saglam` kabul edilir.
- Manuel kalite duzeltme ekrani sonraki asamadir; altyapi buna hazirdir ancak operator UI henuz eklenmemistir.
- CSV dosyalari yeni yapida birincil veri siniri degildir. Tarihli workbook ana kayit katmanidir.

## Yeni Gelistirme Kurali

Yeni islerin varsayilan hedefi `mes_web/` olmalidir. Legacy Node-RED tarafinda sadece:

- mevcut sahayi korumak
- parity karsilastirmasi yapmak
- yerel arsivden referans almak

amacli calisilmalidir.
