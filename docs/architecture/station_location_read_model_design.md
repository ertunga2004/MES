# Station/Location Read Model Design

## 1. Amaç

Bu doküman, `mes.locations` ve `mes.station_location_bindings` tabloları için read-only DB access/query/helper tasarımını tanımlar.

Amaç, runtime'ın station/location/buffer bilgisini lokal PostgreSQL'den okuyabilmesi, fakat bu fazda hiçbir write path açılmamasıdır. Bu tasarım yalnızca bir sonraki kodlama turuna hazırlık dokümanıdır; DDL, migration veya implementation değildir.

Bu tasarım inventory movement, inventory balance, sensor linkage veya MESQL sync değildir.

## 2. Mevcut Doğrulanmış Baseline

Mevcut baseline, `docs/architecture/CURRENT_STATE.md` ve evidence dokümanlarına göre şöyledir:

- Local MES DB operation lifecycle local execution source-of-truth olarak çalışıyor.
- Local successor activation smoke verified:
  - `ASSEMBLY_01` operation 10 complete edildiğinde `PACKAGING_01` operation 20 queue oluyor.
  - Repeated complete duplicate `PACKAGING_01` queue row üretmiyor.
  - Final `PACKAGING_01` operation complete sonrasında work order completed oluyor.
- Paket A migration `db/migrations/003_add_station_locations.sql` manuel uygulanmış durumda.
- `mes.locations` ve `mes.station_location_bindings` tabloları oluşturuldu.
- 8 location ve 8 active station-location binding doğrulandı.
- `PACKAGING_01.station_name` encoding cleanup tamamlandı; hedef değer `İstasyon 2 - Paketleme`.
- MESQL push/pull çalıştırılmadı.
- Runtime/API code henüz `mes.locations` veya `mes.station_location_bindings` tablolarını kullanacak şekilde değişmedi.

Bu dokümanda gerçek uygulanmış DB yapısı için source-of-truth `db/migrations/003_add_station_locations.sql` dosyasıdır. Migration planındaki önceki aday alanlar uygulanmış şema gibi ele alınmaz.

## 3. Kapsam

Bu tasarımın kapsamı:

- `mes.locations` read-only query.
- `mes.station_location_bindings` read-only query.
- Station bazlı location context üretimi.
- Role bazlı binding çözümleme.
- İleride API/UI/Kiosk tarafından okunabilir veri modeli.
- Existing operation lifecycle davranışını değiştirmeden bilgi okuma.
- Future movement ledger için location resolution hazırlığı.

Runtime davranışı bu fazda yalnızca okuma ile sınırlıdır. Operation start/complete akışına stok etkisi, movement kaydı veya queue davranışı eklenmez.

## 4. Kapsam Dışı

Bu tasarımın dışında kalanlar:

- `INSERT`, `UPDATE`, `DELETE` yok.
- Yeni SQL migration yok.
- Inventory movement yok.
- Inventory balance yok.
- Sensor event link yok.
- Work order lifecycle değişikliği yok.
- Station queue değişikliği yok.
- MESQL push/pull yok.
- Docker/compose değişikliği yok.
- F-ERP entegrasyonu yok.
- API endpoint implementasyonu yok.
- UI/dashboard implementasyonu yok.
- Full WMS yok.

## 5. Gerçek Tablo Modeli

Bu bölümdeki tablo modeli `db/migrations/003_add_station_locations.sql` içinden doğrulanan actual schema bilgisidir.

Önemli notlar:

- Actual schema binding için `location_code` kullanır.
- Bu fazda `location_id` ile join varsayımı kurulmaz.
- Join key: `station_location_bindings.location_code = locations.location_code`.
- Binding rol kolonu actual schema içinde `role` adındadır; `binding_role` değildir.

### `mes.locations`

| Kolon | Rolü | Nullable / default | Read modelde kullanılacak mı? |
| --- | --- | --- | --- |
| `location_pk` | DB internal surrogate primary key | `BIGSERIAL PRIMARY KEY`, not null | Hayır; external/read identity olarak sunulmamalı. |
| `location_id` | Text identity / import-friendly id alanı | Nullable, default yok | Evet, varsa pass-through; join için kullanılmamalı. |
| `location_code` | Ana business key ve lookup key | `TEXT NOT NULL`; unique index `ux_mes_locations_location_code` | Evet; primary read key. |
| `location_name` | Görünen ad | Nullable, default yok | Evet. |
| `location_type` | Domain type | `TEXT NOT NULL`; check constraint ile sınırlı | Evet; filtreleme ve UI grouping için kullanılmalı. |
| `parent_location_code` | Hiyerarşik parent location referansı | Nullable, default yok | Evet, varsa context içinde gösterilebilir; bu fazda recursive tree zorunlu değil. |
| `station_code` | Location belirli station'a bağlıysa station referansı | Nullable, default yok; station_code index var | Evet; station'a özel WIP gibi alanlar için kullanılabilir. |
| `active` | Aktif/pasif flag | `BOOLEAN NOT NULL DEFAULT true` | Evet; default read path aktif kayıtları tercih etmeli. |
| `source_system` | Kaynak sistem bilgisi | `TEXT NOT NULL DEFAULT 'mes_web'` | Evet, audit/debug output için opsiyonel. |
| `source_file` | Seed/source dosya etiketi | Nullable, default yok | Evet, audit/debug output için opsiyonel. |
| `external_ref` | External/source reference | Nullable, default yok | Evet, audit/debug output için opsiyonel. |
| `payload` | Esnek JSON payload | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Evet, raw metadata ihtiyacı için pass-through; karar mantığı payload'a bağımlı olmamalı. |
| `metadata` | Esnek JSON metadata | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Evet, seed/audit bilgisi için pass-through. |
| `created_at` | Oluşturma zamanı | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Evet, audit output için opsiyonel. |
| `updated_at` | Güncelleme zamanı | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Evet, audit output için opsiyonel. |

