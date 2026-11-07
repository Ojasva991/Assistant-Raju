"""
Day 5 UI tests: Tasks, Reminders, History, Settings pages and the tray.
Qt runs OFFSCREEN; fake voice, fake listener, temporary database.
Run:  python -m pytest tests/test_ui_pages.py -q
"""

import datetime
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

import assistant as assistant_module  # noqa: E402
import config  # noqa: E402
from assistant import Assistant  # noqa: E402
from intent_classifier import IntentClassifier  # noqa: E402
from ui import prefs  # noqa: E402
from ui.bridge import Bridge  # noqa: E402
from ui.main_window import MainWindow, make_tray_pixmap  # noqa: E402


class FakeVoice:
    def __init__(self, on_speak):
        self.on_speak = on_speak
        self.said = []
        self.muted = False
        self.closed = False

    def speak(self, text):
        self.said.append(text)
        self.on_speak(text)

    def close(self):
        self.closed = True


class FakeListener:
    def __init__(self):
        self.answers = []
        self.before_listen = None
        self.on_heard = None
        self.device_index = 1
        self.recalibrated = 0
        self.listen_calls = 0

    def listen(self):
        self.listen_calls += 1
        if self.before_listen:
            self.before_listen()
        return self.answers.pop(0) if self.answers else ""

    def recalibrate(self):
        self.recalibrated += 1


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def classifier():
    return IntentClassifier()


def make_bot(tmp_path, classifier, bridge, name="t"):
    return Assistant(voice=FakeVoice(bridge.spoke.emit), listener=FakeListener(),
                     db_path=str(tmp_path / f"{name}.db"), classifier=classifier,
                     start_reminders=False, log_path=str(tmp_path / f"{name}.log"),
                     on_error=bridge.error.emit)


@pytest.fixture
def win(qapp, classifier, tmp_path):
    bridge = Bridge()
    bot = make_bot(tmp_path, classifier, bridge)
    window = MainWindow(bridge, bot, theme_mode="light", use_tray=False)
    yield window
    window.close()
    assistant_module.close_logging()


@pytest.fixture
def tray_win(qapp, classifier, tmp_path):
    bridge = Bridge()
    bot = make_bot(tmp_path, classifier, bridge, "tray")
    window = MainWindow(bridge, bot, theme_mode="light", use_tray=True)
    yield window
    window.quit_app()
    QApplication.setQuitOnLastWindowClosed(True)     # the tray turns it off; restore for other tests
    assistant_module.close_logging()


def wait_for(condition, timeout=5.0):
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


# ================= Tasks =================
def test_tasks_empty_state_then_add(win):
    page = win.tasks_page
    win._go(1)
    assert page.empty_label.isVisibleTo(page) and "No tasks yet" in page.empty_label.text()
    page.entry.setText("  buy milk  ")
    page.add_button.click()
    assert page.task_texts() == ["buy milk"]
    assert page.entry.text() == ""
    assert not page.empty_label.isVisibleTo(page)
    assert [t["task"] for t in win.assistant.memory.get_todos()] == ["buy milk"]


def test_tasks_blank_text_adds_nothing(win):
    win.tasks_page.entry.setText("   ")
    win.tasks_page.add_button.click()
    assert win.assistant.memory.get_todos() == []


def test_tasks_done_and_delete_buttons(win):
    memory = win.assistant.memory
    for t in ("a", "b", "c"):
        memory.add_todo(t)
    page = win.tasks_page
    page.refresh()
    assert page.task_texts() == ["a", "b", "c"]
    page._rows[0].done_button.click()                 # a: done
    assert page.task_texts() == ["b", "c"]
    assert [t["task"] for t in memory.get_todos(include_done=True) if t["done"]] == ["a"]
    page._rows[0].delete_button.click()               # b: deleted for good
    assert page.task_texts() == ["c"]
    assert sorted(t["task"] for t in memory.get_todos(include_done=True)) == ["a", "c"]


def test_tasks_show_only_the_current_users_tasks(win):
    win.assistant.memory.add_todo("guest task", user_id=0)
    win.assistant.memory.add_todo("ojas task", user_id=7)
    win.tasks_page.refresh()
    assert win.tasks_page.task_texts() == ["guest task"]
    win.assistant.current_user = {"id": 7, "name": "Ojas"}
    win.tasks_page.refresh()
    assert win.tasks_page.task_texts() == ["ojas task"]


def test_tasks_page_reloads_when_shown(win):
    win.assistant.memory.add_todo("added elsewhere")
    win._go(1)
    assert win.tasks_page.task_texts() == ["added elsewhere"]


