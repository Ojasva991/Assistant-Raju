"""
ui/main_window.py
The main window: sidebar, pages, status bar, and the worker threads.

Threading rule (spec): the UI thread NEVER calls listen(), speak() or execute().
Each voice or typed command runs in its own Python thread (`_cycle`). That thread
only talks back through the signals in ui/bridge.py. Qt queues those signals and
runs the slots on the UI thread, so widgets are only touched from the UI thread.
"""

import logging
import sys
import threading
from typing import Optional

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QPushButton, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

import config
from ui import prefs, theme
from ui.bridge import Bridge
from ui.pages import ChatPage, HistoryPage, RemindersPage, SettingsPage, TasksPage

log = logging.getLogger(__name__)

PAGE_NAMES = ["Chat", "Tasks", "Reminders", "History", "Settings"]


def build_assistant(bridge: Bridge):
    """Creates the real Assistant wired to the bridge. GUI mode: it never calls input()."""
    from assistant import Assistant   # late import: tests can use the window without it
    assistant = Assistant(
        use_microphone=True,
        on_speak=bridge.spoke.emit,            # every reply also appears as a chat bubble
        allow_text_fallback=False,             # a mic problem becomes a message, never input()
        on_error=bridge.error.emit,
        on_due=bridge.reminder_due.emit,
    )
    assistant.listener.on_heard = bridge.heard.emit   # shows what the mic understood
    return assistant


