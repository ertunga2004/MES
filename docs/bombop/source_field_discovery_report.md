# BOM/BOP Source Field Discovery Report

Bu rapor 3E - BOM/BOP Source Field Discovery & v1 Readiness sprinti icin repo ve mevcut dokumanlarda gercek BOM/BOP source field adlarinin bulunup bulunamadigini ozetler.

## Incelenen Dosyalar

| Kaynak | Sonuc |
|---|---|
| `docs/bombop/field_mapping_contract.md` | Canonical alanlar var; tum `source_field` degerleri bilincli olarak `TBD`. |
| `docs/bombop/release_importer_contract.md` | Canonical importer nesneleri var; gercek BOM/BOP JSON field adlari bilinmiyor. |
| `docs/mesql/payload_versioning_policy.md` | `v0` draft/staging, `v1` contract-stable kurali var. |
| `docs/examples/bombop_release_payload.canonical.example.json` | Canonical ornek; gercek BOM/BOP source payload degil. |
| `docs/examples/bombop_validation_response.example.json` | Validation response ornegi; source field kaniti degil. |
| `docs/examples/erp_preparation_staging_export.example.json` | ERP staging ornegi; source field kaniti degil. |
| `docs/mesql/shared_schema_draft.md` | Shared schema canonical hedefleri var. |
| `docs/mesql/shared_schema_open_questions.md` | Gercek BOM/BOP release JSON alan adlari acik olarak listelenmis. |
| `db/drafts/mesql_shared_schema_draft.sql` | Draft SQL hedef kolonlari var; source field kaniti degil. |
| `docs/erp/FERP_INTEGRATION.md` | F-ERP label ve is emri/stok hareket sinirlari var. |
| `docs/erp/FERP_JSON_CONTRACT.md` | F-ERP label-first import/export sinirlari var. |
| `docs/agent_memory/10_db_pre_plan_summary.md` | Manufacturing master data on plan ozeti var. |
| `docs/db_pre_plan/Manufacturing_Master_Data_Database_Detayli_Tasarim.xlsx` | Kavramsal manufacturing master data workbook'u; aday alanlar var, gercek BOM/BOP app field'i degil. |
| `db/migrations/005_package_bom_wip.sql` | Mevcut MES runtime package BOM/WIP alanlari var; BOM/BOP source field kaniti degil. |
| `docs/agent_memory/39_station_kiosk_package_bom_design.md` | Station/package runtime tasarim adaylari var; BOM/BOP source field kaniti degil. |
| `mes_web/masterdata.py` | Kiosk masterdata Excel parser alanlari var; BOM/BOP source field kaniti degil. |

## Aranan Kavramlar

| Kavram grubu | Aranan terimler |
|---|---|
| BOM/BOP | `BOM/BOP`, `MBOM`, `BOP`, `bom`, `bop`, `route`, `package_bom` |
| Release | `release`, `release_status`, `released_at`, `valid_from`, `valid_to` |
| Product/revision | `product_revision`, `revision_code`, `item_code`, `item_revision` |
| Operation/station | `operation`, `operation_no`, `operation_code`, `station_code`, `work_center_code` |
| Package | `package_stock_code`, `component_stock_code`, `component_qty`, `required_qty` |

## Bulunan Net Field Adlari

Gercek BOM/BOP uygulamasina ait confirmed source field adi bulunamadi.

| Field | Durum | Gerekce |
|---|---|---|
| Gercek BOM/BOP source field seti | Bulunamadi | Repo icinde BOM/BOP uygulamasina ait kaynak JSON/CSV/XLSX payload yok. |
| Gercek release package nested structure | Bulunamadi | Mevcut ornekler canonical MESQL ornekleridir. |
| Gercek importer endpoint veya API payload | Bulunamadi | Endpoint uydurulmayacak; kaynak yok. |

## Bulunan Ama Kesin Olmayan Aday Alanlar

Bu alanlar kavramsal veya runtime kaynaklardan geldi. Production importer icin confirmed sayilmaz.

