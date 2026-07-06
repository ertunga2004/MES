# Local Station Inventory Model

Bu dokuman mevcut local MES DB ve runtime state yapisini read-only incelemeye dayanir. Kod, migration veya DB schema degisikligi yapilmaz; MESQL entegrasyonu bu kapsamda bilincli olarak disarida tutulur.

## Mevcut Durum

Local MES tarafinda iki paralel model vardir:

- Runtime JSON/state modeli: `workOrders.ordersById`, `orderSequence`, `activeOrderByStation`, `inventoryByProduct`, `packagingBuffer`, `packagingSessions`, `itemsById`.
- PostgreSQL shadow/current-state modeli: `mes.work_orders`, `mes.work_order_operations`, `mes.station_queue`, `mes.item_station_events`, `mes.package_sessions`, `mes.package_component_wip`, `mes.package_traceability`, `mes.production_completions`.

`mes.stations` tablosu mevcut ve `ASSEMBLY_01`, `PACKAGING_01` gibi station domain key'lerini tasiyabiliyor. Ancak istasyonlarin input/output lokasyonlari bu tabloda veya baska bir lokasyon tablosunda birinci sinif kavram olarak temsil edilmiyor.

`mes.work_order_operations` operasyon seviyesini tasiyor: `order_id`, `operation_no`, `sequence_no`, `station_code`, `status`, miktarlar ve zaman damgalari. V2 operation endpointleri bu tabloyu DB-authoritative kabul ediyor.

`mes.station_queue` istasyon bazli gunluk queue projeksiyonu. V2 migration sonrasi `work_order_operation_id` kolonu var; yani operasyon baglami destekleniyor. Eski transition hook tarafinda ise queue satirlari daha cok `station_code + order_id + queue_rank + status` uzerinden uretiliyor.

`inventoryByProduct` runtime state icinde renk/urun eslesmesine gore toplu stok projeksiyonu gibi calisiyor. Bu bir hareket defteri degil; hangi lokasyondan hangi lokasyona ne zaman consume/produce yapildigini append-only sekilde saklamiyor.

`packagingBuffer` runtime state icinde paketleme input buffer'i gibi calisiyor. Tamamlanan GOOD assembly item'lari uygun olursa buffer'a giriyor, paketleme start sirasinda reserve ediliyor, finish sirasinda consumed oluyor. DB tarafinda bunun kismi karsiligi `mes.package_component_wip` ve `mes.package_traceability`.

`package_sessions` paketleme proses oturumunu temsil ediyor. Paketleme, runtime tarafinda ayri bir package flow/session olarak modellenmis; DB'de `mes.package_sessions` shadow-write ile tutuluyor. Paketleme ayni zamanda is emri seviyesinde `WO-PKT-*` gibi package work order'larla da baglaniyor. Bu nedenle is emri, operasyon, queue ve package session kavramlari tamamen ayrilmis degil; birlikte calisiyor ama sinirlar karisik.

## Tespit Edilen Eksikler

1. Station input/output location kavrami yok. Station tanimi sadece `station_code`, isim, line ve metadata seviyesinde.
2. Ara stok/buffer location kavrami genel ve tutarli bir tablo olarak yok. Paketleme icin runtime `packagingBuffer` ve DB `package_component_wip` var, fakat genel station buffer/location modeli degil.
3. Inventory movement defteri yok. `inventoryByProduct`, `package_component_wip`, `production_completions` ve `item_station_events` birlikte iz birakiyor ama tek bir stok hareket ledger'i degiller.
4. Sensor event ile stok hareketi arasinda dogrudan, kavramsal bir consume/produce/backflush baglantisi yok. Sensor/MEGA log item state'i guncelliyor; item completion sonrasinda work order veya inventory/buffer routing tetikleniyor.
5. Operation complete sonrasi local successor activation davranisi gorunmuyor. `complete_operation_v2` mevcut operasyonu completed yapar, queue satirini completed yapar, tum operasyonlar bittiyse work order'i completed yapar; bir sonraki operasyonu queued/ready yapma veya queue'ya publish etme adimi yok.
6. `station_queue` iki farkli anlamda kullaniliyor: runtime work order sirasi projeksiyonu ve v2 operation queue. Bu gecis icin yararli, fakat hedef modelde queue satiri mutlaka operation ve input location baglamina baglanmali.
7. Runtime state ile DB arasinda fail-open shadow-write/read yaklasimi var. Bu prototip icin guvenli, fakat fiziksel konveyor hattinda source-of-truth siniri netlesmezse drift riski var.

