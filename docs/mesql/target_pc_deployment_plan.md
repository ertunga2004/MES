# Target PC Deployment Plan

Bu dokuman hedef PC deployment ve migration apply sirasi icin planlama notudur. Komut calistirma talimati degildir; bu sprintte Docker komutu, DB komutu veya migration apply yapilmaz.

## Calisma Modeli

- Gelistirme bu PC uzerinde ve Git ile yapilir.
- Hedef PC deployment/test SSH uzerinden planlanir.
- Hedef PC'de dogrudan gelistirme, drift ve geri alma riskini artirir.
- Runtime/Docker klasoru ile kaynak repo siniri korunur.

## Hedef PC'de Dogrudan Gelistirmenin Riskleri

| Risk | Etki |
| --- | --- |
| Git disi hotfix | Kod gecmisi ve rollback zorlasir. |
| Elle config degisikligi | Feature flag ve runtime davranisi izlenemez. |
| Backup'siz DB apply | Veri kaybi ve geri donus riski. |
| Docker volume silme | Runtime DB population kaybi. |
| Migration/hook karisikligi | Hata kaynagı ayristirilamaz. |

## Degismez Guardrailler

- Backup olmadan migration yok.
- `docker compose down -v` yok.
- DB volume silinmez.
- Migration ve runtime hook ayni fazda uygulanmaz.
- DB hatasi runtime'i cokertmemelidir.
- Commit/push/apply icin ayrica kullanici onayi gerekir.

## Migration Apply Sirasi

Planlanan guvenli sira:

1. Git kaynagini hedef PC'de guncelle.
2. Docker servis durumunu kontrol et.
3. DB backup al.
4. Read-only compatibility report calistir.
5. Migration dry-run veya apply planini incele.
6. Izole migration apply yap.
7. Post-migration verification calistir.
8. Health check yap.
9. Feature flag davranisini ayrica ve kontrollu test et.

Bu liste operasyon planidir; bu dokuman komut calistirmaz ve migration dosyasi yerine gecmez.

## Backup ve Verify

Backup en az sunlari kapsamalidir:

- DB dump.
- Runtime JSON/log kritik dosyalari.
- FERP import/export state dosyalari gerekiyorsa ilgili snapshot.
- `.env` veya compose degisikligi olacaksa onceki kopya.

Verification:

- Count baseline.
- Duplicate/null key report.
- Application `/health`.
- Ilgili verify scriptleri.
- UI smoke: dashboard/kiosk kritik gorunumleri.

## Rollback Notu

Rollback planı migration dosyasindan ayri yazilmali ve migration oncesi onaylanmalidir. Feature flag kapatmak runtime davranisini geri alabilir; fakat DB schema degisikligini tek basina geri almaz.

## Sonuc

Hedef PC deployment sirasi once kanit, sonra apply mantigiyla ilerlemelidir. Bu dokuman sadece planlama kaynagidir; production komutu veya migration uygulama talimati degildir.
