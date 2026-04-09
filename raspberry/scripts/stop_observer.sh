#!/usr/bin/env bash
set -eu

pkill -f "run_observer.py" 2>/dev/null || true
echo "Observer stopped."
