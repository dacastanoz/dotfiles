#!/usr/bin/env bash
# Polybar Bluetooth indicator.
#   no output state   -> adapter missing
#   󰂲  grey          -> powered off / blocked
#   󰂯              -> on, nothing connected
#   󰂱 Name [NN%]    -> connected device (battery when reported)
# Usage: bluetooth.sh [toggle]
set -u
GREY="#4c566a"
ACCENT="#88c0d0"

if [ "${1:-}" = "toggle" ]; then
    if bluetoothctl show 2>/dev/null | grep -q 'Powered: yes'; then
        bluetoothctl power off >/dev/null 2>&1
    else
        rfkill unblock bluetooth
        sleep 1
        bluetoothctl power on >/dev/null 2>&1
    fi
    exit 0
fi

show=$(bluetoothctl show 2>/dev/null)
if [ -z "$show" ]; then
    echo ""
    exit 0
fi
if ! grep -q 'Powered: yes' <<<"$show"; then
    echo "%{F$GREY}󰂲%{F-}"
    exit 0
fi

out=""
while read -r _ mac name; do
    [ -z "$mac" ] && continue
    battery=$(bluetoothctl info "$mac" 2>/dev/null | sed -n 's/.*Battery Percentage:.*(\([0-9]*\)).*/\1/p')
    entry="$name"
    [ -n "$battery" ] && entry="$entry $battery%"
    out="${out:+$out, }$entry"
done < <(bluetoothctl devices Connected 2>/dev/null | awk '$1=="Device"')

if [ -n "$out" ]; then
    # Keep the bar compact.
    [ "${#out}" -gt 28 ] && out="${out:0:27}…"
    echo "%{F$ACCENT}󰂱%{F-} $out"
else
    echo "󰂯"
fi
