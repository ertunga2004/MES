# AT-ZEZE | Çalışma ve Katkı Rehberi

> Bu rehber **yalnızca AT-ZEZE çalışma dalındaki** işbirliği için hazırlanmıştır. Ayrıntılı teknoloji seçimi, mimari ve proje yönetim planını öğrenciler oluşturur.

## Çalışma alanı

- Repo: `ertunga2004/MES`
- Ortak entegrasyon dalı: `at-zeze/pre-sql-two-station`
- Temel sürüm: `562e13bd46bacc4c4e1f8420a01c915dc20e6d37` (16.05.2026)
- **`main` ve başka projelerin dallarına commit/push/merge yapılmaz.**
- Öğrenciler kendi konu dallarını ortak AT-ZEZE dalından açabilir (`feat/...`, `fix/...`, `docs/...`). Değişiklikler PR ile ortak dala alınır; değişiklikleri mümkünse diğer ekip üyesi inceler.
- `force push`, tarihçe yeniden yazma veya başkasının değişikliklerini silme işlemlerinden kaçının. Zorunluysa önce birlikte görüşün.

## Önce anlamak, sonra düzenlemek

Repo içeriğini, mevcut MES kurulumunu ve kullanılan donanımı inceleyin. Özellikle `README.md`, `mes_web/README.md`, `mes_web/`, `CPP/` ve `Giyotin_kontrol/` başlangıç için yol göstericidir.

**Klasörleri yeniden düzenleme ve teknik çözümü seçme yetkisi ekibe aittir.** Ancak önce hangi parçaların aktif kullanıldığını tespit edin. İşlevsel değişikliklerle geniş çaplı klasör taşıma işlerini mümkünse ayrı PR'larda yapın; çalışan konveyörü bozmayın. Gizli anahtar, kişisel bilgi, cihaz parolası, `.env`, üretilmiş büyük dosya ve canlı üretim kayıtlarını repoya eklemeyin.

## İlk çalışma / ilk sunum

Başlangıçta amaç kodu hızla değiştirmek değil, **mevcut sistemi çalıştırıp ve anlayıp kendi planınızı önermektir**:

1. Erişebildiğiniz kaynakları ve başlangıç durumunu doğrulayın; çalıştırabildiğiniz yazılım/testleri, çalıştıramadıklarınızdan ayırın.
2. `PROJECT_BRIEF.md` içindeki hedeflere yönelik **kendi ön tasarımınızı** ve gerekçelerinizi hazırlayın.
3. İş bölümü, dönem içi takvim, önemli riskler, ihtiyaçlar ve gösterim/test yaklaşımını belirleyin.
4. İlk sunumda varsayımları, çözülemeyen soruları ve atölyeden beklenen kararları açıkça gösterin.

Dosya ve klasör adlarını ekip seçebilir. Kısa Markdown belgeleri GitHub üzerinde takip edilebilir kılın.

## Günlük çalışma düzeni

- Görevleri küçük, kapanabilir parçalara bölün. GitHub Issues/PR veya eşdeğer hafif bir takip düzeni kullanın; araç seçimi ekibe ait.
- Haftalık kısa ilerleme paylaşımında **yapılan / sıradaki / engel** bilgisini iletin. Kayıtlar mümkünse Issue/PR bağlantılarıyla desteklensin.
- Denenmiş bir çözümü savunurken ölçüm, test veya karşılaştırma gösterin. Çalışmayan ve henüz yapılmayan işleri yapılmış gibi raporlamayın.
- Kod değişikliğinde mevcut ilgili testleri çalıştırın; yeni davranış için doğrulama hazırlayın. Test edilmeyen fiziksel işlevleri açıkça belirtin.
- Değişiklikleri küçük ve anlaşılır commit'lerle takip edin; PR açıklamasında **ne, neden, nasıl doğrulandı** sorularını yanıtlayın.

## Fiziksel donanım ve simülasyon güvenliği

Giyotin ve hareketli mekanizmalar için fiziksel korumalar, acil durdurma, yetkisiz çalıştırma ve elektriksel güvenlik konuları tasarım değerlendirmesinin parçasıdır. **Kodu yüklemek veya MES'ten komut göndermek bir güvenlik doğrulaması değildir.** Gerçek cihaza hareket komutu veren testler, gerekli güvenlik değerlendirmesi ve atölye onayı olmadan otomatik çalıştırılmamalı.

Simülasyon ve gerçek veriler açıkça ayırt edilmelidir. Simülasyon modu fiziksel aktüatörleri yanlışlıkla tetiklememelidir.

## Ne zaman atölyeye danışılır?

**Yardım ve tasarım incelemesi** isteyin; atölye ekibi problemi sizin yerinize çözmeyecek. Özellikle şu durumları erken bildirin:

- Kapsam veya dönem sonu teslim hedefinin değişmesi
- Yeni donanım/bütçe ihtiyacı ya da fiziksel güvenlik riski
- Mevcut MES ana işlevlerinde regresyon veya veri kaybı ihtimali
- Birden fazla makul yaklaşım arasında önemli mimari tercih

Dönem sonu tesliminde çalışan gösterim, çalıştırma talimatı, tasarım gerekçeleri, test/deney sonuçları ve bilinen sınırlamalar bulunmalıdır.
