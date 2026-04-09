#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"
source .venv/bin/activate

export PYTHONUNBUFFERED=1
export DISPLAY="${DISPLAY:-:0}"
export MES_OBSERVER_SET_CLOCK_CMD="/usr/bin/sudo -n /home/pi/Documents/vision/scripts/set_system_time.sh"

pkill -f "run_observer.py" 2>/dev/null || true

exec python run_observer.py --config config/observer.example.json --boxes config/boxes.example.json
