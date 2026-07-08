# Station Execution Schema Review Checkpoint

## 1. Amaç

Bu doküman, `docs/architecture/station_execution_schema_plan.md` dosyasının
`004_station_execution_schema.sql` migration taslağına geçmek için yeterli
olgunluğa ulaşıp ulaşmadığını değerlendirir.

Bu checkpoint implementation değildir:

- Kod yazmaz.
- SQL migration üretmez.
- DB'ye bağlanmaz.
- Docker veya psql çalıştırmaz.
- Kiosk, IoT, lifecycle veya inventory davranışı değiştirmez.

## 2. Review Sonucu

Schema plan migration planlamasına geçmek için yeterlidir.

Gerekçe:

- Master data ve runtime execution tabloları ayrılmıştır.
- Mevcut `work_order_operations` ve `station_queue` lifecycle'ı ilk fazda
  korunmaktadır.
- Yeni execution state için sidecar tablo yaklaşımı seçilmiştir.
- `operation_steps` ilişki anahtarı `route_operation_id` olarak
  netleştirilmiştir.
- Event source matching station-scoped olarak tanımlanmıştır.
- Event ledger append-only, runtime state mutation ise ayrı katman olarak
  konumlanmıştır.
- `production_flow_events` inventory movement veya balance olarak
  yorumlanmayacak şekilde ayrılmıştır.

Sonuç:

```text
004_station_execution_schema.sql için migration planı hazırlanabilir.
Henüz migration SQL yazılmamalıdır.
```

## 3. Migration Öncesi Kapanmış Kararlar

Aşağıdaki kararlar migration planı açısından kapanmış kabul edilir:

- `start_mode` ve `finish_mode` ayrı fiziksel alanlardır.
- `control_policy` engine için zorunlu ana alan değildir.
- `control_policy`, seed/setup kolaylığı için metadata veya opsiyonel convenience
  alanı olarak değerlendirilebilir.
- MVP enumları dar tutulacaktır.
- Future enum değerleri ilk migration'da aktif engine davranışı olarak
  kullanılmayacaktır.
- Auto step için event source zorunludur.
- Kiosk MVP'de sadece current actionable step'i gösterecektir.
- `operation_completion_policy = auto_complete_pending_approval` ana hedef
  modeldir.
- `production_flow_event` için güvenli default final approval / closed sonrası
  oluşmasıdır.
- Inventory movement ve balance bu migration fazının dışındadır.
- `operation_events` append-only audit ledger olarak kullanılacaktır.
- Runtime state mutation ile event ledger ayrı tutulacaktır.
- `operation_steps`, `route_operation_id` üzerinden `route_operations` satırına
  bağlanacaktır.
- `operation_code` okunabilir business alan olarak kalacaktır; tek başına step
  FK gibi kullanılmayacaktır.
- Event source station-scoped kabul edilecektir.
- Yeni execution state için `mes.work_order_operation_execution_state` sidecar
  tablosu kullanılacaktır.
- Mevcut `work_order_operations.status` ilk fazda bozulmayacaktır.

## 4. Migration Öncesi Dikkat Edilecek Noktalar

Bu maddeler migration SQL yazılırken açıkça ele alınmalıdır:

- FK circularity:
  `work_order_operation_execution_state`, `work_order_operation_steps`,
  `operation_events` ve `operation_approvals` arasında bazı ilişki kolonları ilk
  fazda nullable başlamalıdır.
- `last_event_id`, `last_approval_id`, `started_by_event_id`,
  `completed_by_event_id` gibi audit linkleri migration sırasında zorunlu FK
  haline getirilmemelidir.
- `operation_events` idempotency kuralı station-scoped olmalıdır:
  `(station_code, event_source, external_event_id)` where `external_event_id is
  not null`.
- Future alternatif olarak `event_source_id + external_event_id` değerlendirilebilir,
  fakat ilk migration buna zorlanmamalıdır.
- `operation_steps.start_event_source_code` ve
  `operation_steps.finish_event_source_code` doğrudan global FK gibi
  modellenmemelidir. Geçerlilik, `route_operation.station_code + source_code`
  kombinasyonuyla setup validator tarafından doğrulanmalıdır.
- Seed verisi schema migration içine karıştırılmamalıdır.

## 5. Implementation Öncesi Kapanması Gerekenler

Aşağıdaki kararlar migration yazımını engellemez; ancak runtime engine veya UI
implementation başlamadan önce kapanmalıdır:

- Step instance üretim zamanı:
  - Operation ready olduğunda mı?
  - Work order release olduğunda mı?
- Runtime engine feature flag adı ve default değeri.
- Sidecar state'in API/UI'ye hangi fazda açılacağı.
- Mevcut `work_order_operations.status` ile
  `work_order_operation_execution_state.execution_status` mapping tablosu.
- `production_flow_event` kesin üretim anı:
  - `closed` / final approval sonrası güvenli default.
  - `evidence_completed` yalnız read-only visibility için opsiyonel.
- Setup validator'ın ilk formu:
  - CLI/script.
  - Admin endpoint.
  - Manual runbook checklist.
- Kiosk dynamic action payload şekli.
- Rejected eventlerin UI/API'de nasıl gösterileceği.

## 6. Future Olarak Kalabilecekler

Aşağıdaki konular ilk migration ve ilk runtime implementation için zorunlu
değildir:

- Inventory movement ledger.
- Balance/current stock view.
- Full WMS davranışı.
- MESQL master data sync.
- Supervisor/quality approval workflow derinleştirmesi.
- Buffered auto event processing.
- Advanced OEE dashboard.
- Setup workbook import automation.
- Global operation catalog.
- Timed/scheduled/external future policy değerleri.

## 7. Hazırlık Durumu

`004_station_execution_schema.sql` için önerilen hazırlık durumu:

```text
Schema design: READY_FOR_MIGRATION_PLAN
Migration SQL: NOT_STARTED
Seed SQL: NOT_STARTED
Runtime implementation: NOT_STARTED
Kiosk dynamic action implementation: NOT_STARTED
IoT adapter implementation: NOT_STARTED
OEE/KPI implementation: NOT_STARTED
```

## 8. Guardrails

Bu checkpoint ile aşağıdakiler yapılmamıştır:

- Kod değişikliği.
- SQL migration oluşturma.
- DB bağlantısı.
- Docker/compose/container çalıştırma.
- psql çalıştırma.
- MESQL push/pull.
- Kiosk implementation.
- Operation lifecycle mutation.
- Inventory movement/balance implementation.
- Test/smoke çalıştırma.
