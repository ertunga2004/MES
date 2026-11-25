/**
 * Atölye Önizleme - Örnek Veri Modülü
 * Tüm veriler sentetik ve "ÖRNEK VERİ" olarak açıkça etiketlenmiştir.
 * Gerçek kayıt değildir, üretim kaydı oluşturmaz.
 */

// ============================================================
// Kiosk Tasarımı (Bantlama İstasyonu - sidebar şablonu)
// ============================================================

export const SAMPLE_KIOSK_DESIGN = {
  title: "Bantlama İstasyonu",
  instructions: "Bantlama işlemini adımlara göre tamamlayın. Her adım onaylandıktan sonra bir sonrakine geçin.",
  layout: "sidebar",
  shiftPosition: "top",
  station: "bantlama",
  cards: [
    { kind: "order", title: "Aktif İş Emri", size: "full", source: "order", visible: true, body: "" },
    { kind: "instructions", title: "Operatör Talimatı", size: "full", source: "fixed", visible: true, body: "Bantlama için 2 kesilmiş bant bir kutuya yeterlidir. Renk kodlarına dikkat edin." },
    { kind: "steps", title: "Kontrol Adımları", size: "full", source: "fixed", visible: true, body: "" },
    { kind: "timer", title: "Süre Sayacı", size: "medium", source: "fixed", visible: true, body: "" },
    { kind: "progress", title: "Üretim Sayacı", size: "medium", source: "order", visible: true, body: "" },
    { kind: "wip", title: "WIP Bekleme Alanları", size: "large", source: "station", visible: true, body: "" },
    { kind: "actions", title: "İşlemler", size: "full", source: "fixed", visible: true, body: "" }
  ],
  features: {
    timer: true,
    progress: { target: 50, unit: "adet" },
    result: ["Tamamlandı", "Eksik", "Beklemede"]
  },
  steps: [
    { label: "Bant rengini kontrol et", kind: "check", required: true, options: [], interruptible: false },
    { label: "Kutu kodunu tara", kind: "text", required: true, options: [], interruptible: false },
    { label: "Bant uzunluğunu ölç (mm)", kind: "number", required: true, options: [], interruptible: false },
    { label: "Kalite onayı", kind: "choice", required: true, options: ["Geçti", "Geçmedi - Yeniden işlem", "Geçmedi - Hurda"], interruptible: false }
  ],
  sections: [
    { title: "Güvenlik Notu", body: "Makine çalışırken koruyucu kalkanı asla kaldırmayın." }
  ],
  before: "İşe başlamadan önce bant rengini ve kutu kodunu doğrulayın.",
  after: "İş bitiminde bandı kesin ve kutuyu paketleme alanına gönderin."
};

// ============================================================
// İstasyon Durumu (Tablet ve İzleme için paylaşılan veri)
// ============================================================

export const SAMPLE_STATION_STATE = {
  station: {
    id: "bantlama",
    name: "Bantlama İstasyonu",
    line: "KNV-01"
  },
  shift: {
    operator: "Ahmet Yılmaz",
    startedAt: "2026-11-25T06:00:00+03:00"
  },
  run: {
    id: 12345,
    operator: "Ahmet Yılmaz",
    orderRef: "WO-2026-0456",
    startedAt: "2026-11-25T08:15:00+03:00",
    timer: {
      activeMs: 2700000,
      waitingMs: 300000,
      since: Date.now() - 2700000,
      paused: false
    },
    quantity: 23,
    values: [true, "KUTU-789", 450, "Geçti"],
    result: null
  },
  orders: [
    { id: "WO-2026-0456", customer: "ABC Ltd.", status: "active", qty: 50, completed_qty: 23, remaining_qty: 27, stock_name: "Standart Kutu", stock_code: "BOX-STD", color: "blue" },
    { id: "WO-2026-0457", customer: "XYZ A.Ş.", status: "queued", qty: 30, completed_qty: 0, remaining_qty: 30, stock_name: "Küçük Kutu", stock_code: "BOX-SM", color: "red" },
    { id: "WO-2026-0458", customer: "DEF Tic.", status: "queued", qty: 40, completed_qty: 0, remaining_qty: 40, stock_name: "Büyük Kutu", stock_code: "BOX-LG", color: "yellow" }
  ],
  wipAreas: [
    { code: "wip-1", title: "WIP Alanı 1 (Giriş)", occupied: 1, capacity: 5 },
    { code: "wip-2", title: "WIP Alanı 2 (Çıkış)", occupied: 0, capacity: 3 }
  ],
  parked: [
    { id: 101, orderRef: "WO-2026-0455", itemRef: "KUTU-456", area: "wip-1", reason: "Malzeme bekleme" }
  ],
  lastRun: {
    operator: "Mehmet Demir",
    orderRef: "WO-2026-0455",
    timer: { activeMs: 4200000, waitingMs: 600000 },
    quantity: 50,
    result: "Tamamlandı"
  },
  reasons: {
    "material_wait": "Malzeme bekleme",
    "quality_hold": "Kalite onayı bekleme",
    "maintenance": "Bakım",
    "shift_change": "Vardiya değişimi"
  },
  canOperate: true,
  occupied: false,
  version: 3
};

