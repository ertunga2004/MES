# Station Execution Seed Setup Plan

## 1. Amaç

Bu doküman, SQL-driven station execution modelinin ilk çalışır kurulumunda
gerekli minimum master data listesini ve seed/setup yaklaşımını tanımlar.

Bu doküman seed SQL değildir. Insert cümlesi yazmaz, DB'ye bağlanmaz ve migration
uygulamaz.

## 2. Kapsam

Minimum seed/setup kapsamı:

- Items.
- Process route.
- Route operations.
- Operation steps.
- Station event sources.
- Station/location binding rollerini kullanan input/output location
  çözümleme yaklaşımı.
- `ASSEMBLY_01` ve `PACKAGING_01` örnek akışı.

## 3. Kapsam Dışı

- SQL migration.
- Seed SQL implementation.
- Runtime engine kodu.
- Kiosk dynamic action kodu.
- IoT/MQTT adapter kodu.
- OEE/KPI implementation.
- Inventory movement/balance.
- MESQL push/pull.
- Docker/DB/psql çalıştırma.

## 4. Seed Formatı Kararı

İlk faz için üç seçenek vardır:

```text
Option A: minimal seed SQL
Option B: JSON/YAML setup dosyası + validator/importer
Option C: workbook tabanlı setup
```

Default öneri:

```text
Option A ile başlanabilir, ancak seed SQL schema migration'dan ayrı tutulmalıdır.
```

Gerekçe:

- İlk lokal prototipte en hızlı doğrulama yoludur.
- Migration review sırasında schema ile data birbirine karışmaz.
- JSON/workbook importer henüz implementation gerektirir; bu goal kapsamında
  implementation yoktur.

Future öneri:

- JSON/YAML setup dosyası + setup validator daha sürdürülebilir olabilir.
- Workbook, operatör/akademik demo setup için ileride eklenebilir.

## 5. Minimum Item Seed Taslağı

Bu liste SQL değildir; setup hedefidir.

| item_code | item_type | Amaç |
| --- | --- | --- |
| `RAW_BOX` | `raw_material` veya `box` | ASSEMBLY_01 input malzemesi |
| `COLOR_CLASSIFIED_BOX` | `semi_finished` | ASSEMBLY_01 output / PACKAGING_01 input |
| `PACKAGED_PRODUCT` | `finished_good` | PACKAGING_01 output mamul |

Varsayımlar:

- Unit ilk fazda `piece` veya mevcut lokal terminolojiye uygun tekil birim
  olarak seçilir.
- Item code değişmez business key kabul edilir.
- Pasifleştirme delete yerine `active = false` ile yapılır.

## 6. Minimum Route Seed Taslağı

Route:

```text
route_code = ROUTE_BOX_PACKAGING_V1
version = 1
item_code = PACKAGED_PRODUCT
active = true
```

Anlam:

- Bu route, `RAW_BOX` girdisinden başlayıp `PACKAGED_PRODUCT` çıktısına giden
  iki istasyonlu demo üretim akışını temsil eder.
- Versioned route yaklaşımı kullanılmalıdır.
- Route değişirse aynı route row update edilmemeli; yeni version eklenmelidir.

## 7. Route Operations Seed Taslağı

Sections 7-10, `applied V1 historical baseline` değerlerini belgeler. Bu bölümlerdeki
identifier ve policy değerleri target V2 önerisi değildir; mevcut seed ve
historical/runtime referansları açıklamak için korunur. V2 target yalnız Bölüm
15'te geçiş önerisi olarak gösterilir ve henüz uygulanmamıştır.

### Operation 10 - ASSEMBLY_01

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP10
route_code = ROUTE_BOX_PACKAGING_V1
route_version = 1
sequence_no = 10
operation_code = ASSEMBLY_COLOR_CLASSIFY
station_code = ASSEMBLY_01
input_item_code = RAW_BOX
output_item_code = COLOR_CLASSIFIED_BOX
input_qty_per_cycle = 1
output_qty_per_cycle = 1
input_location_role = input
output_location_role = output_buffer
scrap_location_role = output_scrap
operation_completion_policy = auto_complete_pending_approval
```

### Operation 20 - PACKAGING_01

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP20
route_code = ROUTE_BOX_PACKAGING_V1
route_version = 1
sequence_no = 20
operation_code = PACKAGING_FINAL
station_code = PACKAGING_01
input_item_code = COLOR_CLASSIFIED_BOX
output_item_code = PACKAGED_PRODUCT
input_qty_per_cycle = 1
output_qty_per_cycle = 1
input_location_role = input
output_location_role = output_good
scrap_location_role = output_scrap
operation_completion_policy = auto_complete_pending_approval
```

