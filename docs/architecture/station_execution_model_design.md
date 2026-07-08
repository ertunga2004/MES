# SQL-Driven Station Execution Model Design

## 1. Tasarım Bağlamı

Local MES DB operation lifecycle şu an local execution için source-of-truth
durumundadır. Mevcut doğrulanmış davranışta `work_order_operations` ve
`station_queue` üzerinden operasyon başlatma, tamamlama, successor operation
aktivasyonu ve final operation sonrası work order kapanışı local DB tarafından
yönetilir.

Station/location modeli oluşturulmuştur. `mes.locations` ve
`mes.station_location_bindings` tabloları mevcuttur. Station/location
read-only helper ve API doğrulanmıştır. Kiosk read-only station/location kartı
HTTP/static smoke ve controlled manual visual check ile doğrulanmıştır.

Kiosk artık istasyonun giriş, active WIP, sağlam çıkış, fire/hurda çıkış ve
ara buffer lokasyonlarını gösterebilmektedir. Bu görünürlük read-only'dir;
start/complete, queue mutation, inventory movement, MESQL veya DB write
başlatmaz.

Ancak sistem henüz SQL-driven station execution seviyesinde değildir. Eksik ana
parça station + operation + step + event + policy yürütme modelidir.

Bu doküman implementation dokümanı değildir; SQL migration veya kod değişikliği
üretmez. Sonraki schema planı ve runtime engine implementation için temel
tasarımdır.

## 2. Ana Hedef

MES sistemi, simülasyon programı gibi SQL'den beslenebilmelidir.

Manuel kurulumda veya ileride MESQL'den çekilecek master data ile aşağıdaki
bilgiler tanımlanabilmelidir:

- İstasyonlar.
- Lokasyonlar.
- Hammadde, yarı mamul, mamul, kart, kutu gibi item tanımları.
- Hangi item'ın hangi operasyondan geçeceği.
- Operasyonun hangi istasyonda yapılacağı.
- Operasyonun iş adımları.
- Her iş adımının nasıl başlayacağı.
- Her iş adımının nasıl biteceği.
- Hangi adımın manuel, otomatik veya hibrit olduğu.
- Otomatik adımların hangi event source'tan beslendiği.
- Hangi adımın zorunlu olduğu.
- Hangi adımın süre tuttuğu.
- Operasyonun ne zaman kanıta göre tamamlandı sayılacağı.
- Operasyonun ne zaman tam kapanacağı.
- Ürün giriş/çıkış bilgisinin ne zaman oluşacağı.
- OEE/KPI için hangi timestamp'lerin tutulacağı.

Bu hedef Kiosk butonlarının, sensor/robot olaylarının ve operasyon kapanışının
hard-coded akışlardan çıkarılıp SQL master data ve runtime state üzerinden
yönetilmesini amaçlar.

## 3. Terminoloji

### Station

Fiziksel veya lojik üretim yürütme noktasıdır.

Örnekler:

- `ASSEMBLY_01`
- `PACKAGING_01`

Station iş yapan noktadır. Location ile karıştırılmamalıdır.

### Location

Malzeme veya ürünün bulunduğu fiziksel ya da lojik noktadır.

Örnekler:

- `RAW_MATERIAL`
- `ASSEMBLY_WIP`
- `BETWEEN_ASSEMBLY_PACKAGING`
- `PACKAGING_WIP`
- `FINISHED_GOODS`
- `SCRAP_AREA`

Buffer bir station değildir; location subtype'ıdır.

### Item

Sistemde hareket eden veya dönüşen nesnedir.

Örnekler:

- Hammadde.
- Yarı mamul.
- Mamul.
- Kart.
- Kutu.
- Paketlenmiş ürün.

### Operation

İş emrinin istasyonda yapılacak üretim işlemidir.

Örnekler:

- Kutu ayırma.
- Renk sınıflandırma.
- Robot kol ile bırakma.
- Gözlem/onay.
- Paketleme.

### Operation Step

Operasyonun küçük yürütme adımıdır.

Örnekler:

- Renk sensörü giriş algıladı.
- Robot kol ürünü bıraktı.
- Operatör gözlem yaptı.
- Paketleme başlatıldı.
- Paketleme adım 1 bitirildi.
- Final onay verildi.