### `mes.station_location_bindings`

| Kolon | Rolü | Nullable / default | Read modelde kullanılacak mı? |
| --- | --- | --- | --- |
| `binding_pk` | DB internal surrogate primary key | `BIGSERIAL PRIMARY KEY`, not null | Hayır; external/read identity olarak sunulmamalı. |
| `binding_id` | Text identity / import-friendly id alanı | Nullable, default yok | Evet, varsa pass-through; lookup için zorunlu değil. |
| `station_code` | Station business key | `TEXT NOT NULL` | Evet; ana filtreleme key'i. |
| `role` | Binding rolü | `TEXT NOT NULL`; check constraint ile sınırlı | Evet; `input`, `active_wip`, `output_good`, `output_scrap`, `output_buffer` çözümü için ana alan. |
| `location_code` | Binding'in hedef location business key'i | `TEXT NOT NULL`; index var | Evet; `mes.locations.location_code` ile join key. |
| `item_scope` | Item/product bazlı opsiyonel scope | Nullable, default yok | Evet; future scoped resolution için. |
| `operation_scope` | Operation bazlı opsiyonel scope | Nullable, default yok | Evet; future scoped resolution için. |
| `priority` | Aynı station/role/scope için çözüm önceliği | `INTEGER NOT NULL DEFAULT 100` | Evet; deterministic resolution için kullanılmalı. |
| `active` | Aktif/pasif flag | `BOOLEAN NOT NULL DEFAULT true` | Evet; default read path aktif binding'leri tercih etmeli. |
| `source_system` | Kaynak sistem bilgisi | `TEXT NOT NULL DEFAULT 'mes_web'` | Evet, audit/debug output için opsiyonel. |
| `source_file` | Seed/source dosya etiketi | Nullable, default yok | Evet, audit/debug output için opsiyonel. |
| `external_ref` | External/source reference | Nullable, default yok | Evet, audit/debug output için opsiyonel. |
| `payload` | Esnek JSON payload | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Evet, raw metadata ihtiyacı için pass-through; karar mantığı payload'a bağımlı olmamalı. |
| `metadata` | Esnek JSON metadata | `JSONB NOT NULL DEFAULT '{}'::jsonb` | Evet, seed/audit bilgisi için pass-through. |
| `created_at` | Oluşturma zamanı | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Evet, audit output için opsiyonel. |
| `updated_at` | Güncelleme zamanı | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Evet, audit output için opsiyonel. |

Mevcut active binding uniqueness modeli:

```text
station_code,
role,
location_code,
COALESCE(item_scope, ''),
COALESCE(operation_scope, '')
WHERE active = true
```

Bu uniqueness, aynı station/role/location/scope kombinasyonunun aktif duplicate üretmesini engeller. Ancak aynı station/role için birden fazla location ileride mümkün olabileceği için read helper resolution sırası deterministic olmalıdır.

## 6. Domain Sözlüğü

Location type:

- `raw_material`: Hammadde veya giriş stok alanı.
- `wip`: Work-in-progress / station üzerinde veya station'a bağlı işlem içi alan.
- `buffer`: İki station veya iki proses adımı arasında bekleme alanı.
- `finished_goods`: Tamamlanmış ürün çıkış alanı.
- `scrap`: Fire/hurda alanı.
- `hold`: Bloke, bekletme veya kalite karantinası alanı.
- `rework`: Rework/yeniden işlem alanı.

Binding role:

- `input`: Station için default giriş location'ı.
- `active_wip`: Station üzerinde aktif işlem/WIP location'ı.
- `output_good`: İyi ürün çıkış location'ı.
- `output_scrap`: Scrap/fire çıkış location'ı.
- `output_buffer`: İyi ürünün bir sonraki station'a geçmeden önce beklediği buffer location'ı.

Station:

- Fiziksel veya operasyonel iş merkezi.
- Örnekler: `ASSEMBLY_01`, `PACKAGING_01`.
- Station execution resource'tur; stok lokasyonu değildir.

Location:

- Stok, akış veya alan kavramıdır.
- Buffer bir station değildir; `location_type = 'buffer'` olan bir location subtype'ıdır.
- `location_code` read modelde ana business key olarak kullanılmalıdır.

## 7. Minimum Read Use-Case'leri

