# MESQL ERP/BOM-BOP/MES Veri Alisveris Sozlesmesi

Bu dokuman MESQL ortak veri tabanina gecis oncesi sistemler arasi veri sinirini tanimlar. Kod, migration veya runtime davranisi degistirmez.

## 1. Sistem Rolleri

| Sistem | Rol | Kesin bilinen sinir | Acik / kararlastirilacak alan |
|---|---|---|---|
| ERP/F-ERP | Uretim emri otoritesi ve resmi stok/uretim hareketlerinin sahibi | F-ERP is emri importu label-first JSON ile temsil ediliyor. `mym4004`, `mym4008`, `mym4009`, `mym4104`, `mym4043`, `mym4086` uretim yonetimi kapsaminda. | ERP'ye gidecek hazirlik master datasinin nihai import mekanizmasi. |
| BOM/BOP Programi | Uretim hazirlik, MBOM ve BOP hazirlik otoritesi | Is nesnesi seviyesi belli: urun, komponent, MBOM, BOP, rota/operasyon, paket BOM, revizyon, release durumu. | BOM/BOP local DB semasi ve release JSON alan adlari. |
| MESQL Ortak DB / Backend | Ortak veri, dogrulama, operasyonel hafiza ve sistemler arasi veri siniri | MVP DB cekirdegi: `mes.work_orders`, `mes.station_queue`, `mes.work_order_events`, `mes.package_component_wip`. Operation/station mapping icin canonical kaynak MESQL manufacturing domainidir. Sonraki hazirlik: `mes.package_sessions`. | Backend API endpoint adlari ve shared schema DDL isimleri. |
| MES / Kiosk / Dashboard | Saha yurutme, operator akisi, kiosk ve dashboard gorunumu | Is emri durumlari, station queue, WIP, package session ve event log MES tarafinda uretilir. | ERP'ye aktarilacak OEE/kalite detay seviyesi. |

## 2. Ana Veri Akis Resmi

```text
BOM/BOP -> MESQL -> ERP -> MESQL -> MES -> MESQL -> ERP
```

Bu akis, uygulamalarin birbirlerinin local DB'lerine dogrudan baglanmamasini temel kabul alir. BOM/BOP ve MES farkli PC'lerde calisabilir; ortak iletisim siniri MESQL Backend API / MESQL ortak DB olmalidir.

## 3. Otorite Modeli

| Veri / karar alani | Otorite | Not |
|---|---|---|
| Uretim hazirlik, MBOM, BOP hazirlik | BOM/BOP | Ilk etapta ERP sifira yakin veya bos baslayabilir; hazirlik verisi BOM/BOP ve hazirlik programlarindan cikar. |
| Ortak veri, dogrulama, operasyonel hafiza | MESQL | MESQL hazirlik verisini toplar, dogrular, ERP'ye aktarir ve MES gerceklesmelerini toplar. |
| Operation/station mapping master data | MESQL manufacturing domain | BOM/BOP mapping'i MESQL'e release eder. MES bu mapping'i MESQL'den okur. `mes.station_queue` gunluk operasyonel siralamadir, master data otoritesi degildir. |
| Uretim emri | ERP/F-ERP | Uretim emrini ERP olusturur ve MESQL'e basar. |
| Saha yurutme ve gerceklesme | MES | MES, gunluk is emirlerini MESQL'den alir; istasyon bazli siralama ve gerceklesme kayitlarini MESQL'e yazar. |

## 4. BOM/BOP -> MESQL Veri Alisverisi

Bu fazda BOM/BOP verisi is nesnesi seviyesinde tanimlanir. BOM/BOP uygulamasinin nihai tablo veya JSON alan adlari kesinlesmemistir.

| Is nesnesi | MESQL'e tasinacak anlam | Durum |
|---|---|---|
| Urun kodu / adi | Uretilecek mamul veya yari mamul aday tanimi | Kesin is nesnesi |
| Komponent / parca kodu / adi | MBOM ve paket BOM satirlarinda tuketilecek parca aday tanimi | Kesin is nesnesi |
| MBOM | Parent urun ile komponent ihtiyacini baglayan hazirlik nesnesi | Kesin is nesnesi |
| BOP / rota | Urunun uretim adimlari ve rota bilgisi | Kesin is nesnesi |
| Operasyon sirasi | BOP icindeki sira bilgisi | Kesin is nesnesi |
| Operasyon-istasyon eslesmesi | MES yurutmede hangi operasyonun hangi istasyon/is merkezinde yapilacagi | Kesin is nesnesi, dogrulama kuralina bagli |
| Paket BOM | Paket urunu ve komponent ihtiyaclari | Kesin is nesnesi |
| Revizyon / versiyon | Ayni urunun farkli hazirlik setlerini ayirmak icin kullanilir | Kararlastirilacak detay |
| Release / onay durumu | MES'e ve ERP'ye gidebilir veri ile taslak/veri hatali paketi ayirir | Deger listesi kapandi: sadece `RELEASED` veri ERP/MES'e gider |

