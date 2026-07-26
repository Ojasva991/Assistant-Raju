# Changelog

All notable changes to this project, in the order they were made.
Version numbers are informal (this was a school project built
iteratively, not a versioned release).

## What changed from v2 → v2.1

- Fixed a `pyttsx3` bug where J would speak once, then go silent —
  it now creates a fresh TTS engine per sentence instead of reusing one.
- Added `gui.py`: a Tkinter window (mic button, text input, live
  transcript log, status indicator, continuous-listening mode).

## What changed from v1

- **Memory**: `memory.json` → SQLite (`data/memory.db`) with separate
  tables for notes, learned commands, todos, reminders, and preferences.
- **TTS**: `win32com`/SAPI → `pyttsx3`, so it's no longer Windows-only.
- **Intent classifier**: 5 intents / ~13 examples → 18 intents / ~150+
  examples, plus a confidence threshold so it says "I'm not sure"
  instead of guessing when it's unsure. Run `python intent_classifier.py`
  directly to see a held-out accuracy report for your project write-up.
- **Safety**: learned voice commands can now only resolve to apps
  already in the `config.APPS` whitelist — no more running arbitrary
  shell text from voice input. Learned commands also require a
  yes/no voice confirmation before running.
- **New features**: to-do list, reminders (with a background thread
  that checks and speaks them), voice calculator, system stats,
  screenshots, clipboard reading, offline Wikipedia fallback.
- **Robustness**: the main loop no longer crashes on one bad command.

## Notes for your machine

- `_play_music()` uses `os.startfile()`, which is Windows-only. Put
  your mp3s in `data/music/` — see the comment in `assistant.py` if
  you want a cross-platform version (e.g. using the `playsound` package).
- `config.APPS` commands (`calc`, `mspaint`, etc.) are Windows commands.
  If you ever move to Mac/Linux, update that dict.

## What changed from v2.1 → v2.2

- **Wake word**: J now ignores speech until it hears "hey j" first
  (e.g. "hey j, open notepad"). Say just "hey j" alone and it'll
  prompt "Yes?" and listen for your actual command. This means the
  mic can stay on without J reacting to every random sound or
  unrelated conversation in the room. Typed input in the GUI still
  works without the wake word — typing is already an explicit action.
  Change the trigger phrase in `config.py` (`WAKE_WORD`).
- **Fuzzy matching**: mic mishearings like "opne notepad" or "open
  note pad" now still correctly open Notepad, instead of falling
  through to "I didn't understand." Uses Python's built-in `difflib`
  — no extra dependency. Applies to apps, websites, and your learned
  custom commands. Tune strictness via `FUZZY_CUTOFF` in `config.py`
  (closer to 1.0 = stricter, fewer false matches).

## Files added in this round

- `fuzzy_match.py` — the `best_match()` helper, stdlib-only

## What changed from v2.2 → v2.3

- **Fixed mic not picking up audio**: `config.MIC_DEVICE_INDEX` now
  pins a specific microphone device instead of relying on Windows'
  "default" device, which was capturing near-silence. Run
  `py mic_test.py` (lists all devices, tests the default) or
  `py mic_device_test.py` (tests specific indices one by one) any time
  audio stops working — e.g. after plugging in a headset — to find
  the right index and update `config.py`.
- **Fixed wake word not triggering**: short phrases like "hii j" or
  "hey j" often get mistranscribed by speech recognition into an
  actual word it knows (e.g. "aj"), so an exact match failed even
  when you said it correctly. `config.WAKE_WORD_ALIASES` now lists
  common mistranscriptions, and `find_wake_word()` in
  `fuzzy_match.py` fuzzy-matches against all of them.

## Files added in this round

- `mic_test.py` — lists mics, tests the default device
- `mic_device_test.py` — tests specific device indices

## What changed from v2.3 → v2.4

- **User profiles**: multiple people can now share one J installation
  with separate memory. Say "create a profile" (gives your name +
  a spoken PIN), then "log in" any time to switch to your own notes,
  to-dos, and reminders. Say "who am i" to check, "log out" to return
  to the shared guest bucket. PIN matching is fuzzy (via `difflib`)
  since speech recognition can mangle short PIN phrases.
  ⚠️ This is NOT real security — PINs are stored as plain text and
  meant only to separate profiles for convenience, not to protect
  anything sensitive.
- **Smarter recall**: "what did I say about my exam" now searches
  for the most RELEVANT note by topic, instead of always returning
  only the most recent note. Works automatically in "keyword" mode
  (TF-IDF, already installed via scikit-learn) with no setup. Install
  `sentence-transformers` (commented out in requirements.txt) for a
  real offline meaning-based upgrade — it'll auto-detect and switch
  modes, no code changes needed either way.
