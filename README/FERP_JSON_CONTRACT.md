# FERP JSON Contract

Bu dokuman MES ile FERP arasindaki JSON sozlesmesini tarif eder. UI dili MES olarak kalir; dis JSON, import/export ve entegrasyon dokumantasyonu FERP object + label diliyle calisir.

## Tek Kaynak

- Label kaynagi: `README/ferp_labels.xlsx`
- Registry kodu: `mes_web/ferp_labels.py`
- Excel okunamazsa registry fonksiyonlari acik hata doner.
- Import akisi registry hatasinda is emrini dusurmez; response icinde warning doner.
- Export akisi kapanisi geri almaz; dosya yazma veya registry hatasi `ferp_export.status = error` veya export warnings icinde gorunur.

## Kapsam

Ilk kapsam bu FERP object kodlariyla sinirlidir:

- Uretim Yonetimi: `mym4104`, `mym4004`, `mym4008`, `mym4009`, `mym4043`, `mym4086`
- Malzeme Yonetimi: `mym2008`, `mym2010`, `mym2056`

## Registry API

Kod ici yardimcilar:

- `get_labels_for_object(object_code)`
- `find_label(object_code, label_code)`
- `require_label(object_code, label_code)`
- `validate_label_payload(object_code, payload)`

`validate_label_payload` ciktisi:

```json
{
  "valid": false,
  "known_labels": ["lblMMFB0_NUMBER"],
  "unknown_labels": ["lblUNKNOWN"],
  "missing_required_labels": ["lblMMFB0_QTY"],
  "warnings": ["FERP_UNKNOWN_LABELS: lblUNKNOWN"]
}
```

## Label-First Import

Public import JSON FERP label-first payload kabul eder. Bu payload MES runtime state icindeki normalize alanlara cevrilir; runtime tamamen `lbl...` alanlarina tasinmaz.

```json
{
  "orders": [
    {
      "ferp_object": "mym4004",
      "ferp_screen": "Is Emirleri",
      "ferp_labels": {
        "lblMMFB0_NUMBER": "WO-FERP-001",
        "lblMMFB0_DATE": "2026-04-27",
        "lblMMFB0_QTY": 3,
        "lblMTM00_CODE": "FIN-RED",
        "lblMTM00_NAME": "Finished Red",
        "lblMUNT0_CODE": "AD",
        "lblMMFB4_TIME": 15
      }
    }
  ],
  "replace_existing": true
}
```

Mevcut MES canonical input sekli korunur. Bilinmeyen label importu patlatmaz; response icinde `warnings` olarak doner.

## Export

Is emri operator onayi ile kapatildiktan sonra accept-active response semasi korunur ve sadece `ferp_export` alani eklenir.

Pending dosya yolu:

```text
logs/ferp_exports/pending/FERP_<order_id>_<timestamp>.json
```

Dosya adi guvenlidir: `order_id` sanitize edilir, timestamp dosya adina uygun uretilir, ayni ad varsa overwrite yapilmaz.

Export paket semasi:

```json
{
  "schema": "ferp_mes_export.v1",
  "source": {
    "system": "MES",
    "module_id": "konveyor_main"
  },
  "work_order": {
    "ferp_object": "mym4004",
    "ferp_screen": "Is Emirleri",
    "ferp_labels": {
      "lblMMFB0_NUMBER": "WO-FERP-001",
      "lblMMFB0_QTY": 3
    }
  },
  "station_flow": [],
  "ferp_documents": [],
  "quality_summary": {
    "GOOD": 1,
    "REWORK": 0,
    "SCRAP": 0,
    "TOTAL": 1
  },
  "warnings": []
}
```

## Istasyon Akisi

Export `station_flow` list/dict tabanlidir; yeni istasyon eklemek icin `mes_web/ferp_export.py` icindeki template genisletilir.

- `SENSOR-01`: hammadde girer, renk okuma sonrasi yari mamul cikar.
- `VISION-01`: yari mamul kalite izinden gecer.
- `ROBOT-01`: yari mamul girer, mamul cikar.

## Belge/Hareket Adaylari

Export bu FERP belge adaylarini uretir:

- `mym2010` Cikis Hareketleri: hammadde cikisi
- `mym2008` Giris Hareketleri: yari mamul ve mamul girisi
- `mym2056` Onayli Depo Transferleri: istasyon/depo/lokasyon arasi yari mamul hareketi

Kalite ayrimi:

- `GOOD`: mamul giris satiri
- `REWORK`: ayri rework/yari mamul satiri
- `SCRAP`: normal mamul girisinden ayri fire/hurda satiri

Malzeme hareket miktari icin FERP Excel kaynaginda net hareket satiri quantity label'i bulunmadigi icin satir miktari simdilik `qty` alaninda acik sekilde export edilir ve warning eklenir.
