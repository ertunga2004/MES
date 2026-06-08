# Work Orders Status Policy

## Amaç
Bu doküman, `mes.work_orders` tablosundaki `status` alanının tasarımı, anlamı, runtime ile veritabanı arasındaki durum uyumsuzluklarının (status drift) nasıl ele alınacağına dair verilen mimari kararları ve E2B kontrollü resync sonuçlarını içerir.

## E2 Analiz Tarihi
2026-06-08

## Drift Bulgusu
PostgreSQL veritabanındaki `mes.work_orders` tablosunda bulunan 6 iş emrinden 5 tanesinin `status` değerinin runtime JSON state dosyası (`oee_runtime_state.json`) ile uyumsuz olduğu (drift) tespit edilmiştir:
- **DB tarafı:** Tüm kayıtların durumu `queued` olarak kalmıştı.
- **Runtime tarafı:** 4 kayıt `completed`, 1 kayıt `active` ve 1 kayıt `queued` durumundaydı.

## Drift Nedeni
Drift'in temel nedeni veritabanı mirror mekanizmasının pasif modda çalıştırılmasıdır:
- `mes.work_orders` tablosu ilk olarak D1/D1.5 aşamalarında mirror edildi ve veriler `queued` statüsündeyken DB'ye yazıldı.
- Daha sonraki canlı/fiziksel testlerde runtime JSON tarafında iş emirleri aktifleşti ve tamamlandı.
- Ancak `MES_WEB_DB_ENABLED=false` ve `MES_WEB_DB_MIRROR_WORK_ORDERS=false` flag'leri kapalı tutulduğu için veritabanı bu güncellemeleri alamadı ve pasif kalarak drift oluşturdu.

## Karar: mes.work_orders Current-State Mirror
MVP (Minimum Viable Product) aşaması için `mes.work_orders` tablosunun bir **Current-State Mirror (Güncel Durum Aynası)** olarak kabul edilmesine karar verilmiştir.

## Status Alanının Anlamı
- `mes.work_orders.status` alanı, runtime JSON'daki ilgili iş emrinin **en güncel** durumunu yansıtmalıdır.
- İş emri durum geçişleri (örn: `queued` -> `active` -> `completed`) runtime üzerinde gerçekleştikçe, veritabanındaki karşılık gelen satır da güncellenmelidir.

## Neden Import/Master Snapshot Olarak Bırakılmadı?
- Eğer veritabanı sadece ilk import anındaki durumu (snapshot) korusaydı, MES Web bileşenlerinin iş emirlerinin güncel tamamlanma durumlarını takip etmesi zorlaşacaktı.
- Tablonun güncel mirror olarak tasarlanması, ileride veritabanı okumaları (DB Read) etkinleştirildiğinde MES sisteminin tutarlı bir şekilde çalışabilmesi için gereklidir.
- Kod tabanındaki mevcut UPSERT yapısı da (`ON CONFLICT DO UPDATE SET status = EXCLUDED.status`) bu güncel ayna tasarımını desteklemektedir.

## Work Order Events/History İçin Gelecek Notu
- İş emirlerinin durum geçişlerinin tarihçesini (durum değişiklik zamanları, geçmiş durumlar vb.) takip etmek için ayrı bir tarihçe tablosunun (`mes.work_order_events` veya `status_history`) oluşturulması planlanmaktadır.
- MVP sonrasında, raporlama ve OEE analizlerinin doğruluğunu artırmak amacıyla bu tarihçe modeli ayrıca değerlendirilecektir.

## E2B Controlled Resync Sonucu
E2A politika kararları doğrultusunda, veritabanında oluşan drift'in giderilmesi için E2B fazında kontrollü resync işlemi yapılmıştır:
- **Alınan Yedek:** `data\db_backups\mes_postgres_20260608-172057.sql` adıyla veritabanı yedeği alınmıştır.
- **Başlangıç Durumu:** 5 iş emrinde status drift mevcuttu.
- **Uygulama Yöntemi:** `mirror_work_orders_to_db.py` scripti tek seferlik (one-off) container kullanılarak çalıştırılmıştır.
- **Uygulama Sonucu:** `inserted=0, updated=6` (tüm 6 iş emri veritabanında güncellendi).
- **Mükerrerlik Kontrolü:** Mükerrer (duplicate) kayıt oluşmamıştır.
- **Resync Sonrası Verify Durumu:** E2B apply sonrası verify scripti tamamen temiz döndü:
  - `matched_external_refs=6`
  - `missing_in_db=0`
  - `extra_in_db=0`
  - `changed_or_suspicious=0`
  - `status matched=6 changed=0`
- **Uygulama Sağlığı:** MES Web health kontrolünde `200 OK` dönmüştür, sistem kararlıdır.
- **Çalışma Parametreleri:** Runtime DB flag'leri (`MES_WEB_DB_ENABLED` ve `MES_WEB_DB_MIRROR_WORK_ORDERS`) false/false olarak kalmıştır. `.env`, kod, veritabanı migration'ları ve docker compose dosyalarında herhangi bir değişiklik yapılmamıştır.

## Güvenlik Sınırları
- **Source-of-truth geçişi değildir:** Bu karar ve senkronizasyon çalışması MES sisteminin ana veri kaynağını veritabanına taşımaz. Ana veri kaynağı hâlâ JSON/Excel/FERP dosyalarıdır.
- **Runtime DB read yoktur:** Uygulama çalışma zamanında iş emri durumu sorgularken veritabanına başvurmaz.
- **JSON/Excel/FERP/MQTT akışı korunur:** Mevcut entegrasyonlar ve veri akış kanalları tamamen izole edilmiş ve korunmuştur.
- **Runtime flags normalde false kalır:** Canlı çalışma flag defaultları kapalı tutulmaktadır.
- **Controlled sync backup + one-off apply ile yapılmalıdır:** Olası drift giderme işlemleri her zaman DB backup alınarak ve kontrollü script apply çalıştırılarak yapılmalıdır.

## Sonraki Faz Önerisi
- `vision_events` veya `oee_snapshots` gibi diğer OEE olay ve durum tabloları için mirror ve dry-run analizlerini başlatmak.
