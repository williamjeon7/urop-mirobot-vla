"""Shared trial names for server reservations and Windows recording transfer."""
import re

COLORS = ("red", "green", "blue")
RECORDING_PATTERN = r"I[1-9][0-9]*(?:red|green|blue)?"
RECORDING_RE = re.compile(RECORDING_PATTERN)


def valid_recording_name(name):
    return isinstance(name, str) and RECORDING_RE.fullmatch(name) is not None


def recording_number(name, color=None):
    if not valid_recording_name(name):
        return None
    match = re.fullmatch(r"I([1-9][0-9]*)(red|green|blue)?", name)
    return int(match[1]) if match[2] == color else None
