"""
assistant.py
The J assistant itself — wires together speech, memory, the intent
classifier, and all the feature modules. This replaces the old
single-file main.py logic.
"""

import os
import webbrowser
import datetime
import random

import config
from speech_engine import SpeechEngine
from listener import Listener
from database import MemoryManager
from intent_classifier import IntentClassifier
from fuzzy_match import best_match, find_wake_word

from features.todo import TodoFeature
from features.reminders import ReminderFeature
from features.calculator import CalculatorFeature
from features.system_utils import SystemUtilsFeature
from features.knowledge import KnowledgeFeature
from features.user_profile import UserProfileFeature
from features.semantic_memory import SemanticMemory
from features.briefing import BriefingFeature
from features.sentiment import SentimentFeature
from database import GUEST_ID

GREETINGS = [
    f"Hello, I am your assistant {config.ASSISTANT_NAME}. How can I help you?",
    f"Hey, {config.ASSISTANT_NAME} here. What can I do for you?",
]
UNKNOWN_RESPONSES = [
    "I'm not sure I understood that. Could you rephrase it?",
    "Sorry, I didn't quite catch what you meant.",
]
FRUSTRATED_UNKNOWN_RESPONSES = [
    "I'm sorry, I'm having trouble understanding. Let's try that again, slowly.",
    "My apologies, that didn't come through clearly. Could you say it a different way?",
]
FRUSTRATED_ACKNOWLEDGMENTS = [
    "Sorry about that.",
    "I hear you, let me help.",
    "Apologies for the trouble.",
]


