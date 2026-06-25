# BOM/BOP Source Payload Request Email

Konu: BOM/BOP kaynak payload ornegi talebi

Merhaba,

MESQL ortak veri modeli ve BOM/BOP v1 importer hazirligi icin kaynak sistemdeki ham BOM/BOP payload yapisini dogrulamamiz gerekiyor. Bu calismada amac, mevcut kaynak field adlarini, status/revision davranisini ve operasyon-istasyon/work center iliskisini netlestirmektir.

Lutfen mumkunse asagidaki kapsami iceren kucuk bir ornek paket paylasabilir misiniz?

- Product master ornegi
- Product revision/version ornegi
- Component/stok karti ornegi
- MBOM header ve line ornekleri
- BOP/route header ve operation ornekleri
- Operation-station veya operation-work center mapping ornegi
- Package BOM varsa header ve line ornegi
- Release status kodlari ve anlamlari
- Varsa validation/warning/error mesaj ornekleri

Kabul edilebilir formatlar:

- JSON export
- CSV veya XLSX export
- SQLite/PostgreSQL schema dump ve ornek satirlar
- Uygulama local DB ornegi

Onemli notlar:

- Kaynak field adlari lutfen degistirilmeden paylasilsin.
- Degerler maskelenebilir; ancak field adlari, status kodlari, revision kodlari ve iliski anahtarlari korunmalidir.
- Musteri adi, kullanici adi, fiyat, token, sifre, API key veya connection string paylasilmamalidir.
- Ayni urun/component farkli dosyalarda geciyorsa tutarli maskeli kod kullanilmasi yeterlidir.

Minimum senaryo olarak su ornekler yeterlidir:

- Uretime cikabilir bir release
- Uretime cikamayacak bir draft/review/pending veya benzeri durum
- Mumkunse operasyon mapping'i eksik bir ornek
- Varsa kaynak sistemin urettiği bir validation/warning/error ornegi

Paket icine kisa bir README eklenirse yeterlidir. README'de dosyalarin neyi temsil ettigi ve hangi status'un uretime yayinlanabilir oldugu belirtilmelidir.

Tesekkurler.
