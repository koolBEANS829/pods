# pods

A small AirPods controller for Linux. One Python process gives you:

- `pods anc | transparency | adaptive | off`: noise control, confirmed by the AirPods
  themselves (the command exits 1 if they don't confirm)
- `pods battery` and `pods status`
- **Ear-detect pause**: take a bud out and whatever is playing pauses; put it back and
  those players resume
  - Turn it off or on with **Pause when removed** in the tray menu, or `pods ear off` /
    `pods ear on` (`pods ear` shows it). The choice is remembered across restarts, in
    `~/.local/state/pods/ear-pause`.
- A **tray icon**, shown only while the AirPods are connected. Right-click it for battery
  levels and the noise modes.

## Why another one

LinuxPods and LibrePods' Linux app switch the AirPods' PipeWire card profile to `off`
when both buds come out. On reconnect they can miss switching it back, and the AirPods
then connect with working controls but **no sound**. `pods` never touches audio devices,
card profiles or the default sink. Ear detection only pauses and plays media players over
MPRIS.

## Requirements

- Linux with BlueZ, and your AirPods already paired
- A Python ≥ 3.11 that has `socket.AF_BLUETOOTH` and PySide6. Your distro's own Python is
  the safe bet. Homebrew and conda builds often lack Bluetooth sockets, so the script's
  shebang is `/usr/bin/python3`. On Fedora: `sudo dnf install python3-pyside6`.
- Only one program can hold the AirPods' control channel. Quit any other AirPods app first.

Tested on AirPods Pro 3 (A3063), Fedora 44 and KDE Plasma 6 (Wayland). Other models that
speak the same protocol may work, but they are untested.

## Install

```sh
git clone https://github.com/koolBEANS829/pods ~/projects/pods   # pods.service expects this path
ln -s ~/projects/pods/pods ~/.local/bin/pods
cp ~/projects/pods/pods.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now pods
ln -s ~/projects/pods/pods.fish ~/.config/fish/completions/pods.fish   # optional, fish users
```

Logs: `journalctl --user -u pods -f`.

## Config

`~/.config/pods/config.toml` (optional):

```toml
pause_when = "one"    # pause when either bud leaves an ear (default, like Apple)
# pause_when = "both" # keep playing until both are out
```

## Tests

```sh
cd ~/projects/pods && /usr/bin/python3 -m unittest
```

The protocol tests run against real packets captured from a pair of AirPods Pro 3. On a
Wayland desktop, one test shows a real tray icon for about a second.

## Credits

The protocol facts come from [LibrePods](https://github.com/librepods-org/librepods)'
AAP definitions and from LinuxPods. The code here is written from scratch. Licensed
GPL-3.0, like them.