class J:
    def __init__(self, use_microphone=True, on_speak=None):
        self.voice = SpeechEngine(on_speak=on_speak)
        self.listener = Listener(use_microphone=use_microphone)
        self.memory = MemoryManager()
        self.ai = IntentClassifier()

        # feature modules
        self.todo = TodoFeature(self.memory, self.voice, self.listener)
        self.reminders = ReminderFeature(self.memory, self.voice, self.listener)
        self.calculator = CalculatorFeature(self.voice)
        self.system_utils = SystemUtilsFeature(self.voice)
        self.knowledge = KnowledgeFeature(self.voice)
        self.profiles = UserProfileFeature(self.memory, self.voice, self.listener)
        self.semantic_memory = SemanticMemory(self.memory)
        self.briefing = BriefingFeature(self.memory, self.voice)
        self.sentiment = SentimentFeature()

        # No profile logged in by default -- memory uses the shared
        # "guest" bucket until someone logs in or creates a profile.
        self.current_user = None
        self.last_sentiment = {"compound": 0.0, "label": "neutral"}

        self.reminders.start_background_checker()

    @property
    def current_user_id(self):
        return self.current_user["id"] if self.current_user else GUEST_ID

    def greet(self):
        self.voice.speak(random.choice(GREETINGS))

    # ---------------- WAKE WORD ----------------
    def listen_for_command(self):
        """
        Waits for one utterance from the mic. Only returns something if
        a wake word was heard — otherwise returns None so the caller
        just keeps listening silently, without J reacting to every
        stray sound or unrelated conversation in the room.

        Uses fuzzy matching against config.WAKE_WORD_ALIASES because
        short wake phrases often get mistranscribed by speech
        recognition (e.g. "hii j" heard as "aj").

        If you say the wake word with nothing else, J prompts "Yes?"
        and listens once more for the actual command.
        """
        heard = self.listener.listen()
        if not heard:
            return None

        remainder = find_wake_word(heard, config.WAKE_WORD_ALIASES)
        if remainder is None:
            return None  # wake word not detected, ignore silently

        if remainder:
            return remainder

        self.voice.speak("Yes?")
        follow_up = self.listener.listen()
        return follow_up or None

    # ---------------- MAIN DISPATCH ----------------
    def execute(self, query):
        if not query:
            return

        self.last_sentiment = self.sentiment.analyze(query)
        if self.last_sentiment["label"] == "negative":
            self.voice.speak(random.choice(FRUSTRATED_ACKNOWLEDGMENTS))

        # 0. Direct-match for common phrases that must always work,
        # regardless of ML classifier confidence dilution.
        if query in config.GREETING_PHRASES:
            self.voice.speak(random.choice(GREETINGS))
            return

        if query in config.BRIEFING_PHRASES:
            user_name = self.current_user["name"] if self.current_user else None
            self.briefing.give_briefing(user_id=self.current_user_id, user_name=user_name)
            return

        # 1. Offline apps — exact match first
        for app, command in config.APPS.items():
            if f"open {app}" in query:
                self.voice.speak(f"Opening {app}")
                os.system(command)
                return

        # 1b. Offline apps — fuzzy fallback (catches mic mishearings like
        # "opne notepad" or "open note pad")
        app_phrases = {f"open {app}": app for app in config.APPS}
        match = best_match(query, list(app_phrases.keys()), cutoff=config.FUZZY_CUTOFF)
        if match:
            app = app_phrases[match]
            self.voice.speak(f"Opening {app}")
            os.system(config.APPS[app])
            return

        # 2. Websites — exact match first
        for site, url in config.WEBSITES.items():
            if f"open {site}" in query:
                self.voice.speak(f"Opening {site}")
                webbrowser.open(url)
                return

        # 2b. Websites — fuzzy fallback
        site_phrases = {f"open {site}": site for site in config.WEBSITES}
        match = best_match(query, list(site_phrases.keys()), cutoff=config.FUZZY_CUTOFF)
        if match:
            site = site_phrases[match]
            self.voice.speak(f"Opening {site}")
            webbrowser.open(config.WEBSITES[site])
            return

        # 3. Learned custom commands — exact match, then fuzzy fallback
        matched_trigger = query
        learned = self.memory.get_command(query)
        if learned is None:
            triggers = self.memory.get_all_triggers()
            close_trigger = best_match(query, triggers, cutoff=config.FUZZY_CUTOFF)
            if close_trigger:
                matched_trigger = close_trigger
                learned = self.memory.get_command(close_trigger)

        if learned:
            confirm = self._confirm(f"Run the learned command for '{matched_trigger}'?")
            if confirm:
                self.voice.speak("Executing learned command")
                os.system(learned)
            else:
                self.voice.speak("Okay, cancelled.")
            return

        # 4. Knowledge lookup
        if query.startswith("who is") or query.startswith("tell me about"):
            self.knowledge.answer(query)
            return

        # 5. ML intent classification for everything else
        intent, confidence = self.ai.predict(query)
        self._handle_intent(intent, query)

    def _handle_intent(self, intent, query):
        if intent == "time":
            now = datetime.datetime.now().strftime("%H:%M")
            self.voice.speak(f"The time is {now}")

        elif intent == "date":
            today = datetime.datetime.now().strftime("%d %B %Y")
            self.voice.speak(f"Today's date is {today}")

        elif intent == "music":
            self._play_music()

        elif intent == "remember":
            self.voice.speak("What should I remember?")
            data = self.listener.listen()
            if data:
                self.memory.add_note(data, user_id=self.current_user_id)
                self.voice.speak("I have saved it")

        elif intent == "recall":
            note = self._recall(query)
            if note:
                self.voice.speak(f"You told me: {note}")
            else:
                self.voice.speak("I don't remember anything yet")

        elif intent == "learn_command":
            self._learn_command()

        elif intent == "todo_add":
            self.todo.add_task(user_id=self.current_user_id)

        elif intent == "todo_show":
            self.todo.show_tasks(user_id=self.current_user_id)

        elif intent == "reminder_add":
            self.reminders.add_reminder(user_id=self.current_user_id)

        elif intent == "calculator":
            self.calculator.calculate(query)

        elif intent == "system_stats":
            self.system_utils.report_stats()

        elif intent == "screenshot":
            self.system_utils.take_screenshot()

        elif intent == "clipboard":
            self.system_utils.read_clipboard()

        elif intent == "greeting":
            self.voice.speak(random.choice(GREETINGS))

        elif intent == "daily_briefing":
            user_name = self.current_user["name"] if self.current_user else None
            self.briefing.give_briefing(user_id=self.current_user_id, user_name=user_name)

        elif intent == "thanks":
            self.voice.speak("You're welcome!")

        elif intent == "search":
            self.knowledge.answer(query)

        elif intent == "register_profile":
            user = self.profiles.register()
            if user:
                self.current_user = user

        elif intent == "login":
            user = self.profiles.login()
            if user:
                self.current_user = user

        elif intent == "logout":
            if self.current_user:
                self.voice.speak(f"Logged out. Bye, {self.current_user['name']}.")
                self.current_user = None
            else:
                self.voice.speak("You're not logged into a profile.")

        elif intent == "whoami":
            if self.current_user:
                self.voice.speak(f"You're logged in as {self.current_user['name']}.")
            else:
                self.voice.speak("You're using the guest profile. Say 'log in' or "
                                  "'create a profile' to use your own.")

        elif intent == "exit":
            self.voice.speak("Thank you. Goodbye")
            self.reminders.stop()
            raise SystemExit

        else:  # "unknown" — low confidence
            if self.last_sentiment["label"] == "negative":
                self.voice.speak(random.choice(FRUSTRATED_UNKNOWN_RESPONSES))
            else:
                self.voice.speak(random.choice(UNKNOWN_RESPONSES))

    # ---------------- HELPERS ----------------
    def _recall(self, query):
        """
        Smarter recall: if you mention a topic ("what did I say about
        my exam"), search for the most RELEVANT note using semantic
        memory search. If you just say "recall" with no topic, return
        the most recent note like before.
        """
        for marker in (" about ", " regarding ", " related to "):
            if marker in query:
                topic = query.split(marker, 1)[1].strip()
                if topic:
                    return self.semantic_memory.find_relevant_note(
                        topic, user_id=self.current_user_id
                    )
        return self.memory.get_latest_note(user_id=self.current_user_id)

    def _play_music(self):
        files = [f for f in os.listdir(config.MUSIC_DIR)
                 if f.lower().endswith((".mp3", ".wav"))]
        if not files:
            self.voice.speak(f"No music found. Add mp3 files to {config.MUSIC_DIR}")
            return
        track = os.path.join(config.MUSIC_DIR, random.choice(files))
        self.voice.speak("Playing music")
        os.startfile(track)  # Windows only; see README for cross-platform note

    def _learn_command(self):
        self.voice.speak("Say the trigger phrase")
        trigger = self.listener.listen()
        self.voice.speak("Say the action, for example: open notepad")
        action = self.listener.listen()

        if not trigger or not action:
            self.voice.speak("I didn't catch that, cancelling.")
            return

        resolved_action = self._resolve_safe_action(action)
        if resolved_action is None:
            self.voice.speak(
                "Sorry, that action isn't on my safe list, so I can't learn it."
            )
            return

        self.memory.teach_command(trigger, resolved_action)
        self.voice.speak("I have learned a new command")

    def _resolve_safe_action(self, action_text):
        """
        Safety measure: a learned command can ONLY resolve to one of the
        pre-approved apps in config.APPS. Arbitrary shell text is never
        accepted, even from voice input, so J can't be tricked into
        running something dangerous.
        """
        for app_name, shell_command in config.APPS.items():
            if app_name in action_text:
                return shell_command
        return None

    def _confirm(self, prompt_text):
        self.voice.speak(f"{prompt_text} Say yes or no.")
        answer = self.listener.listen()
        return "yes" in answer
