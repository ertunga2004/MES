# Production Completions Event Semantics

## 1. Purpose
Bu belgenin amacı, `mes.production_completions` tablosunu canlı (live) hook mantığına entegre etmeden önce, üretim (completion) olayı semantiğini, verinin sistemde hangi noktada oluştuğunu ve hangi koşullarda veritabanına yazılmasının güvenli olduğunu analiz etmektir. Bu analiz, kod değiştirilmeden yalnızca mevcut script ve yapıların incelenmesiyle oluşturulmuştur.

## 2. Source Files Reviewed
- `mes_web/oee_state.py`
- `mes_web/mqtt_runtime.py`
- `scripts/mirror_production_completions_to_db.py`

## 3. Current DB State
- `mes.production_completions` tablosunda **8 adet kayıt** bulunmaktadır.
- Tabloda `external_ref` alanı üzerine F1F-B aşamasında **UNIQUE(external_ref)** partial index başarılı bir şekilde eklenmiştir.

## 4. Current Runtime Completion Flow
- **MQTT "production_count" adında bir raw topic BULUNMAMAKTADIR.** Sistem bu şekilde çalışmaz.
- Completion olayı, `mes_web/oee_state.py` içerisindeki `_complete_runtime_item` fonksiyonunda gerçekleşir.
- Bir parça (item) sensör veya kamera kararıyla final durumuna eriştiğinde `completed_at` atanır ve `queue_status` = `"completed"` olur.
- Hemen ardından `_route_completed_item_to_work_orders` çağrılarak parça ya aktif bir iş emrine (Work Order) bağlanır, ya da depoya/hurdaya (inventory/scrap_excluded) yönlendirilir.

## 5. Valid Completion Candidate Definition
Mevcut `scripts/mirror_production_completions_to_db.py` referans alındığında, bir kaydın **APPLY_SAFE** (DB'ye yazılabilir) kabul edilmesi için gerekenler:
1. Kaydın bir `item_id` veya extracted item id barındırması.
2. Bir `completed_at` timestamp'ine sahip olması.
3. Açıkça bir `order_id`'ye (iş emrine) bağlı olması.
Bu koşulların dışındaki (eksik veya iş emriyle eşleşmeyen) loglar SKIPPED durumuna düşmektedir.

## 6. Off-Order vs Work-Order-Bound Completion Policy
- **Work-Order-Bound:** İş emrine (aktif order'a) ait parçalar (`order_id` dolu) veritabanına loglanır.
- **Off-Order/Scrap:** İş emri olmadan tamamlanan (off_order_completion) veya direkt Scrap olan parçalar (`order_id` = None), mevcut SQL şema eşleşmesinde `external_ref` oluşturulamayacağı için (bkz. natural key) mirror script tarafından dışarıda bırakılır (SKIPPED_MISSING_ORDER_ID). Live hook mantığında da şimdilik `order_id` olmayan parçalar atlanmalıdır.

## 7. Natural Key / external_ref Policy
- Mirror script'e göre natural key: **`{order_id}_{item_id}`**
- `external_ref` kolonuna doğrudan bu key yazılır.
- **Uyumluluk:** F1F-B aşamasında kurulan `UNIQUE(external_ref)` kısıtlaması, `{order_id}_{item_id}` formatı ile %100 uyumludur. Bu key, hem order hem item seviyesinde kesin (deterministic) ve tekrarlanamaz (idempotent) özellik taşır.

## 8. Duplicate and Replay Risk Analysis
- `_complete_runtime_item` fonksiyonunun en başında `if item.get("completed_at"): return False` kontrolü vardır. Dolayısıyla bir parça zaten tamamlanmışsa tekrar completion transition'a sokulmaz. Bu, MQTT re-deliver durumlarını filtreler.
- Runtime state reload olduğunda (json dosyasından okunduğunda), okunan itemlar zaten `completed_at` dolgulu olarak geldiğinden tekrar live hook'u tetiklemezler.
- Buna rağmen fail-open (güvenli) bir wrapper yapısı kullanmak, veritabanına aynı key tekrar iletilmek istendiğinde (Unique Violation) backend'i çökertmeden yola devam edebilmek için hayati bir korumadır.

## 9. F2B Dry-Run Hook Recommendation
- Kod değişikliğinde `oee_state.py` içine direkt veritabanı yollamak yerine; `_complete_runtime_item` veya `_route_completed_item_to_work_orders` sonuna **dry-run** logları atacak bir no-op (işlevsiz) hook planlanmalıdır.
- **Feature Flags:**
  - `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=true`
  - `MES_WEB_DB_ENABLED=true`
- DB modülü çağrılıp sadece "Dry Run: Simulated insert for order_id_item_id" şeklinde konsol (veya application log) uyarısı üretilmeli, gerçek DB Write **yapılmamalıdır.**

## 10. F2C Live Hook Preconditions
F2C aşamasında bu hook'un gerçekten DB'ye yazabilmesi için gereken ön şartlar:
1. F1F UNIQUE index başarıyla tamamlanmış olmalı (Tamamlandı).
2. F2B Dry-Run safhasında incelenen logların temiz (gerçek senaryoda doğru veriyi basıyor) olduğu doğrulanmalı.
3. Yeni `safe_db_write` fonksiyonu (fail-open) kullanılarak, DB erişilemezse uygulamanın çökmesi engellenmeli.
4. Hook hata verse bile JSON state'ine yazılma (klasik akış) kesintiye uğramamalı.

## 11. Things Not To Do
- `production_count` adında bir topic var sayma; bu topic kodda bulunmuyor.
- `order_id` içermeyen off-order parçaları zorla veritabanına yazmaya kalkma (Mevcut mirror akışı da bunu engelliyor).
- Completion log ve itemsById mantığını ayrı ayrı loglayıp çift veri (duplicate) yaratma; yalnızca bir çıkış noktası (`_complete_runtime_item` başarısı sonrası) kullanılmalıdır.
- F2B Dry-Run denemeden doğrudan F2C Live Write açma.

## 12. Next Recommended Step
Bu analiz başarılı bir şekilde tamamlanmış ve `docs/agent_memory/23_production_completions_event_semantics.md` altına dokümante edilmiştir.
- **Sonraki Adım:** `F2A commit/push`
- **Sonraki Faz:** `F2B: no-op/dry-run production_completions hook tasarımı`.
