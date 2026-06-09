# External Ref Compatibility Report

## 1. Purpose
Bu dokümanın amacı F1F UNIQUE(external_ref) migration öncesi canlı veritabanında (PostgreSQL) oluşabilecek kopya (duplicate) veya boş (null/blank) kayıt risklerini tespit etmektir. Uyumluluk denetimi tamamen read-only SELECT sorgularıyla gerçekleştirilmiştir.

## 2. Runtime Safety State
- **Health sonucu:** 200 OK (Mevcut sistemin ayakta olduğu doğrulandı)
- **MES_WEB_DB_ENABLED:** false
- **MES_WEB_DB_MIRROR_WORK_ORDERS:** false
- *Not:* Bu fazda hiçbir şekilde INSERT/UPDATE/DELETE/ALTER işlemi gerçekleştirilmemiştir. Sadece `mes` yetkilisiyle read-only (SELECT) sorgular atılmıştır.

## 3. Table Counts
E5F ve F1D sayımlarına tam uyum gözlemlendi:
| Table | Populated Count |
| --- | --- |
| `mes.work_orders` | 6 |
| `mes.production_completions` | 8 |
| `mes.vision_events` | 43 |
| `mes.device_sessions` | 0 |
| `mes.oee_snapshots` | 0 |
| `mes.downtime_events` | 0 |
| `mes.maintenance_records` | 0 |
| `mes.quality_overrides` | 0 |

## 4. production_completions Compatibility
- **count:** 8
- **null/blank external_ref count:** 0
- **duplicate external_ref result:** 0 adet kopya kayıt var.
- **sample row notes:** Loglar incelendiğinde her `completed_at` adımına karşılık gelen bir unique order_id + item_id hash tabanlı referansın sorunsuz yazıldığı görüldü.
- **UNIQUE(external_ref) migration readiness:** PASS

## 5. vision_events Compatibility
- **count:** 43
- **null/blank external_ref count:** 0
- **duplicate external_ref result:** 0 adet kopya kayıt var.
- **sample row notes:** Excel backfill senaryosuyla yüklenen verilerde oluşturulan tüm external_ref'ler tamamen tekil.
- **UNIQUE(external_ref) migration readiness:** PASS

## 6. work_orders Key Check
- **duplicate order_id result:** 0 adet kopya kayıt var.
- **duplicate external_ref result:** 0 adet kopya kayıt var.
- **current-state mirror policy note:** Zaten `ux_mes_work_orders_order_id` adında bir kısıtlama mevcuttur. Upsert mantığı başarıyla çalışmaktadır ve hiçbir mükerrer order_id barındırmamaktadır.

## 7. Constraint / Index Observation
- **existing constraints summary:** `mes.work_orders` için order_id unique. Operatörler, istasyonlar ve hata kodları için kısıtlamalar bulunuyor.
- **existing indexes summary:** Tüm _pk kolonlarında btree primary key var. Ayrıca bazı _at (tarih) kolonlarında indeksler mevcuttur.
- **production_completions external_ref UNIQUE currently exists?:** No
- **vision_events external_ref UNIQUE currently exists?:** No

## 8. F1F Migration Readiness Decision
- **mes.production_completions UNIQUE(external_ref) migration ready mı?:** PASS (Hazır)
- **mes.vision_events UNIQUE(external_ref) migration ready mı?:** PASS (Hazır)
- Her iki tablo da tertemiz (0 null, 0 duplicate) olduğu için hiçbir data cleanup (veri temizliği) gerekmemektedir.
- **F1F migration adayları:**
  - `CREATE UNIQUE INDEX ux_mes_production_completions_external_ref ON mes.production_completions (external_ref);`
  - `CREATE UNIQUE INDEX ux_mes_vision_events_external_ref ON mes.vision_events (external_ref);`

## 9. Required F1F Safety Rules
- **Backup:** İşlemden önce DB backup (pg_dump) almak zorunludur.
- **Migration ayrı faz:** F1F başlı başına bağımsız bir script/aşama olarak koşulmalıdır.
- **Runtime hook aynı fazda yok:** Migration sırasında veya hemen peşine, sistem hook'a açılmamalı; önce doğrulanmalıdır.
- **Read transition aynı fazda yok:** Okuma fonksiyonları değiştirilmemelidir.
- **Verify scriptler:** Migration sonrası `verify_production_completions_db_mirror.py` ve `verify_vision_events_db_mirror.py` tekrar çalıştırılmalıdır.
- **Rollback:** Ters giden durumlarda index'i DROP edecek script/plan olmalıdır.
- **Docker down -v yok:** Mevcut 6/8/43 count'ları asla uçurulmamalıdır.

## 10. Things Not To Do
- Bu rapora dayanarak hemen F1F migration scriptini/dosyasını yazmaya başlama (komutu bekle).
- Canlı hook ekleme.
- DB yazma (write) yapma.
- external_ref dışında yeni bir key üzerinden constraint kurgulama.
- vision_track_id tabanlı constraint deneme (çünkü event_level tracking external_ref içindedir).

## 11. Next Recommended Step
Tüm readiness testleri (PASS) olduğu için veri temizliğine gerek yoktur.
**Sıradaki hedef:** F1F UNIQUE(external_ref) migration plan and migration script.
