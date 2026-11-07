"""
features/user_profile.py
Lets several people share one Raju installation while keeping separate
memory (notes, todos, reminders, prefs) per person.

PIN safety (spec section C):
  - The PIN is never stored. Only a salted PBKDF2 hash is saved.
  - Login needs an EXACT match (no fuzzy matching: "1235" is not "1234").
  - Spoken digits become digits ("one two three four" -> "1234").
  - After 3 wrong PINs in a row, login is locked for 60 seconds.
It is still a convenience feature to separate profiles on one PC, not
protection for sensitive data: anyone with the PC and the database file
can try to guess a short PIN offline.
"""

import hashlib
import hmac
import logging
import math
import os
import re
import time
from typing import Callable, Dict, List, Optional

import config
from features.numbers import NUMBER_WORDS, words_to_number
from listener import hear_answer, why_nothing_heard

log = logging.getLogger(__name__)

DIGIT_WORDS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
# Google often writes a spoken digit as the word that sounds the same.
# Only used when the phrase also has a real digit ("seven to eight six").
HOMOPHONES = {"to": "2", "too": "2", "for": "4", "won": "1", "ate": "8"}
# Things people say before the PIN or the name ("my pin is ...", "my name is ...").
_PIN_PREFIX = re.compile(r"^(?:(?:my|the) )?(?:pin|password|code)(?: is)? |^(?:it is|its|it s) ")
_NAME_PREFIX = re.compile(r"^(?:my name is|my name s|i am|i m|this is|it is|its|it s) ")
_HASH_NAME = "pbkdf2_sha256"
# Old versions saved "one two three four" as "onetwothreefour" (spaces removed).
_LEGACY_DIGIT_WORDS = re.compile("(?:" + "|".join(DIGIT_WORDS) + ")+")


# ---------------- PIN helpers (pure functions, easy to test) ----------------
def normalize_pin(text: str) -> str:
    """'1 2 3 4', '1234' and 'one two three four' all become '1234'.
    Digit words are converted ONLY when every word is a digit or a digit
    word; a word PIN like 'blue sky' just loses its spaces ('bluesky').
    Also understood: 'my pin is 1234', 'seven to eight six', 'seven thousand two
    hundred eighty six'. Login and register use this same function, so they agree."""
    cleaned = " ".join(re.sub(r"[\W_]+", " ", (text or "").lower()).split())
    words = _PIN_PREFIX.sub("", cleaned).split()
    if not words:
        return ""
    # "7,286" arrives as "7 286"; "seven to eight six" has a homophone for two.
    if (all(w in DIGIT_WORDS or w in HOMOPHONES or w.isdigit() for w in words)
            and any(w in DIGIT_WORDS or w.isdigit() for w in words)):
        return "".join(DIGIT_WORDS.get(w) or HOMOPHONES.get(w) or w for w in words)
    # "seven thousand two hundred eighty six" -> 7286
    if all(w in NUMBER_WORDS or w == "and" for w in words):
        value = words_to_number(words)
        if isinstance(value, int):
            return str(value)
    return "".join(words)


