# Configurable MES Execution Core

Bu repository, farklı üretim sistemlerine uyarlanabilen yerel bir üretim
yürütme çekirdeğini geliştirir. Mevcut konveyör, sensörler ve robot kol bu
mimarinin fiziksel doğrulama platformu ve reference plant'idir; projenin ürün
sınırı yalnız bu hatta özgü değildir.

## Proje amacı

MES; iş emri lifecycle'ı, rota/operasyon yürütme, istasyon kuyruğu,
config-driven station execution, operatör kiosk'u, MQTT/IoT adaptörleri, audit
ve OEE görünürlüğünü kontrollü sözleşmelerle bir araya getirir. Uzun vadeli
sanal üretim kaynağı, dijital tesis ve agent destekli karar altyapısı roadmap
kapsamındadır; bugün uygulanmış capability olarak kabul edilmez.

## Güncel doğrulanmış yetenekler

- FastAPI tabanlı dashboard, operatör kiosk'u ve teknisyen ekranı.
- Yerel PostgreSQL üzerinde work-order route release, deterministic lifecycle
  kimlikleri, station queue ve runtime completion bridge.
- Kiosk ve canonical MQTT ingress için ortak, config-driven station-execution
  application boundary.
- Manual/manual, implicit/manual, manual/implicit, configured-source
  implicit/implicit ve source-less internal implicit/implicit transition
  kombinasyonları.
- Lifecycle/route/step/action kimliği, idempotent replay ve deterministic
  conflict davranışı.
- Canonical MQTT yolu için persistent session, generation-aware callback'ler
  ve terminal transaction sonucundan sonra manual ACK.
- Workbook/OEE/runtime yolları retained compatibility ve audit sınırı olarak
  korunur.

Ayrıntılı ve tarihli doğrulama için
[Current State](docs/architecture/CURRENT_STATE.md) belgesini kullanın.

## Sistem sınırları

- `MES`, bu repository'de aktif geliştirilen yerel production-execution
  sistemidir.
- `MESQL`, ayrı merkezi entegrasyon/veri çekirdeği çalışmasıdır ve açıkça
  scope'a alınmadıkça frozen/deferred kabul edilir.
- Fiziksel hareket ve emniyet otoritesi firmware/control katmanındadır; MES Web
  üretim bağlamı, kayıt, orchestration ve kullanıcı etkileşimini yönetir.
- Fiziksel ve sanal event kaynakları explicit adapter/contract üzerinden sisteme
  girmelidir.
- Feature-flagged bir capability, flag açıkça etkinleştirilmeden varsayılan
  production davranışı değildir.

## Repository haritası

- `mes_web/`: FastAPI uygulaması, runtime, MQTT ve DB integration kodu.
- `tests/`: offline unit/API ve deterministic concurrency testleri.
- `db/`: MES migration ve seed artefaktları.
- `docker/mes/`: kontrollü Docker/PostgreSQL runtime ve launcher'lar.
- `Baslaticilar/`: Windows uygulama launcher'ları.
- `CPP/`, `raspberry/`, `picktolight/`: fiziksel/edge/reference bileşenler.
- `docs/architecture/`: canonical state, phase boundary ve tasarım belgeleri.
- `docs/runbooks/`: apply/smoke planları ve immutable execution evidence.

## Hızlı başlangıç

Güvenli local varsayılan olarak proje-local Python ortamıyla loopback üzerinde
çalıştırın:

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r .\mes_web\requirements.txt
$env:MES_WEB_HOST = '127.0.0.1'
$env:MES_WEB_PORT = '8080'
& '.\.venv\Scripts\python.exe' -m mes_web
```

Windows launcher seçeneği:

```powershell
& '.\Baslaticilar\MES Web.cmd'
```

Bu launcher doğrulanmış mevcut davranışında `MES_WEB_HOST=0.0.0.0` kullanır ve
dashboard/Kiosk yüzeyini aynı ağdan erişilebilir yapar. Repository'de genel bir
authentication katmanı yoktur; launcher yalnız trusted local network üzerinde
ve write feature flag'leri kontrol edildikten sonra kullanılmalıdır. Yalnız bu
PC'den erişim için yukarıdaki `127.0.0.1` manuel komutunu tercih edin.

Offline test keşfi:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_mes_web_*.py'
```

Launcher ayrıntıları için [Baslaticilar](Baslaticilar/README.md), uygulama
arayüzleri için [MES Web](mes_web/README.md), Docker seçenekleri için
[Docker MES](docker/mes/README.md) belgelerine bakın.

## Güvenlik notları

- Production `mes` DB write, migration apply, physical broker testi ve source
  rollout ayrı açık görev/onay gerektirir.
- `.env`, secret, dump, backup ve runtime output commit edilmez.
- Database doğrulamasında mümkün olduğunda disposable clone kullanılır.
- Historical FAIL evidence silinmez; sonraki PASS yalnız kendi kapsamını açıkça
  supersede eder.
- Push yalnız açık kullanıcı talimatıyla yapılır.

## Dokümantasyon haritası

- [Current verified state](docs/architecture/CURRENT_STATE.md)
- [Phase 6A acceptance evidence](docs/runbooks/phase_6a_station_integration_acceptance_evidence_20260719.md)
- [Phase 6B entry boundary](docs/architecture/PHASE_6B_ENTRY.md)
- [Documentation index](docs/INDEX.md)
- [Repository agent instructions](AGENTS.md)

## Güncel faz

Phase 6A station integration, commit `ae023142058a0a5fa79c6b99e257097abbde8dd1`
ile doğrulanmıştır. Phase 6B implementation `NOT_STARTED`; başlamadan önce
[Phase 6B Entry](docs/architecture/PHASE_6B_ENTRY.md) gate'i karşılanmalıdır.
