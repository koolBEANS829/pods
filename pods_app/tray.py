"""Tray icon: shown only while the AirPods are connected. Right-click for the menu.

(Left-click can't open it in the right place: on Wayland Qt doesn't know where
the pointer is. Right-click menus are drawn by Plasma itself, at the icon.)
"""
from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import aap
from .control import battery_text

MODES = [("anc", "Noise Cancellation"), ("transparency", "Transparency"),
         ("adaptive", "Adaptive"), ("off", "Off")]


class Tray(QObject):
    def __init__(self, link):
        super().__init__()
        self.link = link
        self.noise = None
        self.menu = QMenu()
        self.battery_lines = [self.menu.addAction("Left —  Right —"), self.menu.addAction("Case —")]
        for line in self.battery_lines:
            line.setEnabled(False)  # information, not buttons
        self.menu.addSeparator()
        self.group = QActionGroup(self.menu)  # makes the four modes radio buttons
        self.modes = {}
        for mode, label in MODES:
            action = QAction(label, self.group, checkable=True)
            action.triggered.connect(lambda _checked=False, m=mode: self._choose(m))
            self.menu.addAction(action)
            self.modes[mode] = action

        # Plasma's tray holds a Qt "quit lock" while the icon shows; hiding the icon
        # releases it, and Qt's default is then to quit the whole app. Never do that.
        QApplication.instance().setQuitLockEnabled(False)
        self.icon = QSystemTrayIcon(QIcon.fromTheme("audio-headphones"))
        self.icon.setContextMenu(self.menu)
        self.icon.setToolTip(link.name)
        link.up.connect(self._up)
        link.down.connect(self.icon.hide)
        link.event.connect(self._on_event)

    def _up(self):
        self.icon.setToolTip(self.link.name)
        self.icon.show()

    def _on_event(self, ev):
        if isinstance(ev, aap.Battery):
            top, case = battery_text(ev).split("\n")
            self.battery_lines[0].setText(top)
            self.battery_lines[1].setText(case)
            self.icon.setToolTip(f"{self.link.name}\n{top}\n{case}")
        elif isinstance(ev, aap.Noise):
            self.noise = ev.mode
            self._tick(ev.mode)

    def _choose(self, mode):
        self.link.send(aap.set_noise(mode))
        self._tick(self.noise)  # undo Qt's tick: it moves when the AirPods confirm, not on click

    def _tick(self, mode):
        self.group.setExclusive(False)  # lets "unknown" mean no tick at all
        for m, action in self.modes.items():
            action.setChecked(m == mode)
        self.group.setExclusive(True)
