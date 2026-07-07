# Station/Location Read-Only API Smoke Runbook

## 1. Amaç

Bu runbook, station/location read-only API endpointlerinin lokal ortamda tekrar doğrulanması için kalıcı prosedürdür.

Evidence dokümanında başarılı smoke kaydedildi; bu dosya ise tekrar çalıştırılabilir standart prosedürü tanımlar.

Runbook yalnız read-only HTTP `GET` smoke içerir. DB write, SQL migration, MESQL, UI/Kiosk veya operation lifecycle mutation içermez.

## 2. Ne Zaman Çalıştırılır?

Bu runbook şu durumlarda çalıştırılmalıdır:

- `mes_web/__main__.py` route değişikliği sonrası.
- `mes_web/db/mesql_v2.py` station/location helper değişikliği sonrası.
- `db/migrations/003_add_station_locations.sql` seed/binding değişikliği sonrası.
- Docker image/source path değişikliği sonrası.
- Release/sunum öncesi manuel doğrulama.
- API'nin UI/Kiosk tarafından kullanılmaya başlanmasından önce.

## 3. Ön Koşullar

- Repo temiz olmalı.
- Docker Desktop çalışıyor olmalı.
- `mes_postgres` volume silinmemiş olmalı.
- Paket A migration uygulanmış olmalı.
- `mes.locations` ve `mes.station_location_bindings` mevcut olmalı.
- Beklenen seed data:
  - 8 location.
  - 6 active location.
  - `PACKAGING_01` 4 active binding.
  - `ASSEMBLY_01` 4 active binding.
- `.env` değiştirilmemeli.
- MESQL frozen kalmalı.

## 4. Kesin Yasaklar

- `docker compose down -v` yok.
- Docker volume silme yok.
- DB write yok.
- `psql` yok.
- SQL migration yok.
- MESQL push/pull yok.
- `POST`, `PUT`, `PATCH`, `DELETE` yok.
- Operation lifecycle endpointleri yok.
- Work order start/complete yok.
- UI/Kiosk değişikliği yok.
- `.env` değişikliği yok.

## 5. Precheck Komutları

```powershell
git status --short
git log --oneline -10
docker compose -f docker\mes\compose.portable.yaml ps
Invoke-RestMethod http://127.0.0.1:8080/health
```

Beklenen:

- `git status --short` clean.
- `mes_postgres` Up / healthy.
- `mes_web` Up.
- Health `ok`.

## 6. Unit Regression

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_station_location_api
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_mesql_v2
```

Beklenen:

- `tests.test_mes_web_station_location_api`: OK.
- `tests.test_mes_web_mesql_v2`: OK.

Fail olursa HTTP smoke'a geçilmemelidir.

## 7. Feature Flag Enable İçin Geçici Override

`.env` değiştirmeden geçici override oluştur:

```powershell
$SmokeOverride = Join-Path $env:TEMP "mes_station_location_api_smoke.override.yaml"

@"
services:
  mes_web:
    environment:
      MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED: "true"
"@ | Set-Content -Encoding UTF8 $SmokeOverride

