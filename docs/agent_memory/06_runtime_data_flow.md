# Runtime Data Flow

Mevcut source-of-truth dosya tabanlıdır.

Ana runtime state:

```text
logs/oee_runtime_state.json
```

Bu JSON içinde OEE state, work orders, items, counts, device/maintenance/help/vision gibi canlı durum alanları tutulur. `OeeRuntimeStateManager` bu dosyayı atomik state sınırı olarak kullanır.

Excel workbook:

- MES runtime ve iş emri durumları Excel workbook'a yazılabilir.
- `excel_runtime.py` ve `ExcelRuntimeSink` mevcut Excel akışını yönetir.
- PostgreSQL geçişi bu akışı değiştirmemelidir.

FERP import/export:

- Work order JSON dosyaları FERP import boundary olarak kullanılır.
- FERP XLS/XML template ve export çıktıları dosya tabanlı kalır.
- Export artifact dosyaları DB içine taşınmamıştır.

MQTT/ESP32/bridge:

- MQTT runtime bağlantı, heartbeat, bridge status ve ESP32/MEGA eventleri dashboard ve runtime state'i besler.
- Bu state şu an DB source-of-truth değildir.
- MQTT/ESP32 fiziksel bağlantısı başarıyla doğrulanmıştır ve çalışmaktadır.
- MQTT şu an yalnızca runtime dashboard/state akışında kullanılmaktadır.
- PostgreSQL tarafına MQTT event mirror altyapısı henüz eklenmemiştir; entegrasyon öncesi öncelikle dry-run analiz yapılmalıdır.


Optional PostgreSQL mirror:

- `mes_web/db/work_order_mirror.py` sadece `workOrders.ordersById` verisini `mes.work_orders` tablosuna map eder.
- Hook noktası `app.py` içindeki `sync_work_order_runtime(state)` fonksiyonudur.
- İki flag birlikte true ise DB upsert denenir:

```text
MES_WEB_DB_ENABLED=true
MES_WEB_DB_MIRROR_WORK_ORDERS=true
```

- Flag false ise no-op.
- DB hatası olursa runtime çökmez; hata loglanır veya result olarak döner.
- DB read yoktur.
- PostgreSQL source-of-truth değildir.
