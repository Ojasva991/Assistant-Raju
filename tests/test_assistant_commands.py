"""
Tests for section B (assistant core).
No microphone, speakers, internet or real app launching:
  - FakeVoice records what Raju says
  - FakeListener gives scripted answers (for yes/no questions)
  - the database is a temporary file
  - subprocess.Popen, webbrowser.open and the OS "open" helper are replaced
Run:  python -m pytest tests -q
"""

import datetime
import os

import pytest

import assistant
import config
from assistant import Assistant, format_time, is_yes, normalize_query
from fuzzy_match import find_known_name
from intent_classifier import IntentClassifier


class FakeVoice:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)

    @property
    def last(self):
        return self.said[-1] if self.said else ""


class FakeListener:
    def __init__(self, answers=()):
        self.answers = list(answers)

    def listen(self):
        return self.answers.pop(0) if self.answers else ""


@pytest.fixture(scope="module")
def shared_classifier():
    return IntentClassifier()  # trained once, reused by every test here


@pytest.fixture
def bot(tmp_path, monkeypatch, shared_classifier):
    launched, opened, system_opened = [], [], []
    monkeypatch.setattr(assistant.subprocess, "Popen",
                        lambda args, **kw: launched.append(args))
    monkeypatch.setattr(assistant.webbrowser, "open",
                        lambda url: opened.append(url) or True)
    monkeypatch.setattr(assistant, "open_with_system", system_opened.append)

    def boom(*args, **kwargs):
        raise AssertionError("os.system must never be used")
    monkeypatch.setattr(os, "system", boom)

    a = Assistant(voice=FakeVoice(), listener=FakeListener(),
                  db_path=str(tmp_path / "test.db"),
                  classifier=shared_classifier, start_reminders=False,
                  log_path=str(tmp_path / "test.log"))
    a.launched, a.opened, a.system_opened = launched, opened, system_opened
    yield a
    assistant.close_logging()  # release the log file (Windows cannot delete open files)


# ---------------- cleaning the query ----------------
@pytest.mark.parametrize("raw, expected", [
    ("OPEN NOTEPAD!", "open notepad"),
    ("  Open Notepad please  ", "open notepad please"),
    ("Raju, open notepad", "open notepad"),
    ("raju open youtube", "open youtube"),
    ("What's the time?", "whats the time"),
])
def test_normalize_query(raw, expected):
    assert normalize_query(raw) == expected


def test_old_name_still_works():
    assert assistant.J is assistant.Assistant


# ---------------- open apps and sites (the "done when" sentences) ----------------
@pytest.mark.parametrize("sentence, command", [
    ("Open Notepad please", "notepad"),
    ("launch calculator", "calc"),
    ("OPEN NOTEPAD!", "notepad"),
    ("raju open paint", "mspaint"),
    ("start task manager", "taskmgr"),
    ("opne notepad", "notepad"),       # mishearing
    ("open note pad", "notepad"),      # mishearing
])
def test_open_app_sentences(bot, sentence, command):
    bot.execute(sentence)
    assert bot.launched == [[command]]
    assert bot.opened == []


@pytest.mark.parametrize("sentence, url", [
    ("go to youtube", "https://youtube.com"),
    ("take me to github", "https://github.com"),
    ("open my gmail", "https://mail.google.com"),
    ("Open Google!", "https://google.com"),
])
def test_open_site_sentences(bot, sentence, url):
    bot.execute(sentence)
    assert bot.opened == [url]
    assert bot.launched == []


def test_wrong_kind_from_the_model_is_repaired(bot):
    # The model said "open_app" but the name is a website: it must still open.
    bot._handle_intent("open_app", "open youtube")
    assert bot.opened == ["https://youtube.com"]


def test_unknown_name_lists_known_names(bot):
    bot._handle_intent("open_app", "open spaceship")
    assert bot.launched == [] and bot.opened == []
    assert "notepad" in bot.voice.last
    bot._handle_intent("open_site", "open spaceship")
    assert "youtube" in bot.voice.last


def test_failed_start_is_reported(bot, monkeypatch):
    def fail(args, **kw):
        raise FileNotFoundError("no such program")
    monkeypatch.setattr(assistant.subprocess, "Popen", fail)
    bot.execute("open notepad")
    assert "couldn't open notepad" in bot.voice.last


def test_uri_apps_use_the_system_helper(bot):
    bot.execute("open settings")
    assert bot.system_opened == ["ms-settings:"]
    assert bot.launched == []


def test_no_shell_and_only_allowed_commands():
    assert assistant.run_allowed_command("del /q *") is False
    assert assistant.run_allowed_command("notepad & calc") is False


