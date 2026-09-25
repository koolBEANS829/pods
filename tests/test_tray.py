import unittest

from PySide6.QtWidgets import QApplication

from pods_app import aap
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


if __name__ == "__main__":
    unittest.main()