| Use-case | Input | Output | Guardrail | Bu fazda write var mı? |
| --- | --- | --- | --- | --- |
| 1. Aktif location listesini oku | `active_only=true`, opsiyonel `location_type` | `LocationRow` listesi | Varsayılan aktif kayıtlar; pasif `HOLD_AREA` / `REWORK_AREA` ancak açık filtreyle gösterilmeli. | Hayır. |
| 2. Tek location'ı `location_code` ile oku | `location_code` | `LocationRow` veya `None` | `location_code` normalize edilip uppercase okunmalı; bulunamazsa create/update denenmemeli. | Hayır. |
| 3. Station'a bağlı aktif binding'leri oku | `station_code`, `active_only=true`, opsiyonel `role` | `StationLocationBindingRow` listesi | Varsayılan aktif binding; station yoksa boş liste döndürmek yeterli olabilir. | Hayır. |
| 4. Station + role için default location çöz | `station_code`, `role`, opsiyonel `item_scope`, `operation_scope` | `LocationRow` veya `None` | Sadece active binding + active location; join `location_code` ile; birden fazla adayda deterministic priority uygulanmalı. | Hayır. |
| 5. Station location context üret | `station_code` | `StationLocationContext` | Context bilgi amaçlıdır; operation lifecycle kararlarını bu fazda değiştirmez. | Hayır. |
| 6. Operation complete sonrası output location bilgisini sadece görüntülemek için oku | `station_code`, completion classification veya role (`output_good` / `output_scrap`) | Display-only output location bilgisi | Movement, production completion veya station queue davranışına bağlanmamalı. | Hayır. |
| 7. Kiosk/dashboard için station'ın input/WIP/output/scrap/buffer noktalarını göster | `station_code` | Role bazlı grouped location context | UI read-only olmalı; missing role durumunda hata yerine eksik context gösterebilir. | Hayır. |
| 8. Future movement ledger için location resolution hazırlığı yap | `station_code`, `role`, future item/operation scope | Resolved candidate veya `None` | Ledger yazılmaz; resolution sonucu yalnızca ilerideki movement tasarımı için kullanılabilir. | Hayır. |

Resolution guardrail'leri:

- `active_only=True` default olmalı.
- Binding ve location tarafında aktiflik ayrı ayrı kontrol edilmeli.
- Join `binding.location_code = location.location_code` ile kurulmalı.
- `location_id` join key olarak kullanılmamalı.
- Query'ler `SELECT` ile sınırlı kalmalı; `FOR UPDATE`, `INSERT`, `UPDATE`, `DELETE` kullanılmamalı.
- Scope desteği eklenirse spesifik scope, generic scope'a göre öncelikli okunmalı; eşitlikte `priority ASC`, sonra `location_code ASC` gibi deterministic sıralama kullanılmalı.

## 8. Önerilen Helper Fonksiyonları

Bu bölüm implementation değildir; yalnızca bir sonraki kodlama turu için helper imzası ve davranış tasarımıdır. İsimler ve return type'lar kodlama sırasında mevcut `mes_web.db.mesql_v2` stiline göre uyarlanabilir.

Önerilen helper adayları:

```text
list_locations(active_only=True, location_type=None) -> list[LocationRow]
get_location_by_code(location_code: str) -> LocationRow | None
list_station_location_bindings(station_code: str, active_only=True, role=None) -> list[StationLocationBindingRow]
resolve_station_location(station_code: str, role: str, item_scope=None, operation_scope=None) -> LocationRow | None
get_station_location_context(station_code: str) -> StationLocationContext
```

### `LocationRow`

Minimum önerilen read payload:

```text
location_code
location_id
location_name
location_type
parent_location_code
station_code
active
source_system
source_file
external_ref
payload
metadata
created_at
updated_at
```

`location_pk` internal DB identity olduğu için public/read payload içinde zorunlu değildir.

### `StationLocationBindingRow`

Minimum önerilen read payload:

```text
binding_id
station_code
role
location_code
item_scope
operation_scope
priority
active
source_system
source_file
external_ref
payload
metadata
created_at
updated_at
```

`binding_pk` internal DB identity olduğu için public/read payload içinde zorunlu değildir.

### `StationLocationContext`

Önerilen context shape:

```text
station_code
bindings
locations_by_role
input_location
active_wip_location
output_good_location
output_scrap_location
output_buffer_location
missing_roles
```

Notlar:

- `bindings`: station için active binding listesi.
- `locations_by_role`: role -> resolved location listesi veya tekil default location map'i olarak tasarlanabilir.
- `missing_roles`: UI/debug için hangi role binding'inin bulunmadığını gösterebilir.
- `output_buffer_location` her station için zorunlu değildir; örneğin `PACKAGING_01` için mevcut seed setinde `output_buffer` yoktur.

### Query / helper davranış prensipleri

- Existing `read_station_queue_v2` pattern'ine benzer şekilde DB bağlantısı read helper içinde açılabilir.
- `database_connection(config)` yoksa mevcut hata modeline uyumlu şekilde `DATABASE_DISABLED` benzeri hata üretilebilir.
- JSONB alanları mevcut `_json_safe` yaklaşımıyla serialize edilebilir.
- `station_code`, `location_code` ve `role` input'ları normalize edilmelidir:
  - `station_code`: uppercase.
  - `location_code`: uppercase.
  - `role`: lowercase.
