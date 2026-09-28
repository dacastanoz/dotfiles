#!/usr/bin/env bash
# Polybar airplane-mode indicator: prints an icon only while every radio is
# soft-blocked; prints nothing otherwise (module is hidden).
states=$(rfkill -n -o SOFT 2>/dev/null)
if [ -n "$states" ] && ! grep -q '^unblocked' <<<"$states"; then
    echo "%{F#ebcb8b}󰀝%{F-}"
else
    echo ""
fi
