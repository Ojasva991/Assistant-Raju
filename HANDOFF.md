# HANDOFF: read this first in every new chat

Project: Raju, a system-specific Windows voice assistant (offline core, online extras, like Jarvis).
Owner rules: simple English, short answers, result first. PySide6 only (never Tkinter). Python 3.10 syntax.
Ask the owner before adding any paid API or heavy dependency. Every bug fix gets a pytest test.
Plan: 7 days from Mon 2 Nov 2026, see `05_schedule.md` in project knowledge.

## Status
- Last finished day: **Day 7** (demo script, report outline, slides outline; no code changes). Sandbox only; Day 4, 5, 6 NOT tried on the owner's PC yet.
- The 7-day plan is finished and checked on the owner's PC (owner confirmed). Day 4-6 "not tried on PC" notes below are now OUT OF DATE.
- NEXT: follow `docs/ROADMAP.md` (Phases A to H). Owner decisions: Hindi + English first; models in local `models/` (Drive = backup only);
  personal project, later a research paper from real measurements. Start with Phase A unless the owner says otherwise.
- This zip is the base for the next day. Do not ask the owner what is needed. Work on this zip.

## What Day 1 changed (done)
- `intent_classifier.py` rewritten: loads `training_data.json` (447 sentences after dedupe, 27 intents),
  masks numbers as `num`, rule table first (confidence 1.0), then model, then threshold.
- Model: TF-IDF 1-2 grams + LogisticRegression (C=10). Chosen by 5-fold CV x 5 repeats.
  Naive Bayes 73.5%, LogReg 82.9%, LinearSVC 82.6% (tie). Final with rules and threshold: 83.9%.
- `config.py`: `MODEL_NAME="logreg"`, `CONFIDENCE_THRESHOLD=0.12`, `TRAINING_DATA_PATH`, CV settings.
- Tests: `tests/test_classifier.py`, 27 tests.

## What Day 2 changed (done)
- `assistant.py` rewritten: class `Assistant` (`J = Assistant` alias), `normalize_query`, one prediction per
  command, handlers `open_app` / `open_site` via `_open_target`, `is_yes` (whole words, "no" wins),
  `run_allowed_command` (Popen, no shell, only `config.APPS` values), `open_with_system` (one helper for
  startfile / open / xdg-open), `format_time` ("3:44 PM"), `setup_logging` (rotating `data/assistant.log`).
- `Assistant(...)` has keyword arguments for tests: `voice`, `listener`, `db_path`, `classifier`,
  `start_reminders`, `log_path`.
