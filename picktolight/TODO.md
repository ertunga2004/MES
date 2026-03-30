# Yarin Yapilacaklar

1. Is resetleme butonu eklenecek.
   Python GUI tarafinda mevcut urunu sifirlayip ilk adima donduren bir kontrol olacak.
   Gerekirse MQTT uzerinden ESP32 veya harici buton icin de reset komutu tanimlanacak.

2. Itemlerin kutu numarasi GUI uzerinden degistirilebilir hale getirilecek.
   `products.json` icindeki montaj adimlarinin `box_number` alanlari arayuzden duzenlenebilecek.
   Degisiklikten sonra hem recete hem ERP snapshot aninda guncellenecek.

3. `Enter` ve `Space` kisayollari gelistirilecek.
   Eger secili bir yazi giris alani yoksa bu tuslar istasyon butonu gibi calisacak.
   Eger imlec bir `Entry` veya yazilabilir alan icindeyse normal tus davranisi korunacak.