Release status karar listesi:

| Status | Anlam | ERP/MES'e gider mi? |
|---|---|---|
| `DRAFT` | Taslak hazirlik | Hayir |
| `IN_REVIEW` | Incelemede | Hayir |
| `APPROVED` | Onaylandi ama uretime release edilmedi | Hayir |
| `RELEASED` | Uretime acik nihai release | Evet |
| `ARCHIVED` | Eski veya kapatilmis release | Hayir |
| `REJECTED` | Reddedildi | Hayir |
| `PENDING` | Staging/import bekleyen durum | Hayir |

## 5. MESQL -> ERP/F-ERP Uretim Hazirlik Aktarimi

Kaynak dokumanlarda bilinen F-ERP label alanlari disinda label uydurulmaz. MESQL, BOM/BOP release verisinden ERP icin stok karti, is merkezi/operasyon ve sure adaylari uretebilir.

| Hazirlik anlami | Bilinen F-ERP label | Not |
|---|---|---|
| Stok / urun kodu | `lblMTM00_CODE` | Urun veya stok kodu |
| Stok / urun adi | `lblMTM00_NAME` | Operator ve ERP gorunumu icin ad |
| Stok tipi | `lblMTMT0_CODE` | Mamul, yari mamul vb. |
| Birim | `lblMUNT0_CODE` | Ornek: ADET / AD |
| Lot kodu | `lblMTML0_CODE` | Bazi is emri tiplerinde var |
| Parti no | `lblMTML0_PRTY_NO` | Tamirat vb. bloklarda var |
| Is merkezi | `lblMFW00_CODE` | OEE / operasyon kirilimi |
| Operasyon | `lblMFWO0_CODE` | Operasyon kodu |
| Hazirlik suresi | `lblMMFB4_SETUP_TIME` | Kaynakta saniye olarak kullaniliyor |
| Ideal dongu / islem suresi | `lblMMFB4_TIME` | Is emri bazli ideal cycle |

Component master icin de ayni bilinen stok label ailesi kullanilabilir: `lblMTM00_CODE`, `lblMTM00_NAME`, `lblMTMT0_CODE`, `lblMUNT0_CODE`. Component'e ozel bilinmeyen F-ERP label uydurulmaz.

ERP'de stok karti zaten varsa sessiz overwrite yapilmaz:

| Durum | Karar |
|---|---|
| `lblMTM00_CODE` ERP'de yok | Create candidate |
| Kod var, ad/tip/birim uyumlu | Map/skip |
| Kod var, ad/tip/birim celiskili | Conflict report / manual review |
| Revizyon farki var | Revision review |

Acik: ERP'ye hazirlik aktariminin nihai mekanizmasi henuz sabit degildir. Olasi yollar manuel ERP girisi, Excel import, label-first JSON veya REST/API entegrasyonudur. Bu konu Faz 2 icin planning block'tur; servis/entegrasyon katmanini bloklar, ortak DB taslak semasini bloklamaz.

## 6. ERP/F-ERP -> MESQL Uretim Emri Aktarimi

F-ERP is emri aktarimi label-first JSON kontratiyla ilerler. Public import payload `ferp_object`, `ferp_screen` ve `ferp_labels` tasir; MES runtime icinde bu bilgiler normalize alanlara cevrilir.

| JSON parcasi / label | Anlam | Durum |
|---|---|---|
| `ferp_object` | F-ERP object kodu, ornek `mym4004` | Kesin kontrat parcasi |
| `ferp_screen` | F-ERP ekran adi, ornek Is Emirleri | Kesin kontrat parcasi |
| `ferp_labels` | Label-first alan sozlugu | Kesin kontrat parcasi |
| `lblMMFB0_NUMBER` | Sistem No / is emri id | Bilinen label |
| `lblMMFB0_DATE` | Is emri tarihi | Bilinen label |
| `lblMMFB0_QTY` | Hedef miktar | Bilinen label |
| `lblMTM00_CODE` | Stok kodu | Bilinen label |
| `lblMTM00_NAME` | Stok adi | Bilinen label |
| `lblMUNT0_CODE` | Birim | Bilinen label |
| `lblMFW00_CODE` | Is merkezi | Bilinen label |
| `lblMFWO0_CODE` | Operasyon | Bilinen label |
| `lblMMFB4_TIME` | Sure / ideal cycle | Bilinen label |