Notlar:

- `route_operation_id`, step tanımlarının gerçek ilişki anahtarıdır.
- `operation_code`, okunabilir business alan olarak kalır.
- Operation sequence mevcut successor activation davranışı ile kavramsal olarak
  uyumlu olmalıdır.

## 8. Station Event Sources Seed Taslağı

Event source değerleri station-scoped kabul edilir.

### ASSEMBLY_01

| station_code | source_code | source_type | event_channel | Amaç |
| --- | --- | --- | --- | --- |
| `ASSEMBLY_01` | `COLOR_SENSOR_ENTRY` | `sensor` | `mqtt` veya `http` | Renk sensörü giriş kanıtı |
| `ASSEMBLY_01` | `ROBOT_ARM_DROP` | `robot` | `mqtt` veya `http` | Robot bırakma tamamlandı kanıtı |
| `ASSEMBLY_01` | `KIOSK_OPERATOR` | `kiosk` | `kiosk` | Operatör gözlem/final onay |

### PACKAGING_01

| station_code | source_code | source_type | event_channel | Amaç |
| --- | --- | --- | --- | --- |
| `PACKAGING_01` | `KIOSK_OPERATOR` | `kiosk` | `kiosk` | Manuel paketleme start/finish/final onay |

Kritik kural:

```text
source_code global unique değildir.
KIOSK_OPERATOR iki istasyonda tekrar edebilir.
Geçerlilik station_code + source_code ile kontrol edilir.
```

## 9. ASSEMBLY_01 Operation Steps

Bu örnek seed hedefidir; SQL değildir.

### Step 10 - Color Sensor Entry Evidence

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP10
step_no = 10
step_code = COLOR_SENSOR_ENTRY_EVIDENCE
start_mode = auto_start
finish_mode = auto_finish
start_event_source_code = COLOR_SENSOR_ENTRY
finish_event_source_code = COLOR_SENSOR_ENTRY
required_for_completion = true
records_duration = false
approval_required_after_finish = false
actor_type = sensor
```

### Step 20 - Robot Arm Drop Completed

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP10
step_no = 20
step_code = ROBOT_ARM_DROP_COMPLETED
start_mode = implicit_start
finish_mode = auto_finish
finish_event_source_code = ROBOT_ARM_DROP
required_for_completion = true
records_duration = true
approval_required_after_finish = false
actor_type = robot
```

### Step 30 - Operator Observation Approval

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP10
step_no = 30
step_code = OPERATOR_OBSERVATION_APPROVAL
start_mode = implicit_start
finish_mode = manual_finish
finish_event_source_code = KIOSK_OPERATOR
required_for_completion = true
records_duration = true
approval_required_after_finish = true
actor_type = operator
```

## 10. PACKAGING_01 Operation Steps

### Step 10 - Packaging Start

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP20
step_no = 10
step_code = PACKAGING_START
start_mode = manual_start
finish_mode = implicit_finish
start_event_source_code = KIOSK_OPERATOR
required_for_completion = true
records_duration = true
approval_required_after_finish = false
actor_type = operator
```

### Step 20 - Packaging Finish / Final Approval

```text
route_operation_id = ROUTE_BOX_PACKAGING_V1_OP20
step_no = 20
step_code = PACKAGING_FINAL_APPROVAL
start_mode = implicit_start
finish_mode = manual_finish
finish_event_source_code = KIOSK_OPERATOR
required_for_completion = true
records_duration = true
approval_required_after_finish = true
actor_type = operator
```

Not:

- PACKAGING_01 ilk fazda manuel station olarak kalır.
- Kiosk butonları hard-coded olmamalı; bu step policy'den türemelidir.

