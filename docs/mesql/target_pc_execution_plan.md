# MESQL Read-Only Compatibility Report — Target PC Execution Plan

**Kaynak:** `main = b83e860`, tag `mesql-read-only-compatibility-reports-ok`  
**Kapsam:** Yalnızca planlama ve risk analizi. Kod değişikliği, migration, Docker komutu veya DB yazma bu belgede yoktur.

---

## Verdict

> **Execution planı güvenli olarak hazırlandı.**  
> Aşağıdaki sıra izlendiği ve her adımda durum doğrulandığı sürece rapor çalıştırılabilir.  
> Backup alınmadan hiçbir adıma geçilemez. Rapor FAIL içeriyorsa migration planlamaya geçilemez.

---

## Preconditions (Ön Koşullar)

### P1 — Doğru Branch / Tag

Hedef PC'de kaynak repo doğru commit'te olmalı:

```
git status          → temiz working tree, no uncommitted changes
git log --oneline -3
# beklenen: b83e860 en üstte
git tag --points-at HEAD
# beklenen: mesql-read-only-compatibility-reports-ok
```

> **Stop koşulu:** Working tree kirli veya HEAD farklı commit'teyse önce senkronize et.

### P2 — Docker Servislerinin Durumu

Compose dosyası: `<portable-runtime-root>\compose.yaml`

Beklenen çalışan servisler ve container adları:

| Servis | Container adı | Hedef PC host port |
|---|---|---|
| PostgreSQL | `mes_postgres` | `localhost:5433` |
| MES Web | `mes_web` | `localhost:8080` |
| Adminer (opsiyonel) | `mes_adminer` | `localhost:8082` |

Durum kontrol taslağı:
```
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
Beklenen çıktıda `mes_postgres` için `healthy` görünmeli.

> **Stop koşulu:** `mes_postgres` `Up (healthy)` değilse rapor çalıştırılamaz.

### P3 — DB Adı / User Bilgisi Nereden Doğrulanır

Compose ve `.env.example`'dan elde edilen defaults:

| Parametre | Default değer | Doğrulama yeri |
|---|---|---|
| DB adı (`POSTGRES_DB`) | `mes` | `.env` dosyası → compose.yaml |
| DB user (`POSTGRES_USER`) | `mes` | `.env` dosyası → compose.yaml |
| Container içi port | `5432` | compose.yaml |
| Host port | `5433` | compose.yaml |
| Şifre | `.env` → `POSTGRES_PASSWORD` | `.env` dosyası (commit edilmez) |

`.env` dosyası hedef PC'de compose klasöründe (`c:\..\.DOCKER\MES\.env`) bulunmalı ve commit edilmemiş olmalı. Doğrulama:

```
# .env içeriğini okuyun (şifre ekrana gelebilir, dikkatli olun)
type .env | findstr POSTGRES
```

### P4 — Migration Chain 001–007 Uygulanmış mı?

Migration chain durumunu doğrulamak için **read-only** bir tablo kontrol sorgusu çalıştırılır (migration tablo yoksa FAIL verir):

```sql
-- Taslak doğrulama sorgusu — veri değiştirmez
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'mes'
ORDER BY table_name;
```

Beklenen en az şu tablolar listede görünmeli:

```
ferp_export_outbox, ferp_import_batches, item_station_events,
oee_snapshots, package_bom_lines, package_component_wip,
package_sessions, package_traceability, production_completions,
quality_overrides, station_queue, stations, vision_events,
work_order_events, work_orders
```

> **Stop koşulu:** `mes` şeması yoksa veya tablolar eksikse 001–007 migration'larını önce uygulamanız gerekir. Bu execution planının kapsamı dışındadır; ayrı onay ve rollback planı gerektirir.

---

## Backup Öncesi Kontrol

### B1 — Hangi Dosyalar / DB Dump Alınmalı

| Kapsam | Dosya / hedef | Neden |
|---|---|---|
| PostgreSQL DB dump | `data\db_backups\mes_GGAAYYYY_HHSS.dump` | Migration öncesi veri kanıtı |
| Runtime state JSON | `data\logs\oee_runtime_state.json` | Runtime source-of-truth korunması |
| FERP export/import state | `data\logs\ferp_exports\` | ERP entegrasyon izlenebilirliği |
| `.env` dosyası | Ayrı güvenli konuma kopyala | Config drift önleme |

### B2 — Backup Taslak Komutları

> ⚠️ Aşağıdaki komutlar yalnızca taslaktır. Çalıştırmadan önce container adını ve path'i `.env` içeriğiyle doğrula.

**A) `backup_mes_db.cmd` kullanarak (önerilen — mevcut script):**
```cmd
cd <portable-runtime-root>\launchers\maintenance
backup_mes_db.cmd
```
Backup `data\db_backups\` altına yazılır.

**B) Manuel pg_dump taslağı (backup_mes_db.cmd kullanılamıyorsa):**
```cmd
docker exec mes_postgres pg_dump -U mes -d mes -Fc -f /backups/mes_pre_compat_report.dump
```
Dump, compose volume üzerinden `data\db_backups\mes_pre_compat_report.dump` olarak erişilir.

**C) Runtime JSON dosyaları yedek taslağı:**
```cmd
xcopy /E /I data\logs data\logs_backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%
```

> **Stop koşulu:** Backup başarısız veya backup dosyası 0 byte ise rapor çalıştırılamaz.

---

## Execution Sequence

### Adım 1 — Durum Kontrol (read-only)

```cmd
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
- `mes_postgres` → `Up (healthy)` görünmeli
- Görünmüyorsa: stop, servisleri başlat, tekrar kontrol et

