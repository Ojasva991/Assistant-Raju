# Raju — Offline Voice Assistant

A voice assistant built as a school project (AI & ML, B.Tech), evolved
from a single-file script into a modular Python application with a
local SQLite database, a scikit-learn intent classifier, and a
Tkinter GUI. **No external AI API is used anywhere** — the "AI" is a
Naive Bayes intent classifier trained on-device from a small labeled
dataset (see `intent_classifier.py`), and every feature (memory,
sentiment, fuzzy matching, semantic search) runs locally.

## Features

- **Wake word activation** — ignores speech until it hears "raju" or
  "raj", so the mic can stay on without reacting to background noise
- **Fuzzy mishearing recovery** — corrects mic mistranscriptions
  (e.g. "opne notepad") using `difflib`, no ML needed
- **App & website launcher** — "open notepad", "open youtube", etc.
- **To-do list & reminders** — voice-driven, with a background thread
  that speaks reminders when they're due
- **Voice calculator** — "what is fifteen plus twenty"
- **System stats, screenshots, clipboard reading**
- **Wikipedia lookups** with an offline fallback knowledge base
- **Memory** — SQLite-backed notes, with topic-relevant recall
  ("what did I say about my exam") via TF-IDF or, optionally, offline
  sentence embeddings
- **User profiles** — multiple people can share one installation with
  separate memory, switched via a spoken PIN
- **Daily briefing** — "good morning" reads back today's date, tasks,
  reminders, and latest note
- **Sentiment-aware responses** — recognizes frustrated phrasing
  (via VADER, a lexicon-based scorer) and responds more gently
- **Safety** — learned voice commands can only resolve to a
  pre-approved app whitelist, with a spoken yes/no confirmation
  before running anything
- **GUI mode** — a Tkinter window with a mic button, text input,
  live transcript, and continuous-listening mode, for demos

See `CHANGELOG.md` for the full build history and design decisions
behind each feature (useful if you're writing this up for a report).

## Project structure

```
J_assistant/
├── main.py                    # entry point (console mode)
├── gui.py                     # entry point (GUI mode)
├── assistant.py                # Raju's main class, wires everything together
├── config.py                    # apps, wake word, thresholds, paths — edit here first
├── database.py                   # SQLite memory layer (notes, todos, reminders, users, prefs)
├── intent_classifier.py           # Naive Bayes intent classifier + training data
├── fuzzy_match.py                  # mishearing recovery (stdlib difflib, no dependency)
├── speech_engine.py                 # text-to-speech (pyttsx3)
├── listener.py                       # speech-to-text + typed-input fallback
├── mic_test.py                        # diagnostic: lists mics, tests the default device
├── mic_device_test.py                  # diagnostic: tests specific mic device indices
├── requirements.txt
├── features/
│   ├── todo.py                    # to-do list
│   ├── reminders.py                # reminders + background checker thread
│   ├── calculator.py                # spoken math
│   ├── system_utils.py               # battery/RAM/CPU stats, screenshot, clipboard
│   ├── knowledge.py                   # Wikipedia + offline fallback
│   ├── user_profile.py                 # profile registration + fuzzy PIN login
│   ├── semantic_memory.py               # topic-relevant note search
│   ├── briefing.py                       # daily briefing summary
│   └── sentiment.py                       # VADER-based sentiment detection
└── data/                       # created automatically at runtime
    ├── memory.db                # SQLite database
    ├── music/                    # drop mp3/wav files here for "play music"
    └── screenshots/
```

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` on Mac/Linux
pip install -r requirements.txt
```

Run it:
```
python main.py          # console mode
python main.py --text   # console mode, typed input instead of mic
python gui.py           # GUI mode
```

If audio stops working correctly (e.g. after plugging in a headset),
run `python mic_test.py` to find the right microphone device index
and update `MIC_DEVICE_INDEX` in `config.py`.

## Example commands

Say the wake word first, e.g. "raju, open notepad":

```
raju open notepad / open youtube
raju what is the time / what is the date
raju add a task            → then say the task
raju show my tasks
raju remind me in ten minutes   → then say what, then when
raju remember this          → then say what to remember
raju what did I say about my exam    → topic-relevant recall
raju what is fifteen plus twenty
raju how much battery do I have
raju take a screenshot
raju who is albert einstein
raju create a profile / log in / who am i / log out
raju good morning              → daily briefing
```

## Notes for your machine

- `config.APPS` and the music-playback code (`os.startfile`) are
  Windows-specific — update `config.py` if you move to Mac/Linux.
- `sentence-transformers` is optional (commented out in
  `requirements.txt`) — upgrades memory recall from keyword-based to
  true meaning-based search. Everything works without it.

## Disclaimer

The user-profile PIN system is a convenience feature for separating
memory between people sharing one installation, **not real security**
— PINs are stored as plain text.
