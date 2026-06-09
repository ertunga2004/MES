# F2B Production Completions Dry-Run Hook

## 1. Purpose
Bu dokümanın amacı, tamamlanan (completed) üretim loglarının (`mes.production_completions`) gerçek PostgreSQL yazma (live hook) aşaması olan F2C öncesinde diagnostic / test amaçlı `dry-run` mekanizmasının kurulumunu detaylandırmaktır.

## 2. Claude Gate Review Decision
Claude Gate Review doğrultusunda, DB Write işlemlerinin henüz güvenli (live) duruma geçirilmemesine ve aradaki `routing` mekanizmasının `dry-run` log üreterek analiz edilmesine karar verilmiştir. Blocker bulunmamaktadır.

## 3. Hook Location
Hook fonksiyonu (`_dry_run_production_completion_hook`), `mes_web/oee_state.py` içerisinde, parça work_order'a veya inventory'ye yönlendirildikten (`_route_completed_item_to_work_orders`) hemen sonra, ancak `return True` ile fonksiyon bitmeden önce çalışmaktadır.

## 4. Flag Conditions
Dry-run diagnostic logları yalnızca şu üç şart sağlandığında çalışır:
- `MES_WEB_DB_ENABLED=true`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN=true`
- `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=false`
Eğer `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS=true` (live) ise sistem DB write yapmayı bekler, ancak bu F2B fazı olduğundan yazma yapılmayacağı için sadece WARNING logu üretir.

## 5. Diagnostic Payload
Log formatı `[DRY_RUN:production_completions]` önekiyle (prefix) şu çıktıları üretir:
- `status`: Kaydın DB'ye atılabilirlik durumu (örn. APPLY_SAFE, OFF_ORDER)
- `item_id`: Tamamlanan kaydın ID'si
- `order_id`: Eşleşen iş emri ID'si (veya yoksa boş)
- `external_ref`: DB'deki partial unique index (natural_key) olarak eklenecek aday (`order_id_item_id`)
- `classification`: GOOD / REWORK / SCRAP vb.
- `completed_at`: Bitiş zamanı damgası
- `inventoryAction`: İş emri dışında depoya alma durumu (scrap_excluded vb.)
- `work_order_match_key`: Eşleşme anahtarı

## 6. OFF_ORDER / APPLY_SAFE Policy
- **APPLY_SAFE:** Kayıt bir `order_id`, `item_id` ve `completed_at` içeriyorsa.
- **OFF_ORDER:** Kayıt bir iş emriyle (`order_id`) eşleşmiyorsa, DB'ye loglanmaz. Diagnostic ekranına OFF_ORDER basar.

## 7. No-DB-Write Guarantee
- F2B kapsamında kod kesinlikle DB modüllerini import etmez.
- `safe_db_write` fonksiyonu **çağrılmaz.**
- `psycopg` kullanılmaz.
- SQL syntax barındırmaz.

## 8. Test Plan
- `py_compile` ile syntax doğrulandı.
- Mevcut `production_completions` mirror count 8 olarak stabil kaldı.
- `safe_db_write`, `INSERT`, `UPDATE` pattern taramaları negatif (temiz) çıktı.
- `health` 200 OK döndü.

## 9. F2C Entry Criteria
Bir sonraki canlı hook fazı (F2C) için ön koşullar:
- Bu dry-run uygulamasının log çıktılarında `status=APPLY_SAFE` formatının tam ve duplicate-free olarak gözlemlenmesi.
- `oee_state.py` içine `safe_db_write` importunun güvenli eklenebileceğinin onaylanması.

## 10. Things Not To Do
- "Production Count" varsayımı (topic tabanlı loglama) bu noktada tamamen dışlanmıştır.
- `db_enabled=false` iken log üretmekten kaçınılmıştır.
- Exception durumları ana `_complete_runtime_item` akışını kesinlikle bloklamayacaktır (try/except wrapper mevcuttur).

## 11. Next Recommended Step
Bu dokümanın oluşturulması ve oee_state.py üzerindeki değişikliğin kaydedilmesi sonrası, **F2B commit/push** işlemi yapılıp F2C öncesi hazırlık kapatılmalıdır.
