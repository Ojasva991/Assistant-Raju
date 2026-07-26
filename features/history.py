"""
features/history.py
Every command you give Raju gets logged (query, detected intent,
timestamp), scoped per user profile. This feature lets you hear a
quick summary out loud, or export the full log to a CSV file you can
open in Excel/Sheets -- handy for a project report or just reviewing
what you've been asking it to do.
"""

import csv
import datetime
import os

import config


class HistoryFeature:
    def __init__(self, memory, voice):
        self.memory = memory
        self.voice = voice

    def show_recent(self, user_id=0, limit=5):
        entries = self.memory.get_history(user_id=user_id, limit=limit)
        if not entries:
            self.voice.speak("You don't have any command history yet.")
            return

        self.voice.speak(f"Here are your last {len(entries)} commands.")
        for e in entries:
            time_str = e["timestamp"][11:16]  # HH:MM
            print(f"  [{time_str}] {e['query']}  (intent: {e['intent']})")
        self.voice.speak("Check the screen for the full list.")

    def export(self, user_id=0):
        entries = self.memory.get_history(user_id=user_id, limit=100000)
        if not entries:
            self.voice.speak("There's no history to export yet.")
            return None

        filename = f"history_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(config.DATA_DIR, filename)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "query", "intent"])
            for e in reversed(entries):  # oldest first in the exported file
                writer.writerow([e["timestamp"], e["query"], e["intent"]])

        self.voice.speak(f"Exported {len(entries)} commands to {filename} "
                          f"in your data folder.")
        return filepath
