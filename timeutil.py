"""
timeutil.py
Tiny time helpers shared by the assistant and the reminders, so both say
the time the same way ("3:44 PM", not "15:44").
"""

import datetime


def format_time(moment: datetime.datetime) -> str:
    """'3:44 PM' instead of '15:44'. Written by hand because strftime's
    no-leading-zero flag (%-I) does not work on Windows."""
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{hour}:{moment.minute:02d} {suffix}"
