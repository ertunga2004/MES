# Physical MQTT / ESP32 Validation

## Amaç
Bu belgenin amacı, fiziksel ESP32 / IoT bridge ve MEGA kartının MQTT üzerinden Dockerized MES Web sistemi ile kurduğu bağlantının canlı ortamda yapılan manuel test ve doğrulama sonuçlarını kaydetmektir.

---

## Doğrulama Detayları

* **Test Tarihi:** 2026-06-08
* **Runtime Modu:** Portable Docker (`compose.portable.yaml` tabanlı)
* **Kullanılan Servisler:**
  * `mes_web` (Portable Docker container)
  * `mes_postgres` (PostgreSQL container)
  * `mes_adminer` (Adminer container)
  * Fiziksel ESP32 / IoT bridge

---

## Test Sonuçları ve Durum

### MQTT Bağlantı Sonucu
* **Doğrulama Durumu:** **Başarılı**. Kullanıcı, fiziksel ESP32 / IoT MQTT bağlantısının sorunsuz çalıştığını ve hat üzerindeki canlı veri/komut akışını manuel olarak doğrulamıştır.

### Docker Servis ve Sağlık Durumu
* **Docker Servisleri:** Bütün servisler (`mes_web`, `mes_postgres`, `mes_adminer`) kesintisiz çalışmaktadır (`Up`).
* **MES Web Health:** `http://127.0.0.1:8080/health` endpoint'i `200 OK` (Uvicorn status: ok) cevabını vermektedir.

### MQTT Parametreleri (Resolved AppConfig)
* **MQTT Host:** `broker.emqx.io`
* **MQTT Port:** `1883`
* **Topic Root:** `sau/iot/mega/konveyor`
* **Publish Enabled:** `True`
* **Command Mode:** `full_live`

### Beklenen Topic Ailesi
`topic_root` altında (`sau/iot/mega/konveyor/`):
* `status` (Konveyör durum)
* `logs` (Operasyon ve olay logları)
* `heartbeat` (Cihaz yaşam sinyali)
* `bridge/status` (ESP32 Wi-Fi ve MQTT telemetrisi)
* `cmd` (Preset motor/yön komutları)
* `vision/status` (Vision observer durumu)
* `vision/events` (Renk ve geçiş olayları)

---

## Fiziksel Bağlantı Yorumu

1. **Docker Ağ Bariyerinin Olmaması:** Docker runtime mimarisi MQTT bağlantısına engel teşkil etmemektedir. `mes_web` container'ı MQTT broker'ına (EMQX) erişebildiği sürece ESP32/bridge ile iki yönlü haberleşme sağlıklı şekilde devam eder.
2. **ESP32 Yapılandırması:** ESP32 tarafı aynı broker adresi ve aynı topic root ailesiyle çalıştığı sürece entegrasyon şeffaf bir şekilde yürütülür.

---

## Kesinleşen Durum Özeti

* Docker portable runtime stabil çalışıyor.
* MES Web `200 OK` durumunda.
* PostgreSQL mirror hattı (Faz C2 ile) daha önce başarıyla doğrulandı.
* IoT/MQTT fiziksel bağlantı kullanıcı tarafından doğrulandı.

> [!IMPORTANT]
> **Tasarım Sınırları Notu:**
> * Bu test ve doğrulama bir PostgreSQL source-of-truth geçişi değildir.
> * DB mirror flagleri (`MES_WEB_DB_ENABLED` ve `MES_WEB_DB_MIRROR_WORK_ORDERS`) test sonunda `false` güvenli moduna geri alınmıştır.
> * MQTT runtime state ve bridge online/offline durumu ayrı bir event/mirror çalışmasına konu olabilir.

---

## Sonraki Önerilen Teknik Faz
* MQTT/ESP32 eventlerinin PostgreSQL'e dry-run analizi
* `device_sessions` mirror aday analizi
* `vision_events` mirror aday analizi
* `oee_snapshots` mirror aday analizi
