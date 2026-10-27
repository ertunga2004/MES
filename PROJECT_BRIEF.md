# AT-ZEZE | Proje Görevlendirmesi

> **Sürüm:** 1.0 | **Tarih:** 27 Ekim 2026  
> **Ekip:** Zehra (@zehrakuzey) ve Zeynep (@zeynepp36)  
> **Çalışma türü:** Endüstri Mühendisliği **Tasarım Projesi** (bitirme projesinden ayrı)

## Amaç

Mevcut mini konveyör ve MES sistemini **iki istasyonla genişletmek**; MES'i ileride yeni istasyonların eklenmesini kolaylaştıracak şekilde geliştirmek; sistemin **AnyLogic ayrık olay simülasyonu** ve **Babylon.js dijital ikizi** ile birlikte çalışmasını sağlamak.

Bu belge **problemi ve beklenen sonuçları** açıklar. Yazılım mimarisi, fiziksel yerleşim, haberleşme yöntemleri, klasör düzeni, iş bölümü ve uygulama planı **proje ekibinin tasarım kararlarıdır**. Atölye ekibi ihtiyaç olduğunda danışmanlık ve tasarım incelemesi sağlar; projeyi öğrencilerin yerine geliştirmez.

## Mevcut ve hedeflenen üretim akışı

1. **Yeni İstasyon 1 – Giyotin/kesim:** Bant malzemelerinin istenen ebatlarda kesilmesi.
2. **Yeni İstasyon 2 – Manuel kaplama:** Kesilmiş bantların, renksiz kutuların bulunduğu tezgâhta operatör tarafından kutulara uygulanması.
3. **Mevcut hat:** Kaplanmış ürünün konveyörden geçerek mevcut **renk sensörü → robot kol/ayırma → paketleme** aşamalarını izlemesi.

Yeni istasyonlar mevcut hattın yerine geçmez, **onu besler**. Mevcut sistemin çalışan işlevlerinin korunması hedeflenir.

## İstenen sonuçlar

- **Fiziksel genişletme:** İki istasyonun tasarlanması, mevcut hatla uyumlu çalıştırılması ve güvenliğinin değerlendirilmesi.
- **Genişletilebilir MES:** Yeni istasyonların sisteme dâhil edilebildiği, üretim işlerinin ve istasyon bilgilerinin izlenebildiği bir yapı. İhtiyaca uygun operatör ekranları da bunun parçasıdır.
- **AnyLogic:** Yeni ve mevcut akışı temsil eden, farklı düzenlemelerin/parametrelerin sonuçlarını değerlendirmeye elverişli simülasyon.
- **Babylon.js:** Üretim sisteminin görsel dijital ikizi; hem gerçek MES verileri hem de AnyLogic simülasyon verileriyle çalışabilme.
- **Yeniden yapılandırma döngüsü:** AnyLogic'te değişiklik önerisini sınama → Babylon.js üzerinden davranışı gözlemleme → uygun bulunan değişikliği fiziksel hatta uygulama → dijital ikizi yeniden **gerçek sistem verisine** bağlama.

Simülasyondan gelen veri **gerçek ölçüm** olarak gösterilmemeli; simülasyonun fiziksel ekipmanı doğrudan kontrol etmesi varsayılmamalıdır. Bu ayrımın teknik çözümünü ekip tasarlar.

## Başlangıç kaynakları

- Kaynak repo: https://github.com/ertunga2004/MES
- Proje dalı: `at-zeze/pre-sql-two-station`
- Temel commit: `562e13bd46bacc4c4e1f8420a01c915dc20e6d37` (16 Mayıs 2026; SQL ve Docker geçişleri öncesi).
- MES'in aktif omurgası: `mes_web/` (FastAPI, web arayüzleri, MQTT/WebSocket, OEE, Excel tabanlı kayıt).
- İlgili mevcut donanım/yazılım: `CPP/`, `Giyotin_kontrol/`, `raspberry/` ve kök README.
- Kaplama paneli başlangıç çalışması: https://github.com/zeynepp36/kaplama-operator-paneli
- Daha önce hazırlanmış Babylon.js çalışmalarının **bulunduğu yer ve mevcut durum** ekip tarafından doğrulanacaktır; bu temel commit'te bulunduğu varsayılmamalıdır.

Bu kaynaklar zorunlu mimari veya değiştirilemez kod değildir. Ekip yeniden kullanma, uyarlama veya gerekçeli değiştirme kararı verebilir.

## İlk teslim: Ön inceleme + proje önerisi

**Kod geliştirmeden önce**, kısa ve anlaşılır bir çalışma sunulması beklenir:

1. **Mevcut durum ve ihtiyaçlar:** Erişilebilen parçalar, çalışan/eksik bileşenler, bilinmeyenler ve donanım ihtiyaçları.
2. **Ön tasarım:** Fiziksel süreç şeması ve MES–AnyLogic–Babylon.js bağlantısı için önerilen yaklaşım; önemli alternatiflerin kısa gerekçesi.
3. **Yürütme planı:** Zehra/Zeynep iş bölümü, dönem içindeki aşamalar, kontrol noktaları, riskler, doğrulama yöntemi ve tahmini bitiş.

Bu belgelerin dosya adlarını ve klasörlerini ekip belirleyebilir. İlk inceleme toplantısından sonra ekip uygulama çalışmalarına kendi planıyla devam eder.

## Projenin tamamlanma ölçütü

Dönem içinde **çalışan bir uçtan uca gösterim** hazırlanmalıdır: yeni iki istasyondan mevcut hatta uzanan üretim akışı, MES üzerinde izleme/operatör etkileşimi, AnyLogic senaryosunun Babylon.js'de gözlemlenmesi ve dijital ikizin gerçek sistem verisiyle yeniden çalışması. Mevcut konveyör özellikleri için regresyon kontrolü ve sınırlamalar açıkça raporlanır.

Bir **endüstri mühendisliği değerlendirmesi** de beklenir: örneğin istasyon kapasitesi, çevrim süresi, darboğaz veya ara stok gibi ölçütlerden uygun olanlarını ekip belirleyip simülasyondan sonuç çıkarır. Sadece görsel animasyon yeterli değildir.

## Kapsam ve danışmanlık sınırı

- Çalışma **tasarım projesidir**; genel amaçlı ticari “Super MES” geliştirilmesi hedeflenmez.
- SQL'e, Docker'a, belirli bir framework'e veya önceki prototiplerin aynen korunmasına geçiş **zorunlu değildir**. Böyle bir karar gerekçelendirilmeli ve değerlendirilmelidir.
- Fiziksel güvenlik, maliyet/bütçe, takvim veya temel kapsamı etkileyen kararlar uygulamadan önce atölyeye danışılmalıdır.
- **Tasarım, plan, kod, test ve raporların sorumluluğu öğrencilerdedir.** Atölye ekibi problemin sahibi, teknik danışman ve kabul incelemesini yapan taraftır.