- Query sabitleri `SELECT_*_SQL` olarak ayrılabilir.
- Read helper'lar transaction veya row lock gerektirmemelidir.
- Helper'lar operation lifecycle helper'larına side-effect üretmemelidir.
- İlk kodlama turunda unit testler fake cursor/connection yaklaşımıyla SQL shape ve output mapping doğrulamalıdır.

### Önerilen çözüm sırası

1. `list_locations` ile active location inventory görünürlüğü.
2. `get_location_by_code` ile tekil location lookup.
3. `list_station_location_bindings` ile station/role binding görünürlüğü.
4. `resolve_station_location` ile active binding + active location join.
5. `get_station_location_context` ile Kiosk/dashboard için role bazlı birleşik context.

Bu sıra, mevcut operation lifecycle'a dokunmadan read-only visibility sağlar. Movement ledger, balance view, sensor link ve MESQL mapping ayrı fazlarda ele alınmalıdır.

## 9. Önerilen Veri Modelleri

Bu bölüm implementation değildir. Amaç, bir sonraki kodlama turunda kullanılacak dataclass/dict shape'lerini önceden netleştirmektir.

Model adları öneridir. Kodlama sırasında mevcut `mes_web.db.mesql_v2` stiline göre `JsonObject` dict çıktısı veya `@dataclass(slots=True)` ara modeli tercih edilebilir.

### `LocationRow`

`LocationRow`, `mes.locations` satırının read model karşılığıdır.

Önerilen alanlar:

```text
location_pk
location_code
location_id
location_name
location_type
parent_location_code
station_code
active
source_system
source_file
external_ref
payload
metadata
created_at
updated_at
```

Alan notları:

| Alan | Tip / shape önerisi | Not |
| --- | --- | --- |
| `location_pk` | integer | DB internal identity. Helper içi debug/audit için taşınabilir; public API output'ta zorunlu değildir. |
| `location_code` | string | Zorunlu business key. Uppercase normalize edilmiş beklenir. |
| `location_id` | string veya null | Migration seed'inde `location_code` ile aynı değer kullanıldı; join key değildir. |
| `location_name` | string veya null | UI/display için. |
| `location_type` | string | `raw_material`, `wip`, `buffer`, `finished_goods`, `scrap`, `hold`, `rework`. |
| `parent_location_code` | string veya null | Bu fazda recursive tree zorunlu değil. |
| `station_code` | string veya null | Station'a özel WIP location'ları için bilgi alanı. |
| `active` | boolean | Varsayılan read path aktif kayıtları döndürmeli. |
| `source_system` | string | Audit/debug için. |
| `source_file` | string veya null | Seed source bilgisi. |
| `external_ref` | string veya null | External/source reference. |
| `payload` | object/dict | JSONB; yoksa `{}` olarak normalize edilmeli. |
| `metadata` | object/dict | JSONB; yoksa `{}` olarak normalize edilmeli. |
| `created_at` | timestamp/string | `_json_safe` ile JSON serializable hale getirilmeli. |
| `updated_at` | timestamp/string | `_json_safe` ile JSON serializable hale getirilmeli. |

Minimum API/UI output için `location_code`, `location_name`, `location_type`, `station_code`, `active`, `metadata` yeterli olabilir. Helper içi full row modeli ise tüm alanları taşımalıdır.

### `StationLocationBindingRow`

`StationLocationBindingRow`, `mes.station_location_bindings` satırının read model karşılığıdır.

Önerilen alanlar:

```text
binding_pk
binding_id
station_code
role
location_code
item_scope
operation_scope
priority
active
source_system
source_file
external_ref
payload
metadata
created_at
updated_at
```

Alan notları:

| Alan | Tip / shape önerisi | Not |
| --- | --- | --- |
| `binding_pk` | integer | DB internal identity. Helper içi debug/audit için taşınabilir; public API output'ta zorunlu değildir. |
| `binding_id` | string veya null | Seed'de `station_code:role:location_code` shape'i kullanıldı. |
| `station_code` | string | Uppercase station business key. |
| `role` | string | Lowercase binding role. Actual kolon adı `role`; `binding_role` kullanılmamalı. |
| `location_code` | string | Location join key. |
| `item_scope` | string veya null | Gelecek product/item override için. |
| `operation_scope` | string veya null | Gelecek operation/route override için. |
| `priority` | integer | Resolution sırasında düşük değer önce gelir. Seed default `100`. |
| `active` | boolean | Varsayılan read path aktif binding'leri döndürmeli. |
| `source_system` | string | Audit/debug için. |
| `source_file` | string veya null | Seed source bilgisi. |
| `external_ref` | string veya null | External/source reference. |
| `payload` | object/dict | JSONB; yoksa `{}` olarak normalize edilmeli. |
| `metadata` | object/dict | JSONB; yoksa `{}` olarak normalize edilmeli. |
| `created_at` | timestamp/string | `_json_safe` ile JSON serializable hale getirilmeli. |
| `updated_at` | timestamp/string | `_json_safe` ile JSON serializable hale getirilmeli. |

### `ResolvedStationLocation`

`ResolvedStationLocation`, bir station + role çözümünün sonucunu açıklamak için kullanılabilir.

Önerilen alanlar:

```text
station_code
role
location
binding
resolution_reason
candidate_count
missing
```

