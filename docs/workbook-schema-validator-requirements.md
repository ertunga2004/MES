# Workbook Schema Validator Requirements

## 1. Amac

Bu dokuman, ilk guvenli kod fazi olarak onerilen Workbook Schema Validator icin dar kapsamli, read-only/warning-only gereksinimleri tanimlar.

Bu dokuman kod degisikligi, SQL DDL, migration script veya Excel sablonu degisikligi degildir. Sadece validator implementasyonu oncesi gereksinim dokumanidir.

## 2. Kapsam

Validator kapsaminda hedeflenen kontroller:

- Gunluk MES workbook icinde beklenen sheet'lerin varligi
- Beklenen kolonlarin sheet bazinda varligi
- Fazladan kolonlarin raporlanmasi
- Kolon sirasindaki farklarin raporlanmasi
- Bos workbook, bulunamayan workbook ve invalid/corrupt workbook durumlarinin acik raporlanmasi
- Excel sink davranisini degistirmeden schema saglik raporu uretilmesi

Validator ilk fazda sadece kontrol ve raporlama araci olarak dusunulmelidir.

## 3. Kapsam Disi Alanlar

Validator ilk fazda asagidakileri yapmamalidir:

- Excel workbook'u degistirmek
- Excel template'i otomatik duzeltmek
- Eksik sheet veya kolonu otomatik eklemek
- Excel sink davranisini degistirmek
- Runtime JSON davranisini degistirmek
- FERP import/export davranisini degistirmek
- SQL DDL veya migration uretmek
- Workbook'u canli transactional DB gibi kullanmak
- Source-of-truth migration baslatmak

## 4. Kaynak Sozlesmeler

| Kaynak | Sozlesme rolu | Kural |
|---|---|---|
| `docs/workbook-schema.md` | Sheet rolleri ve workbook kaynak otoritesi | Workbook audit/projection/backfill/replay kaynagidir |
| `docs/workbook-field-inventory.md` | Fiili sheet/kolon envanteri | Kolon adlari degistirilmeden envanterlenir |
| `docs/workbook-data-dictionary.md` | Alan seviyesinde veri sozlugu | Projection, audit, snapshot ve raw archive ayrimi korunur |
| `docs/database-logical-schema-blueprint.md` | Logical DB mapping | Workbook DB source-of-truth degildir |
| `docs/implementation-readiness-checklist.md` | Ilk guvenli uygulama adaylari | Workbook schema validator birinci oncelikli adaydir |
| `mes_web/excel_runtime.py` | Runtime sheet/kolon kontrati | `SHEET_COLUMNS` ve kolon sabitleri beklenen kolon kaynagidir |
| `mes_web/config.py` | Workbook path/config kontrati | Validator path davranisini degistirmemelidir |

## 5. Beklenen Sheet Listesi

Validator asagidaki sheet listesini beklenen workbook kontrati olarak kullanmalidir:

| Sheet | Rol | Ilk faz davranisi |
|---|---|---|
| `0_Tanimlamalar` | Mevcut masterdata kaynagi | Eksikse warning |
| `1_Olay_Logu` | Normalized audit/event projection | Eksikse warning |
| `2_Olcumler` | Measurement audit/projection | Eksikse warning |
| `3_Arizalar` | Fault audit/projection | Eksikse warning |
| `4_Uretim_Tamamlanan` | Production completion audit/projection | Eksikse warning |
| `5_OEE_Anliklari` | Calculated OEE snapshot/time-series | Eksikse warning |
| `6_Vision` | Vision observation audit | Eksikse warning |
| `7_Is_Emirleri` | Work order projection | Eksikse warning |
| `8_Depo_Stok` | Operational inventory projection | Eksikse warning |
| `9_Bakim_Kayitlari` | Maintenance audit/projection | Eksikse warning |
| `99_Raw_Logs` | Raw log archive/debug | Eksikse warning |

## 6. Beklenen Kolon Kaynagi

Beklenen kolon kaynagi `mes_web/excel_runtime.py` icindeki mevcut kolon sabitleridir. Validator bu sabitleri kaynak kontrat olarak ele almali; kolon adlarini degistirmemelidir.

