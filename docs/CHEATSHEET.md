# Desktop cheatsheet (i3 on CachyOS)

Every keybind and menu of this setup. Items marked *laptop*, *Bluetooth* or *Acer* only exist on machines where that hardware is detected.

`$mod` = Super (Windows key).

## Keys

| Key | Action |
|---|---|
| `$mod+F1` | **Shortcuts / help menu**: every shortcut and useful command, searchable; Enter runs it (see below) |
| `$mod+d` | App launcher (rofi, icons) |
| `ctrl+space` | Rofi combi (windows + commands), unchanged |
| `$mod+c` | Control center: Wi-Fi, Bluetooth, airplane, audio, mic, displays, connection details, fix connections |
| `$mod+i` | Connection details: IP, DNS, signal, Wi-Fi password, QR code to share Wi-Fi |
| `$mod+Shift+a` | Audio output picker (speakers / HDMI / headset / BT, card profiles) |
| `$mod+Shift+i` | Microphone picker |
| `$mod+p` | Displays menu (extend, mirror, external/laptop only, resolution, UI scale, profiles) |
| `$mod+ctrl+p`, `Fn` display key | Old quick cycle (display-toggle): laptop -> extend -> mirror -> external only |
| `$mod+n` | Thunar file manager |
| `$mod+b` | Bluetooth manager (blueman) |
| `$mod+Shift+e` | Power menu (lock / logout / suspend / reboot / shutdown) |
| `$mod+l` | Lock screen, unchanged |
| `$mod+Shift+p` | Calculator (gnome-calculator, now installed) |
| `$mod+Shift+t` | Temperature / system monitor (btop with live CPU + temperature graphs, floating) |
| `$mod+Shift+b` | **Battery menu**: health, 80 % charge limit, power profile, calibration |
| `Alt+SysRq` + `R E I S U B` | Emergency safe reboot when the desktop is frozen but the kernel is alive (hold Alt+SysRq/PrtSc, type the letters ~1 s apart) |
| `$mod+grave` / `$mod+Shift+grave` | Close all notifications / show the last one again |
| Media keys | play-pause / next / previous (playerctl) |
| Volume / brightness keys | unchanged (xob OSD) |
| `Fn` airplane key | the kernel toggles the radios; a notification shows the new state |
| `Print` / `Shift+Print` | Screenshot area to clipboard / full screen to ~/Pictures/Screenshots, unchanged |
| `Alt+Shift+space` | Switch keyboard layout latam <-> us, unchanged |

## Polybar (top bar)

Left to right: Arch logo (click: launcher, right-click: control center), workspaces (click to switch), CPU, RAM, clock (click: long format), updates (click: opens `paru`), airplane icon (only shown when airplane mode is on; click to turn it off), volume, Wi-Fi, Bluetooth, battery, keyboard icon (shortcuts / help menu), control center icon, power icon, tray.

- Volume: click to open the mixer, right-click to mute, middle-click for the output picker, scroll to change the volume.
- Wi-Fi: shows the network name and signal %. Click for the network picker, middle-click for connection details, right-click to open the connection editor.
- Bluetooth: click to open blueman, right-click to turn it on or off, middle-click for the paired devices menu.
- Battery: percentage, then a yellow `󰌾80` when the 80 % limit is on and the power-profile glyph (󰌪 / 󰾅 / 󰓅). Click for the battery menu, right-click to cycle the power profile. Health appears here only if it falls below 60 %.
- The tray is only on the laptop screen's bar. It holds nm-applet, blueman and udiskie (udiskie only appears when a drive is plugged in).

- Temperature (after CPU): CPU temperature, green < 75°C, yellow ≥ 75, orange ≥ 85, red ≥ 90. It adds "throttled", "critical" or "OFF in Ns" when the thermal guard steps in. Click to open the live monitor (btop), right-click for a summary of every sensor (CPU, GPU + package watts, NVMe, Wi-Fi, CPU frequency, power profile, boost, ryzenadj limits, guard level).

## Shortcuts / help menu (`$mod+F1` or the keyboard icon in the bar)