Davranış notları:

- `location`: resolved `LocationRow` veya `None`.
- `binding`: resolved `StationLocationBindingRow` veya `None`.
- `resolution_reason`: örnek değerler `exact_scope`, `generic_scope`, `not_found`, `inactive_location`, `ambiguous_candidates`.
- `candidate_count`: debug ve test için değerlidir.
- `missing`: location bulunamadığında veya binding yoksa `true` olabilir.

İlk implementasyonda bu model ayrı public output olmak zorunda değildir; `resolve_station_location` yalnız `LocationRow | None` döndürebilir. Ancak context üretiminde resolution açıklaması ileride işe yarar.

### `StationLocationContext`

`StationLocationContext`, Kiosk/dashboard/API tarafından okunabilecek birleşik read modeldir.

Önerilen alanlar:

```text
station_code
bindings
locations
locations_by_role
input_location
active_wip_location
output_good_location
output_scrap_location
output_buffer_location
missing_roles
inactive_or_missing_locations
generated_at
```

Alan notları:

| Alan | Not |
| --- | --- |
| `station_code` | Context'in üretildiği station. |
| `bindings` | Station için okunmuş active binding listesi. |
| `locations` | Binding'lerle join edilmiş unique location listesi. |
| `locations_by_role` | Role -> location listesi veya role -> default location map'i. İlk fazda tekil default map yeterli olabilir. |
| `input_location` | `role = 'input'` çözümü. |
| `active_wip_location` | `role = 'active_wip'` çözümü. |
| `output_good_location` | `role = 'output_good'` çözümü. |
| `output_scrap_location` | `role = 'output_scrap'` çözümü. |
| `output_buffer_location` | `role = 'output_buffer'` çözümü; her station için zorunlu değildir. |
| `missing_roles` | Expected role yoksa UI/debug için liste. |
| `inactive_or_missing_locations` | Binding var ama active location yoksa açıklayıcı liste. |
| `generated_at` | Opsiyonel runtime timestamp; DB write gerektirmez. |

İlk fazda expected role seti station'a göre esnek olmalıdır. Örneğin mevcut seed'de `PACKAGING_01` için `output_buffer` yoktur; bu tek başına hata değildir.

## 10. Query Tasarımı

Bu bölüm SQL migration değildir. Bir sonraki kodlama turunda eklenecek `SELECT_*_SQL` sabitleri için tasarım notudur.

### Location list query

Amaç:

- Aktif veya tüm location kayıtlarını listelemek.
- Opsiyonel `location_type` filtresi uygulamak.

Önerilen davranış:

```text
SELECT columns
FROM mes.locations
WHERE (:active_only false OR active = true)
  AND (:location_type is null OR location_type = :location_type)
ORDER BY location_type ASC, location_code ASC
```

Guardrail:

- Query yalnız `SELECT` olmalı.
- `FOR UPDATE` kullanılmamalı.
- `location_type` lowercase normalize edilmeli.
- `active_only=True` default olmalı.

### Location by code query

Amaç:

- Tek location'ı `location_code` ile bulmak.

Önerilen davranış:

```text
SELECT columns
FROM mes.locations
WHERE location_code = :location_code
LIMIT 1
```

Guardrail:

- `location_code` uppercase normalize edilmeli.
- Bulunamazsa helper `None` döndürmeli; create/update denememeli.
- `location_id` lookup veya join için kullanılmamalı.

### Station binding list query

Amaç:

- Station'a bağlı binding'leri role filtresiyle veya filtresiz okumak.

Önerilen davranış:

```text
SELECT columns
FROM mes.station_location_bindings
WHERE station_code = :station_code
  AND (:active_only false OR active = true)
  AND (:role is null OR role = :role)
ORDER BY role ASC, priority ASC, location_code ASC
```

Guardrail:

- `station_code` uppercase normalize edilmeli.
- `role` lowercase normalize edilmeli.
- Station bulunamadığında boş liste yeterlidir; bu read helper station master validation yapmamalı.

### Station location resolution query

Amaç:

- Station + role + optional scope için default active location çözmek.

Actual join:

```text
station_location_bindings.location_code = locations.location_code
```

Önerilen davranış:

```text
SELECT binding columns, location columns
FROM mes.station_location_bindings b
JOIN mes.locations l ON l.location_code = b.location_code
WHERE b.station_code = :station_code
  AND b.role = :role
  AND b.active = true
  AND l.active = true
  AND scope guard
ORDER BY scope specificity DESC, b.priority ASC, b.location_code ASC
LIMIT 1
```

Scope guard ilk fazda generic seed ile uyumlu olmalıdır:

```text
item_scope IS NULL
operation_scope IS NULL
```

İleride scope override açılırsa önerilen öncelik:

1. `item_scope` ve `operation_scope` ikisi de exact match.
2. Sadece `operation_scope` exact match.
3. Sadece `item_scope` exact match.
4. İkisi de null generic binding.

Bu scope davranışı implementation sırasında açık testlerle korunmalıdır.

### Station context query yaklaşımı

İki güvenli yaklaşım vardır:

1. `list_station_location_bindings` + `get_location_by_code` / batched location lookup ile context üretmek.
2. Tek joined query ile station binding ve location satırlarını birlikte okumak.

