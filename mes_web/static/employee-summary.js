const workspace = location.pathname.split("/").pop();
const titles = { cutting: "Giyotin", coating: "Kaplama", conveyor: "Konveyör Operatörü" };
const heading = document.getElementById("station-name");
const order = document.getElementById("station-order");
const values = document.getElementById("station-values");
heading.textContent = titles[workspace] || "İstasyon";
document.title = `${heading.textContent} · Salt okunur izleme`;

async function refresh() {
  try {
    const response = await fetch(`/api/employee-observer/${encodeURIComponent(workspace)}`, { cache: "no-store" });
    if (!response.ok) throw new Error();
    const state = await response.json();
    order.textContent = state.order ? `Aktif iş emri · ${state.order}` : "Aktif iş emri bekleniyor";
    values.replaceChildren(...state.rows.map(([label, value]) => {
      const row = document.createElement("div");
      row.className = "employee-summary-row";
      const title = document.createElement("dt");
      title.textContent = label;
      const amount = document.createElement("dd");
      amount.textContent = value;
      row.append(title, amount);
      return row;
    }));
  } catch {
    order.textContent = "İstasyon bilgisi alınamadı. Bağlantı yeniden denenecek.";
  } finally {
    setTimeout(refresh, 3000);
  }
}

refresh();
