# Tablet Kiosk Teknik Spesifikasyon MD Dokümanı

## Özet
`docs/tablet-kiosk-teknik-spesifikasyon.md` adlı Türkçe bir Markdown dokümanı hazırlanacak. Doküman mevcut `mes_web` mimarisini referans alacak, ancak tablet kiosk entegrasyonu için **JSON tabanlı domain topic modelini** ana sözleşme olarak tanımlayacak. Mevcut `sau/iot/mega/konveyor` `topic_root` korunacak; `tablet/log` yalnızca legacy/audit amaçlı anlatılacak.

Dokümanın ana önerisi şu olacak:
- Tablet bir **browser kiosk** olarak çalışır.
- Tablet **doğrudan MQTT broker’a bağlanmaz**.
- Tablet, `mes_web` ile **HTTPS + REST + WebSocket** üzerinden konuşur.
- `mes_web`, hem UI state yöneticisi hem de **MQTT bridge/orchestrator** rolünü üstlenir.
- MQTT tarafında ayrık **state topicleri** ve **event topicleri** tanımlanır.

## Dokümanda Yer Alacak Karar Tamamlayıcı İçerik

### 1. Mimari ve Ağ Topolojisi
Doküman şu mimariyi net ve çizimle anlatacak:
- Aynı LAN/Wi-Fi içinde çalışan `mes_web` host cihazı, MQTT broker, üretim ekipmanları, vision kaynağı ve tablet kiosk.
- Tablet yalnızca `mes_web` adresini açar: örnek `https://mes-host/kiosk/{device_id}`.
- `mes_web` tarafı:
  - REST: operatör aksiyonlarını kabul eder.
  - WebSocket: kiosk ekranını canlı günceller.
  - MQTT: topic publish/subscribe yapar.
  - Runtime state: iş emri, OEE, fault, quality, maintenance akışlarını tek yerde toplar.
- Güven sınırı:
  - MQTT kullanıcı bilgisi browser’a verilmez.
  - Broker erişimi yalnızca backend’dedir.
  - Kiosk route cihaz bazlı kimlik (`device_id`) ve statik kiosk token veya reverse proxy erişim kuralı ile korunur.

### 2. Kiosk İşlevleri ve Operatör Akışları
Doküman aşağıdaki ekran ve akışları karar verilmiş şekilde tarif edecek:
- Açılış/bağlantı ekranı:
  - cihaz adı, hat adı, bağlantı durumu, son sync zamanı
- İş emri ekranı:
  - bekleyen iş emri listesi
  - sıralama değişirse tablette aynı sıranın görünmesi
  - aktif iş emri kartı
  - çok renkli iş emrinde `requirements` alt kalemleri görünür
  - başlatma, geçiş nedeni girişi, depodan düşen miktar bilgisi
- Kalite ekranı:
  - son tamamlanan ürünler
  - `GOOD/REWORK/SCRAP` override
- Duruş ekranı:
  - planlı / plansız ayrımı
  - kategori + neden kodu + serbest metin + başlat/bitir
- Bakım ekranı:
  - bakım çağrısı açma
  - bakım başladı / bitti / kapatıldı
- OEE ekranı:
  - vardiya OEE
  - aktif iş emri OEE
  - availability / performance / quality
  - planlı duruş / plansız duruş / runtime / kalan süre

### 3. Kiosk HTTP ve WebSocket Arayüzleri
Doküman kiosk tarafı için aşağıdaki route yapısını tanımlayacak:
- `GET /kiosk/{device_id}`
- `GET /api/modules/{module_id}/kiosk/bootstrap`
- `POST /api/modules/{module_id}/kiosk/work-orders/start`
- `POST /api/modules/{module_id}/kiosk/work-orders/reorder`
- `POST /api/modules/{module_id}/kiosk/quality/override`
- `POST /api/modules/{module_id}/kiosk/downtime/start`
- `POST /api/modules/{module_id}/kiosk/downtime/stop`
- `POST /api/modules/{module_id}/kiosk/maintenance/request`
- `POST /api/modules/{module_id}/kiosk/maintenance/start`
- `POST /api/modules/{module_id}/kiosk/maintenance/complete`
- `POST /api/modules/{module_id}/kiosk/session/heartbeat`
- `WS /ws/modules/{module_id}/kiosk/{device_id}`

Doküman her endpoint için:
- amaç
- request alanları
- response alanları
- hata kodları
- idempotency beklentisi
- UI davranışı
tanımlayacak.

## MQTT Topic ve Payload Sözleşmesi

### 4. Topic Ağacı
Doküman aşağıdaki topic setini ana sözleşme olarak verecek.

Mevcut topicler, değişmeden korunacak:
- `${topic_root}/status`
- `${topic_root}/logs`
- `${topic_root}/heartbeat`
- `${topic_root}/bridge/status`
- `${topic_root}/cmd`
- `${topic_root}/vision/status`
- `${topic_root}/vision/tracks`
- `${topic_root}/vision/heartbeat`
- `${topic_root}/vision/events`
- `${topic_root}/tablet/log`  
  Bu topic legacy/audit olarak tanımlanacak; ana entegrasyon kanalı olmayacak.

