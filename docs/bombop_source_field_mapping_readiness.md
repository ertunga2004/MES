# BOM/BOP Source Field Mapping Readiness

Bu dokuman 3D mapping contract'indaki canonical alanlar icin source field readiness durumunu listeler.

Readiness status:

| Status | Anlam |
|---|---|
| `CONFIRMED` | Gercek BOM/BOP source payload icinde dogrulandi |
| `CANDIDATE` | Kavramsal workbook/runtime tasarimindan aday var, gercek source degil |
| `TBD` | Source field henuz belirlenmedi |
| `BLOCKED` | Production importer icin source payload veya karar gerekli |

## Readiness Tablosu

| canonical_field | current_source_field | readiness_status | evidence | blocker | required_next_action |
|---|---|---|---|---|---|
| `release_id` | `TBD` | BLOCKED | Mevcut kaynaklarda real release id yok | Gercek BOM/BOP export ornegi yok | Source payload iste |
| `source_system` | `TBD` | TBD | Canonical default `BOM_BOP` var | Kaynak sistem adi standardi yok | Source owner ile isim standardi belirle |
| `released_at` | `TBD` | BLOCKED | Real release timestamp yok | Release lifecycle kaynagi yok | Source payload ve release log iste |
| `release_status` | `TBD` | BLOCKED | MESQL status listesi var, source mapping yok | BOM/BOP status degerleri bilinmiyor | Status crosswalk iste |
| `product.product_code` | `TBD` / candidate `item_code` | CANDIDATE | Manufacturing workbook `07_Sample_mfg_items.item_code` | Gercek BOM/BOP field degil | Real product payload ile dogrula |
| `product.product_name` | `TBD` / candidate `item_name` | CANDIDATE | Manufacturing workbook `item_name` | Gercek BOM/BOP field degil | Real product payload ile dogrula |
| `product.product_type` | `TBD` / candidate `item_type` | CANDIDATE | Manufacturing workbook `item_type` | Deger listesi mapping gerekli | Type crosswalk iste |
| `product.unit_code` | `TBD` / candidate `base_uom` | CANDIDATE | Manufacturing workbook `base_uom` | Unit mapping gerekli | Unit crosswalk iste |
| `product.source_system` | `TBD` | TBD | Canonical alan var | Kaynak sistem standardi yok | Source owner karar versin |
| `product_revision.product_ref` | `TBD` / candidate `item_code` | CANDIDATE | Product code candidate ile baglanabilir | Gercek revision yapisi yok | Revision payload iste |
| `product_revision.revision_code` | `TBD` | BLOCKED | Real revision field yok | Unique model icin gerekli | Revision/version field iste |
| `product_revision.release_status` | `TBD` | BLOCKED | MESQL status listesi var | Source status mapping yok | Status crosswalk iste |
| `product_revision.valid_from` | `TBD` | TBD | Valid window canonical | Source effective date yok | Effective date field iste |
| `product_revision.valid_to` | `TBD` | TBD | Valid window canonical | Source close date yok | Valid-to policy iste |
| `components[].component_code` | `TBD` / candidate `item_code`, `component_item_code` | CANDIDATE | Manufacturing workbook and MBOM sample | Gercek BOM/BOP field degil | Component payload ile dogrula |
| `components[].component_name` | `TBD` / candidate `item_name` | CANDIDATE | Manufacturing workbook `item_name` | Gercek BOM/BOP field degil | Component master sample iste |
| `components[].component_type` | `TBD` / candidate `item_type` | CANDIDATE | Manufacturing workbook `item_type` | Type crosswalk gerekli | Type crosswalk iste |
| `components[].unit_code` | `TBD` / candidate `base_uom`, `uom` | CANDIDATE | Manufacturing workbook samples | Unit crosswalk gerekli | Unit crosswalk iste |
| `mbom.product_revision_ref` | `TBD` / candidate `parent_item_code` | CANDIDATE | `10_Sample_MBOM.parent_item_code` | Revision ref yok | Parent+revision mapping iste |
| `mbom.mbom_revision` | `TBD` | BLOCKED | Real MBOM revision field yok | Unique model icin gerekli | MBOM revision field iste |
| `mbom.plant_code` | `TBD` / candidate `plant_code` | CANDIDATE | Work center sample has `plant_code` | MBOM header plant field yok | MBOM header sample iste |
| `mbom.release_status` | `TBD` | BLOCKED | MESQL status listesi var | Source status mapping yok | Status crosswalk iste |
| `mbom.lines[].component_ref` | `TBD` / candidate `component_item_code` | CANDIDATE | `10_Sample_MBOM.component_item_code` | Gercek payload yok | MBOM line sample iste |
| `mbom.lines[].required_quantity` | `TBD` / candidate `quantity` | CANDIDATE | `10_Sample_MBOM.quantity` | Gercek payload yok | MBOM line quantity field dogrula |
| `mbom.lines[].unit_code` | `TBD` / candidate `uom` | CANDIDATE | `10_Sample_MBOM.uom` | Unit crosswalk gerekli | Unit field dogrula |
| `mbom.lines[].line_no` | `TBD` | TBD | Runtime package design has `line_no`, sample MBOM lacks explicit line no | Gercek MBOM line order yok | Line order field iste |
| `bop.product_revision_ref` | `TBD` | BLOCKED | BOP header real source yok | Revision link gerekli | BOP header sample iste |
| `bop.bop_revision` | `TBD` | BLOCKED | Real BOP revision field yok | Unique model icin gerekli | BOP revision field iste |
| `bop.plant_code` | `TBD` / candidate `plant_code` | CANDIDATE | Work center sample has `plant_code` | BOP header plant field yok | BOP header sample iste |
| `bop.release_status` | `TBD` | BLOCKED | MESQL status listesi var | Source status mapping yok | Status crosswalk iste |
| `bop.operations[].operation_sequence` | `TBD` / candidate `operation_no` | CANDIDATE | `09_Sample_operations.operation_no` | Gercek BOP operation source yok | BOP operations sample iste |
| `bop.operations[].operation_code` | `TBD` / candidate `operation_code` | CANDIDATE | `09_Sample_operations.operation_code` | Gercek BOP operation source yok | Operation code field dogrula |
| `bop.operations[].operation_name` | `TBD` / candidate `operation_name` | CANDIDATE | `09_Sample_operations.operation_name` | Gercek BOP operation source yok | Operation name field dogrula |
| `bop.operations[].setup_time_seconds` | `TBD` | BLOCKED | F-ERP label var, source field yok | Standard time source yok | Setup/cycle sample iste |
| `bop.operations[].cycle_time_seconds` | `TBD` | BLOCKED | F-ERP label var, source field yok | Standard time source yok | Setup/cycle sample iste |
| `operation_station_mapping[].operation_ref` | `TBD` / candidate `operation_code` | CANDIDATE | Operation sample has `operation_code` | Gercek mapping payload yok | Mapping sample iste |
| `operation_station_mapping[].station_code` | `TBD` / candidate `station_code` | CANDIDATE | Package design note has `station_code` | Not BOM/BOP source | Mapping source dogrula |
| `operation_station_mapping[].work_center_code` | `TBD` / candidate `work_center_code` | CANDIDATE | `08_Sample_work_centers`, `09_Sample_operations` | Gercek mapping payload yok | Work center mapping sample iste |
| `operation_station_mapping[].mapping_status` | `TBD` | BLOCKED | No source mapping status | Release validation icin gerekli | Mapping lifecycle field iste |
| `operation_station_mapping[].validation_level` | `TBD` | TBD | MESQL computed olabilir | Source mu computed mi karari yok | Computed/source kararini kapat |
| `package_bom.package_product_revision_ref` | `TBD` / candidate `package_stock_code` | CANDIDATE | Runtime `mes.package_bom_lines.package_stock_code` | Runtime field, source degil | Package BOM source sample iste |
| `package_bom.package_bom_revision` | `TBD` | BLOCKED | Real package BOM revision yok | Unique model icin gerekli | Package BOM revision field iste |
| `package_bom.plant_code` | `TBD` | BLOCKED | Package BOM plant source yok | Plant scope gerekli | Package BOM header sample iste |
| `package_bom.release_status` | `TBD` | BLOCKED | Source status mapping yok | Release lifecycle gerekli | Status crosswalk iste |
| `package_bom.lines[].component_ref` | `TBD` / candidate `component_stock_code`, `component_item_code` | CANDIDATE | Runtime migration and package design note | Runtime/design source, not real BOM/BOP | Package BOM line sample iste |
| `package_bom.lines[].required_quantity` | `TBD` / candidate `required_qty`, `component_qty` | CANDIDATE | Runtime migration and package design note | Runtime/design source, not real BOM/BOP | Quantity field dogrula |
| `package_bom.lines[].unit_code` | `TBD` / candidate `uom` | CANDIDATE | Package design note `uom` | Gercek source yok | Unit field dogrula |
| `package_bom.lines[].line_no` | `TBD` / candidate `line_no` | CANDIDATE | Package design note has `line_no` | Gercek source yok | Line field dogrula |

## Ozet

| Status | Sayisal yorum |
|---|---|
| CONFIRMED | 0 |
| CANDIDATE | Kavramsal workbook/runtime tasarimindan cok sayida aday var |
| TBD | Source/computed karari bekleyen alanlar var |
| BLOCKED | Release/revision/status ve gercek payload gerektiren alanlar bloklu |
