const employeeDashboard = (() => {
  const select = document.getElementById("employee-dashboard-select");
  const customKiosks = document.getElementById("employee-custom-kiosks");
  const status = document.getElementById("employee-dashboard-status");
  const frame = document.getElementById("employee-dashboard-frame");
  let catalogRequest;

  function showSelectedPanel() {
    const option = select.selectedOptions[0];
    frame.title = `${option.textContent} izleme paneli`;
    if (frame.getAttribute("src") !== option.value) frame.src = option.value;
  }

  async function refreshCatalog() {
    catalogRequest?.abort();
    const request = new AbortController();
    catalogRequest = request;
    status.textContent = "Yayımlanan kiosklar yükleniyor…";
    status.hidden = false;
    try {
      const response = await fetch("/api/employee-observer/kiosks", {
        cache: "no-store",
        signal: request.signal,
      });
      if (!response.ok) throw new Error("Kiosk listesi alınamadı");
      const entries = await response.json();
      if (request.signal.aborted) return;
      const selectedPath = select.value;
      const options = entries.filter((entry) => (
        /^[a-z][a-z0-9-]{1,39}$/.test(entry.slug) &&
        typeof entry.title === "string" && entry.title.trim() &&
        entry.path === `/calisan/kiosk/${entry.slug}`
      )).map(({ title, path }) => new Option(title, path));
      customKiosks.replaceChildren(...options);
      customKiosks.hidden = options.length === 0;
      select.value = selectedPath;
      if (select.selectedIndex < 0) select.selectedIndex = 0;
      showSelectedPanel();
      status.hidden = true;
    } catch (error) {
      if (request.signal.aborted) return;
      if (select.selectedOptions[0]?.parentElement === customKiosks) select.selectedIndex = 0;
      customKiosks.replaceChildren();
      customKiosks.hidden = true;
      showSelectedPanel();
      status.textContent = "Yayımlanan kiosklar yüklenemedi. İstasyon sekmesini yeniden açarak tekrar deneyebilirsiniz.";
    }
  }

  select.addEventListener("change", showSelectedPanel);

  return {
    setVisible(visible) {
      if (visible) {
        showSelectedPanel();
        refreshCatalog();
      } else {
        catalogRequest?.abort();
        frame.removeAttribute("src");
      }
    },
  };
})();
