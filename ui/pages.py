"""
ui/pages.py
The five pages shown to the right of the sidebar: Chat, Tasks, Reminders, History, Settings.

Rules (spec): pages only read and write the database through the assistant's objects and
emit Qt signals. They never call listen(), speak() or execute(). Every page has
refresh() (reload from the database when shown) and set_tokens() (theme colours).
"""

import datetime
import logging
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

import config
from timeutil import format_time
from ui import prefs, theme
from ui.widgets import ChatView, MicButton, StatusPill

log = logging.getLogger(__name__)

MAX_HISTORY_ROWS = 200       # the History page shows the newest 200 (Export CSV has them all)

WELCOME = (f'Hi, I am {config.ASSISTANT_NAME}. Click the mic and say "{config.WAKE_WORD}" '
           f"and then your command, or type a command below.")


class ChatPage(QWidget):
    submitted = Signal(str)      # the user pressed Enter or Send
    mic_clicked = Signal()

    def __init__(self, tokens: theme.Tokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.title = "Chat"

        head = QHBoxLayout()
        heading = QLabel("Chat")
        heading.setObjectName("heading")
        self.pill = StatusPill()
        head.addWidget(heading)
        head.addStretch(1)
        head.addWidget(self.pill)

        self.chat = ChatView()
        self.chat.add_message(WELCOME, "raju")      # empty state: explains the wake word

        self.mic = MicButton(tokens)
        self.mic.clicked.connect(self.mic_clicked)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Type a command or press the mic")
        self.entry.setAccessibleName("Command")
        self.entry.setToolTip("Type a command and press Enter (Ctrl+L)")
        self.entry.returnPressed.connect(self._send)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primary")
        self.send_button.setToolTip("Send the command (Enter)")
        self.send_button.clicked.connect(self._send)

        bottom = QHBoxLayout()
        bottom.addWidget(self.mic)
        bottom.addWidget(self.entry, 1)
        bottom.addWidget(self.send_button)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 12)
        lay.setSpacing(10)
        lay.addLayout(head)
        lay.addWidget(self.chat, 1)
        lay.addLayout(bottom)

    # ---- called by the main window (always on the UI thread) ----
    def _send(self) -> None:
        text = self.entry.text().strip()
        if text:
            self.submitted.emit(text)

    def clear_entry(self) -> None:
        self.entry.clear()

    def add_user(self, text: str) -> None:
        self.chat.add_message(text, "user")

    def add_raju(self, text: str) -> None:
        self.chat.add_message(text, "raju")

    def add_system(self, text: str) -> None:
        self.chat.add_message(text, "system")

    def set_status(self, text: str, state: str) -> None:
        self.pill.set_status(text, state)

    def set_tokens(self, tokens: theme.Tokens) -> None:
        self.mic.set_tokens(tokens)

    def refresh(self) -> None:
        pass   # the chat has nothing to reload

    def focus_entry(self) -> None:
        self.entry.setFocus()


# ---------------------------------------------------------------- helpers
def _heading_row(title: str) -> QHBoxLayout:
    row = QHBoxLayout()
    heading = QLabel(title)
    heading.setObjectName("heading")
    row.addWidget(heading)
    row.addStretch(1)
    return row


def _page_layout(page: QWidget) -> QVBoxLayout:
    lay = QVBoxLayout(page)
    lay.setContentsMargins(20, 16, 20, 12)
    lay.setSpacing(10)
    return lay


