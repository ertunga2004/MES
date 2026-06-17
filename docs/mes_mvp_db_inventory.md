# MES MVP DB Inventory

## 1. Mevcut MES MVP Tablolari / State Kaynaklari

PostgreSQL tarafinda kullanilan ana tablolar:

- `mes.work_orders`
- `mes.work_order_events`
- `mes.production_completions`
- `mes.item_station_events`
- `mes.package_bom_lines`
- `mes.package_component_wip`
- `mes.package_traceability`

Runtime/state kaynaklari:

- `oee_runtime_state.json`
- work order FERP JSON import dosyalari
- Excel workbook log/output
- MQTT/observer event akisi
- dashboard/kiosk memory snapshot

## 2. Su An PostgreSQL'de Olan Veriler

- Work order current-state mirror: `mes.work_orders`
- Work order transition/event log: `mes.work_order_events`
- Uretim completion kayitlari: `mes.production_completions`
- Istasyon event kayitlari: `mes.item_station_events`
- Paket BOM satirlari: `mes.package_bom_lines`
- Paket komponent WIP: `mes.package_component_wip`
- Paket traceability: `mes.package_traceability`

## 3. Hala JSON / Runtime / Memory Tarafinda Olan Veriler

- Shift runtime state
- Global ve station active state uyumluluk alanlari
- Kiosk device registry
- Operator secimi ve kiosk session state
- Packaging session runtime state
- Dashboard snapshot cache
- Excel export/import operational fallback
- MQTT son event bufferlari
- OEE trend ve recent item listeleri

## 4. Ana DB Fazinda Kalicilastirilmasi Gereken Ilk 10 Entity

1. `work_orders`
2. `work_order_events`
3. `stations`
4. `operators`
5. `package_component_wip`
6. `package_sessions`
7. `item_traceability`
8. `quality_events`
9. `station_queue`
10. `station_status` veya `dashboard_snapshots`

## 5. Riskler

- Runtime state ile DB current-state ayrisabilir.
- Legacy `activeOrderId` alanlari station-scoped modelle birlikte uyumluluk icin yasiyor.
- JSON bootstrap/fallback halen operasyonel guvenlik agi olarak kullaniliyor.
- Excel/FERP/MQTT akislari tam SQL source-of-truth degil.
- Paket WIP fiziksel uretimi temsil ettigi icin destructive reset/cancel islemlerinde ayrica korunmali.

## 6. Sonraki DB Fazi Onerisi

Once `work_orders` + `station_queue` + `work_order_events` PostgreSQL source-of-truth yapilmali.

Bundan sonra `package_sessions`, `package_component_wip`, `item_traceability` ve `quality_events` runtime JSON'dan kademeli olarak DB merkezli hale getirilmeli.
