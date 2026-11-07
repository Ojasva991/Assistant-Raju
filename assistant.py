"""
assistant.py
The Raju assistant itself: wires together speech, memory, the intent
classifier and all the feature modules.

Order of work inside execute():
  1. Clean the query (lowercase, no punctuation, no leading wake word).
  2. Predict the intent ONCE; the same result is used for the history
     log and for choosing the handler.
  3. Direct phrases, learned commands, then the handler for the intent.
"""

import datetime
import logging
import os
import random
import re
import subprocess
import sys
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from typing import Optional

import config
from speech_engine import SpeechEngine
from listener import Listener, hear_answer
from database import MemoryManager, GUEST_ID
from intent_classifier import IntentClassifier, clean_text
from fuzzy_match import best_match, find_wake_word, find_known_name
from timeutil import format_time  # also re-exported: `from assistant import format_time` works

from features.todo import TodoFeature
from features.reminders import ReminderFeature
from features.calculator import CalculatorFeature
from features.system_utils import SystemUtilsFeature
from features.knowledge import KnowledgeFeature
from features.user_profile import UserProfileFeature
from features.semantic_memory import SemanticMemory
from features.briefing import BriefingFeature
from features.sentiment import SentimentFeature
from features.history import HistoryFeature

log = logging.getLogger(__name__)

GREETINGS = [
    f"Hello, I am your assistant {config.ASSISTANT_NAME}. How can I help you?",
    f"Hey, {config.ASSISTANT_NAME} here. What can I do for you?",
]
# Each reply says it did not understand AND gives one example command
# (spec section A), so the user knows what to try next.
UNKNOWN_RESPONSES = [
    "Sorry, I didn't understand that. Try saying, open notepad.",
    "I'm not sure what you meant. You can say, what time is it.",
    "I didn't catch that. For example, say, add a task.",
]
FRUSTRATED_UNKNOWN_RESPONSES = [
    "I'm sorry, I'm having trouble understanding. Let's try again, for example, what is the date.",
    "My apologies, that didn't come through clearly. You could say, show my tasks.",
]
FRUSTRATED_ACKNOWLEDGMENTS = [
    "Sorry about that.",
    "I hear you, let me help.",
    "Apologies for the trouble.",
]

# Sentences that start like this AND contain a known app/site name are
# treated as "open it", even if the model is unsure.
OPEN_VERBS = ("open", "launch", "start", "run", "go to", "take me to", "browse to")

# ---------------- yes / no ----------------
_YES = re.compile(r"\b(?:yes|yeah|yep|sure|okay|ok|do it)\b")
# A "no" word anywhere wins over a "yes" word ("not okay", "no, don't do it").
_NO = re.compile(r"\b(?:no|nope|not|dont|never|cancel|stop)\b")


def is_yes(answer: str) -> bool:
    """Whole words only: 'yesterday' is not a yes. Everything unclear is a no."""
    text = clean_text(answer or "")
    return bool(_YES.search(text)) and not _NO.search(text)


# ---------------- small helpers ----------------
# Google often writes sums with symbols ("12 + 7"). clean_text would delete
# the symbol, so they are turned into words first.
_MATH_SYMBOLS = [
    (re.compile(r"\s*\+\s*"), " plus "),
    (re.compile(r"\s*[×*]\s*"), " times "),
    (re.compile(r"\s*[÷/]\s*"), " divided by "),
    (re.compile(r"(?<=\d)\s*-\s*(?=\d)"), " minus "),
    (re.compile(r"(?<=\d)\s+x\s+(?=\d)"), " times "),
]


def normalize_query(text: str) -> str:
    """Same cleaning for typed and spoken input: lowercase, no punctuation,
    math symbols as words, and a leading wake word ("raju open notepad") is removed."""
    text = text or ""
    for pattern, words in _MATH_SYMBOLS:
        text = pattern.sub(words, text)
    clean = clean_text(text)
    words = clean.split()
    if words and words[0] in config.WAKE_WORD_ALIASES:
        words = words[1:]
    return " ".join(words)


