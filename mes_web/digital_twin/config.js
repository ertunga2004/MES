export const LINE_CONFIG = Object.freeze({ capacity: 10, conveyorMs: 15000, movingMs:12000, sensorWaitMs:3000, pickupMs:2000, spacing:.45, robotCycleMs: 8000,
  hopperX: 5.55, sensorX: -3.25, pickupX: -4.05,
  robotDropMs: 5000, robotReleaseMs: 6000 });

export function workingTime(wallMs, pauses = []) {
  return wallMs - pauses.reduce((sum,pause) => sum + Math.max(0, Math.min(wallMs,pause.end)-pause.start),0);
}
export function wallTime(activeMs, pauses = []) {
  let wall = activeMs;
  for (const pause of pauses) {
    if (wall >= pause.start) wall += pause.end-pause.start;
    else break;
  }
  return wall;
}
