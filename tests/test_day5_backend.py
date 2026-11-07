"""
Day 5 backend tests: new database methods, section G small fixes.
No microphone, no speakers: fake voice and a temporary SQLite file.
"""

import csv
import datetime
import os
import sqlite3

import pytest

import config
from database import MemoryManager
from features import knowledge
from features.briefing import BriefingFeature, greeting_for
from features.history import HistoryFeature
from features.knowledge import KnowledgeFeature, extract_topic
from features.todo import TodoFeature


class FakeVoice:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


@pytest.fixture
def memory(tmp_path):
    return MemoryManager(str(tmp_path / "t.db"))


# ---------------- database ----------------
def test_delete_todo_only_for_its_owner(memory):
    memory.add_todo("mine", user_id=1)
    memory.add_todo("theirs", user_id=2)
    mine = memory.get_todos(user_id=1)[0]["id"]
    memory.delete_todo(mine, user_id=2)             # wrong user: nothing happens
    assert [t["task"] for t in memory.get_todos(user_id=1)] == ["mine"]
    memory.delete_todo(mine, user_id=1)
    assert memory.get_todos(user_id=1) == []
    assert [t["task"] for t in memory.get_todos(user_id=2)] == ["theirs"]


def test_complete_todo_with_user_id_checks_the_owner(memory):
    memory.add_todo("a", user_id=1)
    task_id = memory.get_todos(user_id=1)[0]["id"]
    memory.complete_todo(task_id, user_id=2)        # not the owner
    assert len(memory.get_todos(user_id=1)) == 1
    memory.complete_todo(task_id, user_id=1)
    assert memory.get_todos(user_id=1) == []
    memory.add_todo("b", user_id=1)
    memory.complete_todo(memory.get_todos(user_id=1)[0]["id"])   # old call style still works
    assert memory.get_todos(user_id=1) == []


def test_get_reminders_lists_pending_and_done_soonest_first(memory):
    memory.add_reminder("late", "2026-11-06T18:00:00", user_id=1)
    memory.add_reminder("early", "2026-11-06T08:00:00", user_id=1)
    memory.add_reminder("other user", "2026-11-06T09:00:00", user_id=2)
    memory.mark_reminder_done(memory.get_reminders(user_id=1)[0]["id"])
    rows = memory.get_reminders(user_id=1)
    assert [r["task"] for r in rows] == ["early", "late"]
    assert rows[0]["done"] == 1


def test_delete_reminder_only_for_its_owner(memory):
    memory.add_reminder("x", "2026-11-06T08:00:00", user_id=1)
    rid = memory.get_reminders(user_id=1)[0]["id"]
    memory.delete_reminder(rid, user_id=2)
    assert len(memory.get_reminders(user_id=1)) == 1
    memory.delete_reminder(rid, user_id=1)
    assert memory.get_reminders(user_id=1) == []


def test_clear_history_removes_only_this_users_rows(memory):
    memory.log_history("a", "time", user_id=1)
    memory.log_history("b", "time", user_id=1)
    memory.log_history("c", "time", user_id=2)
    assert memory.clear_history(user_id=1) == 2
    assert memory.get_history(user_id=1) == []
    assert len(memory.get_history(user_id=2)) == 1


def test_history_stores_confidence(memory):
    memory.log_history("what time is it", "time", confidence=0.93)
    memory.log_history("exit", "exit")
    rows = memory.get_history()
    assert rows[1]["confidence"] == pytest.approx(0.93)
    assert rows[0]["confidence"] is None


def test_old_history_table_without_confidence_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL "
                 "DEFAULT 0, query TEXT NOT NULL, intent TEXT, timestamp TEXT NOT NULL)")
    conn.execute("INSERT INTO history (user_id, query, intent, timestamp) VALUES (0, 'old', 'time', 'x')")
    conn.commit()
    conn.close()
    memory = MemoryManager(path)
    assert memory.get_history()[0]["confidence"] is None       # old row kept
    memory.log_history("new", "time", confidence=0.5)
    assert memory.get_history()[0]["confidence"] == 0.5