İlk implementation için tek joined query daha az round-trip üretir. Ancak mapping karmaşıklığı artarsa önce binding list, sonra location map yaklaşımı daha okunabilir olabilir.

Önerilen context sıralaması:

```text
ORDER BY b.role ASC, b.priority ASC, b.location_code ASC
```

### Explicit SELECT query adayları

Aşağıdaki query adayları implementation değildir; `mes_web/db/mesql_v2.py` içinde ileride tanımlanabilecek `SELECT_*_SQL` sabitleri için actual schema'ya uygun başlangıç taslağıdır.

#### Aktif locations

```sql
SELECT
  location_pk,
  location_id,
  location_code,
  location_name,
  location_type,
  parent_location_code,
  station_code,
  active,
  source_system,
  source_file,
  external_ref,
  payload,
  metadata,
  created_at,
  updated_at
FROM mes.locations
WHERE (%(active_only)s = false OR active = true)
  AND (%(location_type)s IS NULL OR location_type = %(location_type)s)
ORDER BY location_type, location_code;
```

#### Location by code

```sql
SELECT
  location_pk,
  location_id,
  location_code,
  location_name,
  location_type,
  parent_location_code,
  station_code,
  active,
  source_system,
  source_file,
  external_ref,
  payload,
  metadata,
  created_at,
  updated_at
FROM mes.locations
WHERE location_code = %(location_code)s;
```

#### Station bindings joined with locations

```sql
SELECT
  b.binding_pk,
  b.binding_id,
  b.station_code,
  b.role,
  b.location_code,
  b.item_scope,
  b.operation_scope,
  b.priority,
  b.active,
  b.source_system AS binding_source_system,
  b.source_file AS binding_source_file,
  b.external_ref AS binding_external_ref,
  b.payload AS binding_payload,
  b.metadata AS binding_metadata,
  b.created_at AS binding_created_at,
  b.updated_at AS binding_updated_at,
  l.location_pk,
  l.location_id,
  l.location_name,
  l.location_type,
  l.parent_location_code,
  l.station_code AS location_station_code,
  l.active AS location_active,
  l.source_system AS location_source_system,
  l.source_file AS location_source_file,
  l.external_ref AS location_external_ref,
  l.payload AS location_payload,
  l.metadata AS location_metadata,
  l.created_at AS location_created_at,
  l.updated_at AS location_updated_at
FROM mes.station_location_bindings b
LEFT JOIN mes.locations l
  ON l.location_code = b.location_code
WHERE b.station_code = %(station_code)s
  AND (%(active_only)s = false OR b.active = true)
  AND (%(role)s IS NULL OR b.role = %(role)s)
ORDER BY b.role, b.priority, b.location_code;
```

#### Resolve station + role

```sql
SELECT
  b.binding_pk,
  b.binding_id,
  b.station_code,
  b.role,
  b.location_code,
  b.item_scope,
  b.operation_scope,
  b.priority,
  b.active,
  l.location_pk,
  l.location_id,
  l.location_name,
  l.location_type,
  l.parent_location_code,
  l.station_code AS location_station_code,
  l.active AS location_active,
  l.payload AS location_payload,
  l.metadata AS location_metadata
FROM mes.station_location_bindings b
JOIN mes.locations l
  ON l.location_code = b.location_code
WHERE b.station_code = %(station_code)s
  AND b.role = %(role)s
  AND b.active = true
  AND l.active = true
  AND (
    b.item_scope IS NULL
    OR b.item_scope = %(item_scope)s
  )
  AND (
    b.operation_scope IS NULL
    OR b.operation_scope = %(operation_scope)s
  )
ORDER BY
  CASE WHEN b.item_scope = %(item_scope)s THEN 0 ELSE 1 END,
  CASE WHEN b.operation_scope = %(operation_scope)s THEN 0 ELSE 1 END,
  b.priority ASC,
  b.location_code ASC
LIMIT 1;
```

Risk notları:

- Scope parametreleri `None` iken SQL matching dikkatli test edilmelidir.
- İlk implementation generic/null scope ile sınırlı tutulabilir.
- Join key her zaman `location_code` olmalıdır.
- `location_id` veya `location_pk` join key yapılmamalıdır.
- Query adayları yalnız `SELECT` içerir; write path açmaz.

## 11. Resolution ve Guardrail Kuralları

Read modelin değişmez kuralları:

- `mes.locations` ve `mes.station_location_bindings` sadece okunur.
- Runtime bu fazda location veya binding seed etmeye çalışmaz.
- Missing binding, missing location veya inactive location durumunda DB write ile self-heal yapılmaz.
- Buffer station değildir; `location_type = 'buffer'` olan location olarak okunur.
- Work order lifecycle, station queue, production completion ve outbox davranışları değişmez.
- MESQL push/pull davranışı açılmaz.

Input normalization:

| Input | Normalization |
| --- | --- |
| `station_code` | `_upper(...)` benzeri uppercase trim |
| `location_code` | `_upper(...)` benzeri uppercase trim |
| `role` | lowercase trim |
| `location_type` | lowercase trim |
| `item_scope` | empty string -> `None` |
| `operation_scope` | empty string -> `None` |