def hash_pin(pin: str) -> str:
    """Returns 'pbkdf2_sha256$iterations$salt$hash'. A new random salt is
    used each time, so two users with the same PIN get different hashes."""
    iterations = config.PIN_HASH_ITERATIONS
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return f"{_HASH_NAME}${iterations}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Compares in constant time (hmac.compare_digest), so the time taken
    does not reveal how many characters were right."""
    try:
        name, iterations, salt_hex, digest_hex = stored.split("$")
        if name != _HASH_NAME:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except ValueError:  # empty or damaged hash: never a match
        return False


def _legacy_to_new_pin(old_pin: str) -> str:
    """Old plain PINs were stored with spaces removed. If one is made only of
    digit words ('onetwothreefour'), convert it so the new spoken-digit
    login ('1 2 3 4') still works for that user."""
    old_pin = (old_pin or "").strip().lower()
    if _LEGACY_DIGIT_WORDS.fullmatch(old_pin):
        return "".join(DIGIT_WORDS[w] for w in re.findall("|".join(DIGIT_WORDS), old_pin))
    return old_pin


class UserProfileFeature:
    def __init__(self, memory, voice, listener, clock: Callable[[], float] = time.monotonic):
        self.memory = memory
        self.voice = voice
        self.listener = listener
        self._clock = clock          # tests pass a fake clock
        self._failed = 0             # wrong PINs in a row
        self._locked_until = 0.0
        self.migrate_plain_pins()

    # ---------------- migration ----------------
    def migrate_plain_pins(self) -> int:
        """Turns old plain-text PINs into hashes and blanks the old column.
        Runs at every start; does nothing when there is nothing to migrate."""
        migrated = 0
        for row in self.memory.get_users_with_plain_pin():
            self.memory.set_pin_hash(row["id"], hash_pin(_legacy_to_new_pin(row["pin"])))
            migrated += 1
        if migrated:
            log.info("Migrated %d plain-text PIN(s) to salted hashes", migrated)
        return migrated

    # ---------------- lockout ----------------
    def lock_seconds_left(self) -> int:
        return max(0, math.ceil(self._locked_until - self._clock()))

    def _register_wrong_pin(self) -> bool:
        """Counts a wrong PIN. Returns True if login is now locked."""
        self._failed += 1
        if self._failed >= config.PIN_MAX_ATTEMPTS:
            self._failed = 0
            self._locked_until = self._clock() + config.PIN_LOCK_SECONDS
            log.warning("Login locked for %s seconds after wrong PINs", config.PIN_LOCK_SECONDS)
            return True
        return False

    def _speak_locked(self) -> None:
        self.voice.speak(f"Too many wrong PINs. Please wait "
                         f"{self.lock_seconds_left()} seconds and try again.")

    def _find_user(self, pin: str, users: List[Dict]) -> Optional[Dict]:
        for user in users:
            if verify_pin(pin, user.get("pin_hash", "")):
                return user
        return None

    def _ask(self, again: str, secret: bool = False) -> str:
        """Hears an answer; if nothing came, says WHY and asks once more."""
        for attempt in range(2):
            text = hear_answer(self.listener, secret=secret)
            if text:
                return text
            if attempt == 0:
                self.voice.speak(f"{why_nothing_heard(self.listener)} {again}")
        return ""

    # ---------------- register ----------------
    def register(self) -> Optional[Dict]:
        """Creates a new profile. Returns {'id', 'name'}, or None if cancelled."""
        if self.lock_seconds_left():
            self._speak_locked()
            return None

        self.voice.speak("What's your name?")
        name = _NAME_PREFIX.sub("", " ".join((self._ask("Please say your name again.") or "").lower().split())).title()
        if not name:
            self.voice.speak("I didn't catch that, cancelling.")
            return None

        self.voice.speak(f"Choose a PIN with at least {config.PIN_MIN_LENGTH} digits "
                         "or letters. Say it now.")
        pin = normalize_pin(self._ask("Please say your PIN again.", secret=True))
        if not pin:
            self.voice.speak("I didn't catch a PIN, cancelling.")
            return None
        if len(pin) < config.PIN_MIN_LENGTH:
            self.voice.speak(f"That PIN is too short. It needs at least "
                             f"{config.PIN_MIN_LENGTH} characters. Please start again.")
            return None

        # Say it twice: a misheard PIN would lock the user out of their own profile.
        self.voice.speak("Please say the PIN once more to confirm.")
        if normalize_pin(hear_answer(self.listener, secret=True)) != pin:
            self.voice.speak("The two PINs did not match, so no profile was created. "
                             "Please try again.")
            return None

        if self._find_user(pin, self.memory.get_all_users()):
            # The message does not say WHICH user has it. A rejected PIN also
            # counts as a wrong attempt, so this cannot be used to guess PINs.
            self._register_wrong_pin()
            self.voice.speak("I can't use that PIN. Please start again with a different one.")
            return None

        user_id = self.memory.add_user(name, hash_pin(pin))
        self.voice.speak(f"Profile created. Welcome, {name}.")
        return {"id": user_id, "name": name}

    # ---------------- login ----------------
    def login(self) -> Optional[Dict]:
        """Asks for a PIN. Exact match only. Returns {'id', 'name'} or None."""
        if self.lock_seconds_left():
            self._speak_locked()
            return None

        users = self.memory.get_all_users()
        if not users:
            self.voice.speak("There are no profiles yet. Say 'create a profile' first.")
            return None

        self.voice.speak("Please say your PIN to log in.")
        first_try = True
        while True:
            # After a wrong PIN Raju listens again, so you do not have to say "log in" again.
            heard = (self._ask("Please say your PIN again.", secret=True) if first_try
                     else hear_answer(self.listener, secret=True))
            if not heard:
                # Silence is not a wrong PIN, so it costs no try.
                self.voice.speak("I didn't catch that." if first_try else
                                 "Okay, login cancelled. Say log in to try again.")
                return None
            first_try = False

            user = self._find_user(normalize_pin(heard), users)
            if user:
                self._failed = 0
                self.voice.speak(f"Welcome back, {user['name']}.")
                return {"id": user["id"], "name": user["name"]}

            if self._register_wrong_pin():
                self.voice.speak(f"Sorry, that PIN is not right. Login is locked for "
                                 f"{config.PIN_LOCK_SECONDS} seconds.")
                return None
            left = config.PIN_MAX_ATTEMPTS - self._failed
            self.voice.speak(f"Sorry, that PIN is not right. {left} "
                             f"{'try' if left == 1 else 'tries'} left. Say it again.")
