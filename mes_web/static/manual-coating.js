const form = document.getElementById("coating-form");
const operator = document.getElementById("operator");
const quantity = document.getElementById("quantity");
const quantityField = document.getElementById("quantity-field");
const quantityLabel = document.getElementById("quantity-label");
const save = document.getElementById("save");
const order = document.getElementById("order");
const count = document.getElementById("count");
const meter = document.getElementById("progress");
const statusText = document.getElementById("order-status");
const notice = document.getElementById("notice");
const isCutting = window.location.pathname === "/giyotin";
const pendingKey = isCutting ? "mes-cutting-pending" : "mes-manual-coating-pending";
const readApi = "/api/manual-coating";
const writeApi = isCutting ? "/api/cutting-workflow" : readApi;

if (isCutting) {
  document.title = "Giyotin · MES";
  document.getElementById("station-title").textContent = "Giyotin";
  meter.setAttribute("aria-label", "Kesim ilerlemesi");
}

let progress = null;
let pending = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
let busy = false;
let refreshing = false;
let writeGeneration = 0;
let activeIdentity;

if (pending) {
  operator.value = pending.operator;
  quantity.value = pending.quantity ?? "";
  notice.textContent = "Önceki kaydın sonucu bekleniyor. Aynı kaydı yeniden dene.";
}

function inputLimit() {
  if (isCutting) {
    const cutting = progress?.cutting;
    return cutting?.order_open && !cutting.legacy_blocked ? cutting.target_tapes - cutting.cut_tapes : 0;
  }
  return progress?.can_record ? progress.remaining_qty : 0;
}

function render() {
  const cutting = progress?.cutting;
  const limit = inputLimit();
  const shownQty = isCutting ? cutting?.cut_tapes || 0 : progress?.completed_qty || 0;
  const target = isCutting ? cutting?.target_tapes : progress?.target_qty;
  const unit = isCutting ? "bant parçası" : cutting ? "kutu" : "adet";
  order.textContent = progress?.order_id || "Aktif iş emri yok";
  count.textContent = progress?.unit_supported ? `${shownQty} / ${target} ${unit}` : "–";
  meter.max = target || 1;
  meter.value = shownQty;
  quantityLabel.textContent = isCutting ? "Kesilen bant parçası" : cutting ? "Kaplanan kutu adedi" : "Kaplanan parça adedi";

  if (progress && !progress.unit_supported) statusText.textContent = "Bu istasyon yalnızca adet birimli iş emirlerini kaydeder.";
  else if (cutting?.legacy_blocked) statusText.textContent = "Bu işte eski akış kayıtları var. Doğrudan aktarım için yeni bir iş emri aç.";
  else if (isCutting && cutting?.order_open) {
    const ready = `Kaplamaya hazır: ${cutting.available_boxes} kutu.`;
    statusText.textContent = limit > 0 ? `${limit} bant parçası daha kesilecek. ${ready}` : `Kesim hedefi tamamlandı. ${ready}`;
  } else if (!isCutting && progress?.complete) {
    statusText.textContent = progress.awaiting_handoff ? "Kaplama hedefi tamamlandı. Hat teslimi bekleniyor." : "Kaplama hedefi tamamlandı.";
  } else if (!isCutting && cutting && progress.can_record) {
    statusText.textContent = `${limit} kutu için bant hazır. Kaplamaya başlayabilirsin.`;
  } else if (!isCutting && cutting?.order_open) {
    statusText.textContent = cutting.unpaired_tapes === 1
      ? "Bir bant hazır. Bir kutu için bir bant daha bekleniyor."
      : "Bir kutu için iki kesilmiş bant bekleniyor.";
  } else if (progress?.can_record) statusText.textContent = `${limit} parça daha kaplanacak.`;
  else statusText.textContent = isCutting ? "Yeni kesim kaydı beklemede." : "Yeni kaplama kaydı beklemede.";

  operator.readOnly = quantity.readOnly = Boolean(pending) || busy;
  quantityField.hidden = !(pending || limit > 0);
  quantity.disabled = quantityField.hidden;
  if (pending || quantityField.hidden) quantity.removeAttribute("max");
  else quantity.max = limit;
  save.disabled = busy || !(pending || limit > 0);
  save.textContent = busy ? "Kaydediliyor…" : pending ? "Aynı kaydı yeniden dene" : isCutting ? "Kesimi kaydet" : "Kaplamayı kaydet";
}

async function refresh() {
  if (busy || refreshing) return;
  refreshing = true;
  const generation = writeGeneration;
  try {
    const response = await fetch(readApi, { cache: "no-store", signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error("Bağlantı kurulamadı.");
    const data = await response.json();
    if (generation === writeGeneration) {
      const nextOrder = JSON.stringify([data.progress?.order_id, data.progress?.order_key]);
      if (!pending && activeIdentity !== undefined && activeIdentity !== nextOrder) {
        quantity.value = "";
        notice.textContent = "Aktif iş emri değişti. Yeni emri kontrol et.";
      }
      activeIdentity = nextOrder;
      progress = data.progress;
      render();
    }
  } catch {
    if (generation === writeGeneration) {
      progress = null;
      render();
      statusText.textContent = "Sunucuya ulaşılamıyor.";
    }
  } finally {
    refreshing = false;
  }
}

function clearPending() {
  sessionStorage.removeItem(pendingKey);
  pending = null;
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy || !(pending || inputLimit() > 0)) return;
  if (!pending) {
    const name = operator.value.trim();
    if (!name) {
      notice.textContent = "Operatör adını gir.";
      operator.focus();
      return;
    }
    pending = {
      request_id: crypto.randomUUID(), order_id: progress.order_id, order_key: progress.order_key,
      operator: name, quantity: quantity.valueAsNumber,
    };
    sessionStorage.setItem(pendingKey, JSON.stringify(pending));
  }
  busy = true;
  writeGeneration += 1;
  render();
  try {
    const response = await fetch(writeApi, {
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
      notice.textContent = data.duplicate ? "Bu işlem daha önce kaydedildi." : isCutting ? "Kesim kaydedildi." : "Kaplama kaydedildi.";
    } else if (response.status < 500) {
      clearPending();
      progress = null;
      const errors = {
        COATING_ORDER_CHANGED: "Aktif iş emri değişti. Yeni emri kontrol et.",
        COATING_QUANTITY_UNAVAILABLE: "Girilen adet için yeterli bant yok veya iş emri kayda kapalı.",
        COATING_REQUEST_CONFLICT: "Bu kayıt numarası daha önce başka bir işlemde kullanılmış.",
        CUTTING_ORDER_CHANGED: "Aktif iş emri değişti veya kayda kapandı.",
        CUTTING_QUANTITY_UNAVAILABLE: "Kesim adedi kalan bant hedefini aşıyor.",
        CUTTING_LEGACY_ORDER: "Bu işte eski akış kayıtları var. Yeni bir iş emri aç.",
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
setInterval(refresh, 1000);
