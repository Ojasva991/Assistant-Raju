"""Tests for section D: reminder parser and the checker. No real waiting:
a fixed 'now', a fake voice and a temporary database."""

import datetime
import threading
import time

import pytest

from database import MemoryManager
from features.reminders import ReminderFeature, parse_relative_time

NOW = datetime.datetime(2026, 11, 2, 10, 0, 0)
M = datetime.timedelta


class FakeVoice:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


class FakeListener:
    def __init__(self, answers=()):
        self.answers = list(answers)

    def listen(self):
        return self.answers.pop(0) if self.answers else ""


@pytest.fixture
def memory(tmp_path):
    return MemoryManager(str(tmp_path / "r.db"))


def make(memory, answers=(), voice=None, **kwargs):
    voice = voice or FakeVoice()
    kwargs.setdefault("now", lambda: NOW)
    return ReminderFeature(memory, voice, FakeListener(answers), **kwargs), voice


# ---------------- the parser ----------------
@pytest.mark.parametrize("text, delta", [
    ("in ten minutes", M(minutes=10)),
    ("in 10 minutes", M(minutes=10)),
    ("after 5 minutes", M(minutes=5)),
    ("after five minutes", M(minutes=5)),
    ("in an hour", M(hours=1)),
    ("in one hour", M(hours=1)),
    ("in half an hour", M(minutes=30)),
    ("in a half hour", M(minutes=30)),
    ("in two hours", M(hours=2)),
    ("in 2 hours", M(hours=2)),
    ("in a minute", M(minutes=1)),
    ("in twenty five seconds", M(seconds=25)),
    ("in two and a half hours", M(hours=2, minutes=30)),
    ("in an hour and ten minutes", M(hours=1, minutes=10)),
    ("in 1 hour 30 minutes", M(hours=1, minutes=30)),
    ("in a quarter of an hour", M(minutes=15)),
    ("in 90 minutes", M(minutes=90)),
    ("in 10min", M(minutes=10)),
    ("ten minutes", M(minutes=10)),                     # "in" is optional
    ("Remind me IN TEN MINUTES!", M(minutes=10)),
    ("remind me to call mom in 5 minutes", M(minutes=5)),
])
def test_parse_relative_time(text, delta):
    assert parse_relative_time(text, NOW) == NOW + delta


@pytest.mark.parametrize("text", [
    "", None, "tomorrow", "remind me to call mom", "in five six minutes",
    "in zero minutes", "in minutes", "my second cousin", "in banana hours",
])
def test_parse_returns_none_instead_of_guessing(text):
    assert parse_relative_time(text, NOW) is None


# ---------------- adding a reminder by voice ----------------
def test_add_reminder_asks_task_then_time(memory):
    feature, voice = make(memory, ["to call mom", "in ten minutes"])
    feature.add_reminder(user_id=3)
    rows = memory.get_due_reminders("2099-01-01T00:00:00")
    assert [(r["task"], r["remind_at"], r["user_id"]) for r in rows] == [
        ("call mom", (NOW + M(minutes=10)).isoformat(), 3)]  # "to " is removed from the task
    assert voice.said[-1] == "Okay, I'll remind you to call mom at 10:10 AM."


def test_time_in_the_first_sentence_is_not_asked_again(memory):
    feature, voice = make(memory, ["buy milk"])  # only ONE answer is given
    feature.add_reminder(query="remind me in half an hour")
    rows = memory.get_due_reminders("2099-01-01T00:00:00")
    assert rows[0]["remind_at"] == (NOW + M(minutes=30)).isoformat()
    assert not any("When should I" in s for s in voice.said)


def test_unclear_time_sets_no_reminder(memory):
    feature, voice = make(memory, ["call mom", "sometime later"])
    feature.add_reminder()
    assert memory.get_due_reminders("2099-01-01T00:00:00") == []
    assert "not set" in voice.said[-1]


def test_missing_task_sets_no_reminder(memory):
    feature, voice = make(memory, [""])
    feature.add_reminder()
    assert memory.get_due_reminders("2099-01-01T00:00:00") == []


# ---------------- the checker ----------------
def add_due(memory, text="call mom", at=NOW - M(seconds=1), user_id=0):
    memory.add_reminder(text, at.isoformat(), user_id=user_id)


def test_due_reminder_is_spoken_once(memory):
    add_due(memory)
    feature, voice = make(memory)
    assert feature.check_due_once() == ["call mom"]
    assert voice.said == ["Reminder: call mom"]
    assert feature.check_due_once() == []  # already done: never repeated


def test_future_reminder_is_not_fired(memory):
    add_due(memory, at=NOW + M(minutes=5))
    feature, voice = make(memory)
    assert feature.check_due_once() == []
    assert voice.said == []


def test_reminders_of_every_user_fire(memory):
    add_due(memory, "a", user_id=0)
    add_due(memory, "b", user_id=7)
    feature, _ = make(memory)
    assert sorted(feature.check_due_once()) == ["a", "b"]


def test_marked_done_before_speaking(memory):
    add_due(memory)
    seen = {}

    class CheckingVoice(FakeVoice):
        def speak(self, text):
            # At this moment the reminder must already be finished in the database.
            seen["still_due"] = memory.get_due_reminders(NOW.isoformat())
            super().speak(text)

    feature, _ = make(memory, voice=CheckingVoice())
    feature.check_due_once()
    assert seen["still_due"] == []


def test_speech_failure_does_not_repeat_the_reminder(memory):
    add_due(memory)

    class BrokenVoice:
        def speak(self, text):
            raise RuntimeError("speaker broke")

    feature, _ = make(memory, voice=BrokenVoice())
    assert feature.check_due_once() == ["call mom"]   # no exception escapes
    assert feature.check_due_once() == []             # and it does not come back


def test_on_due_gets_the_text(memory):
    add_due(memory)
    got = []
    feature, voice = make(memory, on_due=got.append)
    feature.check_due_once()
    assert got == ["call mom"]
    assert voice.said == ["Reminder: call mom"]


def test_broken_on_due_does_not_stop_the_spoken_reminder(memory):
    add_due(memory)

    def bad_callback(text):
        raise RuntimeError("tray crashed")

    feature, voice = make(memory, on_due=bad_callback)
    feature.check_due_once()
    assert voice.said == ["Reminder: call mom"]


def wait_for(condition, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_thread_survives_an_error_and_keeps_working(memory):
    add_due(memory)
    feature, voice = make(memory, check_interval=0.01)
    real = memory.get_due_reminders
    calls = {"n": 0}

    def flaky(now_iso=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database was busy")
        return real(now_iso)

    memory.get_due_reminders = flaky
    feature.start_background_checker()
    try:
        assert wait_for(lambda: voice.said == ["Reminder: call mom"])
        assert feature._thread.is_alive()
        assert calls["n"] >= 2
    finally:
        feature.stop()
        feature._thread.join(timeout=2)


def test_stop_ends_the_thread_quickly_even_with_a_long_interval(memory):
    feature, _ = make(memory, check_interval=60)
    feature.start_background_checker()
    thread = feature._thread
    feature.stop()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_starting_twice_makes_one_thread(memory):
    feature, _ = make(memory, check_interval=60)
    feature.start_background_checker()
    first = feature._thread
    feature.start_background_checker()
    assert feature._thread is first
    assert sum(t.name == "reminder-checker" for t in threading.enumerate()) >= 1
    feature.stop()
    first.join(timeout=2)
