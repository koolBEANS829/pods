import unittest
from pathlib import Path

from pods_app import aap

FIXTURES = Path(__file__).parent / "fixtures"


def packets(name):
    """Every packet in tests/fixtures/<name>.hex (lines starting with # are notes)."""
    lines = (FIXTURES / f"{name}.hex").read_text().splitlines()
    return [bytes.fromhex(line) for line in lines if line.strip() and not line.startswith("#")]


class Builders(unittest.TestCase):
    def test_noise_packets(self):
        self.assertEqual(aap.set_noise("off").hex(), "0400040009000d01000000")
        self.assertEqual(aap.set_noise("anc").hex(), "0400040009000d02000000")
        self.assertEqual(aap.set_noise("transparency").hex(), "0400040009000d03000000")
        self.assertEqual(aap.set_noise("adaptive").hex(), "0400040009000d04000000")

    def test_unknown_noise_mode_is_refused(self):
        with self.assertRaises(ValueError):
            aap.set_noise("banana")


class RealPackets(unittest.TestCase):
    def test_handshake_ack(self):
        self.assertEqual(aap.parse(packets("handshake_ack")[0]), aap.HandshakeAck())

    def test_noise(self):
        self.assertEqual(aap.parse(packets("noise")[0]), aap.Noise("anc"))

    def test_battery_one_bud_worn(self):
        b = aap.parse(packets("battery")[0])
        self.assertEqual(b.right, aap.Level(10, charging=False))
        self.assertEqual(b.left, aap.Level(None, charging=False))
        self.assertEqual(b.case, aap.Level(None, charging=False))
        self.assertEqual(b.primary, "right")

    def test_ear_secondary_disconnected(self):
        self.assertEqual(aap.parse(packets("ear")[0]), aap.Ear("in", "gone"))


class Malformed(unittest.TestCase):
    def test_unknown_packet_is_ignored(self):
        self.assertIsNone(aap.parse(bytes.fromhex("0400040009001700000000")))

    def test_empty_packet_is_ignored(self):
        self.assertIsNone(aap.parse(b""))

    def test_battery_wrong_length(self):
        good = packets("battery")[0]
        self.assertIsNone(aap.parse(good[:-1]))
        self.assertIsNone(aap.parse(good + b"\x00"))

    def test_battery_count_over_three(self):
        bad = bytes.fromhex("040004000400") + b"\x04" + bytes.fromhex("0201640201") * 4
        self.assertIsNone(aap.parse(bad))

    def test_battery_bad_spacer_bytes(self):
        bad = bytearray(packets("battery")[0])
        bad[8] = 0x07  # first entry's second byte must be 0x01
        self.assertIsNone(aap.parse(bytes(bad)))

    def test_noise_unknown_mode_code(self):
        self.assertIsNone(aap.parse(bytes.fromhex("0400040009000d09000000")))

    def test_ear_too_short(self):
        self.assertIsNone(aap.parse(bytes.fromhex("04000400060000")))


if __name__ == "__main__":
    unittest.main()
