# v2 ideas — only after v1 survives a week of real use

- Left-click opens the menu. Needs our own StatusNotifierItem with ItemIsMenu=true
  (Qt's tray reports the cursor at 0,0 on Wayland, so QMenu.popup lands in the corner).
