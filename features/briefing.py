"""
features/briefing.py
"Good morning" -> a spoken summary of the day: date, pending to-dos,
today's reminders, and the most recent note. Pulls together data
that already exists across the other features into one useful readout.
"""

import datetime


class BriefingFeature:
    def __init__(self, memory, voice):
        self.memory = memory
        self.voice = voice

    def give_briefing(self, user_id=0, user_name=None):
        who = f", {user_name}" if user_name else ""
        today_str = datetime.datetime.now().strftime("%A, %d %B %Y")
        self.voice.speak(f"Good morning{who}. Today is {today_str}.")

        self._report_todos(user_id)
        self._report_reminders(user_id)
        self._report_latest_note(user_id)

    def _report_todos(self, user_id):
        todos = self.memory.get_todos(user_id=user_id)
        if not todos:
            self.voice.speak("You have no pending tasks.")
            return

        self.voice.speak(f"You have {len(todos)} pending task"
                          f"{'s' if len(todos) != 1 else ''}.")
        preview = ", ".join(t["task"] for t in todos[:3])
        self.voice.speak(f"Top of the list: {preview}")

    def _report_reminders(self, user_id):
        reminders = self.memory.get_todays_reminders(user_id=user_id)
        if not reminders:
            self.voice.speak("No reminders set for today.")
            return

        self.voice.speak(f"You have {len(reminders)} reminder"
                          f"{'s' if len(reminders) != 1 else ''} today.")
        for r in reminders:
            time_str = r["remind_at"][11:16]  # 'YYYY-MM-DDTHH:MM:SS' -> 'HH:MM'
            status = "already handled" if r["done"] else f"at {time_str}"
            self.voice.speak(f"- {r['task']}, {status}")

    def _report_latest_note(self, user_id):
        note = self.memory.get_latest_note(user_id=user_id)
        if note:
            self.voice.speak(f"Your most recent note: {note}")
