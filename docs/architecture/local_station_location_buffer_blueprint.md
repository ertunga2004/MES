# Local Station / Location / Buffer Blueprint

## 1. Amaç

Bu blueprint, local MES DB üzerinde station, location, buffer, station queue, sensor event ve ileride eklenecek inventory movement kavramlarının minimum sınırlarını netleştirir.

Mevcut doğrulanmış local execution baseline, `work_order_operation` yaşam döngüsünün local PostgreSQL üzerinde source-of-truth olarak çalışabileceğini gösterdi. Successor activation akışı da smoke edildi: `ASSEMBLY_01` op10 tamamlanınca `PACKAGING_01` op20 queue oldu, repeated complete duplicate queue üretmedi, op20 tamamlanınca work order completed oldu.

Kapanması gereken boşluk şudur: operasyon akışı artık çalışıyor, fakat stokun nerede olduğu, station WIP alanlarının nasıl okunacağı, buffer görünürlüğünün nasıl üretileceği ve sensor event'lerin stok hareketine nasıl kanıt olacağı ayrı bir model olarak tanımlı değil.

Bu model, konveyör/MES/OEE/FERP/MESQL yolculuğunda local execution katmanının malzeme ve lokasyon semantiğini kurar. MESQL entegrasyonu frozen iken local MES'in çalışmaya devam edebilmesi, daha sonra ise açık kavramlarla MESQL'e aktarılabilmesi hedeflenir.

## 2. Kapsam Dışı

- Bu doküman migration değildir.
- Kod değişikliği değildir.
- SQL DDL tanımı değildir.
- MESQL push/pull değildir.
- ERP entegrasyon implementasyonu değildir.
- Docker, compose, CMD veya runtime değişikliği değildir.
- Tam WMS tasarımı değildir.
- Mevcut `mes` schema'sını destructively değiştirme planı değildir.

## 3. Kavram Ayrımı

`station`: İş merkezi veya etkileşim noktasıdır. Operatör, sensör, PLC, kiosk veya fiziksel konveyör noktasıyla ilişkilidir. Örnek: `ASSEMBLY_01`, `PACKAGING_01`.

`location`: Stokun fiziksel veya mantıksal olarak bulunduğu yerdir. Station değildir. Örnek: `RAW_MATERIAL`, `ASSEMBLY_WIP`, `FINISHED_GOODS`.

`buffer`: Bir location subtype'ıdır. İki operasyon veya iki station arasında bekleyen WIP, komponent veya ara stok için kullanılır. Buffer ayrı bir station gibi queue çalıştırmaz.

`work_order`: Üretilecek işin ana planlama ve takip kaydıdır. Operasyon rotasının üst seviyesidir.

`work_order_operation`: Work order içindeki belirli icra adımıdır. Execution identity bu seviyede tutulmalıdır. `station_queue` için temel kimlik `work_order_operation_id` olmalıdır.

`station_queue`: Bir station'da yürütülecek operation execution akışını temsil eder. Work order listesi değil, operation-first queue projection olmalıdır. `order_id` okunabilir/denormalized alan olarak kalabilir.

`inventory_movement`: Stok etkisi olan consume, produce, transfer, reserve, release, scrap, backflush veya adjust olayının append-only kaydıdır. Sensor event'in kendisi değil, ondan türeyen stok etkisidir.

`sensor_event`: Fiziksel kanıttır. Item algılama, renk ölçümü, station geçişi veya cihaz sinyali olabilir. Doğrudan negatif stok yazmamalı; inventory movement'a dönüşecek policy tarafından yorumlanmalıdır.

`package_session`: Paketleme operasyonu içindeki yürütme oturumudur. Süre, rezervasyon, komponent tüketimi ve traceability için kullanılır. Work order veya operation yerine geçmemelidir.

`packaging_unit`: Paketleme sonucunda oluşan fiziksel veya mantıksal paket birimidir. Work order'ın yerine geçmez; operation/package session sonucuna bağlanır.

## 4. Minimum Local Topology

Minimum stations:

| Station | Rol |
| --- | --- |
| `ASSEMBLY_01` | Montaj/üretim station'ı; hammadde veya komponentten assembly output üretir. |
| `PACKAGING_01` | Paketleme station'ı; assembly output'u paketler, good/scrap sonucuna bağlar. |