- First screen: categories with their own icon, color and row count. "All" searches everything at once. Inside a list, type to fuzzy-search keys, commands or descriptions; `Esc` goes back to the categories.
- Row marks: green play = runs the i3 binding (exactly what the key does), blue terminal = runs the command in a floating ghostty popup (`sudo` ones ask for the password there; press Enter to close), green arrow = opens a program or folder, grey copy = information only (Enter copies the key/command and shows a notification).
- Categories: i3 apps & launchers, i3 windows & workspaces (incl. resize-mode keys), System & connections, Media & screenshots, Monitoring, Files & apps (Thunar folders, Notion, WhatsApp, VS Code, Obsidian, Chrome, Thunar keys), Dev toolkit, Terminal commands, Ghostty, tmux, Neovim / LazyVim, yazi, lazygit, Shell (fish, zoxide, atuin, fzf).
- It stays in sync on its own: i3 rows are read from `~/.config/i3/config` (label = the `# desc: ...` comment above a `bindsym`), ghostty rows from `ghostty +list-keybinds`, tmux rows from `~/.tmux.conf`, Neovim rows from `~/.config/nvim/lua` (disabled plugins skipped), yazi custom keys from its keymap.toml.
- Edit the curated lists in `~/.config/shortcuts-menu/*.tsv` (one file per category, `commands.tsv` = Terminal commands). Columns, TAB separated: section, key or command, description, optional kind (`term`, `launch`, `copy`), optional action.
- To give a new i3 binding a clean label, put `# desc: What it does` on the line right above it.
- Results are cached in `~/.cache/shortcuts-menu/` and rebuilt when any source changes. `shortcuts-menu --counts` shows rows per category; `shortcuts-menu --category nvim` opens one category directly.

## Overheating and freezes

- **Thermal guard** (`thermal-guard.service`, always on). It checks CPU, GPU and NVMe temperatures every 2 s:
  - CPU/GPU ≥ 85°C for 20 s: power-saver profile + CPU boost off, with a notification.
  - ≥ 90°C for 10 s: the power limit also drops to 10 W, with a critical notification.
  - ≥ 95°C for 10 s (or NVMe ≥ 90°C): **a red notification that stays on screen plus an alarm sound: "shutting down in 30 s, save your work"**. The countdown updates every 10 s. If the temperature drops below 92°C the shutdown is cancelled ("Shutdown cancelled").
  - ≥ 100°C: it powers off right away (you get one last notification).
  - Below 75°C for a minute: your previous power profile, boost and limits come back.
