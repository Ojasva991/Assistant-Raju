"""
intent_classifier.py
The "AI" part of the project: a small text-classification model that
maps a spoken sentence to an intent. Trained fresh each run on the
examples below (fast — this is a tiny dataset, not a deep model).

Upgrades vs the original version:
  - Far more training examples per intent (was ~2-3, now ~12+)
  - More intents (todo, reminder, calculator, system stats, screenshot,
    clipboard, greeting, thanks)
  - Confidence threshold: if the model isn't sure, it says so instead
    of guessing wrong
  - train_and_report() lets you print accuracy on a held-out test split
    for your project report
"""

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

import config

TRAINING_DATA = {
    "open_app": [
        "open notepad", "open calculator", "open paint", "open command prompt",
        "open file explorer", "launch notepad", "start calculator",
        "open settings", "open control panel", "open task manager",
        "can you open notepad", "please open the calculator",
    ],
    "open_site": [
        "open youtube", "open google", "open github", "open gmail",
        "open whatsapp", "go to youtube", "launch google", "take me to github",
        "open my gmail", "open whatsapp web",
    ],
    "time": [
        "what is the time", "tell me time", "what time is it",
        "current time please", "do you know the time", "what's the time now",
    ],
    "date": [
        "what is the date", "today date", "what is today's date",
        "what day is it", "tell me the date", "current date please",
    ],
    "music": [
        "play music", "start music", "play a song", "play some music",
        "put on some music", "play the guitar song",
    ],
    "exit": [
        "exit", "quit", "stop jarvis", "stop j", "shut down", "goodbye j",
        "close the assistant", "that's all",
    ],
    "remember": [
        "remember this", "remember that", "please remember something",
        "note this down", "save this for me", "make a note",
    ],
    "recall": [
        "show your memory", "what do you remember", "recall my note",
        "what did i tell you", "show my notes", "what did i say about my exam",
        "what do you remember about my project", "recall what i said about",
        "what did i tell you about", "do you remember anything about",
        "what do you know about my", "tell me what i said about",
    ],
    "learn_command": [
        "learn this command", "teach you something", "learn a new command",
        "i want to teach you", "add a custom command",
    ],
    "todo_add": [
        "add a task", "add to my todo list", "add a to-do",
        "remind me to do something", "put this on my list", "new task",
        "add a new task", "add task", "add something to my list",
        "i need to add a task", "create a new to-do", "add an item to my list",
    ],
    "todo_show": [
        "show my tasks", "what is on my to-do list", "show my todo list",
        "list my tasks", "what do i need to do", "show my list",
        "what's on my list", "show pending tasks", "list my to-dos",
    ],
    "reminder_add": [
        "remind me in ten minutes", "set a reminder", "remind me later",
        "set an alarm", "remind me to call mom", "wake me up in an hour",
        "set a reminder for me", "create a reminder", "please remind me",
    ],
    "calculator": [
        "what is fifteen plus twenty", "calculate two plus two",
        "what is ten times five", "add three and four", "what is 100 divided by 4",
        "subtract five from ten",
    ],
    "system_stats": [
        "how much battery do i have", "how much ram is free",
        "check system status", "what is my cpu usage", "battery percentage",
    ],
    "screenshot": [
        "take a screenshot", "capture the screen", "screenshot this",
    ],
    "clipboard": [
        "read my clipboard", "what did i copy", "read clipboard",
    ],
    "greeting": [
        "hello", "hi raju", "hey there", "good evening", "hi", "hey",
    ],
    "daily_briefing": [
        "good morning", "give me my briefing", "daily briefing",
        "what's on my plate today", "morning briefing", "start my day",
        "give me a rundown of my day", "brief me for today",
        "what do i have today", "catch me up for today",
    ],
    "thanks": [
        "thank you", "thanks raju", "appreciate it", "thanks a lot",
        "thank you so much", "you are amazing", "thanks for the help",
        "that was great thank you", "much appreciated", "thanks so much",
    ],
    "search": [
        "who is albert einstein", "tell me about the eiffel tower",
        "who is elon musk", "tell me about python programming",
        "who was mahatma gandhi",
    ],
    "register_profile": [
        "create a profile", "create a new profile", "sign me up",
        "register a new user", "i want to create a profile",
        "make a new profile for me",
    ],
    "login": [
        "log me in", "log in", "please log me in", "i want to log in",
        "switch user", "login to my profile",
    ],
    "logout": [
        "log me out", "log out", "sign me out", "switch to guest",
    ],
    "whoami": [
        "who am i", "which profile am i using", "am i logged in",
        "whose profile is this", "what is my name", "tell me who i am",
        "am i using a profile", "check my login status",
    ],
    "show_history": [
        "show my command history", "what have i asked you",
        "show my history", "what have i said today", "recent commands",
        "show what i've asked", "list my recent commands",
    ],
    "export_history": [
        "export my history", "export my command history",
        "save my history to a file", "download my history",
        "export history to a file", "create a history export",
    ],
}


class IntentClassifier:
    def __init__(self):
        self.vectorizer = CountVectorizer()
        self.model = MultinomialNB()
        self.train()

    def _flatten(self):
        X, y = [], []
        for intent, samples in TRAINING_DATA.items():
            for s in samples:
                X.append(s)
                y.append(intent)
        return X, y

    def train(self):
        X, y = self._flatten()
        X_vec = self.vectorizer.fit_transform(X)
        self.model.fit(X_vec, y)

    def predict(self, text):
        """Returns (intent, confidence). Intent is 'unknown' if below threshold."""
        vec = self.vectorizer.transform([text])
        probs = self.model.predict_proba(vec)[0]
        best_idx = probs.argmax()
        confidence = probs[best_idx]
        intent = self.model.classes_[best_idx]

        if confidence < config.CONFIDENCE_THRESHOLD:
            return "unknown", confidence
        return intent, confidence

    def train_and_report(self):
        """Optional: prints a held-out accuracy score. Handy for your report."""
        X, y = self._flatten()
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y
        )
        vec = CountVectorizer()
        X_train_vec = vec.fit_transform(X_train)
        X_test_vec = vec.transform(X_test)

        model = MultinomialNB()
        model.fit(X_train_vec, y_train)
        preds = model.predict(X_test_vec)
        acc = accuracy_score(y_test, preds)
        print(f"[IntentClassifier] Held-out accuracy: {acc:.2%} "
              f"({len(y_test)} test samples, {len(set(y))} intents)")
        return acc


if __name__ == "__main__":
    # Run this file directly to see a quick accuracy report:
    #   python intent_classifier.py
    clf = IntentClassifier()
    clf.train_and_report()
