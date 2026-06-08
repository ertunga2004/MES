# MES Masterplan

MES projesinin ana hedefi, konveyör tabanlı üretim hattı için web tabanlı, gösterilebilir ve geliştirilebilir bir MES/OEE/FERP prototipi oluşturmaktır. Sistem FastAPI tabanlı MES Web, React/static arayüzler, MQTT/ESP32/bridge akışı, Excel workbook, FERP import/export dosyaları ve runtime JSON state üzerinden çalışır.

Hedef mimari Docker üzerinde çalıştırılabilir MES Web + PostgreSQL + Adminer + portable Docker yapısıdır. PostgreSQL host PC'ye kurulmayacak; Docker container olarak `mes_postgres` içinde çalışacaktır. Adminer da Docker servisidir. MES Web hem development hem portable Docker modunda çalıştırılabilir.

Klasör ayrımı korunmalıdır:

```text
MES kaynak repo:
C:\Users\ertun\Documents\.CODE\codex\MES

MES Docker runtime/deployment:
C:\Users\ertun\Documents\.CODE\.DOCKER\MES
```

Kaynak kod Git repo içinde kalır. Docker runtime klasörü çalıştırma, volume, backup, export ve portable bundle işleri için ayrıdır. Development modda kaynak kod bind mount yaklaşımı kullanılabilir. Portable modda kaynak kod image içine alınır ve yeni PC'de aynı kaynak yoluna ihtiyaç kalmaz.

PostgreSQL ileride source-of-truth olabilir; ancak geçiş kademeli yapılacaktır. Şu anda DB, passive foundation ve mirror doğrulama katmanıdır. Mevcut runtime source-of-truth hâlâ JSON/Excel/FERP akışıdır. DB read yoktur. Runtime DB write yalnızca feature flag ile optional `mes.work_orders` mirror hook seviyesindedir.

Nihai yön:

- MES Web Docker üzerinde çalışır.
- PostgreSQL Docker volume içinde kalıcı veri tutar.
- Adminer 8082 üzerinden DB kontrolü sağlar.
- Portable image ve SQL backup ile yeni PC'ye taşınabilirlik sağlanır.
- PostgreSQL geçişi önce mirror, sonra optional write, sonra flag-gated read, en son source-of-truth olarak ilerler.