| Sabit | Ilgili sheet | Rol |
|---|---|---|
| `SHEET_COLUMNS` | Sheet -> kolon listesi mapping'i | Ana kontrat |
| `EVENT_LOG_COLUMNS` | `1_Olay_Logu` | Event log kolonlari |
| `MEASUREMENT_COLUMNS` | `2_Olcumler` | Measurement kolonlari |
| `COMPLETED_COLUMNS` | `4_Uretim_Tamamlanan` | Production completion kolonlari |
| `OEE_SNAPSHOT_COLUMNS` | `5_OEE_Anliklari` | OEE snapshot kolonlari |
| `VISION_COLUMNS` | `6_Vision` | Vision kolonlari |
| `RAW_LOG_COLUMNS` | `99_Raw_Logs` | Raw log kolonlari |
| `WORK_ORDER_COLUMNS` | `7_Is_Emirleri` | Work order projection kolonlari |
| `INVENTORY_COLUMNS` | `8_Depo_Stok` | Operational inventory projection kolonlari |
| `FAULT_COLUMNS` | `3_Arizalar` | Fault kolonlari |
| `MAINTENANCE_COLUMNS` | `9_Bakim_Kayitlari` | Maintenance kolonlari |

Not: `0_Tanimlamalar` mevcut masterdata kaynagidir; bu sheet'in blok yapisi masterdata reader gereksinimleriyle ayrica degerlendirilmelidir. Workbook schema validator ilk fazda sheet varligi ve okunabilirlik kontroluyle sinirli kalabilir.

## 7. Validator Davranis Kurallari

Validator davranisi:

- Read-only veya warning-only olmalidir.
- Excel workbook'u kaydetmemelidir.
- Workbook icinde sheet, kolon veya hucre degistirmemelidir.
- Excel template'i otomatik duzeltmemelidir.
- Excel sink davranisini degistirmemelidir.
- Eksik sheet veya kolon varsa ilk fazda sistem akisini durdurmamalidir.
- Eksik sheet veya kolon icin acik warning/report uretmelidir.
- Fazladan kolonlari info olarak raporlamalidir.
- Runtime JSON'a yazmamalidir.
- FERP import/export akisini degistirmemelidir.
- Validator sonucu opsiyonel rapor olarak tuketilmelidir.

## 8. Warning / Error Siniflandirmasi

| Durum | Ilk faz sinifi | Runtime davranisi | Not |
|---|---|---|---|
| Missing sheet | warning | Akis durmaz | Sheet adi ve workbook path raporlanir |
| Missing column | warning | Akis durmaz | Sheet bazinda kolon listelenir |
| Extra column | info | Akis durmaz | Ileri uyumluluk veya manuel kolon olabilir |
| Column order mismatch | info veya warning | Akis durmaz | Mevcut yazimi bozmuyorsa info tercih edilir |
| Empty workbook | warning | Akis durmaz | Workbook olusum akisi bozulmamalidir |
| Workbook file not found | warning veya skipped | Akis durmaz | Mevcut olusturma akisi korunur |
| Invalid/corrupt workbook | warning veya error onerisi | Ilk fazda write path bozulmaz | Runtime sink etkilenmemelidir |
| Validator internal failure | warning | Akis durmaz | Validator kendisi sistem kesintisi sebebi olmamalidir |

Strict error sinifi ileride dusunulebilir, ancak ilk fazda default davranis warning/report olmalidir.

## 9. Rapor Formati

Validator raporu sozluk/JSON benzeri bir formatla asagidaki alanlari onermelidir:

| Alan | Tip | Aciklama |
|---|---|---|
| `status` | string | `ok`, `warning`, `skipped`, `error_candidate` gibi ozet durum |
| `checked_at` | datetime_iso | Kontrol zamani |
| `workbook_path` | string | Kontrol edilen workbook dosya yolu |
| `missing_sheets` | list[string] | Eksik sheet adlari |
| `missing_columns_by_sheet` | object | Sheet bazinda eksik kolon listeleri |
| `extra_columns_by_sheet` | object | Sheet bazinda fazladan kolon listeleri |
| `column_order_notes` | object/list | Kolon sirasi farklari ve etkisi |
| `warnings` | list[string] | Warning mesajlari |
| `errors` | list[string] | Ilk fazda sadece raporlanan error adaylari |
| `summary` | string/object | Insan tarafindan okunabilir kisa ozet |

Ornek status yorumlari:

- `ok`: Beklenen sheet ve kolon kontrati saglaniyor.
- `warning`: Eksik sheet/kolon veya okunabilirlik riski var, ancak akis durdurulmuyor.
- `skipped`: Dosya yok veya validator kosulu saglanmadi, mevcut workbook olusturma akisi korunuyor.
- `error_candidate`: Corrupt/invalid workbook gibi ileride strict error olabilecek durum.