### Event

Kiosk, sensör, robot, observer, PLC veya sistemden gelen kanıttır.

### Policy

Bir adımın nasıl başlayacağını, nasıl biteceğini ve operasyon kapanışını yöneten
kuraldır.

## 4. İstasyon Örnekleri

### 4.1 ASSEMBLY_01 / İstasyon 1

Bu istasyon hibrit/otomatik istasyon olarak tasarlanmalıdır.

İstenen mantık:

- Giriş renk sensörü ile algılanır.
- Robot kol çıkış bırakma event'i üretir.
- Operatör gözlem/onay yapar.
- Sensör ve robot işlemleri Kiosk butonuyla yapılmaz.
- Gözlem manuel olduğu için Kiosk üzerinden onaylanabilir.
- Operasyon, zorunlu kanıtlar tamamlanınca `evidence_completed` olabilir.
- Son onay gerekiyorsa `pending_final_approval` durumuna geçebilir.
- Onaydan sonra ürün çıkışı kabul edilir.

Örnek step seti:

```text
Station: ASSEMBLY_01

Step 10 - Color sensor entry detected
start_mode = auto_start
finish_mode = auto_finish
start_event_source = COLOR_SENSOR_ENTRY
finish_event_source = COLOR_SENSOR_ENTRY
required_for_completion = true
records_duration = false

Step 20 - Robot arm drop completed
start_mode = auto_start veya implicit_start
finish_mode = auto_finish
finish_event_source = ROBOT_ARM_DROP
required_for_completion = true
records_duration = true

Step 30 - Operator observation approval
start_mode = implicit_start
finish_mode = manual_finish
required_for_completion = true
records_duration = true
approval_required_after_finish = true
```

Not: Bu sadece örnek tasarımdır. Nihai schema planında event mapping daha net
hale getirilecektir.

### 4.2 PACKAGING_01 / İstasyon 2

Bu istasyon manuel istasyon olarak tasarlanmalıdır.

İstenen mantık:

- Sensör yok.
- Paketleme adımları Kiosk üzerinden başlatılıp/bitirilebilir.
- Her adım için ayrı buton istenebilir.
- Daha basit kurulumda sadece operasyon başlat ve operasyon bitir butonları
  gösterilebilir.
- Bu davranış Kiosk kodundan değil, DB'deki step policy'den türemelidir.

Örnek detaylı manuel senaryo:

```text
Station: PACKAGING_01

Step 10 - Paketleme başlat
start_mode = manual_start
finish_mode = manual_finish
required_for_completion = true
records_duration = true

Step 20 - Ürünü kutuya yerleştir
start_mode = manual_start
finish_mode = manual_finish
required_for_completion = true
records_duration = true

Step 30 - Etiketle
start_mode = manual_start
finish_mode = manual_finish
required_for_completion = true
records_duration = true

Step 40 - Final kontrol/onay
start_mode = implicit_start
finish_mode = manual_finish
required_for_completion = true
approval_required_after_finish = true
```

Örnek sade manuel senaryo:

```text
Station: PACKAGING_01

operation_start_policy = manual_start_required
operation_completion_policy = auto_complete_pending_approval

Step 10 - Paketleme operasyonu başladı
start_mode = manual_start
finish_mode = none
required_for_completion = true

Step 20 - Paketleme tamamlandı
start_mode = implicit_start
finish_mode = manual_finish
required_for_completion = true
approval_required_after_finish = true
```

## 5. Policy Modeli

Tek `control_policy` alanına sıkışmak doğru temel model değildir. Asıl teknik
model şu ayrık alanlara dayanmalıdır:

```text
start_mode
finish_mode
start_event_source
finish_event_source
operation_completion_policy
```

Terminoloji notu:

- Bu kavramsal dokümanda erken örneklerde `start_event_source` ve
  `finish_event_source` ifadeleri kullanılır.
- Migration öncesi kesin schema planında bu alanlar
  `start_event_source_code` ve `finish_event_source_code` olarak
  netleştirilmiştir.
- `operation_steps`, `route_operation_id` üzerinden `route_operations` satırına
  bağlanır; `operation_code` tek başına step FK olarak kullanılmaz.
