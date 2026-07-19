# Runtime Guardrails

Bu dokuman MES runtime icin dokunulmamasi gereken sinirlari aktif dokumana konsolide eder. Kaynak notlar `docs/agent_memory/08_guardrails_and_do_not_touch.md`, `docs/agent_memory/06_runtime_data_flow.md`, arşivlenmiş `docs/archive/legacy_plans/ai_guide.md` ve SQL checkpoint notlaridir.

Bu dokuman runtime kodu, Docker config veya DB migration degisikligi yapmaz.

## Kritik Komut ve Veri Sinirlari

- `docker compose down -v` kullanilmaz.
- DB volume silinmez.
- Backup olmadan migration yoktur.
- Production benzeri DB'de kontrolsuz `DROP`, `TRUNCATE`, `DELETE`, `ALTER` calistirilmaz.
- `.env`, `data`, `logs`, `exports`, SQL backup, dump, tar ve runtime dosyalari commit edilmez.
- Runtime hotfix Git disi birakilmaz; kod degisikligi kaynak repoda izlenmelidir.

## Runtime Otoriteleri

| Bilesen | Otorite / rol |
| --- | --- |
| Mega | Fiziksel karar ve hareket otoritesidir. |
| ESP32 | Seri <-> MQTT bridge'dir. |
| MES Web | Browser dashboard, kiosk, teknisyen ekranlari ve backend runtime katmanidir. |
| Vision observer | Pasif yardimci gozlem katmanidir; Mega kararinin yerine gecmez. |
| Workbook/runtime JSON | Audit, fallback ve runtime state sinirlari olarak korunur. |
| PostgreSQL/MESQL | Kademeli DB foundation ve ortak hafiza hedefidir; full source-of-truth gecisi ayrica kanit ister. |

## MQTT ve Fiziksel Akis

- MQTT root keyfi degistirilmez.
- MQTT/ESP32/bridge akisi dashboard ve runtime state'i besler.
- Var olmayan MQTT topic varsayilmaz.
- Vision verisi yardimci ve pasif ele alinmalidir.

## Workbook ve Runtime State

- Birincil kalici veri siniri eski CSV degil, workbook ve runtime state akislariyla birlikte korunur.
- `logs/oee_runtime_state.json` runtime state icin atomik sinirdir.
- Excel workbook audit/reporting log path olarak korunur.
- FERP import/export dosya sinirlari korunur.
- DB gecisi bu yollarin aniden kaldirilmasi anlamina gelmez.

## OEE ve Reset Kurallari

- Aktif vardiya olmadan OEE baslatilmaz.
- Sistem acildiginda onceki vardiya otomatik acik gelmez.
- `__reset_counts__` Mega'ya gonderilmez; backend icinde yerel sifirlama yapar.
- Dahili sure alanlari birincil olarak milisaniye tutulur.

## UI ve Snapshot Kontratlari

- Dashboard snapshot kontrati bozulmamalidir.
- Operator kiosk ve teknisyen snapshot kontratlari ayri tutulmalidir.
- Kiosk ve teknisyen ekranlari browser tabanlidir; MQTT bilgisi bilmez.
- Kiosk kalite override davranisi ve teknisyen `acknowledge/resolve` akisi korunmalidir.
- Package/kiosk/station flow degisikligi yapilacaksa once mevcut kontrat ve test kapsamı okunmalidir.

## DB Gecis Guardrailleri

- DB hatasi runtime'i cokertmemelidir.
- DB read ve DB write ayni fazda acilmamalidir.
- Migration ve runtime hook ayni sprintte yapilmamalidir.
- DB zorunlulugu eklenmemelidir.
- Mirror/verify scriptleri silinmemelidir.
- DB read overlay, mirror/upsert davranisindan ayrilmalidir.

## BOM/BOP ve ERP Sinirlari

- BOM/BOP source owner gelmeden importer, adapter veya production payload gelistirilmez.
- Bilinmeyen BOM/BOP source field adi uydurulmaz.
- Bilinmeyen F-ERP label uydurulmaz.
- ERP/F-ERP export veya conflict lifecycle production kullanima alinacaksa once ilgili `docs/erp/` karar dokumanlari okunur.

## Is Akisi

1. Once aktif `docs/INDEX.md` ve ilgili domain README okunur.
2. Sonra plan cikarilir.
3. Dar kapsamli degisiklik yapilir.
4. Dry-run/read-only analiz veya verify ile kanit toplanir.
5. Runtime veya DB etkisi varsa kullanici onayi olmadan apply/commit/push yapilmaz.
