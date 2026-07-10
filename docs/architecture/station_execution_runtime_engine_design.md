# Station Execution Runtime Engine Design

## 1. Amaç

Bu doküman, SQL-driven station execution runtime engine davranışını tasarlar.
Hedef, Kiosk/sensor/robot/observer eventlerini append-only ledger'a kaydederken
step state ve operation-level sidecar state'i kontrollü şekilde güncellemektir.

Bu doküman implementation değildir. Kod yazmaz, SQL migration üretmez, DB'ye
bağlanmaz ve mevcut operation lifecycle davranışını değiştirmez.

## 2. Kapsam

- Event processing algoritması.
- `operation_events` append-only ledger davranışı.
- `work_order_operation_steps` step transition kuralları.
- `work_order_operation_execution_state` sidecar state update mantığı.
- `evidence_completed`, `pending_final_approval`, `closed` transition'ları.
- Mevcut `work_order_operations` / `station_queue` lifecycle ile compatibility
  mode.

## 3. Kapsam Dışı

- Python/API implementation.
- SQL migration.
- Kiosk UI implementation.
- MQTT/IoT adapter implementation.
- Inventory movement/balance.
- MESQL push/pull.
- Docker/DB/psql/test/smoke çalıştırma.

## 4. Temel İlkeler

- `operation_events` append-only audit ledger'dır.
- Runtime state mutation ledger'dan ayrıdır.
- Rejected eventler mümkünse `accepted = false` ve `rejection_reason` ile
  saklanır.
- Event idempotency station-scoped olmalıdır.
- Yeni execution state sidecar tabloda tutulur.
- Mevcut `work_order_operations.status` ilk fazda source-of-truth olmaya devam
  eder.
- Yeni engine feature flag / compatibility mode ile devreye alınır.

## 5. Runtime Aktörleri

Event kaynakları:

- Kiosk.
- Sensor.
- Robot.
- Observer.
- PLC.
- System/internal transition.

Runtime hedefleri:

- `mes.operation_events`
- `mes.work_order_operation_steps`
- `mes.work_order_operation_execution_state`
- Opsiyonel final aşamada `mes.operation_approvals`
- Opsiyonel final aşamada `mes.production_flow_events`

## 6. Event Processing Akışı

Logical akış:

```text
1. Event request alınır.
2. station_code ve source_code normalize edilir.
3. station_code + source_code active station_event_sources içinde doğrulanır.
4. external_event_id veya idempotency_key ile duplicate kontrolü yapılır.
5. İlgili active/ready work_order_operation bulunur.
6. Operation için sidecar execution state bulunur veya compatibility mode'a göre hazırlanır.
7. Current actionable step çözülür.
8. Event, beklenen step start/finish/evidence/approval davranışıyla eşleşiyor mu kontrol edilir.
9. operation_events ledger kaydı oluşturulur.
10. Event kabul edilirse step state transition uygulanır.
11. Required step completion kontrol edilir.
12. operation_completion_policy uygulanır.
13. Sidecar execution_state güncellenir.
14. Gerekirse approval veya production_flow_event adayı oluşur.
15. Mevcut lifecycle mutation gerekiyorsa feature flag ve compatibility mapping ile ayrı fazda ele alınır.
```

## 7. Idempotency

MVP idempotency anahtarı:

```text
station_code + event_source + external_event_id
```

Alternatif:

```text
idempotency_key
```

Kurallar:

- Aynı station/source/external_event_id tekrar gelirse step ikinci kez
  ilerlememelidir.
- Duplicate accepted event yeniden state mutation üretmemelidir.
- Aynı `source_code` farklı istasyonlarda tekrar edebileceği için station code
  idempotency anahtarının parçası olmalıdır.
- IoT tarafı external event id üretmiyorsa adapter deterministic idempotency key
  üretmelidir.

## 8. Step State Transition Kuralları

Step status değerleri:

```text
pending
active
completed
skipped
failed
cancelled
```

MVP transition önerileri:

| Current | Trigger | Next |
| --- | --- | --- |
| `pending` | manual start | `active` |
| `pending` | auto start | `active` |
| `pending` | auto finish with implicit start | `completed` |
| `active` | manual finish | `completed` |
| `active` | auto finish | `completed` |
| `pending` | implicit start after previous completed | `active` |
| `active` | cancel/fail | `cancelled` veya `failed` |

Guardrails:

- Completed step tekrar completed yapılmamalıdır.
- Required step skip yalnız explicit policy ile mümkün olmalıdır.
- Auto finish event yanlış station/source'tan geldiyse rejected event olmalıdır.
- Future buffered events ilk MVP davranışı değildir.

## 9. Current Actionable Step Algoritması

MVP algoritması:

```text
1. Operation step instance'larını step_no ASC sırala.
2. İlk pending veya active step'i bul.
3. Step active ise finish action mümkün mü kontrol et.
4. Step pending ise start action mümkün mü kontrol et.
5. Auto-only step ise buton üretme; event bekle.
6. Manual action varsa sadece bu step için action üret.
7. Required completed ise sonraki step'e geç.
```

Kural:

```text
show_only_current_actionable_step = true
```

## 10. Operation-Level Sidecar State

Tablo:

```text
mes.work_order_operation_execution_state
```

MVP execution status değerleri:

```text
queued
ready
active
evidence_completed
pending_final_approval
closed
cancelled
failed
```

State anlamı:

- `queued`: Operation henüz current station action'a hazır değildir.
- `ready`: Operation istasyon için hazırlanabilir durumdadır.
- `active`: En az bir step başlamıştır veya operation active kabul edilmiştir.
- `evidence_completed`: Required evidence/step seti tamamlanmıştır.
- `pending_final_approval`: Sistemsel kanıt tamamdır, final approval beklenir.
- `closed`: Operation tam kapanmıştır.

