# AI Collaboration Guide

## Amac

Bu belge, projede calisan ekip uyelerinin ChatGPT, Codex veya benzeri araclara ayni baglamla gorev verebilmesini kolaylastirmak icin hazirlandi. Hedef, daha tutarli promptlar yazmak ve AI'nin yanlis varsayimlarla repo disina tasmasini onlemektir.

## AI'ya Gorev Vermeden Once

Her gorevde su 5 bilgiyi verin:

- hedef: ne degisecek veya ne duzelecek
- kapsam: hangi dosyalar incelenecek veya degisecek
- sinirlar: neye dokunulmayacak
- teslim: ne tur cikti bekleniyor
- dogrulama: sonucu nasil kontrol edecegiz

Kotu ornek:

```text
Bu projeyi duzelt.
```

Iyi ornek:

```text
`mega.cpp` ve `mqtt-topics.md` uzerinde calis. Ama MQTT root'u degistirme. Amac, yeni bir alarm tipini loglara ve dokumana eklemek. Sonunda hangi topicte ne yayinlanacagini ozetle.
```

## Bu Repo Icin Sabit Baglam

- `mega.cpp`, fiziksel akis ve sorting kararinin ana otoritesidir.
- `esp32.cpp`, Mega seri cikisini MQTT'ye tasiyan bridge rolundedir.
- Ana MQTT root: `sau/iot/mega/konveyor/`
- Vision root: `sau/iot/mega/konveyor/vision`
- Vision servisi pasiftir; sayim ve dogrulama icin veri uretir ama ana karari override etmez.
- FERP entegrasyonu su anda `production_events.csv` ve `production_completed.csv` uzerinden dusunulmelidir.
- `node-red.json`, dashboard ve veri akisini temsil eder.

## Hangi Gorevte Hangi Dosyalari Paylasmali

### Konveyor, robot veya renk karari

- `mega.cpp`
- `architecture.md`
- `mqtt-topics.md`

### MQTT, broker veya bridge davranisi

- `esp32.cpp`
- `mqtt-topics.md`
- gerekiyorsa `node-red.json`

### FERP veya veri aktarimi

- `FERP_INTEGRATION.md`
- `data-model.md`
- ilgili CSV dosyalari

### Vision ve kamera tarafi

- `raspberry/README.md`
- `raspberry/config/observer.example.json`
- `raspberry/config/boxes.example.json`
- ilgili Python dosyalari

### Genel sistem yorumu

- once `README.md`
- sonra `architecture.md`

## Prompt Sablonu

Asagidaki sablon, ekip ici kullanima uygundur:

```text
Amac:
<tek cumlede hedef>

Kapsam:
<degisecek veya incelenecek dosyalar>

Sinirlar:
<dokunulmayacak kisimlar, isimler, topicler, kolonlar>

Beklenen cikti:
<kod, dokuman, analiz, refactor, test vb.>

Dogrulama:
<hangi komut, hangi senaryo, hangi kontrol>
```

## AI'ya Verilebilecek Iyi Gorev Ornekleri

- `production_completed.csv` kolonlarini temel alarak FERP import mapper taslagi hazirla.
- `raspberry/observer/tracker.py` icin `line_crossed` olayini aciklayan teknik dokuman yaz.
- `esp32.cpp` icindeki `bridge/status` payload'ini dokumanla eslestir.
- `mega.cpp` log formatlarina gore Node-RED tarafi icin parser kurallari oner.

## Riskli Istekler

Asagidaki tipte istemler AI'nin fazla varsayim yapmasina neden olur:

- "Tum sistemi yeniden tasarla"
- "ERP entegrasyonunu tamamla" fakat kontrat vermeden
- "MQTT tarafini modernize et" fakat topic uyumlulugunu belirtmeden
- "Vision ile sorting'i yonet" fakat mevcut pasif rol kararini degistirdigini soylemeden

## AI'dan Beklenen Cikti Formati

Ekip ici standart olarak AI'dan su 4 basligi istemek faydalidir:

- hangi dosyalari inceledi veya degistirdi
- neyi neden degistirdi
- nasil dogruladi veya neden dogrulayamadi
- acik kalan riskler veya varsayimlar

## Dokuman Kullanma Sirasi

Projeye yeni giren biri veya bir AI araci icin onerilen okuma sirasi:

1. `README.md`
2. `architecture.md`
3. goreve gore ilgili teknik dokuman
4. ilgili kod dosyasi

## Kisa Kontrol Listesi

AI gorevi gondermeden once sunu kontrol edin:

- ilgili dosyalar eklendi mi
- topic, kolon veya event isimleri acik yazildi mi
- degismemesi gereken kisimlar belirtildi mi
- cikti beklentisi net mi
- dogrulama sekli yazildi mi