### Adım 2 — Migration Chain Kontrolü (read-only)

```cmd
docker exec -i mes_postgres psql -U mes -d mes -c "\dt mes.*"
```
Tablo listesi yukarıdaki P4 beklentisiyle karşılaştırılır.

### Adım 3 — Backup Al

`backup_mes_db.cmd` çalıştır. Backup dosyasının `data\db_backups\` altında oluştuğunu ve 0 byte olmadığını doğrula:
```cmd
dir data\db_backups\
```

### Adım 4 — Quickcheck Raporu Çalıştır

> SQL dosyası: `db/reports/compatibility/runtime_mes_compatibility_report.quickcheck.sql`  
> Bu dosya yalnızca `SELECT` içerir. Veri değiştirmez.

**Taslak komut — container içinden:**
```cmd
docker exec -i mes_postgres psql -U mes -d mes ^
  -f /app/db/reports/compatibility/runtime_mes_compatibility_report.quickcheck.sql ^
  --tuples-only --no-align -F"|" ^
  > quickcheck_result_%date:~-4,4%%date:~-10,2%%date:~-7,2%.txt 2>&1
```

> **Not:** `/app/` path'i compose.yaml'daki bind mount'tan gelir. `MES_CODE_ROOT` bind mount hedef PC'de farklıysa path güncellenmeli. Alternatif: SQL dosyasını önce host'a kopyalayıp `docker cp` ile container'a aktarabilirsiniz.

**Alternatif — host'ta psql kuruluysa:**
```cmd
psql -h localhost -p 5433 -U mes -d mes ^
  -f "c:\..\.CODE\codex\MES\db\reports\compatibility\runtime_mes_compatibility_report.quickcheck.sql" ^
  --tuples-only --no-align -F"|" ^
  > quickcheck_result_%date:~-4,4%%date:~-10,2%%date:~-7,2%.txt
