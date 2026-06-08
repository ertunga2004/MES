# Vision Events Raw Event Source Policy

## Amaç
Bu doküman, MES PostgreSQL geçişi kapsamında `mes.vision_events` tablosunun veri kaynağı stratejisini, veri bütünlüğü kurallarını, natural key/idempotency kararlarını ve E3 analizi sonrasındaki mimari yönelimi belirlemek amacıyla oluşturulmuştur.

## E3 Analiz Tarihi
* **Tarih:** 2026-06-08

## İncelenen Kaynaklar
1. **Runtime JSON State:** `data/oee_runtime_state.json`
2. **PostgreSQL Tablo Tanımı:** `db/migrations/001_initial_mes_schema.sql` içindeki `mes.vision_events` şeması.
3. **MQTT Topics Dokümantasyonu:** `docs/mqtt-topics.md` içindeki vision event stream yapıları.

## Runtime JSON Bulguları
Mevcut `oee_runtime_state.json` dosyasının analizi sonucunda, bu dosyanın ham (raw) vision event loglarını barındırmadığı, bunun yerine şu yapıları içerdiği görülmüştür:
* **`vision` Alanı:** Raw event geçmişi değil, sistemin o anki bağlantı durumu, hata durumu ve genel istatistikleri barındıran bir `current-state/summary` nesnesidir.
* **`processedVisionEventKeys` Alanı:** Olayların kendisini veya payload detaylarını saklamaz, yalnızca mükerrer işlemeyi engellemek için kullanılan benzersiz anahtarların (`dedupe key`) listesini tutar.
* **`itemsById` Alanı:** Ham olay geçmişi değil, konveyörden geçen nesnelerin en son durumunu yansıtan bir projeksiyondur (`item projection`).

## Neden JSON Tabanlı Backfill Uygun Değil?
`oee_runtime_state.json` içinde ham olay geçmişi bulunmadığı için, mevcut JSON dosyasını okuyup `mes.vision_events` tablosunu dolduracak bir dry-run/apply backfill scripti yazılması uygun değildir. JSON verisi üzerinden yapılacak bir aktarım sadece anlık bir durumu veya eksik bir geçmişi yansıtabilir ve veritabanının olay günlüğü (event log) niteliğini karşılayamaz.

## mes.vision_events İçin Gerçek Kaynak Adayları
`mes.vision_events` tablosunu beslemek için gerçek zamanlı ham olay akışına veya geçmiş loglara erişim sağlanmalıdır:
1. **MQTT Live Stream:** `sau/iot/mega/konveyor/vision/events` topic ailesi üzerinden akan canlı olay stream'i.
2. **Excel/CSV Raw Vision Logs:** Eğer varsa, geçmiş olayların depolandığı ham vision log dosyaları.
3. **Gelecekte Runtime Hook:** MES Web uygulaması üzerinde MQTT mesajlarının yakalandığı handler katmanına eklenecek bir veritabanı yazma hook'u.

## Natural Key / Idempotency Adayı
Veritabanına yazılacak olayların mükerrer olmaması ve idempotent şekilde kaydedilmesi için şu strateji izlenecektir:
* **Öncelik - `event_key`:** MQTT mesajından veya log dosyasından gelen benzersiz `event_key` (örneğin GUID veya özgün bir UUID) doğrudan natural key olarak kullanılacaktır.
* **Fallback - Kombinasyon:** Eğer kaynak veride hazır bir `event_key` bulunmuyorsa, `topic + detected_at + item_id` gibi alanların birleşiminden oluşan bir fallback anahtarı türetilebilir. Ancak bu yöntem zaman damgası hassasiyetine bağlı olduğundan dikkatli kullanılmalıdır.

## Mapping Adayları
MQTT mesajlarından veya raw loglardan `mes.vision_events` tablosuna eşlenecek alanlar:
* `event_key` (Natural key)
* `item_id` (Tespit edilen nesne ID'si)
* `event_type` (Olay türü, örn: tespit, hata vb.)
* `detected_at` (Tespit edilme zamanı)
* `source_system` (Kaynağı belirten sistem adı)
* `source_file` (Eğer Excel/CSV loglarından aktarılıyorsa dosya adı)
* `external_ref` (Varsa harici referans numarası)
* `payload` (JSON formatında ham mesaj içeriği)
* `metadata` (JSON formatında ek öznitelikler)

## Karar
1. **JSON Tabanlı Script Yazılmayacak:** Mevcut `oee_runtime_state.json` üzerinden `vision_events` dry-run/apply veya doğrulama scripti yazılmayacaktır.
2. **Ham Kaynak Netleştirilecek:** Tablo doldurulmadan önce raw event kaynağının biçimi ve konumu netleştirilecektir.
3. **MQTT Hook Planlanacak:** Eğer canlı veri yansıtma (live mirror) yapılacaksa, MES Web'in MQTT alım anında (`MQTT receive handler`) çalışacak bir veritabanı hook'u tasarlanacaktır.
4. **Historical Backfill Stratejisi:** Eğer geçmişe dönük veri doldurma istenecekse, Excel/CSV ham log kaynağı talep edilecektir.

## Güvenlik Sınırları
* **Source-of-truth Geçişi Değildir:** PostgreSQL sadece pasif bir ayna (mirror) olarak konumlandırılmaya devam edecektir.
* **Runtime DB Read Yoktur:** Uygulama çalışma zamanında veritabanından vision event okuması yapmayacaktır.
* **Mevcut Akış Korunur:** JSON/Excel/FERP/MQTT akışlarının işleyişi korunacaktır.
* **Apply Script Yoktur:** `vision_events` tablosu için şu aşamada herhangi bir yazma/güncelleme scripti oluşturulmamıştır.

## Sonraki Önerilen Faz
* **E5A:** Vision raw log kaynağı var mı envanter çalışması.
* **E5B:** Eğer geçmişe dönük raw log kaynağı yoksa, live MQTT hook entegrasyon planının hazırlanması.