## Hedef Kavram Modeli

Hedef local execution cekirdegi su kavramlari ayirmali:

- Work order: Ne uretilecek ve hangi operasyon rotasindan gececek?
- Operation: Is emrinin belirli station/location uzerindeki icra adimi.
- Station: Fiziksel veya manuel is merkezi. Operator, sensor, PLC veya kiosk ile etkilesir.
- Location: Stokun fiziksel veya mantiksal bulundugu yer. Ornek: `RAW_IN`, `ASSEMBLY_01_IN`, `ASSEMBLY_01_WIP`, `ASSEMBLY_01_OUT`, `PKG_BUFFER`, `PACKAGING_01_IN`, `FG_OUT`.
- Buffer: Bir location turudur; iki istasyon arasinda bekleyen WIP veya komponent stokunu temsil eder.
- Station queue: Bir stationda icra edilecek operation sirasi. Work order listesi degil, operation execution listesi olmalidir.
- Package session: Paketleme operasyonunun icindeki oturum/proses calismasi. Work order veya operation yerine gecmemeli.
- Inventory movement: Her consume, produce, transfer, reserve, release, scrap ve backflush olayinin append-only kaydi.

## Station / Location / Buffer Ayrimi

Station ile location ayni sey olmamali.

Station:

- Operator ekranina, sensor kaynagina, PLC/konveyor noktasina ve is merkezi yetkinligine karsilik gelir.
- Ornek: `ASSEMBLY_01`, `PACKAGING_01`.

Location:

- Stokun nerede oldugunu gosterir.
- Ornek: `ASSEMBLY_01_INPUT`, `ASSEMBLY_01_WIP`, `ASSEMBLY_01_OUTPUT`, `PACKAGING_BUFFER`, `PACKAGING_01_INPUT`, `FINISHED_GOODS`.

Buffer:

- Ara stok icin kullanilan location alt tipidir.
- Paketleme buffer'i bugunku `packagingBuffer` davranisinin genellestirilmis halidir.

Station tanimi default input/output location'lari referanslamali; operation ise gerekiyorsa bu defaultlari override edebilmelidir.

## Manuel Istasyon Akisi

Manuel istasyonda operator/kiosk butonlari net stok hareketleri uretmeli:

1. Queue satiri `operation_id`, `station_code`, `input_location_id`, `output_location_id` ile gorunur.
2. Operator start der.
3. Sistem input location'dan gerekli miktari reserve veya consume eder.
4. Operation `active`, queue satiri `active`, item/lot `station WIP` durumuna gecer.
5. Operator complete der.
6. Sistem station WIP'ten output location'a produce/transfer hareketi yazar.
7. Operation `completed`, queue satiri `completed` olur.
8. Successor operation varsa hedef station queue'ya queued/ready olarak publish edilir.

Bu akis paketleme gibi el isi istasyonlar icin de gecerli olmalidir. Paket session sadece complete icindeki alt sureci, sureyi ve komponent secimini izlemelidir.

## Sensorlu Otomatik Istasyon Akisi

Sensorlu istasyonda fiziksel algilama olayi stok hareketine baglanmalidir:

1. Sensor event gelir: item id, renk/olcum, event time, device id, station code.
2. Sistem ilgili station ve sensor mapping'inden input/output/WIP location'i cozer.
3. Implicit consume veya backflush hareketi uretilir:
   - Giris malzemesi takip ediliyorsa input location'dan consume.
   - Tekil hammadde izlenmiyorsa backflush kaydi ile planli miktar dusulur.
4. Item station WIP'e alinir.
5. Tamamlama/final karar geldiginde output veya buffer location'a produce/transfer edilir.
6. `item_station_events` olayi kaydetmeye devam eder, fakat stok etkisi `inventory_movements` gibi ayri bir defterde tutulur.

Mevcut `apply_mega_log` ve `_complete_runtime_item` akisi bu hedefe yakin bir event kaynagi sagliyor, ancak stok hareketi semantigini genel ledger olarak yazmiyor.

## Ara Stok Takibi

Ara stok bugun paketleme icin ozel olarak var:

