# MES Docker Infrastructure

This folder contains only the Docker infrastructure for MES.

MES source code:

```text
C:\Users\ertun\Documents\.CODE\codex\MES
```

MES Docker infrastructure:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES
```

The MES source code folder must not be deleted, moved, or restructured by this Docker setup.

## Current Boundary

PostgreSQL is only ready infrastructure in this phase.

The current MES application does not use PostgreSQL as source-of-truth. These existing boundaries remain unchanged:

- Excel workbook output
- `logs/oee_runtime_state.json`
- FERP import/export files
- runtime state

This setup defaults to `MES_WEB_DB_ENABLED=false` via `.env` overrides. No migration, SQL table design, MESQL DB, BOM_BOP DB, Redis, RabbitMQ, MinIO, TimescaleDB, pgvector, OpenSearch, or ClickHouse is included.

`mes_web` does not depend on `mes_postgres` for startup in this phase.

**DB Configuration Note:**
- DB flagleri default `false`.
- Runtime work_orders mirror sadece iki flag (`MES_WEB_DB_ENABLED` ve `MES_WEB_DB_MIRROR_WORK_ORDERS`) `true` ise çalışır.
- Container içinden DB host `mes_postgres:5432`.
- Hosttan bağlantı `localhost:5433`.
- Bu source-of-truth geçişi değildir. Runtime DB read yoktur; JSON/Excel/FERP akışı aynen korunmaktadır.
- C2 Canlı Docker Mirror Hook doğrulaması başarıyla yapılmıştır (2026-06-08).


## Services

| Service | Container | Host access | Internal port | Purpose |
|---|---|---:|---:|---|
| `mes_web` | `mes_web` | `http://127.0.0.1:8080` | `8080` | MES Web |
| `mes_postgres` | `mes_postgres` | `localhost:5433` | `5432` | PostgreSQL ready infrastructure |
| `mes_adminer` | `mes_adminer` | `http://127.0.0.1:8082` | `8080` | Adminer |

Adminer login server value:

```text
mes_postgres
```

## Launcher Inventory (.cmd Scripts)

To keep the `docker/mes` root clean, individual launcher scripts have been moved to the `launchers/` subdirectory. A unified control menu is provided at the root.

**Main Control Menu:**
- `MES_CONTROL.cmd`: The primary, interactive menu to start, stop, and manage all MES Docker environments. It provides options for portable mode, development mode, and maintenance. This is the recommended entry point for daily use.

**Underlying Scripts (in `launchers/`):**

If you prefer direct execution, you can run the scripts in the `launchers/` folder. All scripts safely resolve their working directory to the `docker/mes` root.

| Script | Role | Group | Notes |
|---|---|---|---|
| `launchers\development\start_mes.cmd` | Start dev mode | Development | Uses `compose.yaml` with bind mounts |
| `launchers\development\stop_mes.cmd` | Stop dev mode | Development | |
| `launchers\development\restart_mes.cmd` | Restart dev mode | Development | |
| `launchers\development\status_mes.cmd` | Show dev status/logs | Dev Status | |
| `launchers\portable\start_mes_portable.cmd`| Start portable mode | Portable | Uses `compose.portable.yaml` (image based) |
| `launchers\portable\stop_mes_portable.cmd` | Stop portable mode | Portable | |
| `launchers\portable\restart_mes_portable.cmd`| Restart portable mode | Portable | Calls stop then start scripts |
| `launchers\portable\status_mes_portable.cmd`| Show portable status | Port Status | |
| `launchers\portable\build_mes_portable.cmd`| Build portable image | Port Build | Calls `sync_mes_source.cmd` first |
| `launchers\portable\sync_mes_source.cmd` | Sync `app_source/` | Internal | Prepares the `Dockerfile.mes_web.portable` context |
| `launchers\maintenance\backup_mes_db.cmd` | Dump PostgreSQL DB | Backup | Writes to `data/db_backups/` |
| `launchers\maintenance\export_mes_portable_bundle.cmd`| Create bundle | Export | Calls build and backup scripts, writes to `exports/` |

