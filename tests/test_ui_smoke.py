"""
UI smoke tests (Day 4). They run Qt OFFSCREEN: no window is shown, and there is
no microphone and no speaker (fake voice, fake listener, temporary database).
Run:  python -m pytest tests/test_ui_smoke.py -q
"""

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import assistant as assistant_module  # noqa: E402
from assistant import Assistant  # noqa: E402
from intent_classifier import IntentClassifier  # noqa: E402
from ui.bridge import Bridge  # noqa: E402
from ui.main_window import PAGE_NAMES, MainWindow  # noqa: E402
from ui.widgets import MAX_BUBBLES  # noqa: E402


class FakeVoice:
    """Records speech and, like the real engine, calls on_speak before 'speaking'."""

    def __init__(self, on_speak):
        self.on_speak = on_speak
        self.said = []

    def speak(self, text):
        self.said.append(text)
        self.on_speak(text)

    def close(self):
        pass


class FakeListener:
    def __init__(self):
        self.answers = []
        self.before_listen = None
        self.on_heard = None
        self.error_to_raise = None

    def listen(self):
        if self.before_listen:
            self.before_listen()
        if self.error_to_raise:
            self.error_to_raise()
            return ""
        return self.answers.pop(0) if self.answers else ""


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def classifier():
    return IntentClassifier()


@pytest.fixture
def win(qapp, classifier, tmp_path):
    bridge = Bridge()
    listener = FakeListener()
    voice = FakeVoice(bridge.spoke.emit)
    bot = Assistant(voice=voice, listener=listener, db_path=str(tmp_path / "t.db"),
                    classifier=classifier, start_reminders=False,
                    log_path=str(tmp_path / "t.log"), on_error=bridge.error.emit)
    window = MainWindow(bridge, bot, theme_mode="light")
    window.listener = listener
    yield window
    window.close()
    assistant_module.close_logging()


def wait_for(condition, timeout=5.0):
    """Lets Qt deliver queued signals until condition() is true."""
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return condition()


def idle(window):
    return not window._busy


# ---------------- window and pages ----------------
def test_window_has_five_pages_and_switches_through_all(win):
    assert PAGE_NAMES == ["Chat", "Tasks", "Reminders", "History", "Settings"]
    for i, name in enumerate(PAGE_NAMES):
        win._go(i)
        assert win.current_page_name() == name
        assert win.nav_buttons[i].isChecked()


def test_chat_page_starts_with_a_welcome_bubble_from_raju(win):
    role, text = win.chat_page.chat.messages()[0]
    assert role == "raju"
    assert "raju" in text.lower()
    assert win.status_label.text() == "Idle"
    assert win.user_label.text() == "User: Guest"


def test_both_themes_build(qapp, classifier, tmp_path):
    for mode in ("dark", "light", "system"):
        bridge = Bridge()
        bot = Assistant(voice=FakeVoice(bridge.spoke.emit), listener=FakeListener(),
                        db_path=str(tmp_path / f"{mode}.db"), classifier=classifier,
                        start_reminders=False, log_path=str(tmp_path / f"{mode}.log"))
        w = MainWindow(bridge, bot, theme_mode=mode)
        w.grab()   # renders the window offscreen without errors
        w.close()
    assistant_module.close_logging()


# ---------------- typed commands ----------------
def test_typed_command_shows_user_bubble_then_raju_bubble(win):
    win.chat_page.entry.setText("what time is it")
    win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: idle(win) and win.chat_page.chat.count() >= 3)
    roles = [r for r, _ in win.chat_page.chat.messages()]
    assert roles[-2:] == ["user", "raju"]
    assert "what time is it" in win.chat_page.chat.messages()[-2][1]
    assert "The time is" in win.chat_page.chat.messages()[-1][1]
    assert win.chat_page.entry.text() == ""
    assert win.status_label.text() == "Idle"