- Event source validation station-scoped yapılır:
  `route_operation.station_code + source_code`.

`control_policy` convenience/seed alanı olabilir. Kullanıcı, workbook veya seed
dosyası için okunabilir kısa değer sağlar; engine tarafında ise mümkün olduğunca
`start_mode` ve `finish_mode` ayrı işlenmelidir.

Bu ayrım şu avantajları sağlar:

- Kiosk buton üretimi netleşir.
- Auto event validation daha sağlam olur.
- Hibrit senaryolar tek string'e sıkışmaz.
- Future policy değerleri eklenirken engine daha az kırılır.

## 6. Start Mode Listesi

MVP için zorunlu start mode değerleri:

```text
none
manual_start
auto_start
implicit_start
```

### none

Bu step için ayrı başlangıç tutulmaz. Sadece bitiş, kanıt veya onay takip
edilebilir.

### manual_start

Başlama Kiosk butonu veya operatör onayı ile olur.

Kiosk etkisi:

- Step pending ise `Başlat` butonu gösterilir.

### auto_start

Başlama kullanıcıya sorulmaz. Bir event source tarafından otomatik oluşur.

Zorunlu kural:

- `start_mode = auto_start` ise `start_event_source` zorunludur.
- Event source eksikse step tanımı valid değildir.

### implicit_start

Önceki step tamamlandığında bu step başlamış kabul edilir.

Kullanım:

- Aradaki adımlar için ayrı start event istemediğimiz durumlar.
- Sadece bitiş/onay almak istediğimiz manuel süreçler.

### Future Start Mode Değerleri

MVP dışı değerler:

- `external_start`
- `scheduled_start`

Bu değerler ilk schema ve engine fazında etkinleştirilmemelidir.

## 7. Finish Mode Listesi

MVP için zorunlu finish mode değerleri:

```text
none
manual_finish
auto_finish
implicit_finish
```

### none

Bu step için ayrı bitiş tutulmaz. Sadece start veya event kanıtı olabilir.

### manual_finish

Bitiş Kiosk butonu veya operatör onayı ile olur.

Kiosk etkisi:

- Step active ise `Bitir` veya `Onayla` butonu gösterilir.

### auto_finish

Bitiş kullanıcıya sorulmaz. Bir event source tarafından otomatik oluşur.

Zorunlu kural:

- `finish_mode = auto_finish` ise `finish_event_source` zorunludur.
- Event source eksikse step tanımı valid değildir.

### implicit_finish

Sonraki step başladığında veya operasyon ilerlediğinde bu step bitmiş kabul
edilir.

Dikkat:

- MVP'de dikkatli kullanılmalıdır.
- Süre ölçümü kritik adımlarda tercih edilmemelidir.

### Future Finish Mode Değerleri

MVP dışı değerler:

- `external_finish`
- `timed_finish`

Bu değerler ilk schema ve engine fazında etkinleştirilmemelidir.

## 8. Convenience Control Policy Listesi

Aşağıdaki kısa policy değerleri seed/setup kolaylığı için kullanılabilir:

```text
manual_both
auto_both
manual_start_auto_finish
auto_start_manual_finish
implicit_start_manual_finish
manual_start_implicit_finish
evidence_only
approval_only
tracking_only
```

### manual_both

```text
start_mode = manual_start
finish_mode = manual_finish
```

Başlatma ve bitirme Kiosk'tan alınır.

### auto_both

```text
start_mode = auto_start
finish_mode = auto_finish
```

Başlatma ve bitirme otomatik event ile alınır. `start_event_source` ve
`finish_event_source` zorunludur.

### manual_start_auto_finish

```text
start_mode = manual_start
finish_mode = auto_finish
```

Operatör başlatır, bitiş sensör/robot/observer event'iyle olur.
`finish_event_source` zorunludur.

### auto_start_manual_finish

```text
start_mode = auto_start
finish_mode = manual_finish
```

Başlama sensör/robot/observer event'iyle olur, bitiş operatör tarafından
onaylanır. `start_event_source` zorunludur.

### implicit_start_manual_finish

```text
start_mode = implicit_start
finish_mode = manual_finish
```

Önceki adım bitince başlar, operatör bitirir.