**Important Note:** The paths for `app_source`, `data`, `exports`, and `.env` remain exactly the same (in the `docker/mes` root).

For detailed documentation, refer to `docs/agent_memory/11_launcher_inventory.md`.

## Port Warning

Port `8080` belongs to `mes_web`.

If Docker `mes_web` will run, any manually started Windows `mes_web` must be stopped first. They cannot both use host port `8080` at the same time.

## MES_CODE_ROOT Bind Mount

The first phase uses a development-style bind mount:

```text
MES_CODE_ROOT=C:/Users/ertun/Documents/.CODE/codex/MES
```

This keeps the current MES source code outside the Docker infrastructure folder and mounts it into the container as read-only `/app`.

This is convenient for development, but it is not fully portable. On a new PC, if the MES source tree is in another path, update `.env`.

A fully portable mode can be planned later by copying the source code into the image during build. That is intentionally not done in this task.

## Setup

Create a local `.env` from the example:

```cmd
copy .env.example .env
```

Then edit `.env` if needed.

Change `POSTGRES_PASSWORD` before using this outside a local prototype environment. The example password is only a local default.

## Start

```cmd
start_mes.cmd
```

Equivalent manual command:

```cmd
docker compose up -d --build
```

MES Web:

```text
http://127.0.0.1:8080
```

Adminer:

```text
http://127.0.0.1:8082
```

PostgreSQL from host:

```text
localhost:5433
```

PostgreSQL from containers:

```text
mes_postgres:5432
```

## Stop

```cmd
stop_mes.cmd
```

This runs `docker compose down` and does not remove the PostgreSQL volume.

## Restart

```cmd
restart_mes.cmd
```

## Status

```cmd
status_mes.cmd
```

## Backup PostgreSQL

```cmd
backup_mes_db.cmd
```

Backups are written under:

```text
data\db_backups
```

This backs up only PostgreSQL. It does not replace the current MES Excel/JSON/FERP runtime files.

## Data Locations

Docker infrastructure local data:

```text
data\
```

Important subfolders created by containers or scripts:

- `data\logs` is mounted to `/app/logs` for MES workbook/runtime outputs.
- `data\db_backups` stores PostgreSQL backups made by `backup_mes_db.cmd`.
- `data\work_orders` is available for future explicit work order import experiments, but the current app still keeps its existing default import behavior unless configured otherwise.

The named Docker volume `mes_postgres_data` stores PostgreSQL data.

## Verification

```cmd
docker compose config
docker compose ps
```

Health check:

```text
http://127.0.0.1:8080/health
```

Adminer:

```text
http://127.0.0.1:8082
```

Use these Adminer values:

```text
System: PostgreSQL
Server: mes_postgres
Username: mes
Password: value from .env
Database: mes
```

## Faz 1 Doğrulama Sonucu

Tarih: 2026-06-05

Faz 1 Docker doğrulaması tamamlandı.

Başarılı doğrulamalar:

- Docker Desktop, WSL 2 ve Ubuntu çalışıyor.
- `docker run hello-world` başarılı.
- `docker compose config` başarılı.
- `mes_postgres` healthy durumda.
- `mes_adminer` çalışıyor.
- `mes_web` build edildi ve `8080` portunda çalışıyor.
- Adminer `8082` portunda açılıyor.
- PostgreSQL bağlantısı Adminer üzerinden doğrulandı.
- `backup_mes_db.cmd` çalışıyor.

Korunan sınırlar:

- MES uygulama koduna dokunulmadı.
- Migration oluşturulmadı.
- SQL tablo tasarımı yapılmadı.
- Excel workbook akışı değiştirilmedi.
- JSON runtime state akışı değiştirilmedi.
- FERP import/export akışı değiştirilmedi.

Faz 1 sonucu: Docker altyapısı geliştirme tipi kullanım için doğrulandı. PostgreSQL bu fazda yalnızca hazır altyapıdır; mevcut MES uygulaması PostgreSQL'i source-of-truth olarak kullanmaz.

