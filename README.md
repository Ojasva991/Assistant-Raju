# Raju: voice assistant for Windows

A personal AI/ML project. Raju is a system-specific assistant for one Windows PC, in the style of
the movie assistants: you say the wake word ("raju"), then a command. He works out what you mean,
does it, and answers by voice and on screen. Typing a command works too.

**Raju is a hybrid assistant, not an offline-only one.** The core (intent model, memory, to-do,
reminders, calculator, app control) runs on your PC without internet. Speech recognition currently
uses Google's web service, so speaking commands needs internet. Offline speech and Hindi + English
support are planned, see `docs/ROADMAP.md`.

## What works offline and what needs internet

| Works without internet | Needs internet |
|---|---|
| Intent model (scikit-learn, trained on your PC at start) | Speech recognition (Google's free web API) |
| Memory: notes, to-do list, reminders, history (SQLite) | Wikipedia answers ("who is ...") |
| Calculator, time, date, daily briefing | Opening websites (the browser needs it) |
| Opening apps, screenshots, clipboard, battery/CPU/RAM | |
| Text to speech (Windows voices, via pyttsx3) | |
| Fuzzy matching, sentiment (VADER), profiles and PINs | |

Without internet, speaking commands does not work, but typing them in the window does, and
every offline feature keeps working. Online features say so politely when they fail.
Offline speech recognition (Vosk or faster-whisper) is a planned upgrade; the engine name is
kept in `config.STT_ENGINE`.

## Features

- Wake word "raju" (also "raj"), then a short window where no wake word is needed
- Open apps and websites, with fuzzy matching for mishearings ("opne notepad")
- To-do list and reminders ("remind me in ten minutes"), shown on their own pages
- Calculator ("what is fifteen plus twenty", "two plus three times four")
- Notes with topic recall ("what did I say about my exam")
- Profiles with a spoken PIN (separate notes, tasks, reminders, history)
- Daily briefing, command history with CSV export
- Battery, CPU and RAM, screenshots, clipboard
- Wikipedia lookups with a small offline fallback
- A PySide6 window: chat, Tasks, Reminders, History, Settings, light and dark theme, tray icon

## Setup (Windows, Python 3.10+)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If `pip install pyaudio` fails, install a PyAudio wheel for your Python version first.

## Run

```
python gui.py            the window (main way to use Raju)
python main.py           console mode (voice)
python main.py --text    console mode, typed commands
```

Keyboard in the window: Ctrl+M listen, Ctrl+L text box, Ctrl+1 to Ctrl+5 switch pages.
Closing the window hides Raju to the tray. Use Quit in the tray menu (or say "exit") to stop.

## Check that it works

```
python -m pytest tests -q                 automatic tests (no microphone needed)
python tools\smoke_test.py                quick health check, about 5 seconds
python tools\smoke_test.py --all          also speakers, microphone, real apps, internet
python tools\mic_test.py --all            test every microphone and name the right index
```

Install the test tool first: `pip install -r requirements-dev.txt`.
If the wrong microphone is used, set `MIC_DEVICE_INDEX` in `config.py`, or choose the device on
the Settings page.

## Example commands

```
raju open notepad              raju what time is it
raju go to youtube             raju what is the date
raju add a task                raju show my tasks
raju remind me in ten minutes  raju what is twelve plus seven
raju remember this             raju what did I say about my exam
raju take a screenshot         raju how much battery do I have
raju who is albert einstein    raju good morning
raju create a profile          raju log in / log out / who am I
raju show my history           raju export my history
```

## Folder map

```
gui.py                 launcher for the window
main.py                console mode
assistant.py           the brain: Assistant.execute(query)
config.py              apps, websites, wake word, thresholds, paths
intent_classifier.py   rules + ML model; run it to see the accuracy table
training_data.json     446 example sentences, 27 intents
database.py            SQLite layer (data/memory.db)
fuzzy_match.py         difflib helpers
speech_engine.py       text to speech (worker thread + queue)
listener.py            speech to text
timeutil.py            time formatting
features/              one small module per feature (todo, reminders, calculator, ...)
ui/                    PySide6 window: theme, bridge, widgets, pages, main_window, prefs
tools/                 mic_test.py, smoke_test.py, ui_screenshot.py
docs/                  ROADMAP.md, demo script, report and slides outlines
tests/                 pytest tests
data/                  runtime data (database, log, music, screenshots)
```

## Accuracy of the intent model

Measured with 5-fold cross-validation repeated 5 times on `training_data.json`:
Naive Bayes 73.6%, Logistic Regression 82.6% (chosen), LinearSVC 82.3%.
With the rule table and the confidence threshold: 83.6%. The old version scored about 61%
on its own, smaller data. See `CHANGELOG.md` for the details and the limits of this comparison.

## Safety and privacy notes

- Apps start with `subprocess.Popen` without a shell, and only commands listed in `config.APPS`
  can run. This includes commands you teach Raju.
- PINs are stored as salted PBKDF2 hashes and compared exactly. Three wrong tries lock login for
  60 seconds (until Raju restarts). This separates profiles on a shared PC; it is not protection
  for sensitive data.
- Speech audio is sent to Google for recognition. Wikipedia lookups send your question to Wikipedia.
- `data/assistant.log` keeps the commands you gave, in plain text. It is excluded from git; keep it private.

## Known limits

- English only for now. Hindi + English (Hinglish) is the next big step, see `docs/ROADMAP.md`.
- Wake word is matched in the text that Google returns, so it is not an acoustic wake-word
  detector and it needs internet.
- Tested by the owner on one Windows 11 laptop (Intel i3, 8 GB RAM) with one microphone.
  No tests with other speakers, accents or noisy rooms yet.
- About 37% of unusual, unrelated sentences are still mapped to some action instead of "unknown".
- App commands in `config.APPS` and the music helper are Windows-oriented.

## Roadmap

The plan for the next phases (English polish, Hindi + English, offline speech, optional local LLM,
measurements for a paper) is in `docs/ROADMAP.md`. Demo and report material is in `docs/`.

`sentence-transformers` is optional (commented out in `requirements.txt`) and upgrades note
recall from keyword search to meaning-based search.
