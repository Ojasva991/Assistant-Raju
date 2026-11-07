"""
ui/prefs.py
App settings saved in the `prefs` table (user_id 0, so they belong to the app and not
to one profile). Values are stored as text, so each key has a small convert function.
"""

import logging
from typing import Optional

from database import GUEST_ID

log = logging.getLogger(__name__)

THEME = "theme"                        # "system" | "light" | "dark"
SPEAK_REPLIES = "speak_replies"        # "1" | "0"
MIC_DEVICE = "mic_device"              # device index as text, or "default"
CONTINUOUS_DEFAULT = "continuous_default"   # "1" | "0"
TRAY_HINT_SHOWN = "tray_hint_shown"    # "1" once the "Raju is in the tray" message was shown

THEMES = ("system", "light", "dark")


def get_theme(memory) -> str:
    value = memory.get_pref(THEME, GUEST_ID)
    return value if value in THEMES else "system"


def get_flag(memory, key: str, default: bool) -> bool:
    value = memory.get_pref(key, GUEST_ID)
    if value is None:
        return default
    return value == "1"


def get_mic_device(memory) -> Optional[int]:
    """The saved device index, or None for 'use config.MIC_DEVICE_INDEX'
    (nothing was ever chosen) -- see has_mic_choice()."""
    value = memory.get_pref(MIC_DEVICE, GUEST_ID)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def has_mic_choice(memory) -> bool:
    """True when the user picked a device (a number, or 'default') in Settings."""
    value = memory.get_pref(MIC_DEVICE, GUEST_ID)
    if value == "default":
        return True
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def set_value(memory, key: str, value) -> None:
    if isinstance(value, bool):
        value = "1" if value else "0"
    memory.set_pref(key, str(value), GUEST_ID)
