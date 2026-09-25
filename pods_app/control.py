"""Local command socket: one line in, one reply out.

`pods anc` (the CLI, see client.py) connects to $XDG_RUNTIME_DIR/pods.sock,
sends "anc", and prints what comes back. The reply starts with "ok" or
"error" so the CLI can exit 0 or 1 honestly.
"""
from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import aap
from .client import COMMANDS


class AlreadyRunning(Exception):
    pass


def pct(level):
    if level.percent is None:
        return "—"
    return f"{level.percent}%" + (" charging" if level.charging else "")


def battery_text(b):
    return f"Left {pct(b.left)}  Right {pct(b.right)}\nCase {pct(b.case)}"


class Control(QObject):
    def __init__(self, link, path, confirm_ms=2000):
        super().__init__()
        self.link = link
        self.path = path
        self.confirm_ms = confirm_ms  # how long the AirPods get to confirm a mode change
        self.battery = None           # last aap.Battery
        self.noise = None             # last mode name
        self._waiting = []            # [(conn, mode, timer)] noise changes not yet confirmed
        link.event.connect(self._on_event)
        link.down.connect(self._forget)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept)

    def listen(self):
        probe = QLocalSocket()
        probe.connectToServer(self.path)
        if probe.waitForConnected(500):
            probe.disconnectFromServer()
            raise AlreadyRunning(f"pods is already running ({self.path} is answering)")
        QLocalServer.removeServer(self.path)  # nobody answered, so any file there is stale
        if not self.server.listen(self.path):
            raise OSError(f"can't listen on {self.path}: {self.server.errorString()}")

    def close(self):
        self.server.close()

    # --- what the AirPods tell us ----------------------------------------

    def _on_event(self, ev):
        if isinstance(ev, aap.Battery):
            self.battery = ev
        elif isinstance(ev, aap.Noise):
            self.noise = ev.mode
            for conn, mode, timer in list(self._waiting):
                if mode == ev.mode:
                    self._reply(conn, True, f"noise: {mode}")

    def _forget(self):
        self.battery = None
        self.noise = None

    # --- the socket -------------------------------------------------------

    def _accept(self):
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            conn.readyRead.connect(lambda c=conn: self._read(c))
            conn.disconnected.connect(lambda c=conn: self._drop(c))

    def _read(self, conn):
        if conn.canReadLine():
            self._handle(conn, bytes(conn.readLine()).decode(errors="replace").strip())

    def _handle(self, conn, line):
        if line in aap.NOISE_CODES:
            if not self.link.ready:
                self._reply(conn, False, "AirPods not connected")
            elif self.noise == line:
                self._reply(conn, True, f"noise: {line}")
            elif not self.link.send(aap.set_noise(line)):
                self._reply(conn, False, "AirPods not connected")
            else:
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self._reply(conn, False, f"the AirPods didn't confirm {line}"))
                self._waiting.append((conn, line, timer))
                timer.start(self.confirm_ms)
        elif line == "battery":
            if self.battery is None:
                self._reply(conn, False, "no battery reading" + ("" if self.link.ready else ": AirPods not connected"))
            else:
                self._reply(conn, True, battery_text(self.battery))
        elif line == "status":
            self._reply(conn, True, self._status())
        else:
            self._reply(conn, False, f"unknown command '{line}' (try: {', '.join(COMMANDS)})")

    def _status(self):
        if not self.link.ready:
            return f"{self.link.name}: not connected"
        lines = [f"{self.link.name}: connected", f"noise: {self.noise or 'unknown'}"]
        if self.battery:
            lines.append(battery_text(self.battery))
        return "\n".join(lines)

    def _reply(self, conn, ok, text):
        self._unwait(conn)
        conn.write((("ok" if ok else "error") + "\n" + text + "\n").encode())
        conn.flush()
        conn.disconnectFromServer()

    def _unwait(self, conn):
        for entry in [w for w in self._waiting if w[0] is conn]:
            entry[2].stop()
            entry[2].deleteLater()
            self._waiting.remove(entry)

    def _drop(self, conn):
        self._unwait(conn)  # the CLI gave up (Ctrl+C); never write to it after this
        conn.deleteLater()