// ============================================================
// İzleme Paneli Verisi (Hat genel durumu)
// ============================================================

export const SAMPLE_MONITOR_DATA = {
  lineStatus: {
    header: {
      state_summary: "Hat çalışıyor · Üretim aktif",
      line_id: "KNV-01",
      shift: "Gündüz"
    },
    kpis: {
      oee: 82.5,
      availability: 95.2,
      performance: 88.1,
      quality: 98.3
    },
    production: {
      target: 500,
      actual: 412,
      good: 405,
      rework: 5,
      scrap: 2
    }
  },
  stations: [
    { id: "giyotin", name: "Giyotin", status: "running", currentOrder: "WO-2026-0454", progress: 78, operator: "Can Kaya" },
    { id: "kaplama", name: "Kaplama", status: "running", currentOrder: "WO-2026-0454", progress: 45, operator: "Elif Öz" },
    { id: "bantlama", name: "Bantlama", status: "running", currentOrder: "WO-2026-0456", progress: 46, operator: "Ahmet Yılmaz" },
    { id: "konveyor", name: "Konveyör", status: "idle", currentOrder: null, progress: 0, operator: null },
    { id: "paketleme", name: "Paketleme", status: "waiting", currentOrder: null, progress: 0, operator: null }
  ],
  activeFaults: [],
  recentItems: [
    { item_id: "ITEM-20261125-001", completed_at: "2026-11-25T07:45:12+03:00", classification: "GOOD", display_color: "blue", can_override: true, work_order_id: "WO-2026-0454" },
    { item_id: "ITEM-20261125-002", completed_at: "2026-11-25T07:48:33+03:00", classification: "GOOD", display_color: "blue", can_override: true, work_order_id: "WO-2026-0454" },
    { item_id: "ITEM-20261125-003", completed_at: "2026-11-25T07:52:01+03:00", classification: "REWORK", display_color: "yellow", can_override: true, work_order_id: "WO-2026-0454" },
    { item_id: "ITEM-20261125-004", completed_at: "2026-11-25T07:55:44+03:00", classification: "GOOD", display_color: "red", can_override: true, work_order_id: "WO-2026-0453" },
    { item_id: "ITEM-20261125-005", completed_at: "2026-11-25T08:01:20+03:00", classification: "SCRAP", display_color: "red", can_override: false, work_order_id: "WO-2026-0453" }
  ]
};

// ============================================================
// İstasyon Listesi (İzleme sekmesi seçici için)
// ============================================================

export const STATIONS_LIST = [
  { id: "giyotin", name: "Giyotin", line: "KNV-01" },
  { id: "kaplama", name: "Kaplama", line: "KNV-01" },
  { id: "bantlama", name: "Bantlama", line: "KNV-01" },
  { id: "konveyor", name: "Konveyör", line: "KNV-01" },
  { id: "paketleme", name: "Paketleme", line: "KNV-01" }
];

// ============================================================
// Şablonlar (Designer sekmesi için)
// ============================================================

export const TEMPLATES = {
  process: { title: 'İşlem Takip', hint: 'Kesme, bantlama veya montaj', cards: ['order', 'instructions', 'steps', 'timer', 'wip'], layout: 'sidebar', features: { timer: true, progress: null, result: null } },
  quality: { title: 'Kalite Kontrol', hint: 'Kontrol listesi, ölçüm ve sonuç', cards: ['order', 'steps', 'result', 'instructions', 'wip'], layout: 'double', features: { timer: false, progress: null, result: ['Uygun', 'Yeniden işlem', 'Uygunsuz'] } },
  packing: { title: 'Paketleme', hint: 'Hedef, gerçekleşen ve paket sonucu', cards: ['order', 'progress', 'steps', 'result', 'wip'], layout: 'sidebar', features: { timer: false, progress: { target: 1, unit: 'adet' }, result: ['Tamamlandı', 'Eksik'] } },
  material: { title: 'Malzeme', hint: 'İhtiyaç, mevcut miktar ve bildirim', cards: ['order', 'material', 'steps', 'instructions', 'wip'], layout: 'double', features: { timer: false, progress: null, result: null } },
  status: { title: 'İstasyon Durumu', hint: 'Çalışma, bekleme ve duruş kaydı', cards: ['status', 'order', 'timer', 'downtime', 'steps', 'wip'], layout: 'single', features: { timer: true, progress: null, result: null } }
};