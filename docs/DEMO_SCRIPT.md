# Raju demo script (3 minutes)

## Before you start (2 minutes, once)
1. Internet ON (Google speech needs it). Close other apps that use the mic.
2. `python tools\smoke_test.py` -> all PASS.
3. Add 2 tasks by typing first, so the Tasks page is not empty (or do it live in step 3).
4. Speaker volume at about 50%. Mic as close as you can.
5. Start: `python gui.py`. Wait for the window (1-2 seconds).
6. Backup plan: every step below can also be TYPED in the box. If the mic fails, type and keep talking.

## Timeline

| Time | Say or do | What the audience sees | Say to the audience |
|---|---|---|---|
| 0:00 | Open the window | Chat page, green mic, status "Idle" | "Raju is a voice assistant for my PC. It works offline for its core and uses the internet only for speech recognition and Wikipedia." |
| 0:20 | Press the mic, say: **"Raju, what time is it"** | Mic pulses, then user bubble, Raju bubble, voice answers "3:44 PM" | "Wake word first. Then my own ML model finds the intent." |
| 0:45 | Say (no wake word needed, follow-up window 10 s): **"add a task"** then **"buy milk"** | Task answer. Open Tasks page (Ctrl+2): the new task is there | "No restart. The page reads the same database." |
| 1:10 | **"Raju, remind me in one minute"**, then say the reminder text ("drink water") | Raju confirms the time | "I will come back to this in a minute." |
| 1:30 | **"Raju, what is fifteen plus twenty times two"** | Answer 55 | "No eval. A small safe parser with correct precedence." |
| 1:50 | Type: **"open notepad"** | Notepad opens | "Only apps on a safe list can run. Learned commands outside the list are refused." |
| 2:05 | Press Ctrl+4 (History page) | Table: time, command, intent, confidence | "Every command is logged with the intent and the model confidence. I can export CSV." |
| 2:25 | The reminder fires | Raju speaks it + tray message | "Background thread, marks done before speaking." |
| 2:40 | Click X on the window | Window hides, tray icon stays | "Raju keeps running in the tray." Right-click tray -> Quit |
| 2:50 | Closing line | | "Next step: offline speech with Vosk or faster-whisper." |

## If something goes wrong
- Mic hears nothing: say "that is the live risk of Google speech", type the command. Do not retry more than once.
- Wrong intent: say "the model gives confidence below the threshold, so it asks me to rephrase". Show History page.
- Tray icon not visible: Windows hides it in the "^" area. Drag it out once BEFORE the demo.
- Reminder late: it can be up to 5 seconds late (checker interval).

## Things NOT to show
- Profile PIN login (lockout and spoken PIN are slow in a live demo).
- "who is ..." questions if the internet is weak.
- Screenshot/clipboard commands (they show your private screen).
