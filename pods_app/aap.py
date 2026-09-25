"""AirPods AAP protocol: packet builders and parsers. No I/O.

This is the only file that knows what the bytes mean. Everything else asks
parse() what a packet is and gets back one of the small classes below.
"""
from dataclasses import dataclass

# Sent in this order when the link opens (see link.py).
HANDSHAKE = bytes.fromhex("00000400010002000000000000000000")
SET_FEATURES = bytes.fromhex("040004004d00d700000000000000")
REQUEST_NOTIFICATIONS = bytes.fromhex("040004000f00ffffffffff")

NOISE_CODES = {"off": 0x01, "anc": 0x02, "transparency": 0x03, "adaptive": 0x04}
NOISE_NAMES = {code: name for name, code in NOISE_CODES.items()}

_NOISE = bytes.fromhex("0400040009000d")
_BATTERY = bytes.fromhex("040004000400")
_EAR = bytes.fromhex("040004000600")
_HANDSHAKE_ACK = bytes.fromhex("01000400")
_FEATURES_ACK = bytes.fromhex("040004002b00")
_LINK_DROP = bytes.fromhex("00010000")

_COMPONENTS = {0x02: "right", 0x04: "left", 0x08: "case"}
_EAR_STATES = {0x00: "in", 0x01: "out", 0x02: "case"}  # anything else: "gone"


@dataclass(frozen=True)
class HandshakeAck:
    pass


@dataclass(frozen=True)
class FeaturesAck:
    pass


@dataclass(frozen=True)
class LinkDrop:
    pass


@dataclass(frozen=True)
class Noise:
    mode: str  # "off" | "anc" | "transparency" | "adaptive"


@dataclass(frozen=True)
class Level:
    percent: int | None  # None = that part isn't reporting (show "—", not 0%)
    charging: bool


@dataclass(frozen=True)
class Battery:
    left: Level
    right: Level
    case: Level
    primary: str  # "left" | "right" — the first bud listed in the packet


@dataclass(frozen=True)
class Ear:
    primary: str  # "in" | "out" | "case" | "gone"
    secondary: str


def set_noise(mode):
    """The packet that switches noise control to `mode`."""
    if mode not in NOISE_CODES:
        raise ValueError(f"unknown noise mode: {mode}")
    return _NOISE + bytes([NOISE_CODES[mode], 0, 0, 0])


def parse(p):
    """Turn one packet into one of the classes above, or None if we don't use it."""
    if p.startswith(_HANDSHAKE_ACK):
        return HandshakeAck()
    if p.startswith(_FEATURES_ACK):
        return FeaturesAck()
    if p.startswith(_LINK_DROP):
        return LinkDrop()
    if p.startswith(_NOISE) and len(p) > 7:
        mode = NOISE_NAMES.get(p[7])
        return Noise(mode) if mode else None
    if p.startswith(_BATTERY):
        return _parse_battery(p)
    if p.startswith(_EAR) and len(p) >= 8:
        return Ear(_EAR_STATES.get(p[6], "gone"), _EAR_STATES.get(p[7], "gone"))
    return None


def _parse_battery(p):
    if len(p) < 7:
        return None
    count = p[6]
    if count > 3 or len(p) != 7 + 5 * count:
        return None
    levels = {}
    primary = None
    for i in range(count):
        component, spacer, percent, status, end = p[7 + 5 * i : 12 + 5 * i]
        if spacer != 0x01 or end != 0x01 or component not in _COMPONENTS:
            return None
        name = _COMPONENTS[component]
        if status == 0x04:  # disconnected
            levels[name] = Level(None, charging=False)
        else:
            levels[name] = Level(percent, charging=(status == 0x01))
        if primary is None and name != "case":
            primary = name
    missing = Level(None, charging=False)
    return Battery(
        left=levels.get("left", missing),
        right=levels.get("right", missing),
        case=levels.get("case", missing),
        primary=primary or "right",
    )