- Runtime: `workOrders.packagingBuffer.itemsById`, `availableItemIds`.
- DB: `mes.package_component_wip`.
- Event: `BUFFER_IN`, `BUFFER_OUT` yerine bugun daha cok `BUFFER_IN`, package start/finish eventleri var.

Hedefte ara stok genel location modeliyle izlenmeli:

- Assembly cikisi `ASSEMBLY_01_OUTPUT` veya `PACKAGING_BUFFER` location'ina girer.
- Paketleme input'u `PACKAGING_01_INPUT` veya ayni buffer location'dan consume eder.
- Quality lock, reserve ve consume hareketleri item/lot bazinda takip edilir.

Bu sayede paketleme disinda da yeni istasyon/buffer eklemek icin runtime state'e ozel yeni alan acmak gerekmez.

## Station Queue Davranisi

Mevcut `station_queue`:

- `station_code` zorunlu.
- `order_id` zorunlu.
- `queue_rank` zorunlu.
- `status` queued/active/pending_approval/completed gibi kullaniliyor.
- V2 ile `work_order_operation_id` eklenmis.
- Unique constraint aktif queue icin station/rank ve station/order uzerinden.

Hedef davranis:

- Queue satiri operasyon temelli olmali: `work_order_operation_id` zorunlu hale getirilmeye hazirlanmali.
- Queue satiri station ile beraber input/output location baglamini da gostermeli.
- `order_id` denormalize okunabilir alan olarak kalabilir, ama execution identity operation olmalidir.
- Successor activation local cekirdekte idempotent olmali:
  - tamamlanan operasyonun ayni `order_id` altindaki siradaki `sequence_no` operasyonu bulunur;
  - status `queued` veya `ready` yapilir;
  - station_queue satiri yoksa olusturulur;
  - varsa duplicate uretilmez;
  - son operasyon tamamlandiysa work order completed/pending approval durumuna gecirilir.

## Inventory Movement Defteri

Mevcut tablolar hareket defteri yerine parcali projeksiyonlar sagliyor:

- `production_completions`: tamamlanan urun kaydi.
- `item_station_events`: station-level olay gecmisi.
- `package_component_wip`: paketleme komponent WIP current-state.
- `package_traceability`: paketleme komponent izlenebilirligi.
- `inventoryByProduct`: runtime stok miktari/projeksiyonu.

Hedefte append-only bir movement defteri gerekli:

- Her hareket tek kayit olmali.
- Hareket tipi acik olmali: `RECEIVE`, `CONSUME`, `PRODUCE`, `TRANSFER`, `RESERVE`, `RELEASE`, `SCRAP`, `BACKFLUSH`, `ADJUST`.
- Source ve target location ayrilmali.
- Work order, operation, station, item/lot/package session baglari opsiyonel ama destekli olmali.
- Idempotency icin `external_ref` veya `dedupe_key` olmali.

`item_station_events` olay tarihcesi olarak kalabilir; stok miktari ve lokasyon etkisi movement defterinden okunmalidir.

## Minimum Gerekli Tablo Onerisi

Bu bolum migration degildir; hedef schema tasarimi icin minimum tablo listesidir.

| Tablo | Amac | Not |
| --- | --- | --- |
| `mes.locations` | Fiziksel/mantiksal stok lokasyonlari | `location_code`, `location_type`, `station_code`, `active` |
| `mes.station_location_bindings` | Station default input/output/WIP lokasyonlari | Station esnekligi icin |
| `mes.operation_execution_rules` | Operation input/output policy | Manuel, sensor, backflush, package gibi policy |
| `mes.inventory_items` | Item/lot current-state | Tekil kutu, paket, komponent |
| `mes.inventory_balances` | Location/stock current quantity projeksiyonu | Movement defterinden turetilebilir |
| `mes.inventory_movements` | Append-only stok hareket defteri | Ana hedef tablo |
| `mes.operation_successor_rules` | Siradaki operasyon aktivasyon kurali | Basit rota icin `sequence_no` yeterliyse opsiyonel |
| `mes.station_queue` | Operation execution queue | Mevcut tablo evrilerek kullanilabilir |
| `mes.package_sessions` | Paketleme alt sureci | Work order/operation yerine gecmemeli |
| `mes.package_session_components` | Session icinde reserve/consume edilen komponentler | Mevcut `package_traceability` ile yan yana tasarlanabilir |

