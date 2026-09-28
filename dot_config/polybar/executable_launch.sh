#!/usr/bin/env sh
# Start one polybar ("example") per connected monitor.
# The primary monitor gets bar "example" (with tray); others "example-secondary".

# Serialize concurrent launches (i3 startup + autorandr postswitch at login,
# display-toggle): without the lock two runs can interleave and spawn duplicate bars.
# Bars are started with fd 9 closed so they do not hold the lock.
LOCK="${XDG_RUNTIME_DIR:-/tmp}/polybar-launch.lock"
exec 9>"$LOCK"
flock -w 15 9 || true

killall -q polybar
# Wait (max ~5 s) for old bars to exit, then force-kill leftovers.
i=0
while pgrep -u "$(id -u)" -x polybar >/dev/null && [ $i -lt 10 ]; do sleep 0.5; i=$((i+1)); done
pkill -9 -u "$(id -u)" -x polybar 2>/dev/null

LOG=/tmp/polybar-$(id -u).log
: >"$LOG"

# UI scale: follow Xft.dpi / polybar.height from X resources (set by
# `control-center displays` -> UI scale). This polybar build lacks xrdb support.
POLYBAR_DPI=$(xrdb -query 2>/dev/null | awk '/^Xft.dpi:/{print $2; exit}')
POLYBAR_HEIGHT=$(xrdb -query 2>/dev/null | awk '/^polybar.height:/{print $2; exit}')
export POLYBAR_DPI="${POLYBAR_DPI:-96}" POLYBAR_HEIGHT="${POLYBAR_HEIGHT:-24}"

# Only active, non-mirrored monitors (skips outputs that are connected but off).
monitors=$(polybar --list-monitors 2>/dev/null)
if [ -n "$monitors" ]; then
  primary=$(printf '%s\n' "$monitors" | awk -F: '/\(primary\)/{print $1; exit}')
  [ -z "$primary" ] && primary=$(printf '%s\n' "$monitors" | awk -F: 'NR==1{print $1}')
  for m in $(printf '%s\n' "$monitors" | cut -d: -f1); do
    bar=example-secondary
    [ "$m" = "$primary" ] && bar=example
    MONITOR=$m polybar --reload "$bar" >>"$LOG" 2>&1 9>&- &
  done
else
  polybar --reload example >>"$LOG" 2>&1 9>&- &
fi
