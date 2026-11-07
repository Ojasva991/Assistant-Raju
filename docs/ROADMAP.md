# Raju roadmap (read this with HANDOFF.md at the start of every new chat)

Owner: personal project, no deadline, no submission. Goal: make Raju the best it can be, then write a research paper
from REAL measured results. Target PC: Dell Inspiron 15 3511, Intel i3, 8 GB RAM, Windows 11, 256 GB SSD + 1 TB HDD.
Python 3.10 syntax. PySide6 only. Simple English, short answers, result first.

## Decisions made (owner)
1. Raju is a **hybrid** assistant: offline core + online extras. Never call it "offline" until speech is offline too.
2. **Languages:** Hindi + English (Hinglish) first. Other Indian languages only after that, one at a time.
3. Offline speech, local LLM and Piper voice are wanted, but **ask before installing any heavy dependency or model**.
4. Models live in a local `models/` folder (git-ignored), downloaded by `tools/get_models.py` from the official source
   with a pinned version + SHA-256 + `models/MANIFEST.json`. Google Drive = personal backup only, never the source.
5. Core commands must work with the LLM off and with no internet (typed). The LLM never runs shell commands.
6. Real numbers only. Never write a result in the README, CHANGELOG or paper that we did not measure.

## Rules for every phase
- Start of chat: unzip, read `HANDOFF.md` and this file. Do not ask what is needed. If no zip: ask only for the zip.
- Before code: 2-3 lines "what and why". Every bug fix gets a pytest test. Run all tests before saying "works".
- Say clearly what could not be run (mic, speakers, real desktop).
- End of phase: update HANDOFF.md (status + what changed), CHANGELOG.md, tick the table below, rebuild the full zip
  (no `.venv`, `.git`, `__pycache__`), present it, give PowerShell copy + test commands, and a git commit message.

## Status table (update at the end of each phase)
| Phase | Name | Status |
|---|---|---|
| 0 | Original 7-day plan (classifier, core, safety, UI, docs) | DONE, checked on the owner's PC |
| A | English polish (no new dependencies) | NOT STARTED |
| B | Language-ready code (i18n) + regression tests | NOT STARTED |
| C | Measurement tools + real held-out data | NOT STARTED |
| D | Hindi + English (Hinglish) with Google speech | NOT STARTED |
| E | Offline speech (faster-whisper / Vosk) + models folder | NOT STARTED |
| F | Optional: local LLM fallback, Piper voice | NOT STARTED |
| G | Final evaluation + research paper | NOT STARTED |
| H | Release: README, licence, GitHub release | NOT STARTED |

---
## Phase A: English polish (no new dependencies)
- A1 Add about 60 `unknown` sentences (weather, jokes, chit-chat, near-miss commands). Re-tune threshold. Report the new
  "unknown wrongly triggers an action" number (was 37.5%) and accuracy (was 83.6%).
- A2 Stricter fuzzy app match ("point" must not open Paint): higher cutoff or ask "Did you mean Paint?". Test it.
- A3 Checkbox tick mark in `ui/theme.py` (status must not rely on colour only).
- A4 Replace `print` with `logging` in `semantic_memory.py` and `sentiment.py`.
- A5 "Starting Raju..." message or small splash while the classifier trains.
- A6 Test: one profile can never read another profile's notes, tasks, reminders, history.
- A7 Save PIN lockout in the database (survives restart).
- A8 Real `.pptx` slides from `docs/SLIDES_OUTLINE.md` (use real screenshots from `tools/ui_screenshot.py`).
- **Done when:** all tests pass, new numbers in CHANGELOG, owner checks on PC.
- **Prompt:** "Phase A. Read ROADMAP.md and HANDOFF.md. Do A1 to A7, then A8. Give the full zip."

## Phase B: language-ready code
- B1 Move every sentence Raju says into `i18n/en.json` (keys like `time.reply`) with a `t(key, **values)` helper.
  Code must contain no spoken English text after this.
- B2 `config.LANGUAGE = "en"` (later "hi", "auto") + a Language dropdown in Settings (saved in `prefs`).
- B3 One regression test per intent (27) so nothing breaks when Hindi is added.
- **Done when:** behaviour identical in English, all tests pass, a fake `hi.json` with two keys proves the switch works.
- **Prompt:** "Phase B. Make Raju language-ready with i18n files. Do not change English behaviour."

## Phase C: measurement tools and real data (needed for the paper)
- C1 `tools/record_dataset.py`: shows a sentence, records it with the real mic, saves WAV + a CSV row to
  `data/recordings/` (git-ignored, private). Ask for speaker id, language, noise level (quiet / fan / street).
- C2 Held-out test set: sentences that are NOT in `training_data.json`. The classifier is never trained on it.
- C3 `tools/stt_bench.py`: for each engine, per recording: text, WER, time, peak RAM. Output CSV + summary table.
- C4 `tools/latency_log.py` (or logging fields): time per stage (listen, STT, classify, handler, speak).
- Target data: 150-300 spoken commands, 3 or more speakers if possible (family or friends, with their consent),
  English + Hindi + mixed.
