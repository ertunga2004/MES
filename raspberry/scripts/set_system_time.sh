#!/usr/bin/env bash
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <iso-datetime>" >&2
  exit 2
fi

TARGET_TIME="$1"

PREVIOUS_NTP_STATE="$(timedatectl show -p NTP --value 2>/dev/null || echo unknown)"

timedatectl set-ntp false
date --set "${TARGET_TIME}"
hwclock -w || true

if [ "${PREVIOUS_NTP_STATE}" = "yes" ]; then
  timedatectl set-ntp true || true
fi

echo "system clock updated to ${TARGET_TIME}"
