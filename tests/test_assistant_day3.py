"""Day 3 features as the user meets them: through Assistant.execute().
Fake voice and listener, temporary database, fixed clock. No mic, no speakers."""

import datetime

import pytest

import assistant
import timeutil
from assistant import Assistant, normalize_query
from intent_classifier import IntentClassifier

NOW = datetime.datetime(2026, 11, 2, 10, 0, 0)


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
    return IntentClassifier()


@pytest.fixture
def bot(tmp_path, shared_classifier):
    a = Assistant(voice=FakeVoice(), listener=FakeListener(),
                  db_path=str(tmp_path / "d3.db"), classifier=shared_classifier,
                  start_reminders=False, log_path=str(tmp_path / "d3.log"))
    a._now = lambda: NOW
    yield a
    assistant.close_logging()


# ---------------- math symbols ----------------
@pytest.mark.parametrize("raw, expected", [
    ("12 + 7", "12 plus 7"),
    ("What's 6 x 7?", "whats 6 times 7"),
    ("6 * 7", "6 times 7"),
    ("6 × 7", "6 times 7"),
    ("100/4", "100 divided by 4"),
    ("100 ÷ 4", "100 divided by 4"),
    ("10-3", "10 minus 3"),
    ("10 - 3", "10 minus 3"),
    ("2.5 + 1", "2.5 plus 1"),
    ("show my to-do list", "show my to do list"),    # a hyphen between words stays a space
    ("open notepad", "open notepad"),
])
def test_symbols_become_words(raw, expected):
    assert normalize_query(raw) == expected


# ---------------- calculator through the assistant ----------------
@pytest.mark.parametrize("sentence, answer", [
    ("what is fifteen plus twenty", "35"),
    ("add three and four", "7"),
    ("subtract five from ten", "5"),
    ("Raju, what is 12 + 7?", "19"),
    ("what is 100 / 4", "25"),
    ("what is 8 x 6", "48"),
    ("what is two plus three times four", "14"),
    ("multiply six by seven", "42"),
])
def test_calculator_by_assistant(bot, sentence, answer):
    bot.execute(sentence)
    assert bot.voice.last == f"The answer is {answer}"


def test_divide_by_zero_by_assistant(bot):
    bot.execute("what is ten divided by zero")
    assert "divide by zero" in bot.voice.last


# ---------------- reminders through the assistant ----------------
def due_reminders(bot):
    return bot.memory.get_due_reminders("2099-01-01T00:00:00")


def test_reminder_with_word_number(bot):
    bot.listener.answers = ["call mom", "in ten minutes"]
    bot.execute("set a reminder")
    assert [(r["task"], r["remind_at"]) for r in due_reminders(bot)] == [
        ("call mom", (NOW + datetime.timedelta(minutes=10)).isoformat())]
    assert bot.voice.last == "Okay, I'll remind you to call mom at 10:10 AM."


def test_reminder_time_in_the_first_sentence(bot):
    bot.listener.answers = ["stretch"]
    bot.execute("remind me in half an hour")
    assert due_reminders(bot)[0]["remind_at"] == (NOW + datetime.timedelta(minutes=30)).isoformat()


def test_reminder_belongs_to_the_logged_in_user(bot):
    bot.listener.answers = ["Asha", "1234", "1234"]
    bot.execute("create a profile")
    bot.listener.answers = ["pay rent", "in an hour"]
    bot.execute("set a reminder")
    assert due_reminders(bot)[0]["user_id"] == bot.current_user_id != 0


def test_on_due_is_connected(tmp_path, shared_classifier):
    got = []
    a = Assistant(voice=FakeVoice(), listener=FakeListener(), db_path=str(tmp_path / "x.db"),
                  classifier=shared_classifier, start_reminders=False,
                  log_path=str(tmp_path / "x.log"), on_due=got.append)
    try:
        a._now = lambda: NOW
        a.memory.add_reminder("water plants", (NOW - datetime.timedelta(seconds=1)).isoformat())
        a.reminders.check_due_once()
        assert got == ["water plants"]
    finally:
        assistant.close_logging()


# ---------------- profiles through the assistant ----------------
def test_profile_flow_with_exact_pin(bot):
    bot.listener.answers = ["Asha", "1 2 3 4", "1 2 3 4"]
    bot.execute("create a profile")
    assert bot.current_user["name"] == "Asha"
    bot.execute("log me out")
    assert bot.current_user is None

    bot.listener.answers = ["1235"]
    bot.execute("log me in")
    assert bot.current_user is None                      # the old fuzzy bug let this in

    bot.listener.answers = ["one two three four"]
    bot.execute("log me in")
    assert bot.current_user["name"] == "Asha"
    bot.execute("who am i")
    assert "Asha" in bot.voice.last


def test_login_locks_after_three_wrong_pins(bot):
    bot.listener.answers = ["Asha", "1234", "1234"]
    bot.execute("create a profile")
    bot.execute("log out")
    for _ in range(3):
        bot.listener.answers = ["9999"]
        bot.execute("log in")
    bot.listener.answers = ["1234"]
    bot.execute("log in")
    assert bot.current_user is None
    assert "wait" in bot.voice.last


