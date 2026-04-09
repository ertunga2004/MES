#!/usr/bin/env bash
set -eu

exec /usr/bin/x-terminal-emulator -e /bin/bash -lc '/home/pi/Documents/vision/scripts/start_observer_headless.sh; echo; echo Press Enter to close...; read _'
