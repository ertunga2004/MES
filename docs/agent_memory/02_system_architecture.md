# System Architecture

Ana repo:

```text
C:\Users\ertun\Documents\.CODE\codex\MES
```

Docker runtime/deployment klasörü:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES
```

Docker servisleri:

| Service | Container | Erişim | Not |
|---|---|---|---|
| `mes_web` | `mes_web` | `http://127.0.0.1:8080` | MES Web |
| `mes_postgres` | `mes_postgres` | host `localhost:5433`, container `5432` | PostgreSQL |
| `mes_adminer` | `mes_adminer` | `http://127.0.0.1:8082` | Adminer |

Portlar:

- MES Web host port: `8080`
- Adminer host port: `8082`
- PostgreSQL host port: `5433`
- PostgreSQL container port: `5432`

Development mode:

- `docker/mes/compose.yaml` ve Docker runtime klasöründeki development compose kullanılır.
- İlk fazda `MES_CODE_ROOT` ile kaynak kod bind mount edilebilir.
- Yeni PC'de aynı yol yoksa `.env` güncellenmelidir.

Portable mode:

- `compose.portable.yaml` ve `Dockerfile.mes_web.portable` kullanılır.
- Kaynak kod build sırasında image içine alınır.
- `/app` artık doğrudan `C:\Users\ertun\Documents\.CODE\codex\MES` bind mount değildir.
- Sadece runtime data/log/work_orders/db_backups gibi veri mountları kalır.

GitHub otomatik kod çekmez. Güncelleme için önce kaynak repo tarafında `git pull --ff-only origin main`, sonra Docker runtime tarafında sync/build/restart yapılmalıdır.
