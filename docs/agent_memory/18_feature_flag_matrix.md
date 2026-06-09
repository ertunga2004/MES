# Feature Flag Matrix

## 1. Purpose
Bu doküman, MES sisteminin PostgreSQL source-of-truth geçişinde kullanılacak olan Feature Flag'lerin (özellik anahtarları) listesini, varsayılan değerlerini, geçiş fazlarını ve bağımlılıklarını detaylandırmak için oluşturulmuştur. Amaç, aşamalı geçişi güvenli (fail-open) bir şekilde yönetmektir.

## 2. Current Flags
Mevcut sistemde şu an sadece iki flag tanımlıdır:
- `MES_WEB_DB_ENABLED`: (Default: `false`) Uygulamanın veritabanı işlemlerini tamamen açıp kapatır.
- `MES_WEB_DB_MIRROR_WORK_ORDERS`: (Default: `false`) Work orders verilerinin mirror edilmesi denemeleri için eklenmiş erken aşama bir flag'dir.

## 3. Proposed Flag Groups
Planlanan geçiş adımlarını güvenle uygulayabilmek için yeni eklenecek flag'ler şu gruplara ayrılmaktadır:
- **DB master / connection flags**: Global bağlantı, fail-open politikasını ve loglamayı yönetir.
- **DB write hook flags**: Canlı üretim verilerinin, olay gerçekleştiği anda PostgreSQL'e (insert/upsert) yazılıp yazılmayacağını yönetir.
- **DB read/shadow-read flags**: Uygulamanın veritabanından veri okumasını veya arka planda eski/yeni yapıyı karşılaştırmasını yönetir.
*(Not: Migration ve DB tablo şeması hardening işlemleri ayrı script/SQL fazlarında yapılacak olup, flag ile runtime üzerinden yönetilmez.)*

## 4. Proposed Flags Table

| Flag name | Default | Phase introduced | Purpose | DB write? | DB read? | Runtime behavior change? | Rollback action | Depends on | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `MES_WEB_DB_ENABLED` | `false` | F1B | Global switch for DB integration | No | No | No | Set `false` | None | Master switch. If false, all other flags are ignored. |
| `MES_WEB_DB_FAIL_OPEN` | `false` | F1B | Ensure DB errors don't crash JSON/MQTT flow | No | No | Yes | Set `false` | `MES_WEB_DB_ENABLED` | Critical for safety |
| `MES_WEB_DB_LOG_FAILURES` | `false` | F1B | Log detailed DB connection/write errors | No | No | No | Set `false` | None | Debug only |
| `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS_DRY_RUN` | `false` | F2B | Log product completion attempts without DB write | No | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Safe verification |
| `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS` | `false` | F2C | Live hook (UPSERT) for product completions | Yes | No | No | Set `false` | `MES_WEB_DB_ENABLED`, F1F | Wait for F1F UNIQUE migration |
| `MES_WEB_DB_HOOK_VISION_EVENTS_DRY_RUN` | `false` | F3A | Log vision events without DB write | No | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Uses `apply_vision_event` payload |
| `MES_WEB_DB_HOOK_VISION_EVENTS` | `false` | F3B | Live hook (UPSERT) for vision events | Yes | No | No | Set `false` | `MES_WEB_DB_ENABLED`, F1F | Wait for F1F UNIQUE migration |
| `MES_WEB_DB_HOOK_OEE_SNAPSHOTS_DRY_RUN` | `false` | F4B | Log OEE snapshots without DB write | No | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Safe verification |
| `MES_WEB_DB_HOOK_OEE_SNAPSHOTS` | `false` | F4D | Live hook for OEE snapshots | Yes | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Time-series append |
| `MES_WEB_DB_HOOK_DOWNTIME_EVENTS` | `false` | F5 | Live hook for downtime tracking | Yes | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Deferred table |
| `MES_WEB_DB_HOOK_MAINTENANCE_RECORDS` | `false` | F5 | Live hook for maintenance logs | Yes | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Deferred table |
| `MES_WEB_DB_HOOK_QUALITY_OVERRIDES` | `false` | F5 | Live hook for quality overrides | Yes | No | No | Set `false` | `MES_WEB_DB_ENABLED` | Deferred table |
| `MES_WEB_DB_SHADOW_READ_WORK_ORDERS` | `false` | F7A | Compare DB read with JSON read in background | No | Yes | No | Set `false` | `MES_WEB_DB_ENABLED` | Verifies read parity |
| `MES_WEB_DB_READ_WORK_ORDERS` | `false` | F7B | Use DB as source-of-truth for work orders | No | Yes | Yes | Set `false` | F7A success | Changes runtime source |
| `MES_WEB_DB_SHADOW_READ_DASHBOARD` | `false` | F8 | Compare DB reporting read with existing logic | No | Yes | No | Set `false` | `MES_WEB_DB_ENABLED` | Reporting verification |
| `MES_WEB_DB_READ_DASHBOARD` | `false` | F8 | Use DB as source for Dashboard metrics | No | Yes | Yes | Set `false` | Shadow dashboard success | Transitioning UI reads |
| `MES_WEB_DB_STRICT_TIMESTAMP_GUARD` | `false` | F6 | Reject events with timestamps in future/far past | No | No | Yes | Set `false` | `MES_WEB_DB_ENABLED` | Enforce data integrity |
| `MES_WEB_DB_ALLOW_FUTURE_EVENTS` | `false` | N/A | Bypass timestamp checks completely | No | No | Yes | Set `false` | `MES_WEB_DB_STRICT_TIMESTAMP_GUARD` | **FORBIDDEN / LAB ONLY** |

