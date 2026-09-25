import unittest

from pods_app.link import AAP_UUID, Backoff, pick_device

OTHER = "0000110b-0000-1000-8000-00805f9b34fb"


class BackoffDelays(unittest.TestCase):
    def test_doubles_then_caps_at_30s(self):
        b = Backoff()
        self.assertEqual([b.next() for _ in range(7)], [1000, 2000, 4000, 8000, 16000, 30000, 30000])

    def test_reset_starts_over(self):
        b = Backoff()
        b.next(); b.next()
        b.reset()
        self.assertEqual(b.next(), 1000)


class PickDevice(unittest.TestCase):
    def test_picks_the_airpods_by_uuid(self):
        devices = [("/org/bluez/hci0/dev_speaker", [OTHER], True),
                   ("/org/bluez/hci0/dev_pods", [OTHER, AAP_UUID], False)]
        self.assertEqual(pick_device(devices), "/org/bluez/hci0/dev_pods")

    def test_prefers_connected_airpods(self):
        devices = [("/org/bluez/hci0/dev_old", [AAP_UUID], False),
                   ("/org/bluez/hci0/dev_new", [AAP_UUID], True)]
        self.assertEqual(pick_device(devices), "/org/bluez/hci0/dev_new")

    def test_none_when_no_airpods_paired(self):
        self.assertIsNone(pick_device([("/org/bluez/hci0/dev_speaker", [OTHER], True)]))


if __name__ == "__main__":
    unittest.main()
