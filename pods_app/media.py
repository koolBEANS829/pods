"""Pause media when a bud leaves an ear, resume when it comes back.

Only ever talks to media players (MPRIS over D-Bus). It never touches audio
devices or PipeWire profiles: that is what broke LinuxPods.
"""
import logging

from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

log = logging.getLogger("pods")
MPRIS = "org.mpris.MediaPlayer2."
TIMEOUT_MS = 1000  # a hung player must not freeze the tray


class EarPause:
    """Decides, from ear packets alone, when to pause and when to resume."""

    def __init__(self, pause_when):
        self.pause_when = pause_when  # "one" or "both" (see config.py)
        self.reset()

    def reset(self):
        self._worn = None       # buds in ears at the last packet; None = none seen since connecting
        self._resume_at = None  # buds that must be back in to resume; None = we haven't paused

    def update(self, ear):
        """Returns "pause", "resume" or None."""
        worn = [ear.primary, ear.secondary].count("in")
        before, self._worn = self._worn, worn
        if before is None or worn == before:
            return None  # first packet after connecting, or nothing changed
        if self._resume_at is None:
            if worn < before and (self.pause_when == "one" or worn == 0):
                self._resume_at = before if self.pause_when == "one" else 1
                return "pause"
        elif worn >= self._resume_at:
            self._resume_at = None
            return "resume"
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
        reply = self.bus.call(msg, QDBus.CallMode.Block, TIMEOUT_MS).arguments()
        return reply[0].variant() if reply else None

    def _call(self, player, method):
        msg = QDBusMessage.createMethodCall(player, "/org/mpris/MediaPlayer2",
                                            "org.mpris.MediaPlayer2.Player", method)
        return self.bus.call(msg, QDBus.CallMode.Block, TIMEOUT_MS).type() == QDBusMessage.MessageType.ReplyMessage

    @staticmethod
    def _short(player):
        return player.removeprefix(MPRIS).split(".")[0]