## Faz 2 Tam Taşınabilir Mod

Faz 1 geliştirme modu kaynak kodu runtime sırasında bind mount ile kullanır:

```text
C:\Users\ertun\Documents\.CODE\codex\MES -> /app
```

Faz 2 portable mode kaynak kodu Docker image içine build sırasında kopyalar. Portable mode çalışırken `/app` için `MES_CODE_ROOT` bind mount kullanılmaz. Yeni PC'de `C:\Users\ertun\Documents\.CODE\codex\MES` yolunun bulunması gerekmez.

Portable mode dosyaları:

- `compose.portable.yaml`
- `Dockerfile.mes_web.portable`
- `sync_mes_source.cmd`
- `build_mes_portable.cmd`
- `start_mes_portable.cmd`
- `stop_mes_portable.cmd`
- `restart_mes_portable.cmd`
- `status_mes_portable.cmd`
- `export_mes_portable_bundle.cmd`
- `app_source\` kaynak snapshot klasörü
- `exports\` portable export klasörü

Korunan sınırlar:

- Mevcut MES uygulama kodu değiştirilmez.
- Migration oluşturulmaz.
- SQL tablo tasarımı yapılmaz.
- Excel workbook akışı değiştirilmez.
- JSON runtime state akışı değiştirilmez.
- FERP import/export akışı değiştirilmez.
- MQTT, ESP32, bridge, vision veya yeni servis eklenmez.

Portable mode'da sadece veri amaçlı mountlar kalır:

```text
./data/logs:/app/logs
./data/work_orders:/data/work_orders
./data/db_backups:/backups
```

`./data/db_backups:/backups` PostgreSQL container tarafında kullanılır. PostgreSQL verisi image içine alınmaz; `mes_postgres_data` Docker volume içinde kalır ve SQL backup ile taşınır.

### Portable Kaynak Snapshot

Kaynak snapshot almak için:

```cmd
sync_mes_source.cmd
```

Varsayılan kaynak:

```text
C:\Users\ertun\Documents\.CODE\codex\MES
```

Snapshot hedefi:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\app_source
```

Snapshot sırasında şu içerikler hariç tutulur:

- `.git`
- `.venv`
- `venv`
- `__pycache__`
- `.pytest_cache`
- `.mypy_cache`
- `node_modules`
- `dist`
- `build`
- runtime `logs`
- büyük log/geçici/backup dosyaları
- `.env`

### Portable Build

Portable image üretmek için:

```cmd
build_mes_portable.cmd
```

Bu komut önce `sync_mes_source.cmd` çalıştırır, sonra image build eder:

```cmd
docker compose -f compose.portable.yaml build mes_web
```

Üretilen image:

```text
mes_web_portable:latest
```

### Portable Start / Stop

Portable modu başlatmadan önce Faz 1 geliştirme modu çalışıyorsa durdur:

```cmd
docker compose down
```

Portable modu başlat:

```cmd
start_mes_portable.cmd
```

Kullanılan adresler:

```text
MES Web : http://127.0.0.1:8080
Adminer : http://127.0.0.1:8082
PostgreSQL host portu: localhost:5433
Adminer server: mes_postgres
```

Portable modu durdur:

```cmd
stop_mes_portable.cmd
```

Bu komut `docker compose -f compose.portable.yaml down` çalıştırır. `-v` kullanmaz ve volume silmez.

Portable modu yeniden başlat:

```cmd
restart_mes_portable.cmd
```

Durum kontrolü:

```cmd
status_mes_portable.cmd
```

Bu komut servisleri ve Docker volume listesini gösterir:

```cmd
docker compose -f compose.portable.yaml ps
docker volume ls
```

### Portable Export

Portable bundle hazırlamak için:

```cmd
export_mes_portable_bundle.cmd
```

Bu komut:

