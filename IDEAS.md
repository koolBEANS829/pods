# v2 ideas — only after v1 survives a week of real use

- Left-click opens the menu. Needs our own StatusNotifierItem with ItemIsMenu=true
  (Qt's tray reports the cursor at 0,0 on Wayland, so QMenu.popup lands in the corner).

## Known rough edges (from the v1 code review, 2026-09-25; none seen in real use yet)

- If sending the notification request fails mid-handshake, the link counts as up with no
  socket for ~7s, then heals itself.
- Resume plays a player you paused *again* by hand while the bud was out.
- A noise command in flight when the AirPods disconnect says "didn't confirm" rather than
  "disconnected" (exit code is still 1).
- After a reconnect the tray shows the previous battery lines until the first new reading.
- Rare socket errors (permission, reset) make the CLI print a traceback.
- Invalid UTF-8 in config.toml stops startup (systemd gives up after 5 tries a minute).
- A manual `pods run` holding the socket makes the service fail its 5 starts and stop.
- `PODS_DEBUG=1` logs every packet, including the one carrying the AirPods' serial numbers.
- BlueZ property reads use Qt's 25s default timeout on the GUI thread.
- The link state machine and the MPRIS calls have no unit tests of their own.