- **Done when:** one CSV with Google results on the real recordings exists.
- **Prompt:** "Phase C. Build the recording tool and the benchmark tool. I will record the data on my PC."

## Phase D: Hindi + English (Hinglish)
- D1 Training data: about 400 Hindi/Hinglish sentences, BOTH Roman ("notepad kholo") and Devanagari ("नोटपैड खोलो").
  Claude drafts, the OWNER corrects (Claude can write unnatural Hindi). Keep `unknown` examples in Hindi too.
- D2 Preprocessing: Hindi number words (ek, do, teen, ... sau), time words (minute baad, ghanta, aadha ghanta),
  yes/no (haan, nahi, ji, theek hai), wake word aliases ("राजू", "raju", "raaju").
- D3 Google STT with `hi-IN` and `en-IN`. Decide per utterance: try the configured language, optional second try.
- D4 `i18n/hi.json` replies. Check whether Windows has a Hindi voice (Settings > Time & language > Speech); if not, say
  so and keep English replies or wait for Piper.
- D5 Per-language accuracy table (English, Hindi, Hinglish) with cross-validation AND the held-out set.
- **Done when:** the 27 intents work in Hindi and Hinglish typed input, tests pass, numbers recorded.
- **Prompt:** "Phase D. Add Hindi + English. Draft the Hindi training sentences and I will correct them."

## Phase E: offline speech
- E1 Ask the owner: free SSD space, OK to install `faster-whisper` (and/or `vosk`)?
- E2 `tools/get_models.py` + `models/MANIFEST.json` (name, version, source URL, SHA-256, licence, size).
- E3 Add the engine behind `config.STT_ENGINE` ("google", "faster-whisper", "vosk"). Google stays as an option.
  Whisper models to compare: tiny, base (int8 on CPU). Multilingual is needed for Hindi.
- E4 Run `tools/stt_bench.py` for all engines on the same recordings. Pick by measured WER + latency + RAM.
- E5 Real offline test: Wi-Fi off, cold start, typed + spoken commands, all core commands work.
- **Done when:** a table "engine, language, WER, seconds per utterance, RAM, disk size" is saved in CHANGELOG.
- **Prompt:** "Phase E. I agree to install <engine>. Add it, download the model with the script, and benchmark."

## Phase F: optional extras (only if measurements say it is worth it)
- F1 Local LLM fallback (Ollama or llama.cpp, Qwen2.5-1.5B-Instruct quantised). OFF by default. Used only when the
  intent is `unknown` or `chat`. Output is plain text only. Never executed. Time limit, then template reply.
- F2 Piper TTS, especially if Windows has no Hindi voice. Check licence per voice.
- F3 Measure: seconds to first word, words per second, RAM, with the LLM on and off.
- **Done when:** core works with the LLM off; the numbers show whether to keep it.

## Phase G: evaluation and paper
Possible paper idea (to be confirmed by our own results, not assumed):
"A deterministic-first, optionally generative voice assistant for low-end Windows laptops: measured accuracy, latency
and memory for Hindi-English commands." The novelty is the measured, reproducible comparison on low-end hardware with
Hinglish commands, not a new model.
- G1 Research questions, e.g. RQ1: how accurate are the intent layers on Hindi, English and Hinglish commands?
  RQ2: how do Google, Vosk and Whisper (tiny/base) compare in WER, latency, RAM on an i3 / 8 GB laptop?
  RQ3: does an LLM fallback help enough to justify its cost on this hardware?
- G2 Fair protocol: fixed recordings, same machine, repeated runs (at least 3) with mean and spread, quiet and noisy.
- G3 Limits written honestly: few speakers, own dataset, one laptop.
- G4 Write: abstract, introduction, related work (search real papers; never invent references), system, method,
  results, discussion, limits, conclusion. Put code + manifest + (consented) data in a public repo and Zenodo (DOI).
- G5 Venue: search current student-friendly conferences and workshops at that time; post an arXiv preprint first
  (check the current endorsement rules). Do NOT name venues from memory.
- **Prompt:** "Phase G. Here is the results CSV. Help me write the paper. Use only these numbers."

## Phase H: release
- README (real offline/online table, install, models, licences), CHANGELOG, licence file (owner chooses, MIT is common),
  GitHub release tag, screenshots, a short demo video link (optional).

## Checks before any public release
- No `data/memory.db`, logs, recordings or screenshots in git. No PINs. Check `git log --all -- data/memory.db`.
- Model licences listed. Third-party names and voices credited.
- Anyone recorded gave consent; publish speaker ids, never names.

## Known problems carried forward
See `HANDOFF.md` "Known problems". Biggest: 37.5% of unknown sentences trigger an action; wake word is text-based and
needs internet; lockout resets on restart; English only.
