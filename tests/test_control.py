import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from pods_app import aap
from pods_app.client import ask
from pods_app.control import AlreadyRunning, Control
from pods_app.media import EarSwitch

app = QApplication.instance() or QApplication([])


class FakeLink(QObject):
    up = Signal()
    down = Signal()
    event = Signal(object)

    def __init__(self):
        super().__init__()
        self.name = "AirPods Pro"
        self.ready = True
        self.sent = []

    def send(self, packet):
        if not self.ready:
            return False
        self.sent.append(packet)
        return True


def ask_while_qt_runs(path, line, during=None):
    """Run the (blocking) CLI client in a thread while the Qt loop serves it."""
    result = {}
    t = threading.Thread(target=lambda: result.update(r=ask(path, line)))
    t.start()
    loop = QEventLoop()
    if during:
        QTimer.singleShot(100, during)
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if not t.is_alive() else None)
    poll.start(10)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    t.join(1)
    return result["r"]


class ControlSocket(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "pods.sock")
        self.link = FakeLink()
        self.control = Control(self.link, self.path, confirm_ms=300)
        self.control.listen()

    def tearDown(self):
        self.control.close()
        self.dir.cleanup()

    def test_unknown_command_is_an_error(self):
        ok, text = ask_while_qt_runs(self.path, "banana")
        self.assertFalse(ok)
        self.assertIn("unknown command", text)

    def test_noise_change_waits_for_the_airpods_to_confirm(self):
        ok, text = ask_while_qt_runs(self.path, "transparency",
                                     during=lambda: self.link.event.emit(aap.Noise("transparency")))
        self.assertTrue(ok, text)
        self.assertEqual(self.link.sent, [aap.set_noise("transparency")])
        self.assertIn("transparency", text)

    def test_noise_change_not_confirmed_is_an_error(self):
        ok, text = ask_while_qt_runs(self.path, "adaptive")
        self.assertFalse(ok)
        self.assertIn("didn't confirm", text)

    def test_noise_already_set_answers_at_once(self):
        self.link.event.emit(aap.Noise("anc"))
        ok, text = ask_while_qt_runs(self.path, "anc")
        self.assertTrue(ok, text)

    def test_noise_change_when_disconnected_is_an_error(self):
        self.link.ready = False
        ok, text = ask_while_qt_runs(self.path, "anc")
        self.assertFalse(ok)
        self.assertIn("not connected", text)

    def test_battery_reports_the_last_reading(self):
        self.link.event.emit(aap.Battery(left=aap.Level(None, False), right=aap.Level(82, False),
                                         case=aap.Level(40, True), primary="right"))
        ok, text = ask_while_qt_runs(self.path, "battery")
        self.assertTrue(ok, text)
        self.assertIn("Left —", text)
        self.assertIn("Right 82%", text)
        self.assertIn("Case 40% charging", text)

    def test_battery_before_any_reading_is_an_error(self):
        ok, text = ask_while_qt_runs(self.path, "battery")
        self.assertFalse(ok)

    def test_status_names_mode_and_connection(self):
        self.link.event.emit(aap.Noise("adaptive"))
        ok, text = ask_while_qt_runs(self.path, "status")
        self.assertTrue(ok, text)
        self.assertIn("connected", text)
        self.assertIn("adaptive", text)

    def test_link_down_forgets_readings(self):
        self.link.event.emit(aap.Noise("adaptive"))
        self.link.ready = False
        self.link.down.emit()
        ok, text = ask_while_qt_runs(self.path, "status")
        self.assertIn("not connected", text)
        self.assertNotIn("adaptive", text)


class EarCommands(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "pods.sock")
        self.link = FakeLink()
        self.ear = EarSwitch(os.path.join(self.dir.name, "ear-pause"))
        self.control = Control(self.link, self.path, confirm_ms=300, ear=self.ear)
        self.control.listen()

    def tearDown(self):
        self.control.close()
        self.dir.cleanup()

    def test_ear_shows_the_setting(self):
        self.assertEqual(ask_while_qt_runs(self.path, "ear"), (True, "ear pause: on"))

    def test_ear_off_and_on(self):
        self.assertEqual(ask_while_qt_runs(self.path, "ear off"), (True, "ear pause: off"))
        self.assertFalse(self.ear.on)
        self.assertEqual(ask_while_qt_runs(self.path, "ear on"), (True, "ear pause: on"))
        self.assertTrue(self.ear.on)

    def test_works_while_the_airpods_are_away(self):
        self.link.ready = False
        self.assertEqual(ask_while_qt_runs(self.path, "ear off"), (True, "ear pause: off"))

    def test_status_shows_it_while_connected(self):
        self.ear.set(False)
        ok, text = ask_while_qt_runs(self.path, "status")
        self.assertIn("ear pause: off", text)

    def test_ear_with_a_bad_word_is_an_error(self):
        ok, text = ask_while_qt_runs(self.path, "ear maybe")
        self.assertFalse(ok)
        self.assertIn("unknown command", text)


class CliArguments(unittest.TestCase):
    """The pods script itself, with no app running: only argument checking is under test."""

    def cli(self, *args):
        with tempfile.TemporaryDirectory() as d:
            out = subprocess.run([str(Path(__file__).parent.parent / "pods"), *args], capture_output=True,
                                 text=True, env=dict(os.environ, XDG_RUNTIME_DIR=d), timeout=10)
        return out.returncode, out.stderr

    def test_ear_on_and_off_are_accepted(self):
        for args in (["ear"], ["ear", "on"], ["ear", "off"]):
            code, err = self.cli(*args)
            self.assertIn("isn't running", err, args)  # got past argument checking to the socket

    def test_ear_with_a_bad_word_is_refused(self):
        code, err = self.cli("ear", "maybe")
        self.assertEqual(code, 1)
        self.assertIn("unknown command", err)

    def test_other_commands_still_take_no_argument(self):
        code, err = self.cli("anc", "on")
        self.assertIn("unknown command", err)


class SingleInstance(unittest.TestCase):
    def test_second_instance_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pods.sock")
            first = Control(FakeLink(), path)
            first.listen()
            try:
                with self.assertRaises(AlreadyRunning):
                    Control(FakeLink(), path).listen()
                self.assertTrue(os.path.exists(path))  # the live socket was left alone
            finally:
                first.close()

    def test_stale_socket_file_is_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pods.sock")
            open(path, "w").close()  # left behind by a crash; nothing listening
            c = Control(FakeLink(), path)
            c.listen()
            c.close()


class ClientWithoutApp(unittest.TestCase):
    def test_app_not_running_is_a_friendly_error(self):
        ok, text = ask("/nonexistent/pods.sock", "status")
        self.assertFalse(ok)
        self.assertIn("isn't running", text)


if __name__ == "__main__":
    unittest.main()