### manual_start_implicit_finish

```text
start_mode = manual_start
finish_mode = implicit_finish
```

Operatör başlatır, sonraki adım başlayınca bitmiş kabul edilir.

### evidence_only

```text
start_mode = none
finish_mode = auto_finish
```

Sadece kanıt/event yakalanır. Buton gösterilmez. `finish_event_source`
zorunludur.

### approval_only

```text
start_mode = none
finish_mode = manual_finish
```

Sadece onay adımıdır. Kiosk'ta onay butonu gösterilir.

### tracking_only

```text
start_mode = implicit_start
finish_mode = implicit_finish
```

Süreçte görünür ama kullanıcı aksiyonu veya event istemez. Kapanış için zorunlu
olmamalıdır veya çok dikkatli kullanılmalıdır.

## 9. Operation Completion Policy Listesi

MVP için önerilen değerler:

```text
manual_close
auto_close_on_required_steps
auto_complete_pending_approval
```

### manual_close

Operasyon sadece operatör kapatınca kapanır.

### auto_close_on_required_steps

Tüm zorunlu step'ler tamamlanınca operasyon otomatik kapanır.

### auto_complete_pending_approval

Tüm zorunlu step'ler tamamlanınca operasyon `evidence_completed` olur, ancak
tam kapanış için final approval gerekir.

Bu bizim ana hedef modelimizdir.

Future değerler:

- `supervisor_approval_required`
- `quality_approval_required`

## 10. Operasyon State Machine

Önerilen state machine:

```text
queued
ready
active
step_running
evidence_completed
pending_final_approval
closed
```

MVP sade state machine:

```text
queued
ready
active
evidence_completed
pending_final_approval
closed
```

Anlamlar:

- `queued`: Operasyon sırada.
- `ready`: Operasyon istasyona atanabilir veya başlatılabilir.
- `active`: Operasyon başladı.
- `evidence_completed`: Zorunlu step kanıtları tamamlandı.
- `pending_final_approval`: Sistem bitti sayıyor ama kullanıcı final onay
  vermedi.
- `closed`: Operasyon tam kapandı.

Mevcut `completed` state'i ile hedef modeldeki `evidence_completed` ve `closed`
ayrımı karıştırılmamalıdır. Geçiş planında backward-compatible mapping
tanımlanmalıdır.

## 11. Event Processing Algoritması

```text
1. Event gelir.
   Kaynak: kiosk / sensor / robot / observer / plc / system.

2. Event append-only olarak operation_events içine yazılmaya aday olur.

3. Sistem station_code + source_code + active_operation bilgisiyle ilgili step'i bulur.

4. Event beklenen step ile eşleşiyor mu kontrol edilir.

5. Event duplicate mi kontrol edilir.
   external_event_id, event_hash veya idempotency_key gerekir.

6. Step state transition valid mi kontrol edilir.

7. Event kabul edilirse operation_events içine accepted olarak yazılır.

8. Step status güncellenir.
   pending -> active
   active -> completed
   pending -> completed gibi bazı otomatik kısa geçişler kurala bağlı olabilir.

9. Tüm required_for_completion step'ler tamam mı kontrol edilir.

10. Tamam değilse operasyon active kalır.

11. Tamamsa operation_completion_policy uygulanır:
    - manual_close -> kullanıcı kapanış bekler
    - auto_close_on_required_steps -> closed
    - auto_complete_pending_approval -> evidence_completed / pending_final_approval

12. Operation kapanışı gerçekleştiğinde:
    - production_flow_event oluşturulabilir
    - successor operation queue'ya alınabilir
    - son operasyon ise work_order pending_close veya completed olabilir
```

Event processing append-only event kaydını state mutation'dan ayırmalıdır.
Rejected event'ler de mümkünse `accepted = false` ve `rejection_reason` ile
kaydedilmelidir.

## 12. Kiosk Button Generation Algoritması

```text
1. Kiosk station_code ile açılır.
2. Aktif veya sıradaki work_order_operation alınır.
3. Operation'a bağlı step instance listesi alınır.
4. İlk actionable step bulunur.
5. Step start_mode / finish_mode / status bilgisi okunur.
6. Butonlar DB policy'ye göre türetilir.
```

