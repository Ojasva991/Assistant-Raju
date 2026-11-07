"""
config.py
All constants, paths, and settings for the Raju assistant live here.
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
TRAINING_DATA_PATH = os.path.join(BASE_DIR, "training_data.json")

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
# Only commands that are VALUES in APPS (above) may ever be run. This also
# covers learned commands that come back from the database.
# These two apps need their own console window when started on Windows.
CONSOLE_APPS = ("cmd", "powershell")

# ---------------- LOGGING ----------------
LOG_MAX_BYTES = 500_000   # rotate the log file after about 0.5 MB
LOG_BACKUP_COUNT = 3      # keep this many old log files

# ---------------- MICROPHONE ----------------
# Run `python tools/mic_test.py --all` if audio stops being picked up
# correctly (e.g. after plugging in a headset) to find the right index.
# None = use the system default device.
MIC_DEVICE_INDEX = 1

# ---------------- SPEECH TO TEXT ----------------
# Which recognizer turns audio into text. Only "google" exists today (it needs
# internet). The name is kept here so an offline engine (Vosk, faster-whisper)
# can be added later without touching the rest of the code.
STT_ENGINE = "google"
STT_LANGUAGE = "en-in"
LISTEN_TIMEOUT = 5        # seconds to wait for someone to start speaking (wake word listening)
ANSWER_TIMEOUT = 10       # more time when Raju asked a question and waits for the answer
SHOW_HEARD = True         # console mode: print "Heard: ..." for everything the mic understood
SHOW_SPOKEN_PIN = False   # True shows spoken PINs too (only for testing; PINs are hidden by default)
FOLLOW_UP_SECONDS = 10    # after a reply, new commands need NO wake word for this long (0 = off)
PHRASE_TIME_LIMIT = 8     # longest single phrase, in seconds
AMBIENT_SECONDS = 0.5     # noise calibration time (done once, not every listen)

# ---------------- TEXT TO SPEECH ----------------
TTS_TIMEOUT = 60          # a speak() call never blocks longer than this

# ---------------- PROFILES AND PINS ----------------
PIN_MIN_LENGTH = 4
PIN_MAX_ATTEMPTS = 3          # wrong PINs in a row before login is locked
PIN_LOCK_SECONDS = 60
PIN_HASH_ITERATIONS = 200_000  # PBKDF2 work factor; slow on purpose

# ---------------- REMINDERS ----------------
REMINDER_CHECK_SECONDS = 5    # how often the background thread looks for due reminders

# ---------------- WAKE WORD ----------------
# Primary phrase, plus common ways Google's speech recognizer actually
# transcribes it (short phrases are often misheard as a
# real word, for example "raju" as "raj" — listing aliases fixes that without
# needing a different wake phrase).
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
# Which model answers commands. Options: "naive_bayes", "logreg", "linear_svc".
# Choose by cross-validation: run `python intent_classifier.py` and read the table.
MODEL_NAME = "logreg"
# Below this confidence the assistant says it did not understand instead of guessing.
# Tuned on cross-validated predictions by `python intent_classifier.py`.
CONFIDENCE_THRESHOLD = 0.12
CV_FOLDS = 5          # stratified folds for the model comparison
CV_REPEATS = 5        # repeat with different shuffles so one lucky split cannot decide
RANDOM_SEED = 42

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
