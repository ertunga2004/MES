# BOM/BOP Field Mapping Contract

Bu dokuman BOM/BOP release paketindeki is nesnelerinin MESQL canonical alanlarina nasil eslenecegini tarif eder.

Onemli: Gercek BOM/BOP uygulamasina ait field adlari henuz bilinmiyor. Bu nedenle `source_field` degerleri `TBD` olarak tutulur. Bu dokuman canonical hedef alanlari ve validation beklentisini netlestirir; kaynak field adlarini kesinlestirmez.

## Amac

BOM/BOP kaynak paketinden gelen product, revision, component, MBOM, BOP, operation/station mapping ve package BOM nesnelerini MESQL shared schema taslagindaki canonical alanlara eslemek.

## Kapsam Disi

| Kapsam disi | Not |
|---|---|
| Production importer kodu | Kod yazilmaz |
| Runtime / Docker degisikligi | MES Web davranisi degismez |
| DB migration | Draft SQL DB'ye uygulanmaz |
| Gercek BOM/BOP source field adlari | Bilinmedigi icin uydurulmaz |
| MESQL API endpointleri | Endpoint adi uydurulmaz |

## Mapping Yaklasimi

| Kolon | Anlam |
|---|---|
| `source_field` | Gercek BOM/BOP field adi. Bilinmiyorsa `TBD`. |
| `canonical_field` | MESQL canonical payload alani. |
| `required` | Import/validation icin zorunluluk. |
| `validation` | Minimum validation kural veya hata kodu. |
| `target_table` | Draft shared schema hedef tablosu. |
| `note` | F-ERP label baglami veya aciklama. |

## Product Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `product.product_code` | Yes | `MESQL-VAL-0001 PRODUCT_CODE_MISSING` | `mesql_master.products.product_code` | F-ERP label: `lblMTM00_CODE` |
| `TBD` | `product.product_name` | Recommended | WARN if empty | `mesql_master.products.product_name` | F-ERP label: `lblMTM00_NAME` |
| `TBD` | `product.product_type` | Recommended | Conflict review if ERP mismatch | `mesql_master.products.product_type` | F-ERP label: `lblMTMT0_CODE` |
| `TBD` | `product.unit_code` | Recommended | `MESQL-VAL-0009 UNIT_CODE_CONFLICT` if mismatch | `mesql_master.products.unit_code` | F-ERP label: `lblMUNT0_CODE` |
| `TBD` | `product.source_system` | Recommended | Default from package if missing | `mesql_master.products.source_system` | No F-ERP label |

## Product Revision Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `product_revision.product_ref` | Yes | Must resolve to product | `mesql_master.product_revisions.product_id` | References product canonical code |
| `TBD` | `product_revision.revision_code` | Yes | `MESQL-VAL-0007 PRODUCT_REVISION_CONFLICT` if conflicting | `mesql_master.product_revisions.revision_code` | Unique with product |
| `TBD` | `product_revision.release_status` | Yes | `MESQL-VAL-0010 UNKNOWN_RELEASE_STATUS` | `mesql_master.product_revisions.release_status` | Only `RELEASED` can flow to ERP/MES |
| `TBD` | `product_revision.valid_from` | Optional | Valid window check | `mesql_master.product_revisions.valid_from` | Draft lifecycle |
| `TBD` | `product_revision.valid_to` | Optional | Must be after `valid_from` if present | `mesql_master.product_revisions.valid_to` | Used to close old release |

## Component Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `components[].component_code` | Yes | `MESQL-VAL-0002 COMPONENT_CODE_MISSING` | `mesql_master.components.component_code` | F-ERP label: `lblMTM00_CODE` |
| `TBD` | `components[].component_name` | Recommended | WARN if empty | `mesql_master.components.component_name` | F-ERP label: `lblMTM00_NAME` |
| `TBD` | `components[].component_type` | Recommended | Conflict review if ERP mismatch | `mesql_master.components.component_type` | F-ERP label: `lblMTMT0_CODE` |
| `TBD` | `components[].unit_code` | Recommended | `MESQL-VAL-0009 UNIT_CODE_CONFLICT` if mismatch | `mesql_master.components.unit_code` | F-ERP label: `lblMUNT0_CODE` |
| `TBD` | `components[].source_system` | Recommended | Default from package if missing | `mesql_master.components.source_system` | No F-ERP label |

## MBOM Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `mbom.product_revision_ref` | Yes | Must resolve to product revision | `mesql_manufacturing.mbom_headers.product_revision_id` | Header link |
| `TBD` | `mbom.mbom_revision` | Yes | Unique with product revision + plant | `mesql_manufacturing.mbom_headers.mbom_revision` | Revision model |
| `TBD` | `mbom.plant_code` | Yes | Not blank | `mesql_manufacturing.mbom_headers.plant_code` | Plant scope |
| `TBD` | `mbom.release_status` | Yes | `MESQL-VAL-0010 UNKNOWN_RELEASE_STATUS` | `mesql_manufacturing.mbom_headers.release_status` | Only `RELEASED` flows |
| `TBD` | `mbom.lines[].component_ref` | Yes | Must resolve to component | `mesql_manufacturing.mbom_lines.component_id` | Component link |
| `TBD` | `mbom.lines[].required_quantity` | Yes | `MESQL-VAL-0003 QUANTITY_NOT_POSITIVE` | `mesql_manufacturing.mbom_lines.required_quantity` | Positive quantity |
| `TBD` | `mbom.lines[].unit_code` | Recommended | Unit conflict review | `mesql_manufacturing.mbom_lines.unit_code` | F-ERP label context: `lblMUNT0_CODE` |
| `TBD` | `mbom.lines[].line_no` | Recommended | Positive if present | `mesql_manufacturing.mbom_lines.line_no` | Line order |

