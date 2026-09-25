"""L2CAP link to the AirPods, driven by BlueZ connect/disconnect events.

BlueZ (the system Bluetooth service) tells us when the AirPods connect. We then
open our own channel to them (L2CAP, PSM 0x1001), do the AAP handshake, and
emit every packet they send us. If the channel drops while BlueZ still says
"connected", we redial with a growing delay.
"""
import errno
import logging
import os
import socket
import xml.etree.ElementTree as ET

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal, Slot, SLOT
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from . import aap

AAP_UUID = "74ec2172-0bad-4d01-8f77-997b2be0722a"
AAP_PSM = 0x1001
DIAL_DELAY_MS = 1500        # BlueZ says "connected" a moment before the AirPods will answer
HANDSHAKE_TIMEOUT_MS = 5000
NOTIFY_AGAIN_MS = 2000

log = logging.getLogger("pods")


class Backoff:
    """Retry delays in ms: 1s, 2s, 4s... never more than 30s."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._delay = 1000

    def next(self):
        delay = self._delay
        self._delay = min(delay * 2, 30000)
        return delay


def pick_device(devices):
    """devices: [(dbus_path, uuids, connected)]. Returns the AirPods' path, or None.

    AirPods are recognised by the AAP service UUID, not by a hard-coded address.
    A connected pair wins over one that's only paired.
    """
    pods = [d for d in devices if AAP_UUID in d[1]]
    pods.sort(key=lambda d: not d[2])  # False sorts first, so connected ones lead
    return pods[0][0] if pods else None


def _children(bus, path, service="org.bluez"):
    """Child object paths under a BlueZ path (adapters under /org/bluez, devices under an adapter)."""
    reply = QDBusInterface(service, path, "org.freedesktop.DBus.Introspectable", bus).call("Introspect")
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        return []  # bluetoothd isn't answering; start() looks again later
    return [f"{path}/{node.get('name')}" for node in ET.fromstring(reply.arguments()[0]).findall("node")]


def _bluez_devices(bus):
    devices = []
    for adapter in _children(bus, "/org/bluez"):
        for path in _children(bus, adapter):
            dev = QDBusInterface("org.bluez", path, "org.bluez.Device1", bus)
            if dev.isValid():
                devices.append((path, dev.property("UUIDs") or [], bool(dev.property("Connected"))))
    return devices


class Link(QObject):
    up = Signal()          # handshake done; send() works now
    down = Signal()        # the link that was up has gone
    event = Signal(object)  # one aap.Battery / aap.Ear / aap.Noise from the AirPods

    def __init__(self):
        super().__init__()
        self.bus = QDBusConnection.systemBus()
        self.name = "AirPods"
        self.ready = False
        self._dev = None
        self._mac = None
        self._sock = None
        self._notifier = None
        self._backoff = Backoff()
        self._dial_timer = self._timer(self._dial)
        self._handshake_timer = self._timer(lambda: self._close("no answer from the AirPods", retry=True))
        self._notify_again = self._timer(lambda: self._send(aap.REQUEST_NOTIFICATIONS))

    def _timer(self, callback):
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(callback)
        return t

    # --- BlueZ side -------------------------------------------------------

    def start(self):
        path = pick_device(_bluez_devices(self.bus))
        if path is None:
            delay = self._backoff.next()
            log.info("no paired AirPods found; looking again in %ds", delay // 1000)
            QTimer.singleShot(delay, self.start)
            return
        self._backoff.reset()
        self._dev = QDBusInterface("org.bluez", path, "org.bluez.Device1", self.bus)
        self._mac = self._dev.property("Address")
        self.name = self._dev.property("Alias") or "AirPods"
        self.bus.connect("org.bluez", path, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                         self, SLOT("_bluez_changed(QDBusMessage)"))
        log.info("watching %s (%s)", self.name, self._mac)
        if self._bluez_connected():
            self._dial_timer.start(DIAL_DELAY_MS)

    def _bluez_connected(self):
        return bool(self._dev.property("Connected"))

    @Slot(QDBusMessage)
    def _bluez_changed(self, _msg):
        # Fires for any property change (battery, signal strength...), so just re-read "Connected".
        if self._bluez_connected():
            if self._sock is None and not self._dial_timer.isActive():
                log.info("bluetooth connected")
                self._backoff.reset()
                self._dial_timer.start(DIAL_DELAY_MS)
        else:
            self._dial_timer.stop()
            if self._sock is not None:
                self._close("bluetooth disconnected", retry=False)

    # --- AAP channel ------------------------------------------------------

    def send(self, packet):
        """Send one packet. False if the link isn't up."""
        return self.ready and self._send(packet)

    def _dial(self):
        if not self._bluez_connected():
            return
        sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        sock.setblocking(False)
        err = sock.connect_ex((self._mac, AAP_PSM))
        if err not in (0, errno.EINPROGRESS, errno.EAGAIN):
            sock.close()
            log.info("can't open AirPods channel: %s", os.strerror(err))
            self._dial_timer.start(self._backoff.next())
            return
        self._sock = sock
        self._watch(QSocketNotifier.Type.Write, self._dialed)
        self._handshake_timer.start(HANDSHAKE_TIMEOUT_MS)

    def _watch(self, kind, callback):
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
        self._notifier = QSocketNotifier(self._sock.fileno(), kind, self)
        self._notifier.activated.connect(callback)

    def _dialed(self):
        err = self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err:
            self._close(f"can't open AirPods channel: {os.strerror(err)}", retry=True)
            return
        self._watch(QSocketNotifier.Type.Read, self._readable)
        self._send(aap.HANDSHAKE)

    def _readable(self):
        try:
            packet = self._sock.recv(1024)
        except BlockingIOError:
            return
        except OSError as e:
            self._close(f"read failed: {e.strerror}", retry=True)
            return
        if not packet:
            self._close("the AirPods closed the channel", retry=True)
            return
        log.debug("<< %s", packet.hex())
        ev = aap.parse(packet)
        if isinstance(ev, aap.HandshakeAck):
            self._send(aap.SET_FEATURES)
        elif isinstance(ev, aap.FeaturesAck) and not self.ready:
            self._send(aap.REQUEST_NOTIFICATIONS)
            self._notify_again.start(NOTIFY_AGAIN_MS)  # they sometimes miss the first one
            self._handshake_timer.stop()
            self._backoff.reset()
            self.ready = True
            self.up.emit()
        elif isinstance(ev, aap.LinkDrop):
            self._close("the AirPods dropped the channel", retry=True)
        elif ev is not None and not isinstance(ev, aap.FeaturesAck):
            self.event.emit(ev)

    def _send(self, packet):
        if self._sock is None:
            return False
        try:
            self._sock.send(packet)
            return True
        except OSError as e:
            self._close(f"send failed: {e.strerror}", retry=True)
            return False

    def _close(self, reason, retry):
        was_up = self.ready
        self.ready = False
        self._handshake_timer.stop()
        self._notify_again.stop()
        if self._notifier is not None:
            self._notifier.setEnabled(False)  # before the socket closes, or Qt watches a dead fd
            self._notifier.deleteLater()
            self._notifier = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        log.info("link down: %s", reason)
        if was_up:
            self.down.emit()
        if retry and self._bluez_connected():
            delay = self._backoff.next()
            log.info("retrying in %ds", delay // 1000)
            self._dial_timer.start(delay)
