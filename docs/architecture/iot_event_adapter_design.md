# IoT Event Adapter Design

## 1. Amaç

Bu doküman, renk sensörü, robot kol, observer, PLC veya MQTT kaynaklı olayların
SQL-driven station execution modelinde `operation_events` ledger'ına nasıl
alınacağını tasarlar.

Bu doküman implementation değildir. MQTT, observer, Python/API, Docker veya DB
davranışı değiştirmez.

## 2. Kapsam

- IoT event envelope tasarımı.
- Station-scoped event source mapping.
- Idempotency ve duplicate handling.
- Accepted/rejected event yaklaşımı.
- Auto step matching.
- Adapter ile runtime engine sınırı.

## 3. Kapsam Dışı

- MQTT client implementation.
- Observer implementation.
- Robot/sensor firmware.
- API endpoint implementation.
- SQL migration.
- DB/psql/Docker/test/smoke.
- Inventory movement/balance.
- MESQL push/pull.

## 4. Event Envelope Önerisi

IoT adapter runtime engine'e normalize edilmiş event iletmelidir:

```text
station_code
source_code
event_type
external_event_id
event_time
payload
idempotency_key
```

Opsiyonel alanlar:

```text
work_order_id
work_order_operation_id
step_code
confidence
raw_topic
raw_payload
```

Adapter, raw sensor/robot formatını runtime engine'in beklediği bu normalize
şekle çevirir.

## 5. Station-Scoped Source Mapping

Kritik kural:

```text
source_code global unique değildir.
Event source geçerliliği station_code + source_code ile yapılır.
```

Örnekler:

- `ASSEMBLY_01 + COLOR_SENSOR_ENTRY`
- `ASSEMBLY_01 + ROBOT_ARM_DROP`
- `PACKAGING_01 + KIOSK_OPERATOR`

Mapping validator:

- Station var mı?
- Source bu station altında tanımlı mı?
- Source active mı?
- Source channel gelen transport ile uyumlu mu?
- Auto step bu source'u bekliyor mu?

## 6. MQTT Topic Yaklaşımı

Önerilen topic shape:

```text
mes/stations/{station_code}/sources/{source_code}/events
```

Örnek:

```text
mes/stations/ASSEMBLY_01/sources/COLOR_SENSOR_ENTRY/events
mes/stations/ASSEMBLY_01/sources/ROBOT_ARM_DROP/events
```

Topic'ten gelen station/source bilgisi payload ile çelişirse adapter event'i
rejected adayı olarak işaretlemelidir.

## 7. Idempotency

Adapter mümkünse stable `external_event_id` üretmelidir.

Kaynak sistem external id vermiyorsa:

```text
idempotency_key = station_code + source_code + event_type + normalized event_time bucket + payload hash
```

Not:

- Bu bir implementation tarifi değil, tasarım prensibidir.
- Hash/bucket detayı implementation öncesi ayrıca netleştirilmelidir.
- Duplicate event state mutation üretmemelidir.

## 8. Accepted Event Davranışı

Event accepted olmak için:

- Station/source active olmalıdır.
- Duplicate olmamalıdır.
- İlgili operation/step bulunmalıdır.
- Event type beklenen transition ile uyumlu olmalıdır.
- Auto step source code ile eşleşmelidir.

Accepted event:

- `operation_events.accepted = true` olarak ledger'a yazılır.
- Runtime engine step state transition uygular.
- Sidecar execution state güncellenebilir.

## 9. Rejected Event Davranışı

Rejected nedenleri:

- Unknown station.
- Unknown source.
- Inactive source.
- Invalid channel.
- Duplicate event.
- No active operation.
- No matching current step.
- Wrong event type.
- Payload validation failed.

Mümkünse rejected event de ledger'a yazılmalıdır:

```text
accepted = false
rejection_reason = ...
```

State mutation yapılmamalıdır.

## 10. Adapter / Runtime Engine Sınırı

Adapter sorumluluğu:

- Transport okumak.
- Raw payload normalize etmek.
- Basic envelope validation yapmak.
- Idempotency key adayını üretmek.
- Runtime engine'e event sunmak.

Runtime engine sorumluluğu:

- Station/source setup validation.
- Current operation/step matching.
- Duplicate kararını kesinleştirme.
- Ledger write.
- Step/state transition.
- Rejection reason üretme.

## 11. Örnek Event Kaynakları

### `COLOR_SENSOR_ENTRY`

- Station: `ASSEMBLY_01`
- Source type: `sensor`
- Beklenen kullanım: color/classification evidence.
- Step: `COLOR_SENSOR_ENTRY_EVIDENCE`
- Start/finish: auto start + auto finish.

### `ROBOT_ARM_DROP`

- Station: `ASSEMBLY_01`
- Source type: `robot`
- Beklenen kullanım: robot drop completed evidence.
- Step: `ROBOT_ARM_DROP_COMPLETED`
- Finish: auto finish.

### `KIOSK_OPERATOR`

- Station-scoped kiosk source.
- `ASSEMBLY_01` ve `PACKAGING_01` altında ayrı kaynak olabilir.
- Manual finish / approval eventleri için kullanılır.

## 12. Buffered Event Kararı

MVP default:

```text
Buffered event processing yok.
```

Gerekçe:

- İlk runtime engine daha deterministik kalır.
- Yanlış sıradaki sensor eventleri rejected olarak görülebilir.
- Debug ve evidence daha kolaydır.

Future:

- Erken gelen sensor eventleri kısa süreli buffer'a alınabilir.
- Bu davranış ayrı risk ve idempotency tasarımı ister.

## 13. Kabul Kriterleri

Bu tasarım tamamlanmış sayılır, eğer:

- Event envelope önerisi varsa.
- Station-scoped event source mapping netse.
- Idempotency ve duplicate handling tanımlıysa.
- Accepted/rejected event ayrımı yazılmışsa.
- Adapter ile runtime engine sorumluluk sınırı ayrılmışsa.
- Implementation yapılmamışsa.
