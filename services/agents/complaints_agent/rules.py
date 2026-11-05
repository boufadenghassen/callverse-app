"""Complaint policy data loaded once for the rule and scoring engines."""
import json
import re
from pathlib import Path

from . import _POLICY_PATH

POLICY = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
LEVELS = POLICY["levels"]
ORDER = list(LEVELS)
CLUSTERS = POLICY["clusters"]
SIGNALS = {key: re.compile(value, re.I) for key, value in POLICY["signals"].items()}
RESOLUTIONS = POLICY["resolutions"]
FOLLOW_UP_HOURS = POLICY["follow_up_hours"]
