# Data Model

## Amac

Bu dokuman, projede aktif olarak kullanilan veri yapilarini aciklar. Eski CSV odakli model yerine runtime state, dashboard snapshot, kiosk snapshot ve workbook sheet'leri uzerinden dusunulmelidir.

## Canli Veri Kaynaklari

### 1. MQTT Text ve JSON Akisi

Ana hat topicleri:

- `status`
- `logs`
- `heartbeat`
- `bridge/status`
- `tablet/log`

Vision topicleri:

- `vision/status`
- `vision/heartbeat`
- `vision/tracks`
- `vision/events`

Bu veri kalici model degil, operasyonel olay katmanidir.

### 2. Dashboard Snapshot

`mes_web` tarafinda browser dashboard'a giden ana modeldir.

Ana bloklar:

- `module_meta`
- `connection`
- `system_status`
- `hardware_status`
- `counts`
- `recent_logs`
- `command_permissions`
- `timestamps`
- `vision_ingest`
- `oee`
- `work_orders`

### 3. Kiosk Snapshot

Kiosk route'u icin uretilen ayri UI kontratidir.

Ana bloklar:

- `device`
- `operator`
- `operators`
- `line_status`
- `work_orders`
- `recent_items`
- `operational_state`
- `big_action`
- `active_fault`
- `help_request`
- `maintenance`
- `system_start`

### 4. Teknisyen Snapshot

Teknisyen route'u icin uretilen canli cagri kontratidir.

Ana bloklar:

- `module`
- `device`
- `technician`
- `summary`
- `active_requests`
- `resolved_today`
- `recent_requests`

### 5. OEE Runtime State

Dosya:

- `logs\oee_runtime_state.json`

Ana alanlar:

- `shiftSelected`
- `performanceMode`
- `targetQty`
- `idealCycleMs`
- `idealCycleSec`
- `plannedStopMs`
- `plannedStopMin`
- `operationalState`
- `shift`
- `counts`
- `itemsById`
- `recentItemIds`
- `workOrders`
- `maintenance`
- `helpRequest`
- `deviceRegistry`
- `deviceSessions`
- `activeFault`
- `faultHistory`
- `unplannedDowntimeMs`
- `manualFaultDurationMs`
- `trend`
- `qualityOverrideLog`
- `lastEventSummary`
- `lastUpdatedAt`

`helpRequest` satirlari teknisyen surelerini de tasir:

- `status`: `open`, `acknowledged`, `resolved`
- `faultId`, `faultCode`, `reason`, `faultStartedAt`
- `technicianName`
- `responseDurationMs`
- `repairDurationMs`
- `totalDurationMs`

Ic sure modeli ms-first'tur. `sec/min` alanlari geriye uyum icin turetilir.

### 6. Gunluk Workbook

Dosya:

- `logs\MES_Konveyor_Veritabani_GG-AA-YYYY.xlsx`

Aktif sheet'ler:

- `1_Olay_Logu`
- `2_Olcumler`
- `3_Arizalar`
- `4_Uretim_Tamamlanan`
- `5_OEE_Anliklari`
- `6_Vision`
- `7_Is_Emirleri`
- `8_Depo_Stok`
- `9_Bakim_Kayitlari`
- `99_Raw_Logs`

## Kimlikler

### `item_id`

Bir urunun hatta girdikten sonra tamamlanana kadar tasidigi ana kimliktir.

### `measure_id`

Olcum veya siniflandirma anini temsil eden kimliktir.

### `vision_track_id`

Sadece vision observer tarafindaki track kimligidir. `item_id` yerine gecmez.

### `device_id`

Kiosk veya teknisyen browser istemcisinin cihaz kimligidir. Device registry bunun uzerinden tutulur.

## Olay ve Urun Kurallari

### Tamamlanan Urun

- aktif vardiyada `RELEASED` veya `PICKPLACE_DONE` ile tamamlanan urun runtime state'e islenir
- varsayilan kalite `GOOD` kabul edilir
- kiosk veya dashboard uzerinden `GOOD / REWORK / SCRAP` override yapilabilir

### Inventory Backfill

- aktif is emrine uymayan tamamlanmis urun `off_order_completion` ile depoya alinabilir
- `SCRAP` sinifindaki urun inventory'ye alinmaz
- inventory'deki bir urun sonradan `SCRAP` olursa listeden dusurulur

### Work Order Modeli

`workOrders` blogu su alanlari tutar:

- `toleranceMs`
- `toleranceMinutes`
- `ordersById`
- `orderSequence`
- `activeOrderId`
- `lastCompletedOrderId`
- `lastCompletedAt`
- `inventoryByProduct`
- `transitionLog`
- `completionLog`
- `source`

Order satirlarinda ms taraflari da tutulur:

- `setupTimeMs`
- `cycleTimeMs`
- `plannedDurationMs`
- `runtimeMs`
- `unplannedMs`

## OEE Sure Kurallari

### Siniflandirma

- `openingChecklistDurationMs`
  - OEE disi
- `closingChecklistDurationMs`
  - planned stop / planned maintenance
- `manualFaultDurationMs`
  - unplanned stop

### Formuller

- `Availability = runtime / planned_production_elapsed`
- `planned_production_elapsed = elapsed - planned_stop_budget`
- `runtime = planned_production_elapsed - unplanned_downtime`
- `Performance = completed / expected_by_shift_rate` veya `completed / expected_by_cycle`
- `expected_by_shift_rate = targetQty * planned_production_elapsed / planned_production_total`
- `Quality = good / total`
- `OEE = Availability * Performance * Quality`

## Workbook Sheet Modeli

### `1_Olay_Logu`

- normalize olay kaydi
- kiosk fault, help, teknisyen ack/resolve, maintenance ve audit eventleri burada da tutulur

### `3_Arizalar`

- kiosk kaynakli manuel fault satirlari
- `duration_ms` ve `duration_sec` birlikte yazilir

### `4_Uretim_Tamamlanan`

- `detected_at`
- `completed_at`
- `flow_ms`
- `cycle_ms`
- `final_quality_code`

### `7_Is_Emirleri`

- aktif ve tamamlanan is emirlerinin normalize workbook yansimasi
- ms ve sec kolonlari birlikte bulunur

### `8_Depo_Stok`

- off-order completion veya rollback ile depoya dusen urunler
- hurda urun burada yer almaz

### `9_Bakim_Kayitlari`

- maintenance checklist step detay kaydi
- `duration_ms` ve `duration_sec` birlikte yazilir

## Sonraki Adimlar

- teknisyen cagri ekraninin saha sureleriyle dogrulanmasi
- direct JSON event/state topic kontrati
- workbook replay / rebuild araci
