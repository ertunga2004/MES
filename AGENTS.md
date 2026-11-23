# Codex Global Kullanim Kurallari

## 1. Genel Davranis

- Bu dosya global Codex kullanim kurallaridir.
- Bu kurallar tum Codex sohbetleri ve tum projeler icin varsayilan davranis standardidir.
- Proje klasorlerinde ayrica AGENTS.md varsa, proje ozel kurallar bu global kurallari tamamlar.
- Kullanicinin acik talimati global kurallardan once gelir.
- Belirsizlik varsa varsayim yapma; kisa ve net sekilde belirt.
- Gereksiz uzun aciklama yapma.
- Kullanici "codex planini duzenle", "prompt olustur", "bunu Codex'e verilecek hale getir" derse yalin, dogrudan kopyalanabilir duz metin uret.
- Gereksiz emoji kullanma.
- Komut, kurulum ve tasima islerinde once mevcut durum kontrolu, sonra islem, sonra dogrulama ver.
- Kalici etkili islem yapmadan once kullanicidan acik onay al.

## 2. Sistem Temizligi ve Kurulum Kurallari

- Sistemi gereksiz global kurulumlarla kirletme.
- Once mevcut araclari, PATH durumunu ve proje-local secenekleri kontrol et.
- Mumkunse proje-local kurulum kullan:
  - Python icin `.venv`
  - Node icin proje ici `node_modules`
  - CAD/Text-to-CAD icin repo-local runtime
- Gereksiz global npm paketi, Python paketi, servis, Docker imaji veya sistem araci kurma.
- Yeni arac kurulacaksa:
  1. Neden gerekli oldugunu acikla.
  2. Alternatif daha temiz yol var mi kontrol et.
  3. Kurulumdan once kullanicidan onay al.
  4. Kurulumdan sonra dogrulama komutu calistir.
  5. Kaldirma/geri alma yolunu belirt.
- Windows ortaminda PowerShell kullan.
- PowerShell'de npm icin gerekirse `npm.cmd`, npx icin gerekirse `npx.cmd` kullan.
- PlatformIO icin `pio` gorunmuyorsa `python -m platformio` kullan.
- Python projelerinde dogrudan global pip kullanma; once `.venv` olustur.
- Transfer/yedek klasorlerinde build, install, `.venv`, `node_modules`, `.pio`, `dist`, `build`, log veya cache uretme.

## 3. Guvenlik Kurallari

- Token, API key, sifre, Google hesabi, GitHub hesabi, kisisel dosya veya gizli veri isteyen islemlerde kullanicidan acik izin almadan devam etme.
- Token'i duz metin config dosyasina yazma.
- Commit, push, issue acma, PR acma, branch silme, dosya silme, upload veya donanim yazma islemi yapmadan once kullanicidan acik onay al.
- GitHub MCP varsayilan olarak read-only kabul edilir.
- Google/NotebookLM login islemlerinde ana hesap yerine mumkunse proje/arastirma hesabi oner.
- Kisisel Drive, Mail, Fotograflar veya ozel belgelere erismeye calisma.
- MCP ciktisini kesin dogru kabul etme; onemli kararlari kaynak, test veya kullanici onayi ile dogrula.
- Guvenlik, standart, kalite, mevzuat, finans veya teknik mimari kararlarinda kaynak dayanagi yoksa bunu acikca belirt.

## 4. MCP Kullanim Karar Agaci

### 4.1 NotebookLM MCP

NotebookLM MCP su durumlarda onceliklidir:

- Kullanici NotebookLM, kaynak, PDF, rapor, standart dokuman veya literatur tabani uzerinden calisma istiyorsa.
- MES, OEE, ERP/FERP, AS9100, ISO 9001, EYDEP, kalite yonetimi, akademik fizibilite, literatur ozeti veya proje raporu hazirlaniyorsa.
- Kullanici "kaynaklara gore", "NotebookLM'ye gore", "rapor kaynaklarini incele", "fizibilite hazirla", "Notebook'taki belgeleri kullan" gibi ifadeler kullaniyorsa.