- **Freeze auto-recovery**: if the whole system hangs (the kernel stops), the hardware watchdog reboots it after about 30 s, and a kernel panic reboots after 10 s. **These can't warn you first**: they only act when the machine is already frozen and nothing can draw on screen anymore. Anything unsaved is lost either way; the reboot just saves you a long power-button press.
- If only the picture freezes but the keyboard still works, try `Alt+SysRq+R E I S U B` first (it syncs the disks and reboots cleanly).
- After a crash, look at what happened: `journalctl -b -1 -p 4 -k` (last boot's kernel warnings) and `sudo ls /var/lib/systemd/pstore` (saved panic logs). The journal keeps up to 500 MB now.
- Turn things off if they misbehave:
  - Guard: `sudo systemctl disable --now thermal-guard`
  - Watchdog reboot: `sudo rm /etc/systemd/system.conf.d/90-watchdog.conf && sudo systemctl daemon-reexec`
  - Lockup panic: edit `/etc/sysctl.d/90-freeze-resilience.conf`, then run `sudo sysctl --system`.
- Base CPU limits (*AMD laptop*, ryzenadj, re-applied every 60 s, at boot and after suspend): 80°C target, 15 W sustained / 20 W boost.

## Battery (*laptop*: `$mod+Shift+b`, or click the battery in the bar)

- **Battery menu** (`$mod+Shift+b`, left-click the battery / lock glyph, or Control center › Battery…): charge %, status, time to full/empty, power draw in W, the **80 % charge limit**, the power profile, and a **Battery health** block: colored bar (green ≥ 80 %, yellow 60–79 %, red < 60 %), full capacity vs design in mAh and Wh, how much was lost since new, a plain-language hint and the history trend with a sparkline.
- **80 % charge limit** (*Acer* "health mode" via acer-wmi-battery, on by default): charging stops at 80 %, which slows wear. Turn it off from the menu before a long trip to get 100 %, then turn it back on. The choice is saved in `/etc/battery-care.conf` and re-applied at boot and after suspend. Bar: yellow `󰌾80` = limit on.
- **Power profile**: unplugging switches to **power-saver** automatically; plugging back in returns to whatever you used on AC last time (balanced by default). Right-click the battery in the bar to cycle power-saver → balanced → performance. Bar glyph: 󰌪 power-saver, 󰾅 balanced, 󰓅 performance. While the thermal guard is throttling, profile changes wait until it recovers (it then restores the right profile for AC/battery).
- **Low battery warnings** (discharging only, once per level per discharge): 20 % normal, 10 % critical, 5 % stays on screen + alarm sound. They never suspend or power off the laptop. (UPower's own last-resort action at 2 % is unchanged.)
- **Health history**: one point per day in `~/.local/share/battery-care/health.csv`. Menu › "Health history chart" opens a chart in a floating terminal. The monthly trend appears after two points at least 7 days apart.
- **Calibration** (menu, only with the charger plugged in): the firmware charges to 100 %, discharges fully and recharges once. It takes hours; leave the laptop idle and choose "Calibration: stop" in the menu afterwards. It can make the reported health more accurate.
- Terminal: `battery-status info`, `battery-status history`, `battery-care status`, logs `journalctl -u battery-care -u battery-care-ac`.
- Turn things off: auto profile → set `AUTO_PROFILE=0` in `/etc/battery-care.conf`; limit → menu (or `pkexec battery-care health off`); warnings → `systemctl --user disable --now battery-alert.timer`.

## Control center (`$mod+c`)

- **Wi-Fi networks**: networks marked `saved` connect using their saved profile, which is never changed. A new network asks for its password and is saved with auto-connect. Enterprise (802.1X) networks open the connection editor.
- **Bluetooth devices**: connect or disconnect paired devices. "Headset mode" switches a BT headset between music mode (A2DP) and headset mode with a working mic (HFP).
- **Airplane mode**: blocks or unblocks every radio.
- **Fix connections**: unblocks the radios, turns them on and restarts NetworkManager and Bluetooth. It asks for your password through polkit.
- **Audio output / Microphone**: switch the default device and move audio that is already playing to it. Devices that aren't plugged in are marked `(unplugged)`. When a device is missing (for example HDMI audio is off), a "Switch profile" entry turns it on.
- **Connection details** (`$mod+i`): the active Wi-Fi or Ethernet connection: name, signal, band and channel, speed, security, IP, gateway, DNS, device, MAC, auto-connect and whether the profile is for all users. Actions:
  - Show password / Copy password. A copied password is cleared from the clipboard after 45 s (unless you copied something else meanwhile).
  - Show QR code to share Wi-Fi: a phone camera scans it and joins the network. The image is deleted when you close its window.
  - Edit this connection, Copy all details (without the password).
  - Enterprise networks (802.1X) show the EAP method and your identity instead; there is no shared password to show.
- **Displays**: layouts, the external monitor's resolution and refresh rate, UI scale 100% <-> 150%, saving and loading layouts as profiles, and arandr.
- CLI: `control-center [wifi|bluetooth|audio|mic|displays|details|airplane|radio-status|fix|status]`.

## Displays

- autorandr applies a saved layout automatically when you plug in a monitor, log in or wake from sleep. Profiles are per machine: save one with `autorandr --save <name>` after arranging the screens. A monitor combination it doesn't know is extended horizontally.
- After any layout change, `~/.config/autorandr/postswitch` restarts polybar and redraws the wallpaper.
- UI scale: sets `Xft.dpi` (96 or 144) in `~/.Xresources`. On X11 this scale applies to all screens at once, not per monitor. The bar changes right away; other apps pick it up after a restart or a new login.
- i3 workspaces are not tied to any output, so unplugging a monitor moves its workspaces to the screen that's left.

## Files

- Thunar: bookmarks for the Drive folders (from `~/.config/drive-sync/remotes.conf`), `~/programming/{personal,work}`, Downloads, Documents and Pictures. Right-click actions: Open Terminal Here, Open in VS Code, Open in Neovim, Copy Path, Drag and Drop (dragon). Thumbnails are on. USB drives are mounted automatically by udiskie.
- yazi (TUI file manager): `Ctrl+n` drags the selected files out with dragon-drop, `Ctrl+t` opens a terminal here, `Ctrl+e` opens the folder in Thunar.
- `dragon-drop file...` gives you a small window to drag files into a browser or chat app.

## Apps

- Notion: opens as a Chrome app window. Look for "Notion" in the launcher.
- Text, Markdown, JSON and code files open in VS Code by default. Folders open in Thunar.
- DaVinci Resolve (not installed): i3 rules are ready. The main window has no border (`$mod+f` for fullscreen) and its dialogs and secondary windows float.

## Bluetooth audio

- The adapter turns on at boot (`AutoEnable`). Headset battery levels are reported (`Experimental`).
- A Bluetooth output is preferred as the default sink when it connects (WirePlumber rule `51-bluez-default-sink.conf`).

## Gentleman toolkit

All terminal tools run in ghostty (Gentleman theme). Every normal fish terminal auto-starts a new tmux session (Gentleman.Dots default in `~/.config/fish/config.fish`).

| Key | Action |
|---|---|
| `$mod+Return` | ghostty (new tmux session), unchanged |
| `$mod+Shift+Return` | ghostty attached to the persistent tmux session `main` (created if missing) |
| `$mod+g` | lazygit in a floating popup (outside a repo it shows the recent-repos picker) |
| `$mod+y` | yazi in a floating popup |
| `$mod+o` | Neovim quick-open: pick a project folder (zoxide + fzf), then nvim opens there (`nvim-project`) |

- Popups use the ghostty class `dev.gentleman.popup` (i3 rule: floating, 80% of the screen, centered). Closing a popup with a running program asks for confirmation (ghostty).
- yazi: text/code files open in Neovim, everything else with xdg-open; `z` jumps with zoxide, `Z` with fzf; `Ctrl+n` dragon-drop, `Ctrl+t` terminal here, `Ctrl+e` Thunar. Colors follow the Gentleman terminal palette (`~/.config/yazi/theme.toml`). In fish, `y` runs yazi and leaves you in its last folder when you quit with `q`.
- Terminal everywhere: i3, rofi (`terminal: ghostty`), Thunar "Open Terminal Here"/"Open in Neovim" (`ghostty --working-directory`), yazi `Ctrl+t`, and the GNOME/GIO default terminal (`gsettings ... default-applications.terminal exec ghostty`).
- Theme: desktop (GTK, rofi, dunst, polybar) is Nord; terminal, tmux, nvim and yazi use the Gentleman palette. Both are dark and cool-toned, so they sit together fine. To fully align later, either switch ghostty/nvim to a Nord theme or recolor rofi/dunst/polybar with the Gentleman palette (not applied).

### Updating (in the future)

| Tool | How it is installed | Update |
|---|---|---|
| Homebrew tools (fish, tmux, starship, zoxide, atuin, carapace, lazygit, neovim, fzf, fd, bat, ripgrep, gentle-ai) | Homebrew (`/home/linuxbrew`) | `brew update && brew upgrade` (restart tmux server after a tmux upgrade: `tmux kill-server`) |
| Neovim plugins | lazy.nvim | back up `~/.config/nvim/lazy-lock.json`, then `nvim --headless "+Lazy! sync" +qa`; rollback: restore the lockfile and run `:Lazy restore`. Mason tools: `:Mason` then `U` |
| engram | pacman package `engram-bin` (AUR) | `paru -Syu engram-bin` |
| gentle-ai (pacman copy) | pacman package `gentle-ai` | `paru -Syu gentle-ai` |
| gga | script `~/.local/bin/gga` | re-run its installer from github.com/Gentleman-Programming/gentleman-guardian-angel when a new release appears |
| ghostty, yazi, fzf, bat, eza, fd, ripgrep (system) | pacman | `sudo pacman -Syu` / `paru` |
| Gentleman.Dots configs | its own installer | compare with github.com/Gentleman-Programming/Gentleman.Dots; merge small changes by hand (local configs are customized) |
