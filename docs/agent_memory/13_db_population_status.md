# Controlled DB Population Status Report

## Amaç
Bu doküman, MES PostgreSQL geçişi kapsamında veritabanına aktarılan verilerin mevcut durumunu, doğrulama (verify) sonuçlarını, veri bütünlüğünü ve ertelenen/henüz doldurulmayan tabloların durumunu kayıt altına almak amacıyla oluşturulmuştur.

## Genel Bilgiler
* **Test Tarihi:** 2026-06-08
* **Runtime Ortamı:** Portable Docker
* **PostgreSQL Schema:** `mes`

---

## Veri Doldurulan Tablolar (Verified Populated Tables)

### 1. `mes.work_orders`
* **Kayıt Sayısı:** 6
* **Durum:** Başarılı (E2B kontrollü resync ile status drift temizlendi, verify temiz).
* **Doğrulama Sonucu:** 
  * `json_work_order_count`: 6
  * `db_work_order_count`: 6
  * `matched_external_refs`: 6
  * `missing_in_db`: 0
  * `extra_in_db`: 0
  * `changed_or_suspicious`: 0
  * `status matched`: 6, `changed`: 0
  * E2B kontrollü resync öncesindeki 5 kayıttaki status drift tamamen temizlenmiş ve veritabanındaki durumlar güncel runtime JSON state'iyle birebir senkronize edilmiştir.


### 2. `mes.production_completions`
* **Kayıt Sayısı:** 7
* **Durum:** Başarılı (Kontrollü apply ve one-off container doğrulaması tamamlandı).
* **Doğrulama Sonucu:**
  * `json_apply_safe_count`: 7
  * `db_production_completion_count`: 7
  * `missing_in_db`: 0
  * `extra_in_db`: 0
  * `duplicate_external_refs`: 0
  * `changed_or_suspicious`: 0
  * Bütün `external_ref` natural key'leri (`order_id` + `_` + `item_id`) benzersizdir. `order_id` veya `completed_at` bilgisi eksik olan hiçbir kayıt (off-order completions dahil) DB'ye yazılmamış ve başarıyla skip edilmiştir.

---

## Boş / Henüz Doldurulmayan Tablolar (Empty / Not Yet Populated)

* **`mes.device_sessions`:** Apply işlemi ertelendi. Runtime JSON state'indeki `deviceSessions` kaydında benzersiz bir `sessionId`, `connectedAt` veya `startedAt` bilgisi bulunmamaktadır. `lastSeenAt` volatile (oynak) olduğundan natural key olarak kullanılamaz. Gerçek bir session identity çözümü tasarlanana kadar aktarım yapılmayacaktır.
* **`mes.vision_events`:** Ham (raw) olay verisi ile özet (summary) verisi arasındaki ayrım henüz netleşmediği için analizi beklemektedir.
* **`mes.oee_snapshots`:** Hangi snapshot kaynağının kullanılacağı (dosya bazlı mı yoksa hesaplanmış veri mi) henüz kararlaştırılmamıştır.
* **`mes.downtime_events`:** Runtime loglarında henüz örnek duruş (downtime) olayı bulunmamaktadır.
* **`mes.maintenance_records`:** İş analizi henüz tamamlanmamıştır.
* **`mes.quality_overrides`:** Runtime üzerinde henüz kalite iptali (quality override) örneği oluşmamıştır.

---

## Tekrarlı Kayıt Kontrolü (Duplicate Checks)
Veritabanında `psql` üzerinde doğrudan yapılan sorgularda herhangi bir mükerrer kayıt bulunamamıştır:
* `mes.work_orders` tablosunda mükerrer `order_id`: **0**
* `mes.production_completions` tablosunda mükerrer `external_ref`: **0**

---

## Mevcut Güvenli Durum (Current Safe State)
Veritabanının canlı sisteme etkisi tamamen sınırlandırılmış durumdadır:
* `MES_WEB_DB_ENABLED=false` (Default pasif)
* `MES_WEB_DB_MIRROR_WORK_ORDERS=false` (Default pasif)
* **MES Web Health:** `200 OK` (Uygulama sağlıklı çalışıyor)

---

## Önemli Sınırlar (Boundaries)
1. **PostgreSQL henüz Source-of-Truth değildir:** Veritabanı sadece bir ayna (mirror/outbox) adayıdır.
2. **Runtime Akışı Korunmuştur:** Uygulama hâlâ JSON, Excel, FERP ve MQTT akışları üzerinden çalışmaktadır.
3. **DB Read Yoktur:** Uygulama çalışma zamanında PostgreSQL'den herhangi bir veri okumamaktadır.
4. **Otomatik Hook Yoktur:** `production_completions` için canlı runtime hook'u henüz etkinleştirilmemiştir.

---

## Sonraki Adımlar (Next Recommended Steps)
1. `vision_events` veya `oee_snapshots` tablolarının veri modellerini ve aktarım planlarını analiz etmek.
2. Runtime tarafında gerçek `sessionId` üretimi tasarlanana kadar `device_sessions` aktarımını askıda tutmaya devam etmek.
