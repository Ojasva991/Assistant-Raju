"""
features/reminders.py
Voice reminders. Parses simple relative-time phrases like
"in 10 minutes" or "in 2 hours" and checks for due reminders
in a background thread.
"""

import re
import threading
import time
import datetime


class ReminderFeature:
    def __init__(self, memory, voice, listener, check_interval=15):
        self.memory = memory
        self.voice = voice
        self.listener = listener
        self.check_interval = check_interval
        self._stop = False

    # ---------------- ADDING A REMINDER ----------------
    def add_reminder(self, user_id=0):
        self.voice.speak("What should I remind you about?")
        task = self.listener.listen()
        if not task:
            self.voice.speak("I didn't catch that.")
            return

        self.voice.speak("When should I remind you? For example, in ten minutes.")
        when_text = self.listener.listen()
        remind_at = self._parse_relative_time(when_text)

        if remind_at is None:
            self.voice.speak("I couldn't understand the time, reminder not set.")
            return

        self.memory.add_reminder(task, remind_at.isoformat(), user_id=user_id)
        self.voice.speak(f"Okay, I'll remind you to {task} at {remind_at.strftime('%H:%M')}.")

    def _parse_relative_time(self, text):
        """Parses phrases like 'in 10 minutes' / 'in 2 hours'. Returns a datetime or None."""
        match = re.search(r"(\d+)\s*(second|minute|hour)s?", text)
        if not match:
            return None
        amount, unit = int(match.group(1)), match.group(2)
        delta = {
            "second": datetime.timedelta(seconds=amount),
            "minute": datetime.timedelta(minutes=amount),
            "hour": datetime.timedelta(hours=amount),
        }[unit]
        return datetime.datetime.now() + delta

    # ---------------- BACKGROUND CHECKER ----------------
    def start_background_checker(self):
        """Run in a daemon thread from main.py so reminders fire while J is listening."""
        thread = threading.Thread(target=self._check_loop, daemon=True)
        thread.start()

    def _check_loop(self):
        while not self._stop:
            due = self.memory.get_due_reminders()
            for r in due:
                self.voice.speak(f"Reminder: {r['task']}")
                self.memory.mark_reminder_done(r["id"])
            time.sleep(self.check_interval)

    def stop(self):
        self._stop = True
