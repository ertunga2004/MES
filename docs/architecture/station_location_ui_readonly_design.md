# Station/Location UI Read-Only Design

## 1. Amaç

Bu doküman station/location context bilgisinin MES Web / Kiosk / Dashboard
tarafında nasıl read-only gösterileceğini tasarlar.

Amaç operatöre veya kullanıcıya istasyonun hangi lokasyonlarla ilişkili
olduğunu göstermektir. Bu tasarım herhangi bir operasyonel davranış
başlatmaz. Start operation, complete operation, `station_queue`, work order
lifecycle, inventory movement veya MESQL sync davranışı değişmez.

## 2. Mevcut Doğrulanmış Altyapı

- Paket A migration uygulandı.
- `mes.locations` ve `mes.station_location_bindings` mevcut.
- Read-only helper implementation tamamlandı.
- Read-only API implementation tamamlandı.
- API smoke PASS.
- Tier 1 CI workflow PASS.
- Feature flag default disabled.
- UI/Kiosk henüz bu veriyi tüketmiyor.
- Mevcut UI yüzeyi server template yerine ağırlıklı olarak `mes_web/static`
  altındaki client-side HTML/JS dosyalarından oluşuyor.
- Kiosk snapshot içinde bugün yalnız sınırlı `station_context.station_code`
  alanı bulunuyor; station/location read model context henüz ekrana taşınmıyor.

## 3. Kapsam

Bu tasarımın kapsamı:

- Station/location context'in UI'da bilgi kartı olarak gösterimi.
- Kiosk veya station dashboard ekranında input/output lokasyonlarının
  görünmesi.
- API çağrı stratejisi.
- Loading / disabled / error / missing role davranışları.
- Görsel field isimleri.
- Feature flag davranışı.
- Test stratejisi.
- Guardrail ve kabul kriterleri.

## 4. Kapsam Dışı

- UI implementation yok.
- API değişikliği yok.
- DB write yok.
- SQL migration yok.
- Inventory movement yok.
- Inventory balance yok.
- Sensor event link yok.
- MESQL push/pull yok.
- Work order lifecycle değişikliği yok.
- Station queue değişikliği yok.
- Operation start/complete değişikliği yok.
- Kiosk buton davranışı değişikliği yok.
- F-ERP entegrasyonu yok.
- WMS ekranı yok.
- Stok transfer ekranı yok.

## 5. Kullanıcı İhtiyacı

Operatör veya kullanıcı, bir istasyonda işlem yaparken istasyonun hangi
fiziksel/logical lokasyonlarla ilişkili olduğunu görebilmeli.

Örneğin `PACKAGING_01` için:

- input: `BETWEEN_ASSEMBLY_PACKAGING`
- active_wip: `PACKAGING_WIP`
- output_good: `FINISHED_GOODS`
- output_scrap: `SCRAP_AREA`
- output_buffer: yok / not configured

`ASSEMBLY_01` için:

- input: `RAW_MATERIAL`
- active_wip: `ASSEMBLY_WIP`
- output_good: `BETWEEN_ASSEMBLY_PACKAGING`
- output_buffer: `BETWEEN_ASSEMBLY_PACKAGING`

Bu bilgi sadece görünürlük sağlar; stok hareketi yapmaz.

## 6. Önerilen UI Yerleşimi

### 6.1 Station Context Bilgi Kartı

Önerilen başlık:

```text
Station Location Context
```

veya Türkçe:

```text
İstasyon Lokasyon Bilgisi
```

Alanlar:

```text
Input Location
Active WIP Location
Output Good Location
Output Scrap Location
Output Buffer Location
```

Türkçe label önerisi:

```text
Giriş Lokasyonu
Aktif WIP Lokasyonu
Sağlam Çıkış Lokasyonu
Fire/Hurda Çıkış Lokasyonu
Ara Buffer Lokasyonu
```

Her satırda gösterilecek minimum alanlar:

- role label
- `location_code`
- `location_type`
- aktif/pasif durumu varsa badge
- missing ise `Not configured`

Örnek `PACKAGING_01` görünümü:

```text
İstasyon Lokasyon Bilgisi - PACKAGING_01

Giriş Lokasyonu: BETWEEN_ASSEMBLY_PACKAGING (buffer)
Aktif WIP Lokasyonu: PACKAGING_WIP (wip)
Sağlam Çıkış Lokasyonu: FINISHED_GOODS (finished_goods)
Fire/Hurda Çıkış Lokasyonu: SCRAP_AREA (scrap)
Ara Buffer Lokasyonu: Not configured
```

### 6.2 Kiosk Ekranında Konum

Öneri:

