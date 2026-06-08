# Workflow For Future Agents

Kod değişikliği yeri:

```text
C:\Users\ertun\Documents\.CODE\codex\MES
```

Docker çalıştırma yeri:

```text
C:\Users\ertun\Documents\.CODE\.DOCKER\MES
```

SQL migration yeri:

```text
db/migrations
```

SQL uygulama yeri:

```text
Docker içindeki mes_postgres container
```

Yeni feature için önerilen akış:

1. Plan çıkar.
2. Dar kapsamlı uygulama yap.
3. Dry-run script veya read-only analiz ekle.
4. Manual apply yalnız açık onayla yap.
5. Verify script ile sonucu doğrula.
6. Runtime hook eklenirse feature flag default false olsun.
7. Dokümantasyonu güncelle.
8. Commit/PR için ayrı onay al.

GitHub'dan kod alma:

```powershell
git pull --ff-only origin main
```

Docker güncelleme genel mantığı:

1. Ana repo güncellenir.
2. Docker runtime klasörü veya repo içi Docker kaynakları senkronlanır.
3. Portable image rebuild yapılır.
4. `start_mes_portable.cmd` veya `restart_mes_portable.cmd` ile çalıştırılır.
5. `status_mes_portable.cmd`, `/health`, Adminer ve verify scriptleriyle doğrulanır.

Antigravity için not:

Önce bu klasördeki agent memory dosyalarını oku. Sonra kod değişikliği planı çıkar. Doğrudan büyük refactor veya source-of-truth geçişi yapma.
