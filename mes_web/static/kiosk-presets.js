export const presets = {
  process: {
    title: "İşlem Takip", description: "Kesme, bantlama veya montaj adımları",
    timer: true, target: false, results: [],
    layout: "sidebar", cards: ["order", "instructions", "steps", "timer", "wip"],
  },
  quality: {
    title: "Kalite Kontrol", description: "Kontrol, ölçüm ve sonuç kaydı",
    timer: false, target: false, results: ["Uygun", "Yeniden işlem", "Uygunsuz"],
    layout: "double", cards: ["order", "steps", "result", "instructions", "wip"],
  },
  packing: {
    title: "Paketleme", description: "İş emri hedefi ve paketleme sonucu",
    timer: false, target: true, results: ["Tamamlandı", "Eksik"],
    layout: "sidebar", cards: ["order", "progress", "steps", "result", "wip"],
  },
  material: {
    title: "Malzeme", description: "Malzeme talimatları ve ek bilgi bölümleri",
    timer: false, target: false, results: [],
    layout: "double", cards: ["order", "material", "steps", "instructions", "wip"],
  },
  status: {
    title: "İstasyon Durumu", description: "Açık işin durumu ve süre sayacı",
    timer: true, target: false, results: [],
    layout: "single", cards: ["status", "order", "timer", "downtime", "steps", "wip"],
  },
};

export const layouts = { single: "Tek sütun", double: "İki sütun", sidebar: "Ana panel + yan panel" };
export const sizes = { small: "Küçük", medium: "Orta", large: "Büyük", full: "Tam genişlik" };
export const sources = { fixed: "Sabit içerik", station: "Bağlı istasyon", order: "Seçili iş emri" };
export const stations = { cutting: "Giyotin", coating: "Kaplama", conveyor: "Konveyör" };
export const cardTypes = {
  order: ["İş emri", 1, ["order"]], instructions: ["Operatör talimatı", 0, ["fixed", "order"]],
  steps: ["Akış / kontrol adımları", 2, ["fixed"]], timer: ["Süre sayacı", 0, ["fixed"]],
  progress: ["Üretim sayacı", 0, ["fixed", "order"]], result: ["İşin sonucu", 1, ["fixed"]],
  status: ["İstasyon durumu", 0, ["station"]], wip: ["WIP bekleme alanları", 2, ["station"]],
  downtime: ["Duruş / hata bildirimi", 1, ["fixed"]], actions: ["İşlem butonları", 2, ["fixed"]],
  material: ["Malzeme listesi", 1, ["station", "fixed"]], before: ["İşe başlamadan önce", 0, ["fixed"]],
  after: ["İş bitiminde", 0, ["fixed"]], extra: ["Ek bölümler", 1, ["fixed"]],
};

export function makeCard(kind) {
  const [title, minimum, allowed] = cardTypes[kind];
  return { kind, title, size: Object.keys(sizes)[Math.max(1, minimum)], source: allowed[0], visible: true, body: "" };
}

export function templateCards(preset) {
  return [...preset.cards, "before", "after", "extra", "actions"].map(kind => {
    const card = makeCard(kind);
    if (kind === "progress") card.source = "order";
    return card;
  });
}