def _button(text: str, tooltip: str, name: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setToolTip(tooltip)
    if name:
        btn.setObjectName(name)     # "primary" or "danger" (see theme.py)
    return btn


def format_when(iso_text: str, now: Optional[datetime.datetime] = None) -> str:
    """'3:44 PM' for today, '7 Nov, 3:44 PM' for another day. Bad text is returned as is."""
    try:
        moment = datetime.datetime.fromisoformat(iso_text)
    except (TypeError, ValueError):
        return str(iso_text)
    now = now or datetime.datetime.now()
    if moment.date() == now.date():
        return format_time(moment)
    return f"{moment.day} {moment.strftime('%b')}, {format_time(moment)}"


def _make_table(headers: List[str], name: str) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setAccessibleName(name)
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setShowGrid(False)
    table.setAlternatingRowColors(False)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return table


class _MessageLabel(QLabel):
    """Muted one-line message that takes no space while it is empty."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("", parent)
        self.setObjectName("muted")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setVisible(False)

    def setText(self, text: str) -> None:        # noqa: N802 (Qt naming)
        super().setText(text)
        self.setVisible(bool(text))


# ---------------------------------------------------------------- Tasks
class TasksPage(QWidget):
    """Pending to-dos of the current user, with Done and Delete buttons and an Add field."""

    EMPTY_TEXT = "No tasks yet. Add one here or say 'raju add a task'."

    def __init__(self, assistant, tokens: theme.Tokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.title = "Tasks"
        self.assistant = assistant
        self.tokens = tokens
        self._rows: List[QFrame] = []

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Add a task")
        self.entry.setAccessibleName("New task")
        self.entry.returnPressed.connect(self.add_task)
        self.add_button = _button("Add", "Add the task (Enter)", "primary")
        self.add_button.clicked.connect(self.add_task)
        add_row = QHBoxLayout()
        add_row.addWidget(self.entry, 1)
        add_row.addWidget(self.add_button)

        self.empty_label = QLabel(self.EMPTY_TEXT)
        self.empty_label.setObjectName("muted")
        self.empty_label.setWordWrap(True)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        inner.setLayout(self.list_layout)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(inner)
        self.list_layout.addStretch(1)

        lay = _page_layout(self)
        lay.addLayout(_heading_row("Tasks"))
        lay.addLayout(add_row)
        lay.addWidget(self.empty_label)
        lay.addWidget(self.scroll, 1)

    # ---- actions ----
    def add_task(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        self.assistant.memory.add_todo(text, user_id=self.assistant.current_user_id)
        self.entry.clear()
        self.refresh()

    def _done(self, task_id: int) -> None:
        self.assistant.memory.complete_todo(task_id, user_id=self.assistant.current_user_id)
        self.refresh()

    def _delete(self, task_id: int) -> None:
        self.assistant.memory.delete_todo(task_id, user_id=self.assistant.current_user_id)
        self.refresh()

    # ---- showing ----
    def refresh(self) -> None:
        for row in self._rows:
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        todos = self.assistant.memory.get_todos(user_id=self.assistant.current_user_id)
        self.empty_label.setVisible(not todos)
        for todo in todos:
            row = self._make_row(todo)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self._rows.append(row)

    def _make_row(self, todo: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        label = QLabel(todo["task"])
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        done = _button("Done", f"Mark '{todo['task']}' as done")
        done.setAccessibleName(f"Done: {todo['task']}")
        done.clicked.connect(lambda _c=False, i=todo["id"]: self._done(i))
        delete = _button("Delete", f"Delete '{todo['task']}'", "danger")
        delete.setAccessibleName(f"Delete: {todo['task']}")
        delete.clicked.connect(lambda _c=False, i=todo["id"]: self._delete(i))
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 6, 8, 6)
        lay.addWidget(label, 1)
        lay.addWidget(done)
        lay.addWidget(delete)
        row.label = label
        row.done_button = done
        row.delete_button = delete
        return row

    def task_texts(self) -> List[str]:
        return [row.label.text() for row in self._rows]

    def set_tokens(self, tokens: theme.Tokens) -> None:
        self.tokens = tokens


# ---------------------------------------------------------------- Reminders
class RemindersPage(QWidget):
    """Table of the current user's reminders, an Add form (text + minutes) and Delete."""

    HEADERS = ["Reminder", "Due", "Status"]

    def __init__(self, assistant, tokens: theme.Tokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.title = "Reminders"
        self.assistant = assistant
        self.tokens = tokens

        self.text_entry = QLineEdit()
        self.text_entry.setPlaceholderText("What should I remind you about?")
        self.text_entry.setAccessibleName("Reminder text")
        self.text_entry.returnPressed.connect(self.add_reminder)
        # A number box (not QSpinBox): its tiny arrow buttons are hard to hit and style badly.
        self.minutes = QLineEdit("10")
        self.minutes.setValidator(QIntValidator(1, 24 * 60, self))
        self.minutes.setPlaceholderText("Minutes")
        self.minutes.setAccessibleName("Minutes from now")
        self.minutes.setToolTip("Remind me this many minutes from now (1 to 1440)")
        self.minutes.setFixedWidth(90)
        self.minutes.returnPressed.connect(self.add_reminder)
        self.add_button = _button("Add", "Add the reminder", "primary")
        self.add_button.clicked.connect(self.add_reminder)
        form = QHBoxLayout()
        form.addWidget(self.text_entry, 1)
        form.addWidget(self.minutes)
        form.addWidget(self.add_button)

        self.table = _make_table(self.HEADERS, "Reminders")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_delete_state)

        self.empty_label = QLabel("No reminders yet. Add one here or say 'raju remind me in ten minutes'.")
        self.empty_label.setObjectName("muted")
        self.empty_label.setWordWrap(True)

        self.delete_button = _button("Delete selected", "Delete the selected reminder", "danger")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.delete_button)

        lay = _page_layout(self)
        lay.addLayout(_heading_row("Reminders"))
        lay.addLayout(form)
        lay.addWidget(self.empty_label)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)

    def add_reminder(self, now: Optional[datetime.datetime] = None) -> None:
        text = self.text_entry.text().strip()
        if not text:
            return
        due = (now or datetime.datetime.now()) + datetime.timedelta(minutes=self.minutes_value())
        self.assistant.memory.add_reminder(text, due.isoformat(),
                                           user_id=self.assistant.current_user_id)
        self.text_entry.clear()
        self.refresh()

    def minutes_value(self) -> int:
        """Minutes from the box; a blank or invalid box means 10."""
        try:
            return max(1, min(int(self.minutes.text()), 24 * 60))
        except ValueError:
            return 10

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            return
        self.assistant.memory.delete_reminder(item.data(Qt.ItemDataRole.UserRole),
                                              user_id=self.assistant.current_user_id)
        self.refresh()

    def _update_delete_state(self) -> None:
        self.delete_button.setEnabled(self.table.currentRow() >= 0
                                      and bool(self.table.selectedItems()))

    def refresh(self, now: Optional[datetime.datetime] = None) -> None:
        now = now or datetime.datetime.now()
        reminders = self.assistant.memory.get_reminders(user_id=self.assistant.current_user_id)
        self.empty_label.setVisible(not reminders)
        # Forget the selection: after a delete the next row would otherwise stay selected,
        # and a second click on Delete would remove the wrong reminder.
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.setRowCount(len(reminders))
        grey = QColor(self.tokens.muted)
        for r, rem in enumerate(reminders):
            due = format_when(rem["remind_at"], now)
            try:
                past = datetime.datetime.fromisoformat(rem["remind_at"]) <= now
            except ValueError:
                past = False
            # The status is also written as text, so colour alone never carries the meaning.
            if rem["done"]:
                status = "Done"
            elif past:
                status = "Due now"
            else:
                status = "Pending"
            for c, value in enumerate((rem["task"], due, status)):
                item = QTableWidgetItem(value)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, rem["id"])
                if rem["done"] or past:
                    item.setForeground(grey)        # past-due items are greyed out
                self.table.setItem(r, c, item)
        self._update_delete_state()

    def rows(self) -> List[Tuple[str, str, str]]:
        return [tuple(self.table.item(r, c).text() for c in range(3))
                for r in range(self.table.rowCount())]

    def set_tokens(self, tokens: theme.Tokens) -> None:
        self.tokens = tokens
        self.refresh()