## 11. Location Role Kullanımı

Seed, doğrudan location code hard-code etmek yerine route operation üzerinde rol
tanımlar:

- `input_location_role`
- `output_location_role`
- `scrap_location_role`

Runtime veya setup validator, bu rolleri mevcut
`mes.station_location_bindings` üzerinden çözer.

Örnek:

```text
ASSEMBLY_01 + input -> ASSEMBLY_01 input binding
ASSEMBLY_01 + output_buffer -> between assembly/packaging buffer binding
PACKAGING_01 + input -> PACKAGING_01 input binding
PACKAGING_01 + output_good -> finished goods binding
PACKAGING_01 + output_scrap -> scrap binding
```

Bu çözümleme inventory movement değildir; sadece semantic production flow için
location context sağlar.

## 12. Setup Validation Checklist

Seed uygulanmadan önce veya seed sonrası validator şu kontrolleri yapmalıdır:

- Tüm `item_code` değerleri benzersiz mi?
- `ROUTE_BOX_PACKAGING_V1` version 1 tekil mi?
- Route operations sequence değerleri benzersiz mi?
- Her route operation station mevcut ve active mi?
- Her route operation input/output item mevcut ve active mi?
- Her operation step valid `route_operation_id` değerine bağlı mı?
- Aynı `route_operation_id` altında `step_no` benzersiz mi?
- Aynı `route_operation_id` altında `step_code` benzersiz mi?
- `auto_start` step için `start_event_source_code` var mı?
- `auto_finish` step için `finish_event_source_code` var mı?
- Event source, route operation station altında active mı?
- `KIOSK_OPERATOR` station-scoped olarak doğru station altında var mı?
- Required step bulunmayan operation var mı?
- Birden fazla final approval step varsa explicit warning üretiliyor mu?
- Location role değerleri ilgili station için çözülebiliyor mu?

## 13. Seed Uygulama Sırası

Önerilen logical order:

```text
1. Items
2. Process route
3. Route operations
4. Station event sources
5. Operation steps
6. Setup validation
```

Neden:

- Route operations item/route/station temeline ihtiyaç duyar.
- Operation steps `route_operation_id` üzerinden route operations'a bağlıdır.
- Auto step validation station event sources olmadan tamamlanamaz.

## 14. Kabul Kriterleri

Bu seed/setup planı tamamlanmış sayılır, eğer:

- Minimum items tanımlıysa.
- Minimum route tanımlıysa.
- ASSEMBLY_01 ve PACKAGING_01 route operations tanımlıysa.
- Station-scoped event sources tanımlıysa.
- ASSEMBLY_01 ve PACKAGING_01 operation steps örnekleri varsa.
- Location role çözümleme yaklaşımı belirtilmişse.
- Setup validation checklist yazılmışsa.
- Seed SQL veya code implementation yapılmamışsa.

## 15. Versioned Canonical Transition Target

Sections 7-10 document the existing V1 seed design and remain historical input
to the applied baseline. In particular, `OPERATOR_OBSERVATION_APPROVAL` is the
legacy/current V1 identifier; it must not be renamed through an in-place seed
update or idempotent upsert.

For a future, separately approved route/config version, the recommended
ASSEMBLY operation target is:

```text
1. COLOR_SENSOR_ENTRY_EVIDENCE
   auto_start + auto_finish

2. ROBOT_ARM_DROP_COMPLETED
   implicit_start + auto_finish

3. PROCESS_END_OBSERVATION
   step_name = Proses Sonu Gözlem
   manual_start + manual_finish
   records_duration = true
   required_for_completion = true
   approval_required_after_finish = false
   actor_type = operator

operation_completion_policy = auto_close_on_required_steps
```

Observation is present only when the new version contains that operation-step
row. No `has_observation` column or engine flag is added. Alternative operation
policies remain `manual_close` and `auto_complete_pending_approval`; the latter
requires a distinct operation approval rather than a renamed observation step.

If a route requires quality control, add a separate versioned route operation,
for example `OP15_QUALITY_CONTROL` at `QUALITY_01`, with its own configured step
set. This example is not part of the current seed and no SQL is created here.
