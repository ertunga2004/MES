#!/usr/bin/env bash
set -eu

exec /usr/bin/x-terminal-emulator -e /bin/bash -lc '/home/pi/Documents/vision/scripts/stop_observer.sh; echo; echo Press Enter to close...; read _'
