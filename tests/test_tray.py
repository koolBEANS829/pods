import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from pods_app import aap
from pods_app.media import EarSwitch
from pods_app.tray import Tray
from tests.test_control import FakeLink

app = QApplication.instance() or QApplication([])


class TrayIcon(unittest.TestCase):
    def setUp(self):
        self.link = FakeLink()
        self.tray = Tray(self.link)

    def test_hidden_until_the_link_is_up(self):
        self.assertFalse(self.tray.icon.isVisible())
        self.link.up.emit()
        self.assertTrue(self.tray.icon.isVisible())
        self.link.down.emit()
        self.assertFalse(self.tray.icon.isVisible())

    def test_battery_lines(self):
        self.link.event.emit(aap.Battery(left=aap.Level(82, False), right=aap.Level(79, False),
                                         case=aap.Level(None, False), primary="left"))
        self.assertEqual([a.text() for a in self.tray.battery_lines], ["Left 82%  Right 79%", "Case —"])
        self.assertFalse(self.tray.battery_lines[0].isEnabled())

    def test_click_sends_but_only_the_airpods_move_the_tick(self):
        self.link.event.emit(aap.Noise("anc"))
        self.tray.modes["transparency"].trigger()
        self.assertEqual(self.link.sent, [aap.set_noise("transparency")])
        self.assertTrue(self.tray.modes["anc"].isChecked())
        self.assertFalse(self.tray.modes["transparency"].isChecked())
        self.link.event.emit(aap.Noise("transparency"))
        self.assertTrue(self.tray.modes["transparency"].isChecked())
        self.assertFalse(self.tray.modes["anc"].isChecked())

    def test_stem_press_moves_the_tick(self):
        self.link.event.emit(aap.Noise("adaptive"))
        self.assertEqual([m for m, a in self.tray.modes.items() if a.isChecked()], ["adaptive"])


class EarPauseLine(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ear = EarSwitch(os.path.join(self.dir.name, "ear-pause"))
        self.tray = Tray(FakeLink(), ear=self.ear)

    def test_ticked_while_on(self):
        self.assertEqual(self.tray.ear_line.text(), "Pause when removed")
        self.assertTrue(self.tray.ear_line.isChecked())

    def test_click_flips_the_switch(self):
        self.tray.ear_line.trigger()
        self.assertFalse(self.ear.on)
        self.assertFalse(self.tray.ear_line.isChecked())
        self.tray.ear_line.trigger()
        self.assertTrue(self.ear.on)

    def test_follows_the_cli(self):
        self.ear.set(False)
        self.assertFalse(self.tray.ear_line.isChecked())
        self.ear.set(True)
        self.assertTrue(self.tray.ear_line.isChecked())

    def test_starts_unticked_when_saved_off(self):
        self.ear.set(False)
        self.assertFalse(Tray(FakeLink(), ear=self.ear).ear_line.isChecked())


class NeverQuits(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("WAYLAND_DISPLAY"), "needs the real Plasma tray")
    def test_hiding_the_icon_does_not_quit_the_app(self):
        # Plasma's tray keeps the app alive with a Qt "quit lock" while the icon shows.
        # Hiding it (AirPods into the case) dropped the last lock and Qt quit the whole
        # app with exit code 0, so systemd didn't restart it. Seen live 2026-09-25.
        # PySide6 can't fake that lock, so this shows a real icon for about a second.
        program = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
from pods_app.tray import Tray
from tests.test_control import FakeLink
link = FakeLink()
tray = Tray(link)
QTimer.singleShot(300, link.up.emit)
QTimer.singleShot(1000, link.down.emit)
QTimer.singleShot(2500, lambda: (print("alive"), app.quit()))
app.exec()
"""
        env = dict(os.environ, QT_QPA_PLATFORM="wayland")
        out = subprocess.run([sys.executable, "-c", program], cwd=Path(__file__).parent.parent,
                             env=env, capture_output=True, text=True, timeout=15)
        self.assertIn("alive", out.stdout, "the app quit when its tray icon was hidden")

if __name__ == "__main__":
    unittest.main()