Missing data davranışı:

| Durum | Önerilen davranış |
| --- | --- |
| Location code bulunamadı | `None` döndür veya context içinde missing olarak raporla. |
| Station binding yok | Boş liste döndür; context `missing_roles` doldurabilir. |
| Binding active ama location inactive | Resolution bu location'ı default seçmemeli; context `inactive_or_missing_locations` içinde göstermeli. |
| Aynı station/role için birden fazla active candidate | `priority ASC`, sonra `location_code ASC` ile deterministic seç; debug için candidate count taşı. |
| Role geçersiz | Helper seviyesinde empty result veya validation error; API açılırsa 400 daha uygun olabilir. |
| DB disabled | Mevcut `MesqlV2Error("DATABASE_DISABLED", status_code=503)` pattern'i ile uyumlu kal. |

Role-specific output mapping:

| Operation/display ihtiyacı | Role |
| --- | --- |
| Station input görünürlüğü | `input` |
| Aktif işlem/WIP görünürlüğü | `active_wip` |
| Good completion display target | `output_good` |
| Scrap completion display target | `output_scrap` |
| İki station arası buffer görünürlüğü | `output_buffer` |

Bu fazda role-specific output yalnız display/context amaçlıdır. `complete_operation_v2` sonucu veya `production_completions` insert payload'ı değiştirilmez.

## 12. MESQL, API ve UI Entegrasyon Sınırları

### MESQL sınırı

- MESQL push/pull bu tasarımın parçası değildir.
- `MESQL_SOURCE_SYSTEM`, integration inbox/outbox ve push/pull helper'ları değiştirilmez.
- Location context MESQL export payload'ına eklenmez.
- MESQL frozen durumundan çıkılmadan merkezi eşleme tasarlanmaz.

### API sınırı

Bu doküman API endpoint implementasyonu değildir. İleride açılabilecek endpoint adayları:

```text
GET /api/v2/locations
GET /api/v2/locations/{location_code}
GET /api/v2/stations/{station_code}/locations
GET /api/v2/stations/{station_code}/location-context
```

İlk kodlama turunda API açılması zorunlu değildir. Helper seviyesinde read model tamamlandıktan sonra endpoint açmak daha kontrollüdür.

API açılırsa guardrail:

- Response read-only olmalı.
- `POST`, `PUT`, `PATCH`, `DELETE` endpoint açılmamalı.
- Missing context 500 üretmemeli; açık `missing_roles` veya boş liste döndürebilmeli.
- Runtime config veya `.env` değişikliği gerektirmemeli.

### UI/Kiosk sınırı

UI/Kiosk entegrasyonu ileriki fazdır. İlk amaç, Kiosk/dashboard'ın şunları okuyabilecek hale gelmesidir:

- Station input location.
- Station active WIP location.
- Good output location.
- Scrap output location.
- Buffer location.

Bu bilgi sadece görünürlük sağlamalıdır. Operator action, complete flow, queue transition veya quantity movement kararı bu fazda değişmemelidir.

## Feature Flag Önerisi

Önerilen açık feature flag:

```text
MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED
```

Davranış:

- `false`: Runtime mevcut davranışla devam eder.
- `true`: Read-only station/location helper'ları kullanılabilir.
- Bu flag inventory movement, balance, sensor link veya write path açmaz.
- Bu flag MESQL push/pull açmaz.
- İlk implementation turunda helper'lar unit testlerde doğrudan çağrılabilir; runtime endpoint'e bağlanması ayrı fazdır.
- Default değer ilk fazda `false` kabul edilmelidir.

## 13. Test Tasarımı

Bu turda test çalıştırılmaz ve test dosyası değiştirilmez. Bu bölüm bir sonraki kodlama turu için test tasarımıdır.

Mevcut test pattern'i:

- `tests/test_mes_web_mesql_v2.py` fake cursor/connection kullanıyor.
- `database_connection` patch edilerek DB bağlantısı kurulmadan helper davranışı test ediliyor.
- SQL shape için `executed` listesi ve string assertion kullanılıyor.
- Output mapping için dict alanları assert ediliyor.

Önerilen unit test başlıkları:

```text
test_list_locations_reads_active_locations_by_default
test_list_locations_can_filter_by_location_type
test_get_location_by_code_normalizes_code_and_maps_row
test_get_location_by_code_returns_none_when_missing
test_list_station_location_bindings_filters_by_station_and_role
test_resolve_station_location_joins_by_location_code_not_location_id
test_resolve_station_location_ignores_inactive_location
test_resolve_station_location_orders_by_priority_then_location_code
test_get_station_location_context_groups_roles
test_get_station_location_context_reports_missing_optional_output_buffer
test_station_location_read_helpers_do_not_execute_write_sql
```

Özellikle korunacak assertion'lar:

- SQL içinde `from mes.locations` beklenmeli.
- SQL içinde `from mes.station_location_bindings` beklenmeli.
- Resolution SQL veya mapping tasarımında `location_code` join'i doğrulanmalı.
- `location_id` join key olarak kullanılmamalı.
- Read helper SQL'lerinde `insert into`, `update`, `delete`, `truncate`, `drop`, `for update` bulunmamalı.
- `station_code` parametresi uppercase normalize edilmeli.
- `role` parametresi lowercase normalize edilmeli.
- JSONB `payload` ve `metadata` boşsa `{}` döndürülmeli.