Minimum locations:

| Location | Tip | Amaç |
| --- | --- | --- |
| `RAW_MATERIAL` | input/storage | Assembly input stokunun başlangıç noktası. |
| `ASSEMBLY_WIP` | WIP | `ASSEMBLY_01` üzerinde aktif veya yarı işlenmiş stok. |
| `BETWEEN_ASSEMBLY_PACKAGING` | buffer | Assembly output ile packaging input arasındaki ara stok. |
| `PACKAGING_WIP` | WIP | `PACKAGING_01` üzerinde aktif paketleme işi. |
| `FINISHED_GOODS` | output/storage | Good paketleme çıktısı. |
| `SCRAP_AREA` | scrap/storage | Hurda veya reject çıktısı. |

Opsiyonel ileriki locations:

| Location | Amaç |
| --- | --- |
| `REWORK_AREA` | Yeniden işlenecek ürün veya paketler. |
| `HOLD_AREA` | Kalite bekleme, blokaj veya karantina alanı. |

## 5. Station-Location Binding Önerisi

| Station | Binding rolü | Location |
| --- | --- | --- |
| `ASSEMBLY_01` | input | `RAW_MATERIAL` |
| `ASSEMBLY_01` | active/WIP | `ASSEMBLY_WIP` |
| `ASSEMBLY_01` | output | `BETWEEN_ASSEMBLY_PACKAGING` |
| `PACKAGING_01` | input | `BETWEEN_ASSEMBLY_PACKAGING` |
| `PACKAGING_01` | active/WIP | `PACKAGING_WIP` |
| `PACKAGING_01` | output good | `FINISHED_GOODS` |
| `PACKAGING_01` | output scrap | `SCRAP_AREA` |

Bu binding'ler default olmalıdır. İleride operation veya route bazında override gerekirse additive alanlarla çözülebilir; station master data ile operation execution identity karıştırılmamalıdır.

## 6. Önerilen İlerideki Additive Tablo Adayları

Bu bölüm DDL değildir. Amaç, side-by-side additive migration için tablo sorumluluklarını ve kritik alan adaylarını belirlemektir.

### `mes.locations`

Amaç: Fiziksel veya mantıksal stok lokasyonlarını birinci sınıf kavram yapmak.

Örnek alanlar:

- `location_id`
- `location_code`
- `location_name`
- `location_type` (`storage`, `wip`, `buffer`, `scrap`, `hold`, `rework`)
- `active`
- `metadata`

Dikkat notları:

- `location_code` unique olmalıdır.
- Buffer station değildir; `location_type = buffer` ile modellenmelidir.
- Mevcut schema yıkılmadan seed edilebilir olmalıdır.

### `mes.station_location_bindings`

Amaç: Station için default input, active/WIP, output good ve output scrap lokasyonlarını tanımlamak.

Örnek alanlar:

- `binding_id`
- `station_code`
- `binding_role` (`input`, `active_wip`, `output_good`, `output_scrap`)
- `location_id`
- `effective_from`
- `active`

Dikkat notları:

- Aynı station ve role için aktif tek binding hedeflenmelidir.
- İleride route/operation override ihtimali açık bırakılmalıdır.
- Station code mevcut `mes.stations` veya operation station domain key'i ile tutarlı olmalıdır.

### `mes.inventory_movements`

Amaç: Stok etkisi olan olayları append-only ledger olarak saklamak.

Örnek alanlar:

- `movement_id`
- `movement_type` (`consume`, `produce`, `transfer`, `reserve`, `release`, `scrap`, `backflush`, `adjust`)
- `item_id` veya `lot_id`
- `product_code`
- `quantity`
- `uom`
- `from_location_id`
- `to_location_id`
- `station_code`
- `work_order_id`
- `work_order_operation_id`
- `package_session_id`
- `source_event_id` veya `operation_event_id`
- `dedupe_key`
- `created_at`

Dikkat notları:

- Repeated operation complete duplicate movement üretmemelidir.
- `dedupe_key` veya doğal `source_event_id` idempotency için zorunlu kabul edilmelidir.
- Movement ledger append-only olmalı; düzeltmeler ters kayıt veya `adjust` movement ile yapılmalıdır.

