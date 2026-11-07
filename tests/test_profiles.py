"""Tests for section C: PIN hashing, exact match, lockout, migration.
Fake voice, scripted listener, temporary database, fake clock."""

import hmac
import os
import re
import sqlite3

import pytest

import config
from database import MemoryManager
from features import user_profile
from features.user_profile import UserProfileFeature, hash_pin, normalize_pin, verify_pin


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


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    memory = MemoryManager(str(tmp_path / "p.db"))
    voice, listener, clock = FakeVoice(), FakeListener(), FakeClock()
    feature = UserProfileFeature(memory, voice, listener, clock=clock)
    return feature, memory, voice, listener, clock


def register(setup, name="Asha", pin="1234"):
    feature, _, _, listener, _ = setup
    listener.answers = [name, pin, pin]   # the PIN is said twice (confirmation)
    return feature.register()


def login(setup, pin):
    feature, _, _, listener, _ = setup
    listener.answers = [pin]
    return feature.login()


# ---------------- normalising what was heard ----------------
@pytest.mark.parametrize("heard, pin", [
    ("1234", "1234"),
    ("1 2 3 4", "1234"),
    ("one two three four", "1234"),
    ("One, Two, Three, Four.", "1234"),
    ("12 34", "1234"),
    ("one 2 three 4", "1234"),
    ("zero zero seven", "007"),
    ("oh one two three", "0123"),
    ("blue sky", "bluesky"),           # a word PIN is not turned into digits
    ("one two apple", "onetwoapple"),  # ... and neither is a mix of digits and words
    ("  Banana  ", "banana"),
    ("", ""),
    (None, ""),
])
def test_normalize_pin(heard, pin):
    assert normalize_pin(heard) == pin


# ---------------- hashing ----------------
def test_hash_has_salt_and_never_contains_the_pin():
    one, two = hash_pin("1234"), hash_pin("1234")
    assert one != two                       # a new salt each time
    assert one.startswith("pbkdf2_sha256$")
    assert "1234" not in one.split("$")[0]
    assert verify_pin("1234", one) and verify_pin("1234", two)
    assert not verify_pin("1235", one)


@pytest.mark.parametrize("stored", ["", "1234", "pbkdf2_sha256$x$y$z", "md5$1$00$00",
                                    "pbkdf2_sha256$0$00$00", "a$b$c"])
def test_damaged_or_empty_hash_never_matches(stored):
    assert verify_pin("1234", stored) is False


def test_pin_compare_uses_compare_digest(monkeypatch):
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(user_profile.hmac, "compare_digest",
                        lambda a, b: calls.append(1) or real(a, b))
    verify_pin("1234", hash_pin("1234"))
    assert calls


def test_real_hash_setting_is_slow_enough():
    # The test suite lowers the rounds for speed; the real file must keep them high.
    with open(os.path.join(os.path.dirname(config.__file__), "config.py"), encoding="utf-8") as f:
        rounds = int(re.search(r"PIN_HASH_ITERATIONS\s*=\s*([\d_]+)", f.read()).group(1).replace("_", ""))
    assert rounds >= 100_000


# ---------------- register and login ----------------
def test_register_stores_only_a_hash(setup):
    _, memory, voice, _, _ = setup
    user = register(setup)
    assert user == {"id": 1, "name": "Asha"}          # the hash is not handed around
    row = memory.get_all_users()[0]
    assert row["pin"] == "" and row["pin_hash"].startswith("pbkdf2_sha256$")
    with sqlite3.connect(memory.db_path) as conn:
        dump = "\n".join(conn.iterdump())
    assert "1234" not in dump.replace("1234567", "")   # no plain-text PIN anywhere in the file
    assert "Profile created" in voice.last


def test_exact_pin_logs_in_in_every_spoken_form(setup):
    register(setup)
    for heard in ("1234", "1 2 3 4", "one two three four", "One, two, three, four."):
        assert login(setup, heard)["name"] == "Asha"


