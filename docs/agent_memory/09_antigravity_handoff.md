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

En son tamamlanan faz:

Faz 4J commit hazırlığı ve commit: PostgreSQL mirror foundation ile obsolete `.gsheet` link cleanup branch commit'i oluşturuldu.

Bundan sonra yapılacak ilk 5 iş:

1. Local `main` branch'i GitHub'daki güncel duruma göre güncelle.
2. Docker runtime klasörünü repo içindeki güncel Docker/Faz 4 kaynaklarıyla uyumlu hale getir.
3. Portable image rebuild/restart yap.
4. Flagler kapalıyken sistemin kalktığını doğrula.
5. İki flag true iken work_orders mirror hook'u canlı Docker ortamında kontrollü test et.

Sonra yapılacaklar:

- `device_sessions` mirror.
- `vision_events` mirror.
- `oee_snapshots` mirror.
- `downtime_events` ve `production_completions` mirror.
- FERP import/export outbox metadata.
- DB read tasarımı.
- En son source-of-truth migration.

Kritik sınırlar:

- Önce oku, sonra plan çıkar, sonra uygula.
- Büyük refactor yapma.
- Runtime davranışını küçük feature flag'lerle değiştir.
- Her DB yazımı için verify script kullan.
- Docker compose, migration ve runtime source-of-truth sınırlarını açık onay olmadan değiştirme.
