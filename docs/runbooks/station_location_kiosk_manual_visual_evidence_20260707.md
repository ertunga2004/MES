# Station/Location Kiosk Manual Visual Evidence - 2026-07-07

## 1. Amaç

Bu doküman, Kiosk station/location read-only bilgi kartının gerçek tarayıcıda
görsel olarak doğrulandığını kaydeder.

Bu doğrulama, önceki HTTP/static smoke evidence sonrasında yapılan controlled
manual visual check sonucudur.

Kart sadece istasyon lokasyon bilgisini gösterir. Kart start/complete, queue
mutation, inventory movement, MESQL veya DB write başlatmaz.

## 2. Test Ortamı

- Repo clean.
- Son commitlerde görülenler:
  - `b773064 "docs: record station location kiosk ui smoke evidence"`
  - `3db1d55 "feat: show station location context on kiosk"`
- `mes_postgres`: Up / healthy.
- `mes_web`: Up.
- Health:
  - Feature flag true sonrası `ok`.
  - Reset sonrası `ok`.
- Geçici override kullanıldı.
- `.env` değişmedi.
- Docker volume silinmedi.
- `docker compose down -v` çalıştırılmadı.

## 3. Kullanılan URL'ler

```text
http://127.0.0.1:8080/kiosk/station/PACKAGING_01
http://127.0.0.1:8080/kiosk/station/ASSEMBLY_01
```

## 4. PACKAGING_01 Görsel Sonucu

- Kart gerçek tarayıcıda göründü.
- Kart başlığı: `İstasyon Lokasyon Bilgisi`.
- Değerler doğru görüntülendi.

`PACKAGING_01`:

```text
Giriş Lokasyonu: BETWEEN_ASSEMBLY_PACKAGING (buffer)
Aktif WIP Lokasyonu: PACKAGING_WIP (wip)
Sağlam Çıkış Lokasyonu: FINISHED_GOODS (finished_goods)
Fire/Hurda Çıkış Lokasyonu: SCRAP_AREA (scrap)
Ara Buffer Lokasyonu: Not configured
```

Ek doğrulamalar:

- Console error yok.
- Yatay taşma yok.
- `location-context` status: 200.

## 5. ASSEMBLY_01 Görsel Sonucu

- Kart gerçek tarayıcıda göründü.
- Değerler doğru görüntülendi.

`ASSEMBLY_01`:

```text
Giriş Lokasyonu: RAW_MATERIAL (raw_material)
Aktif WIP Lokasyonu: ASSEMBLY_WIP (wip)
Sağlam Çıkış Lokasyonu: BETWEEN_ASSEMBLY_PACKAGING (buffer)
Fire/Hurda Çıkış Lokasyonu: Not configured
Ara Buffer Lokasyonu: BETWEEN_ASSEMBLY_PACKAGING (buffer)
```

Ek doğrulamalar:

- Console error yok.
- Yatay taşma yok.
- `location-context` status: 200.

## 6. Disabled Behavior

- Override kaldırıldı.
- Base compose ile `mes_web` yeniden oluşturuldu.
- Feature flag reset sonrası Kiosk açıldı.
- Kart disabled mesajını gösterdi:

```text
İstasyon lokasyon bilgisi bu ortamda aktif değil.
```

- API status: 503.
- Kiosk kırılmadı.

## 7. Button / Operation Guardrails

- Start/complete butonlarına basılmadı.
- Queue action kullanılmadı.
- System start/stop kullanılmadı.
- Button layout beklenmedik kırılmadı.
- Operation lifecycle mutation yapılmadı.

## 8. Logs

- 500 yok.
- MESQL yok.
- Start/complete çağrısı yok.
- Queue mutation yok.
- Existing kiosk init POST görüldü:

```text
POST /api/modules/konveyor_main/kiosk/register HTTP/1.1" 200 OK
```

Yorum:

- Bu POST, yeni station/location kartından kaynaklı değildir.
- Bu mevcut Kiosk init davranışıdır.
- Bu manual visual check kapsamında kabul edilmiştir.

## 9. Sonuç

Kiosk station/location read-only bilgi kartı gerçek tarayıcıda `PACKAGING_01`
ve `ASSEMBLY_01` için görsel olarak doğrulanmıştır. Kart doğru lokasyon
context değerlerini göstermiş, console error veya yatay taşma üretmemiş,
feature flag disabled durumda Kiosk'u kırmadan disabled mesajı göstermiştir.
Test boyunca start/complete, queue mutation, MESQL veya operation lifecycle
çağrısı yapılmamıştır. Existing kiosk init POST davranışı gözlenmiş ancak yeni
kartla ilişkili değildir.

Sonuç: PASS.

Not:

- Kullanıcı kendi bağımsız manuel kontrolünü ayrıca yapmamıştır; Codex
  kontrollü browser visual check sırasında kartların geldiği kullanıcı
  tarafından da gözlemlenmiştir.

## 10. Sonraki Adım

- Evidence commit sonrası Kiosk read-only görünürlük fazı kapanır.
- Sonraki ürün adımı Dashboard tarafında station/location read-only kart
  tasarımı olabilir.
- Inventory movement/balance hâlâ sonraki fazdır.