def test_task_added_by_voice_appears_without_restart(win):
    """Acceptance item: adding a task by voice shows on the Tasks page."""
    win._go(1)
    win.assistant.listener.answers = ["call the bank"]
    win.chat_page.entry.setText("add a task")
    win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: idle(win))
    assert win.tasks_page.task_texts() == ["call the bank"]


# ================= Reminders =================
def test_reminders_add_uses_the_minutes_box(win):
    page = win.reminders_page
    page.text_entry.setText("drink water")
    page.minutes.setText("30")
    now = datetime.datetime(2026, 11, 6, 9, 0)
    page.add_reminder(now=now)
    rows = win.assistant.memory.get_reminders()
    assert rows[0]["task"] == "drink water"
    assert rows[0]["remind_at"] == "2026-11-06T09:30:00"
    assert page.text_entry.text() == ""


def test_reminders_blank_or_bad_minutes_means_ten(win):
    page = win.reminders_page
    for text in ("", "abc"):
        page.minutes.setText(text)
        assert page.minutes_value() == 10
    page.minutes.setText("5000")
    assert page.minutes_value() == 1440
    page.minutes.setText("0")
    assert page.minutes_value() == 1


def test_reminders_table_status_and_greying(win):
    memory = win.assistant.memory
    now = datetime.datetime(2026, 11, 6, 12, 0)
    memory.add_reminder("old and done", "2026-11-06T08:00:00")
    memory.add_reminder("missed", "2026-11-06T11:00:00")
    memory.add_reminder("soon", "2026-11-06T13:15:00")
    memory.add_reminder("tomorrow", "2026-11-07T09:05:00")
    memory.mark_reminder_done(memory.get_reminders()[0]["id"])
    page = win.reminders_page
    page.refresh(now=now)
    assert page.rows() == [("old and done", "8:00 AM", "Done"),
                           ("missed", "11:00 AM", "Due now"),
                           ("soon", "1:15 PM", "Pending"),
                           ("tomorrow", "7 Nov, 9:05 AM", "Pending")]
    grey = QColor(win.tokens.muted)
    colours = [page.table.item(r, 0).foreground().color() for r in range(4)]
    assert colours[0] == grey and colours[1] == grey          # past-due: greyed
    assert colours[2] != grey and colours[3] != grey          # future: normal


def test_reminders_delete_selected(win):
    memory = win.assistant.memory
    memory.add_reminder("one", "2030-01-01T10:00:00")
    memory.add_reminder("two", "2030-01-01T11:00:00")
    page = win.reminders_page
    page.refresh()
    assert not page.delete_button.isEnabled()                 # nothing selected
    page.table.selectRow(0)
    assert page.delete_button.isEnabled()
    page.delete_button.click()
    assert [r["task"] for r in memory.get_reminders()] == ["two"]
    assert page.rows()[0][0] == "two"
    assert not page.delete_button.isEnabled()


def test_reminders_empty_state(win):
    win.reminders_page.refresh()
    assert win.reminders_page.empty_label.isVisibleTo(win.reminders_page)
    win.assistant.memory.add_reminder("x", "2030-01-01T10:00:00")
    win.reminders_page.refresh()
    assert not win.reminders_page.empty_label.isVisibleTo(win.reminders_page)


# ================= History =================
def test_history_rows_newest_first_with_confidence(win):
    memory = win.assistant.memory
    memory.log_history("what time is it", "time", confidence=0.93)
    memory.log_history("exit", "exit", confidence=1.0)
    memory.log_history("blah", None)
    page = win.history_page
    page.refresh()
    rows = page.rows()
    assert [r[1] for r in rows] == ["blah", "exit", "what time is it"]
    assert [r[3] for r in rows] == ["-", "100%", "93%"]
    assert rows[0][2] == "-"
    assert not page.empty_label.isVisibleTo(page)


def test_history_empty_state(win):
    win.history_page.refresh()
    assert win.history_page.empty_label.isVisibleTo(win.history_page)


def test_history_shows_at_most_200_rows(win):
    for i in range(230):
        win.assistant.memory.log_history(f"c{i}", "time")
    win.history_page.refresh()
    assert len(win.history_page.rows()) == 200
    assert win.history_page.rows()[0][1] == "c229"


