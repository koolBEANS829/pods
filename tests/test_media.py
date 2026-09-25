import os
import tempfile
import unittest

from pods_app import config
from pods_app.aap import Ear
from pods_app.media import EarPause

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


if __name__ == "__main__":
    unittest.main()
