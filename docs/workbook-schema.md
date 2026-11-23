# Workbook Schema

## 1. Amac

Bu dokuman, gunluk MES workbook'un sistem icindeki rolunu netlestirir. Workbook, canli sistemin transactional database kaynagi degildir. Workbook; audit, projection, raporlama, debug ve ileride backfill/replay icin kullanilabilecek dosya tabanli kayit ciktisidir.

Bu ayrim ozellikle database ayristrmasi, masterdata tasarimi ve FERP entegrasyonu icin kritiktir. Canli karar otoritesi runtime state ve backend domain mantigidir; workbook bu kararlarin sheet bazli gorunur ve denetlenebilir yansimasidir.

## 2. Workbook'un Sistem Icindeki Rolu

Gunluk workbook `mes_web` tarafindan uretilen operasyon kayitlarini tek dosyada toplar.

Varsayilan canli workbook yolu:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`

Template kaynak:

- `MES_Konveyor_Veritabani_Sablonu.xlsx`

Workbook'un rolleri:

- saha/operator tarafindan acilip kontrol edilebilir audit ciktisi olmak
- olay, olcum, tamamlanan urun, OEE, vision, is emri ve bakim projection'larini bir arada tutmak
- gecmis gunler icin raporlama ve inceleme kaynagi olmak
- SQL gecisinde backfill veya replay yardimci kaynagi olmak
- FERP entegrasyonunda sheet bazli kontrol ve dis aktarim icin izlenebilirlik saglamak

Workbook'un rolleri disinda kalanlar:

- canli transactional database olmak
- runtime state'in tek dogruluk kaynagi olmak
- resmi ERP stok kaynagi olmak
- tum olay gecmisini eksiksiz replay edebilen event store olmak

## 3. Kaynak Otoritesi Kurali

Kaynak otoritesi su sekilde okunmalidir:

1. Fiziksel olay ve sorting karari icin kontrol katmani ve MQTT olaylari birincildir.
2. Canli vardiya, OEE, is emri, fault, cihaz ve kiosk state'i icin `logs\oee_runtime_state.json` birincil runtime state'tir.
3. Masterdata icin mevcut sistemde `0_Tanimlamalar` sheet'i kaynaktir; hedefte bu kaynak `FERP_MasterData.xlsx` veya SQL master tables icine ayrilmalidir.
4. Gunluk workbook sheet'leri audit/projection ciktisidir.
5. FERP import icin `mes_web\ferp_import\ferp_work_orders.json` ve FERP label kontrati import siniridir.
6. FERP export icin pending export dosyalari ve FERP XLS/JSON ciktisi export siniridir.

Kural:

- Workbook, canli runtime state'i ezmemelidir.
- Workbook, transactional DB gibi yazma/okuma dongusunun ana kaynagi yapilmamalidir.
- Workbook'tan okuma islemleri backfill, replay, debug, raporlama veya FERP aktarim hazirligi icin kullanilmalidir.

## 4. Gunluk Workbook Sheet Listesi

Aktif sheet'ler:

- `0_Tanimlamalar`
- `1_Olay_Logu`
- `2_Olcumler`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `5_OEE_Anliklari`
- `6_Vision`
- `7_Is_Emirleri`
- `8_Depo_Stok`
- `9_Bakim_Kayitlari`
- `99_Raw_Logs`

Notlar:

- `99_Raw_Logs` normal kullanimda gizli/teknik debug sheet'i gibi ele alinmalidir.
- `7_Is_Emirleri` ve `8_Depo_Stok` workbook icinde projection'dir; bunlarin canonical kaynagi runtime/domain modeldir.
- `5_OEE_Anliklari` event degil, calculated OEE snapshot zaman serisidir.

## 5. Sheet Bazli Siniflandirma

| Sheet | Siniflandirma | Canli kaynak mi? | DB gecis notu |
| --- | --- | --- | --- |
| `0_Tanimlamalar` | Mevcut masterdata kaynagi, hedefte ayrilacak | Katalog icin evet | `FERP_MasterData.xlsx` veya SQL master tables |
| `1_Olay_Logu` | Normalized audit/event projection | Hayir | Event/audit table adayi |
| `2_Olcumler` | Measurement audit/projection | Hayir | Measurement table adayi |
| `3_Arizalar` | Fault audit/projection | Hayir | Fault event/history table adayi |
| `4_Uretim_Tamamlanan` | Production completion audit/projection | Hayir | Production completion table adayi |
| `5_OEE_Anliklari` | Calculated OEE snapshot | Hayir | OEE snapshot/time-series table adayi |
| `6_Vision` | Vision observation audit | Hayir | Vision observation table adayi |
| `7_Is_Emirleri` | Work order projection | Hayir | Projection degil, canonical is emri modeli DB'ye tasinir |
| `8_Depo_Stok` | Operational inventory projection | Hayir | MES oturum stoku olarak kisitli DB adayi |
| `9_Bakim_Kayitlari` | Maintenance audit/projection | Hayir | Maintenance history table adayi |
| `99_Raw_Logs` | Raw log archive/debug | Hayir | Normal raporlama DB'sine degil; `raw_event_archive` adayi |

## 6. Sheet Bazli Girdi -> Islem -> Cikti Analizi

| Sheet | Girdi | Islem | Cikti |
| --- | --- | --- | --- |
| `0_Tanimlamalar` | Workbook/template icindeki katalog bloklari | `masterdata.py` bloklari okur ve normalize eder | Operator, istasyon, ariza tipi ve bakim adimi kataloglari |
| `1_Olay_Logu` | MQTT, kiosk, teknisyen, system ve audit olaylari | Olaylar normalize edilir ve satir olarak yazilir | Denetlenebilir event/audit projection |
| `2_Olcumler` | Sensor olcum ve renk karar verileri | Measurement detaylari kolonlara ayrilir | Olcum audit kaydi |
| `3_Arizalar` | Tablet/kiosk/manual fault state ve fault history | Fault baslangic, bitis ve sure alanlari yansitilir | Ariza audit/projection satirlari |
| `4_Uretim_Tamamlanan` | Tamamlanan urun ve kalite state'i | Urun tamamlanma, kalite, override ve korelasyon alanlari yansitilir | Urun izlenebilirlik kaydi |
| `5_OEE_Anliklari` | Runtime trend, tablet OEE veya periodic snapshot | OEE, availability, performance, quality hesaplari snapshot olarak yazilir | Calculated OEE time-series |
| `6_Vision` | Vision observer olaylari | Track, renk, confidence ve korelasyon alanlari yansitilir | Vision observation audit |
| `7_Is_Emirleri` | Runtime `workOrders.ordersById` | Aktif/kuyruk/tamamlanan is emirleri sheet'e projekte edilir | Work order projection |
| `8_Depo_Stok` | Runtime `workOrders.inventoryByProduct` | Operasyonel stok durumu sheet'e projekte edilir | MES oturum stok projection'i |
| `9_Bakim_Kayitlari` | Maintenance session ve checklist adimlari | Adim bazli sure ve tamamlanma bilgisi yazilir | Maintenance audit/projection |
| `99_Raw_Logs` | Ham MQTT/tablet/vision/system payload | Parse edilmeden veya parse sonucuyla birlikte teknik iz olarak saklanir | Raw debug/audit archive |

## 7. Append / Upsert / Snapshot Davranislari

| Sheet | Davranis | Not |
| --- | --- | --- |
| `0_Tanimlamalar` | Read/reference | Mevcut sistemde masterdata kaynagidir; runtime event yazimi yapilmaz |
| `1_Olay_Logu` | Append | Her normalize olay yeni audit satiri olarak dusmelidir |
| `2_Olcumler` | Append | Olcum kararlari gecmise donuk degistirilmemelidir |
| `3_Arizalar` | Upsert/projection | Acik fault kapaninca sure ve status alanlari guncellenebilir |
| `4_Uretim_Tamamlanan` | Append + targeted update | Kalite override veya late vision bilgisi ilgili satiri guncelleyebilir |
| `5_OEE_Anliklari` | Snapshot/upsert | Ayni snapshot zamani varsa guncellenebilir; calculated time-series olarak okunur |
| `6_Vision` | Append | Vision gozlem olaylari audit izi olarak eklenir |
| `7_Is_Emirleri` | Upsert/projection | Is emri state'i guncellendikce ayni order satiri yansitilir |
| `8_Depo_Stok` | Upsert/projection | Match key bazli operasyonel stok projection'i guncellenir |
| `9_Bakim_Kayitlari` | Upsert/projection | Session/step bazli kayitlar tamamlanma durumuna gore guncellenebilir |
| `99_Raw_Logs` | Append | Ham iz kaydi degistirilmemelidir |

## 8. Backfill ve Replay Kullanimi

Workbook backfill/replay icin kullanilabilir, ancak bu kullanim canli transactional kaynak oldugu anlamina gelmez.

Kullanilabilir backfill kaynaklari:

- `1_Olay_Logu`: normalize event/audit gecmisi
- `2_Olcumler`: measurement gecmisi
- `3_Arizalar`: fault history rekonstruksiyonu
- `4_Uretim_Tamamlanan`: tamamlanan urun ve kalite gecmisi
- `5_OEE_Anliklari`: calculated OEE snapshot zaman serisi
- `6_Vision`: vision observation gecmisi
- `9_Bakim_Kayitlari`: maintenance history
- `99_Raw_Logs`: yalniz debug, audit dogrulama veya raw archive amacli

Kisitlar:

- Workbook projection oldugu icin her domain kararinin tum ara durumlarini tasimayabilir.
- Upsert sheet'lerinde son gorunum bulunabilir; her degisiklik olayi ayrica event olarak yoksa tam replay eksik kalabilir.
- `5_OEE_Anliklari` hesaplanmis snapshot oldugu icin ham OEE event store degildir.
- `99_Raw_Logs` normal raporlama modeli icin kullanilmamalidir.
- `oee_runtime_state.json` gecmis kayit kaynagi degildir; sadece son/current state kurtarma icin degerlendirilebilir.

## 9. Transactional DB Olmama Kurali

Gunluk workbook asagidaki amaclarla kullanilmamalidir:

- canli is emri kuyrugunun tek kaynagi
- aktif vardiya state'inin tek kaynagi
- aktif ariza veya yardim cagrisinin tek kaynagi
- resmi ERP stok defteri
- uygulama tarafindan surekli sorgulanan transactional database
- domain invariants ve is kurallarinin ana saklama katmani

Dogru kullanim:

- audit/projection ciktisi
- operator/muhendis kontrol dosyasi
- raporlama girdisi
- gecmis gun backfill yardimci kaynagi
- FERP entegrasyonuna hazirlik ve kontrol siniri

## 10. Riskler ve Koruyucu Kurallar

| Risk | Etki | Koruyucu kural |
| --- | --- | --- |
| Workbook transactional DB gibi kullanilir | Canli state ve audit birbirine karisir | Workbook sadece audit/projection/backfill kaynagi olarak belgelenmeli |
| `7_Is_Emirleri` canonical is emri kaynagi sanilir | Runtime queue ve import kontrati bozulabilir | Canonical is emri modeli runtime/domain katmanindan ayrica tasarlanir |
| `5_OEE_Anliklari` event store gibi okunur | OEE hesaplari yanlis replay edilir | Sheet calculated snapshot olarak siniflandirilir |
| `99_Raw_Logs` raporlama DB'sine tasinir | Gurultu, performans ve semantik kirlilik olusur | Sadece debug/audit/archive amacli `raw_event_archive` adayi olur |
| `0_Tanimlamalar` uzun vadede workbook icinde kalir | Masterdata surumleme ve yetki yonetimi zorlasir | Hedefte `FERP_MasterData.xlsx` veya SQL master tables ayrimi yapilir |
| Upsert sheet'leri replay icin tek kaynak sanilir | Degisiklik gecmisi eksik kalabilir | Replay icin append event sheet'leri ve raw archive ile capraz kontrol yapilir |

## 11. Ileride SQL'e Geciste Sheet -> Tablo Karsiliklari

| Sheet | Onerilen SQL karsiligi | Tasima tipi |
| --- | --- | --- |
| `0_Tanimlamalar` | `operators`, `stations`, `fault_types`, `maintenance_steps`, `products`, `operation_definitions` | Masterdata migration |
| `1_Olay_Logu` | `event_log` veya `audit_events` | Append-only event/audit |
| `2_Olcumler` | `measurements` | Measurement history |
| `3_Arizalar` | `fault_events`, `fault_history` | Fault history |
| `4_Uretim_Tamamlanan` | `production_completions` | Production traceability |
| `5_OEE_Anliklari` | `oee_snapshots` | Calculated time-series |
| `6_Vision` | `vision_observations` | Observation/audit |
| `7_Is_Emirleri` | `work_order_projection`; canonical icin `work_orders` | Projection + canonical model ayrimi |
| `8_Depo_Stok` | `operational_inventory_projection` | MES oturum stok projection'i |
| `9_Bakim_Kayitlari` | `maintenance_records`, `maintenance_step_records` | Maintenance history |
| `99_Raw_Logs` | `raw_event_archive` | Debug/audit archive; normal raporlama disi |

SQL gecisinde temel kural:

- Once canonical domain tablolar tanimlanir.
- Sonra workbook projection'lari backfill kaynagi olarak okunur.
- Workbook yazimi ilk fazda korunur.
- DB ve workbook ayni anda yazilacaksa workbook yine projection olarak kalir.

## Uygulanacak Sonraki 5 Is

1. `0_Tanimlamalar` icindeki bloklari ayri masterdata alanlarina bolen `docs/masterdata-design.md` dokumanini hazirla.
2. Canonical is emri modeli ile `7_Is_Emirleri` projection'ini ayiran `docs/database-plan.md` taslagini hazirla.
3. Her workbook sheet'i icin kolon sozlesmesini ve geriye uyumluluk kuralini tablo halinde genislet.
4. Backfill/replay icin hangi sheet'in hangi sira ile okunacagini ve hangi sheet'lerin yalniz dogrulama icin kullanilacagini tanimla.
5. `99_Raw_Logs` icin normal raporlama disi, sadece debug/audit/archive amacli saklama politikasini netlestir.