### `mes.inventory_balances` veya inventory balance view

Amaç: Location/product bazında güncel stok görünürlüğü sağlamak.

Örnek alanlar:

- `location_id`
- `product_code`
- `quantity_on_hand`
- `quantity_reserved`
- `quantity_available`
- `updated_at`

Dikkat notları:

- MVP'de view tercih edilebilir; ledger'dan türetildiği için audit daha güçlü kalır.
- Performans veya kiosk dashboard ihtiyacı artarsa materialized view veya current-state tablo düşünülebilir.
- Balance tablosu doğrudan source-of-truth yapılırsa ledger ile drift riski oluşur.

### `mes.sensor_event_links` veya existing sensor events ilişkisi

Amaç: Fiziksel sensor event ile operasyon ve movement etkisini bağlamak.

Örnek alanlar:

- `link_id`
- `sensor_event_id`
- `station_code`
- `work_order_operation_id`
- `movement_id`
- `link_type` (`evidence`, `trigger`, `derived_movement`)
- `created_at`

Dikkat notları:

- Existing sensor events korunabilir; yeni tablo sadece ilişki kurabilir.
- Tek sensor event birden fazla yoruma neden oluyorsa link type açık olmalıdır.
- Duplicate sensor event toleransı için event fingerprint veya source timestamp/device key gerekir.

## 7. Event Semantics

`operation start`: İlgili station input location'ından active/WIP location'a reserve veya transfer movement oluşabilir. Hammadde gerçek item/lot ile izlenmiyorsa policy `backflush_on_complete` olarak ertelenebilir.

`operation complete good`: Active/WIP location'dan output good location'a produce veya transfer movement oluşmalıdır. `ASSEMBLY_01` için hedef `BETWEEN_ASSEMBLY_PACKAGING`, `PACKAGING_01` için hedef `FINISHED_GOODS` olur.

`operation complete scrap`: Active/WIP location'dan `SCRAP_AREA` location'ına scrap movement oluşmalıdır. Good output ve scrap output aynı movement ile karıştırılmamalıdır.

`sensor detects item at station`: Sensor event fiziksel kanıt olarak kaydedilir. Policy'ye göre station entry, WIP transition, item detection veya backflush trigger olabilir. Tek başına stok düşmemelidir.

`package session close`: Paketleme session içindeki reserved komponentler consume edilir, paketleme sonucu good ise `FINISHED_GOODS` produce/transfer edilir; reject ise `SCRAP_AREA` veya ileride `REWORK_AREA`/`HOLD_AREA` kullanılabilir.

`manual correction`: Sayım, kalite karantinası veya operatör düzeltmesi için `adjust`, `transfer`, `release` veya `scrap` movement oluşur. Manuel düzeltmeler reason code ve actor bilgisi olmadan yapılmamalıdır.

## 8. Successor Activation ile İlişki

Mevcut doğrulanmış local akışta `ASSEMBLY_01` op10 complete, `PACKAGING_01` op20 için queue görünürlüğü yaratır. Repeated op10 complete duplicate queue oluşturmaz. Op20 complete sonrasında work order tamamlanır.

Bu blueprint içinde successor activation sadece queue semantiği değildir. İleride aynı operation event birden fazla side effect'e kaynak olabilir:

- op10 complete, op20 queue yaratmanın yanında `ASSEMBLY_WIP` veya station output state'inden `BETWEEN_ASSEMBLY_PACKAGING` location'ına movement yaratabilir.
- op20 start, `BETWEEN_ASSEMBLY_PACKAGING` input location'ından `PACKAGING_WIP` active/WIP location'ına reserve veya transfer movement yaratabilir.
- op20 complete good, `PACKAGING_WIP` içinden `FINISHED_GOODS` location'ına movement yaratabilir.
- op20 complete scrap, `PACKAGING_WIP` içinden `SCRAP_AREA` location'ına scrap movement yaratabilir.

Bu nedenle successor activation'ın idempotency anahtarı ile inventory movement idempotency anahtarı aynı event kökünden türemeli, fakat ayrı uniqueness kurallarıyla korunmalıdır.

