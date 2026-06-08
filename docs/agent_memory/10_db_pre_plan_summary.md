# DB Pre Plan Summary

Kaynak klasör:

```text
docs/db_pre_plan
```

Bu dosyalar taşınmadı veya kopyalanmadı; yalnızca okunup özetlendi. İçerikleri nihai karar değil, mimari kaynakça ve ön analiz olarak ele alınmalıdır.

Okunan dosyalar:

- `Agent_Memory_Knowledge_Database_Detayli_Tasarim.xlsx`
- `Bu sistem için tek bir veri tabanı yeterli olmaz.docx`
- `Data_Warehouse_BI_Database_Detayli_Tasarim.xlsx`
- `Engineering_Master_Data_Database_Detayli_Tasarim.xlsx`
- `ERP_Integration_Database_Detayli_Tasarim (1).xlsx`
- `Event_Altyapisi_Detayli_Tasarim.xlsx`
- `Manufacturing_Master_Data_Database_Detayli_Tasarim.xlsx`
- `MES_Operational_Database_Detayli_Tasarim.xlsx`
- `Quality_Management_Database_Detayli_Tasarim.xlsx`
- `Redis_Cache_Detayli_Tasarim.xlsx`
- `Search_Full_Text_Arama_Database_Detayli_Tasarim.xlsx`
- `Time_Series_Database_Detayli_Tasarim.xlsx`
- `Traceability_Database_Detayli_Tasarim.xlsx`

Dosya bazlı kısa özet:

| Dosya | Amaç | MES PostgreSQL transition ilişkisi |
|---|---|---|
| Agent Memory / Knowledge DB | Ajan belleği, RAG, retrieval, citation, tool memory, feedback ve governance. | Antigravity/agent memory klasörü için uzun vadeli bilgi yönetimi fikrini destekler; mevcut MES DB scope dışında. |
| Tek veri tabanı yeterli olmaz.docx | Engineering, ERP, MES, time-series, quality, BI, document ve agent data ayrımını savunur. | Bugünkü yaklaşımı destekler: MVP PostgreSQL ile başlar ama domainler kademeli ayrılır. |
| Data Warehouse / BI | OEE, KPI, duruş, kalite, maliyet ve production fact/dimension modeli. | `oee_snapshots`, production facts ve ileride BI martları için kaynak fikir. |
| Engineering Master Data | Ürün, parça, EBOM, revizyon, teknik doküman, ECR/ECO. | Mevcut Faz 4 kapsamı dışında; ileride master data domaini olabilir. |
| ERP Integration | ERP/FERP üretim emri, stok, feedback, integration error/retry/outbox. | `ferp_import_batches` ve `ferp_export_outbox` tablolarıyla örtüşür. |
| Event Altyapısı | Event, outbox/inbox, retry, event log ve idempotency yaklaşımı. | Mirror write ve ileride FERP/outbox olay modeli için faydalı. |
| Manufacturing Master Data | MBOM, BOP, operasyon, iş merkezi, makine, standart süre. | `stations`, `maintenance_steps`, operation/work center master data için kaynak. |
| MES Operational DB | Üretim emirleri, operasyon logları, duruş, gerçekleşme ve saha kayıtları. | Bugünkü `mes.work_orders`, `work_order_events`, `production_completions`, `downtime_events` ile en doğrudan örtüşen ön plan. |
| Quality Management | Kalite planı, inspection, measurement, nonconformance, disposition. | `quality_overrides` ve ileride kalite kayıtları mirror tasarımı için kaynak. |
| Redis Cache | Aktif emir, makine status, session, dashboard cache ve TTL politikaları. | Şimdilik ertelendi; Redis eklenmeyecek. |
| Search / Full-Text | Search index, indexed documents/entities, ACL ve relevance. | Şimdilik ertelendi; search katmanı source-of-truth değildir. |
| Time-Series DB | Makine sinyalleri, cycle, alarm, enerji, aggregation. | MQTT/ESP32/bridge ve OEE trend verisi için ileride değerlendirilebilir; şu an TimescaleDB yok. |
| Traceability DB | Lot, seri, tüketim, operation trace, barcode/RFID. | İleride work order completion ve FERP/quality bağlantıları için kaynak; Faz 4 scope dışında. |

Bugünkü uygulanan foundation ile örtüşen noktalar:

- Work orders operasyonel MES verisinin ilk mirror hedefidir.
- JSONB `payload` ve `metadata` kullanımı, detaylı domain model kesinleşmeden veri şekillerini kanıtlamaya uygundur.
- Outbox/inbox ve idempotency fikirleri `ferp_export_outbox`, `ferp_import_batches` ve `ON CONFLICT` upsert yaklaşımıyla uyumludur.
- OEE, downtime, quality, vision ve device session tabloları, ön analizlerdeki MES operational, time-series, quality ve traceability yönleriyle ilişkilidir.

Şimdilik ertelenen noktalar:

- Çoklu database ayrımı.
- Redis, search, time-series özel altyapısı.
- BI/DW yıldız şema.
- Engineering/Manufacturing/Quality master data'nın tam DDL modeli.
- ERP/FERP gerçek outbox processing.
- Agent memory/RAG database.

İleride değerlendirilecek öneriler:

- Önce PostgreSQL içinde `mes` schema mirror kapsamı genişletilmeli.
- Sonra FERP import/export metadata ve outbox netleştirilmeli.
- OEE snapshot ve device/vision event mirror doğrulanmalı.
- Ancak veri hacmi ve sorgu ihtiyacı kanıtlanırsa time-series, BI, search veya cache katmanı gündeme alınmalı.

Bu ön çalışmalar nihai karar değil; Antigravity için mimari kaynakça ve fikir havuzudur.
