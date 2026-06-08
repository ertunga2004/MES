# Guardrails And Do Not Touch

Kesin kurallar:

- Docker compose dosyalarını gerekmedikçe değiştirme.
- `.env`, `data`, `logs`, `exports`, `app_source`, SQL backup, dump, tar ve runtime dosyalarını commit etme.
- DB volume'u silme.
- Açık onay olmadan `docker compose down -v` kullanma.
- PostgreSQL'i host PC'ye kurmaya çalışma; PostgreSQL Docker container olarak çalışır.
- Plan olmadan source-of-truth geçişi yapma.
- Plan olmadan runtime DB read ekleme.
- Excel/JSON/FERP/MQTT akışını bozma.
- Product setup dokümanlarına bu kapsamda dokunma.
- `git add .` kullanma.
- Migration otomatik startup'a bağlanmamalı.
- DB zorunluluğu ekleme.
- `MES_WEB_DB_ENABLED` veya `MES_WEB_DB_MIRROR_WORK_ORDERS` defaultlarını true yapma.
- DB hatası runtime'ı çökertmemeli.
- Başka tabloya write eklemeden önce dry-run, apply ve verify planı yapılmalı.

Mevcut güvenli default:

```text
MES_WEB_DB_ENABLED=false
MES_WEB_DB_MIRROR_WORK_ORDERS=false
```

Riskli komutlar:

- `git add .`
- `git reset --hard` açık plan/onay olmadan
- `git push --force`
- `docker compose down -v`
- Production benzeri DB'de `DROP`, `TRUNCATE`, `DELETE`, kontrolsüz `ALTER`

Önce oku, sonra planla, sonra dar kapsamlı uygula.