```

**Hata olursa ne yapılır:**
- `ERROR: relation "mes.xxx" does not exist` → Migration eksik. Stop. Migration planlamaya geç.
- `FATAL: password authentication failed` → `.env` şifresini doğrula.
- Çıktı boş → `--tuples-only` ile boş satır geliyorsa bu normaldir; `finding_count = 0` iyi sonuçtur.

### Adım 5 — Quickcheck Sonucunu Oku

Çıktı formatı (`|` delimiter):
```
check_group|check_name|severity|finding_count|sample_value|recommendation
```

Quickcheck Go/No-Go:

| Durum | Karar |
|---|---|
| Tüm FAIL satırlarında `finding_count = 0` | → Full raporu çalıştır |
| Herhangi bir FAIL satırında `finding_count > 0` | → STOP. Full raporu çalıştırma. Cleanup planı yaz. |
| Sadece WARN/INFO | → Full raporu çalıştır, daha dikkatli izle |

### Adım 6 — Full Report Çalıştır

> SQL dosyası: `db/reports/compatibility/runtime_mes_compatibility_report.sql`  
> Bu dosya yalnızca `SELECT` içerir. Veri değiştirmez.

**Taslak komut:**
```cmd
docker exec -i mes_postgres psql -U mes -d mes ^
  -f /app/db/reports/compatibility/runtime_mes_compatibility_report.sql ^
  --tuples-only --no-align -F"|" ^
  > full_compat_report_%date:~-4,4%%date:~-10,2%%date:~-7,2%.txt 2>&1