Buton kuralları:

```text
status = pending + start_mode = manual_start
-> Başlat butonu göster.

status = active + finish_mode = manual_finish
-> Bitir butonu göster.

finish_mode = manual_finish + approval_required_after_finish = true
-> Onayla / Son Onay butonu göster.

start_mode = auto_start
-> Başlat butonu gösterme, event bekle.

finish_mode = auto_finish
-> Bitir butonu gösterme, event bekle.

control_policy = tracking_only
-> Buton gösterme.

operation status = pending_final_approval
-> Final Onayla butonu göster.
```

Önemli kural:

```text
show_only_current_actionable_step = true
```

Kiosk aynı anda tüm adımların butonlarını göstermemelidir. MVP'de sadece current
actionable step gösterilmelidir.

## 13. Validation Kuralları

```text
start_mode = auto_start
-> start_event_source zorunlu.

finish_mode = auto_finish
-> finish_event_source zorunlu.

control_policy = auto_both
-> start_event_source ve finish_event_source zorunlu.

control_policy = evidence_only
-> finish_event_source zorunlu.

manual_start veya manual_finish olan step
-> kiosk/manual actor tanımı gerektirir.

required_for_completion = true olan tracking_only step
-> riskli; explicit warning gerektirir.

Step sequence_no benzersiz olmalıdır.

Aynı operation içinde birden fazla final approval step varsa warning veya validation error olmalıdır.

Event source station ile uyumlu olmalıdır.

Inactive event source ile auto step tanımlanamaz.

Auto step için event source eksikse sistem setup valid kabul edilmemelidir.
```

Ek öneriler:

- `operation_completion_policy = auto_close_on_required_steps` kullanılan bir
  operation'da en az bir `required_for_completion = true` step olmalıdır.
- `approval_required_after_finish = true` olan step'lerde actor/audit alanları
  zorunlu olmalıdır.
- Event source idempotency stratejisi tanımlanmadan auto step production'a
  alınmamalıdır.

## 14. Required Data Listesi

### Master Data

- `stations`
- `locations`
- `station_location_bindings`
- `items`
- `item types`
- `routes`
- `route operations`
- `operation steps`
- `station event sources`
- `control policies`
- `operation completion policies`
- `input/output item rules`
- `input/output qty`
- `output location role`
- `scrap/rework/hold behavior`

### Runtime Data

- `work orders`
- `work_order_operations`
- `work_order_operation_steps`
- `operation_events`
- `production_flow_events`
- `approvals`
- `status transitions`
- `KPI/OEE snapshots`

## 15. Minimum SQL Model Önerisi

Bu bölüm implementation değildir; sonraki schema planı için tablo tasarım
önerisidir.

### `mes.items`

Amaç: Sistemde hareket eden veya dönüşen item master datasını tutar.

Kritik alanlar:

- `item_code`
- `item_name`
- `item_type`
- `unit`
- `active`

### `mes.process_routes`

Amaç: Bir item veya ürün ailesi için üretim rotasını tanımlar.

Kritik alanlar:

- `route_code`
- `route_name`
- `item_code`
- `version`
- `active`
- `metadata`

### `mes.route_operations`

Amaç: Route içindeki operasyon sırasını, istasyonu ve input/output item
dönüşümünü tanımlar.

Kritik alanlar:

- `route_code`
- `sequence_no`
- `operation_code`
- `station_code`
- `input_item_code`
- `output_item_code`
- `input_qty_per_cycle`
- `output_qty_per_cycle`
- `operation_completion_policy`

### `mes.operation_steps`

Amaç: Operation master datası altında yürütülecek step tanımlarını tutar.

Kritik alanlar:

- `operation_code`
- `step_no`
- `step_code`
- `step_name`
- `start_mode`
- `finish_mode`
- `start_event_source`
- `finish_event_source`
- `required_for_completion`
- `records_duration`
- `approval_required_after_finish`
- `active`

### `mes.station_event_sources`

Amaç: Bir istasyondan gelebilecek sensor, robot, observer, PLC veya system
event kaynaklarını tanımlar.

Kritik alanlar:

- `station_code`
- `source_code`
- `source_type`
- `mqtt_topic`
- `active`

### `mes.work_order_operation_steps`