Yeni state topicleri:
- `${topic_root}/mes/state/work-orders`
- `${topic_root}/mes/state/oee`
- `${topic_root}/mes/state/fault`
- `${topic_root}/mes/state/maintenance`
- `${topic_root}/mes/state/kiosk`
- `${topic_root}/mes/masterdata/downtime-reasons`
- `${topic_root}/mes/masterdata/maintenance-codes`
- `${topic_root}/mes/masterdata/quality-codes`

Yeni event topicleri:
- `${topic_root}/tablet/heartbeat`
- `${topic_root}/tablet/event/session`
- `${topic_root}/tablet/event/work-order`
- `${topic_root}/tablet/event/quality`
- `${topic_root}/tablet/event/downtime`
- `${topic_root}/tablet/event/maintenance`

### 5. Payload Standartları
Doküman tüm JSON payload’lar için ortak envelope tanımlayacak:
- `schema_version`
- `message_id`
- `ts`
- `module_id`
- `device_id`
- `operator_code`
- `operator_name`
- `shift_code`
- `source`
- `correlation_id`

Alan isimleri:
- MQTT/JSON contract için **snake_case**
- açıklamalar Türkçe
- zaman formatı: ISO-8601 timezone’lı
- parasal olmayan tüm sayaçlar integer
- OEE oranları yüzde olarak değil, açıkça belirtilmiş biçimde taşınacak:
  - state payload’larında `0-100` yüzde alanları
  - örneklerde alan adı sonuna `_pct` eklenecek

MQTT yayın kuralları:
- `state/*`: `QoS 1`, `retain=true`
- `event/*`: `QoS 1`, `retain=false`
- `heartbeat`: `QoS 0`, `retain=false`

### 6. Domain Bazlı Event/State Tanımları
Doküman her domain için örnek JSON verecek:

- `work-order`
  - event tipleri: `selected`, `started`, `reordered`, `transition_reason_submitted`, `completed`
  - state içeriği: queue, active_order, completed, inventory, tolerance_minutes
  - aktif iş emri çok renkliyse `requirements[]` zorunlu

- `quality`
  - event tipleri: `override_requested`, `override_applied`
  - alanlar: `item_id`, `measure_id`, `classification`, `reason_code`, `reason_text`

- `oee`
  - state içeriği:
    - shift kpi
    - active_work_order kpi
    - planned_stop_min
    - unplanned_stop_min
    - runtime_min
    - remaining_min
    - active_fault
  - tablet OEE hesaplamaz; backend hesaplar, tablet gösterir

- `downtime`
  - event tipleri: `started`, `ended`
  - alanlar:
    - `downtime_mode`: `planned` | `unplanned`
    - `category_code`
    - `reason_code`
    - `reason_text`
    - `started_at`, `ended_at`
  - planlı duruş örnekleri:
    - `break`, `lunch`, `setup`, `changeover`, `cleaning`, `planned_maintenance`
  - plansız duruş örnekleri:
    - `mechanical_fault`, `electrical_fault`, `sensor_fault`, `jam`, `material_shortage`, `emergency_stop`

- `maintenance`
  - event tipleri: `request_opened`, `started`, `completed`, `closed`
  - alanlar:
    - `maintenance_ticket_id`
    - `maintenance_code`
    - `priority`
    - `description`
    - `requested_by`, `assigned_to`

## Test ve Kabul Kriterleri
Doküman içinde ayrıca şu acceptance kriterleri yer alacak:
- tablet aynı ağda browser ile kiosk ekranını açabiliyor olmalı
- WebSocket koparsa ekran read-only moda düşmeli ve reconnect göstermeli
- backend yoksa kiosk yeni işlem başlatmamalı
- work order sırası yönetim ekranında değişince kioskta aynı sıra görünmeli
- çok renkli iş emri her alt kalem tamamlanmadan kapanmamalı
- iş emri geçiş toleransı aşılırsa neden girişi zorunlu olmalı
- planlı/plansız duruş OEE üzerinde farklı sınıflanmalı
- bakım eventi aktif duruş/fault ile ilişkilendirilebilmeli
- kalite override yapıldığında ilgili iş emri ve vardiya metrikleri güncellenmeli
- legacy `tablet/log` için geçiş notu bulunmalı, fakat yeni geliştirme bu topic’e bağlanmamalı

## Varsayımlar ve Varsayılan Seçimler
- Doküman dili Türkçe olacak.
- Topic açıklamaları Türkçe, payload anahtarları İngilizce/snake_case olacak.
- Sistem mevcut `mes_web` yapısına uyumlu anlatılacak.
- `topic_root` mevcut varsayılan yapıda kalacak: `sau/iot/mega/konveyor`.
- Browser kiosk doğrudan MQTT kullanmayacak; MQTT sadece backend tarafında olacak.
- v1’de offline write queue olmayacak; bağlantı yoksa kiosk yeni aksiyon almayacak.
- `tablet/log` korunacak ama yalnızca audit/transition compatibility için anlatılacak.
- Doküman içinde en az bir ağ topolojisi diyagramı ve en az iki sequence diagram bulunacak:
  - iş emri başlatma
  - plansız duruş başlatma/bitirme
