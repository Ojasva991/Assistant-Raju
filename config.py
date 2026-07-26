"""
config.py
All constants, paths, and settings for the J assistant live here.
Change things here instead of digging through the rest of the code.
"""

import os

# ---------------- PATHS ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "memory.db")
MUSIC_DIR = os.path.join(DATA_DIR, "music")
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
LOG_PATH = os.path.join(DATA_DIR, "assistant.log")

# Make sure the data folders exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ---------------- OFFLINE APPS ----------------
# app name -> command to run it (Windows commands; edit if you're on Mac/Linux)
APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "wordpad": "write",
    "command prompt": "cmd",
    "powershell": "powershell",
    "control panel": "control",
    "task manager": "taskmgr",
    "file explorer": "explorer",
    "settings": "ms-settings:",
    "snipping tool": "snippingtool",
    "magnifier": "magnify",
    "on screen keyboard": "osk",
}

# ---------------- WEBSITES ----------------
WEBSITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
}

# ---------------- SAFETY ----------------
# Only these shell commands are allowed to be "taught" via learn-mode.
# Anything else gets rejected even if the user tries to teach it.
COMMAND_WHITELIST_PREFIXES = ("start ", "explorer ", "notepad", "calc", "mspaint")

# ---------------- MICROPHONE ----------------
# Run mic_test.py / mic_device_test.py if audio stops being picked up
# correctly (e.g. after plugging in a headset) to find the right index.
# None = use the system default device.
MIC_DEVICE_INDEX = 1

# ---------------- WAKE WORD ----------------
# Primary phrase, plus common ways Google's speech recognizer actually
# transcribes it (short phrases like "hey j" often get misheard as a
# real word like "AJ" — listing aliases fixes that without needing a
# different wake phrase).
WAKE_WORD = "raju"
WAKE_WORD_ALIASES = ["raju", "raj"]

# ---------------- FUZZY MATCHING ----------------
# 0-1 scale, higher = stricter match required. Used to recover from
# mic mishearings like "opne notepad" instead of "open notepad".
FUZZY_CUTOFF = 0.72

# ---------------- SENTIMENT ----------------
# VADER's "compound" score ranges from -1 (very negative) to +1 (very
# positive). These thresholds decide when Raju treats you as sounding
# frustrated vs. just neutral/matter-of-fact.
SENTIMENT_NEGATIVE_THRESHOLD = -0.4
SENTIMENT_POSITIVE_THRESHOLD = 0.5

# ---------------- ML ----------------
CONFIDENCE_THRESHOLD = 0.28  # below this, assistant asks for clarification instead of guessing

# ---------------- MISC ----------------
ASSISTANT_NAME = "Raju"

# ---------------- DIRECT-MATCH PHRASES ----------------
# These are common enough that we skip the ML classifier entirely and
# match them directly -- keeps basic greetings 100% reliable even when
# the classifier's confidence gets diluted by having many intents.
GREETING_PHRASES = ["hello", "hi", "hey", "hey there", "good evening"]
BRIEFING_PHRASES = [
    "good morning", "give me my briefing", "daily briefing",
    "start my day", "morning briefing", "brief me for today",
]