| Aday field | Kaynak | Iliskili canonical alan | Durum |
|---|---|---|---|
| `item_code` | `Manufacturing_Master_Data_Database_Detayli_Tasarim.xlsx`, `07_Sample_mfg_items` | `product.product_code`, `components[].component_code` | CANDIDATE |
| `item_name` | `07_Sample_mfg_items` | `product.product_name`, `components[].component_name` | CANDIDATE |
| `item_type` | `07_Sample_mfg_items` | `product.product_type`, `components[].component_type` | CANDIDATE |
| `base_uom` | `07_Sample_mfg_items` | `unit_code` | CANDIDATE |
| `parent_item_code` | `10_Sample_MBOM` | `mbom.product_revision_ref` / parent product | CANDIDATE |
| `component_item_code` | `10_Sample_MBOM`, package design note | `mbom.lines[].component_ref`, `package_bom.lines[].component_ref` | CANDIDATE |
| `quantity` | `10_Sample_MBOM` | `required_quantity` | CANDIDATE |
| `uom` | `10_Sample_MBOM` | `unit_code` | CANDIDATE |
| `operation_no` | `09_Sample_operations`, `10_Sample_MBOM` | `operation_sequence` | CANDIDATE |
| `operation_code` | `09_Sample_operations` | `operation_code` | CANDIDATE |
| `operation_name` | `09_Sample_operations` | `operation_name` | CANDIDATE |
| `work_center_code` | `08_Sample_work_centers`, `09_Sample_operations` | `work_center_code` | CANDIDATE |
| `plant_code` | `08_Sample_work_centers` | `plant_code` | CANDIDATE |
| `package_stock_code` | `db/migrations/005_package_bom_wip.sql` | package product code | Runtime candidate only |
| `component_stock_code` | `005_package_bom_wip.sql` | package component code | Runtime candidate only |
| `required_qty` | `005_package_bom_wip.sql` | `package_bom.lines[].required_quantity` | Runtime candidate only |

## Bulunamayan Alanlar

| Canonical konu | Bulunamayan source field |
|---|---|
| Release identity | `release_id` |
| Source system identity | `source_system` |
| Release timestamp | `released_at` |
| Product revision code | `product_revision.revision_code` icin gercek source |
| MBOM revision code | `mbom.mbom_revision` icin gercek source |
| BOP revision code | `bop.bop_revision` icin gercek source |
| Package BOM revision code | `package_bom.package_bom_revision` icin gercek source |
| Release status | `release_status` icin gercek source |
| Operation/station mapping status | `mapping_status` icin gercek source |
| Validation response fields | Kaynak BOM/BOP warning/error formati |

## `source_field=TBD` Kalmasi Gereken Alanlar

Gercek BOM/BOP source payload gelene kadar 3D mapping contract'indaki tum `source_field` degerleri `TBD` kalmalidir.

Kavramsal workbook adaylari production importer icin yeterli degildir; sadece mapping gorusmesi icin aday sozluk olarak kullanilabilir.

## Production Importer Icin Gerekli Eksik Kaynaklar

| Eksik kaynak | Neden gerekli |
|---|---|
| Gercek BOM/BOP export JSON/CSV/XLSX ornegi | Source field mapping kapatmak icin |
| BOM/BOP release status deger listesi | MESQL status mapping icin |
| BOM/BOP revision/version alanlari | Unique model ve release lifecycle icin |
| BOM/BOP operation/station mapping ornegi | MES dagitim validation icin |
| BOM/BOP package BOM ornegi | Package BOM line mapping icin |
| Kaynak validation/error formatlari | Validation response mapping icin |

## Sonuc

| Soru | Cevap |
|---|---|
| Gercek BOM/BOP source field bulundu mu? | Hayir. |
| v1 contract'a gecilebilir mi? | Hayir. |
| Neden? | Gercek source payload ve field adlari yok; sadece canonical contract ve kavramsal aday alanlar var. |
| Ne yapilmali? | BOM/BOP uygulamasindan minimum source payload ornegi istenmeli ve mapping workshop yapilmali. |