Kurallar:

- NotebookLM'de kaynak/notebook yoksa kullanicidan notebook veya share link iste.
- Kaynakta acikca bulunmayan bilgiyi varsayim olarak isaretle.
- NotebookLM cevabini dogrudan kopyalama; kisa ozet, kaynak dayanagi, belirsizlikler ve uygulanabilir sonuc olarak isle.
- Ana Google hesabi veya kisisel Drive/Mail verilerine erismeye calisma.
- NotebookLM daha cok kontrollu kaynak tabani ve rapor/fizibilite icin kullanilmalidir.
- Guncel kutuphane API'si gerekiyorsa NotebookLM yerine Context7 kullan.

### 4.2 Context7 MCP

Context7 su durumlarda kullanilmalidir:

- Guncel kutuphane, framework veya API dokumantasyonu gerekiyorsa.
- FastAPI, React, Vite, PlatformIO, MQTT, SQLAlchemy, TanStack Query, Tailwind veya benzeri teknolojilerde guncel kullanim kontrol edilecekse.
- Kod yazarken API imzasi, deprecated ozellik, guncel ornek veya dogru import yapisi belirsizse.

Kurallar:

- Kod uretmeden once ilgili API'nin guncel kullanimini dogrula.
- Context7'den gelen dokumantasyonu kisa teknik ozet olarak kullan.
- Context7 erisimi basarisizsa bunu acikca belirt ve uydurma API uretme.
- Resmi dokumanla desteklenmeyen kritik kod kararlarini kesin hukum gibi sunma.

### 4.3 Google AI Mode MCP

Google AI Mode su durumlarda kullanilmalidir:

- Guncel web arastirmasi gerekiyorsa.
- Benzer projeler, teknoloji trendleri, topluluk pratikleri, urun/arac karsilastirmasi veya "su anda topluluk ne kullaniyor?" turu sorular varsa.
- NotebookLM'de kaynak yoksa ve konu guncel dis kaynak arastirmasi gerektiriyorsa.

Kurallar:

- Google AI Mode kesif ve on arastirma aracidir; final kaynak otoritesi degildir.
- Kaynak kalitesi heterojen olabilir: blog, LinkedIn, YouTube, GitHub, forum veya ikincil kaynaklar gelebilir.
- Kaynak/citation extraction zayifsa bunu raporda acikca belirt.
- Resmi dokuman, akademik kaynak ve birincil kaynaklari ikincil bloglardan ayir.
- Kritik teknik karar, akademik rapor, standart yorumu veya resmi dokumantasyon gerektiren konularda Google AI Mode sonucunu tek basina yeterli kabul etme.
- Gerekirse sonucu NotebookLM, Context7, GitHub MCP veya resmi kaynaklarla dogrula.

### 4.4 GitHub MCP

GitHub MCP su durumlarda kullanilmalidir:

- GitHub reposu, README, klasor yapisi, commit, branch veya proje yapisi okunacaksa.
- Kullanici GitHub'daki bir repo/link hakkinda analiz istiyorsa.
- Mevcut repo yapisi hakkinda read-only inceleme yapilacaksa.

Kurallar:

- Varsayilan mod read-only'dir.
- Issue, PR, commit, push, branch silme, dosya degistirme veya write islemi yapma.
- Write gerektiren bir is varsa once kullanicidan acik onay al.
- Token isteme veya config'e token yazma.
- GitHub'dan okunan bilgi yerel repo icerigiyle celisirse celiski olarak bildir.
- Repo analizi yaparken once README, klasor yapisi, package/requirements/config dosyalari ve test yapisini incele.

### 4.5 Sequential Thinking MCP

Sequential Thinking su durumlarda kullanilmalidir:

- Karmasik planlama, risk siralamasi, migration plani, cok adimli kurulum, hata ayiklama veya kontrol listesi gerekiyorsa.
- Karar agaci, onceliklendirme veya "once ne yapmaliyim?" turu sureclerde kullanilabilir.
- Birden fazla teknoloji, dosya, bagimlilik veya risk iceren isler varsa kullanilabilir.

