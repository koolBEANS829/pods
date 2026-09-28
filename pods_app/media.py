"""Pause media when a bud leaves an ear, resume when it comes back.

Only ever talks to media players (MPRIS over D-Bus). It never touches audio
devices or PipeWire profiles: that is what broke LinuxPods.
"""
import logging
import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

log = logging.getLogger("pods")
MPRIS = "org.mpris.MediaPlayer2."
TIMEOUT_MS = 1000  # a hung player must not freeze the tray
STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "pods" / "ear-pause"


class EarSwitch(QObject):
    """Ear-detect pause on or off: flipped from the tray or `pods ear on|off`, remembered across restarts.

    Saved as the word "on" or "off". No file, or anything else in it, means on.
    """
    changed = Signal(bool)

    def __init__(self, path=STATE):
        super().__init__()
        self.path = Path(path)
        try:
            self.on = self.path.read_bytes().strip() != b"off"
        except OSError:
            self.on = True

    def set(self, on):
        if on == self.on:
            return
        self.on = on
        log.info("ear pause: %s", "on" if on else "off")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("on\n" if on else "off\n")
        except OSError as e:
            log.warning("can't save ear pause to %s: %s (it resets to on at the next start)", self.path, e)
        self.changed.emit(on)


class EarPause:
    """Decides, from ear packets alone, when to pause and when to resume."""

    def __init__(self, pause_when):
        self.pause_when = pause_when  # "one" or "both" (see config.py)
        self.enabled = True           # False: keep counting buds, but never pause or resume (EarSwitch)
        self.reset()

    def reset(self):
        self._worn = None       # buds in ears at the last packet; None = none seen since connecting
        self._resume_at = None  # buds that must be back in to resume; None = we haven't paused
        self._last = None       # the last ear packet, for switch()

    def update(self, ear):
        """Returns "pause", "resume" or None."""
        worn = [ear.primary, ear.secondary].count("in")
        before, self._worn = self._worn, worn
        self._last = ear
        if before is None or worn == before:
            return None  # first packet after connecting, or nothing changed
        if not self.enabled:
            return None
        if self._resume_at is None:
            if worn < before and (self.pause_when == "one" or worn == 0):
                self._resume_at = before if self.pause_when == "one" else 1
                return "pause"
        elif worn >= self._resume_at:
            self._resume_at = None
            return "resume"
        return None

    def switch(self, on):
        """Turns ear pause on or off, acting on where the buds are right now.

        Returns "pause" (switched on with a bud out), "resume" (switched off while
        we're holding music paused) or None.
        """
        self.enabled = on
        if not on:
            if self._resume_at is None:
                return None
            self._resume_at = None
            return "resume"
        if self._last is None or self._resume_at is not None:
            return None
        buds = [self._last.primary, self._last.secondary]
        worn, out = buds.count("in"), buds.count("out")  # a bud in its case or gone isn't "out"
        if out and (self.pause_when == "one" or worn == 0):
            self._resume_at = worn + out if self.pause_when == "one" else 1
            return "pause"
        return None


class Media:
    """Pauses whatever is playing, and later resumes only those players."""

    def __init__(self):
        self.bus = QDBusConnection.sessionBus()
        self._paused = []

    def pause(self):
        self._paused = [p for p in self._players() if self._status(p) == "Playing" and self._call(p, "Pause")]
        log.info("paused: %s", ", ".join(self._short(p) for p in self._paused) or "nothing was playing")

    def resume(self):
        for p in self._paused:
            self._call(p, "Play")
        log.info("resumed: %s", ", ".join(self._short(p) for p in self._paused) or "nothing")
        self._paused = []

    def forget(self):
        self._paused = []

    def _players(self):
        msg = QDBusMessage.createMethodCall("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                            "org.freedesktop.DBus", "ListNames")
        reply = self.bus.call(msg, QDBus.CallMode.Block, TIMEOUT_MS).arguments()
        return [name for name in (reply[0] if reply else []) if name.startswith(MPRIS)]

    def _status(self, player):
        msg = QDBusMessage.createMethodCall(player, "/org/mpris/MediaPlayer2",
                                            "org.freedesktop.DBus.Properties", "Get")
        msg.setArguments(["org.mpris.MediaPlayer2.Player", "PlaybackStatus"])
        reply = self.bus.call(msg, QDBus.CallMode.Block, TIMEOUT_MS)
        if reply.type() != QDBusMessage.MessageType.ReplyMessage:
            return None  # the player vanished or hung; an error's first argument is its text, not a status
        return reply.arguments()[0].variant()

    def _call(self, player, method):
        msg = QDBusMessage.createMethodCall(player, "/org/mpris/MediaPlayer2",
                                            "org.mpris.MediaPlayer2.Player", method)
        return self.bus.call(msg, QDBus.CallMode.Block, TIMEOUT_MS).type() == QDBusMessage.MessageType.ReplyMessage

    @staticmethod
    def _short(player):
        return player.removeprefix(MPRIS).split(".")[0]