def test_assistant_logs_the_confidence(tmp_path):
    """The assistant must pass the one prediction's confidence to the history log."""
    from assistant import Assistant, close_logging
    from intent_classifier import IntentClassifier

    class Listener:
        before_listen = None

        def listen(self):
            return ""

    voice = FakeVoice()
    bot = Assistant(voice=voice, listener=Listener(), db_path=str(tmp_path / "a.db"),
                    classifier=IntentClassifier(), start_reminders=False,
                    log_path=str(tmp_path / "a.log"))
    bot.execute("what time is it")
    close_logging()
    row = bot.memory.get_history()[0]
    assert row["intent"] == "time"
    assert 0.0 < row["confidence"] <= 1.0


# ---------------- history CSV ----------------
def test_write_csv_has_confidence_and_speaks_nothing(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    voice = FakeVoice()
    feature = HistoryFeature(memory, voice)
    assert feature.write_csv() == (None, 0)                      # nothing yet
    memory.log_history("first", "time", confidence=0.9)
    memory.log_history("second", "date")
    path, count = feature.write_csv()
    assert count == 2 and voice.said == []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["timestamp", "query", "intent", "confidence"]
    assert [r[1] for r in rows[1:]] == ["first", "second"]       # oldest first
    assert rows[1][3] == "0.90" and rows[2][3] == ""


def test_voice_export_still_speaks_the_file_name(memory, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    voice = FakeVoice()
    memory.log_history("x", "time")
    path = HistoryFeature(memory, voice).export()
    assert os.path.exists(path)
    assert os.path.basename(path) in voice.said[0]


# ---------------- G: history and todo read-aloud ----------------
def test_history_reads_first_items_and_points_to_the_page(memory, capsys):
    for i in range(5):
        memory.log_history(f"command {i}", "time")
    voice = FakeVoice()
    HistoryFeature(memory, voice).show_recent(limit=5)
    assert voice.said[0] == "Here are your last 5 commands."
    assert voice.said[1:4] == ["command 4.", "command 3.", "command 2."]     # newest first, three only
    assert "History page" in voice.said[-1]
    assert capsys.readouterr().out == ""                                       # no console printing


def test_history_with_few_items_does_not_mention_the_page(memory):
    memory.log_history("only one", "time")
    voice = FakeVoice()
    HistoryFeature(memory, voice).show_recent()
    assert not any("History page" in s for s in voice.said)


def test_todo_show_reads_three_and_points_to_the_page(memory, capsys):
    for t in ("milk", "eggs", "bread", "tea", "rice"):
        memory.add_todo(t)
    voice = FakeVoice()
    TodoFeature(memory, voice, listener=None).show_tasks()
    assert voice.said[0] == "You have 5 pending tasks."
    assert voice.said[1] == "milk; eggs; bread."
    assert "Tasks page" in voice.said[2]
    assert capsys.readouterr().out == ""


def test_todo_show_small_list_is_read_fully_without_page_hint(memory):
    memory.add_todo("milk")
    voice = FakeVoice()
    TodoFeature(memory, voice, listener=None).show_tasks()
    assert voice.said == ["You have 1 pending task.", "milk."]


# ---------------- G: briefing greets by time of day ----------------
@pytest.mark.parametrize("hour,word", [(5, "Good morning"), (11, "Good morning"),
                                       (12, "Good afternoon"), (16, "Good afternoon"),
                                       (17, "Good evening"), (23, "Good evening"),
                                       (2, "Good evening")])
def test_greeting_for_hour(hour, word):
    assert greeting_for(hour) == word


def test_briefing_uses_the_time_of_day_and_the_name(memory):
    voice = FakeVoice()
    now = datetime.datetime(2026, 11, 6, 20, 15)
    BriefingFeature(memory, voice).give_briefing(user_name="Ojas", now=now)
    assert voice.said[0] == "Good evening, Ojas. Today is Friday, 06 November 2026."
    assert not any("Good morning" in s for s in voice.said)


def test_briefing_reminder_lines_have_no_dash(memory):
    memory.add_reminder("call mom", datetime.datetime.now().replace(hour=23, minute=0).isoformat())
    voice = FakeVoice()
    BriefingFeature(memory, voice).give_briefing()
    assert not any(s.startswith("-") for s in voice.said)


# ---------------- G: knowledge ----------------
@pytest.mark.parametrize("query,topic", [
    ("who is albert einstein", "albert einstein"),
    ("who was isaac newton", "isaac newton"),
    ("what is photosynthesis", "photosynthesis"),
    ("what is an algorithm", "an algorithm"),
    ("tell me about the eiffel tower", "the eiffel tower"),
    ("explain black holes", "black holes"),
    ("define gravity", "gravity"),
    ("Who is Narendra Modi?", "Narendra Modi"),
    ("the who is a band", "the who is a band"),        # only the START is cut
    ("who is", ""),
])
def test_extract_topic(query, topic):
    assert extract_topic(query) == topic


def test_answer_looks_up_the_clean_topic(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "FALLBACK_PATH", str(tmp_path / "fb.json"))
    asked = []
    monkeypatch.setattr(knowledge.wikipedia, "summary",
                        lambda topic, sentences=2: asked.append(topic) or "A summary.")
    voice = FakeVoice()
    KnowledgeFeature(voice).answer("explain black holes")
    KnowledgeFeature(voice).answer("what was the cold war")
    assert asked == ["black holes", "the cold war"]


def test_knowledge_json_is_read_and_written_as_utf8(tmp_path, monkeypatch):
    """Windows opens text files as cp1252 by default: every open() must say utf-8."""
    path = str(tmp_path / "fb.json")
    monkeypatch.setattr(knowledge, "FALLBACK_PATH", path)
    seen = []
    real_open = open

    def spy(file, mode="r", *args, **kwargs):
        seen.append((os.path.basename(str(file)), kwargs.get("encoding")))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(knowledge, "open", spy, raising=False)
    voice = FakeVoice()
    feature = KnowledgeFeature(voice)                      # writes the starter file
    with real_open(path, "w", encoding="utf-8") as f:
        f.write('{"caf\\u00e9": "A caf\\u00e9 is a small restaurant."}')
    monkeypatch.setattr(knowledge.wikipedia, "summary",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")))
    feature.answer("what is café")
    assert "small restaurant" in voice.said[-1]
    assert seen and all(enc == "utf-8" for _name, enc in seen)


# ---------------- G: training data and old wording ----------------
def test_training_data_has_no_stop_j():
    import json
    with open(config.TRAINING_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    every = [s for sentences in data.values() for s in sentences]
    assert "stop j" not in every
    assert not any("jarvis" in s for s in every)
    assert "stop raju" in data["exit"]


# ---------------- listener: device list ----------------
def test_list_input_devices_keeps_only_inputs(monkeypatch):
    import listener

    class FakePyAudio:
        def get_device_count(self):
            return 3

        def get_device_info_by_index(self, i):
            return [{"name": "Speakers", "maxInputChannels": 0},
                    {"name": "Microphone (Realtek)", "maxInputChannels": 2},
                    {"name": "USB Headset", "maxInputChannels": 1}][i]

        def terminate(self):
            self.done = True

    class FakeModule:
        PyAudio = FakePyAudio

    monkeypatch.setattr(listener.sr.Microphone, "get_pyaudio", staticmethod(lambda: FakeModule))
    assert listener.list_input_devices() == [(1, "Microphone (Realtek)"), (2, "USB Headset")]


def test_list_input_devices_returns_empty_when_pyaudio_is_missing(monkeypatch):
    import listener

    def boom():
        raise AttributeError("Could not find PyAudio")

    monkeypatch.setattr(listener.sr.Microphone, "get_pyaudio", staticmethod(boom))
    assert listener.list_input_devices() == []
