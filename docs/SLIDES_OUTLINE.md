# Slides outline (10 slides, 5-6 minutes + live demo)

1. **Title**: Raju, a voice assistant for my PC. Name, class, date.
2. **Problem and goal**: control the PC by voice, core works offline, like Jarvis.
3. **How it works**: one diagram (mic -> wake word -> intent model -> action -> voice + screen).
4. **Offline vs online**: two columns. Offline: intent model, memory, to-do, reminders, calculator, apps. Online: Google speech, Wikipedia.
5. **The ML part**: table of 3 models (73.6 / 82.6 / 82.3). Chosen: TF-IDF + Logistic Regression. Why cross-validation.
6. **Before and after**: 60.9% -> 83.6%. "exit", "stop raju", "take screenshot" now work.
7. **Safety**: no shell, safe app list, hashed PIN, lockout. One real bug we found and fixed ("1235" logged in as "1234").
8. **Interface**: 2 screenshots (Chat, Tasks) light and dark.
9. **Testing**: 496 tests, smoke test, fake voice. Honest limits.
10. **Next steps and questions**: offline speech (Vosk), more training data. Then: LIVE DEMO (see DEMO_SCRIPT.md).

Tip: put the live demo after slide 4, not at the end, if time is short.