def open_with_system(target: str) -> None:
    """The ONE place that opens a file or a URI with the operating system
    (music, 'ms-settings:'). Works on Windows, macOS and Linux."""
    if sys.platform.startswith("win"):
        os.startfile(target)  # Windows only, so it is kept in this helper
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def run_allowed_command(command: str) -> bool:
    """
    Starts an app. Only commands that are VALUES in config.APPS are allowed,
    so text from voice input or from the database can never run as a command.
    No shell is used (no os.system), so nothing can be chained with '&' or ';'.
    Returns True if it started, False if it was refused or failed.
    """
    if command not in config.APPS.values():
        log.warning("Refused to run a command that is not in config.APPS: %r", command)
        return False
    try:
        if command.endswith(":"):  # a URI such as ms-settings:, not a program
            open_with_system(command)
            return True
        kwargs = {}
        if sys.platform.startswith("win") and command in config.CONSOLE_APPS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE  # own window
        subprocess.Popen([command], **kwargs)
        return True
    except OSError as e:
        log.error("Could not start %r: %s", command, e)
        return False


_file_handler: Optional[RotatingFileHandler] = None


def setup_logging(log_path: Optional[str] = None) -> None:
    """Rotating log file (query, intent, confidence, errors).
    Safe to call many times: the old handler is replaced, never doubled."""
    global _file_handler
    close_logging()
    handler = RotatingFileHandler(
        log_path or config.LOG_PATH,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    _file_handler = handler


def close_logging() -> None:
    global _file_handler
    if _file_handler is not None:
        logging.getLogger().removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None


class Assistant:
    def __init__(self, use_microphone=True, on_speak=None, *, voice=None,
                 listener=None, db_path=None, classifier=None,
                 start_reminders=True, log_path=None,
                 allow_text_fallback=True, on_error=None, on_due=None):
        # The keyword-only arguments exist so tests can pass a fake voice,
        # a fake listener and a temporary database (no mic, no speakers).
        # GUI mode: allow_text_fallback=False (never input()), on_error(msg) shows mic
        # problems, on_due(text) shows due reminders (tray message).
        setup_logging(log_path)
        self.voice = voice or SpeechEngine(on_speak=on_speak)
        self.listener = listener or Listener(use_microphone=use_microphone,
                                             allow_text_fallback=allow_text_fallback,
                                             on_error=on_error)
        # The mic must not open while Raju is talking (for example a reminder).
        if hasattr(self.voice, "wait_until_idle") and hasattr(self.listener, "before_listen"):
            self.listener.before_listen = self.voice.wait_until_idle
        self.memory = MemoryManager(db_path) if db_path else MemoryManager()
        self.ai = classifier or IntentClassifier()
        self._now = datetime.datetime.now  # tests replace this with a fixed time
        self._clock = time.monotonic       # tests replace this to test the follow-up window
        self._awake_until = 0.0            # follow-up window: no wake word needed until then

        # feature modules
        self.todo = TodoFeature(self.memory, self.voice, self.listener)
        self.reminders = ReminderFeature(self.memory, self.voice, self.listener,
                                         on_due=on_due, now=lambda: self._now())
        self.calculator = CalculatorFeature(self.voice)
        self.system_utils = SystemUtilsFeature(self.voice)
        self.knowledge = KnowledgeFeature(self.voice)
        self.profiles = UserProfileFeature(self.memory, self.voice, self.listener)
        self.semantic_memory = SemanticMemory(self.memory)
        self.briefing = BriefingFeature(self.memory, self.voice)
        self.sentiment = SentimentFeature()
        self.history = HistoryFeature(self.memory, self.voice)

        # No profile logged in by default -- memory uses the shared
        # "guest" bucket until someone logs in or creates a profile.
        self.current_user = None
        self.last_sentiment = {"compound": 0.0, "label": "neutral"}

        if start_reminders:
            self.reminders.start_background_checker()
        log.info("Assistant ready (model=%s)", config.MODEL_NAME)

    @property
    def current_user_id(self):
        return self.current_user["id"] if self.current_user else GUEST_ID

    def follow_up_seconds_left(self) -> float:
        """How long Raju still accepts commands without the wake word."""
        return max(0.0, self._awake_until - self._clock())

    def greet(self):
        self.voice.speak(random.choice(GREETINGS))

    # ---------------- WAKE WORD ----------------
    def listen_for_command(self):
        """
        Waits for one utterance from the mic. Only returns something if
        a wake word was heard -- otherwise returns None so the caller
        just keeps listening silently, without Raju reacting to every
        stray sound or unrelated conversation in the room.

        Uses fuzzy matching against config.WAKE_WORD_ALIASES because
        short wake phrases often get mistranscribed by speech
        recognition.

        If you say the wake word with nothing else, Raju prompts "Yes?"
        and listens once more for the actual command.
        """
        listening_since = self._clock()
        heard = self.listener.listen()
        if not heard:
            return None

        remainder = find_wake_word(heard, config.WAKE_WORD_ALIASES)
        if remainder is None:
            # Follow-up mode: for a few seconds after a reply you can just keep
            # talking without the wake word. Outside that window it is ignored.
            if listening_since < self._awake_until:
                return heard
            return None  # wake word not detected, ignore silently

        if remainder:
            return remainder

        self.voice.speak("Yes?")
        follow_up = hear_answer(self.listener)
        return follow_up or None

    # ---------------- MAIN DISPATCH ----------------
    def execute(self, query):
        raw = query or ""
        query = normalize_query(raw)
        if not query:
            if raw.strip() and clean_text(raw) in config.WAKE_WORD_ALIASES:
                self.voice.speak("Yes?")  # typed wake word alone
            return

        # Sentiment looks at the raw text (capitals and "!" carry mood).
        self.last_sentiment = self.sentiment.analyze(raw)
        if self.last_sentiment["label"] == "negative":
            self.voice.speak(random.choice(FRUSTRATED_ACKNOWLEDGMENTS))

        # Predict ONCE. The same answer goes to the history log and to the handler.
        try:
            intent, confidence = self.ai.predict(query)
        except Exception:
            log.exception("Intent prediction failed for %r", query)
            intent, confidence = "unknown", 0.0
        log.info("query=%r intent=%s confidence=%.2f user=%s",
                 query, intent, confidence, self.current_user_id)
        self.memory.log_history(query, intent=intent, user_id=self.current_user_id,
                                confidence=float(confidence))

        try:
            self._dispatch(query, intent)
        except SystemExit:
            raise
        except Exception:
            log.exception("Command failed: %r", query)
            raise
        # The reply is finished: open the follow-up window (no wake word needed).
        self._awake_until = self._clock() + config.FOLLOW_UP_SECONDS

    def _dispatch(self, query, intent):
        # 0. Direct-match phrases that must always work.
        if query in config.GREETING_PHRASES:
            self.voice.speak(random.choice(GREETINGS))
            return

        if query in config.BRIEFING_PHRASES:
            self._briefing()
            return

        # 1. Learned (taught) commands: exact match, then fuzzy fallback.
        matched_trigger = query
        learned = self.memory.get_command(query)
        if learned is None:
            triggers = self.memory.get_all_triggers()
            close_trigger = best_match(query, triggers, cutoff=config.FUZZY_CUTOFF)
            if close_trigger:
                matched_trigger = close_trigger
                learned = self.memory.get_command(close_trigger)

        if learned:
            self._run_learned(matched_trigger, learned)
            return

        # 2. "open <known name>" must work even when the model is unsure.
        if intent not in ("open_app", "open_site") and self._starts_with_open_verb(query):
            if (find_known_name(query, list(config.APPS), fuzzy=False)
                    or find_known_name(query, list(config.WEBSITES), fuzzy=False)):
                intent = "open_app"

        # 3. Wikipedia-style question the model did not recognise.
        if intent == "unknown" and query.startswith(("who is", "who was", "tell me about")):
            self.knowledge.answer(query)
            return

        # 4. Handler for the predicted intent.
        self._handle_intent(intent, query)

    def _handle_intent(self, intent, query):
        if intent == "open_app":
            self._open_target(query, prefer="app")

        elif intent == "open_site":
            self._open_target(query, prefer="site")

        elif intent == "time":
            self.voice.speak(f"The time is {format_time(self._now())}")

        elif intent == "date":
            today = self._now().strftime("%d %B %Y")
            self.voice.speak(f"Today's date is {today}")

        elif intent == "music":
            self._play_music()

        elif intent == "remember":
            self.voice.speak("What should I remember?")
            data = hear_answer(self.listener)
            if data:
                self.memory.add_note(data, user_id=self.current_user_id)
                self.voice.speak("I have saved it")

        elif intent == "recall":
            note = self._recall(query)
            if note:
                self.voice.speak(f"You told me: {note}")
            else:
                self.voice.speak("I don't remember anything yet")

        elif intent == "learn_command":
            self._learn_command()

        elif intent == "todo_add":
            self.todo.add_task(user_id=self.current_user_id)

        elif intent == "todo_show":
            self.todo.show_tasks(user_id=self.current_user_id)

        elif intent == "reminder_add":
            self.reminders.add_reminder(user_id=self.current_user_id, query=query)

        elif intent == "calculator":
            self.calculator.calculate(query)

        elif intent == "system_stats":
            self.system_utils.report_stats()

        elif intent == "screenshot":
            self.system_utils.take_screenshot()

        elif intent == "clipboard":
            self.system_utils.read_clipboard()

        elif intent == "greeting":
            self.voice.speak(random.choice(GREETINGS))

        elif intent == "daily_briefing":
            self._briefing()

        elif intent == "thanks":
            self.voice.speak("You're welcome!")

        elif intent == "search":
            self.knowledge.answer(query)

        elif intent == "register_profile":
            user = self.profiles.register()
            if user:
                self.current_user = user

        elif intent == "login":
            user = self.profiles.login()
            if user:
                self.current_user = user

        elif intent == "logout":
            if self.current_user:
                self.voice.speak(f"Logged out. Bye, {self.current_user['name']}.")
                self.current_user = None
            else:
                self.voice.speak("You're not logged into a profile.")

        elif intent == "whoami":
            if self.current_user:
                self.voice.speak(f"You're logged in as {self.current_user['name']}.")
            else:
                self.voice.speak("You're using the guest profile. Say 'log in' or "
                                 "'create a profile' to use your own.")

        elif intent == "show_history":
            self.history.show_recent(user_id=self.current_user_id)

        elif intent == "export_history":
            self.history.export(user_id=self.current_user_id)

        elif intent == "exit":
            self.voice.speak("Thank you. Goodbye")
            self.reminders.stop()
            raise SystemExit

        else:  # "unknown" -- low confidence
            if self.last_sentiment["label"] == "negative":
                self.voice.speak(random.choice(FRUSTRATED_UNKNOWN_RESPONSES))
            else:
                self.voice.speak(random.choice(UNKNOWN_RESPONSES))

    # ---------------- OPENING APPS AND WEBSITES ----------------
    @staticmethod
    def _starts_with_open_verb(query):
        return any(query == v or query.startswith(v + " ") for v in OPEN_VERBS)

    def _open_target(self, query, prefer):
        """Finds an app or a website name inside the query and opens it.
        Exact words first, then fuzzy. If the model picked the wrong kind
        ("go to youtube" labelled open_app) the other kind is tried too."""
        kinds = [("app", config.APPS), ("site", config.WEBSITES)]
        if prefer == "site":
            kinds.reverse()

        for fuzzy in (False, True):  # exact for both kinds, then fuzzy
            for kind, table in kinds:
                name = find_known_name(query, list(table), config.FUZZY_CUTOFF, fuzzy=fuzzy)
                if name:
                    self._open_named(kind, name)
                    return

        _, table = kinds[0]
        names = list(table)
        shown = ", ".join(names[:6]) + (", and more" if len(names) > 6 else "")
        label = "app" if prefer == "app" else "website"
        self.voice.speak(f"I don't know that {label}. I can open {shown}.")

    def _open_named(self, kind, name):
        self.voice.speak(f"Opening {name}")
        if kind == "app":
            ok = run_allowed_command(config.APPS[name])
        else:
            ok = bool(webbrowser.open(config.WEBSITES[name]))
        if not ok:
            self.voice.speak(f"Sorry, I couldn't open {name}.")

    def _run_learned(self, trigger, command):
        # The database is not trusted: only values from config.APPS may run.
        if command not in config.APPS.values():
            log.warning("Learned command %r refused: %r is not in config.APPS", trigger, command)
            self.voice.speak("I can't run that learned command because it is not "
                             "on my safe list of apps.")
            return
        if self._confirm(f"Run the learned command for '{trigger}'?"):
            self.voice.speak("Executing learned command")
            if not run_allowed_command(command):
                self.voice.speak("Sorry, I couldn't start it.")
        else:
            self.voice.speak("Okay, cancelled.")

    # ---------------- HELPERS ----------------
    def _briefing(self):
        user_name = self.current_user["name"] if self.current_user else None
        self.briefing.give_briefing(user_id=self.current_user_id, user_name=user_name)

    def _recall(self, query):
        """
        Smarter recall: if you mention a topic ("what did I say about
        my exam"), search for the most RELEVANT note using semantic
        memory search. If you just say "recall" with no topic, return
        the most recent note like before.
        """
        for marker in (" about ", " regarding ", " related to "):
            if marker in query:
                topic = query.split(marker, 1)[1].strip()
                if topic:
                    return self.semantic_memory.find_relevant_note(
                        topic, user_id=self.current_user_id
                    )
        return self.memory.get_latest_note(user_id=self.current_user_id)

    def _play_music(self):
        files = [f for f in os.listdir(config.MUSIC_DIR)
                 if f.lower().endswith((".mp3", ".wav"))]
        if not files:
            self.voice.speak(f"No music found. Add mp3 files to {config.MUSIC_DIR}")
            return
        track = os.path.join(config.MUSIC_DIR, random.choice(files))
        self.voice.speak("Playing music")
        try:
            open_with_system(track)
        except OSError as e:
            log.error("Could not play %s: %s", track, e)
            self.voice.speak("Sorry, I couldn't play that file.")

    def _learn_command(self):
        self.voice.speak("Say the trigger phrase")
        trigger = normalize_query(hear_answer(self.listener))
        self.voice.speak("Say the action, for example: open notepad")
        action = normalize_query(hear_answer(self.listener))

        if not trigger or not action:
            self.voice.speak("I didn't catch that, cancelling.")
            return

        resolved_action = self._resolve_safe_action(action)
        if resolved_action is None:
            self.voice.speak(
                "Sorry, that action isn't on my safe list, so I can't learn it."
            )
            return

        self.memory.teach_command(trigger, resolved_action)
        self.voice.speak("I have learned a new command")

    def _resolve_safe_action(self, action_text):
        """
        Safety measure: a learned command can ONLY resolve to one of the
        pre-approved apps in config.APPS. Arbitrary shell text is never
        accepted, even from voice input.
        """
        name = find_known_name(action_text, list(config.APPS), config.FUZZY_CUTOFF)
        return config.APPS[name] if name else None

    def _confirm(self, prompt_text):
        self.voice.speak(f"{prompt_text} Say yes or no.")
        return is_yes(hear_answer(self.listener))


# Old name, so older code (the old gui.py) that imports J keeps working.
J = Assistant
