"""
tools/ui_screenshot.py
Renders the window OFFSCREEN (no screen needed) and saves PNG files, so the look can be
checked without opening the app. Uses a fake voice, fake listener and a temporary database.

Run:
    python tools/ui_screenshot.py            # light and dark, saved in data/screenshots_ui/
"""

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

import config  # noqa: E402
from assistant import Assistant, close_logging  # noqa: E402
from ui.bridge import Bridge  # noqa: E402
from ui.main_window import PAGE_NAMES, MainWindow  # noqa: E402


class _Voice:
    def __init__(self, on_speak):
        self.on_speak = on_speak

    def speak(self, text):
        self.on_speak(text)

    def close(self):
        pass


class _Listener:
    before_listen = None
    on_heard = None

    def listen(self):
        return ""


def render(mode: str, out_dir: str) -> list:
    app = QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp()
    bridge = Bridge()
    bot = Assistant(voice=_Voice(bridge.spoke.emit), listener=_Listener(),
                    db_path=os.path.join(tmp, "shot.db"), start_reminders=False,
                    log_path=os.path.join(tmp, "shot.log"))
    win = MainWindow(bridge, bot, theme_mode=mode, use_tray=False)
    win.resize(980, 680)
    win.show()
    # Sample data, so the Tasks, Reminders and History pages are not empty in the pictures.
    import datetime
    memory = bot.memory
    for task in ("Buy milk", "Finish the AI report", "Call the bank about the new card"):
        memory.add_todo(task)
    now = datetime.datetime.now()
    memory.add_reminder("Drink water", (now + datetime.timedelta(minutes=25)).isoformat())
    memory.add_reminder("Submit the form", (now + datetime.timedelta(days=1, hours=2)).isoformat())
    memory.add_reminder("Stand up and stretch", (now - datetime.timedelta(minutes=40)).isoformat())
    memory.mark_reminder_done(3)
    for q, intent, conf in (("what time is it", "time", 0.93), ("exit", "exit", 1.0),
                            ("open notepad", "open_app", 0.88), ("add a task", "todo_add", 0.71)):
        memory.log_history(q, intent=intent, confidence=conf)
    chat = win.chat_page
    chat.add_user("what time is it")
    chat.add_raju("The time is 3:44 PM.")
    chat.add_user("what is fifteen plus twenty")
    chat.add_raju("The answer is 35.")
    chat.add_system("Microphone not found. Open Settings and choose another device.")
    chat.add_user("tell me about the eiffel tower and how tall it is, please keep it short")
    chat.add_raju("The Eiffel Tower is a wrought-iron lattice tower in Paris, France. "
                  "It was built in 1889 and is about 330 metres tall.")
    files = []
    win._set_status('Listening for "raju"...')      # mic pulse on
    chat.mic._phase = 0.45                          # freeze the ring in the middle of its pulse
    app.processEvents()
    path = os.path.join(out_dir, f"chat_listening_{mode}.png")
    win.grab().save(path)
    files.append(path)
    win._set_status("Idle")
    for i, name in enumerate(PAGE_NAMES):
        win._go(i)
        app.processEvents()
        path = os.path.join(out_dir, f"page_{i + 1}_{name.lower()}_{mode}.png")
        win.grab().save(path)
        files.append(path)
    win.close()
    close_logging()
    return files


if __name__ == "__main__":
    out = os.path.join(config.DATA_DIR, "screenshots_ui")
    os.makedirs(out, exist_ok=True)
    for m in ("light", "dark"):
        for f in render(m, out):
            print(f)