# ---------------- learned commands ----------------
def test_learned_command_outside_apps_is_refused(bot):
    bot.memory.teach_command("hack", "del /q C:\\*")
    bot.listener.answers = ["yes"]          # even a "yes" must not help
    bot.execute("hack")
    assert bot.launched == []
    assert "safe list" in bot.voice.last


def test_learned_command_inside_apps_runs_after_yes(bot):
    bot.memory.teach_command("my editor", "notepad")
    bot.listener.answers = ["yes please"]
    bot.execute("My Editor!")
    assert bot.launched == [["notepad"]]


@pytest.mark.parametrize("answer", ["no", "yesterday", "not sure", "", "maybe later"])
def test_learned_command_cancelled_when_not_a_clear_yes(bot, answer):
    bot.memory.teach_command("my editor", "notepad")
    bot.listener.answers = [answer]
    bot.execute("my editor")
    assert bot.launched == []
    assert "cancelled" in bot.voice.last


def test_teaching_only_accepts_known_apps(bot):
    bot.listener.answers = ["start my day fast", "open notepad"]
    bot._learn_command()
    assert bot.memory.get_command("start my day fast") == "notepad"
    bot.listener.answers = ["wipe disk", "format the disk"]
    bot._learn_command()
    assert bot.memory.get_command("wipe disk") is None


# ---------------- yes / no ----------------
@pytest.mark.parametrize("answer, expected", [
    ("yes", True), ("Yeah", True), ("yep", True), ("sure", True),
    ("okay", True), ("OK!", True), ("do it", True), ("yes please", True),
    ("no", False), ("nope", False), ("yesterday", False), ("okayish", False),
    ("not okay", False), ("don't do it", False), ("yes no", False),
    ("", False), ("banana", False),
])
def test_is_yes(answer, expected):
    assert is_yes(answer) is expected


# ---------------- time ----------------
@pytest.mark.parametrize("hour, minute, text", [
    (15, 44, "3:44 PM"), (0, 5, "12:05 AM"), (12, 0, "12:00 PM"),
    (9, 7, "9:07 AM"), (23, 59, "11:59 PM"),
])
def test_format_time(hour, minute, text):
    assert format_time(datetime.datetime(2026, 11, 2, hour, minute)) == text


def test_time_command_speaks_12_hour_clock(bot):
    bot._now = lambda: datetime.datetime(2026, 11, 2, 15, 44)
    bot.execute("what is the time")
    assert bot.voice.last == "The time is 3:44 PM"


# ---------------- one prediction, history, logging ----------------
def test_intent_is_predicted_once_and_logged_to_history(bot):
    calls = []
    real = bot.ai.predict
    bot.ai = type("Spy", (), {"predict": lambda self, t: calls.append(t) or real(t)})()
    bot.execute("Open Notepad please")
    assert len(calls) == 1
    row = bot.memory.get_history()[0]
    assert row["query"] == "open notepad please" and row["intent"] == "open_app"


def test_log_file_has_query_intent_and_confidence(bot, tmp_path):
    bot.execute("open notepad")
    text = (tmp_path / "test.log").read_text(encoding="utf-8")
    assert "query='open notepad'" in text and "intent=open_app" in text
    assert "confidence=" in text


# ---------------- other basics ----------------
def test_exit_says_goodbye_and_stops(bot):
    with pytest.raises(SystemExit):
        bot.execute("Exit!")
    assert "Goodbye" in bot.voice.last


def test_greeting_and_wake_word_alone(bot):
    bot.execute("hello")
    assert "Raju" in bot.voice.last
    bot.execute("Raju")
    assert bot.voice.last == "Yes?"


def test_unknown_gives_example_command(bot):
    bot.execute("what is the weather today")
    assert bot.voice.last in assistant.UNKNOWN_RESPONSES


def test_music_uses_the_system_helper(bot, tmp_path, monkeypatch):
    (tmp_path / "song.mp3").write_bytes(b"x")
    monkeypatch.setattr(config, "MUSIC_DIR", str(tmp_path))
    bot.execute("play music")
    assert bot.system_opened and bot.system_opened[0].endswith("song.mp3")


# ---------------- the name finder ----------------
def test_find_known_name():
    names = list(config.APPS)
    assert find_known_name("open notepad please", names) == "notepad"
    assert find_known_name("open command prompt", names) == "command prompt"
    assert find_known_name("opne note pad", names) == "notepad"
    assert find_known_name("open the door", names) is None
    assert find_known_name("open note pad", names, fuzzy=False) is None
