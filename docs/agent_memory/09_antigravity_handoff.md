# Antigravity Handoff

Proje özeti:

MES, konveyör tabanlı akademik/prototip üretim hattı için FastAPI tabanlı MES Web, OEE dashboard, kiosk/technician ekranları, MQTT/ESP32 bridge entegrasyonu, Excel workbook ve FERP import/export dosyalarıyla çalışan bir sistemdir.

Mevcut çalışma durumu:

- Docker portable setup tamamlandı ve main'e alınmış durumda.
- PostgreSQL container ve Adminer altyapısı var.
- `mes` schema ve 15 başlangıç tablo migration ile oluşturuldu.
- **Son doğrulanmış DB durumu (E5F Checkpoint):** 3 temel tablo kontrollü olarak dolduruldu ve `verify clean` alındı:
  - `mes.work_orders` (6 kayıt)
  - `mes.production_completions` (8 kayıt)
  - `mes.vision_events` (43 kayıt)
- Runtime hâlâ JSON/Excel/FERP/MQTT source-of-truth ile çalışıyor.
- DB mirror sadece feature flag ile çalışır, testler sonrasında flagler kapatıldı (`MES_WEB_DB_ENABLED=false`).
- Ertelenen tablolar: `device_sessions`, `oee_snapshots`, `downtime_events`, `maintenance_records`, `quality_overrides`.

En son tamamlanan faz:

- **E5F:** Validated DB population checkpoint. Excel log backfill ile `vision_events` tablosu doğrulandı.

Bundan sonra yapılacak ilk 5 iş:

1. Sıradaki teknik kararı ver: Yeni tablo analizine (örn. `oee_snapshots` veya `downtime_events` örnek datası) mi geçilecek, yoksa mevcut 3 dolu tablo için okuma geçişine (runtime hook / read transition) mi başlanacak?
2. `device_sessions` için gerçek session identity çözümü uyarla ve apply et.
3. Raw MQTT stream'ini DB veya Excel dışında canlı bir worker ile ele almayı tasarla.
4. FERP import/export metadata ve outbox mantığını mirror olarak tasarla.
5. Canlı runtime'da `production_completions` hook'larını aktif et.

Sonra yapılacaklar:

- DB read tasarımı ve feature-flagged entegrasyonu.
- En son source-of-truth migration.
- **Önemli Sınırlar (Özellikle Açık Not):**
  - Bu henüz bir source-of-truth geçişi değildir.
  - Runtime tarafında veritabanı okuması (DB read) yoktur.
  - JSON/Excel/FERP akışı aynen korunmaktadır.
  - DB mirror sadece feature flag ile çalışır.
  - Test sonunda flagler tekrar false yapılmıştır.


Kritik sınırlar:

- Önce oku, sonra plan çıkar, sonra uygula.
- Büyük refactor yapma.
- Runtime davranışını küçük feature flag'lerle değiştir.
- Her DB yazımı için verify script kullan.
- Docker compose, migration ve runtime source-of-truth sınırlarını açık onay olmadan değiştirme.
