# Station/Location Kiosk Read-Only UI Smoke Evidence - 2026-07-07

## 1. Amaç

Bu doküman Kiosk station/location read-only bilgi kartı için yapılan lokal
smoke doğrulamasını evidence olarak kaydeder.

Kart sadece station location context bilgisini gösterir. Operation lifecycle
başlatmaz, operasyon tamamlamaz, `station_queue` güncellemez, inventory
movement oluşturmaz, MESQL push/pull çalıştırmaz ve DB write yapmaz.

Bu evidence gerçek browser visual test yerine HTTP/static/API smoke sonucuna
dayanır.

## 2. Kapsam

Değişen dosyalar:

```text
mes_web/static/kiosk.html
mes_web/static/kiosk.js
mes_web/static/kiosk.css
```

UI kapsamı:

- Kiosk primary panel içinde `İstasyon Lokasyon Bilgisi` kartı.
- Endpoint:
  `GET /api/v2/stations/{station_code}/location-context`
- Gösterilen alanlar:
  - Giriş Lokasyonu
  - Aktif WIP Lokasyonu
  - Sağlam Çıkış Lokasyonu
  - Fire/Hurda Çıkış Lokasyonu
  - Ara Buffer Lokasyonu

Kapsam dışı:

- API route implementation.
- DB write.
- SQL migration.
- MESQL push/pull.
- Inventory movement.
- Operation lifecycle start/complete.
- Queue mutation.
- UI dışı modüller.

## 3. Implementation Commit Notu

```text
3db1d55 feat: show station location context on kiosk
```

## 4. Regression ve Statik Kontroller

```text
tests.test_mes_web_station_location_api: Ran 14 tests ... OK
tests.test_mes_web_mesql_v2: Ran 27 tests ... OK
node --check mes_web\static\kiosk.js: PASS
git diff --check: PASS
```

`git diff --check` sırasında `mes_web/static/kiosk.html`,
`mes_web/static/kiosk.js` ve `mes_web/static/kiosk.css` için CRLF uyarısı
görüldü; whitespace error bulunmadı.

## 5. Guardrail Diff Inspection

Yeni diff içinde aşağıdaki operasyonel write/lifecycle izleri bulunmadı:

```text
POST
PUT
PATCH
DELETE
start_operation
complete_operation
MESQL
push/pull
station_queue mutation
```

Yeni endpoint çağrısı read-only GET context çağrısıdır:

```text
/api/v2/stations/${encodeURIComponent(stationCode)}/location-context
```

## 6. Feature Flag ve Rebuild

Smoke sırasında geçici override dosyası kullanıldı:

```text
%TEMP%\mes_station_location_kiosk_ui_smoke.override.yaml
```

Override ile `mes_web` ortamında şu feature flag açıldı:

```text
MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED=true
```

`mes_web` rebuild/recreate edildi. Compose durumu:

```text
mes_postgres: Up, healthy
mes_web: Up
mes_adminer: Up
```

Health sonucu:

```text
status = ok
```

Feature flag açıkken station/location context endpointleri 200 döndü.
Smoke sonrası override dosyası silindi, base compose ile `mes_web` yeniden
oluşturuldu ve default disabled davranışı tekrar doğrulandı.

## 7. API Context Sonuçları

`PACKAGING_01`:

```text
input = BETWEEN_ASSEMBLY_PACKAGING
active_wip = PACKAGING_WIP
output_good = FINISHED_GOODS
output_scrap = SCRAP_AREA
output_buffer = <null>
```

`ASSEMBLY_01`:

```text
input = RAW_MATERIAL
active_wip = ASSEMBLY_WIP
output_good = BETWEEN_ASSEMBLY_PACKAGING
output_scrap = <null>
output_buffer = BETWEEN_ASSEMBLY_PACKAGING
```

## 8. Kiosk Page ve Static Asset Smoke

Kiosk route sonuçları:

```text
http://127.0.0.1:8080/kiosk -> 200
http://127.0.0.1:8080/static/kiosk.html -> 200
http://127.0.0.1:8080/kiosk/station/PACKAGING_01 -> 200
http://127.0.0.1:8080/kiosk/PACKAGING_01 -> 200
http://127.0.0.1:8080/kiosk.html -> 404
```

Sayfa marker kontrolleri:

```text
stationLocationCard
İstasyon Lokasyon Bilgisi
```

Static asset kontrolleri:

```text
/static/kiosk.js -> 200
/static/kiosk.css -> 200
```

## 9. Visual / Manual Check Notu

Gerçek browser visual check yapılmadı. Nedeni: mevcut Kiosk init akışı browser
load sırasında `registerDevice` POST çağrısı ve runtime write tetikleyebilir.
Bu davranış read-only smoke guardrail'i ile çakışabileceği için bu turda
bilerek yapılmadı.

HTTP/static smoke, kart markup'ının ve asset'lerin servis edildiğini doğruladı.

Sonuç:

```text
PASS with manual visual check pending
```

## 10. Log Kontrolü

Smoke sırasında loglarda aşağıdaki bulgular doğrulandı:

- 500 hata görülmedi.
- MESQL push/pull görülmedi.
- Operation lifecycle mutation görülmedi.
- Start/complete endpoint çağrısı görülmedi.
- Mevcut açık Kiosk/Technician websocket bağlantıları gözlendi.
- Smoke HTTP kontrolleri GET ile sınırlı kaldı.

## 11. No-Write Kontrolü

Smoke sonrası baseline sayımlar:

```text
locations count = 8
PACKAGING_01 binding count = 4
ASSEMBLY_01 binding count = 4
```

Smoke read-only kaldı; DB write yapılmadı ve baseline count değerleri korundu.

## 12. Baseline Reset

Base compose reset sonrası default disabled davranış:

```text
station_location_api_disabled_status = 503
station_location_api_disabled_body = {"detail":"STATION_LOCATION_READ_MODEL_DISABLED"}
```

Feature flag default olarak disabled kaldı. `.env` değiştirilmedi. Geçici
override kalıcı hale getirilmedi.

## 13. Guardrails

- DB write yok.
- `psql` yok.
- Docker volume silme yok.
- `docker compose down -v` yok.
- SQL migration yok.
- API route değişikliği yok.
- MESQL push/pull yok.
- Inventory/balance yok.
- Operation lifecycle mutation yok.
- Start/complete davranışı değişmedi.
- Queue davranışı değişmedi.
- UI sadece read-only GET context gösterimi ekledi.
- Runtime data değiştirilmedi.
- `.env` değiştirilmedi.

## 14. Hüküm

```text
Kiosk station/location read-only bilgi kartı implementation'ı regression/static kontroller, real API context GET doğrulaması, Kiosk page/static asset smoke, logs kontrolü, no-write guardrail ve feature flag baseline reset ile doğrulanmıştır. Gerçek browser visual check, mevcut Kiosk init akışının POST çağrısı tetikleyebilme riski nedeniyle bu read-only smoke kapsamında yapılmamıştır; bu nedenle sonuç PASS with manual visual check pending olarak kaydedilmiştir.
```

## 15. Sonraki Adım

- Evidence commit sonrası Kiosk read-only card phase teknik olarak kapatılabilir.
- Controlled manual visual check ayrı bir turda yapılabilir.
- Manual visual check için mevcut Kiosk init POST çağrısını kabul etmek veya
  izole test/snapshot mock kullanmak gerekir.
- Inventory/balance ayrı gelecek faz kapsamındadır.