def make_tray_pixmap(size: int = 64) -> QPixmap:
    """The tray icon is drawn in code (green circle, white initial): no image file needed."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(theme.ACCENT)))
    p.drawEllipse(2, 2, size - 4, size - 4)
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(int(size * 0.55))
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, config.ASSISTANT_NAME[0].upper())
    p.end()
    return pix


class MainWindow(QMainWindow):
    def __init__(self, bridge: Bridge, assistant, theme_mode: Optional[str] = None,
                 use_tray: Optional[bool] = None):
        """theme_mode None = use the saved setting. use_tray None = use the tray when the
        system has one (tests pass True or False)."""
        super().__init__()
        self.bridge = bridge
        self.assistant = assistant
        self.setWindowTitle(f"{config.ASSISTANT_NAME} - Voice Assistant")
        self.resize(980, 680)
        self.setMinimumSize(720, 520)

        self._busy = False             # True while a listen/execute cycle runs
        self._exiting = False
        self._closed = False
        self._quitting = False         # True once the user really wants to leave (not hide to tray)
        self.tray: Optional[QSystemTrayIcon] = None
        self._error_status = ""        # kept on screen after a mic error until the next cycle
        self._cycle_kind = "voice"
        self._listen_calls = 0         # how many times the mic opened in this cycle

        memory = getattr(assistant, "memory", None)
        if theme_mode is None:
            theme_mode = prefs.get_theme(memory) if memory is not None else "system"
        self.tokens = theme.tokens_for(theme_mode, QApplication.instance())
        QApplication.instance().setStyleSheet(theme.stylesheet(self.tokens))

        self._build_layout()
        self._build_status_bar()
        self._build_shortcuts()
        self._connect_bridge()
        self._hook_listener()
        self._build_tray(use_tray)
        self._apply_saved_prefs()
        self._go(0)
        self._update_user_label()

    # ---------------- building the window ----------------
    def _build_layout(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 14, 10, 10)
        side.setSpacing(4)
        brand = QLabel(config.ASSISTANT_NAME)
        brand.setObjectName("brand")
        side.addWidget(brand)

        self.stack = QStackedWidget()
        self.chat_page = ChatPage(self.tokens)
        self.tasks_page = TasksPage(self.assistant, self.tokens)
        self.reminders_page = RemindersPage(self.assistant, self.tokens)
        self.history_page = HistoryPage(self.assistant, self.tokens)
        self.settings_page = SettingsPage(self.assistant, self.tokens)
        self.pages = [self.chat_page, self.tasks_page, self.reminders_page,
                      self.history_page, self.settings_page]
        self.nav_buttons = []
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, (name, page) in enumerate(zip(PAGE_NAMES, self.pages)):
            btn = QPushButton(name)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setToolTip(f"{name} (Ctrl+{i + 1})")
            btn.clicked.connect(lambda _checked=False, idx=i: self._go(idx))
            group.addButton(btn)
            side.addWidget(btn)
            self.nav_buttons.append(btn)
            self.stack.addWidget(page)
        side.addStretch(1)

        outer.addWidget(sidebar)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.chat_page.submitted.connect(self._on_submitted)
        self.chat_page.mic_clicked.connect(self._on_mic_clicked)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self.settings_page.speak_changed.connect(self._apply_speak)
        self.settings_page.mic_changed.connect(self._apply_mic)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setContentsMargins(10, 0, 10, 0)
        self.status_label = QLabel("Idle")
        self.status_label.setAccessibleName("Status text")
        self.heard_label = QLabel("")
        self.heard_label.setObjectName("muted")
        self.continuous = QCheckBox("Continuous listening")
        self.continuous.setToolTip("Keep listening after every command")
        self.continuous.toggled.connect(self._on_continuous_toggled)
        self.user_label = QLabel("User: Guest")
        bar.addWidget(self.status_label)
        bar.addWidget(self.heard_label, 1)
        bar.addPermanentWidget(self.continuous)
        bar.addPermanentWidget(self.user_label)
        self._set_status("Idle")

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._on_mic_clicked)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._focus_entry)
        for i in range(len(PAGE_NAMES)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda idx=i: self._go(idx))

    def _connect_bridge(self) -> None:
        b = self.bridge
        b.spoke.connect(self._on_spoke)
        b.status.connect(self._set_status)
        b.user_said.connect(self.chat_page.add_user)
        b.heard.connect(self._on_heard)
        b.cycle_done.connect(self._on_cycle_done)
        b.reminder_due.connect(self._on_reminder_due)
        b.error.connect(self._on_error)
        b.failed.connect(self.chat_page.add_system)
        b.exit_requested.connect(self._on_exit_requested)

    def _hook_listener(self) -> None:
        """The listener calls before_listen() every time the mic is about to open
        (after Raju stopped talking). We use it to show the right status text,
        for example 'Listening...' when Raju waits for the answer to a question."""
        listener = getattr(self.assistant, "listener", None)
        if listener is None or not hasattr(listener, "before_listen"):
            return
        original = listener.before_listen

        def before_listen():
            if original:
                original()
            self._listen_calls += 1
            self.bridge.status.emit(self._listening_text())
        listener.before_listen = before_listen

    def _listening_text(self) -> str:
        follow_up = getattr(self.assistant, "follow_up_seconds_left", None)
        wake_needed = not (follow_up and follow_up() > 0)
        if self._cycle_kind == "voice" and self._listen_calls == 1 and wake_needed:
            return f'Listening for "{config.WAKE_WORD}"...'
        return "Listening..."

    # ---------------- settings (saved in the prefs table) ----------------
    def _apply_saved_prefs(self) -> None:
        """Applies the saved settings at start. Nothing saved = the defaults of config.py."""
        memory = getattr(self.assistant, "memory", None)
        if memory is None:
            return
        self._apply_speak(prefs.get_flag(memory, prefs.SPEAK_REPLIES, True))
        if prefs.has_mic_choice(memory):
            self._apply_mic(prefs.get_mic_device(memory))
        if prefs.get_flag(memory, prefs.CONTINUOUS_DEFAULT, False):
            # Start after the window is up, so a slow microphone cannot delay the first paint.
            QTimer.singleShot(300, lambda: None if self._closed else self.continuous.setChecked(True))

    def apply_theme(self, mode: str) -> None:
        self.tokens = theme.tokens_for(mode, QApplication.instance())
        QApplication.instance().setStyleSheet(theme.stylesheet(self.tokens))
        for page in self.pages:
            page.set_tokens(self.tokens)

    def _apply_speak(self, on: bool) -> None:
        # muted = text still appears as a chat bubble, but nothing is spoken
        self.assistant.voice.muted = not on

    def _apply_mic(self, device_index) -> None:
        listener = self.assistant.listener
        listener.device_index = device_index
        recalibrate = getattr(listener, "recalibrate", None)
        if recalibrate:
            recalibrate()      # a new device needs a new noise measurement

    # ---------------- system tray ----------------
    def _build_tray(self, use_tray: Optional[bool]) -> None:
        if use_tray is None:
            use_tray = QSystemTrayIcon.isSystemTrayAvailable()
        if not use_tray:
            return
        # With a tray, closing the window only hides it, so the app must not quit by itself.
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.tray = QSystemTrayIcon(QIcon(make_tray_pixmap()), self)
        self.tray.setToolTip(f"{config.ASSISTANT_NAME} Assistant")
        menu = QMenu(self)
        self.act_show = QAction(f"Show {config.ASSISTANT_NAME}", self)
        self.act_show.triggered.connect(self.show_window)
        self.act_listen = QAction("Listen now", self)
        self.act_listen.triggered.connect(self._listen_from_tray)
        self.act_quit = QAction("Quit", self)
        self.act_quit.triggered.connect(self.quit_app)
        menu.addAction(self.act_show)
        menu.addAction(self.act_listen)
        menu.addSeparator()
        menu.addAction(self.act_quit)
        self.tray.setContextMenu(menu)
        self._tray_menu = menu                    # keep a reference, or Qt may delete it
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _listen_from_tray(self) -> None:
        self.show_window()
        self._on_mic_clicked()

    def quit_app(self) -> None:
        """Really leaves (tray menu Quit, or the voice command 'exit')."""
        self._quitting = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _tray_notify(self, title: str, text: str) -> None:
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Information, 6000)

    # ---------------- navigation ----------------
    def _go(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.pages[index].refresh()      # pages reload their data when shown

    def current_page_name(self) -> str:
        return PAGE_NAMES[self.stack.currentIndex()]

    def _focus_entry(self) -> None:
        self._go(0)
        self.chat_page.focus_entry()

    # ---------------- status ----------------
    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        if text.startswith("Listening"):
            state = "listening"
        elif text.startswith("Mic error"):
            state = "error"
        else:
            state = "idle"
        self.chat_page.set_status(text, state)
        self.chat_page.mic.set_listening(state == "listening")

    def _update_user_label(self) -> None:
        user = getattr(self.assistant, "current_user", None)
        name = user["name"] if user else "Guest"
        self.user_label.setText(f"User: {name}")

    def _hint_busy(self) -> None:
        self.statusBar().showMessage("Raju is busy", 2500)    # no dialog, just a hint

    # ---------------- user actions (UI thread) ----------------
    def _on_mic_clicked(self) -> None:
        if self._busy or self._exiting:
            self._hint_busy()
            return
        self._start_cycle("voice")

    def _on_submitted(self, text: str) -> None:
        if self._busy or self._exiting:
            self._hint_busy()          # the typed text stays in the box
            return
        self.chat_page.clear_entry()
        self.chat_page.add_user(text)
        self._start_cycle("typed", text)

    def _on_continuous_toggled(self, on: bool) -> None:
        if on and not self._busy and not self._exiting:
            self._start_cycle("voice")

    def _start_cycle(self, kind: str, text: str = "") -> None:
        self._busy = True
        self._error_status = ""
        self._cycle_kind = kind
        self._listen_calls = 0
        self.chat_page.mic.set_busy(True)
        threading.Thread(target=self._cycle, args=(kind, text), daemon=True).start()

    # ---------------- the worker thread ----------------
    def _cycle(self, kind: str, text: str) -> None:
        """Runs in a worker thread. It must only emit bridge signals, never touch widgets."""
        try:
            if kind == "voice":
                self.bridge.status.emit(f'Listening for "{config.WAKE_WORD}"...')
                query = self.assistant.listen_for_command()
                if query:
                    self.bridge.user_said.emit(query)
                    self.bridge.status.emit("Thinking...")
                    self.assistant.execute(query)
            else:
                self.bridge.status.emit("Thinking...")
                self.assistant.execute(text)
        except SystemExit:
            self.bridge.exit_requested.emit()
        except Exception as exc:
            log.exception("Command failed")
            self.bridge.failed.emit(f"That command failed ({type(exc).__name__}). "
                                    f"Details are in data/assistant.log.")
        finally:
            self.bridge.cycle_done.emit()

    # ---------------- slots (UI thread) ----------------
    def _on_spoke(self, text: str) -> None:
        self.chat_page.add_raju(text)
        if self._busy:    # a reminder spoken while idle must not leave "Speaking..." on screen
            self._set_status("Speaking...")

    def _on_heard(self, text: str) -> None:
        self.heard_label.setText(f"Heard: {text}")

    def _on_error(self, message: str) -> None:
        self.chat_page.add_system(message)
        reason = message.split(". ")[0].rstrip(".")
        self._error_status = f"Mic error: {reason}"
        self._set_status(self._error_status)
        if self.continuous.isChecked():   # a broken mic must not retry in a loop
            self.continuous.setChecked(False)
            self.chat_page.add_system("Continuous listening is off because of this error.")

    def _on_reminder_due(self, text: str) -> None:
        # Raju also speaks it (so a bubble appears). The tray message helps when the window is hidden.
        self.statusBar().showMessage(f"Reminder: {text}", 8000)
        self._tray_notify("Reminder", text)
        self.pages[self.stack.currentIndex()].refresh()   # the Reminders page shows it as done

    def _on_exit_requested(self) -> None:
        self._exiting = True
        self._quitting = True       # the voice command 'exit' really quits, it does not hide to the tray
        self.chat_page.add_system("Session ended. Closing the window.")
        QTimer.singleShot(400, self.quit_app)

    def _on_cycle_done(self) -> None:
        self._busy = False
        self.chat_page.mic.set_busy(False)
        self._set_status(self._error_status or "Idle")
        self.heard_label.setText("")
        self._update_user_label()
        self.pages[self.stack.currentIndex()].refresh()
        if self.continuous.isChecked() and not self._exiting and not self._error_status \
                and not self._closed:
            QTimer.singleShot(0, lambda: None if self._busy else self._start_cycle("voice"))

    # ---------------- closing ----------------
    def closeEvent(self, event) -> None:
        if self.tray is not None and not self._quitting and not self._closed:
            # The X button hides the window to the tray. Raju keeps running (and listening).
            event.ignore()
            self.hide()
            memory = self.assistant.memory
            if not prefs.get_flag(memory, prefs.TRAY_HINT_SHOWN, False):
                prefs.set_value(memory, prefs.TRAY_HINT_SHOWN, True)
                self._tray_notify(f"{config.ASSISTANT_NAME} is still running",
                                  "It moved to the tray. Right-click the tray icon to open or quit.")
            return
        if not self._closed:
            self._closed = True
            if self.tray is not None:
                self.tray.hide()        # otherwise Windows keeps a dead icon until the mouse passes over it
            self.continuous.setChecked(False)
            try:
                self.assistant.reminders.stop()
            except Exception:
                log.exception("Could not stop the reminder thread")
            close_voice = getattr(self.assistant.voice, "close", None)
            if close_voice:
                try:
                    close_voice()
                except Exception:
                    log.exception("Could not stop the speech worker")
        super().closeEvent(event)


def main(argv: Optional[list] = None) -> int:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(config.ASSISTANT_NAME)
    bridge = Bridge()
    assistant = build_assistant(bridge)
    window = MainWindow(bridge, assistant)
    window.show()
    return app.exec()