Get-Content $SmokeOverride
```

Notlar:

- Bu dosya geçicidir.
- Repo içine alınmaz.
- `.env` değiştirilmez.

## 8. mes_web Rebuild/Recreate

```powershell
docker compose -f docker\mes\compose.portable.yaml -f $SmokeOverride up -d --build mes_web
docker compose -f docker\mes\compose.portable.yaml -f $SmokeOverride ps
Invoke-RestMethod http://127.0.0.1:8080/health
```

Beklenen:

- `mes_web` rebuilt/recreated.
- Health `ok`.
- `mes_postgres` volume korunur.

## 9. Endpoint Smoke Komutları ve Beklenenler

### 9.1 Locations

```powershell
$allLocations = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations?active_only=false"
$activeLocations = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations?active_only=true"
$buffers = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations?location_type=BUFFER"
```

Beklenen:

- `$allLocations.count -eq 8`
- `$activeLocations.count -eq 6`
- `$buffers` içinde `BETWEEN_ASSEMBLY_PACKAGING`
- Buffer `location_type = buffer`

### 9.2 Location Detail

```powershell
$bufferLocation = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations/BETWEEN_ASSEMBLY_PACKAGING"
$finishedGoods = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations/FINISHED_GOODS"
$scrapArea = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations/SCRAP_AREA"
```

Beklenen:

- `BETWEEN_ASSEMBLY_PACKAGING.location_type = buffer`
- `FINISHED_GOODS.location_type = finished_goods`
- `SCRAP_AREA.location_type = scrap`

### 9.3 PACKAGING_01 Bindings

```powershell
$packagingBindings = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/PACKAGING_01/locations"
$packagingOutputGood = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/packaging_01/locations?role=OUTPUT_GOOD"
```

Beklenen:

- `$packagingBindings.count -eq 4`
- `input = BETWEEN_ASSEMBLY_PACKAGING`
- `active_wip = PACKAGING_WIP`
- `output_good = FINISHED_GOODS`
- `output_scrap = SCRAP_AREA`
- Role filter `OUTPUT_GOOD` normalize olur.
- `$packagingOutputGood.count -eq 1`
- Result `FINISHED_GOODS`

### 9.4 ASSEMBLY_01 Bindings

```powershell
$assemblyBindings = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/locations"
```

Beklenen:

- `$assemblyBindings.count -eq 4`
- `input = RAW_MATERIAL`
- `active_wip = ASSEMBLY_WIP`
- `output_good = BETWEEN_ASSEMBLY_PACKAGING`
- `output_buffer = BETWEEN_ASSEMBLY_PACKAGING`

### 9.5 Context Endpoints

```powershell
$packagingContext = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/PACKAGING_01/location-context"
$assemblyContext = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/location-context"
```

Beklenen:

- `PACKAGING_01.input_location = BETWEEN_ASSEMBLY_PACKAGING`
- `PACKAGING_01.active_wip_location = PACKAGING_WIP`
- `PACKAGING_01.output_good_location = FINISHED_GOODS`
- `PACKAGING_01.output_scrap_location = SCRAP_AREA`
- `PACKAGING_01.output_buffer_location = null` olabilir; hata değildir.
- `ASSEMBLY_01.input_location = RAW_MATERIAL`
- `ASSEMBLY_01.active_wip_location = ASSEMBLY_WIP`
- `ASSEMBLY_01.output_good_location = BETWEEN_ASSEMBLY_PACKAGING`
- `ASSEMBLY_01.output_buffer_location = BETWEEN_ASSEMBLY_PACKAGING`

## 10. Error / Validation Smoke

Missing location:

```powershell
try {
    Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations/DOES_NOT_EXIST"
    throw "Expected 404 but request succeeded"
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $body = $_.ErrorDetails.Message
    Write-Host "missing_location_status=$status"
    Write-Host "missing_location_body=$body"
}
```

Beklenen:

- `404 LOCATION_NOT_FOUND`

Invalid location type:

```powershell
try {
    Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations?location_type=unknown"
    throw "Expected 400 but request succeeded"
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $body = $_.ErrorDetails.Message
    Write-Host "invalid_location_type_status=$status"
    Write-Host "invalid_location_type_body=$body"
}
```

Beklenen:

- `400 INVALID_LOCATION_TYPE`

Invalid role:

```powershell
try {
    Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/PACKAGING_01/locations?role=unknown"
    throw "Expected 400 but request succeeded"
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $body = $_.ErrorDetails.Message
    Write-Host "invalid_role_status=$status"
    Write-Host "invalid_role_body=$body"
}
```

Beklenen:

- `400 INVALID_BINDING_ROLE`

Missing station bindings:

```powershell
$missingStation = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/DOES_NOT_EXIST/locations"
```

Beklenen:

- HTTP 200
- `count = 0`
- `data = []`

## 11. No-Write Guardrail

```powershell
$beforeAllLocationCount = $allLocations.count
$beforePackagingBindingCount = $packagingBindings.count
$beforeAssemblyBindingCount = $assemblyBindings.count

$afterAllLocations = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations?active_only=false"
$afterPackagingBindings = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/PACKAGING_01/locations"
$afterAssemblyBindings = Invoke-RestMethod "http://127.0.0.1:8080/api/v2/stations/ASSEMBLY_01/locations"

$afterAllLocationCount = $afterAllLocations.count
$afterPackagingBindingCount = $afterPackagingBindings.count
$afterAssemblyBindingCount = $afterAssemblyBindings.count
```

Beklenen:

- `8 -> 8`
- `4 -> 4`
- `4 -> 4`

## 12. Logs Kontrolü

```powershell
docker compose -f docker\mes\compose.portable.yaml -f $SmokeOverride logs --tail=120 mes_web
```

Beklenen:

- 500 yok.
- MESQL push/pull yok.
- Operation lifecycle mutation yok.

## 13. Smoke Sonrası Baseline Reset

Geçici override dosyasını sil:

```powershell
Remove-Item $SmokeOverride -Force
```

Base compose ile `mes_web` recreate:

```powershell
docker compose -f docker\mes\compose.portable.yaml up -d --build mes_web
Invoke-RestMethod http://127.0.0.1:8080/health
```

Default disabled doğrulaması:

```powershell
try {
    Invoke-RestMethod "http://127.0.0.1:8080/api/v2/locations"
    throw "Expected 503 but request succeeded"
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $body = $_.ErrorDetails.Message
    Write-Host "station_location_api_disabled_status=$status"
    Write-Host "station_location_api_disabled_body=$body"
}
```

Beklenen:

- `503 STATION_LOCATION_READ_MODEL_DISABLED`

## 14. Final Kontrol

```powershell
git status --short
```

Beklenen:

- clean

## 15. PASS / FAIL Kriteri

PASS için:

- Unit regression OK.
- Health OK.
- Feature flag true ile endpoint smoke PASS.
- Expected count değerleri doğru.
- Error/validation sonuçları doğru.
- No-write before/after count'ları aynı.
- Logs temiz.
- Base compose reset sonrası default disabled 503.
- Git clean.

FAIL için:

- Herhangi endpoint 500.
- Count mismatch.
- Feature flag true olmasına rağmen 503.
- Base compose reset sonrası 200 dönmesi.
- DB write şüphesi.
- MESQL push/pull log'u.
- Operation lifecycle mutation log'u.
