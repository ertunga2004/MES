# Read-Only Compatibility Reports

Bu sprintin amaci, runtime `mes` schema icin production migration oncesi calistirilacak read-only compatibility report paketini hazirlamaktir.

Bu dokuman ve SQL raporlari migration degildir. DB'ye veri veya sema degisikligi uygulamaz. Runtime kodu, Docker veya feature flag davranisi degistirmez.

## SQL Dosyalari

Rapor paketi:

- `db/reports/compatibility/runtime_mes_compatibility_report.sql`
- `db/reports/compatibility/runtime_mes_compatibility_report.quickcheck.sql`
- `db/reports/compatibility/README.md`

## Neden Migration Oncesi?

Production migration veya live transition oncesi mevcut veri durumunun kanitlanmasi gerekir:

- Baseline count.
- Null/blank key riski.
- Duplicate idempotency key riski.
- Orphan relation riski.
- Timestamp sanity.
- Station queue ve package runtime tutarliligi.

Rapor temiz degilse migration yapilmamalidir.

## Hedef PC Calisma Prensibi

- Raporlar hedef PC'de manuel ve onayli sekilde calistirilmalidir.
- Raporlardan once DB backup alinmalidir.
- Rapor sonucu `docs/mesql/read_only_compatibility_report_result_template.md` ile dokumante edilmelidir.
- Rapor sonucu otomatik go karari degildir; migration go/no-go ayrica onaylanmalidir.

## Beklenen Cikti Kolonlari

Her rapor su kolonlari dondurur:

- `check_group`
- `check_name`
- `severity`
- `finding_count`
- `sample_value`
- `recommendation`

## Severity Yorumu

| Severity | Anlam | Etki |
| --- | --- | --- |
| `INFO` | Baseline veya dagilim bilgisi. | Karar girdisi. |
| `WARN` | Migration oncesi incelenmesi gereken risk. | Go/no-go oncesi degerlendirilmeli. |
| `FAIL` | Kapanmadan migration veya live transition yapilmamali. | Cleanup/decision gerekir. |

## Sonraki Faz

1. Hedef PC'de DB backup al.
2. Quickcheck raporunu calistir.
3. Tam raporu calistir.
4. Sonucu result template ile dokumante et.
5. Migration go/no-go kararini ayrica ver.

Bu faz SQL raporlarini calistirma fazi degildir; yalniz paket hazirlar.