- Kart, start/complete butonlarının yanında değil, altında veya sağ panelde
  bilgi kartı olarak gösterilmeli.
- Buton akışını etkilememeli.
- Operatörün ana aksiyonlarını gölgelemeyecek sade bir kart olmalı.
- Ekran küçükse collapsible/expandable panel olabilir.
- Mevcut `kiosk.html` düzeninde aday yerler:
  - `primary-panel` altında aktif iş emri bilgisinden sonra küçük bilgi kartı.
  - `queue-panel` üstünde veya altında collapsible read-only panel.
- Mevcut `kiosk.js` içinde ana operasyon butonları `bigActionButton`,
  `systemStartButton` ve queue row action button'larıdır; station/location
  kartı bu butonların enabled/disabled durumunu değiştirmemelidir.

### 6.3 Dashboard Ekranında Konum

Öneri:

- Station detail veya station status alanında read-only context kartı.
- Üretim akış diyagramı varsa station node'una tıklanınca gösterilebilir.
- İlk implementation için sade kart yeterlidir; diyagram/flow visualization
  sonraki fazdır.
- Mevcut dashboard'da `Istasyon Is Emri Board` ve
  `station-work-order-board` doğal yerleşim adayıdır.
- Her `station-work-order-card` içine, active/queue kartlarının üstünde veya
  altında küçük `Station Location Context` bloğu eklenebilir.

## 7. API Tüketim Tasarımı

Ana endpoint:

```text
GET /api/v2/stations/{station_code}/location-context
```

Kullanım:

- Station ekranı açıldığında bir defa çağrılır.
- Station değiştiğinde tekrar çağrılır.
- İsteğe bağlı manuel refresh butonu olabilir.
- Otomatik kısa aralıklı polling gerekli değildir.

Alternatif endpoint:

```text
GET /api/v2/stations/{station_code}/locations
```

Kullanım:

- Daha detaylı binding listesi gerektiğinde.
- İlk UI için context endpoint tercih edilir.

API response'tan kullanılacak alanlar:

- `station_code`
- `input_location`
- `active_wip_location`
- `output_good_location`
- `output_scrap_location`
- `output_buffer_location`
- `missing_roles`
- `inactive_or_missing_locations`

İlk implementation için client-side fetch card seçeneği uygundur. Mevcut
dashboard ve kiosk JavaScript ağırlıklı olduğu için bu yaklaşım loading,
disabled ve error durumlarını ana snapshot lifecycle'ına bağlamadan yönetebilir.

## 8. Feature Flag Davranışı

Feature flag:

```text
MES_WEB_DB_STATION_LOCATION_READ_MODEL_ENABLED
```

Davranış:

- Flag disabled ise API 503 döner.
- UI bu durumda hata gibi değil, "Station/location view disabled" gibi sakin
  bir bilgi göstermeli.
- UI ana operasyon akışını durdurmamalı.
- Start/complete butonlarını devre dışı bırakmamalı.
- Feature flag UI tarafından write path olarak yorumlanmamalı.

Önerilen disabled mesajı:

```text
İstasyon lokasyon bilgisi bu ortamda aktif değil.
```

veya teknik UI için:

```text
Station/location read model disabled.
```

## 9. Loading, Empty ve Error Durumları

### Loading

Gösterim:

```text
Lokasyon bilgisi yükleniyor...
```

### 503 Disabled

Gösterim:

```text
İstasyon lokasyon bilgisi bu ortamda aktif değil.
```

Ana operasyon akışı devam eder.

### 404 / Station Yok

Bu endpoint station binding yoksa 200 + empty context dönebilir. Eğer 404
alınırsa:

```text
Bu istasyon için lokasyon bilgisi bulunamadı.
```

### Missing Role

Örneğin `PACKAGING_01` için `output_buffer` yoksa:

```text
Ara Buffer Lokasyonu: Not configured
```

Bu hata değildir.

### Inactive or Missing Location

Eğer `inactive_or_missing_locations` doluysa:

- Kart içinde uyarı olarak gösterilebilir.
- Ana operation lifecycle durdurulmamalı.
- Mesaj:

```text
Bazı lokasyon eşleşmeleri pasif veya eksik görünüyor.
```

### 500 / Database Error

Gösterim:

```text
Lokasyon bilgisi şu anda okunamadı.
```

Ana operasyon akışı otomatik durdurulmamalı. Ancak log/diagnostic için hata
kaydı önerilebilir.

## 10. Görsel Öncelik

Öncelik sırası:

1. `input_location`
2. `active_wip_location`
3. `output_good_location`
4. `output_scrap_location`
5. `output_buffer_location`

Renk/badge önerisi:

- `raw_material`: hammadde
- `wip`: süreç içi
- `buffer`: ara tampon
- `finished_goods`: mamul
- `scrap`: fire/hurda
- `hold`: bekletme
- `rework`: yeniden işleme

Not:

- Bu turda renk kodu implement edilmeyecek.
- Renkler UI implementation fazında mevcut tasarım sistemine göre seçilmeli.

## 11. Operasyonel Guardrail

- UI bu veriyi sadece okur.
- UI bu veriye göre otomatik start/complete kararı vermez.
- UI bu veriye göre stok hareketi oluşturmaz.
- UI bu veriye göre `station_queue` değiştirmez.
- UI bu veriye göre MESQL push/pull başlatmaz.
- UI bu veriye göre F-ERP kaydı oluşturmaz.
- UI bu veriyi operatör için bağlam bilgisi olarak gösterir.

## 12. Test Stratejisi

Bu bölüm implementation turu için test planıdır.

### UI Unit/Component Testleri

Önerilen testler:

```text
test_station_location_card_renders_context
test_station_location_card_renders_missing_output_buffer_as_not_configured
test_station_location_card_handles_feature_flag_disabled_503
test_station_location_card_handles_empty_context
test_station_location_card_handles_inactive_or_missing_locations_warning
test_station_location_card_does_not_disable_operation_buttons
```

### API Integration Mock Testleri

Önerilen:

- API 200 context dönerse kart doğru dolar.
- API 503 dönerse disabled mesajı görünür.
- API 500 dönerse non-blocking error mesajı görünür.
- Missing `output_buffer_location = null` hata üretmez.

### Guardrail Testleri

Önerilen:

- UI component start/complete endpointlerini çağırmıyor.
- UI component POST/PUT/PATCH/DELETE çağırmıyor.
- UI component MESQL endpointi çağırmıyor.
- UI component sadece GET
  `/api/v2/stations/{station_code}/location-context` çağırıyor.

## 13. Implementation Seçenekleri

### Seçenek A: Server-rendered Card

Artılar:

- Mevcut template yapısına uygunsa basit.
- JS ihtiyacı az.

Eksiler:

- Feature flag/API disabled durumlarını runtime'da göstermek daha sınırlı
  olabilir.
- Bu repo'da ana UI yüzeyi şu an server template ağırlıklı görünmüyor.

### Seçenek B: Client-side Fetch Card

Artılar:

- Feature flag disabled, loading, error durumları daha esnek yönetilir.
- Station değişimlerinde refresh kolaydır.
- Mevcut `kiosk.js` ve dashboard `app.js` yapısıyla daha uyumludur.

Eksiler:

- JS tarafında test ihtiyacı doğar.

Öneri:

- Mevcut MES Web UI yapısı basit HTML/JS olduğu için client-side fetch card
  daha uygun olabilir.
- İlk implementation, server-rendered placeholder + client-side fetch hibrit
  yapıda tutulabilir.
- Kiosk için önce tek station context kartı, dashboard için sonra station board
  içi kart yaklaşımı tercih edilebilir.

## 14. Riskler

| Risk | Etki | Önlem |
| --- | --- | --- |
| UI kartının operasyonel karar gibi algılanması | Operatör yanlış beklentiye girer | "Bilgi amaçlıdır" metni |
| Missing role 500 gibi gösterilir | Gereksiz alarm | `Not configured` gösterimi |
| Feature flag disabled ana akışı bozar | Kiosk kullanılmaz hale gelir | Non-blocking disabled mesajı |
| UI start/complete davranışına bağlanır | Lifecycle bozulabilir | Guardrail testleri |
| Inventory movement fazına erken kayılır | Scope büyür | Read-only kapsam |
| Çok fazla teknik field gösterilir | Operatör karmaşa yaşar | Minimal field set |

## 15. Kabul Kriterleri

Bu design dokümanı için kabul kriterleri:

- UI/Kiosk read-only gösterim amacı net.
- Gösterilecek roller ve label'lar tanımlı.
- API tüketim endpointi net.
- Feature flag disabled davranışı net.
- Missing role / empty / 500 davranışları net.
- Operation lifecycle'a dokunulmayacağı net.
- Inventory movement/balance yok.
- MESQL yok.
- Test stratejisi var.
- Implementation promptuna temel olacak kadar açık.

## 16. Sonraki Adım

- Bu tasarım onaylandıktan sonra bir sonraki teknik adım UI/Kiosk read-only
  implementation olabilir.
- İlk implementation küçük tutulmalı:
  - tek bilgi kartı
  - tek GET endpoint
  - non-blocking error handling
  - start/complete davranışına dokunmadan
- Inventory movement/balance hala sonraki fazdır.
