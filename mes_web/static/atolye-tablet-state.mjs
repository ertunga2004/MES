export const COLORS = { blue: 'Mavi', red: 'Kırmızı', yellow: 'Sarı' };
export const OUTCOMES = { good: 'Sağlam', rework: 'Yeniden işlem', scrap: 'Red', allowed: 'İzinli' };
export const BANTLAMA_STEPS = [
  'Kutuyu masaya koy',
  'Gerekli bandı al',
  'Üstünü kapla',
  'Etrafını kapla',
  'Konveyöre ver',
];

export function completedTapingSteps(box) {
  if (box?.steps?.length !== BANTLAMA_STEPS.length) return 0;
  const next = box.steps.indexOf(false);
  return next < 0 ? BANTLAMA_STEPS.length : next;
}

const TAPING_PROGRESS_KEY = 'mes.bantlama.stepper.v1';

export function restoreTapingProgress(board) {
  const completed = completedTapingSteps(board.activeBox);
  try {
    if (!board.activeBox) {
      localStorage.removeItem(TAPING_PROGRESS_KEY);
      return completed;
    }
    const current = { box: board.activeBox.id, revision: board.revision, completed };
    const saved = JSON.parse(localStorage.getItem(TAPING_PROGRESS_KEY) ?? 'null');
    if (saved?.box === current.box && saved.revision === current.revision && saved.completed === completed) {
      return saved.completed;
    }
    localStorage.setItem(TAPING_PROGRESS_KEY, JSON.stringify(current));
  } catch {
    // The station record is authoritative when browser storage is unavailable.
  }
  return completed;
}
export const FAULT_STATUS = { open: 'Açık', accepted: 'İşlemde', resolved: 'Çözüldü' };
export const STATIONS_LIST = [
  { id: 'bantlama', name: 'Bantlama' }, { id: 'paketleme', name: 'Paketleme' },
  { id: 'giyotin', name: 'Giyotin' }, { id: 'kaplama', name: 'Kaplama' },
  { id: 'konveyor', name: 'Konveyör' }, { id: 'tekniker', name: 'Tekniker' },
  { id: 'kalite', name: 'Kalite' }, { id: 'malzeme', name: 'Malzeme' },
];

export function readyPairs(state, color) {
  return Math.floor((state.cut[color] - state.used[color]) / 2);
}

export function packedTotal(state) {
  return Object.values(state.packed).reduce((total, quantity) => total + quantity, 0);
}

export function readyToPack(state) {
  return state.boxes.filter(box => box.stage === 'exited' && box.outcome === 'good' && state.packed[box.color] < state.goals[box.color]);
}

export function elapsedTaping(box, now) {
  return box.activeMs + (box.paused ? 0 : Math.max(0, now - box.since));
}
