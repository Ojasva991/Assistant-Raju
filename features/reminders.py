"""
features/reminders.py
Voice reminders.

  - parse_relative_time() understands "in ten minutes", "after 5 minutes",
    "in an hour", "in half an hour", "in two and a half hours" ...
  - A background thread looks for due reminders. It never dies on an
    error, marks a reminder as done BEFORE speaking (so it can never repeat
    forever), and calls an optional on_due(text) callback (the UI uses it
    for a tray message).
"""

import datetime
import logging
import re
import threading
from typing import Callable, List, Optional

import config
from features.numbers import NUMBER_WORDS, words_to_number
from listener import hear_answer
from timeutil import format_time

log = logging.getLogger(__name__)

_UNIT_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}
# Words that may stand in front of a unit, besides number words and digits.
_AMOUNT_EXTRA = {"and", "a", "an", "half", "quarter", "of"}
_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def _amount(words: List[str]) -> Optional[float]:
    """Value of the words in front of ONE unit, in that unit.
    ['half', 'an'] -> 0.5, ['two', 'and', 'a', 'half'] -> 2.5, ['ten'] -> 10."""
    while words and words[0] in ("and", "of"):
        words = words[1:]
    if not words:
        return None
    if words in (["half"], ["half", "a"], ["half", "an"], ["a", "half"]):
        return 0.5
    if words in (["quarter"], ["quarter", "of", "a"], ["quarter", "of", "an"], ["a", "quarter", "of", "an"]):
        return 0.25
    if words in (["a"], ["an"]):
        return 1.0
    if len(words) > 3 and words[-3:] == ["and", "a", "half"]:  # "two and a half"
        base = _amount(words[:-3])
        return None if base is None else base + 0.5
    if len(words) == 1 and _DIGITS.fullmatch(words[0]):
        return float(words[0])
    value = words_to_number(words)
    return None if value is None else float(value)


def parse_relative_time(text: str, now: datetime.datetime) -> Optional[datetime.datetime]:
    """Returns 'now' plus the time in the text, or None if no time was found
    (or it was not understood: never a guess). Several parts add up:
    'an hour and ten minutes'."""
    text = re.sub(r"(\d)([a-z])", r"\1 \2", (text or "").lower())  # '10min' -> '10 min'
    words = re.sub(r"[^a-z0-9. ]", " ", text).split()

    total_seconds = 0.0
    start = 0  # a part never reaches back into the part before it
    found = False
    for i, word in enumerate(words):
        if word not in _UNIT_SECONDS:
            continue
        chunk: List[str] = []
        j = i - 1
        while j >= start and (words[j] in NUMBER_WORDS or words[j] in _AMOUNT_EXTRA
                              or _DIGITS.fullmatch(words[j])):
            chunk.insert(0, words[j])
            j -= 1
        amount = _amount(chunk)
        if amount is None:
            return None
        total_seconds += amount * _UNIT_SECONDS[word]
        start = i + 1
        found = True

    if not found or total_seconds <= 0:
        return None
    try:
        return now + datetime.timedelta(seconds=total_seconds)
    except OverflowError:
        return None


class ReminderFeature:
    def __init__(self, memory, voice, listener, check_interval: Optional[float] = None,
                 on_due: Optional[Callable[[str], None]] = None,
                 now: Callable[[], datetime.datetime] = datetime.datetime.now):
        self.memory = memory
        self.voice = voice
        self.listener = listener
        self.check_interval = (config.REMINDER_CHECK_SECONDS
                               if check_interval is None else check_interval)
        self.on_due = on_due      # optional callback(text), set by the UI
        self._now = now           # tests pass a fixed time
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------- ADDING A REMINDER ----------------
    def add_reminder(self, user_id: int = 0, query: str = "") -> None:
        """query is the sentence that started this ("remind me in ten
        minutes"). If it already has a time, Raju does not ask for it again."""
        remind_at = parse_relative_time(query, self._now())

        self.voice.speak("What should I remind you about?")
        task = (hear_answer(self.listener) or "").strip()
        task = re.sub(r"^(?:to|about)\s+", "", task)  # "to call mom" -> "call mom"
        if not task:
            self.voice.speak("I didn't catch that.")
            return

        if remind_at is None:
            self.voice.speak("When should I remind you? For example, in ten minutes.")
            remind_at = parse_relative_time(hear_answer(self.listener), self._now())
        if remind_at is None:
            self.voice.speak("I couldn't understand the time, so the reminder is not set. "
                             "You can say, in ten minutes, or, in half an hour.")
            return

        self.memory.add_reminder(task, remind_at.isoformat(), user_id=user_id)
        self.voice.speak(f"Okay, I'll remind you to {task} at {format_time(remind_at)}.")

    # ---------------- BACKGROUND CHECKER ----------------
    def check_due_once(self) -> List[str]:
        """Fires every reminder that is due. Returns their texts."""
        fired = []
        for reminder in self.memory.get_due_reminders(self._now().isoformat()):
            try:
                # Done FIRST: if speaking fails or hangs, it is not repeated forever.
                self.memory.mark_reminder_done(reminder["id"])
            except Exception:
                log.exception("Could not mark reminder %s as done; skipping it", reminder["id"])
                continue
            fired.append(reminder["task"])
            self._announce(reminder["task"])
        return fired

    def _announce(self, task: str) -> None:
        # Two separate try blocks: a broken tray callback must not stop the
        # spoken reminder, and a speech error must not stop the callback.
        if self.on_due:
            try:
                self.on_due(task)
            except Exception:
                log.exception("on_due callback failed")
        try:
            self.voice.speak(f"Reminder: {task}")
        except Exception:
            log.exception("Could not speak a reminder")

    def start_background_checker(self) -> None:
        """Starts one daemon thread (a second call does nothing)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._check_loop, name="reminder-checker",
                                        daemon=True)
        self._thread.start()

    def _check_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_due_once()
            except Exception:  # the thread must survive anything
                log.exception("Reminder check failed; will try again")
            self._stop_event.wait(self.check_interval)  # wakes at once on stop()

    def stop(self) -> None:
        self._stop_event.set()