- `fuzzy_match.py`: new `find_known_name(text, names, cutoff, fuzzy)`.
- `config.py`: `COMMAND_WHITELIST_PREFIXES` removed; added `CONSOLE_APPS`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`.
- `speech_engine.py`: prints and logs "Raju:" instead of "J:".
- `features/system_utils.py`: `pyautogui` and `pyperclip` imported only when used (pulled forward from section G).
- `main.py` uses `Assistant`. `.gitignore`: added `data/*.log`.
- Tests: `tests/test_assistant_commands.py`. Run all: `python -m pytest tests -q` -> 89 passed (in my sandbox, Linux).
- Verified by mutation: breaking `is_yes` or the APPS check makes tests fail.
- `tools/smoke_test.py` (owner asked for it): `python tools\smoke_test.py` (safe, about 3 s) or `--all`
  (also speakers, mic, real Notepad/Calculator, internet). Exit code 1 on any FAIL. Also run by
  `tests/test_smoke.py`. Day 3 and later: ADD new smoke cases to it for each new feature, and run it before
  giving the zip. Total tests now 92.

## Real-PC results (owner ran `smoke_test.py --all` on 1 Nov, Windows, Python 3.10.4)
- All 19 safe checks pass. Mic index 1 = "Microphone (Realtek(R) Audio)", 29 devices. Real Notepad and Calculator started.
- `--listen`: audio recorded but Google could not understand it (cause not known yet: late speech or low level).
  Re-run `--listen` with the new level output and decide. Owner has not yet confirmed hearing the speaker test.

## What Day 3 changed (done, all in sandbox tests: 333 passed; smoke test 25 PASS)
- **C PINs** (`features/user_profile.py`, `database.py`): PBKDF2-SHA256 salted hash (`pin_hash` column, format
  `pbkdf2_sha256$iterations$salt$hash`), `hmac.compare_digest`, exact match only ("1235" no longer logs in as "1234"),
  spoken digits to digits only when every word is a digit word (`normalize_pin`), min length 4, duplicate PIN rejected
  (message does not name the owner, and counts as a wrong try so `register` cannot be used to guess PINs), lock 60 s after
  3 wrong tries (in memory, resets when Raju restarts; silence is not a wrong try). Old plain-text PINs are migrated at
  start and the old `pin` column is blanked. Old PINs stored as "onetwothreefour" are converted to "1234". Login returns
  `{"id","name"}` only (no hash). Constants: `config.PIN_*`.
- **D Reminders** (`features/reminders.py`): `parse_relative_time(text, now)` handles ten/10, "after", "an hour",
  "half an hour", "two and a half hours", "an hour and ten minutes", "1 hour 30 minutes", "quarter of an hour"; returns
  None instead of guessing. Time said in the first sentence ("remind me in ten minutes") is not asked again.
  Checker thread: survives errors, marks done BEFORE speaking, `on_due(text)` callback (called before the spoken
  reminder), stops at once on `stop()`, starting twice makes one thread. Reply says "10:10 AM".
  `database.get_due_reminders(now_iso=None)`.
- **E Calculator** (`features/calculator.py`, new `features/numbers.py`): no `eval`; words become an expression, then a
  small `ast` evaluator (numbers, + - * / and brackets only). Precedence, "add X and Y", "add X to Y",
  "subtract X from Y" = Y minus X, "multiply/divide X by Y", symbols (+ - * / x), decimals, "1,000", whole numbers
  without ".0", 4 decimals, divide by zero spoken politely. All 20 training sentences give the right answer (tested).
  **word2number is no longer used**: I tested it and it accepts nonsense ("five six" = 11, "a hundred five" = 500),
  so `features/numbers.py` has a strict parser. word2number is still in requirements.txt and `tools/smoke_test.py`
  PACKAGES; ask the owner whether to remove it (Day 6).
- `assistant.normalize_query` now turns math symbols into words ("12 + 7" becomes "12 plus 7"), because Google writes sums
  with symbols and `clean_text` used to delete them. `timeutil.py` (new) holds `format_time`; `assistant.format_time` still works.
- **F Speech** (`speech_engine.py`): one worker thread + queue; `speak()` blocks until its sentence is done; `muted` flag
  (text still shown); fresh pyttsx3 engine per sentence; `wait_until_idle()`; `close()`; pyttsx3 imported late; console
  print survives odd letters (cp1252); `on_speak` errors are caught. COM is initialised in the worker on Windows
  (`pythoncom`, only if installed). `config.TTS_TIMEOUT`.
- **F Listener** (`listener.py`): `Listener(use_microphone, allow_text_fallback, on_error)`. GUI mode
  (`allow_text_fallback=False`) never calls `input()`: it calls `on_error(msg)` once per distinct message and returns "".
  Noise calibration once (`recalibrate()` after a device change; `device_index` attribute). Engine name in
  `config.STT_ENGINE` ("google"); also `STT_LANGUAGE`, `LISTEN_TIMEOUT`, `PHRASE_TIME_LIMIT`, `AMBIENT_SECONDS`.
  Heard text is NOT logged (could be a PIN); `main.py` prints "You: ..." instead. The mic waits until Raju has
  stopped talking (`listener.before_listen = voice.wait_until_idle`, set by `Assistant`).
- `Assistant(..., allow_text_fallback=True, on_error=None, on_due=None)`: the UI passes these.
- Old Tkinter `gui.py`: one-line stopgap so it never calls `input()` (untested, no Tkinter in sandbox). Replaced Day 4.
- Tests added: `test_calculator.py`, `test_reminders.py`, `test_profiles.py`, `test_speech_and_listener.py`,
  `test_assistant_day3.py` (241 new). Run: `python -m pytest tests -q`. Mutation check: breaking lockout, compare_digest,
  mark-done-first, stop-wakeup, subtract order, queue, calibrate-once, GUI input() each made tests fail.
- `tools/smoke_test.py` new safe cases: calculator words and symbols, reminder "in ten minutes", hashed PIN + wrong PIN +
  spoken digits, speech queue with a fake engine. `--speak` now also speaks two sentences from two threads at once.

## Day 3 fixes after the owner's real-PC test (1 Nov evening; 358 tests pass, smoke 25 PASS)
Owner's real run of `main.py` worked (calculator 12 + 7 = 19, reminder, profile, lockout), but: the wake word was needed for
every command, follow-up answers (name, PIN) were often missed, and the spoken PIN was not always understood.
- **Follow-up mode:** after every reply Raju accepts commands WITHOUT the wake word for `config.FOLLOW_UP_SECONDS` (10; 0 = off).
  Checked from when listening STARTED. `exit` does not open it. Code: `Assistant._awake_until`, `listen_for_command`.
- **Answers get more time:** `Listener.listen_answer()` waits `config.ANSWER_TIMEOUT` (10 s, was 5) and drops a leading
  "raju". All questions Raju asks (todo, reminder, remember, learn, yes/no, name, PIN) use `listener.hear_answer(listener)`.
- **PIN hearing:** `normalize_pin` also understands "my pin is ...", "7,286", homophones ("seven to eight six"),
  and "seven thousand two hundred eighty six". Register asks for the PIN twice (confirmation; a mismatch is not a wrong try).
  Name: "my name is ojas upad" becomes "Ojas Upad".
- Tests: +25 (follow-up window, confirm, PIN spellings, answer timeout). Mutation-checked.
- Owner note: if background talking triggers commands in follow-up mode, set `FOLLOW_UP_SECONDS = 0` or lower it.

## Day 3 fix 2 (owner asked, 1 Nov night)
- Login retry: after a wrong PIN Raju says "N tries left. Say it again." and listens again inside the SAME login (waits
  `ANSWER_TIMEOUT`); silence after a wrong PIN ends login ("login cancelled") and costs no try. Lockout still 3 wrong / 60 s.
- Follow-up window is visible: `main.py` prints when the no-wake-word window opens and when the wake word is needed again.
  `Assistant.follow_up_seconds_left()` (the Day 4 UI can show it in the status bar).

## Day 3 fix 3 (owner: "I didn't catch that, cancelling" when saying the name)
- `Listener.last_status` ("ok", "timeout", "unclear", "error"); `why_nothing_heard(listener)` gives a spoken reason
  ("I didn't hear anything" vs "I heard you, but I couldn't make out the words"). Register (name, PIN) and the first
  login PIN ask ONCE more before giving up. Cause not confirmed on the owner's PC: either speech started too late
  or Google could not recognise the name (rare names). Ask the owner which message Raju now says.
- 371 tests pass.

## Day 3 fix 4 (owner: "it should write what he hears")
- Console mode prints `Heard: <text>` for everything the mic understood (wake-word listening too). Answers to Raju's
  questions also print why nothing was understood. PINs show as "(hidden, because it is a PIN)" unless
  `config.SHOW_SPOKEN_PIN = True` (testing only). `config.SHOW_HEARD = False` turns it off.
- `Listener(on_heard=callback)`: GUI mode never prints; the Day 4 UI can pass a callback to show it in the status bar.
  Heard text is still never written to the log file. 381 tests pass.

## What Day 4 changed (done; sandbox: 406 tests pass, smoke test 26 PASS; NOT tried on the owner's real PC yet)
- New package `ui/`: `theme.py` (light/dark tokens + QSS, `RAJU_THEME=dark|light` env override), `bridge.py` (signals:
  spoke, status, user_said, heard, cycle_done, reminder_due, error, failed, exit_requested), `widgets.py` (MicButton painted
  by hand with pulse ring, Bubble, ChatView keeps last 200, StatusPill), `pages.py` (ChatPage real; `PlaceholderPage` for
  Tasks/Reminders/History/Settings), `main_window.py` (sidebar, stacked pages, status bar, shortcuts, worker threads,
  `build_assistant(bridge)`, `main()`).
- `gui.py` is now a thin launcher. Old Tkinter code is gone. `requirements.txt`: `pystray` and `Pillow` replaced by
  `PySide6-Essentials`.
- Threading: the UI never calls listen/speak/execute. `MainWindow._cycle` runs in a Python thread per command and only emits
  bridge signals. `_busy` blocks a second cycle (hint "Raju is busy" in the status bar, typed text stays in the box).
- Status text: Idle, `Listening for "raju"...` (first listen of a voice cycle, no follow-up window), `Listening...` (answers to
  Raju's questions and follow-up window), Thinking..., Speaking... (only during a cycle), `Mic error: <reason>`.
  The window wraps `listener.before_listen` to show the right text AFTER Raju stopped talking.
- Mic pulse = status starts with "Listening". A mic error shows a system line and turns Continuous listening OFF (no retry loop).
- A command that crashes shows "That command failed (<ErrorType>). Details are in data/assistant.log." (no details on screen).
- `exit` closes the window (after the goodbye was spoken). Closing stops the reminder thread and the speech worker.
- Status bar: status text, "Heard: ..." (from `Listener.on_heard`, PINs are hidden), Continuous listening checkbox, `User: <name>`.
- Shortcuts: Ctrl+M listen, Ctrl+L focus the text box, Ctrl+1..5 pages. Pages call `refresh()` when shown and after cycle_done.
- `reminder_due` only shows a status bar message for now (Raju also speaks it, which makes a bubble). Day 5: tray message.
- No tray yet (Day 5), so closing the window quits the app for now.
- `tools/ui_screenshot.py` renders all pages offscreen (light and dark) into `data/screenshots_ui/` (git-ignored).
- `tools/smoke_test.py`: new package check (PySide6) and `ui window (offscreen)` case (runs in a subprocess).
- Tests: `tests/test_ui_smoke.py` (25): pages, themes, typed and voice cycles, busy rule, worker-thread rule, errors,
  continuous mode, exit, close, 200-bubble limit, bubble height regression. Mutation-checked: running the cycle on the UI
  thread, removing the busy guard, not turning continuous off, no 200 limit, "Speaking" while idle, and the old bubble sizing
  each made a test fail.
- Fixed while building: word-wrapped QLabel clipped long text; `Bubble.fit()` now sets width and height from the font metrics.

## What Day 5 changed (done; sandbox: 481 tests pass, smoke test 27 PASS; NOT tried on the owner's real PC yet)
- **Pages** (`ui/pages.py`, placeholders gone): `TasksPage` (rows with Done/Delete, Add field, empty-state text),
  `RemindersPage` (table Reminder/Due/Status, text + minutes number box, Delete selected, past-due and done rows greyed,
  status is also text), `HistoryPage` (Time/Command/Intent/Confidence, newest 200, Export CSV, Clear history with an INLINE
  confirmation row instead of a pop-up), `SettingsPage` (theme system/light/dark, speak replies, microphone dropdown +
  Refresh, continuous-listening default, read-only wake word and user). All pages show the CURRENT user's data and reload
  when shown and after every `cycle_done`.
- **Settings are saved** in the `prefs` table with user_id 0 (app-wide), helper `ui/prefs.py`. Applied at start by
  `MainWindow._apply_saved_prefs` and live when changed: theme (`apply_theme`), speak replies = `voice.muted`, mic =
  `listener.device_index` + `recalibrate()`. Continuous default turns listening on 300 ms after the window starts.
  `MainWindow(theme_mode=None)` reads the saved theme (tests pass "light"/"dark").
- **Microphone list:** `listener.list_input_devices()` (PyAudio, input devices only, `[]` on failure). Listed once when
  Settings is first shown, and on Refresh. Filling the list is never counted as a user choice.
- **Tray** (`main_window.py`): drawn green icon, menu Show Raju / Listen now / Quit. The X button hides to the tray and
  tells the user ONCE (remembered in prefs `tray_hint_shown`). Quit and the voice command `exit` really quit
  (`quit_app`: stops reminders + voice, hides the tray icon, `QApplication.quit()`). A fired reminder shows a tray message.
  `MainWindow(use_tray=None)` auto-detects; no tray (or tests with `use_tray=False`) = closing quits like Day 4.
- **Database:** `delete_todo`, `delete_reminder`, `get_reminders`, `clear_history` (all scoped by user_id),
  `complete_todo(task_id, user_id=None)`, history has a new `confidence` column (old databases are migrated; the assistant
  logs the confidence of its one prediction). CSV has a 4th column `confidence`; `HistoryFeature.write_csv()` writes it
  without speaking (the page uses it; the voice command still speaks the file name).
- **Section G done:** briefing greets by time of day (`greeting_for`: 5-11 morning, 12-16 afternoon, else evening; no "- " in
  reminder lines); "show my tasks" / "show my history" read the first 3 aloud and point to the Tasks / History page, no
  `print`; knowledge strips who is/was/are, what is/was/are, tell me about, explain, define, describe (only at the start;
  bare "who is" now correctly asks what to look up), UTF-8 for the JSON, no `print`; "stop j" removed from
  `training_data.json` (454 sentences); old J / hey j wording removed from comments (`J = Assistant` alias stays on purpose).
- **Bugs found by the new tests:** bare "who is" was not stripped; after deleting a reminder the next row stayed selected
  (a second click would delete the wrong one), so the selection is now cleared on refresh.
- Tests: `tests/test_day5_backend.py` (38), `tests/test_ui_pages.py` (37). Mutation-checked: user scoping of delete, inline
  confirmation, hide-to-tray, mute setting, reminder tray message, topic cleaner each made a test fail.
- `tools/ui_screenshot.py` now puts sample data on the pages (light and dark, `data/screenshots_ui/`).
- `tools/smoke_test.py`: new case `day 5 data (temp db)`.

## What Day 6 changed (done; sandbox: 496 tests pass, smoke test 27 PASS)
- `tools/mic_test.py` replaces `mic_test.py` + `mic_device_test.py` (deleted): `--list`, `--device N`, `--all` (every input
  device, prints sound level + Google text, ends with "Use this in config.py: MIC_DEVICE_INDEX = N"). Exit code 1 if no
  device understood. Tests: `tests/test_mic_tool.py` (15, fake `speech_recognition`; mutation-checked).
- `data/music/.gitkeep`, `data/screenshots/.gitkeep` added. `.gitignore`: added `.pytest_cache/`, `data/*.csv`.
- `word2number` REMOVED from `requirements.txt` and the smoke test package list (nothing imports it; owner can say if they
  want it back). `requirements-dev.txt` = pytest. `config.py` and smoke test now point to `tools/mic_test.py`.
- README rewritten (offline/online table, run + test commands, folder map, safety notes, known limits). CHANGELOG has
  entries for Day 3, 4, 5, 6 and a before/after table (CV accuracy 60.9% -> 83.6%; NB 73.6 / LogReg 82.6 / SVC 82.3;
  446 sentences). Numbers are from `python intent_classifier.py` on 7 Nov.
- NOT done (needs the owner's PC): real mic + speaker test with the window, real tray, high-DPI, dark-mode switch.
  The tick mark for checkboxes is still missing.
- Zip layout: the zip has one top folder `raju/`.

## What Day 7 changed (done; sandbox: 496 tests pass, smoke test 27 PASS; no code changed)
- New `docs/DEMO_SCRIPT.md` (3-minute timeline, pre-demo checklist, fallback plan, things not to show),
  `docs/REPORT_OUTLINE.md` (9 sections with the real numbers), `docs/SLIDES_OUTLINE.md` (10 slides).
- Numbers used: CV accuracy NB 73.6 / LogReg 82.6 / SVC 82.3; final 83.6% with rules + threshold; old app 60.9%; 446 sentences, 27 intents;
  37.5% of unknown sentences wrongly trigger an action; 4.2% real commands rejected.
- Checked: "remind me in one minute" parses (good for the demo). Ctrl+2 = Tasks, Ctrl+4 = History.
- Owner confirmed the real-PC checks of Day 4, 5, 6 (all working).
- README now says hybrid (not offline-only) and links the roadmap; `.gitignore` adds `models/`, `data/recordings/`, `*.wav`.

## Known problems (not fixed yet)
- Day 4 + Day 5: NOT tested on real Windows: real mic + window, speakers while the window is open, Segoe UI look, high-DPI,
  system dark-mode switch, the real system tray (offscreen has none; tray code is tested with a fake-visible tray only),
  the real microphone list (`list_input_devices`) and switching the device while running.
- Checkboxes have no tick mark (checked = green square). Status is still readable in text, but a tick would be clearer.
- The tray notification when Raju hides is shown only once ever. To see it again delete the `tray_hint_shown` row in `prefs`.
- Windows can hide tray icons in the "^" overflow area; the owner may need to drag the Raju icon out once.
- Same microphone names can appear several times in the list (Windows lists each device per audio driver type).
  Use the index that worked in `smoke_test.py --mic`.
- Real `Assistant` start takes a second or two before the window appears (classifier training); no splash screen.
- Lockout is per run (in memory). Two users migrated from the old version with the same PIN: the first one wins at login.
- About 40% of `unknown` sentences still trigger an action on unseen input (more unknown examples would help).
- Fuzzy app match can be too eager for words close to an app name ("point" vs "paint").
- Reminders fire up to `REMINDER_CHECK_SECONDS` (5 s) late. A reminder due while the app is closed fires at next start.
- `config.MIC_DEVICE_INDEX` is 1 in this zip; owner must keep their own value. A device chosen in Settings overrides it.
- `data/assistant.log` stores spoken commands in plain text. It is git-ignored; keep it private.

## Owner's PC
- Project path: `D:\projects\ai assistant`. Backup before Day 1: `D:\projects\ai assistant_backup_before_day1`.
- Copy changed files from the zip into the project with `Copy-Item` (never copy `.venv`).

## End-of-day rule for Claude
At the end of every day: update this file, rebuild the full zip (no `.venv`, no `.git`, no `__pycache__`),
call present_files for it, and give the PowerShell commands to copy it into the project and test it.
