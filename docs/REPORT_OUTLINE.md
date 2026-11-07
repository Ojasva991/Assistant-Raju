# Report outline: Raju, a hybrid voice assistant for Windows

## 1. Introduction (1 page)
- Problem: a personal assistant that controls my own PC, works without internet for the core, like Jarvis.
- Goal and scope. What is NOT in scope (offline speech, paid APIs).

## 2. System design (2 pages)
- Block diagram: mic -> speech to text -> wake word -> normalise -> intent model -> handler -> text to speech + UI.
- Table: part, library, offline or online (from README).
- Folder map and the rule "UI only calls Assistant.execute() and reads the database".
- Threading: UI thread never listens or speaks; worker thread + Qt signals.

## 3. The AI part: intent classifier (2-3 pages)  <- main marks
- Data: 446 sentences, 27 intents including `unknown`, stored in `training_data.json`.
- Preprocessing: lowercase, numbers masked as `num`.
- Model comparison by 5-fold stratified cross-validation x 5 repeats:

| Model | Accuracy |
|---|---|
| Naive Bayes, word counts (old) | 73.6% |
| TF-IDF 1-2 grams + Logistic Regression (chosen) | 82.6% |
| TF-IDF 1-2 grams + LinearSVC | 82.3% |

- Rules before the model (exit, screenshot, clipboard, ...) and confidence threshold 0.12.
- Final result: 83.6% with rules and threshold. Original app: about 60.9% on the same data (CHANGELOG).
- Why cross-validation and not one split (small data, one split is noisy).
- Honest limits: 37.5% of `unknown` sentences still trigger an action; 4.2% real commands rejected.

## 4. Other features (2 pages)
- Memory (SQLite tables), notes recall with TF-IDF, to-do, reminders (time parser), safe calculator (`ast`, no `eval`), system stats, history + CSV.
- Fuzzy matching (`difflib`) for mishearings.
- Sentiment (VADER) and its limit.

## 5. Safety and security (1 page)
- `os.system` replaced by `Popen` without shell, only values from `config.APPS`.
- PIN: salted PBKDF2 hash, `compare_digest`, exact match, lockout after 3 wrong tries. Bug found: fuzzy PIN let "1235" log in as "1234".
- Honest limit: not real security; `assistant.log` holds commands in plain text.

## 6. User interface (1 page)
- PySide6: sidebar, 5 pages, tray, light/dark theme, mic pulse, status text.
- Why PySide6 (compared CustomTkinter, web UI, Flet, Dear PyGui).
- Add the screenshots from `python tools\ui_screenshot.py`.

## 7. Testing (1 page)
- 496 automated tests (pytest) with a fake voice and temporary database, no mic needed.
- Smoke test `tools/smoke_test.py` (27 checks) and `--all` for real mic, speakers, apps.
- Mutation checks: breaking a feature on purpose makes tests fail.
- What was tested on the real PC and what was not (be honest).

## 8. Limits and future work (1 page)
- Google speech needs internet; typed commands are the backup.
- First upgrade: offline speech (Vosk or faster-whisper) via `config.STT_ENGINE`.
- More `unknown` training examples; weather (online, polite failure); real user accounts if ever needed.

## 9. Conclusion + references
- scikit-learn, SpeechRecognition, pyttsx3, PySide6, VADER, Wikipedia library.

## Appendix
- Config options, command list (README), test output.