Mevcut `mes.package_component_wip` paketleme icin gecis current-state tablosu olarak korunabilir; genel buffer modeli geldiginde `inventory_items`/`inventory_balances` uzerine tasinabilir.

## Migration Stratejisi: Mevcut Semayi Yikmadan Side-by-Side

1. Mevcut runtime ve DB tablolarini bozmadan yeni local execution cekirdegi side-by-side kurulur.
2. Once read-only/projection modunda calisir:
   - existing runtime state ve mevcut DB tablolari okunur;
   - station/location/queue/inventory snapshot'i hesaplanir;
   - UI davranisi degistirilmez.
3. Sonra shadow-write eklenir:
   - operation start/complete;
   - sensor completion;
   - package start/finish;
   - inventory consume/produce hareketleri yeni ledger'a idempotent yazilir.
4. Daha sonra read switch yapilir:
   - station queue ekranlari yeni operation queue projection'ini okumaya baslar;
   - fallback eski runtime queue olur.
5. En son eski `inventoryByProduct` ve `packagingBuffer` sadece uyumluluk projeksiyonu haline gelir.

Bu strateji mevcut `safe_write`, dry-run, fail-open ve additive migration prensipleriyle uyumludur.

## P0 / P1 / P2 Uygulama Adimlari

P0:

- Mevcut schema ve runtime kaynaklarini dokumante et.
- Station, location, buffer, operation, package session kavram sozlugunu sabitle.
- `station_queue` icin hedef identity kararini ver: operation-first.
- Local successor activation kuralini tasarla ve test senaryolarini yaz: operation 10 complete -> operation 20 queued + station_queue row.
- Inventory movement defteri icin event tipi ve idempotency anahtarlarini netlestir.

P1:

- `locations` ve station-location binding modelini side-by-side ekle.
- Operation start/complete icin shadow movement yazimini ekle.
- Sensor completion icin implicit consume/backflush + produce/buffer-in movement yazimini ekle.
- Package start/finish icin reserve/consume/produce hareketlerini yaz.
- Queue read modelinde operation/location baglamini gorunur yap.

P2:

- Runtime `inventoryByProduct` ve `packagingBuffer` alanlarini yeni ledger/current-state'den turetilen projeksiyon haline getir.
- Paketleme icin tek item reserve modelinden coklu component/BOM reserve modeline gec.
- Station UI'lari location ve buffer doluluk durumunu gosterecek sekilde genislet.
- Physical line mapping: sensor/device/station/location eslestirmesini master data haline getir.

## Riskler

- Source-of-truth belirsizligi: Runtime JSON ve DB ayni kavramlari farkli sekilde tasirsa drift olusur.
- Queue kimligi belirsizligi: `station_code + order_id` yaklasimi multi-operation work order icin yetersiz kalir.
- Paketleme kavram karisikligi: `WO-PKT-*`, `package_session`, `package_component_wip` ve `packagingBuffer` ayni isi farkli seviyelerde temsil edebilir.
- Sensor event tekrar edilirse duplicate movement riski vardir; idempotency anahtari zorunlu olmalidir.
- Backflush gercek stoktan dusus demektir; hammadde/yarimamul lokasyonlari net degilse stok hatasi uretir.
- Current-state tablolar append-only ledger yerine kullanilirsa geriye donuk audit zayif kalir.

## Acik Kararlar

1. Station master data local MES tarafinda mi, yoksa MESQL'den gelen referans veri olarak mi beslenecek?
2. Location kodlari kim tarafindan yonetilecek: local config, DB seed, yoksa UI?
3. Operation complete sonrasi successor activation localde kesin source-of-truth mu olacak, yoksa MESQL dondugunde merkezi otoriteyle reconcile mi edilecek?
4. Sensorlu istasyonlarda input consume gercek item/lot bazinda mi, yoksa backflush miktar bazinda mi yapilacak?
5. Paketleme input'u tek item mi, coklu BOM component reserve modeli mi olacak?
6. `inventoryByProduct` ne zaman salt projection'a indirilecek?
7. `item_station_events` ile `inventory_movements` arasindaki birebir bag hangi anahtarla kurulacak?
8. Queue status sozlugu ne olacak: `queued`, `ready`, `active`, `blocked`, `completed`, `cancelled` gibi sabit bir liste gerekli mi?
9. Kiosk ekranlari once runtime state mi, DB projection mi okuyacak?

