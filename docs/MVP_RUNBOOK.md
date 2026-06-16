# MES SQL MVP — Runbook

> Operasyonel referans. Sistemi başlat, test et, yedekle, sorun gider.

---

## 1. Sistemi Başlatma

```powershell
# Proje klasörüne git
cd C:\Users\ertun\Documents\.CODE\.DOCKER\MES

# Servisleri başlat (arka planda)
docker compose up -d --build

# Servislerin ayağa kalkmasını bekle (~15 sn)
docker compose ps
```

**Beklenen servisler:**

| Servis         | Container      | Port  | Açıklama          |
|----------------|----------------|-------|--------------------|
| mes_web        | mes_web        | 8080  | MES Web uygulama   |
| mes_postgres   | mes_postgres   | 5433  | PostgreSQL 16       |
| mes_adminer    | mes_adminer    | 8082  | DB yönetim arayüzü  |

**Kontrol:**
```powershell
# Health check
curl http://localhost:8080/health
# Beklenen: {"status":"ok","time":"..."}
```

---

## 2. Smoke Test Çalıştırma

```powershell
cd C:\Users\ertun\Documents\.CODE\.DOCKER\MES
powershell -ExecutionPolicy Bypass -File tools/mvp_smoke_check.ps1
```

**Ne kontrol eder:**
- Docker container durumları (mes_web, mes_postgres, mes_adminer)
- `/health` endpoint HTTP 200
- Container DB flag'leri (MES_WEB_DB_ENABLED, hook'lar, dry-run'lar)
- Tablo satır sayıları (work_orders, work_order_events, production_completions, item_station_events)
- Duplicate detection (external_ref / source+external_ref)
- Dashboard & Kiosk erişilebilirliği
- Aktif/pending work order görünürlüğü

**Çıktı:** `PASS` veya `FAIL` + detay listesi

---

## 3. Backup Alma

```powershell
# Gerçek backup
cd C:\Users\ertun\Documents\.CODE\.DOCKER\MES
powershell -ExecutionPolicy Bypass -File tools/mvp_backup_runtime.ps1

# Dry-run (dosya yazmadan test)
powershell -ExecutionPolicy Bypass -File tools/mvp_backup_runtime.ps1 -DryRun
```

**Neler yedeklenir:**

| Artefakt                      | Açıklama                          |
|-------------------------------|-----------------------------------|
| `mes_full_<ts>.sql`           | PostgreSQL tam dump                |
| `.env`                        | Çalışma zamanı konfigürasyon       |
| `compose.yaml`                | Docker Compose tanımı              |
| `compose.portable.yaml`       | Portable Compose tanımı            |
| `oee_runtime_state.json`      | OEE runtime durum dosyası          |
| `app_source/`                 | Uygulama kaynak kodu snapshot      |
| `manifest.json`               | Backup manifest (içerik listesi)   |

**Backup konumu:** `deploy_backups/mvp_runtime_<yyyyMMdd-HHmmss>/`

---

## 4. Sorun Olursa — İlk 5 Kontrol

### 1️⃣ Container logları
```powershell
docker logs mes_web --tail 50
docker logs mes_postgres --tail 50
```

### 2️⃣ Container health durumu
```powershell
docker inspect --format '{{.State.Health.Status}}' mes_postgres
docker inspect --format '{{.State.Status}}' mes_web
```

### 3️⃣ .env DB flag'leri
```powershell
# Dosyayı oku — DRY_RUN flag'lerin false olduğundan emin ol
type .env | findstr /i "DB_ENABLED HOOK_ DRY_RUN READ_"
```

### 4️⃣ PostgreSQL bağlantı testi
```powershell
docker exec mes_postgres psql -U mes -d mes -c "SELECT 1;"
# Tablo kontrol
docker exec mes_postgres psql -U mes -d mes -c "\dt mes.*"
```

### 5️⃣ OEE runtime state dosyası
```powershell
# Dosya var mı ve boyutu ne?
dir data\logs\oee_runtime_state.json
# Son değişiklik zamanı makul mü?
```

---

## 5. Rollback — Backup'tan Geri Yükleme

### Mevcut backup klasörleri
```powershell
dir deploy_backups\
# Örnek çıktı:
#   mesql_sql_sot_20260616-132702/
#   work_order_transition_fix_20260616-231203/
#   mvp_runtime_20260617-001500/
```

### PostgreSQL restore
```powershell
# 1. Backup klasöründeki SQL dosyasını container'a kopyala
copy deploy_backups\mvp_runtime_<ts>\mes_full_<ts>.sql data\db_backups\

# 2. Container içinden restore
docker exec mes_postgres psql -U mes -d mes -f /backups/mes_full_<ts>.sql
```

### Konfigürasyon restore
```powershell
# Backup'tan .env ve compose dosyalarını geri kopyala
copy deploy_backups\mvp_runtime_<ts>\.env .env
copy deploy_backups\mvp_runtime_<ts>\compose.yaml compose.yaml

# Servisleri yeniden başlat
docker compose up -d --build
```

### OEE state restore
```powershell
copy deploy_backups\mvp_runtime_<ts>\oee_runtime_state.json data\logs\
```

> ⚠️ **DİKKAT:** Restore sonrasında `tools/mvp_smoke_check.ps1` çalıştırarak sistemi doğrula.

---

## Hızlı Referans

| İşlem                | Komut                                                                    |
|----------------------|--------------------------------------------------------------------------|
| Başlat               | `docker compose up -d --build`                                           |
| Durdur               | `docker compose stop`                                                    |
| Smoke test           | `powershell -ExecutionPolicy Bypass -File tools/mvp_smoke_check.ps1`     |
| Backup               | `powershell -ExecutionPolicy Bypass -File tools/mvp_backup_runtime.ps1`  |
| Backup (dry-run)     | `... tools/mvp_backup_runtime.ps1 -DryRun`                              |
| DB shell             | `docker exec -it mes_postgres psql -U mes -d mes`                       |
| Web logları          | `docker logs mes_web --tail 100 -f`                                      |
| Adminer              | `http://localhost:8082`                                                   |