Amaç: Work order operation release edildiğinde oluşan runtime step instance
state'ini tutar.

Kritik alanlar:

- `work_order_operation_id`
- `step_code`
- `status`
- `started_at`
- `completed_at`
- `started_by_event_id`
- `completed_by_event_id`

### `mes.operation_events`

Amaç: Kiosk/sensor/robot/observer/PLC/system eventlerini append-only audit
kaydı olarak tutar.

Kritik alanlar:

- `event_id`
- `event_time`
- `station_code`
- `work_order_id`
- `work_order_operation_id`
- `step_code`
- `event_source`
- `event_type`
- `external_event_id`
- `idempotency_key`
- `payload`
- `accepted`
- `rejection_reason`

### `mes.production_flow_events`

Amaç: Bir operasyon sonucunda ürünün veya yarı mamulün hangi
station/location/item dönüşümünden geçtiğini semantic event olarak kaydeder.

Kritik alanlar:

- `flow_event_id`
- `work_order_id`
- `station_code`
- `operation_code`
- `input_location_code`
- `output_location_code`
- `input_item_code`
- `output_item_code`
- `input_qty`
- `output_qty`
- `event_time`
- `source_operation_event_id`

### `mes.operation_approvals`

Amaç: Final approval, supervisor approval veya quality approval gibi onayları
ayrı audit kaydı olarak tutar.

Kritik alanlar:

- `approval_id`
- `work_order_operation_id`
- `approval_type`
- `approved_by`
- `approved_at`
- `result`
- `note`

## 16. Ürün Giriş/Çıkış Mantığı

İlk fazda gerçek inventory balance yapılmayacaktır. İlk fazda
`production_flow_events` tutulabilir. Bu event, ürünün hangi
station/location/item dönüşümünden geçtiğini gösterir. Inventory movement
ileride bu eventlerden türetilebilir.

Önerilen MVP karar:

```text
production_flow_event, operation evidence_completed veya closed olduğunda oluşur.
inventory movement, final approval sonrası ayrı fazda oluşur.
```

### Option A: `production_flow_event` `evidence_completed` Anında

Artıları:

- Görünürlük erken oluşur.
- OEE/KPI v0 için temel semantic event daha hızlı kullanılabilir.

Eksileri:

- Final approval reddedilirse düzeltme/iptal event'i gerekir.
- Operatör onayı olmadan ürün akışı tamamlanmış gibi algılanabilir.

### Option B: `production_flow_event` `closed` / Final Approval Anında

Artıları:

- Ürün çıkışı onaylanmış operation kapanışına bağlanır.
- Inventory movement'a gelecekte daha güvenli köprü kurar.
- `evidence_completed` ile gerçek kapanış ayrımı korunur.

Eksileri:

- Görünürlük final approval'a kadar gecikir.

Öneri: Option B daha güvenlidir. Ancak MVP'de sadece görünürlük için Option A
kullanılabilir; bu durumda event'in inventory movement olmadığı açıkça
işaretlenmelidir.

## 17. OEE/KPI İçin Minimum Veri

OEE için önce event/timestamp güvenilirliği gerekir.

Minimum gerekli alanlar:

- `operation.started_at`
- `operation.evidence_completed_at`
- `operation.closed_at`
- `step.started_at`
- `step.completed_at`
- `planned_cycle_time`
- `actual_cycle_time`
- `good_qty`
- `scrap_qty`
- `downtime/idle` ileride

İlk KPI v0:

- Operation cycle time.
- Station active time.
- Waiting time.
- Good/scrap count.
- Simple OEE snapshot.

Inventory balance olmadan da temel OEE/KPI v0 üretilebilir. Ancak
quality/good/scrap verisi için operation result veya `production_flow_event`
gerekir.

## 18. Riskler

