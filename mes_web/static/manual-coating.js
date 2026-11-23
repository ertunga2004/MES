const form = document.getElementById("coating-form");
const operator = document.getElementById("operator");
const quantity = document.getElementById("quantity");
const quantityField = document.getElementById("quantity-field");
const lotInput = document.getElementById("lot-id");
const lotField = document.getElementById("lot-field");
const waitingLotText = document.getElementById("waiting-lot");
const save = document.getElementById("save");
const withdraw = document.getElementById("withdraw");
const order = document.getElementById("order");
const count = document.getElementById("count");
const meter = document.getElementById("progress");
const statusText = document.getElementById("order-status");
const notice = document.getElementById("notice");
const isCutting = window.location.pathname === "/giyotin";
const pendingKey = isCutting ? "mes-cutting-pending" : "mes-manual-coating-pending";
const api = "/api/manual-coating";
const cuttingApi = "/api/cutting-workflow";

if (isCutting) {
  document.title = "Giyotin · MES";
  document.getElementById("station-title").textContent = "Giyotin";
  document.getElementById("quantity-label").textContent = "Kesilen parça adedi";
  meter.setAttribute("aria-label", "Kesim ilerlemesi");
}

let progress = null;
let wip = null;
let pending = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
let busy = false;
let requestGeneration = 0;
let activeIdentity;
let waitingIdentity;
if (pending) {
  operator.value = pending.operator;
  quantity.value = pending.quantity ?? "";
  lotInput.value = pending.lot_id ?? "";
  notice.textContent = "Önceki kaydın sonucu bekleniyor. Aynı kaydı yeniden dene.";
}

function render() {
  const cutting = progress?.cutting;
  const shownQty = isCutting ? cutting?.cut_qty || 0 : progress?.completed_qty || 0;
  const sameLot = wip && wip.order_id === progress?.order_id && wip.order_key === progress?.order_key;
  const canCut = cutting?.order_open && cutting.status === "cutting" && cutting.cut_qty < progress.target_qty;
  const canPark = cutting?.order_open && cutting.status === "cutting" && cutting.cut_qty === progress.target_qty && !wip;
  const canPickup = cutting?.order_open && sameLot && wip.cut_qty === progress.target_qty;
  let action;
  order.textContent = progress?.order_id || "Aktif iş emri yok";
  count.textContent = progress?.unit_supported ? `${shownQty} / ${progress.target_qty}` : "–";
  meter.max = progress?.unit_supported ? progress.target_qty || 1 : 1;
  meter.value = progress?.unit_supported ? shownQty : 0;
  waitingLotText.hidden = !wip && !(isCutting && cutting?.lot_id);
  waitingLotText.textContent = wip
    ? `Bekleme alanı: ${isCutting ? `${wip.lot_id} · ` : ""}${wip.order_id} · ${wip.cut_qty} adet`
    : cutting?.lot_id ? `Parti etiketi: ${cutting.lot_id}` : "";
  if (progress && !progress.unit_supported) statusText.textContent = "Bu istasyon yalnızca adet birimli iş emirlerini kaydeder.";
  else if (isCutting) {
    action = canCut ? "cut" : canPark ? "park" : "";
    if (cutting?.status === "picked_up") statusText.textContent = "Partiyi kaplama istasyonu teslim aldı.";
    else if (cutting?.status === "parked") statusText.textContent = "Parti bekleme alanında.";
    else if (canCut) statusText.textContent = `${progress.target_qty - shownQty} parça daha kesilecek.`;
    else if (canPark) statusText.textContent = "Parti tamam. Fiziksel partiye kodu yazıp bekleme alanına bırak.";
    else if (cutting?.order_open && wip) statusText.textContent = "Bekleme alanı dolu.";
    else statusText.textContent = "Yeni kesim kaydı beklemede.";
  }
  else if (progress?.awaiting_handoff) statusText.textContent = "Kaplama hedefi tamamlandı. Hat teslimi bekleniyor.";
  else if (progress?.complete) statusText.textContent = "Kaplama hedefi tamamlandı.";
  else if (progress?.can_record) {
    action = "coat";
    statusText.textContent = `${progress.remaining_qty} parça daha kaplanacak.`;
  } else if (canPickup) {
    action = "pickup";
    statusText.textContent = "Fiziksel parti üzerindeki kodu girip partiyi teslim al.";
  } else if (cutting && cutting.status !== "picked_up") statusText.textContent = "Tam parti giyotinden gelene kadar kaplama beklemede.";
  else statusText.textContent = "Yeni kaplama kaydı beklemede.";
  const shownAction = pending ? pending.action || "coat" : action;
  const canWithdraw = isCutting && Boolean(wip) && !pending;
  operator.readOnly = quantity.readOnly = lotInput.readOnly = Boolean(pending) || busy;
  quantityField.hidden = !["cut", "coat"].includes(shownAction);
  quantity.disabled = quantityField.hidden;
  lotField.hidden = !canWithdraw && !["pickup", "withdraw"].includes(shownAction);
  if (pending || quantityField.hidden) quantity.removeAttribute("max");
  else quantity.max = isCutting ? progress.target_qty - shownQty : progress.remaining_qty;
  withdraw.hidden = !canWithdraw;
  withdraw.disabled = busy;
  save.value = action || "";
  save.disabled = busy || !(pending || action);
  const labels = { cut: "Kesimi kaydet", park: "Bekleme alanına bırak", pickup: "Partiyi teslim al", coat: "Kaplamayı kaydet" };
  save.textContent = busy ? "Kaydediliyor…" : pending ? "Aynı kaydı yeniden dene" : labels[action] || (isCutting ? labels.cut : labels.coat);
}

