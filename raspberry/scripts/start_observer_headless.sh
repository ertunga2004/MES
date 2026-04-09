#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_PATH="${PROJECT_ROOT}/observer.log"

cd "${PROJECT_ROOT}"
source .venv/bin/activate

export PYTHONUNBUFFERED=1
export MES_OBSERVER_SET_CLOCK_CMD="/usr/bin/sudo -n /home/pi/Documents/vision/scripts/set_system_time.sh"

pkill -f "run_observer.py" 2>/dev/null || true
nohup python -u run_observer.py --config config/observer.example.json --boxes config/boxes.example.json --no-gui > "${LOG_PATH}" 2>&1 &
echo "Observer started in headless mode. Log: ${LOG_PATH}"