## 11. Completion Policy Davranışı

### `manual_close`

- Tüm required steps completed olduğunda operation `evidence_completed` olur;
  `active` kalmaz.
- `current_step_code = null` ve `evidence_completed_at = triggering_event_time`
  set edilir.
- `pending_final_approval_at` ve `closed_at` null kalır.
- Kiosk explicit operation close action gösterir; `closed` transition ayrı
  future close helper/fazının sorumluluğudur.

### `auto_close_on_required_steps`

- Tüm required steps completed olduğunda operation `closed` olur.
- `current_step_code = null`, `evidence_completed_at = triggering_event_time`
  ve `closed_at = triggering_event_time` set edilir.
- `pending_final_approval_at` null kalır.
- Final approval yoktur.
- Production flow event closed sonrası üretilebilir.

### `auto_complete_pending_approval`

- Tüm required steps completed olduğunda operation doğrudan
  `pending_final_approval` olur.
- `current_step_code = null`, `evidence_completed_at = triggering_event_time`
  ve `pending_final_approval_at = triggering_event_time` set edilir.
- `closed_at` null kalır.
- Final approval accepted olduğunda `closed` olur.
- Bu fazda approval row oluşturulmaz.

Her üç policy transition'ında triggering `step_finish` event ID değeri
`last_event_id` olur ve `updated_at = triggering_event_time` set edilir.
Mevcut `started_at` ve `last_approval_id` korunur. Policy otoritesi
`work_order_operation_execution_state.operation_completion_policy` veya onun
kaynak config değeridir; `operation_steps.approval_required_after_finish` tek
başına `pending_final_approval` transition'ı üretemez.

Policy transition için ek `system_transition` event'i oluşturulmaz. Event
insert, step completion ve policy update aynı `finish_execution_step`
transaction/cursor akışında atomik yürür. Approval, manual close, production
flow ve work-order lifecycle mutation ayrı future helper/fazlardır.

## 12. Approval Akışı

MVP:

- Final approval operator seviyesinde yeterlidir.
- Approval event Kiosk kaynaklı olabilir.
- Approval audit `operation_approvals` içinde tutulur.
- Approval sonrası `execution_state.closed_at` set edilebilir.

Rejected approval:

- `operation_approvals.result = rejected` olarak auditlenir.
- Execution state `pending_final_approval` veya explicit `failed/hold` benzeri
  future state'e taşınabilir.
- MVP'de rejected handling implementation öncesi ayrıca netleştirilmelidir.

## 13. Compatibility Mode

İlk implementation fazı existing lifecycle'ı kırmamalıdır:

- `work_order_operations.status` yeni state değerleriyle genişletilmez.
- `station_queue` mevcut queue visibility için kullanılmaya devam eder.
- Sidecar state read/compare amaçlı tutulur.
- Successor activation mevcut verified davranışıyla devam eder.
- Feature flag kapalıyken yeni engine state mutation yapmamalıdır.

Mapping ihtiyacı:

| Existing lifecycle | Sidecar önerisi |
| --- | --- |
| queued | queued |
| ready | ready |
| active / in_progress | active |
| completed | closed veya compatibility completed mapping |
| cancelled | cancelled |
| failed | failed |

Bu mapping implementation öncesi test senaryolarıyla netleştirilmelidir.

## 14. Production Flow Event Trigger

Güvenli default:

```text
production_flow_event closed / final approval sonrası oluşur.
```

MVP visibility alternatifi:

```text
evidence_completed anında semantic production_flow_event üretilebilir.
```

Bu alternatif kullanılırsa event'in inventory movement olmadığı açıkça
etiketlenmelidir.

## 15. Rejected Event Davranışı

Rejected event nedenleri:

- Unknown station.
- Unknown source.
- Inactive source.
- Duplicate event.
- No active operation.
- No matching step.
- Step already completed.
- Wrong event type.
- Invalid transition.

Rejected eventler audit açısından değerlidir. Mümkünse ledger'a
`accepted = false` olarak yazılmalıdır; state mutation yapılmamalıdır.

## 16. Kabul Kriterleri

Bu runtime engine design tamamlanmış sayılır, eğer:

- Event ingestion akışı tanımlıysa.
- Append-only ledger ile state mutation ayrılmışsa.
- Step transition kuralları tanımlıysa.
- Sidecar operation state davranışı açıklanmışsa.
- `evidence_completed`, `pending_final_approval`, `closed` transition'ları
  ayrılmışsa.
- Compatibility mode mevcut lifecycle'ı koruyorsa.
- Inventory movement/balance kapsam dışı kalıyorsa.
- Kod veya migration üretilmemişse.

## 17. Canonical Observation and Approval Semantics

The runtime engine treats `PROCESS_END_OBSERVATION` exactly like any other
configured step. Row presence and the generic `start_mode`, `finish_mode`,
`required_for_completion`, `records_duration`, and `active` fields control its
behavior. No step-code-specific observation branch is allowed.

Final approval is a separate operation-level transition and audit record:

```text
required steps complete
-> apply operation_completion_policy
-> when policy requires authorization, record mes.operation_approvals
-> close operation only after the policy condition is satisfied
```

`approval_required_after_finish` remains a compatibility field for existing V1
configuration. The canonical observation target sets it to `false`; putting
`APPROVAL` in an observation identifier does not create the operation-level
audit semantics.

Quality control, when configured, arrives at the engine as a distinct route
operation and execution context with its own steps. Work-order closure remains
outside the operation step engine and requires a separate lifecycle policy.

The retained V1 `OPERATOR_OBSERVATION_APPROVAL` instance and its historical
events are not renamed or mutated by this clarification.