def test_typing_while_busy_is_ignored_and_text_stays(win):
    win._busy = True
    win.chat_page.entry.setText("what time is it")
    before = win.chat_page.chat.count()
    win.chat_page.entry.returnPressed.emit()
    assert win.chat_page.chat.count() == before
    assert win.chat_page.entry.text() == "what time is it"
    assert win.statusBar().currentMessage() == "Raju is busy"


def test_mic_click_while_busy_only_shows_a_hint(win):
    win._busy = True
    win.chat_page.mic.click()
    assert win.statusBar().currentMessage() == "Raju is busy"
    assert not win.chat_page.mic.is_listening()


# ---------------- the worker thread rule ----------------
def test_widgets_are_only_touched_on_the_ui_thread(win):
    seen = []
    original = win.chat_page.add_raju

    def spy(text):
        seen.append(threading.current_thread() is threading.main_thread())
        original(text)
    win.chat_page.add_raju = spy
    # connect() stored the old bound method for _on_spoke only; it calls add_raju by name, so the spy is used
    win.chat_page.entry.setText("what is the date")
    win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: idle(win) and seen)
    assert all(seen)


def test_execute_runs_in_a_worker_thread_not_the_ui_thread(win):
    where = []
    original = win.assistant.execute

    def spy(q):
        where.append(threading.current_thread() is threading.main_thread())
        return original(q)
    win.assistant.execute = spy
    win.chat_page.entry.setText("hello")
    win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: idle(win) and where)
    assert where == [False]


# ---------------- voice ----------------
def test_voice_cycle_with_wake_word(win):
    win.listener.answers = ["raju what is the date"]
    win.chat_page.mic.click()
    assert wait_for(lambda: idle(win) and win.chat_page.chat.count() >= 3)
    msgs = win.chat_page.chat.messages()
    assert msgs[-2] == ("user", "what is the date")
    assert "date" in msgs[-1][1].lower()


def test_voice_cycle_without_wake_word_is_ignored(win):
    win.listener.answers = ["what is the date"]
    before = win.chat_page.chat.count()
    win.chat_page.mic.click()
    assert wait_for(lambda: idle(win))
    assert win.chat_page.chat.count() == before
    assert win.status_label.text() == "Idle"


def test_status_says_listening_for_raju_and_mic_pulses(win):
    states = []
    original = win._set_status

    def spy(text):
        states.append((text, win.chat_page.mic.is_listening()))
        original(text)
    win._set_status = spy
    win.bridge.status.disconnect()
    win.bridge.status.connect(win._set_status)
    win.listener.answers = [""]
    win.chat_page.mic.click()
    assert wait_for(lambda: idle(win))
    assert any(t == 'Listening for "raju"...' for t, _ in states)
    assert win.chat_page.mic.is_listening() is False        # back to idle afterwards


def test_mic_pulse_follows_the_status_text(win):
    win._set_status('Listening for "raju"...')
    assert win.chat_page.mic.is_listening()
    assert win.chat_page.pill.text() == 'Listening for "raju"...'
    win._set_status("Thinking...")
    assert not win.chat_page.mic.is_listening()


def test_question_from_raju_shows_listening_for_the_answer(win):
    # "add a task" makes Raju ask a question and wait for the answer
    seen = []
    win.bridge.status.connect(seen.append)
    win.listener.answers = ["raju add a task", "buy milk"]
    win.chat_page.mic.click()
    assert wait_for(lambda: idle(win) and any("buy milk" in t for _, t in win.chat_page.chat.messages()))
    assert "Listening..." in seen


# ---------------- errors ----------------
def test_mic_error_shows_a_message_and_a_status_and_does_not_freeze(win):
    msg = "Microphone not found or blocked. Open Settings and choose another device."
    win.listener.error_to_raise = lambda: win.bridge.error.emit(msg)
    win.chat_page.mic.click()
    assert wait_for(lambda: idle(win) and win.status_label.text().startswith("Mic error"))
    assert win.status_label.text() == "Mic error: Microphone not found or blocked"
    assert ("system", msg) in win.chat_page.chat.messages()
    assert win.chat_page.pill.property("state") == "error"


