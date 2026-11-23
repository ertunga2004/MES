const form = document.getElementById("coating-form");
const operator = document.getElementById("operator");
const quantity = document.getElementById("quantity");
const save = document.getElementById("save");
const order = document.getElementById("order");
const count = document.getElementById("count");
const meter = document.getElementById("progress");
const statusText = document.getElementById("order-status");
const notice = document.getElementById("notice");
const pendingKey = "mes-manual-coating-pending";
const api = "/api/manual-coating";

let progress = null;
let pending = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
let busy = false;
let writeGeneration = 0;
if (pending) {
  operator.value = pending.operator;
  quantity.value = pending.quantity;
  notice.textContent = "Önceki kaydın sonucu bekleniyor. Aynı kaydı yeniden dene.";
}

function render() {
  order.textContent = progress?.order_id || "Aktif iş emri yok";
  count.textContent = progress?.unit_supported ? `${progress.completed_qty} / ${progress.target_qty}` : "–";
  meter.max = progress?.unit_supported ? progress.target_qty || 1 : 1;
  meter.value = progress?.unit_supported ? progress.completed_qty : 0;
  if (progress && !progress.unit_supported) statusText.textContent = "Bu istasyon yalnızca adet birimli iş emirlerini kaydeder.";
  else if (progress?.awaiting_handoff) statusText.textContent = "Kaplama hedefi tamamlandı. Hat teslimi bekleniyor.";
  else if (progress?.complete) statusText.textContent = "Kaplama hedefi tamamlandı.";
  else if (progress?.can_record) statusText.textContent = `${progress.remaining_qty} parça daha kaplanacak.`;
  else statusText.textContent = "Yeni kaplama kaydı beklemede.";
  operator.readOnly = quantity.readOnly = Boolean(pending) || busy;
  if (pending || !progress?.can_record) quantity.removeAttribute("max");
  else quantity.max = progress.remaining_qty;
  save.disabled = busy || !(pending || progress?.can_record);
  save.textContent = busy ? "Kaydediliyor…" : pending ? "Aynı kaydı yeniden dene" : "Kaplamayı kaydet";
}

async function refresh() {
  if (busy) return;
  const generation = writeGeneration;
  try {
    const response = await fetch(api, { cache: "no-store", signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error("Bağlantı kurulamadı.");
    const data = await response.json();
    if (generation === writeGeneration) {
      progress = data.progress;
      render();
    }
  } catch {
    if (generation === writeGeneration) {
      progress = null;
      render();
      statusText.textContent = "Sunucuya ulaşılamıyor.";
    }
  }
}

function clearPending() {
  sessionStorage.removeItem(pendingKey);
  pending = null;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy || !(pending || progress?.can_record)) return;
  if (!pending) {
    const name = operator.value.trim();
    if (!name) {
      notice.textContent = "Operatör adını gir.";
      operator.focus();
      return;
    }
    pending = {
      request_id: crypto.randomUUID(), order_id: progress.order_id,
      order_key: progress.order_key, operator: name, quantity: quantity.valueAsNumber,
    };
    sessionStorage.setItem(pendingKey, JSON.stringify(pending));
  }
  busy = true;
  writeGeneration += 1;
  render();
  try {
    const response = await fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pending),
      signal: AbortSignal.timeout(10000),
    });
    const data = await response.json();
    if (response.ok) {
      progress = data.progress;
      clearPending();
      quantity.value = "";
      notice.textContent = data.duplicate ? "Bu kaplama kaydı daha önce alındı." : "Kaplama kaydedildi.";
    } else if (response.status < 500) {
      clearPending();
      progress = null;
      const errors = {
        COATING_ORDER_CHANGED: "Aktif iş emri değişti. Yeni emri kontrol et.",
        COATING_QUANTITY_UNAVAILABLE: "Adet kalan hedefi aşıyor veya iş emri kayda kapalı.",
        COATING_REQUEST_CONFLICT: "Bu kayıt numarası daha önce başka bir işlemde kullanılmış.",
      };
      notice.textContent = errors[data.detail] || "Kayıt reddedildi. Bilgileri kontrol et.";
    } else {
      throw new Error("Kayıt doğrulanamadı.");
    }
  } catch {
    notice.textContent = "Kayıt doğrulanamadı. Aynı kaydı yeniden deneyebilirsin.";
  } finally {
    busy = false;
    render();
    refresh();
  }
});

render();
refresh();
setInterval(refresh, 5000);