def test_export_csv_button_writes_a_file_and_shows_where(win, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    page = win.history_page
    page.export_button.click()
    assert "no history" in page.message.text().lower()
    win.assistant.memory.log_history("open notepad", "open_app", confidence=0.9)
    page.export_button.click()
    assert page.message.text().startswith("Saved 1 commands to ")
    files = [f for f in os.listdir(tmp_path) if f.startswith("history_export_")]
    assert len(files) == 1
    assert win.assistant.voice.said == []                      # the button does not speak


def test_clear_history_needs_confirmation(win):
    memory = win.assistant.memory
    memory.log_history("a", "time")
    memory.log_history("other user", "time", user_id=9)
    page = win.history_page
    page.refresh()
    page.clear_button.click()
    assert page.confirm_row.isVisibleTo(page)
    assert len(memory.get_history()) == 1                      # nothing deleted yet
    page.confirm_no.click()
    assert not page.confirm_row.isVisibleTo(page)
    assert len(memory.get_history()) == 1
    page.clear_button.click()
    page.confirm_yes.click()
    assert memory.get_history() == []
    assert page.rows() == [] and page.empty_label.isVisibleTo(page)
    assert page.message.text() == "Cleared 1 commands."
    assert len(memory.get_history(user_id=9)) == 1             # other profiles keep theirs


def test_pending_confirmation_closes_when_page_is_shown_again(win):
    win.history_page.clear_button.click()
    win._go(0)
    win._go(3)
    assert not win.history_page.confirm_row.isVisibleTo(win.history_page)


# ================= Settings =================
def test_settings_defaults_and_read_only_block(win):
    page = win.settings_page
    assert page.theme_combo.currentData() == "light" or page.theme_combo.currentData() == "system"
    assert page.speak_check.isChecked()
    assert not page.continuous_check.isChecked()
    assert config.WAKE_WORD in page.wake_label.text()
    assert page.user_label.text() == "Current user: Guest"
    win.assistant.current_user = {"id": 3, "name": "Ojas"}
    win._go(4)
    assert page.user_label.text() == "Current user: Ojas"


def test_theme_setting_is_saved_and_applied(win):
    page = win.settings_page
    page.theme_combo.setCurrentIndex(page.theme_combo.findData("dark"))
    assert win.tokens.name == "dark"
    assert prefs.get_theme(win.assistant.memory) == "dark"
    assert win.chat_page.mic is not None
    assert win.history_page.tokens.name == "dark"
    assert "#14181C" in QApplication.instance().styleSheet()
    page.theme_combo.setCurrentIndex(page.theme_combo.findData("light"))
    assert win.tokens.name == "light"


def test_speak_replies_off_mutes_the_voice_but_text_still_shows(win):
    win.settings_page.speak_check.setChecked(False)
    assert win.assistant.voice.muted is True
    assert prefs.get_flag(win.assistant.memory, prefs.SPEAK_REPLIES, True) is False
    win.settings_page.speak_check.setChecked(True)
    assert win.assistant.voice.muted is False


def test_microphone_choice_changes_the_device_and_recalibrates(qapp, win):
    page = win.settings_page
    page._device_lister = lambda: [(1, "Microphone (Realtek)"), (4, "USB Headset")]
    page.refresh_devices()
    assert page.mic_combo.currentData() == 1                   # the device Raju uses now
    before = win.assistant.listener.recalibrated
    page.mic_combo.setCurrentIndex(page.mic_combo.findData(4))
    assert win.assistant.listener.device_index == 4
    assert win.assistant.listener.recalibrated == before + 1
    assert prefs.get_mic_device(win.assistant.memory) == 4
    page.mic_combo.setCurrentIndex(page.mic_combo.findData("default"))
    assert win.assistant.listener.device_index is None
    assert prefs.has_mic_choice(win.assistant.memory)


def test_filling_the_device_list_is_not_a_user_choice(win):
    page = win.settings_page
    emitted = []
    page.mic_changed.connect(emitted.append)
    page._device_lister = lambda: [(1, "A"), (2, "B")]
    page.refresh_devices()
    page.refresh_devices()
    assert emitted == []
    assert not prefs.has_mic_choice(win.assistant.memory)


def test_no_microphone_found_says_what_to_do(win):
    page = win.settings_page
    page._device_lister = lambda: []
    page.refresh_devices()
    assert "Plug one in" in page.mic_note.text()


def test_device_lister_crash_does_not_break_the_page(win):
    def boom():
        raise OSError("audio service down")
    win.settings_page._device_lister = boom
    win.settings_page.refresh_devices()                        # must not raise
    assert win.settings_page.mic_combo.count() >= 1


def test_saved_microphone_that_is_unplugged_stays_visible(win):
    prefs.set_value(win.assistant.memory, prefs.MIC_DEVICE, 9)
    page = win.settings_page
    page._device_lister = lambda: [(1, "A")]
    page.refresh_devices()
    assert "(not found)" in page.mic_combo.currentText()
    assert "not connected" in page.mic_note.text()


def test_devices_are_listed_once_when_first_shown(win):
    calls = []
    win.settings_page._device_lister = lambda: calls.append(1) or [(1, "A")]
    win._go(4)
    win._go(0)
    win._go(4)
    assert len(calls) == 1


def test_continuous_default_is_saved(win):
    win.settings_page.continuous_check.setChecked(True)
    assert prefs.get_flag(win.assistant.memory, prefs.CONTINUOUS_DEFAULT, False) is True


def test_saved_settings_are_applied_at_start(qapp, classifier, tmp_path):
    bridge = Bridge()
    bot = make_bot(tmp_path, classifier, bridge, "prefs")
    memory = bot.memory
    prefs.set_value(memory, prefs.THEME, "dark")
    prefs.set_value(memory, prefs.SPEAK_REPLIES, False)
    prefs.set_value(memory, prefs.MIC_DEVICE, 6)
    w = MainWindow(bridge, bot, use_tray=False)               # theme_mode None = use the saved one
    try:
        assert w.tokens.name == "dark"
        assert bot.voice.muted is True
        assert bot.listener.device_index == 6
        assert w.settings_page.theme_combo.currentData() == "dark"
        assert not w.settings_page.speak_check.isChecked()
    finally:
        w.close()
        assistant_module.close_logging()


def test_continuous_default_turns_listening_on_at_start(qapp, classifier, tmp_path):
    bridge = Bridge()
    bot = make_bot(tmp_path, classifier, bridge, "cont")
    prefs.set_value(bot.memory, prefs.CONTINUOUS_DEFAULT, True)
    w = MainWindow(bridge, bot, theme_mode="light", use_tray=False)
    try:
        assert wait_for(lambda: w.continuous.isChecked())
        w.continuous.setChecked(False)
        assert wait_for(lambda: idle(w))
    finally:
        w.close()
        assistant_module.close_logging()


# ================= Tray =================
def test_tray_icon_is_green_and_has_the_three_menu_entries(tray_win):
    pix = make_tray_pixmap()
    assert not pix.isNull()
    centre_edge = QColor(pix.toImage().pixelColor(8, 32))     # inside the circle, outside the letter
    assert centre_edge.green() > centre_edge.red()
    texts = [a.text() for a in tray_win.tray.contextMenu().actions() if not a.isSeparator()]
    assert texts == ["Show Raju", "Listen now", "Quit"]


def test_closing_the_window_hides_it_to_the_tray(tray_win):
    notes = []
    tray_win._tray_notify = lambda title, text: notes.append((title, text))
    stopped = []
    tray_win.assistant.reminders.stop = lambda: stopped.append(True)
    tray_win.show()
    tray_win.close()
    assert not tray_win.isVisible()
    assert not tray_win._closed and stopped == []              # still running
    assert len(notes) == 1 and "tray" in notes[0][1].lower()   # told the user
    tray_win.show_window()
    assert tray_win.isVisible()
    tray_win.close()
    assert len(notes) == 1                                     # the hint is shown only once


def test_tray_hint_is_remembered_between_runs(tray_win):
    tray_win._tray_notify = lambda *a: None
    tray_win.close()
    assert prefs.get_flag(tray_win.assistant.memory, prefs.TRAY_HINT_SHOWN, False)


def test_quit_from_the_tray_stops_everything(tray_win):
    stopped = []
    tray_win.assistant.reminders.stop = lambda: stopped.append(True)
    tray_win.show()
    tray_win.act_quit.trigger()
    assert tray_win._closed and stopped == [True]
    assert tray_win.assistant.voice.closed
    assert not tray_win.isVisible()


def test_listen_now_from_the_tray_starts_a_voice_cycle(tray_win):
    tray_win.act_listen.trigger()
    assert wait_for(lambda: tray_win.assistant.listener.listen_calls >= 1 and idle(tray_win))
    assert tray_win.isVisible()


def test_reminder_that_fires_shows_a_tray_notification(tray_win):
    notes = []
    tray_win._tray_notify = lambda title, text: notes.append((title, text))
    tray_win.bridge.reminder_due.emit("call mom")
    assert wait_for(lambda: notes)
    assert notes[0] == ("Reminder", "call mom")


def test_exit_command_really_quits_even_with_a_tray(tray_win):
    tray_win.show()
    tray_win.chat_page.entry.setText("exit")
    tray_win.chat_page.entry.returnPressed.emit()
    assert wait_for(lambda: tray_win._closed, 5)


def test_without_a_tray_closing_really_closes(win):
    win.close()
    assert win._closed