Ornek iskelet:

```json
{
  "orders": [
    {
      "ferp_object": "mym4004",
      "ferp_screen": "Is Emirleri",
      "ferp_labels": {
        "lblMMFB0_NUMBER": "",
        "lblMMFB0_DATE": "",
        "lblMMFB0_QTY": 0,
        "lblMTM00_CODE": "",
        "lblMTM00_NAME": "",
        "lblMUNT0_CODE": "",
        "lblMFW00_CODE": "",
        "lblMFWO0_CODE": "",
        "lblMMFB4_TIME": 0
      }
    }
  ],
  "replace_existing": true
}
```

## 7. MESQL -> MES Yurutme Verileri

| Veri | MES tarafindaki kullanim | Kaynak / durum |
|---|---|---|
| Gunluk is emirleri | Kiosk ve dashboard is emri listesi | ERP -> MESQL importundan gelir |
| `station_queue` | Istasyon bazli gunluk sira ve aktif/pending projeksiyonu | `mes.station_queue` MVP DB cekirdeginde; master data otoritesi degildir |
| Urun / stok bilgisi | Operator ekraninda urun tanimi ve is emri baglami | F-ERP label importu ve BOM/BOP hazirlik verisi |
| Operasyon / BOP bilgisi | Hangi is adiminin hangi sira ile yurutulecegi | Sadece `RELEASED` ve mapping'i tamam olan veri MES'e dagitilir |
| Paket BOM | Paketleme komponent uygunlugu | BOM/BOP release ve MESQL dogrulamasina bagli |
| WIP uygunlugu | Paketleme komponent reserve/consume kontrolu | `mes.package_component_wip` MVP DB cekirdeginde |
| Aktif / pending is durumu | Kiosk is akisi ve onay bekleyen durumlar | `mes.work_orders`, `mes.work_order_events`, runtime fallback |

## 8. MES -> MESQL Gerceklesme Verileri

MES sahada olusan hareketleri MESQL'e yazar. Mevcut MVP kaynaklarina gore temel cekirdek `mes.work_order_events` ve current-state icin `mes.work_orders` / `mes.station_queue` siniridir.

| Gerceklesme | MESQL'e yazilan anlam |
|---|---|
| Is emri basladi | Start transition ve aktif is durumu |
| Is emri bitti | Finish transition, tamamlanma bilgisi |
| Onayla / kapat | Operator onayi ve F-ERP export adayi |
| Iptal | Cancel transition ve event log |
| Station reorder | Istasyon sira degisikligi |
| Uretim tamamlamasi | Completion hook / tamamlanan urun izi |
| WIP uretim / tuketim | Paket komponent uygunluk, reserve, consume ve reset kontrolu |
| Package session start / finish | `mes.package_sessions` hazirlik kapsaminda; event payload icinde de izlenebilir |
| Event log | `mes.work_order_events` |
| GOOD / REWORK / SCRAP kalite dagilimi | F-ERP export kalite ozetine kaynak |

## 9. MESQL -> ERP/F-ERP Gerceklesme Export'u

F-ERP export semasi kaynak sozlesmeye gore `ferp_mes_export.v1` olarak kalir.

| Export parcasi | Anlam |
|---|---|
| `schema` | `ferp_mes_export.v1` |
| `work_order` | Kapanan is emrinin F-ERP object/screen/label baglami |
| `station_flow` | Istasyon akisi ve ara hareket ozetleri |
| `ferp_documents` | F-ERP belge/hareket adaylari |
| `quality_summary` | GOOD / REWORK / SCRAP / TOTAL dagilimi |
| `warnings` | Eksik label, miktar belirsizligi veya export uyarilari |

## 10. F-ERP Belge/Hareket Adaylari

| Akis | F-ERP blok | Nesne | Not |
|---|---|---|---|
| Hammadde cikisi | Cikis Hareketleri | `mym2010` | Is emri icin tuketilen malzeme adayi |
| Mamul / yari mamul girisi | Giris Hareketleri | `mym2008` | Tamamlanan veya ara uretim giris adayi |
| Depo / lokasyon transferi | Onayli Depo Transferleri | `mym2056` | WIP / yari mamul depo-lokasyon ayrimi gerekiyorsa |

## 11. Kalite/OEE Ayrimi

