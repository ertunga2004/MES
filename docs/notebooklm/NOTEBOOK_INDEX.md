# NotebookLM Notebook Index

Bu belge, MES projesi icin kullanilan NotebookLM defterlerinin haritasidir. AI araclari bir soruda NotebookLM kullanacaksa once bu dosyayi okumali, sonra sorunun turune gore ilgili defteri secmelidir.

## Kullanim Kurali

1. Kod degisikligi, test veya runtime davranisi icin nihai kaynak repo dosyalari ve testlerdir.
2. NotebookLM, kaynakli proje hafizasi ve dokuman sentezi icin kullanilir; repo yerine gecmez.
3. Sorunun hangi deftere ait oldugu belirsizse once `MES Core / Mimari` defterinden genel baglam alinir.
4. NotebookLM cevabi kod degisikligine dayanak yapilacaksa ilgili repo dosyasi ayrica okunur.
5. Deftere eklenen dosyalar proje klasorunden kaldirilmaz; repo source of truth olarak kalir.

## MES Core / Mimari

Notebook URL:

- https://notebooklm.google.com/notebook/fa031655-2218-4cc9-9d60-37e6f3a99488

Icerik:

- `README.md`
- `docs/README.md`
- `docs/AI_GUIDE.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/mqtt-topics.md`
- `docs/tablet_plan.md`
- `docs/hardware.md`
- `docs/field-test-plan.md`
- `docs/archive/legacy_plans/roadmap.md` (arşivlendi; aktif referans için `docs/agent_memory/` kullanın)
- `mes_web/README.md`
- `raspberry/README.md`
- `picktolight/README.md`
- `Baslaticilar/README.md`

Ne zaman kullanilir:

- mimari kararlar
- OEE, availability, performance ve quality kurallari
- MQTT topic rolleri
- dashboard, kiosk ve teknisyen snapshot kontratlari
- Raspberry vision observer rolu
- saha test plani ve operasyon akisi
- genel proje baglami

Ornek sorular:

- "Bu projede OEE availability hesabinda planned stop, manual fault ve opening checklist nasil ele alinmali?"
- "Yeni kiosk davranisi eklerken hangi snapshot kontratlari korunmali?"
- "Raspberry vision katmani sorting karari verir mi, yoksa pasif capraz kontrol mudur?"

## FERP / Veri Entegrasyonu

Notebook URL:

- https://notebooklm.google.com/notebook/16982ce8-e36e-4d8b-a568-5e69b94de8b2

Icerik:

- `docs/FERP_INTEGRATION.md`
- `docs/FERP_JSON_CONTRACT.md`
- Excel dosyalarindan turetilmis Markdown/PDF label sozlukleri
- workbook schema ozetleri
- FERP label ve zorunlu alan dokumanlari

Not:

- `.xlsx` ve `.xls` dosyalari NotebookLM'e dogrudan eklenemeyebilir.
- Bu dosyalar icin tercih edilen kaynak, Excel'den turetilmis Markdown/PDF veri sozlugu ve ornek satir ozetidir.

Ne zaman kullanilir:

- FERP label eslesmeleri
- is emri import/export kararlari
- MES JSON alanlari
- workbook sheet anlamlari
- FERP'e gidecek uretim ve stok hareketi adaylari

Ornek sorular:

- "MES is emri JSON alanlari FERP label alanlariyla nasil eslesiyor?"
- "Robot kol tamamlamasindan sonra FERP'e hangi stok veya uretim hareketi aday olarak gitmeli?"
- "Workbook'taki hangi sheet FERP export icin kaynak kabul edilmeli?"

## MES Literatur ve Tez

Notebook URL:

- https://notebooklm.google.com/notebook/13a66b19-41e6-4770-8060-65387e91af68

Icerik:

- `docs/Tez/*.docx`
- bitirme raporu ve ara rapor taslaklari
- MES, OEE, ISA-95, ISA-88, Endustri 4.0, SCADA/MES entegrasyonu ve izlenebilirlik kaynaklari
- okul tez yazim kilavuzu veya akademik format dokumanlari

Ne zaman kullanilir:

- akademik rapor yazimi
- literatur ozeti
- standart aciklamasi
- projenin akademik gerekcelendirmesi
- tez bolumleri arasinda dil ve kapsam tutarliligi

Ornek sorular:

- "MES sistemlerinin ISA-95 baglamindaki rolunu kaynakli ozetle."
- "Bu proje icin OEE kavramini akademik rapor dilinde acikla."
- "Endustri 4.0 ve MES entegrasyonu icin literatur temelli giris metni hazirla."