# ---------------------------------------------------------------- History
class HistoryPage(QWidget):
    """Time, command, intent and confidence of the newest commands. Export CSV, Clear history."""

    HEADERS = ["Time", "Command", "Intent", "Confidence"]

    def __init__(self, assistant, tokens: theme.Tokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.title = "History"
        self.assistant = assistant
        self.tokens = tokens

        self.export_button = _button("Export CSV", "Save the full history as a CSV file in the data folder")
        self.export_button.clicked.connect(self.export_csv)
        self.clear_button = _button("Clear history", "Delete all your history", "danger")
        self.clear_button.clicked.connect(self._ask_clear)
        head = _heading_row("History")
        head.addWidget(self.export_button)
        head.addWidget(self.clear_button)

        # Inline confirmation: no pop-up window that could block the app.
        self.confirm_label = QLabel("Delete all history for this user? This cannot be undone.")
        self.confirm_yes = _button("Yes, clear it", "Delete the history now", "danger")
        self.confirm_yes.clicked.connect(self.clear_history)
        self.confirm_no = _button("Cancel", "Keep the history")
        self.confirm_no.clicked.connect(self._cancel_clear)
        self.confirm_row = QFrame()
        self.confirm_row.setObjectName("row")
        confirm_lay = QHBoxLayout(self.confirm_row)
        confirm_lay.setContentsMargins(12, 6, 8, 6)
        confirm_lay.addWidget(self.confirm_label, 1)
        confirm_lay.addWidget(self.confirm_yes)
        confirm_lay.addWidget(self.confirm_no)
        self.confirm_row.setVisible(False)

        self.message = _MessageLabel()

        self.table = _make_table(self.HEADERS, "Command history")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.empty_label = QLabel("No history yet. Every command you give Raju is listed here.")
        self.empty_label.setObjectName("muted")

        lay = _page_layout(self)
        lay.addLayout(head)
        lay.addWidget(self.confirm_row)
        lay.addWidget(self.message)
        lay.addWidget(self.empty_label)
        lay.addWidget(self.table, 1)

    # ---- actions ----
    def export_csv(self) -> Optional[str]:
        path, count = self.assistant.history.write_csv(user_id=self.assistant.current_user_id)
        if path is None:
            self.message.setText("There is no history to export yet.")
            return None
        self.message.setText(f"Saved {count} commands to {path}")
        return path

    def _ask_clear(self) -> None:
        self.confirm_row.setVisible(True)
        self.confirm_no.setFocus()          # the safe choice has the focus

    def _cancel_clear(self) -> None:
        self.confirm_row.setVisible(False)

    def clear_history(self) -> None:
        removed = self.assistant.memory.clear_history(user_id=self.assistant.current_user_id)
        self.confirm_row.setVisible(False)
        self.message.setText(f"Cleared {removed} commands.")
        self.refresh(keep_message=True)

    # ---- showing ----
    def refresh(self, keep_message: bool = False) -> None:
        if not keep_message:
            self.message.setText("")
        self.confirm_row.setVisible(False)
        entries = self.assistant.memory.get_history(user_id=self.assistant.current_user_id,
                                                    limit=MAX_HISTORY_ROWS)
        self.empty_label.setVisible(not entries)
        self.table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            conf = e.get("confidence")
            values = (format_when(e["timestamp"]), e["query"], e["intent"] or "-",
                      "-" if conf is None else f"{round(conf * 100)}%")
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def rows(self) -> List[Tuple[str, str, str, str]]:
        return [tuple(self.table.item(r, c).text() for c in range(4))
                for r in range(self.table.rowCount())]

    def set_tokens(self, tokens: theme.Tokens) -> None:
        self.tokens = tokens


# ---------------------------------------------------------------- Settings
class SettingsPage(QWidget):
    """Theme, speak replies, microphone, continuous default; wake word and user are read-only.
    Each change is saved to the prefs table and announced with a signal; the main window
    applies it."""

    theme_changed = Signal(str)                 # "system" | "light" | "dark"
    speak_changed = Signal(bool)
    mic_changed = Signal(object)                # device index (int) or None for the system default
    continuous_default_changed = Signal(bool)

    DEFAULT_MIC = "default"

    def __init__(self, assistant, tokens: theme.Tokens,
                 device_lister: Optional[Callable[[], List[Tuple[int, str]]]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.title = "Settings"
        self.assistant = assistant
        self.tokens = tokens
        self._device_lister = device_lister
        self._loading = True
        self._devices_loaded = False
        memory = assistant.memory

        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Theme")
        self.theme_combo.setMaximumWidth(260)
        for label, value in (("System", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(prefs.THEMES.index(prefs.get_theme(memory)))
        self.theme_combo.currentIndexChanged.connect(self._on_theme)

        self.speak_check = QCheckBox("Speak replies out loud")
        self.speak_check.setToolTip("Off: replies only appear as text")
        self.speak_check.setChecked(prefs.get_flag(memory, prefs.SPEAK_REPLIES, True))
        self.speak_check.toggled.connect(self._on_speak)

        self.mic_combo = QComboBox()
        self.mic_combo.setAccessibleName("Microphone")
        self.mic_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mic_combo.setMinimumContentsLength(28)
        self.mic_combo.setMaximumWidth(520)
        self.mic_combo.currentIndexChanged.connect(self._on_mic)
        self.refresh_button = _button("Refresh", "Look for microphones again")
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.mic_note = QLabel("")
        self.mic_note.setObjectName("muted")
        self.mic_note.setWordWrap(True)

        self.continuous_check = QCheckBox("Start with continuous listening on")
        self.continuous_check.setToolTip("When Raju starts, keep listening after every command")
        self.continuous_check.setChecked(prefs.get_flag(memory, prefs.CONTINUOUS_DEFAULT, False))
        self.continuous_check.toggled.connect(self._on_continuous)

        self.wake_label = QLabel("")
        self.user_label = QLabel("")
        info = QFrame()
        info.setObjectName("panel")
        info_lay = QVBoxLayout(info)
        info_lay.setContentsMargins(14, 10, 14, 10)
        note = QLabel("Fixed settings")
        note.setObjectName("muted")
        info_lay.addWidget(note)
        info_lay.addWidget(self.wake_label)
        info_lay.addWidget(self.user_label)

        lay = _page_layout(self)
        lay.addLayout(_heading_row("Settings"))
        lay.addWidget(self._caption("Theme"))
        lay.addWidget(self.theme_combo)
        lay.addSpacing(6)
        lay.addWidget(self.speak_check)
        lay.addSpacing(6)
        lay.addWidget(self._caption("Microphone"))
        mic_row = QHBoxLayout()
        mic_row.addWidget(self.mic_combo)
        mic_row.addWidget(self.refresh_button)
        mic_row.addStretch(1)
        lay.addLayout(mic_row)
        lay.addWidget(self.mic_note)
        lay.addSpacing(6)
        lay.addWidget(self.continuous_check)
        lay.addSpacing(10)
        lay.addWidget(info)
        lay.addStretch(1)

        self._loading = False
        self._update_info()

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        return label

    # ---- saving ----
    def _on_theme(self, _index: int) -> None:
        if self._loading:
            return
        mode = self.theme_combo.currentData()
        prefs.set_value(self.assistant.memory, prefs.THEME, mode)
        self.theme_changed.emit(mode)

    def _on_speak(self, on: bool) -> None:
        if self._loading:
            return
        prefs.set_value(self.assistant.memory, prefs.SPEAK_REPLIES, on)
        self.speak_changed.emit(on)

    def _on_continuous(self, on: bool) -> None:
        if self._loading:
            return
        prefs.set_value(self.assistant.memory, prefs.CONTINUOUS_DEFAULT, on)
        self.continuous_default_changed.emit(on)

    def _on_mic(self, _index: int) -> None:
        if self._loading:
            return
        data = self.mic_combo.currentData()
        if data is None:
            return
        prefs.set_value(self.assistant.memory, prefs.MIC_DEVICE, data)
        self.mic_changed.emit(None if data == self.DEFAULT_MIC else int(data))

    # ---- microphones ----
    def _list_devices(self) -> List[Tuple[int, str]]:
        lister = self._device_lister
        if lister is None:
            from listener import list_input_devices   # late import: needs speech_recognition
            lister = list_input_devices
        try:
            return list(lister())
        except Exception:
            log.exception("Listing microphones failed")
            return []

    def _saved_or_current_device(self):
        """What should be selected: the saved choice, else the device Raju really uses."""
        memory = self.assistant.memory
        if prefs.has_mic_choice(memory):
            index = prefs.get_mic_device(memory)
            return self.DEFAULT_MIC if index is None else index
        current = getattr(self.assistant.listener, "device_index", config.MIC_DEVICE_INDEX)
        return self.DEFAULT_MIC if current is None else current

    def refresh_devices(self) -> None:
        """Looks for microphones again (also called the first time the page is shown)."""
        devices = self._list_devices()
        wanted = self._saved_or_current_device()
        self._loading = True            # filling the list must not count as a user choice
        self.mic_combo.clear()
        self.mic_combo.addItem("System default", self.DEFAULT_MIC)
        for index, name in devices:
            self.mic_combo.addItem(f"[{index}] {name}", index)
        position = self.mic_combo.findData(wanted)
        if position < 0 and wanted != self.DEFAULT_MIC:
            self.mic_combo.addItem(f"[{wanted}] (not found)", wanted)   # keeps the saved choice visible
            position = self.mic_combo.count() - 1
        self.mic_combo.setCurrentIndex(max(position, 0))
        self._loading = False
        self._devices_loaded = True
        if not devices:
            self.mic_note.setText("No microphone was found. Plug one in and press Refresh.")
        elif position < 0 or self.mic_combo.currentText().endswith("(not found)"):
            self.mic_note.setText("The saved microphone is not connected. Choose another one.")
        else:
            self.mic_note.setText("")

    # ---- showing ----
    def _update_info(self) -> None:
        user = getattr(self.assistant, "current_user", None)
        self.wake_label.setText(f'Wake word: "{config.WAKE_WORD}"')
        self.user_label.setText(f"Current user: {user['name'] if user else 'Guest'}")

    def refresh(self) -> None:
        self._update_info()
        if not self._devices_loaded:        # listing devices takes a moment: do it once, when first shown
            self.refresh_devices()

    def set_tokens(self, tokens: theme.Tokens) -> None:
        self.tokens = tokens
