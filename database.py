"""
database.py
Local SQLite database — no external server, no API. Single file
(data/memory.db) that Python's built-in sqlite3 module reads/writes.

Tables:
    users      -> profiles: name + spoken PIN, so multiple people can
                  use the same J installation with separate memory
    notes      -> free-form things the user asked J to remember
    commands   -> learned voice-command -> shell-command mappings (shared)
    todos      -> to-do list items (per user)
    reminders  -> time-based reminders (shared checker, tagged by user)
    prefs      -> simple key/value preferences (per user)

user_id = 0 means "guest" / no profile logged in — this keeps things
working exactly as before for anyone who doesn't care about profiles.
"""

import sqlite3
import datetime
from contextlib import contextmanager

import config

GUEST_ID = 0


class MemoryManager:
    def __init__(self, db_path=config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    pin TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                    trigger TEXT PRIMARY KEY,
                    action TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    task TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    task TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS prefs (
                    user_id INTEGER NOT NULL DEFAULT 0,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (user_id, key)
                )
            """)

    # ---------------- USERS / PROFILES ----------------
    def add_user(self, name, pin):
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, pin, created_at) VALUES (?, ?, ?)",
                (name, pin, datetime.datetime.now().isoformat()),
            )
            return cur.lastrowid

    def get_all_users(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
            return [dict(r) for r in rows]

    def get_user_by_id(self, user_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    # ---------------- NOTES ----------------
    def add_note(self, content, user_id=GUEST_ID):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)",
                (user_id, content, datetime.datetime.now().isoformat()),
            )

    def get_notes(self, limit=10, user_id=GUEST_ID):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT content, created_at FROM notes "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_note(self, user_id=GUEST_ID):
        notes = self.get_notes(limit=1, user_id=user_id)
        return notes[0]["content"] if notes else None

    # ---------------- LEARNED COMMANDS (shared across users) ----------------
    def teach_command(self, trigger, action):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO commands (trigger, action) VALUES (?, ?)",
                (trigger, action),
            )

    def get_command(self, trigger):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT action FROM commands WHERE trigger = ?", (trigger,)
            ).fetchone()
            return row["action"] if row else None

    def get_all_triggers(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT trigger FROM commands").fetchall()
            return [r["trigger"] for r in rows]

    # ---------------- TODOS ----------------
    def add_todo(self, task, user_id=GUEST_ID):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO todos (user_id, task, done, created_at) VALUES (?, ?, 0, ?)",
                (user_id, task, datetime.datetime.now().isoformat()),
            )

    def get_todos(self, include_done=False, user_id=GUEST_ID):
        with self._connect() as conn:
            if include_done:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE user_id = ? ORDER BY id", (user_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM todos WHERE user_id = ? AND done = 0 ORDER BY id",
                    (user_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def complete_todo(self, task_id):
        with self._connect() as conn:
            conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (task_id,))

    # ---------------- REMINDERS ----------------
    def add_reminder(self, task, remind_at_iso, user_id=GUEST_ID):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reminders (user_id, task, remind_at, done) VALUES (?, ?, ?, 0)",
                (user_id, task, remind_at_iso),
            )

    def get_due_reminders(self):
        """Checks across ALL users — the background checker runs once for
        the whole app, regardless of who's currently logged in."""
        now = datetime.datetime.now().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE remind_at <= ? AND done = 0", (now,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_todays_reminders(self, user_id=GUEST_ID):
        """All reminders scheduled for today for this user, done or not --
        used for the daily briefing, not the live due-reminder checker."""
        today_prefix = datetime.date.today().isoformat()  # 'YYYY-MM-DD'
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE user_id = ? AND remind_at LIKE ? "
                "ORDER BY remind_at",
                (user_id, f"{today_prefix}%"),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_reminder_done(self, reminder_id):
        with self._connect() as conn:
            conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,))

    # ---------------- PREFERENCES ----------------
    def set_pref(self, key, value, user_id=GUEST_ID):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO prefs (user_id, key, value) VALUES (?, ?, ?)",
                (user_id, key, value),
            )

    def get_pref(self, key, user_id=GUEST_ID):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM prefs WHERE user_id = ? AND key = ?", (user_id, key)
            ).fetchone()
            return row["value"] if row else None