| Sinif | ERP/F-ERP etkisi | MESQL/BI etkisi |
|---|---|---|
| GOOD | ERP mamul girisine gider | Kalite ozetinde GOOD sayilir |
| REWORK | Ayri rework / yari mamul satirina gider | Rework takibi MESQL/BI tarafinda detaylanir |
| SCRAP | Fire / hurda satirina gider | Hurda/fire analizi MESQL/BI tarafinda detaylanir |
| Anlik OEE / durus / makine alarmi | Ilk etapta ERP'ye gitmez | MESQL/BI tarafinda kalir |

## 12. Dort Sistemli Veri Nesnesi Matrisi

| Veri nesnesi | BOM/BOP | MESQL | ERP/F-ERP | MES |
|---|---|---|---|---|
| Urun master adayi | Hazirlar | Toplar, dogrular, aktarir | Stok/urun karti olarak kullanir | Is emri baglaminda okur |
| Komponent master adayi | Hazirlar | Toplar, dogrular, aktarir | Stok/komponent karti olarak kullanir | WIP/paketleme baglaminda okur |
| MBOM | Hazirlar | Release ve validation siniri | MRP/hazirlik icin kullanir | Tuketim/WIP baglaminda okur |
| BOP / rota | Hazirlar | Release ve validation siniri | Metod/rota hazirligi icin kullanir | Yurutme sirasi olarak okur |
| Operasyon-istasyon eslesmesi | Hazirlar | MES'e dagitim oncesi dogrular | Is merkezi/operasyon baglami | Station queue ve kiosk akisi |
| Paket BOM | Hazirlar | WIP/paketleme icin dogrular | Gerekirse stok/uretim hazirligi | Paket komponent kontrolu |
| Uretim emri | Okumaz / dogrudan yazmaz | ERP'den alir, MES'e verir | Olusturur | Yurutur |
| Station queue | Yazmaz | `mes.station_queue` | Yazmaz | Siralar ve gunceller |
| Work order event | Yazmaz | `mes.work_order_events` | Export ile ozet alir | Uretir |
| Kalite ozeti | Yazmaz | Export ozetine hazirlar | GOOD/REWORK/SCRAP hareket adayi alir | Sahada uretir |
| OEE / durus detayi | Yazmaz | MESQL/BI tarafinda tutar | Ilk etapta almaz | Sahada uretir |

## 13. Minimum Entegrasyon Fazlari

| Faz | Akis | Hedef |
|---|---|---|
| Faz 1 | BOM/BOP -> MESQL | Uretim hazirlik verisini MESQL'e release etmek |
| Faz 2 | MESQL -> ERP | Hazirlik verisini ERP'ye stok/MBOM/rota/metod adayi olarak aktarmak. Nihai mekanizma acik oldugu icin planning block. |
| Faz 3 | ERP -> MESQL | ERP uretim emirlerini label-first JSON ile MESQL'e almak |
| Faz 4 | MESQL -> MES | Gunluk is emri, station queue, BOP ve WIP bilgisini MES'e dagitmak |
| Faz 5 | MES -> MESQL | Gerceklesme, event, WIP, package session ve kalite ozetini toplamak |
| Faz 6 | MESQL -> ERP | `ferp_mes_export.v1` ile gerceklesme/stok hareket adaylarini ERP'ye aktarmak |

## 14. Yapilmayacak Dogrudan Baglantilar

| Baglanti | Karar |
|---|---|
| BOM/BOP -> MES dogrudan | Yok |
| MES -> BOM/BOP local DB dogrudan | Yok |
| MES -> ERP dogrudan yazma | Yok |
| ERP -> MES runtime state dogrudan yazma | Yok |

## 15. Acik Kalan Alanlar

| Alan | Durum | Bagimlilik / blokaj |
|---|---|---|
| BOM/BOP nihai release JSON / tablo formati | Acik | Production importer yazimini bloklar |
| MESQL Backend API endpointlerinin nihai isimleri | Acik | API servis katmani ve client entegrasyonunu bloklar |
| MESQL -> ERP hazirlik aktarim mekanizmasi | Acik / Faz 2 planning block | ERP hazirlik servis entegrasyonunu bloklar; ortak DB taslak semasini bloklamaz |
| ERP'ye kalite/OEE detay seviyesinin sonraki faz karari | Kararlastirilacak | ERP gerceklesme export kapsam genisletmesini bloklar |
| F-ERP stok hareket quantity label eksikligi / qty warning konusu | Acik; kaynak sozlesmede `qty` ve warning ile tasindigi belirtiliyor | Resmi stok hareket import kesinlestirmesini bloklar |
| BOM/BOP release validation kurallarinin detay sozlugu | Kismi kapandi | DDL/test yaziminda ayrintili hata kodlari ve WARN/FAIL sozlugu gerekir |
