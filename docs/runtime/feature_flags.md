# Runtime Feature Flags

Bu dokuman runtime ve DB gecisinde kullanilan feature flag mantigini aktif dokumana konsolide eder. Kaynak notlar `docs/agent_memory/18_feature_flag_matrix.md`, `docs/agent_memory/08_guardrails_and_do_not_touch.md`, `docs/mesql/sql_source_of_truth.md` ve SQL MVP checkpoint notlaridir.

Bu dokuman config degisikligi degildir. Yeni runtime flag eklemez, default deger degistirmez ve production davranisi acmaz.

## Neden Feature Flag?

MES runtime halen Excel, JSON, FERP ve MQTT akislarini korur. SQL/MESQL gecisi kademeli oldugu icin yeni DB baglantisi, write hook, read overlay veya export davranisi ancak flag ile izole edilmelidir.

Feature flag hedefleri:

- Yeni davranisi dar kapsamda acmak.
- Sorun olursa eski runtime akisini bozmadan kapatmak.
- Dry-run, live hook, shadow read ve final read switch fazlarini ayirmak.
- Migration, hook ve read gecisini ayni sprintte karistirmamak.

## Temel Kurallar

- DB write hook ve DB read ayni fazda acilmamalidir.
- Migration ve runtime hook ayni sprintte olmamalidir.
- `MES_WEB_DB_ENABLED` gibi DB master flag defaultlari guvenli kalmalidir.
- Flag kapaliyken runtime davranisi degismemelidir.
- DB hatasi core MES runtime'i cokertmemelidir.
- Canli flag acma/kapama test sonunda tekrar guvenli moda alinmalidir.

## Mevcut Bilinen DB Flag Sinirlari

| Flag | Genel anlam | Guvenlik notu |
| --- | --- | --- |
| `MES_WEB_DB_ENABLED` | DB entegrasyon master switch | Varsayilan guvenli kalmali; tek basina full source-of-truth anlamina gelmez. |
| `MES_WEB_DB_MIRROR_WORK_ORDERS` | JSON/FERP work orders -> DB mirror/upsert | Read flag ile karistirilmamali. |
| `MES_WEB_DB_READ_WORK_ORDERS` | Work order view icin DB read overlay | Read-only davranistir; mirror/upsert tetiklememelidir. |
| `MES_WEB_DB_FAIL_OPEN` | DB hatasinda runtime'in calismaya devam etmesi | SQL gecisinde kritik guvenlik davranisidir. |
| `MES_WEB_DB_HOOK_PRODUCTION_COMPLETIONS` | Production completions live write hook | Natural key/unique kararlarindan sonra acilabilir. |
| `MES_WEB_DB_HOOK_STATION_EVENTS` | Station event live writer | Idempotency ve controlled flow ile dogrulanmalidir. |

Bu tablo mevcut ve tarihsel memory notlarini ozetler; yeni config ekleme talimati degildir.

## Flag Turleri

| Flag turu | Amac | Ornek karar |
| --- | --- | --- |
| DB connection | DB entegrasyonunu global olarak ac/kapat | Master switch default guvenli olmalidir. |
| Mirror write | Runtime JSON/FERP state'i DB'ye upsert etmek | Read source degistirmez. |
| Live hook | Event olusurken DB'ye yazmak | Once dry-run ve compatibility gerekir. |
| Read source switch | Runtime view veya raporu DB'den okumak | Once shadow read/compare gerekir. |
| ERP/F-ERP export | Export/outbox davranisini izole etmek | ERP conflict ve label kararlarini gerektirir. |
| BOM/BOP importer | BOM/BOP source payload import davranisini izole etmek | Source owner gelmeden acilmamalidir. |

## Mirror / Write / Read Gecis Prensibi

Onerilen sira:

1. Read-only analiz veya dry-run.
2. Mirror/write hook no-op gozlem.
3. Controlled live hook.
4. Verify clean.
5. Shadow read/compare.
6. Read source switch.
7. Source-of-truth switch.

Write hook DB'ye veri yazar ama runtime'in okuma kaynagini degistirmez. Read switch runtime'in okuma kaynagini etkiler; bu nedenle ayri fazda ele alinmalidir.

## Dry-Run / No-Op Hook

Dry-run veya no-op hook:

- Event'i yakalar.
- Yazilacak payload'i loglar veya raporlar.
- DB'ye production write yapmaz.
- Verify ve compatibility icin kanit toplar.

Live hook ancak dry-run sonucu temizse ve gerekli unique/natural-key kararlar kapanmissa acilmalidir.

## Shadow Read / Compare

Shadow read:

- Eski kaynak ve DB kaynagini ayni anda okur.
- Runtime davranisini DB sonucuna gecirmez.
- Farklari raporlar.
- Clean sonuc alinmadan read source switch yapilmaz.

Work orders icin MVP read overlay tamamlanmis olsa bile full dashboard, OEE, package, quality ve downtime SQL read ayrica tasarlanmalidir.

## Rollback

- Sorun cikan dar flag `false` yapilir.
- Gerekirse `MES_WEB_DB_ENABLED=false` ile DB entegrasyonu izole edilir.
- Excel/JSON/FERP/MQTT fallback ve audit yollari korunur.
- DB read ya da write flag'i kapatmak migration rollback yerine gecmez; migration icin ayri rollback plan gerekir.

## Yapilmamasi Gerekenler

- `.env`, Docker veya runtime config defaultlarini bu dokuman sprintinde degistirme.
- Read flag ile mirror/upsert davranisini karistirma.
- Migration'i feature flag ile gizleme.
- BOM/BOP importer flag'i source owner olmadan acma.
- ERP/F-ERP export flag'i label ve conflict lifecycle kararlari kapanmadan production kullanima alma.