- **Classifier tuning**: adding 4 new intents (profiles/login/logout/
  whoami) diluted confidence scores across the now-23 intents, so
  correct answers like "add a task" started falling below the
  confidence threshold. Fixed by adding more training examples to
  the weakest intents and retuning the threshold — held-out accuracy
  actually went UP to ~61% (from ~54%) despite having more intents,
  since the extra training data more than made up for the dilution.

## Files added in this round

- `features/user_profile.py` — profile registration + fuzzy PIN login
- `features/semantic_memory.py` — topic-relevant note search
  (semantic mode if `sentence-transformers` installed, else keyword
  fallback via TF-IDF)

## What changed from v2.4 → v2.5

- **Daily briefing mode**: say "good morning" (or "give me my
  briefing", "daily briefing", "start my day") for a spoken summary
  of your day — today's date, pending to-dos, any reminders set for
  today, and your most recent note, all pulled together in one go.
  Scoped to whichever profile is logged in, same as everything else.
- **Reliability fix**: common greeting/briefing phrases now bypass
  the ML classifier and match directly, so "hello" and "good morning"
  always work reliably no matter how diluted the classifier's
  confidence gets as we keep adding intents (same class of bug we
  hit and fixed with "add a task" earlier).

## What changed from v2.5 → v2.6

- **Sentiment-aware responses**: Raju now notices when you sound
  frustrated (e.g. "this stupid thing never works") and responds with
  a brief acknowledgment ("Sorry about that") before proceeding, and
  uses a gentler apology if it also doesn't understand the command.
  Uses VADER, a lexicon-based sentiment scorer — not a neural model
  or API, just word-list lookups + simple rules, fully offline and
  instant. Install: `pip install vaderSentiment` (already in
  requirements.txt). Tune sensitivity via `SENTIMENT_NEGATIVE_THRESHOLD`
  / `SENTIMENT_POSITIVE_THRESHOLD` in `config.py`.
  ⚠️ Honest limitation: VADER catches word-level negativity ("stupid",
  "annoying", "useless") but not implied frustration through phrasing
  alone — e.g. "why can't you just open notepad already" scores as
  neutral since it has no explicitly negative words. It's a real but
  limited signal, not true understanding of tone.
- **Classifier fix**: "thanks" only had 4 training examples, so
  phrases like "thank you so much, you're amazing" were being
  misclassified as "recall" (0.53 confidence). Expanded to 10
  examples — fixed, and overall accuracy stayed at ~61%.

## Files added in this round

- `features/sentiment.py` — VADER-based sentiment detection

## Next steps

- System tray icon
- Command history export

## What changed from v2.6 → v2.7

- **System tray icon**: closing the GUI window (the X button) now
  minimizes to the system tray instead of quitting, using `pystray` +
  `Pillow` (the icon itself is drawn in code — a green circle with
  Raju's initial — no image file needed). Right-click the tray icon
  for "Show Raju" / "Quit". Continuous listening keeps running while
  minimized, since Tkinter's event loop and background threads are
  unaffected by `root.withdraw()`.
  Note: `pystray`'s event loop runs on its own thread (a platform
  requirement, not a choice), so its menu callbacks route through
  `root.after(0, ...)` to safely reach Tkinter — the exact same
  thread-safety pattern used for the speech/listen background thread.
- **Bugfix**: the GUI's "Listening..." status text still said
  `hey j` from before the Raju rename — now pulls from
  `config.WAKE_WORD` dynamically so it can't go stale again.

## Files added in this round

(none — tray icon logic lives in `gui.py`)

## What changed from v2.7 → v2.8

- **Command history**: every command is now logged to a new `history`
  table (query, detected intent, timestamp), scoped per user profile.
  Say "show my command history" for a spoken summary of the last 5,
  or "export my history" to save a full CSV (timestamp, query,
  intent) to `data/` — openable in Excel/Sheets. Logging happens via
  a lightweight independent classifier call so it captures the
  ML model's actual guess even for commands handled by an earlier
  exact/fuzzy match (e.g. "open notepad" still logs its ML-predicted
  intent even though the app-launcher path handled it directly).

## Files added in this round

- `features/history.py` — history viewing + CSV export

---

This completes every feature from our original planning list:
GUI, wake word, fuzzy matching, user profiles, semantic memory,
daily briefing, sentiment-aware responses, system tray icon, and
command history export.
