# Antigravity Handoff

Proje özeti:

MES, konveyör tabanlı akademik/prototip üretim hattı için FastAPI tabanlı MES Web, OEE dashboard, kiosk/technician ekranları, MQTT/ESP32 bridge entegrasyonu, Excel workbook ve FERP import/export dosyalarıyla çalışan bir sistemdir.

Mevcut çalışma durumu:

- Docker portable setup tamamlandı ve main'e alınmış durumda.
- PostgreSQL container ve Adminer altyapısı var.
- `mes` schema ve 15 başlangıç tablo migration ile oluşturuldu.
- `mes.work_orders` ilk mirror tablo olarak doğrulandı.
- Runtime hâlâ JSON/Excel/FERP/MQTT source-of-truth ile çalışıyor.
- Optional runtime work_orders mirror hook eklendi ama default kapalı.
- C2 runtime work_orders DB mirror hook passed.
- C3 physical MQTT/ESP32 connectivity was manually validated by the user.
- Next safe work: event mirror dry-run planning, not source-of-truth migration.


En son tamamlanan faz:

- Aşama C1.5 / C1.6: Docker Compose DB flag plumbing entegrasyonu ve doğrulaması tamamlandı.
- Aşama C2: Optional runtime work_orders mirror hook canlı Docker doğrulaması başarıyla tamamlandı (2026-06-08).

Bundan sonra yapılacak ilk 5 iş:

1. `device_sessions` için DB mirror planı çıkar ve uygula.
2. `vision_events` için DB mirror planı çıkar ve uygula.
3. `oee_snapshots` için DB mirror planı çıkar ve uygula.
4. `downtime_events` ve `production_completions` için DB mirror planı çıkar ve uygula.
5. FERP import/export metadata ve outbox mantığını mirror olarak tasarla.

Sonra yapılacaklar:

- DB read tasarımı ve feature-flagged entegrasyonu.
- En son source-of-truth migration.
- **Önemli Sınırlar (Özellikle Açık Not):**
  - Bu bir source-of-truth geçişi değildir.
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
