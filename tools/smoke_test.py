"""
tools/smoke_test.py
A fast "does Raju still work?" check. Run it after every change.

    python tools/smoke_test.py            safe checks only (about 5 seconds)
    python tools/smoke_test.py --speak    also speak one sentence (speakers)
    python tools/smoke_test.py --mic      also list microphones, check MIC_DEVICE_INDEX
    python tools/smoke_test.py --listen   also record one phrase (needs internet)
    python tools/smoke_test.py --apps     also REALLY open Notepad and Calculator
    python tools/smoke_test.py --online   also check that the internet is reachable
    python tools/smoke_test.py --all      all of the above

The default run uses a fake voice, a temporary database and a temporary log,
and it does NOT start real apps, so it is safe anywhere.
Result per check: PASS, WARN (works, but something optional is missing) or
FAIL. The exit code is 1 if anything failed.
"""

import argparse
import importlib
import os
import re
import sys
import tempfile
import time
import traceback
from unittest import mock

# Make the project modules importable no matter where the script is started.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class Report:
    def __init__(self):
        self.rows = []
        self.seconds = 0.0

    def add(self, name, status, detail=""):
        self.rows.append((name, status, detail))
        print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

    def count(self, status):
        return sum(1 for _, s, _ in self.rows if s == status)


def run_check(report, name, func):
    """Runs one check. func returns a detail string (PASS), or (status, detail).
    Any exception is a FAIL, so one broken check never hides the others."""
    try:
        result = func()
        status, detail = result if isinstance(result, tuple) else (PASS, result or "")
        report.add(name, status, detail)
    except Exception as e:  # a smoke test must report everything, not stop
        last = traceback.extract_tb(e.__traceback__)[-1]
        report.add(name, FAIL, f"{type(e).__name__}: {e} ({os.path.basename(last.filename)}:{last.lineno})")


# ---------------------------------------------------------------------
# Fakes (same idea as the pytest tests)
# ---------------------------------------------------------------------
class FakeVoice:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


class FakeListener:
    def __init__(self):
        self.answers = []

    def listen(self):
        return self.answers.pop(0) if self.answers else ""


# ---------------------------------------------------------------------
# Basic checks
# ---------------------------------------------------------------------
def check_python():
    v = sys.version_info
    if v < (3, 10):
        raise RuntimeError(f"Python {v.major}.{v.minor} is too old, need 3.10+")
    return f"Python {v.major}.{v.minor}.{v.micro}"


# module name -> (pip name, required?)
PACKAGES = {
    "speech_recognition": ("SpeechRecognition", True),
    "pyttsx3": ("pyttsx3", True),
    "sklearn": ("scikit-learn", True),
    "vaderSentiment": ("vaderSentiment", True),
    "psutil": ("psutil", True),
    "PySide6": ("PySide6-Essentials", True),   # the window (gui.py)
    "wikipedia": ("wikipedia", True),
    "pyaudio": ("pyaudio", False),      # only the microphone needs it
    "pyautogui": ("pyautogui", False),  # only screenshots
    "pyperclip": ("pyperclip", False),  # only the clipboard
}


def check_packages():
    missing_required, missing_optional = [], []
    for module, (pip_name, required) in PACKAGES.items():
        try:
            importlib.import_module(module)
        except Exception:  # ImportError, or a display problem
            (missing_required if required else missing_optional).append(pip_name)
    if missing_required:
        raise RuntimeError("missing: " + ", ".join(missing_required)
                           + "  (run: pip install -r requirements.txt)")
    if missing_optional:
        return WARN, "optional missing: " + ", ".join(missing_optional)
    return f"{len(PACKAGES)} packages found"


def check_config():
    import config
    assert config.APPS and config.WEBSITES, "APPS or WEBSITES is empty"
    assert os.path.exists(config.TRAINING_DATA_PATH), "training_data.json not found"
    assert config.WAKE_WORD in config.WAKE_WORD_ALIASES, "wake word not in aliases"
    return (f"{len(config.APPS)} apps, {len(config.WEBSITES)} sites, "
            f"MIC_DEVICE_INDEX={config.MIC_DEVICE_INDEX}")


