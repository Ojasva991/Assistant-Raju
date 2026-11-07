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

## Day 1 (v3.0 in progress): intent classifier

- Training sentences now load from `training_data.json` (455 sentences,
  27 intents including an explicit `unknown`). After number masking,
  8 sentences were identical to another one and were kept once (447).
- Numbers and number words become the token `num`, so "fifteen plus
  twenty" and "12 plus 7" look the same to the model.
- Model chosen by 5-fold stratified cross-validation, repeated 5 times
  with different shuffles (every sentence is predicted by a model that
  never saw it):

  | Model | Accuracy | Macro-F1 |
  |---|---|---|
  | Naive Bayes on word counts (old model) | 73.5% +/- 0.7% | 0.748 |
  | TF-IDF (1-2 word pairs) + Logistic Regression (chosen) | 82.9% +/- 0.9% | 0.842 |
  | TF-IDF (1-2 word pairs) + LinearSVC (calibrated) | 82.6% +/- 0.8% | 0.839 |

  Logistic Regression and LinearSVC are tied inside the noise; Logistic
  Regression was chosen because it is slightly higher and gives real
  probabilities without a calibration step.
- Rule table (exit, quit, stop raju, screenshot, clipboard,
  battery/cpu/ram, thanks) runs before the model and returns
  confidence 1.0. Model + threshold 0.12 + rules: 83.9% cross-validated.
- Threshold 0.12 (was 0.28): the highest value that costs at most
  0.5 points of accuracy.
- Before and after, same CV method: old model on the old 186-sentence
  data 60.9% (the earlier single split gave 61.7%); new pipeline 83.9%.
  Not a perfect comparison: the old data had no `unknown` class.
- Known weakness: about 40% of the `unknown` sentences are
  still mapped to some action (for example "book a flight" -> todo_add)
  when the model is tested on unseen sentences. More `unknown` examples
  would help.
- When Raju does not understand, the reply now gives one example command.
- Tests: `tests/test_classifier.py` (27 tests). Run `python -m pytest tests -q`.

## v3.0 work in progress: Day 2 (assistant core)

- Class `J` renamed to `Assistant` (`J = Assistant` kept for old imports).
- Every query is cleaned first (lowercase, no punctuation, leading wake word removed),
  so typed and spoken input behave the same.
- The intent is predicted once per command and reused for the history log and the handler.
- New handlers for `open_app` and `open_site` (exact name first, then fuzzy). If the model
  picks the wrong kind ("go to youtube" as an app), the other kind is tried. Unknown names
  make Raju say which names he knows.
- `_confirm` accepts whole words only (yes, yeah, yep, sure, okay, ok, do it).
  A "no" word wins ("not okay"). "yesterday" is no longer a yes.
- `os.system` removed. Apps start with `subprocess.Popen` (no shell), and only commands that
  are values in `config.APPS` may run, including learned commands from the database.
  `COMMAND_WHITELIST_PREFIXES` deleted.
- One helper (`open_with_system`) for opening files and URIs on Windows, macOS and Linux.
- Time is spoken as "3:44 PM".
- Rotating log file `data/assistant.log` (query, intent, confidence, errors).
- `pyautogui` and `pyperclip` are imported only when used (spoken error if missing).
- Tests: `tests/test_assistant_commands.py` (60 checks). Total with Day 1: 87, all pass.
- Added `tools/smoke_test.py`: a quick health check (packages, config, classifier, 15 assistant
  commands with a fake voice and a temporary database). Flags `--speak`, `--mic`, `--listen`,
  `--apps`, `--online`, `--all` test the real speakers, microphone, apps and internet.
  `tests/test_smoke.py` runs it inside pytest. Total tests: 89.
- Smoke test fix after the first run on the owner's PC: an HTTP error from Wikipedia now counts as
  "internet reachable" (it was a false warning), and `--listen` now prints the recording length and level.

## Day 3 (v3.0 in progress): safety, reminders, calculator, speech

- **PINs:** PBKDF2-SHA256 salted hash, `hmac.compare_digest`, exact match only ("1235" no longer
  logs in as "1234"). Spoken digits ("one two three four") become "1234" only when every word is
  a digit word. Minimum 4 characters, duplicate PINs refused, login locks for 60 seconds after
  3 wrong tries. Old plain-text PINs are migrated at start and the old column is blanked.
  Raju asks for a new PIN twice to catch mishearing.
- **Reminders:** "in ten minutes", "after 5 minutes", "in an hour", "half an hour", "two and a half
  hours" all work. The checker thread survives errors, marks a reminder done before speaking, and
  calls `on_due(text)` (the window uses it for a tray message).
- **Calculator:** no `eval`. Words become an expression and a small `ast` evaluator solves it
  (correct precedence, "add X and Y", "subtract X from Y", brackets). Whole numbers have no ".0",
  other results have at most 4 decimals, divide by zero is answered politely.
  `word2number` is no longer used (it accepts nonsense such as "five six" = 11), so
  `features/numbers.py` has a strict parser instead.
