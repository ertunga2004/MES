# Docker And PostgreSQL Runtime

Çalıştırma klasörü:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES
```

Portable MES komutları:

```text
start_mes_portable.cmd
stop_mes_portable.cmd
restart_mes_portable.cmd
status_mes_portable.cmd
```

Backup:

```text
backup_mes_db.cmd
```

Portable export:

```text
export_mes_portable_bundle.cmd
```

Erişim:

- MES Web: `http://127.0.0.1:8080`
- Adminer: `http://127.0.0.1:8082`
- PostgreSQL hosttan: `localhost:5433`
- PostgreSQL Docker network içinden: `mes_postgres:5432`
- Adminer server değeri: `mes_postgres`

Docker volume:

```text
mes_postgres_data
```

Backup klasörü:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES\data\db_backups
```

Önemli kurallar:

- Docker GitHub'dan otomatik kod çekmez.
- Kod güncellemek için önce repo güncellenir, sonra Docker image build/restart yapılır.
- `docker compose down -v` açık onay olmadan kullanılmaz; volume siler.
- PostgreSQL verisi image içinde değildir; volume ve SQL backup ile taşınır.
- `mes_web` 8080 kullanıyorsa Windows üzerinde manuel başlatılmış başka MES Web aynı portu kullanamaz.
- Compose artık DB flaglerini `.env` üzerinden alabilir.
- Default `false` olduğu için normal davranış değişmez.
- C2 runtime hook testi bu plumbing sonrası tekrar yapılmalıdır.