Smoke/regression tasarımı:

- Existing local successor activation testleri aynı kalmalı.
- `complete_operation_v2` ve `start_operation_v2` davranışı read model eklenince değişmemeli.
- MESQL push dry-run/pull dry-run testleri etkilenmemeli.

## 14. Implementation Prompt İçin Notlar

Bir sonraki kodlama turu için önerilen iş sırası:

1. `mes_web/db/mesql_v2.py` içine read-only SQL sabitleri ekle.
2. Row mapping helper'larını ekle:
   - `_location_row(row)`
   - `_station_location_binding_row(row)`
3. Public read helper'ları ekle:
   - `list_locations`
   - `get_location_by_code`
   - `list_station_location_bindings`
   - `resolve_station_location`
   - `get_station_location_context`
4. Unit testleri fake cursor/connection ile ekle.
5. Existing operation lifecycle testlerini regression olarak çalıştır.
6. API endpoint gerekirse ayrı turda ekle.

Implementation guardrail:

- SQL migration yazma.
- Existing migration dosyasını değiştirme.
- Operation lifecycle write path'lerine location write ekleme.
- `complete_operation_v2` içinde movement veya balance yazma.
- `station_queue` update/insert davranışını değiştirme.
- MESQL push/pull payload'ını değiştirme.
- Docker/compose/CMD değiştirme.
- `.env` değiştirme.

Önerilen ilk kodlama kapsamı sadece helper + unit test olmalıdır. API/UI entegrasyonu daha sonra, helper davranışı stabilize olduktan sonra yapılmalıdır.

## 15. Riskler ve Açık Kararlar

Riskler:

| Risk | Etki | Mitigation |
| --- | --- | --- |
| `location_id` ile join varsayımı kurulması | Actual schema ile uyumsuz read sonucu | Join key her yerde `location_code` olarak test edilmeli. |
| Station ve location kavramlarının karışması | Buffer station gibi davranabilir, queue/OEE semantiği bozulur | Buffer yalnız `location_type = 'buffer'` olarak gösterilmeli. |
| Read helper'ın operation lifecycle'a side-effect eklemesi | Existing smoke davranışı bozulabilir | Helper'lar standalone read-only kalmalı. |
| Missing binding'in runtime error'a dönüşmesi | Kiosk/dashboard kırılabilir | Context içinde missing role raporlanmalı; hard fail sadece explicit API validation'da düşünülmeli. |
| Scope resolution erken karmaşıklaşması | MVP helper gereksiz büyür | İlk faz generic `item_scope IS NULL` / `operation_scope IS NULL` ile başlayabilir. |
| JSONB payload'a domain logic bağlanması | Şema dışı kırılgan davranış | Domain kararları typed kolonlardan alınmalı; payload audit/pass-through kalmalı. |

Açık kararlar:

- API endpointleri bu helper turunda mı, sonraki turda mı açılacak?
- `StationLocationContext.locations_by_role` tekil default map mi, role -> list map mi olacak?
- `output_buffer` missing olması station bazında optional mı kabul edilecek, yoksa expected role seti station'a göre mi tutulacak?
- Scope resolution ilk implementasyonda generic-only mi kalacak?
- Public API output `location_pk` / `binding_pk` alanlarını gizleyecek mi?

Bu kararlar implementation öncesinde kısa kapsam kararı olarak netleştirilmelidir.

## 16. Kabul Kriterleri

Bu tasarım dokümanı tamam sayılmak için:

- Actual schema `db/migrations/003_add_station_locations.sql` ile uyumlu olmalı.
- `location_code` join key olarak açıkça belirtilmiş olmalı.
- `location_id` join varsayımı dışlanmış olmalı.
- `role` actual kolon adı olarak kullanılmalı; `binding_role` uygulanmış şema gibi yazılmamalı.
- Read-only helper adayları açık olmalı.
- Veri model alanları implementation promptuna temel olacak kadar net olmalı.
- Query guardrail'leri write path açmayacak şekilde tanımlanmalı.
- Feature flag önerisi açıkça tanımlandı.
- SELECT query adayları actual schema'ya uygun şekilde yazıldı.
- Query adaylarında write keyword bulunmuyor.
- Join key `location_code`.
- Test tasarımı fake cursor/connection pattern'iyle uyumlu olmalı.
- Existing operation lifecycle, station queue ve MESQL davranışlarının değişmeyeceği açık olmalı.
- SQL migration, Python/API implementation, DB bağlantısı, Docker/compose işlemi, MESQL push/pull veya test/smoke çalıştırma içermemeli.

## 17. Sonraki Uygulanabilir İş

Önerilen sonraki iş:

```text
Implement read-only station/location helper functions for Paket A tables
```

Önerilen dar kapsam:

- `mes_web/db/mesql_v2.py` içinde read-only helper + SQL constants.
- `tests/test_mes_web_mesql_v2.py` içinde fake cursor/connection unit testleri.
- API endpoint, UI entegrasyonu, inventory movement, balance, sensor link ve MESQL mapping yok.