def test_pin_1235_does_not_log_in_as_1234(setup):
    # The original bug: fuzzy matching scored "1235" vs "1234" at 0.75.
    register(setup)
    assert login(setup, "1235") is None
    assert login(setup, "12345") is None
    assert login(setup, "123") is None
    assert login(setup, "4321") is None


def test_login_returns_the_right_user_of_several(setup):
    register(setup, "Asha", "1234")
    register(setup, "Ravi", "9876")
    assert login(setup, "9876")["name"] == "Ravi"
    assert login(setup, "1234")["name"] == "Asha"


def test_login_without_profiles(setup):
    assert login(setup, "1234") is None
    assert "no profiles" in setup[2].last


def test_short_pin_is_rejected(setup):
    assert register(setup, pin="123") is None
    assert "too short" in setup[2].last
    assert setup[1].get_all_users() == []


def test_duplicate_pin_is_rejected_without_naming_the_owner(setup):
    register(setup, "Asha", "1234")
    assert register(setup, "Ravi", "1 2 3 4") is None
    assert len(setup[1].get_all_users()) == 1
    assert "Asha" not in setup[2].last
    assert "already" not in setup[2].last


def test_cancel_when_nothing_is_heard(setup):
    feature, _, voice, listener, _ = setup
    listener.answers = [""]
    assert feature.register() is None
    listener.answers = ["Asha", ""]
    assert feature.register() is None


# ---------------- lockout ----------------
def test_three_wrong_pins_lock_login_for_60_seconds(setup):
    _, _, voice, listener, clock = setup
    register(setup)
    for _ in range(3):
        assert login(setup, "0000") is None
    assert "locked for 60 seconds" in voice.last

    # Locked: even the CORRECT pin is refused, and Raju does not even listen.
    listener.answers = ["1234"]
    assert setup[0].login() is None
    assert listener.answers == ["1234"]          # the answer was never consumed
    assert "wait 60 seconds" in voice.last

    clock.now += 30
    assert login(setup, "1234") is None
    assert "wait 30 seconds" in voice.last

    clock.now += 31                               # 61 s after the lock started
    assert login(setup, "1234")["name"] == "Asha"


def test_wrong_pins_reset_after_a_success(setup):
    register(setup)
    login(setup, "0000")
    login(setup, "0000")
    assert login(setup, "1234") is not None       # success resets the counter
    login(setup, "0000")
    login(setup, "0000")
    assert login(setup, "1234") is not None       # still not locked


def test_lock_counts_only_in_a_row_and_silence_is_free(setup):
    register(setup)
    for _ in range(5):
        setup[3].answers = [""]
        setup[0].login()                          # nothing heard: no strike
    assert login(setup, "1234") is not None


def test_tries_left_message(setup):
    register(setup)
    login(setup, "0000")
    assert any("2 tries left" in said for said in setup[2].said)
    login(setup, "0000")
    assert any("1 try left" in said for said in setup[2].said)


def test_register_is_blocked_while_locked(setup):
    register(setup)
    for _ in range(3):
        login(setup, "0000")
    assert register(setup, "Ravi", "9876") is None
    assert len(setup[1].get_all_users()) == 1


def test_guessing_pins_through_register_also_locks(setup):
    register(setup, "Asha", "1234")
    for guess in ("1234", "1234", "1234"):        # "already used" would be an oracle
        register(setup, "Eve", guess)
    assert setup[0].lock_seconds_left() == config.PIN_LOCK_SECONDS