Kurallar:

- Her kucuk is icin kullanma.
- Ciktiyi kisa ve uygulanabilir kontrol listesine donustur.
- Kullanici yalin cikti istiyorsa uzun muhakeme dokme.
- Planlari "on kontrol -> islem -> dogrulama -> geri alma" formatinda duzenle.

## 5. Text-to-CAD Skill Kullanimi

Text-to-CAD MCP degildir; Codex skill olarak kullanilir.

Su durumlarda kullanilmalidir:

- Mekanik aparat, braket, sensor tutucu, servo montaj aparati, Arduino/ESP32 kutusu, robotik parca veya basit CAD modeli istenirse.
- STEP, STL, GLB, DXF, URDF, SDF, SRDF gibi CAD/robotik cikti gerekiyorsa.
- Kullanici "text-to-cad", "cad", "stl", "step", "braket", "sensor tutucu", "montaj aparati", "robot parcasi", "3D baski" gibi ifadeler kullanirsa.

Kurallar:

- Once parcanin amaci, baglanti noktalari, yaklasik olculer ve uretim yontemi netlestir.
- Kullanici olcu vermediyse makul varsayimlari acikca belirt.
- Ana proje dosyalarini degistirme.
- CAD ciktilari ayri demo/output klasorune alinsin.
- Uretim oncesi modeli `inspect` ile kontrol et.
- STEP/STL gibi ciktilari uretmeden once dosya yollarini acikca belirt.
- Kesme, lazer, 3D baski veya montaj toleransi gerekiyorsa ayrica belirt.
- CAD Explorer veya local server acik kaldiysa test bitince kapatilmasini hatirlat.

## Text-to-CAD / CAD Explorer Windows Notlari

- Text-to-CAD MCP degildir; Codex skill olarak kullanilir.
- CAD uretimi icin `cad`, `cad-explorer`, `step-parts`, `urdf`, `sdf`, `srdf`, `sendcutsend` skill'leri kullanilabilir.
- Ana proje dosyalarina dogrudan CAD ciktisi yazma; ciktilari ayri workspace/demo/output klasorune al.
- CAD ciktisi uretildikten sonra en azindan su dogrulamalari yap:
  - STEP/STL dosyasi olustu mu?
  - `inspect refs --facts --planes --positioning` gecti mi?
  - Bounding box, faces, solids/shapes ve major planes mantikli mi?

### CAD Explorer Calistirma Notu

Windows ortaminda CAD Explorer icin iki farkli kopya olabilir:

1. Skill kopyasi:
   C:\Users\ertun\.codex\skills\cad-explorer\scripts\explorer

2. Repo-local dogru kopya:
   C:\Users\ertun\Documents\.CODE\tools\text-to-cad\skills\cad-explorer\scripts\explorer

Oncelik:

- CAD Explorer baslatilirken repo-local kopya tercih edilmelidir:
  C:\Users\ertun\Documents\.CODE\tools\text-to-cad\skills\cad-explorer\scripts\explorer

Neden:

- `.codex\skills\cad-explorer\scripts\explorer` altinda `package.json` olabilir ama `node_modules` olmayabilir.
- Bu durumda `Cannot find module 'vite/package.json'` hatasi olusabilir.
- Global `npm install` yapma.
- Gerekirse yalniz ilgili repo-local explorer klasorunde dependency kontrolu yap.
- Repo-local text-to-cad kopyasinda `node_modules` ve `vite` varsa onu kullan.

### Sandbox / Vite Notu

- CAD Explorer Vite ile baslarken sandbox icinde `Access is denied` hatasi verebilir.
- Bu durumda global kurulum yapma.
- Repo-local CAD Explorer'i sandbox disinda baslatmayi dene.
- Modeli acmak icin local URL uret:
  - STEP ornegi: http://127.0.0.1:4179/?file=<model.step>
  - STL ornegi: http://127.0.0.1:4179/?file=<model.stl>
- Dogrulama icin su endpointleri kontrol et:
  - http://127.0.0.1:4179/__cad/server
  - http://127.0.0.1:4179/__cad/catalog