| Risk | Etki | Önlem |
| --- | --- | --- |
| Yanlış station/location/operation ayrımı | Model fiziksel akışı yanlış temsil eder | Terminoloji ve FK sınırlarını schema planında açık ayır |
| Auto step için event source eksikliği | Step hiç tamamlanmaz veya invalid çalışır | `auto_start`/`auto_finish` validation zorunlu olsun |
| Sensör event duplicate gelmesi | Step veya operasyon iki kez ilerler | `external_event_id`, `event_hash` veya `idempotency_key` zorunlu olsun |
| Yanlış step'e event düşmesi | Operasyon hatalı kapanır | station + source + active operation + expected step matching uygula |
| Kiosk çok fazla buton göstermesi | Operatör yanlış aksiyon alır | `show_only_current_actionable_step = true` ile başla |
| Final approval unutulması | Operasyon yarım state'te kalır | `pending_final_approval` görünür alarm/queue kriteri tasarla |
| `evidence_completed` ile `closed` ayrımının karışması | Ürün çıkışı erken kabul edilir | State isimlerini ve transition kurallarını UI/API'de açık göster |
| `production_flow_event` ile inventory movement'ın karışması | Balance yanlış anlaşılır | `production_flow_event` semantic event, inventory ayrı faz olarak belgelenmeli |
| OEE'nin eksik timestamp ile üretilmesi | KPI güvenilmez olur | KPI v0 sadece güvenilir timestamp alanlarını kullansın |
| SQL modelinin fazla erken sertleşmesi | Future sensor/policy ihtiyaçları kilitlenir | MVP enumları dar tut, JSON metadata ve versioning alanları bırak |

## 19. Faz Planı

### Faz 1 - Station Execution Model Design

Bu doküman.

### Faz 2 - Station Execution Schema Plan

Yeni SQL tablo ve migration planı.

### Faz 3 - Manual Seed/Setup Plan

İlk çalışır sistem için items, routes, operations, steps ve event sources manuel
tanımlanır.

### Faz 4 - Runtime Step Engine

Event ingestion, step transition ve operation completion policy uygulanır.

### Faz 5 - Kiosk Dynamic Action Buttons

Kiosk butonları DB policy'ye göre oluşur.

### Faz 6 - IoT Event Adapter

MQTT/sensor/robot/observer eventleri `operation_events` içine alınır.

### Faz 7 - Production Flow Event

Ürün giriş/çıkış semantic eventleri üretilir.

### Faz 8 - OEE/KPI v0

Temel OEE/KPI eventlerden hesaplanır.

### Faz 9 - Setup Automation

İlk kurulum seed/workbook/MESQL master data çekme yarı otomatik hale gelir.

## 20. Açık Kararlar

Açık kararlar:

- `control_policy` fiziksel DB alanı mı olacak yoksa derived/convenience mı?
- `production_flow_event` `evidence_completed` anında mı, final approval
  sonrasında mı oluşacak?
- Final approval operator seviyesi yeterli mi, supervisor/quality gerekli mi?
- İlk migration'da bütün future policy değerleri mi yer alacak, yoksa MVP
  enumları mı?
- Operation step instance'ları iş emri release anında mı üretilecek, operasyon
  ready olduğunda mı?
- Auto event eşleşmesi sadece active step'e mi izin verecek, yoksa buffered
  event kabul edilecek mi?
- Kiosk aynı anda kaç actionable button gösterecek?

Önerilen default kararlar:

- `start_mode` + `finish_mode` ayrı alanlar olmalıdır.
- `control_policy` convenience/derived olarak ele alınmalıdır.
- `production_flow_event` final approval sonrası daha güvenlidir.
- MVP enumları ile başlamak daha güvenlidir.
- Kiosk sadece current actionable step'i göstermelidir.
- Auto event source zorunlu olmalıdır.
- Duplicate event idempotency zorunlu olmalıdır.

## 21. Kabul Kriterleri

Bu doküman için kabul kriterleri:

- Station/Location/Operation/Step/Event/Policy ayrımı net.
- `ASSEMBLY_01` ve `PACKAGING_01` örnekleri var.
- `start_mode` ve `finish_mode` listeleri tanımlı.
- Convenience `control_policy` listesi tanımlı.
- `operation_completion_policy` listesi tanımlı.
- Event processing algoritması var.
- Kiosk button generation algoritması var.
- Validation kuralları var.
- Required data listesi var.
- Minimum SQL model önerisi var.
- `production_flow_event` ve inventory movement ayrımı net.
- OEE/KPI için minimum veri tanımlı.
- Riskler ve faz planı var.
- Implementation yapılmadı.
