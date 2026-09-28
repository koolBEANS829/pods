import os
import tempfile
import unittest

from pods_app import config
from pods_app.aap import Ear
from pods_app.media import EarPause, EarSwitch

BOTH_IN = Ear("in", "in")
ONE_OUT = Ear("in", "out")
BOTH_OUT = Ear("out", "out")
ONE_WORN = Ear("in", "gone")   # other bud dead or not paired right now
NONE_WORN = Ear("out", "gone")


def feed(ep, *ears):
    return [ep.update(e) for e in ears]


class PauseWhenOne(unittest.TestCase):
    def test_first_packet_after_connect_does_nothing(self):
        # Connecting with the buds out must not pause, and with them in must not start music.
        self.assertEqual(feed(EarPause("one"), BOTH_OUT), [None])
        self.assertEqual(feed(EarPause("one"), BOTH_IN), [None])

    def test_one_bud_out_pauses_and_back_in_resumes(self):
        self.assertEqual(feed(EarPause("one"), BOTH_IN, ONE_OUT, BOTH_IN), [None, "pause", "resume"])

    def test_repeat_packets_do_nothing(self):
        self.assertEqual(feed(EarPause("one"), BOTH_IN, BOTH_IN, ONE_OUT, ONE_OUT), [None, None, "pause", None])

    def test_second_bud_out_after_pause_does_not_pause_again(self):
        self.assertEqual(feed(EarPause("one"), BOTH_IN, ONE_OUT, BOTH_OUT), [None, "pause", None])

    def test_resume_waits_for_every_bud_that_was_in(self):
        self.assertEqual(feed(EarPause("one"), BOTH_IN, BOTH_OUT, ONE_OUT, BOTH_IN),
                         [None, "pause", None, "resume"])

    def test_wearing_a_single_bud(self):
        self.assertEqual(feed(EarPause("one"), ONE_WORN, NONE_WORN, ONE_WORN), [None, "pause", "resume"])

    def test_putting_buds_in_without_a_pause_does_not_resume(self):
        self.assertEqual(feed(EarPause("one"), BOTH_OUT, ONE_OUT, BOTH_IN), [None, None, None])

    def test_reset_forgets_a_pause(self):
        ep = EarPause("one")
        feed(ep, BOTH_IN, ONE_OUT)
        ep.reset()  # link dropped
        self.assertEqual(feed(ep, BOTH_IN), [None])


class PauseWhenBoth(unittest.TestCase):
    def test_one_bud_out_keeps_playing(self):
        self.assertEqual(feed(EarPause("both"), BOTH_IN, ONE_OUT), [None, None])

    def test_both_out_pauses_and_either_back_resumes(self):
        self.assertEqual(feed(EarPause("both"), BOTH_IN, BOTH_OUT, ONE_OUT), [None, "pause", "resume"])


class SwitchedOff(unittest.TestCase):
    def test_never_pauses_or_resumes(self):
        ep = EarPause("one")
        ep.enabled = False
        self.assertEqual(feed(ep, BOTH_IN, ONE_OUT, BOTH_IN, BOTH_OUT), [None, None, None, None])

    def test_keeps_counting_buds_so_switching_on_mid_wear_still_pauses(self):
        ep = EarPause("one")
        ep.enabled = False
        feed(ep, BOTH_OUT, BOTH_IN)
        ep.enabled = True
        self.assertEqual(feed(ep, ONE_OUT), ["pause"])

    def test_switching_off_while_paused_never_resumes(self):
        ep = EarPause("one")
        feed(ep, BOTH_IN, ONE_OUT)  # paused
        ep.enabled = False
        self.assertEqual(feed(ep, BOTH_IN), [None])
        ep.enabled = True
        self.assertEqual(feed(ep, ONE_OUT, BOTH_IN), ["pause", "resume"])


class Switch(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "pods", "ear-pause")

    def test_on_when_nothing_saved(self):
        self.assertTrue(EarSwitch(self.path).on)

    def test_off_is_remembered_across_restarts(self):
        EarSwitch(self.path).set(False)
        self.assertFalse(EarSwitch(self.path).on)
        EarSwitch(self.path).set(True)
        self.assertTrue(EarSwitch(self.path).on)

    def test_garbled_file_means_on(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "wb") as f:
            f.write(b"\xff\xfe nope")
        self.assertTrue(EarSwitch(self.path).on)

    def test_changed_fires_only_on_a_real_change(self):
        switch = EarSwitch(self.path)
        seen = []
        switch.changed.connect(seen.append)
        switch.set(True)
        switch.set(False)
        switch.set(False)
        self.assertEqual(seen, [False])

    def test_unwritable_state_still_flips_for_this_run(self):
        switch = EarSwitch("/dev/null/pods/ear-pause")
        switch.set(False)
        self.assertFalse(switch.on)


class Config(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_missing_file_gives_defaults(self):
        self.assertEqual(config.load("/nonexistent/config.toml"), {"pause_when": "one"})

    def test_both(self):
        self.assertEqual(config.load(self.write('pause_when = "both"\n'))["pause_when"], "both")

    def test_bad_value_falls_back_to_default(self):
        self.assertEqual(config.load(self.write('pause_when = "never"\n'))["pause_when"], "one")

    def test_broken_toml_falls_back_to_defaults(self):
        self.assertEqual(config.load(self.write('pause_when = \n')), {"pause_when": "one"})


class BrokenPlayers(unittest.TestCase):
    """A player that errors or hangs must not break ear-pause (review finding I1).

    Only ever asks for PlaybackStatus of fake names: never pauses a real player.
    """

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        from pods_app.media import Media
        self.media = Media()

    def test_vanished_player_has_no_status(self):
        self.assertIsNone(self.media._status("org.mpris.MediaPlayer2.podstest_gone"))

    def test_hung_player_has_no_status(self):
        import subprocess
        import sys
        name = f"org.mpris.MediaPlayer2.podstest_hung{os.getpid()}"
        hung = subprocess.Popen([sys.executable, "-c", f"""
import sys, time
from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection
app = QCoreApplication([])
QDBusConnection.sessionBus().registerService("{name}")
print("ready", flush=True)
time.sleep(10)  # owns the name but never answers, like a frozen browser
"""], stdout=subprocess.PIPE, text=True)
        self.addCleanup(hung.kill)
        self.assertEqual(hung.stdout.readline().strip(), "ready")
        self.assertIsNone(self.media._status(name))


if __name__ == "__main__":
    unittest.main()