def test_mic_error_turns_continuous_listening_off(win):
    win.continuous.setChecked(True)     # starts a voice cycle at once
    win.listener.error_to_raise = lambda: win.bridge.error.emit("Microphone not found.")
    assert wait_for(lambda: not win.continuous.isChecked(), 5)
    assert wait_for(lambda: idle(win))
    assert any("Continuous listening is off" in t for _, t in win.chat_page.chat.messages())


def test_a_crashing_command_is_reported_and_the_window_stays_usable(win):
    def boom(q):
        raise RuntimeError("secret detail")
    win.assistant.execute = boom
    win.chat_page.entry.setText("hello")
    win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: idle(win))
    last_role, last_text = win.chat_page.chat.messages()[-1]
    assert last_role == "system" and "RuntimeError" in last_text
    assert "secret detail" not in last_text     # details go to the log, not the screen
    assert win.status_label.text() == "Idle"


# ---------------- continuous listening and exit ----------------
def test_continuous_listening_starts_the_next_cycle_after_cycle_done(win):
    calls = []
    original = win.listener.listen

    def counting():
        calls.append(1)
        return original()
    win.listener.listen = counting
    win.continuous.setChecked(True)
    assert wait_for(lambda: len(calls) >= 3, 5)
    win.continuous.setChecked(False)
    assert wait_for(lambda: idle(win))


def test_exit_command_closes_the_window(win):
    win.show()
    win.chat_page.entry.setText("exit")
    win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: not win.isVisible(), 5)
    assert win._exiting


def test_closing_stops_the_reminder_thread(win):
    stopped = []
    win.assistant.reminders.stop = lambda: stopped.append(True)
    win.close()
    assert stopped == [True]


# ---------------- chat view ----------------
def test_chat_keeps_only_the_last_200_messages(win):
    for i in range(MAX_BUBBLES + 25):
        win.chat_page.add_raju(f"line {i}")
    assert win.chat_page.chat.count() == MAX_BUBBLES
    assert win.chat_page.chat.messages()[-1][1] == f"line {MAX_BUBBLES + 24}"
    assert win.chat_page.chat.messages()[0][1] == "line 25"


def test_user_label_shows_the_logged_in_name(win):
    win.assistant.current_user = {"id": 7, "name": "Ojas"}
    win._update_user_label()
    assert win.user_label.text() == "User: Ojas"


def test_reminder_due_shows_a_status_bar_message(win):
    win.bridge.reminder_due.emit("call mom")
    assert wait_for(lambda: "call mom" in win.statusBar().currentMessage())


def test_heard_text_is_shown_then_cleared(win):
    win.bridge.heard.emit("open notepad")
    assert wait_for(lambda: win.heard_label.text() == "Heard: open notepad")
    win._on_cycle_done()
    assert win.heard_label.text() == ""


def test_reply_spoken_while_idle_does_not_leave_speaking_on_screen(win):
    # a reminder is spoken by the reminder thread, outside any command cycle
    win.bridge.spoke.emit("Reminder: call mom")
    assert wait_for(lambda: win.chat_page.chat.messages()[-1] == ("raju", "Reminder: call mom"))
    assert win.status_label.text() == "Idle"


def test_bubble_is_tall_enough_for_long_text(win):
    # regression: a word-wrapped label used to be too short and clipped the last lines
    long_text = "word " * 120
    win.chat_page.add_raju(long_text)
    _, bubble = win.chat_page.chat._rows[-1]
    label = bubble.label
    assert label.width() <= int(win.chat_page.chat.viewport().width() * 0.72)
    assert label.height() >= label.heightForWidth(label.width()) - 4
    assert label.height() > 60       # several lines, not one