_classifier = {}


def check_classifier():
    from intent_classifier import IntentClassifier
    clf = IntentClassifier()
    _classifier["clf"] = clf  # reused by the assistant checks below
    expected = {"exit": "exit", "stop raju": "exit",
                "take screenshot": "screenshot",
                "what is the weather today": "unknown",
                "open notepad": "open_app"}
    got = {s: clf.predict(s)[0] for s in expected}
    wrong = {s: g for s, g in got.items() if g != expected[s]}
    if wrong:
        raise AssertionError(f"wrong intents: {wrong}")
    return f"{len(expected)} sample sentences classified correctly"


# ---------------------------------------------------------------------
# Assistant checks (fake voice, temp database, no real launching)
# ---------------------------------------------------------------------
def check_assistant_commands(report):
    import assistant
    from assistant import Assistant

    launched, opened = [], []
    voice, listener = FakeVoice(), FakeListener()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, \
            mock.patch.object(assistant.subprocess, "Popen", lambda a, **k: launched.append(a)), \
            mock.patch.object(assistant.webbrowser, "open", lambda u: opened.append(u) or True), \
            mock.patch.object(assistant, "open_with_system", lambda t: launched.append(t)):
        bot = Assistant(voice=voice, listener=listener,
                        db_path=os.path.join(tmp, "smoke.db"),
                        classifier=_classifier.get("clf"), start_reminders=False,
                        log_path=os.path.join(tmp, "smoke.log"))
        try:
            def case(sentence, check, answers=()):
                launched.clear()
                opened.clear()
                voice.said.clear()
                listener.answers = list(answers)

                def go():
                    bot.execute(sentence)
                    return check()
                run_check(report, f"command: {sentence!r}", go)

            def expect(cond, message):
                if not cond:
                    raise AssertionError(f"{message} failed (Raju said: {voice.said})")
                return message

            def last():
                return voice.said[-1] if voice.said else ""

            case("open notepad",
                 lambda: expect(launched == [["notepad"]], "starts notepad"))
            case("OPEN NOTEPAD!",
                 lambda: expect(launched == [["notepad"]], "starts notepad"))
            case("Open Notepad please",
                 lambda: expect(launched == [["notepad"]], "starts notepad"))
            case("launch calculator",
                 lambda: expect(launched == [["calc"]], "starts calculator"))
            case("go to youtube",
                 lambda: expect(opened == ["https://youtube.com"], "opens youtube"))
            case("what is the time",
                 lambda: expect(re.fullmatch(r"The time is \d{1,2}:\d{2} (AM|PM)", last()),
                                "says 12-hour time"))
            case("what is the date",
                 lambda: expect(last().startswith("Today's date"), "says the date"))
            case("hello",
                 lambda: expect("Raju" in last(), "greets"))
            case("what is the weather today",
                 lambda: expect(last() in assistant.UNKNOWN_RESPONSES,
                                "says it did not understand"))
            case("what is fifteen plus twenty",
                 lambda: expect("35" in last(), "answers 35"))
            case("add a task",
                 lambda: expect(any(t["task"] == "buy milk" for t in bot.memory.get_todos()),
                                "saves the task in the database"),
                 answers=["buy milk"])
            case("remember this",
                 lambda: expect(bot.memory.get_latest_note() == "my exam is on friday",
                                "saves the note in the database"),
                 answers=["my exam is on friday"])

            # ---- Day 3: calculator, reminders, profiles ----
            case("add three and four",
                 lambda: expect(last() == "The answer is 7", "answers 7"))
            case("subtract five from ten",
                 lambda: expect(last() == "The answer is 5", "answers 5"))
            case("what is 12 + 7",
                 lambda: expect(last() == "The answer is 19", "answers 19 (symbol +)"))
            case("what is two plus three times four",
                 lambda: expect(last() == "The answer is 14", "answers 14 (precedence)"))

            def reminder():
                import datetime
                listener.answers = ["call mom", "in ten minutes"]
                bot.execute("set a reminder")
                rows = bot.memory.get_due_reminders("2099-01-01T00:00:00")
                expect(len(rows) == 1 and rows[0]["task"] == "call mom", "saves the reminder")
                delta = datetime.datetime.fromisoformat(rows[0]["remind_at"]) - datetime.datetime.now()
                return expect(9 * 60 < delta.total_seconds() < 10 * 60 + 5,
                              "'in ten minutes' is about 10 minutes from now")
            run_check(report, "reminder: 'in ten minutes' (word number)", reminder)

            def profiles():
                listener.answers = ["Asha", "1 2 3 4", "1 2 3 4"]
                bot.execute("create a profile")
                expect(bot.current_user and bot.current_user["name"] == "Asha", "creates a profile")
                row = bot.memory.get_all_users()[0]
                expect(row["pin"] == "" and row["pin_hash"].startswith("pbkdf2_sha256$"),
                       "stores only a salted hash")
                bot.execute("log out")
                listener.answers = ["1235"]
                bot.execute("log in")
                expect(bot.current_user is None, "wrong PIN 1235 is refused")
                listener.answers = ["one two three four"]
                bot.execute("log in")
                return expect(bot.current_user and bot.current_user["name"] == "Asha",
                              "spoken digits log in")
            run_check(report, "profiles: hashed PIN, exact match", profiles)

            def unsafe():
                bot.memory.teach_command("hack", "del /q C:\\*")
                launched.clear()
                listener.answers = ["yes"]
                bot.execute("hack")
                return expect(launched == [], "refuses an unsafe learned command")
            run_check(report, "safety: unsafe learned command", unsafe)

            def history():
                rows = bot.memory.get_history()
                return expect(rows and all(r["intent"] for r in rows),
                              f"logs {len(rows)} commands with their intent")
            run_check(report, "history", history)

            def exits():
                try:
                    bot.execute("exit")
                except SystemExit:
                    return "exit stops the assistant"
                raise AssertionError("'exit' did not stop the assistant")
            run_check(report, "command: 'exit'", exits)
        finally:
            assistant.close_logging()  # release the log file before the temp folder is deleted


