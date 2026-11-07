"""
ui/bridge.py
The ONLY way worker threads talk to the window. A worker thread emits a
signal; Qt queues it and runs the slot on the UI thread, so no widget is ever
touched from another thread.
"""

from PySide6.QtCore import QObject, Signal


class Bridge(QObject):
    spoke = Signal(str)             # Raju said something (also fired when muted)
    status = Signal(str)            # status text: Idle, Listening..., Thinking...
    user_said = Signal(str)         # what the user said or typed
    heard = Signal(str)             # what the microphone understood (PINs come hidden)
    cycle_done = Signal()           # one listen or execute cycle finished
    reminder_due = Signal(str)      # a reminder fired (Day 5: tray message)
    error = Signal(str)             # microphone or speech problem
    failed = Signal(str)            # a command crashed (details are in the log file)
    exit_requested = Signal()       # the user said "exit"
