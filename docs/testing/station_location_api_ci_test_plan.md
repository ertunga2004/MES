# Station/Location Read-Only API CI Test Plan

## 1. Amaç

Bu doküman station/location read-only API için CI/CD test stratejisini tanımlar.

Bu turda CI implementasyonu yapılmaz. GitHub Actions YAML, workflow veya runner konfigürasyonu oluşturulmaz.

Amaç hangi testlerin CI'da çalışacağı, hangilerinin local/manual smoke olarak kalacağı ve hangi guardrail'lerin korunacağıdır.

## 2. Test Katmanları

### Tier 1 - Offline Unit/API Tests

CI'da hemen çalıştırılabilir.

Komutlar:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_station_location_api
& '.\.venv\Scripts\python.exe' -m unittest tests.test_mes_web_mesql_v2
```

Özellik:

- DB yok.
- Docker yok.
- Helper mock var.
- Route validation ve feature flag test edilir.
- Operation lifecycle helper çağrılmama test edilir.

### Tier 2 - Containerized API Smoke

CI'da opsiyonel/future.

Gereksinim:

- Docker service.
- PostgreSQL container.
- Seed edilmiş `mes.locations` ve `mes.station_location_bindings`.
- Feature flag temporary enable.
- HTTP `GET` endpoint smoke.

Risk:

- CI ortamında DB seed/migration yönetimi gerekir.
- Docker startup süresi artar.
- Secrets/env dikkat ister.

### Tier 3 - Manual/Local Release Smoke

Şimdilik ana güvence.

Kaynak:

- `docs/runbooks/station_location_api_smoke_runbook.md`

Ne zaman:

- Release öncesi.
- API değişikliği sonrası.
- DB seed/migration değişikliği sonrası.
- UI/Kiosk bağlanmadan önce.

## 3. CI'ya Hemen Alınacak Minimum Testler

Minimum CI adayları:

- `tests.test_mes_web_station_location_api`
- `tests.test_mes_web_mesql_v2`

Bu testler:

- DB'ye bağlanmaz.
- Docker gerektirmez.
- Feature flag disabled/enable davranışını mock/env patch ile doğrular.
- Helper çağrılarını doğrular.
- Raw DB access guard içerir.
- Lifecycle helper çağrılmama guard içerir.

## 4. CI'ya Hemen Alınmayacak Testler

Şimdilik CI'ya alınmayacak testler:

- Gerçek HTTP API smoke.
- Docker compose rebuild/recreate.
- Local PostgreSQL seed data count kontrolleri.
- Base compose reset doğrulaması.

Neden:

- CI ortamında Docker ve seed setup daha hassas.
- Önce manuel runbook ile standartlaştırıldıktan sonra containerized CI tasarlanmalı.
- DB volume/seed lifecycle yanlış kurulursa false negative doğabilir.

## 5. Gelecek CI Containerized Smoke Tasarımı

Önerilen gelecek akış:

```text
checkout repo
set up Python
install mes_web requirements
run Tier 1 tests
start docker compose test stack
apply station/location migration to empty test DB
enable MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED=true
start mes_web
wait for /health
run HTTP GET smoke
assert counts and response codes
assert no write side effects
tear down containers without deleting developer local volumes
```

Önemli:

- Bu akış gerçek local Docker volume'a dokunmamalı.
- CI için ayrı compose project name kullanılmalı.
- CI için ayrı ephemeral DB volume kullanılmalı.
- `down -v` sadece CI ephemeral volume için kabul edilebilir; lokal runbookta yasaktır.
- Local production-ish `mes_postgres_data` volume asla silinmemeli.

## 6. Guardrail Testleri

CI'da korunması gereken guardrail'ler:

- API yalnız `GET`.
- Feature flag default disabled.
- Disabled iken helper çağrılmaz.
- Invalid query param 400.
- Missing location 404.
- Missing station bindings 200 empty list.
- Missing `output_buffer` 500 üretmez.
- API route raw SQL yazmaz.
- API route `database_connection` çağırmaz.
- API route `start_operation_v2`, `complete_operation_v2`, `read_station_queue_v2` çağırmaz.
- MESQL push/pull çağrılmaz.
- DB write helper çağrılmaz.

## 7. Kabul Kriterleri

CI planı için:

- Tier 1 testler net.
- Tier 2 future smoke ayrılmış.
- Local runbook referansı var.
- Guardrail'ler açık.
- CI implementasyonu yapılmadı.
- Lokal Docker volume riskleri açıklanmış.
- Station/location API'nin read-only kapsamı korunmuş.

## 8. Sonraki Adım

- Bu plan onaylandıktan sonra ilk teknik adım CI'ya yalnız Tier 1 offline unit/API testlerini eklemek olabilir.
- Containerized API smoke ayrı future fazdır.
- UI/Kiosk entegrasyonu bu CI planından bağımsız bir sonraki ürün fazı olarak ele alınmalıdır.