- **Speech:** one worker thread speaks one sentence at a time from a queue, so replies never
  overlap. `speak()` still waits until the sentence is done. A `muted` flag exists for the window.
- **Listening:** no `input()` in window mode; on a mic problem the window gets an error message.
  Noise calibration happens once, not on every listen. After every reply there is a 10-second
  window where no wake word is needed (`FOLLOW_UP_SECONDS`, 0 = off). Questions Raju asks get
  10 seconds for the answer. Engine name is kept in `config.STT_ENGINE`.
- Console mode prints "Heard: ..." so you can see what the microphone understood.
  PINs are hidden there, and spoken text is never written to the log file.

## Day 4 (v3.0 in progress): PySide6 window

- Tkinter and pystray are gone. New package `ui/`: `theme.py` (light and dark), `bridge.py`
  (the only way worker threads talk to the window), `widgets.py` (hand-painted mic button with
  a pulse ring, chat bubbles), `pages.py`, `main_window.py`. `gui.py` is a thin launcher.
- The window never calls `listen()`, `speak()` or `execute()`; each command runs in a worker
  thread and sends results back as signals. While one command runs, a second one is refused
  with the hint "Raju is busy".
- Status text is always words (Idle, Listening, Thinking, Speaking, Mic error: ...), never only colour.
- Shortcuts: Ctrl+M listen, Ctrl+L text box, Ctrl+1 to Ctrl+5 pages.

## Day 5 (v3.0 in progress): all pages, tray, settings

- Pages: Tasks (Done, Delete, Add), Reminders (table, add, delete), History (table, Export CSV,
  Clear history with an inline confirmation), Settings (theme, speak replies, microphone list,
  continuous listening, read-only wake word and user). They show the current user's data.
- Settings are saved in the `prefs` table and applied live.
- System tray icon (Show Raju, Listen now, Quit). The X button hides to the tray and says so
  once. A reminder that fires shows a tray message.
- History table has a `confidence` column (old databases are migrated).
- Section G fixes: the briefing greets by time of day; "show my tasks" and "show my history"
  read the first three aloud and point to the page; the knowledge lookup removes "who is / what
  is / tell me about / explain / define" before searching; JSON files are read as UTF-8.
- Bugs found by the new tests: a bare "who is" was not handled, and after deleting a reminder the
  next row stayed selected (a second click would have deleted the wrong one).

## Day 6 (v3.0): clean-up, docs, release notes

- `mic_test.py` and `mic_device_test.py` are merged into `tools/mic_test.py`:
  `--list`, `--device N`, `--all` (tests every input device and tells you which index to use).
  Tests in `tests/test_mic_tool.py` (no real microphone needed).
- `.gitignore` now also excludes `.pytest_cache/` and `data/*.csv`. `data/music/.gitkeep` and
  `data/screenshots/.gitkeep` keep the empty folders in git.
- `word2number` removed from `requirements.txt` (nothing uses it). `requirements-dev.txt` has `pytest`.
- README rewritten: it no longer says "offline" and no longer says PINs are plain text. It now
  lists which parts work offline and which need internet.

### Before and after (measured, not estimated)

| | Before (v2.8) | After (v3.0) |
|---|---|---|
| Training sentences | 186 in the code | 446 in `training_data.json` (27 intents, with `unknown`) |
| Intent model | Naive Bayes on word counts | TF-IDF (1-2 words) + Logistic Regression, plus a rule table |
| Accuracy, same CV method | 60.9% (single split earlier: 61.7%) | 83.6% with rules and threshold |
| Model comparison on the new data (5-fold x 5) | n/a | Naive Bayes 73.6%, Logistic Regression 82.6%, LinearSVC 82.3% |
| Real commands wrongly rejected | not measured | 4.2% |
| `unknown` sentences that still trigger an action | not measured | 37.5% |
| "exit", "stop raju", "take screenshot", "what is the weather today" | unknown, unknown, unknown, unknown | exit, exit, screenshot, unknown |
| Automated tests | 0 | 496 pass (sandbox, Linux) |
| Smoke test (`tools/smoke_test.py`) | n/a | 27 checks pass (sandbox) |

The before and after are not a perfect comparison: the old data had no `unknown` class and was
much smaller. The 83.6% still comes from cross-validation on sentences the model did not train on,
but the sentences were written by the same person, so real speech will score lower.

### Not verified yet
- Real microphone and speakers with the window open, the real system tray, high-DPI screens and
  the Windows dark-mode switch were only tested offscreen in a Linux sandbox. Run
  `python tools\smoke_test.py --all` and `python tools\mic_test.py --all` on the PC.
- Checkboxes show a green square when checked, without a tick mark.

## Day 7

- Added `docs/DEMO_SCRIPT.md`, `docs/REPORT_OUTLINE.md`, `docs/SLIDES_OUTLINE.md`, `docs/ROADMAP.md`. No code changes; 496 tests pass.
- README: Raju is described as a hybrid assistant (online speech for now); roadmap link; honest limits. `.gitignore`: `models/`, recordings, `*.wav`.