# ---------------- wiring ----------------
def test_format_time_still_importable_from_assistant():
    assert assistant.format_time is timeutil.format_time


def test_gui_mode_flags_reach_the_listener(tmp_path, shared_classifier):
    errors = []
    a = Assistant(voice=FakeVoice(), db_path=str(tmp_path / "g.db"), classifier=shared_classifier,
                  start_reminders=False, log_path=str(tmp_path / "g.log"),
                  allow_text_fallback=False, on_error=errors.append)
    try:
        assert a.listener.allow_text_fallback is False
        assert a.listener.on_error == errors.append
    finally:
        assistant.close_logging()


def test_mic_waits_for_the_voice(tmp_path, shared_classifier):
    class TalkingVoice(FakeVoice):
        def wait_until_idle(self, timeout=None):
            return True

    voice = TalkingVoice()
    a = Assistant(voice=voice, db_path=str(tmp_path / "w.db"), classifier=shared_classifier,
                  start_reminders=False, log_path=str(tmp_path / "w.log"))
    try:
        assert a.listener.before_listen == voice.wait_until_idle
    finally:
        assistant.close_logging()


# ---------------- follow-up mode: no wake word right after a reply ----------------
@pytest.fixture
def timed_bot(bot):
    bot.time = [1000.0]
    bot._clock = lambda: bot.time[0]
    return bot


def hear(bot, text):
    bot.listener.answers = [text]
    return bot.listen_for_command()


def test_wake_word_is_needed_at_first(timed_bot):
    assert hear(timed_bot, "open notepad") is None
    assert hear(timed_bot, "raju open notepad") == "open notepad"


def test_no_wake_word_needed_right_after_a_reply(timed_bot):
    timed_bot.execute("what is the time")
    timed_bot.time[0] += 6
    assert hear(timed_bot, "what is the date") == "what is the date"


def test_each_reply_keeps_the_window_open(timed_bot):
    for _ in range(3):
        timed_bot.execute("what is the time")
        timed_bot.time[0] += 9
        assert hear(timed_bot, "what is the date") == "what is the date"


def test_window_closes_after_a_while(timed_bot):
    import config
    timed_bot.execute("what is the time")
    timed_bot.time[0] += config.FOLLOW_UP_SECONDS + 1
    assert hear(timed_bot, "what is the date") is None


def test_a_long_command_that_started_in_time_is_accepted(timed_bot):
    # The window is checked when listening STARTED, not when the sentence ended.
    import config
    timed_bot.execute("what is the time")
    started = timed_bot.time[0]
    timed_bot.listener.answers = ["what is the date"]
    original = timed_bot.listener.listen

    def slow_listen():
        timed_bot.time[0] = started + config.FOLLOW_UP_SECONDS + 3   # speech ended late
        return original()
    timed_bot.listener.listen = slow_listen
    assert timed_bot.listen_for_command() == "what is the date"


def test_follow_up_can_be_switched_off(timed_bot, monkeypatch):
    import config
    monkeypatch.setattr(config, "FOLLOW_UP_SECONDS", 0)
    timed_bot.execute("what is the time")
    assert hear(timed_bot, "what is the date") is None


def test_wake_word_still_works_inside_the_window(timed_bot):
    timed_bot.execute("what is the time")
    assert hear(timed_bot, "raju what is the date") == "what is the date"


def test_exit_does_not_open_the_window(timed_bot):
    with pytest.raises(SystemExit):
        timed_bot.execute("exit")
    assert hear(timed_bot, "what is the date") is None


def test_asked_questions_use_the_longer_listening(tmp_path, shared_classifier):
    class AnswerListener(FakeListener):
        used = []

        def listen(self):
            self.used.append("listen")
            return ""

        def listen_answer(self):
            self.used.append("answer")
            return "buy milk"

    listener = AnswerListener()
    a = Assistant(voice=FakeVoice(), listener=listener, db_path=str(tmp_path / "q.db"),
                  classifier=shared_classifier, start_reminders=False, log_path=str(tmp_path / "q.log"))
    try:
        a.execute("add a task")
        assert listener.used == ["answer"]
        assert a.memory.get_todos()[0]["task"] == "buy milk"
    finally:
        assistant.close_logging()


def test_follow_up_seconds_left(timed_bot):
    import config
    assert timed_bot.follow_up_seconds_left() == 0
    timed_bot.execute("what is the time")
    assert timed_bot.follow_up_seconds_left() == config.FOLLOW_UP_SECONDS
    timed_bot.time[0] += 4
    assert timed_bot.follow_up_seconds_left() == config.FOLLOW_UP_SECONDS - 4
    timed_bot.time[0] += 100
    assert timed_bot.follow_up_seconds_left() == 0


def test_login_retry_through_the_assistant(bot):
    bot.listener.answers = ["Asha", "1234", "1234"]
    bot.execute("create a profile")
    bot.execute("log out")
    bot.listener.answers = ["9999", "1234"]    # wrong, then right, after ONE "log in"
    bot.execute("log in")
    assert bot.current_user["name"] == "Asha"