def check_ui_window():
    """Builds the PySide6 window OFFSCREEN in a separate process (no screen needed),
    switches through all five pages and renders them. Uses a fake voice and mic."""
    import subprocess
    with tempfile.TemporaryDirectory() as out:
        code = ("import sys; sys.path.insert(0, r'%s'); import ui_screenshot; "
                "print(len(ui_screenshot.render('light', r'%s')))"
                % (os.path.join(ROOT, "tools"), out))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                              text=True, timeout=90)
        if done.returncode != 0:
            raise RuntimeError((done.stderr or done.stdout).strip().splitlines()[-1])
        if done.stdout.strip().splitlines()[-1] != "6":
            raise RuntimeError("expected 6 rendered pages, got: " + done.stdout.strip()[-80:])
    return "window built, 5 pages rendered"


def check_day5_data():
    """Tasks, reminders, history and settings storage, plus the greeting and the topic
    cleaner (Day 5). Uses a temporary database."""
    import datetime
    from database import MemoryManager
    from features.briefing import greeting_for
    from features.knowledge import extract_topic
    from ui import prefs
    with tempfile.TemporaryDirectory() as tmp:
        memory = MemoryManager(os.path.join(tmp, "day5.db"))
        memory.add_todo("milk")
        memory.delete_todo(memory.get_todos()[0]["id"])
        memory.add_reminder("x", datetime.datetime.now().isoformat())
        memory.delete_reminder(memory.get_reminders()[0]["id"])
        memory.log_history("what time is it", "time", confidence=0.9)
        if memory.clear_history() != 1:
            raise RuntimeError("clear_history did not remove the row")
        prefs.set_value(memory, prefs.THEME, "dark")
        if prefs.get_theme(memory) != "dark":
            raise RuntimeError("settings were not saved")
        if memory.get_todos() or memory.get_reminders():
            raise RuntimeError("delete did not remove the rows")
    if greeting_for(9) != "Good morning" or greeting_for(20) != "Good evening":
        raise RuntimeError("greeting does not follow the time of day")
    if extract_topic("who was isaac newton") != "isaac newton":
        raise RuntimeError("topic cleaner is wrong")
    return "todo/reminder/history/settings storage, greeting, topic cleaner"


