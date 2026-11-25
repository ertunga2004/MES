export const COLORS = { blue: 'Mavi', red: 'Kırmızı', yellow: 'Sarı' };
export const OUTCOMES = { good: 'Sağlam', rework: 'Yeniden işlem', scrap: 'Red', allowed: 'İzinli' };
export const TAPING_STEPS = ['Bant rengini doğrula', 'Kutu kodunu tara', 'Bant uzunluğunu ölç', 'Kalite kontrolünü tamamla'];
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
