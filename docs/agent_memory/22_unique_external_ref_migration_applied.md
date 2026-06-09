# UNIQUE(external_ref) Migration Applied

## 1. Purpose
Bu dokümanın amacı, F1F-B aşamasında `mes.production_completions` ve `mes.vision_events` tablolarına uygulanan `UNIQUE(external_ref)` partial index migration'ının başarılı şekilde tamamlandığını ve mevcut sistem bütünlüğünün korunduğunu kalıcı olarak kayıt altına almaktır.

## 2. Applied Migration
- **Uygulanan SQL:** `db/migrations/002_unique_external_refs.sql`
- **İçerik:** `mes.production_completions` ve `mes.vision_events` tabloları için partial unique index oluşturulmuştur.

## 3. Backup Reference
- **Yedek Dosyası:** `data\db_backups\mes_postgres_20260609-132110.sql`
- Sistem migration öncesi güvenli bir şekilde yedeklenmiştir.

## 4. Pre-Migration State
- `mes.production_completions` count: 8
- `mes.vision_events` count: 43
- Null veya blank `external_ref`: 0
- Duplicate `external_ref`: 0

## 5. Applied Indexes
Aşağıdaki indeksler başarıyla şemaya eklenmiştir ve aktiftir:
- `ux_mes_production_completions_external_ref`
- `ux_mes_vision_events_external_ref`
- **Koşul (WHERE):** `external_ref IS NOT NULL AND btrim(external_ref) <> ''`

## 6. Post-Migration Verification
Migration uygulandıktan sonra sistem stabilitesi doğrulanmıştır:
- Tablo count'larında değişiklik yoktur (6, 8, 43 stabil).
- Duplicate veya null `external_ref` ihlali oluşmamıştır (0).
- `verify_production_completions_db_mirror.py`: Clean (missing=0, extra=0, dup=0, changed=0).
- `verify_vision_events_db_mirror.py`: Clean (missing=0, extra=0, dup=0, changed=0).
- Veri kaybı veya bütünlük bozulması yaşanmamıştır.

## 7. Runtime Safety State
- **MES Health:** 200 OK (Sistem ayakta).
- **Runtime Flags:**
  - `MES_WEB_DB_ENABLED=false`
  - `MES_WEB_DB_MIRROR_WORK_ORDERS=false`
- Uygulama çalışırken arka planda schema değişikliği yapılmıştır, ancak kod henüz veritabanını kullanamamaktadır.

## 8. Rollback Status
- **Gerekmedi.**
- İşlem sıfır hatayla uygulandığı için `db/migrations/002_unique_external_refs_rollback.sql` komutlarına başvurulmamıştır.

## 9. What This Enables
- `production_completions` ve `vision_events` tabloları artık event idempontency özelliğine sahiptir.
- Aynı olayın yanlışlıkla çift yazılmasını (duplicate) veritabanı seviyesinde önleyecek güçlü bir kısıtlama (constraint) oluşturulmuştur.
- Güvenli bir Canlı Hook (Live Hook) entegrasyonu için veritabanı altyapısı hazır hale getirilmiştir.

## 10. What This Does NOT Enable Yet
- **Bu migration live hook açmaz.** Sistem hâlâ var olan log mekanizması üzerinden çalışmaktadır.
- **Bu migration DB read transition yapmaz.** Uygulama hâlâ JSON/Excel okumaya devam etmektedir.
- **PostgreSQL hâlâ full source-of-truth değildir.** Yalnızca bir yansıma (mirror) ve hazırlık konumundadır.
- Live hook entegrasyonu için F2A/F2B/F2C ve F3A/F3B fazları adım adım ilerletilmelidir.
- Runtime flag'leri `false` konumunda kalmıştır.

## 11. Next Recommended Step
- **F1F-B Commit/Push:** Bu dokümanın repoya gönderilmesi.
- **F2A:** `production_completions` event semantics analysis refresh.
- Ardından **F2B:** No-op/dry-run `production_completions` hook tasarımı.
- *Not:* Live hook F2C aşamasına kadar devreye alınmayacaktır.