## 9. Idempotency ve Duplicate Prevention

- Repeated complete duplicate `station_queue` yaratmamalıdır.
- Repeated complete duplicate `inventory_movement` yaratmamalıdır.
- `station_queue` için execution identity `work_order_operation_id` olmalıdır.
- `inventory_movements` için `source_event_id`, `operation_event_id` veya deterministik `dedupe_key` gerekir.
- Sensor event'ler duplicate gelebilir; device id, event timestamp, item id, station code ve event type üzerinden tolerans/fingerprint tasarlanmalıdır.
- Retried API call ile replay edilen integration event aynı sonucu üretmeli, ek movement üretmemelidir.
- Manual correction idempotent olmayabilir; bu durumda her düzeltme açık actor/reason ile ayrı movement olarak kaydedilmelidir.

## 10. MVP Uygulama Sırası

Faz A: Blueprint ve seed kararları

- Station/location/buffer sözlüğü sabitlenir.
- Minimum topology ve binding listesi kabul edilir.
- Location code isimleri değiştirilmeden kullanılacak hale getirilir.

Faz B: Additive migration tasarımı

- DDL yazılmadan tablo sorumlulukları, ilişkiler ve idempotency kuralları netleştirilir.
- Existing `mes` schema'sı bozulmadan side-by-side yaklaşım korunur.

Faz C: Seed insert script veya migration

- `ASSEMBLY_01`, `PACKAGING_01` binding'leri ve minimum locations seed edilir.
- Seed işlemleri tekrar çalıştırılabilir olacak şekilde tasarlanır.

Faz D: Shadow-write `inventory_movements`

- Operation start/complete, package session close ve sensor evidence üzerinden movement ledger'a idempotent shadow-write eklenir.
- UI read source hemen değiştirilmez.

Faz E: Dashboard/kiosk read visibility

- Station queue ekranlarında operation-first identity ve location/buffer visibility gösterilir.
- Buffer doluluğu ledger/view üzerinden okunur.

Faz F: MESQL export mapping

- MESQL frozen durumundan çıkınca local kavramlar merkezi visibility/export formatına eşlenir.
- MESQL local execution kararlarının ön koşulu haline getirilmez.

## 11. Riskler

Station ile location karışırsa, execution resource ile stok konumu aynı kavrama dönüşür. Bu durumda queue, sensor ve inventory visibility birbirini bozar; örneğin buffer doluluğu station availability gibi okunabilir.

Buffer station yapılırsa, ara stok noktası gereksiz yere operation execution aktörü olur. Bu durum sahte queue satırları, yanlış OEE station ölçümü ve gereksiz operator/kiosk akışı üretir.

Work order yerine package_session konursa, üretim planlama seviyesi ile paketleme oturumu karışır. Traceability kısa vadede kolay görünür, fakat route, successor activation ve operation lifecycle bozulur.

Sensor event doğrudan stok düşerse, fiziksel kanıt muhasebe etkisine erken bağlanır. Duplicate sensor event, yanlış renk ölçümü veya retry negatif stok ve audit hatası yaratabilir.

Inventory balance tablo mu view mı olmalı sorusu MVP'de audit lehine cevaplanmalıdır. View veya ledger-derived projection daha güvenlidir. Current-state tablo gerekirse performans için eklenebilir, fakat source-of-truth ledger olmalıdır.

## 12. Kabul Kriterleri

- Station/location ayrımı net olmalıdır.
- Buffer'ın location subtype olduğu açık olmalıdır.
- Minimum topology `ASSEMBLY_01`, `PACKAGING_01` ve temel locations ile yer almalıdır.
- Station-location binding önerisi yer almalıdır.
- Future additive table candidates amaç, örnek alan ve constraint/idempotency notlarıyla yer almalıdır.
- Current successor activation akışıyla bağlantı kurulmalıdır.
- Migration, SQL DDL, Python, CMD, compose, Dockerfile veya runtime değişikliği yapılmamış olmalıdır.
- MESQL push/pull çalıştırılmamış olmalıdır.

## 13. Sonraki Codex İşi Önerisi

Design additive station/location migration plan