```

**WARN/FAIL nasıl yorumlanır:**

| Severity | Anlam | Eylem |
|---|---|---|
| `INFO` + `finding_count = 0` | Tablo boş veya temiz | Kayıt al, devam et |
| `INFO` + `finding_count > 0` | Baseline sayım / dağılım | Kayıt al, karşılaştırmak için sakla |
| `WARN` + `finding_count > 0` | Migration öncesi inceleme gerekir | `sample_value` değerini gör, karar ver |
| `FAIL` + `finding_count = 0` | Temiz | ✅ |
| `FAIL` + `finding_count > 0` | **Migration bloklayıcı** | ❌ STOP — cleanup planı gerekir |

**Kritik FAIL kategorileri:**

| check_group | Anlam |
|---|---|
| `null_blank_keys` | Natural key eksik → unique index uygulanamaz |
| `duplicate_keys` | İdempotency çakışması → upsert veya unique migration riskli |
| `station_queue_consistency` | Queue rank çakışması → operasyon akışı bozuk |
| `timestamp_sanity: completed before started` | Veri bütünlüğü sorunu |
| `package_runtime_consistency` | BOM quantity veya session tutarsızlığı |

---

## Sonuç Dokümantasyonu

### Result Template Nasıl Doldurulur

Dosya:
[`read_only_compatibility_report_result_template.md`](read_only_compatibility_report_result_template.md)

Dolduracağınız alanlar:

| Alan | Nereden alınır |
|---|---|
| `Run date` | Çalıştırma tarihi/saati |
| `Target PC` | Hedef PC hostname veya tanımı |
| `Git commit` | `git log --oneline -1` çıktısı |
| `DB backup alındı mı?` | `backup_mes_db.cmd` çıktısı |
| `Backup path / reference` | `data\db_backups\` altındaki dosya adı |
| `Rapor dosyası` | Quickcheck + full report çıktı dosya adları |
| `Operator / reviewer` | İşlemi yapan kişi |
| FAIL/WARN sayımları | Rapor çıktısından `grep FAIL` / `grep WARN` |
| `Migration go/no-go` | Aşağıdaki kriterlere göre |

Doldurulmuş template commit edilmeli mi?

> **Öneri:** Sonuç dosyasını `docs/mesql/results/` altına (eğer klasör yoksa oluşturarak) `compat_result_GGAAYYYY.md` adıyla commit edin. `.env`, dump dosyası veya şifre içermeyen, yalnızca count/severity/decision bilgisi içeren kayıt güvenlidir.

---

## Go / No-Go Kriterleri

| Durum | Karar |
|---|---|
| Tüm FAIL satırları `finding_count = 0` **ve** tüm WARN satırları gözden geçirildi | **GO — Migration planlamaya geçilebilir** |
| Herhangi bir `FAIL finding_count > 0` var | **NO-GO — Cleanup planı yazılmadan migration yapılamaz** |
| WARN var ama FAIL yok | **Conditional GO — Her WARN için aksiyon kararı yazılmalı** |
| Rapor çalışmadı (table missing, auth error) | **NO-GO — Ön koşullar tamamlanmadan devam edilemez** |

---

## Riskler

### R1 — Missing Table (oee_snapshots ve diğerleri)

**Risk:** Full report `mes.oee_snapshots` dahil 14 tabloyu sorgular. `001_initial_mes_schema.sql` uygulanmamışsa `oee_snapshots` yoktur ve `WITH ... SELECT` bloğunun tamamı hata verir — tek bir tablo eksikliği tüm raporu keser.

**Önlem:** P4 adımındaki tablo listesi kontrolünü atlamayın. `mes` şemasındaki tablo sayısı en az 15 olmalı.

**Tetikleyici durum:** Hedef PC'de DB volume fresh veya partial migration uygulandıysa.

---

### R2 — Farklı DB Adı / User

**Risk:** Hedef PC `.env` dosyasında `POSTGRES_DB` veya `POSTGRES_USER` default `mes` değerinden farklı ayarlanmışsa `psql -U mes -d mes` komutu authentication veya database not found hatası verir.

**Önlem:** Komut çalıştırmadan önce `.env` içeriğini okuyun ve parametreleri güncelleyin:
```cmd
type .env | findstr POSTGRES
```
Değerler farklıysa draft komutlardaki `-U mes -d mes` parametrelerini güncelleyin.

---

### R3 — Eski Migration Chain

**Risk:** Migration 001–004 uygulanmış ama 005 (`package_bom_lines`), 006 (`station_queue`) veya 007 (`package_sessions`) uygulanmamışsa full report bu tablolarda hata verir.

**Önlem:** P4 tablo listesi kontrolünde eksik tabloyu tespit edin. 7 migration numarası yerine tablo varlığını doğrulayın.

**Recovery:** Eksik migration'lar önce ayrı onay + rollback planıyla uygulanmalı, ardından bu rapor tekrar çalıştırılmalıdır.

---

### R4 — Yanlış Hedef PC

**Risk:** Rapor hedef üretim PC yerine geliştirme ortamında çalıştırılırsa sonuç anlamlı değil; migration kararı yanlış verilir.

**Önlem:** Result template'deki `Target PC` alanına hostname yazın. `git log` ile commit'in doğru olduğunu doğrulayın. Hedef PC'yi bir önceki adımda tespit edin.

---

### R5 — Backup Alınmadan Rapor Çalıştırma

**Risk:** Read-only rapor DB'ye zarar vermez. Ancak aynı oturumda sonuç yanlış yorumlanıp migration apply kararı verilirse backup yoktur.

**Önlem:** Backup → Quickcheck → Full report sırası değiştirilemez. Template'deki `DB backup alındı mı?` alanı boşsa go kararı verilemez.

---

### R6 — MES_CODE_ROOT Bind Mount Yolu

**Risk:** `compose.yaml` içindeki bind mount `${MES_CODE_ROOT:-C:/Users/ertun/Documents/.CODE/codex/MES}:/app:ro` şeklinde. Hedef PC'de kaynak repo farklı bir path'deyse `/app/db/reports/...` path'i geçersiz olur ve SQL dosyası container içinde bulunamaz.

**Önlem:** `docker exec mes_postgres ls /app/db/reports/compatibility/` ile path'i doğrulayın. Dosya görünmüyorsa SQL dosyasını `docker cp` ile container'a kopyalayın veya `psql` komutunu host'tan çalıştırın.

---

## Draft Commands (Tam Sıra)

Aşağıdaki komutlar sırasıyla çalıştırılmalıdır. Her biri çalıştırılmadan önce önceki adımın sonucu doğrulanmalıdır.

```
┌──────────────────────────────────────────────────────────────────┐
│ ADIM 1: Git durumu                                               │
│                                                                  │
│   git log --oneline -3                                           │
│   git status                                                     │
│   # → b83e860 en üstte, working tree temiz                       │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ADIM 2: Docker servisleri                                        │
│                                                                  │
│   docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"│
│   # → mes_postgres Up (healthy)                                  │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ADIM 3: Migration chain kontrolü                                 │
│                                                                  │
│   docker exec -i mes_postgres psql -U mes -d mes -c "\dt mes.*" │
│   # → 15+ tablo görünmeli                                        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ADIM 4: BACKUP (zorunlu)                                         │
│                                                                  │
│   cd <portable-runtime-root>\launchers\                             │
│           maintenance                                            │
│   backup_mes_db.cmd                                              │
│   dir ..\..\data\db_backups\                                     │
│   # → Dosya mevcut ve > 0 byte                                   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ADIM 5: Quickcheck                                               │
│                                                                  │
│   docker exec -i mes_postgres psql -U mes -d mes                 │
│     -f /app/db/reports/compatibility/                            │
│          runtime_mes_compatibility_report.quickcheck.sql         │
│     --tuples-only --no-align -F"|"                               │
│     > quickcheck_GGAAYYYY.txt 2>&1                               │
│                                                                  │
│   # FAIL finding_count > 0 varsa → STOP                         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ADIM 6: Full report                                              │
│                                                                  │
│   docker exec -i mes_postgres psql -U mes -d mes                 │
│     -f /app/db/reports/compatibility/                            │
│          runtime_mes_compatibility_report.sql                    │
│     --tuples-only --no-align -F"|"                               │
│     > full_compat_GGAAYYYY.txt 2>&1                              │
│                                                                  │
│   # FAIL finding_count > 0 varsa → NO-GO                        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ADIM 7: Result template doldur, commit et                        │
│                                                                  │
│   docs/mesql/results/compat_result_GGAAYYYY.md                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Stop Conditions

