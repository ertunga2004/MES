# Controlled DB Population Status Report (E5F Checkpoint)

## Amaç
Bu doküman, MES PostgreSQL geçişi kapsamında veritabanına aktarılan verilerin mevcut durumunu, doğrulama (verify) sonuçlarını, veri bütünlüğünü ve ertelenen/henüz doldurulmayan tabloların durumunu kayıt altına almak amacıyla oluşturulmuştur.

## Genel Bilgiler
* **Test Tarihi:** 2026-06-09
* **Runtime Ortamı:** Portable Docker
* **PostgreSQL Schema:** `mes`

---

## Doğrulanan Veri Doldurulan Tablolar (Validated Populated Tables)

### 1. `mes.work_orders`
* **Kayıt Sayısı:** 6
* **Durum:** Başarılı (E2B kontrollü resync ile status drift temizlendi).
* **Verify:** Clean (6 kayıt)

### 2. `mes.production_completions`
* **Kayıt Sayısı:** 8
* **Durum:** Başarılı (Kontrollü apply ve idempotency testi tamamlandı).
* **Verify:** Clean (8 kayıt)

### 3. `mes.vision_events`
* **Kayıt Sayısı:** 43
* **Durum:** Başarılı (Excel backfill üzerinden kontrollü apply tamamlandı, idempotency testi geçti).
* **Verify:** Clean (43 kayıt)
  * `missing_in_db`: 0, `extra_in_db`: 0, `duplicate_external_refs`: 0, `changed_or_suspicious`: 0

---

## Boş / Ertelenen Tablolar (Empty / Deferred Tables)

Aşağıdaki tablolara henüz veri aktarımı yapılmamış veya analiz sürecindedir:
* **`mes.device_sessions`:** Stable session identity yok. Gerçek session çözümü tasarlanana kadar ertelendi.
* **`mes.oee_snapshots`:** Snapshot source policy (dosya vs. db vs. hesaplanmış) henüz belirlenmedi.
* **`mes.downtime_events`:** Runtime üzerinde henüz örnek event yok, analiz bekliyor.
* **`mes.maintenance_records`:** İş analizi henüz tamamlanmadı.
* **`mes.quality_overrides`:** Örnek event yok, analiz bekliyor.

---

## Tekrarlı Kayıt Kontrolü (Duplicate Checks)
Veritabanında doğrudan yapılan `psql` GROUP BY/HAVING COUNT sorgularında tekrarlı (duplicate) kayıt bulunmamıştır:
* `mes.work_orders`: 0 duplicate
* `mes.production_completions`: 0 duplicate
* `mes.vision_events`: 0 duplicate

---

## Doğrulama Script Sonuçları (Verify Script Results)
Tüm tabloların read-only Python scriptleri temiz döndü (idempotent senaryolar doğrulandı, missing/extra=0). (Not: Canlı runtime üzerindeki anlık drift ihtimalleri dışında ana snapshot verileri tamamen denktir.)

---

## Mevcut Güvenli Durum (Runtime Safe State)
Veritabanının canlı sisteme etkisi tamamen sınırlandırılmış durumdadır:
* `MES_WEB_DB_ENABLED=false` (Default pasif)
* `MES_WEB_DB_MIRROR_WORK_ORDERS=false` (Default pasif)
* **MES Web Health:** `200 OK`

---

## Önemli Sınırlar (Current Boundary)
1. **PostgreSQL mirror/population doğrulandı:** Veritabanı sadece 3 ana grupta kontrollü dolduruldu.
2. **Runtime DB Read Yok:** Canlı uygulama PostgreSQL'den veri okumaz.
3. **Source-of-Truth Geçişi Yok:** Sadece ayna (mirror/outbox) olarak beklemektedir.
4. **Mevcut Akış Korunuyor:** JSON/Excel/FERP/MQTT akışları ana doğrulanmış kaynaklardır.

---

## Sonraki Adımlar (Next Recommended Work)
1. Sıradaki teknik kararı vermek: Yeni tablo analizine mi (örn. `oee_snapshots`) devam edilecek, yoksa var olan dolu tablolar üzerinden *runtime hook/read transition* (okuma geçişi) mi denenecek?
2. `downtime_events` ve `quality_overrides` için örnek data / event oluşturmak.
3. Raw MQTT stream'ini DB veya Excel dışında canlı bir worker ile ele almayı tasarlamak.