# ---------------- migration of old databases ----------------
def make_old_database(path, pins):
    """The database layout of v2.8: plain-text PIN column, no pin_hash."""
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL, pin TEXT NOT NULL, created_at TEXT NOT NULL)""")
        for name, pin in pins:
            conn.execute("INSERT INTO users (name, pin, created_at) VALUES (?, ?, 'x')", (name, pin))


def test_old_plain_pins_become_hashes_and_the_old_column_is_blank(tmp_path):
    path = str(tmp_path / "old.db")
    make_old_database(path, [("Asha", "1234"), ("Ravi", "onetwonineeight"), ("Mina", "bluesky")])
    memory = MemoryManager(path)
    feature = UserProfileFeature(memory, FakeVoice(), FakeListener(["1234"]))

    rows = memory.get_all_users()
    assert all(r["pin"] == "" and r["pin_hash"].startswith("pbkdf2_sha256$") for r in rows)
    with sqlite3.connect(path) as conn:
        dump = "\n".join(conn.iterdump())
    assert "onetwonineeight" not in dump and "bluesky" not in dump   # no plain text left
    assert "'1234'" not in dump

    assert feature.login()["name"] == "Asha"


def test_old_word_pin_still_works_after_migration(tmp_path):
    path = str(tmp_path / "old.db")
    make_old_database(path, [("Mina", "bluesky"), ("Ravi", "onetwonineeight")])
    memory = MemoryManager(path)
    feature = UserProfileFeature(memory, FakeVoice(), FakeListener(["blue sky"]))
    assert feature.login()["name"] == "Mina"
    feature.listener.answers = ["1 2 9 8"]
    assert feature.login()["name"] == "Ravi"


def test_migration_runs_once(tmp_path):
    path = str(tmp_path / "old.db")
    make_old_database(path, [("Asha", "1234")])
    memory = MemoryManager(path)
    first = UserProfileFeature(memory, FakeVoice(), FakeListener())
    before = memory.get_all_users()[0]["pin_hash"]
    assert first.migrate_plain_pins() == 0
    assert memory.get_all_users()[0]["pin_hash"] == before   # not hashed a second time


def test_new_database_has_the_new_column(tmp_path):
    memory = MemoryManager(str(tmp_path / "new.db"))
    uid = memory.add_user("Asha", hash_pin("1234"))
    row = memory.get_user_by_id(uid)
    assert row["pin"] == "" and row["pin_hash"]


# ---------------- follow-up fixes: confirmation and tolerant PIN hearing ----------------
@pytest.mark.parametrize("heard, pin", [
    ("my pin is 1234", "1234"),
    ("the pin is one two three four", "1234"),
    ("it's 4 7 1 1", "4711"),
    ("7,286", "7286"),                                  # Google writes 7,286
    ("seven to eight six", "7286"),                     # 'to' heard for two
    ("one for three for", "1434"),
    ("seven thousand two hundred eighty six", "7286"),  # said as a number
    ("to for", "tofor"),                                # no real digit: stays a word PIN
    ("blue sky", "bluesky"),
])
def test_normalize_pin_understands_what_google_really_writes(heard, pin):
    assert normalize_pin(heard) == pin


def test_register_and_login_agree_on_odd_spellings(setup):
    register(setup, "Asha", "seven to eight six")
    for heard in ("7286", "7 2 8 6", "my pin is 7,286", "seven two eight six"):
        assert login(setup, heard)["name"] == "Asha"


def test_pin_must_be_confirmed(setup):
    feature, memory, voice, listener, _ = setup
    listener.answers = ["Asha", "1234", "1235"]          # second time was misheard
    assert feature.register() is None
    assert "did not match" in voice.last
    assert memory.get_all_users() == []
    assert not feature.lock_seconds_left()               # a misheard PIN is not a wrong try


def test_confirmation_may_be_said_differently(setup):
    feature, _, _, listener, _ = setup
    listener.answers = ["Asha", "1 2 3 4", "one two three four"]
    assert feature.register()["name"] == "Asha"


def test_name_is_cleaned(setup):
    feature, _, _, listener, _ = setup
    listener.answers = ["my name is ojas upad", "1234", "1234"]
    assert feature.register()["name"] == "Ojas Upad"


# ---------------- retry inside the same login (no need to say "log in" again) ----------------
def test_wrong_pin_then_right_pin_in_one_login(setup):
    feature, _, voice, listener, _ = setup
    register(setup)
    listener.answers = ["0000", "1234"]        # one "log in", two answers
    assert feature.login()["name"] == "Asha"
    assert any("2 tries left. Say it again" in said for said in voice.said)
    assert listener.answers == []


def test_three_wrong_pins_in_one_login_lock(setup):
    feature, _, voice, listener, _ = setup
    register(setup)
    listener.answers = ["0000", "1111", "2222", "1234"]   # the correct one comes too late
    assert feature.login() is None
    assert "locked for 60 seconds" in voice.last
    assert listener.answers == ["1234"]                   # not even listened to


def test_silence_after_a_wrong_pin_ends_login_without_another_strike(setup):
    feature, _, voice, listener, _ = setup
    register(setup)
    listener.answers = ["0000"]                # then nobody speaks
    assert feature.login() is None
    assert "login cancelled" in voice.last
    listener.answers = ["0000", "0000"]        # 1 strike before + 2 now = 3 -> lock
    feature.login()
    assert feature.lock_seconds_left() == config.PIN_LOCK_SECONDS


def test_first_silence_keeps_the_old_message(setup):
    register(setup)
    assert login(setup, "") is None
    assert setup[2].last == "I didn't catch that."


# ---------------- name or PIN not heard: say why, ask once more ----------------
class StatusListener(FakeListener):
    """A listener that also says WHY the last listen gave nothing."""

    def __init__(self, answers=(), statuses=()):
        super().__init__(answers)
        self.statuses = list(statuses)
        self.last_status = "ok"

    def listen(self):
        text = super().listen()
        self.last_status = "ok" if text else (self.statuses.pop(0) if self.statuses else "timeout")
        return text


def test_name_not_heard_asks_again_and_then_works(setup):
    feature, memory, voice, _, _ = setup
    feature.listener = StatusListener(["", "ojas upad", "1234", "1234"], ["unclear"])
    assert feature.register()["name"] == "Ojas Upad"
    assert any("couldn't make out the words" in s and "name again" in s for s in voice.said)


def test_silence_gets_a_different_message_than_unclear_speech(setup):
    feature, _, voice, _, _ = setup
    feature.listener = StatusListener(["", "ojas", "1234", "1234"], ["timeout"])
    feature.register()
    assert any("didn't hear anything" in s for s in voice.said)


def test_name_not_heard_twice_cancels(setup):
    feature, memory, voice, _, _ = setup
    feature.listener = StatusListener(["", ""], ["unclear", "unclear"])
    assert feature.register() is None
    assert voice.last == "I didn't catch that, cancelling."
    assert memory.get_all_users() == []


def test_pin_not_heard_asks_again(setup):
    feature, _, voice, _, _ = setup
    feature.listener = StatusListener(["Asha", "", "1234", "1234"], ["timeout"])
    assert feature.register()["name"] == "Asha"
    assert any("PIN again" in s for s in voice.said)


def test_login_pin_not_heard_asks_again(setup):
    register(setup)
    feature = setup[0]
    feature.listener = StatusListener(["", "1234"], ["timeout"])
    assert feature.login()["name"] == "Asha"


def test_only_pin_questions_are_marked_secret(setup):
    class Recorder(FakeListener):
        def __init__(self, answers):
            super().__init__(answers)
            self.secret_flags = []

        def listen_answer(self, secret=False):
            self.secret_flags.append(secret)
            return self.listen()

    feature = setup[0]
    feature.listener = Recorder(["Asha", "1234", "1234"])
    feature.register()
    assert feature.listener.secret_flags == [False, True, True]   # name, PIN, confirmation
    feature.listener = Recorder(["0000", "1234"])
    feature.login()
    assert feature.listener.secret_flags == [True, True]
