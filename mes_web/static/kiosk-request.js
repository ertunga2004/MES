const messages = {
  KIOSK_INVALID_TEXT: "Metin alanlarının boş olmadığını ve uzunluk sınırlarına uyduğunu kontrol et.",
  KIOSK_INVALID_OPTIONS: "Her seçenek listesinde birbirinden farklı 2–12 satır olmalı.",
  KIOSK_INVALID_CARD: "Kart türünü ve veri kaynağını kontrol et.",
  KIOSK_INVALID_ADDRESS: "Adres için küçük harf, rakam ve kısa çizgi kullan.",
  KIOSK_DESIGN_LIMIT: "En fazla 30 adım ve 20 ek bölüm eklenebilir.",
  KIOSK_DRAFT_CHANGED: "Taslak başka bir ekranda değişti. Sayfayı yenileyip kaydedilen sürümü aç.",
  KIOSK_STEPS_REQUIRED: "Yayınlamak için en az bir adım ekle.",
  KIOSK_INVALID_STEP_VALUE: "Zorunlu adımları ve girilen değerleri kontrol et.",
  KIOSK_INVALID_RESULT: "İşin sonucunu seç.",
  KIOSK_START_CHANGED: "İş emri veya kiosk sürümü değişti. Güncel ekranı kontrol et.",
  KIOSK_RUN_ALREADY_OPEN: "Bu istasyonda zaten açık bir iş var.",
  KIOSK_RUN_CHANGED: "İstasyonun işi değişti. Güncel ekranı kontrol et.",
  KIOSK_INVALID_QUANTITY: "Geçerli bir miktar yaz.",
  KIOSK_WAITING_AREA_DISABLED: "Bu iş için tanımlı bir bekleme alanı seç.",
  KIOSK_WAITING_STEP_REQUIRED: "Beklemeye izin verilen adımı seç ve önceki zorunlu adımları tamamla.",
  KIOSK_WAITING_ITEM_CONFLICT: "Bu iş etiketi zaten bekliyor veya kayıt sınırına ulaşıldı.",
  KIOSK_WRITE_FAILED: "Sunucu kaydı yazamadı. Tekrar dene.",
};

export async function kioskRequest(path, method = "GET", payload) {
  const options = { method, cache: "no-store", signal: AbortSignal.timeout(10000) };
  if (payload !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Sunucuya ulaşılamadı. Bağlantıyı kontrol et.");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(messages[data.detail] || "İşlem tamamlanamadı. Alanları kontrol et.");
  return data;
}
