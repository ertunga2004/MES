# Kiosk Dynamic Action Design

## 1. Amaç

Bu doküman, Kiosk action/button davranışının hard-coded akışlardan çıkarılıp
SQL-driven operation step policy'den türetilmesi için read/write davranış
tasarımını açıklar.

Bu doküman Kiosk implementation değildir. HTML, CSS, JavaScript, Python/API veya
DB davranışı değiştirmez.

## 2. Baseline

Mevcut Kiosk station/location read-only kartı doğrulanmıştır.

Korunacak davranışlar:

- Station/location kartı read-only kalır.
- Mevcut operation start/complete butonları yeni feature flag açılmadan
  bozulmaz.
- Kiosk mevcut station route'ları ve static asset davranışı korunur.
- MESQL push/pull yoktur.

## 3. Kapsam

- DB policy'den action üretme modeli.
- `manual_start`, `manual_finish`, `auto_start`, `auto_finish`,
  `implicit_start`, `implicit_finish` UI anlamları.
- Current actionable step algoritması.
- Final approval action modeli.
- Existing Kiosk ile compatibility planı.

## 4. Kapsam Dışı

- Kiosk HTML/JS/CSS implementation.
- API endpoint implementation.
- Runtime engine code.
- SQL migration.
- DB/psql/Docker/test/smoke.
- Inventory movement/balance.

## 5. Kiosk Action Kaynağı

Kiosk action'ları doğrudan şu kaynaklardan türetilmelidir:

- Active station.
- Active veya ready work order operation.
- Operation step instances.
- Step `start_mode`.
- Step `finish_mode`.
- Step `status`.
- `approval_required_after_finish`.
- Operation `execution_status`.
- Operation `operation_completion_policy`.

Kiosk, master `operation_steps` yerine mümkünse runtime
`work_order_operation_steps` state'ini okumalıdır.

## 6. Action Modeli

Önerilen action shape:

```text
action_id
action_type
station_code
work_order_id
work_order_operation_id
step_code
step_name
label
enabled
reason
requires_confirmation
expected_event_type
```

Bu shape implementation değildir; API/UI tasarım sözleşmesi önerisidir.

## 7. Mode Davranışları

### `manual_start`

UI davranışı:

- Step `pending` ise başlat action'ı gösterilir.
- Action label örneği: `Başlat`.
- Action accepted olursa runtime engine step'i `active` yapar.

### `manual_finish`

UI davranışı:

- Step `active` ise bitir/onayla action'ı gösterilir.
- `approval_required_after_finish = true` ise label `Onayla` veya `Final Onay`
  olabilir.

### `auto_start`

UI davranışı:

- Start butonu gösterilmez.
- Step beklenen event source'tan event bekler.
- Kiosk read-only status gösterebilir: `Sensör/robot olayı bekleniyor`.

### `auto_finish`

UI davranışı:

- Finish butonu gösterilmez.
- Step active veya pending-with-implicit-start durumunda event bekler.

### `implicit_start`

UI davranışı:

- Start butonu gösterilmez.
- Önceki step tamamlandıktan sonra engine step'i active kabul edebilir.

### `implicit_finish`

UI davranışı:

- Finish butonu gösterilmez.
- Sonraki step veya engine transition ile tamamlanabilir.

## 8. Current Actionable Step Algoritması

MVP:

```text
1. station_code ile current operation context al.
2. Operation için sidecar execution_state al.
3. work_order_operation_steps listesini step_no ASC sırala.
4. İlk pending/active step'i bul.
5. Step auto-only ise kullanıcı action'ı üretme.
6. Step manual_start bekliyorsa tek start action üret.
7. Step manual_finish bekliyorsa tek finish/approval action üret.
8. Operation pending_final_approval ise final approval action üret.
9. Aynı anda birden fazla primary action gösterme.
```

Kritik kural:

```text
Kiosk aynı anda tüm step butonlarını göstermemelidir.
```

## 9. UI State Önerileri

Kiosk action paneli şu durumları ayırt etmelidir:

- `no_operation`: İstasyonda aktif/sıradaki iş yok.
- `waiting_auto_event`: Current step auto event bekliyor.
- `manual_action_required`: Operatör action'ı gerekiyor.
- `pending_final_approval`: Final approval bekleniyor.
- `closed`: Operation kapanmış.
- `error_or_invalid_setup`: Setup veya runtime state tutarsız.

Bu state'ler mevcut station/location kartından ayrı gösterilmelidir.

## 10. Compatibility Plan

İlk faz:

- Existing Kiosk operation buttons korunur.
- Dynamic action panel read-only preview olarak eklenebilir.
- Feature flag kapalıyken action POST yapılmaz.
- Feature flag açıkken bile existing lifecycle ile mapping test edilmeden
  destructive davranış açılmaz.

İkinci faz:

- Dynamic action POST endpointleri runtime engine'e event gönderir.
- Existing direct complete/start akışı kademeli olarak engine event akışına
  bağlanır.

## 11. Error Handling

Kiosk açık ve net reason göstermelidir:

- Operation yok.
- Step setup eksik.
- Event source inactive.
- Station/location context missing.
- Current step auto event bekliyor.
- Action feature flag disabled.
- Runtime engine compatibility mode read-only.

## 12. Kabul Kriterleri

Bu tasarım tamamlanmış sayılır, eğer:

- Kiosk action'ların DB policy'den nasıl türeyeceği tanımlıysa.
- Manual/auto/implicit mode UI davranışları ayrılmışsa.
- Current actionable step algoritması varsa.
- Mevcut read-only station/location kartının korunacağı yazılmışsa.
- Implementation yapılmamışsa.