## 5. Default Policy
- Tüm yeni flagler default olarak `false` olmalıdır.
- `MES_WEB_DB_ENABLED` flag'i `false` ise, diğer tüm DB flag'leri etkisiz kalmalıdır.
- Hiçbir flag aktifleştirilmediğinde runtime behavior'da (mevcut akışta) en ufak bir değişiklik olmamalıdır.
- Production (canlı) deployment'larda varsayılan değerler asla `true` olmayacaktır.

## 6. Dependency Rules
- Live hook flag'leri aktif olsa bile, veri yazılabilmesi için ön koşul `MES_WEB_DB_ENABLED=true` olmasıdır.
- Production Completions ve Vision Events için canlı yazma hook'ları (F2C ve F3B), kesinlikle **F1F UNIQUE(external_ref)** migration işlemi tamamlandıktan sonra aktif edilebilir.
- Read flag'lerinin (`_READ_`) aktif edilmesi, sadece `_SHADOW_READ_` fazının başarıyla ve sıfır tutarsızlıkla (clean result) tamamlandığının kanıtlanmasını gerektirir.
- Final source-of-truth switch işlemi için tüm doğrulama scriptlerinin (verify) çoklu döngüde hatasız (multi-run verify clean) çıkması zorunludur.

## 7. Rollback Rules
- Herhangi bir flag'de problem çıkması durumunda, ilgili flag `false` yapılarak anında anlık geri dönüş (rollback) sağlanabilir.
- `MES_WEB_DB_ENABLED` kapatıldığı anda, tüm sistem SQL veritabanından izole olup orijinal MES JSON/Excel/MQTT akışına geri dönmelidir.
- Veritabanı çökmesi/timeout durumlarında bile sistem çakılmamalı, Fail-open politikası korunmalıdır (`MES_WEB_DB_FAIL_OPEN` ile garantilenmelidir).

## 8. Things Not To Do
- `.env` veya docker konfigürasyonlarında varsayılan olarak herhangi bir flag `true` **yapılmamalıdır**.
- Yazma (hook) flag'leri ile okuma (read) flag'leri aynı geçiş fazında kesinlikle **açılmamalıdır**.
- Veritabanı şema güncellemeleri (migrations) flag'lerle gizlenmemeli, bağımsız migration scriptleriyle yönetilmelidir.
- `allow-future` (gelecekteki olay tarihlerini bypass eden) flag, bir production (canlı ortam) flag'i olarak **önerilmemeli**, dokümanlarda sadece laboratuvar veya hata ayıklama amaçlı olduğu belirtilmelidir.
- Varolan mirror ve verify scriptleri kod tabanından **silinmemelidir**.
