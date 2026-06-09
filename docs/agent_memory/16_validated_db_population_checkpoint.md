# Validated DB Population Checkpoint (E5F)

**Tarih:** 2026-06-09
**Aşama:** E5F

Bu doküman, MES sisteminin PostgreSQL'e geçişi sırasında kontrollü olarak doldurulan ve doğrulanan (verify clean) veritabanı tablolarının anlık durumunu özetler.

## Doğrulanan Tablolar (Populated & Verified)

Şu ana kadar 3 temel tablo Excel/JSON kaynaklarından okunarak `mes` veritabanına aktarılmış ve read-only scriptler ile doğrulanmıştır.

| Tablo Adı | Kayıt Sayısı | Durum | Doğrulama (Verify) |
| --- | --- | --- | --- |
| `mes.work_orders` | 6 | E2B kontrollü resync tamamlandı, status drift temizlendi. | Clean (Missing: 0, Extra: 0, Duplicate: 0) |
| `mes.production_completions` | 8 | Kontrollü apply tamamlandı. | Clean (Missing: 0*, Extra: 0, Duplicate: 0) |
| `mes.vision_events` | 43 | Excel backfill tamamlandı. | Clean (Missing: 0, Extra: 0, Duplicate: 0) |

*(Not: Üretim tamamlanma (production_completions) tarafındaki olası anlık driftler haricinde kaynak sistemle DB arasında tam tutarlılık gözlemlenmiştir.)*

## Ertelenen / Boş Tablolar

Henüz örnek verisi olmayan, analiz aşamasında olan veya session identity/source policy netleşmeyen tablolar:

1. `mes.device_sessions` (Stable key bekleniyor)
2. `mes.oee_snapshots` (Source policy belirlenmesi bekleniyor)
3. `mes.downtime_events` (Örnek data bekleniyor)
4. `mes.maintenance_records` (Analiz bekleniyor)
5. `mes.quality_overrides` (Örnek data bekleniyor)

## Sistem Sınırları

Şu anki doğrulanmış durumda:
- Veritabanına canlı (canlı akış üzerinden) yazma işlemi sadece feature-flag (`MES_WEB_DB_ENABLED=false`) arkasındadır.
- Okuma (DB Read) kesinlikle **yoktur**. 
- Source-of-truth hâlâ JSON, Excel ve MQTT akışlarıdır.

## Önerilen Sonraki Adımlar

- **Seçenek A:** Henüz doldurulmamış olan tabloların (örn. `oee_snapshots` veya FERP verileri) analizine devam etmek.
- **Seçenek B:** Doğrulanmış ve doldurulmuş olan bu 3 tablo (`work_orders`, `production_completions`, `vision_events`) için read-only / hybrid veritabanı okuma stratejisine geçiş yapmak.