def check_speech_queue():
    """Two threads speak at once into a FAKE engine: they must come out one
    after the other. (The real speakers are tested by --speak.)"""
    import threading
    from speech_engine import SpeechEngine

    state = {"active": 0, "max": 0, "spoken": []}
    lock = threading.Lock()

    class Engine:
        def setProperty(self, *a):
            pass

        def say(self, text):
            self.text = text

        def runAndWait(self):
            with lock:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            time.sleep(0.05)
            with lock:
                state["active"] -= 1
                state["spoken"].append(self.text)

        def stop(self):
            pass

    voice = SpeechEngine(engine_factory=Engine)
    threads = [threading.Thread(target=voice.speak, args=(f"line {i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    voice.close()
    assert len(state["spoken"]) == 4, f"only {len(state['spoken'])} of 4 sentences were spoken"
    assert state["max"] == 1, "two sentences were spoken at the same time"
    return "4 sentences from 4 threads, spoken one at a time"


# ---------------------------------------------------------------------
# Optional checks on the real machine
# ---------------------------------------------------------------------
def check_speak():
    """Speaks one sentence, then two sentences from two threads at the same
    time. You should hear them one AFTER the other, never mixed together."""
    import threading
    from speech_engine import SpeechEngine
    voice = SpeechEngine()
    voice.speak("Smoke test. If you can hear this, the speakers work.")
    print("      Now two sentences are started at the same time...")
    threads = [threading.Thread(target=voice.speak, args=(text,)) for text in
               ("This is the first sentence.", "This is the second sentence.")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    voice.close()
    return ("spoke 3 sentences. Did you HEAR the first one? Were the last two spoken one "
            "after the other, not mixed? If not, check volume/output device, and tell me")


def check_mic_devices():
    import config
    import speech_recognition as sr
    try:
        names = sr.Microphone.list_microphone_names()
    except (AttributeError, ImportError):
        raise RuntimeError("PyAudio is missing or broken (run: pip install pyaudio)")
    if not names:
        raise RuntimeError("no microphones found (check Windows sound settings and pyaudio)")
    idx = config.MIC_DEVICE_INDEX
    if idx is not None and not (0 <= idx < len(names)):
        raise RuntimeError(f"MIC_DEVICE_INDEX={idx} does not exist; there are {len(names)} devices")
    where = "default device" if idx is None else f"[{idx}] {names[idx]}"
    return f"{len(names)} devices; Raju uses: {where}"


# Rough guide only: 16-bit audio of an empty room is usually far below this.
QUIET_LEVEL = 150


def audio_level(audio):
    """Returns (seconds, loudness) of a recording. loudness is the RMS of the
    16-bit samples, or None if it cannot be measured."""
    seconds = len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
    try:
        import audioop  # standard library up to Python 3.12
        return seconds, audioop.rms(audio.frame_data, audio.sample_width)
    except ImportError:
        return seconds, None


def check_listen():
    import config
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    print("      Say a short sentence now (you have 5 seconds)...")
    try:
        with sr.Microphone(device_index=config.MIC_DEVICE_INDEX) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=6)
    except sr.WaitTimeoutError:
        return WARN, "no speech heard in 5 seconds (mic level too low, or wrong device)"
    except (AttributeError, ImportError):
        raise RuntimeError("PyAudio is missing or broken (run: pip install pyaudio)")
    except OSError as e:
        raise RuntimeError(f"cannot open the microphone ({e}); run --mic to see the devices")
    try:
        text = recognizer.recognize_google(audio, language="en-in")
    except sr.UnknownValueError:
        seconds, level = audio_level(audio)
        if level is not None and level < QUIET_LEVEL:
            return WARN, (f"recorded {seconds:.1f} s but it was almost silent (level {level}). "
                          "Raise the microphone volume in Windows Sound settings, or try "
                          "another device index (python tools/mic_test.py --all)")
        return WARN, (f"recorded {seconds:.1f} s (level {level}) but Google could not understand it. "
                      "Speak clearly right after the prompt, and try again")
    except sr.RequestError as e:
        return WARN, f"audio recorded, but Google is not reachable ({e})"
    return f"heard: {text!r}"


def check_real_apps():
    import assistant
    if not sys.platform.startswith("win"):
        return WARN, "skipped: the real app test is for Windows"
    for command in ("notepad", "calc"):
        if not assistant.run_allowed_command(command):
            raise RuntimeError(f"could not start {command}")
    return "started Notepad and Calculator - please close them"


def check_online():
    import urllib.error
    import urllib.request
    # Some sites refuse the default Python User-Agent, so send our own name.
    request = urllib.request.Request("https://en.wikipedia.org",
                                     headers={"User-Agent": "RajuSmokeTest/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=4):
            pass
    except urllib.error.HTTPError:
        # The server answered (with an error code), so the internet works.
        return "internet reachable (Google speech and Wikipedia can work)"
    except Exception as e:
        return WARN, f"no internet ({type(e).__name__}): Google speech and Wikipedia will not work"
    return "internet reachable (Google speech and Wikipedia can work)"


# ---------------------------------------------------------------------
def run_smoke(speak=False, mic=False, listen=False, apps=False, online=False):
    """Runs everything and returns the Report (used by main() and by pytest)."""
    start = time.time()
    report = Report()
    run_check(report, "python version", check_python)
    run_check(report, "packages", check_packages)
    run_check(report, "config", check_config)
    run_check(report, "intent classifier", check_classifier)
    run_check(report, "speech queue (fake engine)", check_speech_queue)
    run_check(report, "day 5 data (temp db)", check_day5_data)
    run_check(report, "ui window (offscreen)", check_ui_window)
    try:
        check_assistant_commands(report)
    except Exception as e:
        report.add("assistant starts", FAIL, f"{type(e).__name__}: {e}")
    if online:
        run_check(report, "internet", check_online)
    if mic:
        run_check(report, "microphone devices", check_mic_devices)
    if listen:
        run_check(report, "microphone + Google speech", check_listen)
    if speak:
        run_check(report, "speakers (text to speech)", check_speak)
    if apps:
        run_check(report, "real apps", check_real_apps)
    report.seconds = time.time() - start
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Quick health check for Raju.")
    parser.add_argument("--speak", action="store_true", help="speak one sentence")
    parser.add_argument("--mic", action="store_true", help="list microphones")
    parser.add_argument("--listen", action="store_true", help="record one phrase")
    parser.add_argument("--apps", action="store_true", help="really open Notepad and Calculator")
    parser.add_argument("--online", action="store_true", help="check the internet")
    parser.add_argument("--all", action="store_true", help="all optional checks")
    args = parser.parse_args(argv)

    optional = args.speak or args.mic or args.listen or args.apps or args.online or args.all
    report = run_smoke(
        speak=args.speak or args.all, mic=args.mic or args.all,
        listen=args.listen or args.all, apps=args.apps or args.all,
        online=args.online or args.all,
    )
    print(f"\n{report.count(PASS)} passed, {report.count(WARN)} warnings, "
          f"{report.count(FAIL)} failed ({report.seconds:.1f} s)")
    if not optional:
        print("Tip: add --all to also test microphone, speakers, real apps and internet.")
    return 1 if report.count(FAIL) else 0


if __name__ == "__main__":
    sys.exit(main())
