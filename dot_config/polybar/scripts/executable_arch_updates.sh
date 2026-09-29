#!/usr/bin/env bash
# Polybar "updates" module: pending repo + AUR updates.
#
# One shared worker computes the results; every bar only READS the cache, so
# two bars (eDP + HDMI) never run two `paru -Qua` at once (concurrent paru
# processes race on ~/.local/state/paru/devel.toml and fail the rename).
#
#   arch_updates.sh              print the compact bar label (fast, cache only;
#                                starts a background refresh when stale)
#   arch_updates.sh --refresh    refresh the cache now (waits for the lock)
#   arch_updates.sh --refresh-bg refresh in the background (no-op if running)
#   arch_updates.sh --menu       rofi menu: pending updates + actions
#
# Cache: ~/.cache/bar-updates/{count,list,errors,stamp}
#   count  "<total> <repo> <aur>"
#   list   "repo|aur<TAB>name old -> new" per line
#   errors "<epoch><TAB><source>: <message>" per line (appended, capped)
#   stamp  "<epoch> ok|error" of the last finished run
# Repo updates use `checkupdates` (pacman-contrib: private db copy, no pacman
# lock); AUR updates use `paru -Qua`. stderr never reaches stdout.
set -u
export LC_TIME=C   # English dates in menus

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/bar-updates"
LOCK="${XDG_RUNTIME_DIR:-/tmp}/bar-updates.lock"
MAX_AGE=1800      # refresh at most every 30 min
MAX_ERRORS=200    # lines kept in the errors file

C_ICON="#88c0d0" C_MUTED="#4c566a" C_WARN="#ebcb8b"
ICON=$'\U000F03D6'   # nf-md-package_variant
WARN=$'\U000F0026'   # nf-md-alert

SELF=$(readlink -f "$0")

stamp_get() { # -> "<epoch> <status>" (defaults "0 ok")
    local t=0 s=ok
    [ -r "$CACHE/stamp" ] && read -r t s <"$CACHE/stamp"
    [[ $t =~ ^[0-9]+$ ]] || t=0
    echo "$t ${s:-ok}"
}

log_error() { # log_error <source> <text...>; one line per non-empty input line
    local src="$1" line now
    now=$(date +%s)
    shift
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        printf '%s\t%s: %s\n' "$now" "$src" "${line:0:300}" >>"$CACHE/errors"
    done <<<"$*"
}

run_checks() {
    local tmp repo_out aur_out rc repo=0 aur=0 status=ok
    mkdir -p "$CACHE"
    tmp=$(mktemp -d) || return 1
    # shellcheck disable=SC2064 # expand $tmp now
    trap "rm -rf '$tmp'" RETURN

    # checkupdates: 0 = updates listed, 2 = no updates, anything else = error.
    checkupdates >"$tmp/repo" 2>"$tmp/repo.err" </dev/null
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
        status=error
        log_error checkupdates "$(cat "$tmp/repo.err")"
        [ -s "$tmp/repo.err" ] || log_error checkupdates "exit code $rc"
    fi

    # paru -Qua: 0 = updates listed, 1 with no stderr = nothing to upgrade.
    paru -Qua >"$tmp/aur" 2>"$tmp/aur.err" </dev/null
    rc=$?
    if { [ "$rc" -ne 0 ] && [ -s "$tmp/aur.err" ]; } || [ "$rc" -gt 1 ] \
        || grep -qi '^error' "$tmp/aur.err"; then
        status=error
        log_error paru "$(cat "$tmp/aur.err")"
        [ -s "$tmp/aur.err" ] || log_error paru "exit code $rc"
    fi

    repo_out=$(awk 'NF{print "repo\t" $0}' "$tmp/repo")
    aur_out=$(awk 'NF && $0 !~ /^(::|warning|error)/{print "aur\t" $0}' "$tmp/aur")
    [ -n "$repo_out" ] && repo=$(wc -l <<<"$repo_out")
    [ -n "$aur_out" ] && aur=$(wc -l <<<"$aur_out")

    printf '%s\n' "$repo_out" "$aur_out" | awk 'NF' >"$CACHE/list.tmp"
    echo "$((repo + aur)) $repo $aur" >"$CACHE/count.tmp"
    mv -f "$CACHE/list.tmp" "$CACHE/list"
    mv -f "$CACHE/count.tmp" "$CACHE/count"
    if [ -f "$CACHE/errors" ]; then
        tail -n "$MAX_ERRORS" "$CACHE/errors" >"$CACHE/errors.tmp" && mv -f "$CACHE/errors.tmp" "$CACHE/errors"
    fi
    echo "$(date +%s) $status" >"$CACHE/stamp"
}

