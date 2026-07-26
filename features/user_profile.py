"""
features/user_profile.py
Lets multiple people share one J installation while keeping separate
memory (notes, todos, reminders, prefs) per person.

Security note: this is a convenience feature for a personal/hobby
project, NOT real security. The PIN is stored as plain text and
compared with fuzzy matching (since speech recognition isn't
perfectly reliable) — anyone who can talk to J can guess a short PIN.
Don't use this for anything sensitive.
"""

import re
import difflib


def _normalize(text):
    """'one two three four' and '1234' should be treated as the same PIN."""
    return re.sub(r"\s+", "", text.lower().strip())


class UserProfileFeature:
    def __init__(self, memory, voice, listener):
        self.memory = memory
        self.voice = voice
        self.listener = listener

    def register(self):
        """Creates a new profile. Returns the new user dict, or None if cancelled."""
        self.voice.speak("What's your name?")
        name = self.listener.listen()
        if not name:
            self.voice.speak("I didn't catch that, cancelling.")
            return None

        self.voice.speak("Choose a short PIN, like a few numbers or a word. Say it now.")
        pin_raw = self.listener.listen()
        if not pin_raw:
            self.voice.speak("I didn't catch a PIN, cancelling.")
            return None

        pin = _normalize(pin_raw)
        user_id = self.memory.add_user(name.strip(), pin)
        self.voice.speak(f"Profile created. Welcome, {name}.")
        return {"id": user_id, "name": name.strip(), "pin": pin}

    def login(self):
        """Asks for a PIN and matches it against existing profiles (fuzzy,
        since speech recognition can mangle short PIN phrases). Returns
        the matched user dict, or None if no confident match."""
        self.voice.speak("Please say your PIN to log in.")
        heard = self.listener.listen()
        if not heard:
            self.voice.speak("I didn't catch that.")
            return None

        heard_normalized = _normalize(heard)
        users = self.memory.get_all_users()
        if not users:
            self.voice.speak("There are no profiles yet. Say 'create a profile' first.")
            return None

        # exact match first
        for u in users:
            if u["pin"] == heard_normalized:
                self.voice.speak(f"Welcome back, {u['name']}.")
                return u

        # fuzzy fallback for mic mishearings
        pins = [u["pin"] for u in users]
        close = difflib.get_close_matches(heard_normalized, pins, n=1, cutoff=0.7)
        if close:
            matched_pin = close[0]
            user = next(u for u in users if u["pin"] == matched_pin)
            self.voice.speak(f"Welcome back, {user['name']}.")
            return user

        self.voice.speak("Sorry, I didn't recognize that PIN.")
        return None
