# Work Orders Status Policy

## Amaç
Bu doküman, `mes.work_orders` tablosundaki `status` alanının tasarımı, anlamı ve runtime ile veritabanı arasındaki durum uyumsuzluklarının (status drift) nasıl ele alınacağına dair verilen mimari kararları ve politikaları içerir.

## E2 Analiz Tarihi
2026-06-08

## Drift Bulgusu
PostgreSQL veritabanındaki `mes.work_orders` tablosunda bulunan 6 iş emrinden 5 tanesinin `status` değerinin runtime JSON state dosyası (`oee_runtime_state.json`) ile uyumsuz olduğu tespit edilmiştir:
- **DB tarafı:** Tüm kayıtların durumu `queued` olarak kalmıştır.
- **Runtime tarafı:** 4 kayıt `completed`, 1 kayıt `active` ve 1 kayıt `queued` durumundadır.

## Drift Nedeni
Drift'in temel nedeni veritabanı mirror mekanizmasının pasif modda çalıştırılmasıdır:
- `mes.work_orders` tablosu ilk olarak D1/D1.5 aşamalarında mirror edildi ve veriler `queued` statüsündeyken DB'ye yazıldı.
- Daha sonraki canlı/fiziksel testlerde runtime JSON tarafında iş emirleri aktifleşti ve tamamlandı.
- Ancak `MES_WEB_DB_ENABLED=false` ve `MES_WEB_DB_MIRROR_WORK_ORDERS=false` flag'leri kapalı tutulduğu için veritabanı bu güncellemeleri alamadı ve pasif kalarak drift oluşturdu.

## Karar: mes.work_orders Current-State Mirror
MVP (Minimum Viable Product) aşaması için `mes.work_orders` tablosunun bir **Current-State Mirror (Güncel Durum Aynası)** olarak kabul edilmesine karar verilmiştir.

### Status Alanının Anlamı
- `mes.work_orders.status` alanı, runtime JSON'daki ilgili iş emrinin **en güncel** durumunu yansıtmalıdır.
- İş emri durum geçişleri (örn: `queued` -> `active` -> `completed`) runtime üzerinde gerçekleştikçe, veritabanındaki karşılık gelen satır da güncellenmelidir.

### Neden Import/Master Snapshot Olarak Bırakılmadı?
- Eğer veritabanı sadece ilk import anındaki durumu (snapshot) korusaydı, MES Web bileşenlerinin iş emirlerinin güncel tamamlanma durumlarını takip etmesi zorlaşacaktı.
- Tablonun güncel mirror olarak tasarlanması, ileride veritabanı okumaları (DB Read) etkinleştirildiğinde MES sisteminin tutarlı bir şekilde çalışabilmesi için gereklidir.
- Kod tabanındaki mevcut UPSERT yapısı da (`ON CONFLICT DO UPDATE SET status = EXCLUDED.status`) bu güncel ayna tasarımını desteklemektedir.

## Work Order Events/History İçin Gelecek Notu
- İş emirlerinin durum geçişlerinin tarihçesini (durum değişiklik zamanları, geçmiş durumlar vb.) takip etmek için ayrı bir tarihçe tablosunun (`mes.work_order_events` veya `status_history`) oluşturulması planlanmaktadır.
- MVP sonrasında, raporlama ve OEE analizlerinin doğruluğunu artırmak amacıyla bu tarihçe modeli ayrıca değerlendirilecektir.

## Controlled Sync Gerekliliği
- Sistemdeki pasif mod kaynaklı driftlerin temizlenmesi ve veritabanı doğrulama (verify) betiğinin başarıyla tamamlanması için periyodik veya kontrollü senkronizasyon çalıştırılmalıdır.
- Drift'in çözümü için `mirror_work_orders_to_db.py` betiğinin manuel tetiklenmesi veya geçici olarak mirror flag'lerinin açılarak runtime üzerinden senkronizasyonun sağlanması gereklidir.

## Güvenlik Sınırları
- **Source-of-truth geçişi değildir:** Bu karar ve senkronizasyon çalışması MES sisteminin ana veri kaynağını veritabanına taşımaz. Ana veri kaynağı hâlâ JSON/Excel/FERP dosyalarıdır.
- **Runtime DB read yoktur:** Uygulama çalışma zamanında iş emri durumu sorgularken veritabanına başvurmaz.
- **JSON/Excel/FERP/MQTT akışı korunur:** Mevcut entegrasyonlar ve veri akış kanalları tamamen izole edilmiş ve korunmuştur.
- **Drift sync manuel/flag kontrollü yapılmalıdır:** Senkronizasyon işlemleri kontrollü bir şekilde gerçekleştirilmelidir.

## Sonraki Faz: E2B Controlled Work Orders Resync
Bir sonraki aşamada (E2B), bu karar doğrultusunda veritabanında oluşan drift'in giderilmesi için kontrollü bir şekilde `mirror_work_orders_to_db.py` scripti koşturulacak ve `verify_work_orders_db_mirror.py` ile doğrulama yapılacaktır.