refresh() { # refresh wait|nowait
    mkdir -p "$CACHE"
    exec 8>"$LOCK"
    if [ "$1" = wait ]; then
        flock -w 900 8 || return 1
    else
        flock -n 8 || return 0   # another run is already in progress
    fi
    run_checks
    exec 8>&-
}

refresh_bg() {
    setsid -f "$SELF" --refresh-bg >/dev/null 2>&1 </dev/null
}

print_label() {
    local total=0 t status now
    read -r t status < <(stamp_get)
    now=$(date +%s)
    if (( now - t >= MAX_AGE )); then
        # Only spawn when no refresh holds the lock.
        if ( exec 8>"$LOCK"; flock -n 8 ); then refresh_bg; fi
    fi
    [ -r "$CACHE/count" ] && read -r total _ <"$CACHE/count"
    [[ $total =~ ^[0-9]+$ ]] || total=0

    local out
    if (( total > 0 )); then
        out="%{F$C_ICON}$ICON%{F-} $total"
    else
        out="%{F$C_MUTED}$ICON%{F-}"
    fi
    [ "$status" = error ] && out+=" %{F$C_WARN}$WARN%{F-}"
    echo "$out"
}

ago() { # epoch -> "5m ago"
    local d=$(( $(date +%s) - $1 ))
    if (( $1 == 0 )); then echo "never"
    elif (( d < 60 )); then echo "just now"
    elif (( d < 3600 )); then echo "$((d / 60))m ago"
    elif (( d < 86400 )); then echo "$((d / 3600))h ago"
    else echo "$((d / 86400))d ago"; fi
}

esc() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

rofi_menu() { # rofi_menu <prompt> [message]
    local args=(-dmenu -i -no-custom -markup-rows -p "$1")
    [ -n "${2:-}" ] && args+=(-mesg "$2")
    rofi "${args[@]}"
}

show_errors() {
    local clear="󰃢  Clear errors" rows choice
    rows=$(if [ -s "$CACHE/errors" ]; then
        tac "$CACHE/errors" | while IFS=$'\t' read -r t msg; do
            printf '%s  %s\n' "$(date -d "@$t" '+%d %b %H:%M')" "$msg"
        done | esc
    else
        echo "No errors recorded"
    fi)
    choice=$(printf '%s\n%s\n' "$clear" "$rows" | rofi_menu "Update errors") || return 0
    [ "$choice" = "$clear" ] && clear_errors
}

clear_errors() {
    local t status
    : >"$CACHE/errors" 2>/dev/null
    read -r t status < <(stamp_get)
    [ "$status" = error ] && echo "$t ok" >"$CACHE/stamp"
}

menu() {
    if pgrep -x rofi >/dev/null 2>&1; then pkill -x rofi; return 0; fi
    local update="󰚰  Update now" refresh_now="󰑐  Refresh now"
    local errors="󰀦  Show errors" clear="󰃢  Clear errors"
    local t status total=0 repo=0 aur=0 header list choice
    read -r t status < <(stamp_get)
    [ -r "$CACHE/count" ] && read -r total repo aur <"$CACHE/count"
    header="Last check: $( ((t > 0)) && date -d "@$t" '+%a %d %b %H:%M') ($(ago "$t"))"
    header+=" · $repo repo · $aur AUR"
    [ "$status" = error ] && header+=" · last run had errors"
    if [ -s "$CACHE/list" ]; then
        list=$(awk -F'\t' '{printf "%-4s  %s\n", $1, $2}' "$CACHE/list" | esc)
    else
        list="System is up to date"
    fi

    choice=$(printf '%s\n' "$update" "$refresh_now" "$errors" "$clear" "$list" \
        | rofi_menu "Updates ($total)" "$(esc <<<"$header")") || return 0
    case "$choice" in
        "$update")
            # shellcheck disable=SC2016 # expanded by the child bash
            setsid -f ghostty --class=dev.gentleman.popup --window-width=0 --window-height=0 \
                --title="System update" -e bash -c \
                'paru -Syu; echo; read -rp "Press Enter to close" _; "$1" --refresh-bg' _ "$SELF" \
                >/dev/null 2>&1 ;;
        "$refresh_now")
            refresh_bg
            notify-send -a Updates -i system-software-update "Updates" "Checking for updates…" 2>/dev/null ;;
        "$errors") show_errors ;;
        "$clear") clear_errors ;;
    esac
}

case "${1:-}" in
    "") print_label ;;
    --refresh) refresh wait ;;
    --refresh-bg) refresh nowait ;;
    --menu) menu ;;
    *) echo "Usage: arch_updates.sh [--refresh|--refresh-bg|--menu]" >&2; exit 2 ;;
esac
