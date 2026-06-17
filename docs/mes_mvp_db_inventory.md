# MES MVP DB Inventory

## 1. DB Source-of-Truth Kabul Edilenler

Bu MVP fazinda tam enterprise SOT hedeflenmiyor. Kontrollu gecis icin su tablolar operasyonel cekirdegin DB tarafindaki ana kaydi kabul edilir:

- `mes.work_orders`: work order current-state mirror/read kaynagi.
- `mes.work_order_events`: start, finish, accept, cancel, reorder ve package process transition log.
- `mes.package_component_wip`: paketleme komponent uygunluk, reserve, consume ve reset kontrol kaydi.
- `mes.production_completions`: uretilen item completion hook kaydi.
- `mes.item_station_events`: station tracking hook kaydi.
- `mes.package_traceability`: paket finished sonrasi komponent/package trace kaydi.

Kod ici SOT siniri: `mes_web/db/source_of_truth.py`.

## 2. Runtime Fallback Kalanlar

Runtime fallback bilincli olarak korunur:

- `oee_runtime_state.json`
- `workOrders.orderSequence`
- `workOrders.activeOrderId` ve `workOrders.activeOrderByStation`
- `workOrders.packagingSessions`
- shift/OEE transient state
- kiosk device/operator UI state
- dashboard/websocket snapshot cache
- Excel/FERP/MQTT operasyonel fallback akislari

DB read hata, bos sonuc veya runtime active drift durumunda work order okuma runtime JSON'a fail-open doner.

## 3. Ilk Tasinacak Tablolar

### station_queue

Mevcut kaynak: runtime `workOrders.orderSequence`.

Onerilen minimal schema:

- `station_code text not null`
- `order_id text not null`
- `queue_rank integer not null`
- `status text not null`
- `updated_at timestamptz not null default now()`
- unique: `(station_code, order_id)`
- index: `(station_code, queue_rank)`

Faz 2D-mini notu: migration yazilmadi. `mes.work_orders.metadata.queue_rank` ve `metadata.station_code` DB-readiness icin doldurulur.

### package_sessions

Mevcut kaynak: runtime `workOrders.packagingSessions`.

Onerilen minimal schema:

- `session_id text primary key`
- `package_order_id text not null`
- `station_code text not null`
- `status text not null`
- `started_at timestamptz`
- `finished_at timestamptz`
- `duration_seconds numeric`
- `payload jsonb not null default '{}'::jsonb`
- `updated_at timestamptz not null default now()`

Faz 2D-mini notu: migration yazilmadi. `package_started` ve `package_finished` olaylari `work_order_events.payload.package_process` icinde session/duration bilgisini tasir.

## 4. Current-State ve Event Tutarliligi

`mirror_work_order_transition_from_state` her transition sonrasi:

- `mes.work_orders` current-state satirlarini upsert eder.
- `mes.work_order_events` idempotent event yazar.
- status, target quantity, started/completed timestamp ve full payload korunur.
- station ownership ve queue rank `metadata` icinde tutulur.

Bu davranis `MES_WEB_DB_HOOK_WORK_ORDER_TRANSITIONS=true` ile aktiftir. Dry-run aciksa DB write yapmaz.

## 5. Runtime Reset / DB Ayrisma Riski

En kritik risk: runtime state reset veya manuel DB duzeltmesi sonrasi `oee_runtime_state.json` ile DB current-state ayrisabilir.

Koruma:

- DB read empty/error/drift durumunda runtime fallback.
- work order reset plan alanlarini korur, operasyonel alanlari sifirlar.
- WIP reset work order reset ile ayni fiziksel anlama gelmez; `package_component_wip` destructive silinmez.
- `tools/check_mes_db_consistency.ps1` read-only kontrol icin eklendi.

## 6. Bir Sonraki Sprint Onerisi

Sonraki kontrollu faz:

`work_orders + station_queue DB source-of-truth`

Minimum hedef:

- `station_queue` migration ve read path.
- reorder endpointinin queue_rank DB write/read kullanmasi.
- `activeOrderByStation` bilgisinin DB read tarafinda deterministic hesaplanmasi.
- `package_sessions` icin migration taslagi ve shadow-write.