- `exports\` klasörünü kullanır.
- `mes_web_portable:latest` image yoksa önce build eder.
- `backup_mes_db.cmd` ile PostgreSQL backup almayı dener.
- Mümkünse şu image'ları tek tar dosyasına export eder:
  - `mes_web_portable:latest`
  - `postgres:16-alpine`
  - `adminer:4`

Örnek image export çıktısı:

```text
exports\mes_portable_images_YYYY-MM-DD_HH-MM-SS.tar
```

Restore notu da aynı klasöre yazılır:

```text
exports\mes_portable_restore_YYYY-MM-DD_HH-MM-SS.txt
```

### Yeni PC'ye Taşıma Özeti

Tam taşıma için önerilen sıra:

1. `build_mes_portable.cmd`
2. `backup_mes_db.cmd`
3. `export_mes_portable_bundle.cmd`
4. `.DOCKER\MES` klasörünü yeni PC'ye kopyala.
5. Yeni PC'de Docker Desktop + WSL 2 kur.
6. Image tar dosyasını içeri al:

```cmd
docker load -i exports\mes_portable_images_YYYY-MM-DD_HH-MM-SS.tar
```

7. Portable modu başlat:

```cmd
start_mes_portable.cmd
```

8. Gerekirse SQL backup restore et.

Not: PostgreSQL verisi Docker image içinde değildir. DB taşıma için `data\db_backups` altındaki SQL backup kullanılmalıdır.

### Portable Doğrulama

1. Geliştirme modunu durdur:

```cmd
docker compose down
```

2. Portable build:

```cmd
.\build_mes_portable.cmd
```

3. Portable başlat:

```cmd
.\start_mes_portable.cmd
```

4. Servis kontrol:

```cmd
docker compose -f compose.portable.yaml ps
```

5. MES Web kontrol:

```text
http://127.0.0.1:8080
```

6. Adminer kontrol:

```text
http://127.0.0.1:8082
```

7. `/app` için kaynak kod bind mount olmadığını doğrula:

```cmd
docker inspect mes_web --format "{{range .Mounts}}{{println .Type .Source \"->\" .Destination}}{{end}}"
```

Bu kontrolde şu bind mount görünmemelidir:

```text
C:\Users\ertun\Documents\.CODE\codex\MES -> /app
```

## Faz 2 Doğrulama Sonucu

Tarih: 2026-06-05

Faz 2 portable mode doğrulaması tamamlandı.

Başarılı doğrulamalar:

- Portable compose config başarılı.
- `build_mes_portable.cmd` başarılı.
- `start_mes_portable.cmd` başarılı.
- `mes_web` portable image ile çalıştı.
- `/app` için kaynak kod bind mount kaldırıldı.
- `docker inspect` çıktısında yalnızca `data\logs -> /app/logs` ve `data\work_orders -> /data/work_orders` mountları görüldü.
- `C:\Users\ertun\Documents\.CODE\codex\MES -> /app` mountu görünmedi.
- `export_mes_portable_bundle.cmd` başarılı çalıştı.
- PostgreSQL backup üretildi.
- Docker image export tar dosyası üretildi.
- Restore notu üretildi.

Korunan sınırlar:

- MES uygulama koduna dokunulmadı.
- `compose.yaml` değiştirilmedi.
- `compose.portable.yaml` değiştirilmedi.
- Dockerfile dosyaları değiştirilmedi.
- CMD dosyaları değiştirilmedi.
- Migration oluşturulmadı.
- SQL tablo tasarımı yapılmadı.
- Excel, JSON ve FERP runtime akışı değiştirilmedi.

Faz 2 sonucu: Portable mode doğrulandı. `mes_web` artık portable modda kaynak kodu `/app` bind mountu olmadan, image içine kopyalanmış uygulama snapshot'ı ile çalışabilir.

## Rollback

Stop containers without deleting data:

```cmd
docker compose down
```

Removing the PostgreSQL Docker volume is destructive and should only be done with explicit confirmation:

```cmd
docker compose down -v
```
