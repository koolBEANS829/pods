"""~/.config/pods/config.toml, read with tomllib. Tunables live here, never in the source.

    pause_when = "one"    # pause when either bud leaves an ear (Apple's default)
    pause_when = "both"   # keep playing until both are out
"""
import logging
import tomllib
from pathlib import Path

PATH = Path.home() / ".config" / "pods" / "config.toml"
DEFAULTS = {"pause_when": "one"}
CHOICES = {"pause_when": ("one", "both")}

log = logging.getLogger("pods")


def load(path=PATH):
    cfg = dict(DEFAULTS)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return cfg
    except (tomllib.TOMLDecodeError, OSError) as e:
        log.warning("%s: %s; using defaults", path, e)
        return cfg
    for key, value in data.items():
        if value in CHOICES.get(key, ()):
            cfg[key] = value
        else:
            log.warning("%s: ignoring %s = %r", path, key, value)
    return cfg