## 10. Runtime Entegrasyon Siniri

Validator runtime entegrasyonunda sinirli kalmalidir:

- Excel sink oncesi veya sonrasi read-only kontrol olarak calisabilir.
- Kontrol sonucu log/report olarak uretilir.
- Workbook write path'i engellenmez.
- Workbook olusturma ve flush akisi degistirilmez.
- Runtime JSON state degistirilmez.
- FERP import/export akisi degistirilmez.
- DB veya shadow DB baglantisi kurulmaz.

Ilk fazda validator, uygulama davranisini degistiren gatekeeper olmamalidir. Sadece gorunurluk ve erken uyari saglamalidir.

## 11. Test Senaryolari

| Test senaryosu | Beklenen sonuc | Kritik kabul |
|---|---|---|
| Tam uyumlu workbook | `status=ok`, eksik sheet/kolon yok | Warning uretilmez |
| Eksik sheet olan workbook | `status=warning`, `missing_sheets` dolu | Akis durmaz |
| Eksik kolon olan workbook | `status=warning`, `missing_columns_by_sheet` dolu | Sheet/kolon adi acik raporlanir |
| Fazladan kolon olan workbook | `status=ok` veya `warning`, `extra_columns_by_sheet` dolu | Extra column info olarak gorunur |
| Kolon sirasi farkli workbook | `column_order_notes` dolu | Mevcut yazimi bozmuyorsa info |
| Bos workbook | `status=warning` | Workbook olusturma akisi bozulmaz |
| Dosya yok senaryosu | `status=skipped` veya `warning` | Mevcut yeni workbook olusturma akisi bozulmaz |
| Corrupt/invalid workbook senaryosu | `status=warning` veya `error_candidate` | Excel sink/runtime write path bozulmaz |

Test kapsaminda `tests/test_mes_web_excel_runtime.py` mevcut Excel runtime davranisi icin referans alinmalidir. Yeni testler validator davranisini dar kapsamda dogrulamali; Excel template veya workbook write behavior degisikligi beklememelidir.

## 12. Rollback ve Guvenlik Kurallari

Rollback prensipleri:

- Validator devre disi kalirsa mevcut sistem davranisi aynen devam etmelidir.
- Validator raporu uretilmezse Excel sink etkilenmemelidir.
- Validator hata alirsa runtime write path bozulmamalidir.
- Feature flag veya config eklenirse default davranis mevcut sistemle ayni kalmalidir.
- Validator hicbir dosyayi otomatik onarmamalidir.

Guvenlik kurallari:

- Workbook audit/projection/backfill/replay kaynagi olarak kalir.
- Workbook transactional DB gibi kullanilmaz.
- `0_Tanimlamalar` masterdata kaynagi olarak korunur.
- Runtime JSON davranisi degismez.
- FERP import/export davranisi degismez.
- SQL DDL veya migration yazilmaz.

## 13. Kabul Kriterleri

Ilk faz Workbook Schema Validator kabul kriterleri:

- Validator read-only veya warning-only calisir.
- Validator workbook'u degistirmez.
- Validator Excel template'i otomatik duzeltmez.
- Validator Excel sink davranisini degistirmez.
- Eksik sheet warning olarak raporlanir.
- Eksik kolon warning olarak raporlanir.
- Fazladan kolon info olarak raporlanir.
- Kolon sirasi farki akisi durdurmaz.
- Dosya yok senaryosu mevcut workbook olusturma akisini bozmaz.
- Corrupt/invalid workbook senaryosu runtime write path'i bozmaz.
- Testler workbook yaziminin korundugunu dogrular.
- Runtime JSON ve FERP import/export davranisi degismez.

## 14. Uygulanacak Sonraki 5 Is

1. `SHEET_COLUMNS` kaynakli beklenen sheet/kolon kontratini test fixture olarak dokumante et.
2. Warning/report mesajlari icin standart kod ve insan okunabilir mesaj formatini belirle.
3. `tests/test_mes_web_excel_runtime.py` icin tam uyumlu, eksik sheet, eksik kolon, extra kolon ve dosya yok senaryolarini planla.
4. Validator'in Excel sink'e nasil baglanmadan veya sink'i bozmadan cagrilacagini tasarla.
5. Masterdata validation/fallback report gereksinim dokumanina gecmeden once validator kabul kriterlerini readiness checklist ile eslestir.
