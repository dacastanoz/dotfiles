# dotfiles: CachyOS + i3 desktop

A lightweight, Nord-themed i3 desktop for CachyOS, managed with [chezmoi](https://www.chezmoi.io/).
One command installs the packages, the user configs and the system tweaks, and adapts them to the machine
(laptop or desktop, Wi-Fi, Bluetooth, AMD or Intel).

## Quick path

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply dacastanoz
```

1. Enter your sudo password when asked (packages and `/etc` files).
2. Do the [post-install steps](#post-install-steps).
3. Reboot.

Preview first, without changing anything:

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init dacastanoz   # clone only
chezmoi diff                                              # what would change
chezmoi apply                                             # when you are happy
```

## What it does

| Step | Script / files | Result |
|------|----------------|--------|
| 1. Packages | `run_once_before_00-packages.sh` + `packages/*.txt` | pacman, AUR (paru) and brew packages; only missing ones are installed |
| 2. Dotfiles | `dot_config/`, `dot_local/`, `dot_gtkrc-2.0` | i3, polybar, rofi, dunst, picom, ghostty, yazi, Thunar, GTK/Qt theme, btop, scripts |
| 3. System | `run_onchange_after_10-system.sh` + `system/` | sysctl, journald, oomd, watchdog, thermal guard, NetworkManager, Bluetooth, kernel cmdline |
| 4. User | `run_onchange_after_20-user.sh` | user units, icon folder color, gsettings, i3 reload |

Every `/etc` file that gets replaced is backed up once as `<file>.bak-chezmoi`.
Scripts are idempotent: running `chezmoi apply` again only changes what differs.

## Machine detection

Detected automatically by `.chezmoi.toml.tmpl` at `chezmoi init` (no prompts):

| Detected | How | What changes |
|----------|-----|--------------|
| Battery (`hasBattery`) | `/sys/class/power_supply/*/type = Battery` | polybar battery modules, battery menu (`$mod+Shift+b`), auto power profile on AC/battery, low-battery alerts, health history |
| Wi-Fi (`hasWifi`) | `/sys/class/net/*/wireless` | polybar network module, control-center Wi-Fi rows, NetworkManager tweaks |
| Bluetooth (`hasBluetooth`) | `/sys/class/bluetooth/*` | blueman/bluez packages, polybar module, control-center rows, `$mod+b`, `main.conf` |
| AMD Ryzen (`hasRyzen`) | `/proc/cpuinfo` vendor | hardware watchdog (`sp5100_tco`, only if it loads) |
| AMD laptop (`isAMDLaptop`) | Ryzen + battery | `ryzenadj` power/thermal limits |
| Acer laptop (`isAcerLaptop`) | DMI vendor + battery | `acer-wmi-battery-dkms` 80 % charge limit |
| AMD GPU (`hasAMDGPU`) | DRM vendor `0x1002` | `amdgpu.gpu_recovery=1` on the kernel cmdline |
| CPU sensor (`cpuSensor`) | hwmon `k10temp` / `coretemp` / `zenpower` | polybar temperature, btop sensor, thermal guard (k10temp only) |
| limine (`hasLimine`) | `/etc/default/limine` | kernel cmdline edits + `limine-update` |

See the values for this machine with `chezmoi data | grep -A20 '"hasBattery"'`.
After a hardware change, refresh them with `chezmoi init && chezmoi apply`.

## Post-install steps

- [ ] **Google Drive sync** (optional): `rclone config` to create the remotes, then
  `cp ~/.config/drive-sync/remotes.conf.example ~/.config/drive-sync/remotes.conf`, edit it,
  run `drive-sync --resync <name>` once per remote and `chezmoi apply` (enables `drive-sync.timer`).
- [ ] **Displays**: arrange screens (`$mod+p` or `arandr`), then `autorandr --save <name>` (profiles are per machine and not in the repo).
- [ ] **Wallpaper**: put an image at `~/.config/i3/wallpaper.png` (not shipped).
- [ ] **Terminal toolkit**: install [Gentleman.Dots](https://github.com/Gentleman-Programming/Gentleman.Dots) with its own installer (nvim, tmux, fish, starship, ghostty shaders).
- [ ] **Browser**: Chrome/Brave, Settings > Performance > Memory Saver on (RAM is tight on 8 GB laptops).
- [ ] **Reboot**: needed for the kernel cmdline, watchdog and Wi-Fi driver options (the system script lists them).

## Daily use

| Task | Command |
|------|---------|
| Pull and apply the latest repo | `chezmoi update` |
| See what differs on this machine | `chezmoi diff` |
| Save a config you changed on this machine | `chezmoi re-add ~/.config/i3/config` (plain files) or `chezmoi edit ~/.config/polybar/config.ini` (templates) |
| Publish your changes | `chezmoi cd && git add -A && git commit -m "feat(i3): ..." && git push` |
| Add a new file | `chezmoi add ~/.config/foo/bar.conf` |

Templates (`*.tmpl`) cannot be re-added: edit them with `chezmoi edit` so the machine conditions survive.

## Keybinds

`$mod` is the Super key. Full list: [docs/CHEATSHEET.md](docs/CHEATSHEET.md), or press `$mod+F1` for the searchable shortcuts menu.

| Key | Action |
|-----|--------|
| `$mod+d` | App launcher |
| `$mod+c` | Control center (Wi-Fi, Bluetooth, audio, displays, airplane) |
| `$mod+i` | Connection details, Wi-Fi password / QR |
| `$mod+p` | Displays menu |
| `$mod+n` | Thunar |
| `$mod+Shift+a` / `$mod+Shift+i` | Audio output / microphone picker |
| `$mod+Shift+t` | Temperature and system monitor |
| `$mod+Shift+b` | Battery menu (laptops) |
| `$mod+Shift+e` | Power menu |
| `$mod+F1` | Shortcuts menu |
| `$mod+g` / `$mod+y` / `$mod+o` | lazygit / yazi / Neovim project picker popups |

## Safety and rollback

| Feature | Turn it off |
|---------|-------------|
| Thermal guard (throttles, then powers off at 95 °C after a 30 s warning) | `sudo systemctl disable --now thermal-guard` |
| Hardware watchdog reboot after a hard freeze | `sudo rm /etc/systemd/system.conf.d/90-watchdog.conf /etc/modprobe.d/blacklist.conf /etc/modules-load.d/sp5100_tco.conf && sudo systemctl daemon-reexec` |
| Kernel lockup panics (reboot 10 s after a panic) | edit `/etc/sysctl.d/90-freeze-resilience.conf`, then `sudo sysctl --system` |
| Kernel cmdline changes | `sudo cp /etc/default/limine.bak-chezmoi /etc/default/limine && sudo limine-update` |
| Battery care (auto profile, charge limit) | `sudo systemctl disable --now battery-care`; limit only: `pkexec battery-care health off`; alerts: `systemctl --user disable --now battery-alert.timer` |
| ryzenadj limits (15 W / 20 W, 80 °C) | `sudo systemctl disable --now ryzenadj.timer ryzenadj.service` |
| Any other `/etc` file | restore `<file>.bak-chezmoi` |

The ryzenadj limits were tuned for a 15 W Ryzen 7 5700U. On a different APU review
`/usr/local/bin/ryzenadj-apply` (`chezmoi cd` then `system/usr/local/bin/ryzenadj-apply`).

## Intentionally excluded

| Not in the repo | Why / where it comes from |
|-----------------|---------------------------|
| `~/.config/rclone/rclone.conf`, `remotes.conf`, bisync state | OAuth tokens and personal folder names |
| NetworkManager connections, keyrings, SSH/GPG, `gh`/cloud CLI configs | secrets |
| autorandr profiles | contain monitor EDIDs, per machine |
| nvim, tmux, fish (except `functions/y.fish`), starship, ghostty shaders | owned by Gentleman.Dots and its installer |
| Browser profiles, caches, logs, `*.bak*` files | machine state |
| Wallpaper | image license unknown |

## Layout

```text
.chezmoi.toml.tmpl        machine detection (data for all templates)
.chezmoitemplates/        shared template snippets
dot_config/, dot_local/   files placed in $HOME (*.tmpl are rendered per machine)
packages/                 pacman.txt, aur.txt, brew.txt
system/                   files copied to / by the system script
run_*.sh.tmpl             bootstrap scripts (packages, system, user)
docs/CHEATSHEET.md        every keybind and menu
```

## License

[MIT](LICENSE)