| Koşul | Ne yapılır |
|---|---|
| `mes_postgres` `healthy` değil | Docker servis durumunu düzelt, tekrar kontrol et |
| `mes` şeması yok veya tablo eksik | Migration planlamaya geç, bu rapor tekrar |
| `.env` okuma başarısız | Hedef PC'deki `.env`'i kontrol et |
| Backup dosyası oluşmadı / 0 byte | Backup sorununu gider, tekrar dene |
| Quickcheck FAIL `finding_count > 0` | Full raporu çalıştırma, cleanup planı yaz |
| Full report FAIL `finding_count > 0` | Migration NO-GO, cleanup planı yaz |
| SQL çalışmıyor (table not found) | R1/R3 riskine bak, migration eksik |
| `/app/db/reports/...` path bulunamıyor | R6 riskine bak, path'i güncelle |

---

## Output Files to Collect

| Dosya | İçerik | Nerede tutulur |
|---|---|---|
| `quickcheck_GGAAYYYY.txt` | Quickcheck ham çıktısı | Geçici, result template'e özetle |
| `full_compat_GGAAYYYY.txt` | Full report ham çıktısı | Geçici, result template'e özetle |
| `data\db_backups\*.dump` | PostgreSQL dump | Hedef PC'de kalır, commit edilmez |
| `docs/mesql/results/compat_result_GGAAYYYY.md` | Doldurulmuş result template | **Commit edilir** |

> ⚠️ Ham çıktı dosyaları (`*.txt`, `*.dump`) commit edilmez. Şifre, miktar veya iç veri içerebilir. Yalnızca doldurulmuş result template commit edilir.

---

## Open Questions

| Soru | Etki | Yanıt kaynağı |
|---|---|---|
| Hedef PC'de `MES_CODE_ROOT` farklı mı? | SQL dosya path'i değişir | Hedef PC `.env` dosyası |
| Hedef PC'de `POSTGRES_DB` / `POSTGRES_USER` default `mes` mi? | Komut parametreleri değişir | Hedef PC `.env` dosyası |
| `backup_mes_db.cmd` hedef PC'de çalışıyor mu? | Backup adımı değişir | Launcher script çıktısı |
| 001–007 migrationlarının hepsi hedef PC'de uygulandı mı? | R1 ve R3 riski | P4 kontrol adımı |
| `oee_snapshots` tablosu hedef PC'de var mı? | Full report kesilme riski | P4 kontrol adımı |
| Result template'i nereye commitlemeli? | `docs/mesql/results/` oluşturulacak mı? | Proje kararı |