### CAD Explorer Komut Prensibi

- Once dosya yollarini dogrula.
- Sonra repo-local explorer uzerinden `npm.cmd run dev:ensure` kullan.
- PowerShell'de npm icin `npm.cmd` kullan.
- Port cakismasi varsa yeni port sec.
- Basarili olursa kullaniciya acilacak local URL'yi ver.
- Basarisiz olursa net hata nedenini raporla.

### Alternatif Goruntuleyiciler

CAD Explorer calismazsa:

- STEP/STL icin FreeCAD oner.
- STEP icin CAD Assistant oner.
- STL icin MeshLab veya Windows 3D Viewer oner.

### Kapatma Notu

- CAD Explorer local server acik kaldiysa test bitince kapatilmasi gerektigini kullaniciya hatirlat.
- Gereksiz arka plan Node/Vite sureci birakma.

## 6. Kaynak Onceligi

- Standart, kalite, akademik, proje kaynagi: once NotebookLM.
- Guncel kod API'si ve framework dokumani: once Context7.
- Genel guncel web arastirmasi ve trend: Google AI Mode.
- Repo okuma ve GitHub proje analizi: GitHub MCP.
- Riskli veya cok adimli planlama: Sequential Thinking.
- Mekanik/CAD/robotik cikti: Text-to-CAD skill.

## 7. MES Projesi Icin Global Baglam

Kullanicinin ana gelistirme yonu:

- Backend: Python FastAPI
- Frontend: React
- MES/OEE/ERP-FERP prototipi
- MQTT/IoT/konveyor/renk sensoru/robot kol/AGV/teknisyen ekrani/kiosk ekrani
- Node-RED'den web tabanli MES_web mimarisine gecis

MES ile ilgili onerilerde:

- Node-RED yerine web tabanli MES_web mimarisi oncelikli dusun.
- Backend FastAPI, frontend React kabuluyle ilerle.
- OEE, is emri, stok hareketi, kalite kaydi, ariza/teknisyen cagrisi ve ERP/FERP entegrasyonlarini kavramsal butunluk icinde ele al.
- Gereksiz enterprise karmasikligi ekleme.
- Akademik/prototip seviyesinde gosterilebilir, surdurulebilir ve gelistirilebilir yapi oner.
- Donanim/IoT entegrasyonunda MQTT, seri haberlesme, ESP32/Mega/PlatformIO ve sensor akisini dikkate al.
- Kritik mimari kararlar icin once kaynak ve mevcut proje yapisini kontrol et.

## 8. Cevap ve Plan Formati

Kurulum, tasima, debug veya proje plani verirken su formati tercih et:

1. Mevcut durum
2. Risk
3. Yapilacak islem
4. Komutlar
5. Dogrulama
6. Geri alma veya sonraki adim

Kullanici kopyalanabilir prompt istiyorsa:

- Sadece promptu ver.
- Gereksiz aciklama ekleme.
- Markdown karmasasini minimum tut.
- Gerekirse duz text ver.

Kullanici hizli karar istiyorsa:

- Net oneri ver.
- Alternatifleri kisa karsilastir.
- Belirsizligi acikca belirt.

## 9. Yasak veya Onay Gerektiren Isler

Asagidakileri acik kullanici onayi olmadan yapma:

- Commit
- Push
- PR acma
- Issue acma
- Branch silme
- Dosya silme
- Kalici sistem ayari degistirme
- Global paket kurma
- Docker kurma
- Servis kurma
- Upload/firmware yazma
- Donanima yazilim basma
- Token/API key yazma
- Hesap login islemini tamamlama
- Kisisel dosya, mail, Drive veya ozel veri erisimi

## 10. Dogrulama

Bu dosya guncellendikten sonra:

- Dosya yolunu raporla.
- Yedek dosya yolunu raporla.
- Eklenen ana basliklari listele.
- Codex Windows App'i kapatip yeniden acmam gerektigini belirt.
- Yeni bir sohbette bu kurallari test etmek icin kisa test promptu oner.
