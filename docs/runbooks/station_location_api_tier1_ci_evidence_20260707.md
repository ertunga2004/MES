# Station/Location API Tier 1 CI Evidence - 2026-07-07

## 1. Amaç

- Bu doküman, station/location read-only API için eklenen Tier 1 offline
  GitHub Actions workflow'unun push sonrası başarıyla çalıştığını kaydeder.
- Bu evidence CI run metadata'sına dayanır.
- Bu tur Docker, PostgreSQL, HTTP smoke, migration veya MESQL içermez.

## 2. Kapsam

Kapsamdaki workflow:

```text
.github/workflows/station-location-api-tier1.yml
```

Workflow adı:

```text
Station Location API Tier 1
```

Kapsamdaki testler:

```text
python -m unittest tests.test_mes_web_station_location_api
python -m unittest tests.test_mes_web_mesql_v2
```

Kapsam dışı:

- Docker yok.
- PostgreSQL yok.
- DB bağlantısı yok.
- psql yok.
- HTTP API smoke yok.
- SQL migration yok.
- MESQL yok.
- Operation lifecycle real DB smoke yok.
- UI/Kiosk yok.

## 3. Commit ve Run Bilgisi

```text
latest commit: 329ffbe "ci: add station location api tier1 tests"
branch: main
workflow name: Station Location API Tier 1
run id: 28867373267
job id: 85620827055
status: completed
conclusion: success
job: Offline unit/API tests
duration: 12s
URL: https://github.com/ertunga2004/MES/actions/runs/28867373267
```

## 4. Test Sonucu Yorumu

- Workflow step `Run station/location API Tier 1 tests` success döndü.
- Bu step iki Tier 1 offline test modülünü çalıştırmak üzere tasarlanmıştır:
  - `tests.test_mes_web_station_location_api`
  - `tests.test_mes_web_mesql_v2`
- `gh run view 28867373267 --log` log indirme denemesi GitHub API'den
  `HTTP 403: Must have admin rights to Repository` döndürdüğü için
  `Ran 14 tests`, `Ran 27 tests`, `OK` satırları doğrudan logdan
  okunamamıştır.
- Buna rağmen run/job/step metadata'sı `completed/success` olduğu için Tier 1
  CI doğrulaması PASS kabul edilmiştir.

## 5. Annotation Notu

- GitHub annotation olarak `actions/checkout@v4` ve `actions/setup-python@v5`
  için Node.js 20 deprecation uyarısı görülmüştür.
- Bu uyarı workflow fail sebebi değildir.
- Şu an aksiyon gerektirmez.
- Gelecekte GitHub Actions major version güncellemesi sırasında ele
  alınabilir.

## 6. Guardrails

- Kod değişmedi.
- Workflow değişmedi.
- Test değişmedi.
- DB yok.
- Docker yok.
- PostgreSQL yok.
- psql yok.
- HTTP smoke yok.
- MESQL yok.
- Migration yok.
- Operation lifecycle real DB smoke yok.
- UI/Kiosk yok.
- Commit/push yok.

## 7. Hüküm

```text
Station/location read-only API için Tier 1 offline CI workflow'u GitHub Actions üzerinde başarıyla çalışmış ve completed/success sonucu üretmiştir. Log satırları yetki nedeniyle doğrudan indirilememiş olsa da run/job/step metadata'sı test step'inin başarıyla tamamlandığını göstermektedir. Bu nedenle Tier 1 CI checkpoint PASS kabul edilmiştir.
```

## 8. Sonraki Adım

- Evidence commit sonrası Tier 1 CI fazı kapanır.
- Sonraki ürün/mimari karar: UI/Kiosk tarafında station/location context'in
  read-only gösterimi mi, yoksa future containerized API smoke planının
  ilerletilmesi mi?
- Şimdilik containerized smoke future fazdır.
