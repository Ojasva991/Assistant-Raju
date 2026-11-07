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

SPOKEN_ITEMS = 3   # how many commands "show my history" reads aloud


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
        # Read the first few aloud, newest first; the rest is on the History page.
        for e in entries[:SPOKEN_ITEMS]:
            self.voice.speak(e["query"] + ".")
        if len(entries) > SPOKEN_ITEMS:
            self.voice.speak("The full list is on the History page.")

    def write_csv(self, user_id=0):
        """Writes the full history to a CSV file in the data folder (oldest first).
        Returns (path, number_of_rows), or (None, 0) when there is nothing to write.
        No speech here, so the History page can use it too."""
        entries = self.memory.get_history(user_id=user_id, limit=100000)
        if not entries:
            return None, 0

        filename = f"history_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(config.DATA_DIR, filename)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "query", "intent", "confidence"])
            for e in reversed(entries):  # oldest first in the exported file
                conf = e.get("confidence")
                writer.writerow([e["timestamp"], e["query"], e["intent"],
                                 "" if conf is None else f"{conf:.2f}"])
        return filepath, len(entries)

    def export(self, user_id=0):
        filepath, count = self.write_csv(user_id)
        if filepath is None:
            self.voice.speak("There's no history to export yet.")
            return None
        self.voice.speak(f"Exported {count} commands to {os.path.basename(filepath)} "
                         f"in your data folder.")
        return filepath