async function refresh() {
  if (busy) return;
  const generation = ++requestGeneration;
  try {
    const response = await fetch(api, { cache: "no-store", signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error("Bağlantı kurulamadı.");
    const data = await response.json();
    if (generation === requestGeneration) {
      const nextOrder = JSON.stringify([data.progress?.order_id, data.progress?.order_key]);
      const nextLot = data.wip?.lot_id;
      if (!pending && activeIdentity !== undefined && activeIdentity !== nextOrder) {
        quantity.value = "";
        lotInput.value = "";
        notice.textContent = "Aktif iş emri değişti. Yeni emri kontrol et.";
      } else if (!pending && waitingIdentity !== nextLot) lotInput.value = "";
      activeIdentity = nextOrder;
      waitingIdentity = nextLot;
      progress = data.progress;
      wip = data.wip;
      render();
    }
  } catch {
    if (generation === requestGeneration) {
      progress = null;
      wip = null;
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
  const action = event.submitter?.value;
  if (busy || !(pending || action)) return;
  if (!pending) {
    const name = operator.value.trim();
    if (!name) {
      notice.textContent = "Operatör adını gir.";
      operator.focus();
      return;
    }
    const source = action === "withdraw" ? wip : progress;
    if (!source) return;
    const needsLot = action === "pickup" || action === "withdraw";
    if (needsLot && !lotInput.value.trim()) {
      notice.textContent = "Parti üzerindeki kodu gir.";
      lotInput.focus();
      return;
    }
    pending = { request_id: crypto.randomUUID(), order_id: source.order_id, order_key: source.order_key, operator: name };
    if (action !== "coat") pending.action = action;
    if (action === "cut" || action === "coat") pending.quantity = quantity.valueAsNumber;
    if (needsLot) pending.lot_id = lotInput.value.trim();
    sessionStorage.setItem(pendingKey, JSON.stringify(pending));
  }
  busy = true;
  requestGeneration += 1;
  render();
  try {
    const response = await fetch(pending.action ? cuttingApi : api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pending),
      signal: AbortSignal.timeout(10000),
    });
    const data = await response.json();
    if (response.ok) {
      progress = data.progress;
      if (pending.action) wip = data.wip;
      const savedAction = pending.action;
      clearPending();
      quantity.value = "";
      lotInput.value = "";
      const savedMessages = { cut: "Kesim kaydedildi.", park: "Parti bekleme alanına kaydedildi.", pickup: "Parti teslim alındı.", withdraw: "Parti bekleme alanından geri çekildi." };
      notice.textContent = data.duplicate ? "Bu işlem daha önce kaydedildi." : savedMessages[savedAction] || "Kaplama kaydedildi.";
    } else if (response.status < 500) {
      clearPending();
      progress = null;
      wip = null;
      const errors = {
        COATING_ORDER_CHANGED: "Aktif iş emri değişti. Yeni emri kontrol et.",
        COATING_QUANTITY_UNAVAILABLE: "Adet kalan hedefi aşıyor veya iş emri kayda kapalı.",
        COATING_REQUEST_CONFLICT: "Bu kayıt numarası daha önce başka bir işlemde kullanılmış.",
        COATING_LOT_REQUIRED: "Kaplama için önce doğru partiyi teslim al.",
        CUTTING_ORDER_CHANGED: "Aktif iş emri değişti veya kayda kapandı.",
        CUTTING_LOT_INCOMPLETE: "Kesilen adet iş emrinin tamamını karşılamıyor.",
        CUTTING_WIP_OCCUPIED: "Bekleme alanı dolu. Önce bekleyen partiyi çıkar.",
        CUTTING_WRONG_LOT: "Parti kodu bekleyen partiyle eşleşmiyor.",
        CUTTING_QUANTITY_UNAVAILABLE: "Kesim adedi kalan hedefi aşıyor veya parti devredilmiş.",
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