## BOP Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `bop.product_revision_ref` | Yes | Must resolve to product revision | `mesql_manufacturing.bop_headers.product_revision_id` | Header link |
| `TBD` | `bop.bop_revision` | Yes | Unique with product revision + plant | `mesql_manufacturing.bop_headers.bop_revision` | Revision model |
| `TBD` | `bop.plant_code` | Yes | Not blank | `mesql_manufacturing.bop_headers.plant_code` | Plant scope |
| `TBD` | `bop.release_status` | Yes | `MESQL-VAL-0010 UNKNOWN_RELEASE_STATUS` | `mesql_manufacturing.bop_headers.release_status` | Only `RELEASED` flows |
| `TBD` | `bop.operations[].operation_sequence` | Yes | `MESQL-VAL-0004 DUPLICATE_OPERATION_SEQUENCE` | `mesql_manufacturing.bop_operations.operation_sequence` | Unique inside BOP |
| `TBD` | `bop.operations[].operation_code` | Yes | Not blank for ERP mapping | `mesql_manufacturing.bop_operations.operation_code` | F-ERP label: `lblMFWO0_CODE` |
| `TBD` | `bop.operations[].operation_name` | Recommended | WARN if empty | `mesql_manufacturing.bop_operations.operation_name` | No known F-ERP label |
| `TBD` | `bop.operations[].setup_time_seconds` | Optional | Non-negative if present | `mesql_manufacturing.bop_operations.setup_time_seconds` | F-ERP label: `lblMMFB4_SETUP_TIME` |
| `TBD` | `bop.operations[].cycle_time_seconds` | Optional | Positive if present | `mesql_manufacturing.bop_operations.cycle_time_seconds` | F-ERP label: `lblMMFB4_TIME` |

## Operation/Station Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `operation_station_mapping[].operation_ref` | Yes | Must resolve to BOP operation | `mesql_manufacturing.operation_station_mapping.bop_operation_id` | Operation link |
| `TBD` | `operation_station_mapping[].station_code` | Required for MES release | `MESQL-VAL-0005` if missing on `RELEASED` | `mesql_manufacturing.operation_station_mapping.station_code` | MES station, not ERP label |
| `TBD` | `operation_station_mapping[].work_center_code` | Recommended | Required if ERP route export needs work center | `mesql_manufacturing.operation_station_mapping.work_center_code` | F-ERP label: `lblMFW00_CODE` |
| `TBD` | `operation_station_mapping[].mapping_status` | Yes | Known release status list | `mesql_manufacturing.operation_station_mapping.mapping_status` | Mapping lifecycle |
| `TBD` | `operation_station_mapping[].validation_level` | Yes | `PASS`, `WARN`, `HOLD`, `FAIL` | `mesql_manufacturing.operation_station_mapping.validation_level` | Default depends on status |

Mapping missing defaults: `DRAFT` / `IN_REVIEW` -> WARN, `APPROVED` -> HOLD, `RELEASED` -> FAIL. MES'e dagitilacak operation mapping'siz olamaz.

## Package BOM Mapping

| source_field | canonical_field | required | validation | target_table | note |
|---|---|---|---|---|---|
| `TBD` | `package_bom.package_product_revision_ref` | Yes | Must resolve to product revision | `mesql_manufacturing.package_bom_headers.package_product_revision_id` | Package product link |
| `TBD` | `package_bom.package_bom_revision` | Yes | Unique with package product revision + plant | `mesql_manufacturing.package_bom_headers.package_bom_revision` | Revision model |
| `TBD` | `package_bom.plant_code` | Yes | Not blank | `mesql_manufacturing.package_bom_headers.plant_code` | Plant scope |
| `TBD` | `package_bom.release_status` | Yes | Known release status list | `mesql_manufacturing.package_bom_headers.release_status` | Only `RELEASED` flows |
| `TBD` | `package_bom.lines[].component_ref` | Yes | `MESQL-VAL-0013 PACKAGE_BOM_COMPONENT_MISSING` | `mesql_manufacturing.package_bom_lines.component_id` | Component link |
| `TBD` | `package_bom.lines[].required_quantity` | Yes | `MESQL-VAL-0003 QUANTITY_NOT_POSITIVE` | `mesql_manufacturing.package_bom_lines.required_quantity` | Positive quantity |
| `TBD` | `package_bom.lines[].unit_code` | Recommended | Unit conflict review | `mesql_manufacturing.package_bom_lines.unit_code` | F-ERP label context: `lblMUNT0_CODE` |
| `TBD` | `package_bom.lines[].line_no` | Recommended | Positive if present | `mesql_manufacturing.package_bom_lines.line_no` | Line order |

## F-ERP Label Baglantilari

| Canonical alan | Bilinen F-ERP label |
|---|---|
| `product_code` / `component_code` | `lblMTM00_CODE` |
| `product_name` / `component_name` | `lblMTM00_NAME` |
| `product_type` / `component_type` | `lblMTMT0_CODE` |
| `unit_code` | `lblMUNT0_CODE` |
| `work_center_code` | `lblMFW00_CODE` |
| `operation_code` | `lblMFWO0_CODE` |
| `setup_time_seconds` | `lblMMFB4_SETUP_TIME` |
| `cycle_time_seconds` | `lblMMFB4_TIME` |

Unknown F-ERP labels are not invented. Unknown BOM/BOP source fields remain `TBD` until the real source payload is provided.
