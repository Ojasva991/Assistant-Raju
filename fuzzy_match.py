"""
fuzzy_match.py
Lightweight fuzzy text matching using Python's built-in `difflib` —
no extra pip install needed. This is what lets Raju recover from mic
mishearings like "opne notepad" or "open note pad" instead of just
giving up because the text isn't an exact match.

How it works: difflib.get_close_matches compares the input string
against a list of known-good phrases and scores similarity from 0
(nothing alike) to 1 (identical). We only accept a match if it's
above `cutoff`, so unrelated commands don't get wrongly matched.
"""

import difflib


def best_match(text, candidates, cutoff=0.72):
    """
    Returns the closest string from `candidates` that's similar enough
    to `text`, or None if nothing clears the cutoff.
    """
    if not text or not candidates:
        return None
    matches = difflib.get_close_matches(text, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def find_wake_word(heard, wake_phrases, cutoff=0.6):
    """
    Slides a window across `heard` looking for anything close enough to
    one of `wake_phrases`. This catches speech-recognition mishearings
    of short wake phrases (e.g. "raju" transcribed as "raj") without
    needing an exact substring match.

    Very short aliases (<=3 characters, e.g. "raj") are matched
    EXACTLY, not fuzzily — fuzzy similarity ratios on very short
    strings are unstable and cause false triggers (e.g. "day" or
    "may" scoring deceptively close to a short alias). Longer aliases
    still use fuzzy matching to tolerate real mishearings.

    Returns the remaining text AFTER the wake phrase (e.g. "open
    notepad" from "hii j open notepad"), or None if no wake phrase
    was found. Returns "" (empty string, not None) if the wake word
    was heard with nothing after it.
    """
    if not heard:
        return None

    words = heard.split()
    best_ratio = 0
    best_remainder = None

    for phrase in wake_phrases:
        phrase_len = len(phrase.split())
        exact_only = len(phrase) <= 3

        for i in range(len(words) - phrase_len + 1):
            window = " ".join(words[i:i + phrase_len])

            if exact_only:
                ratio = 1.0 if window == phrase else 0.0
            else:
                ratio = difflib.SequenceMatcher(None, window, phrase).ratio()

            if ratio > best_ratio:
                best_ratio = ratio
                best_remainder = " ".join(words[i + phrase_len:])

    if best_ratio >= cutoff:
        return best_remainder
    return None


def find_known_name(text, names, cutoff=0.72, fuzzy=True):
    """
    Finds which known name (an app or a website) is mentioned inside a
    sentence, e.g. "open notepad please" -> "notepad".

    Step 1: whole-word match. The longest name wins, so "command prompt"
            beats a shorter name that is part of it.
    Step 2 (only if fuzzy=True): compare every group of 1-3 neighbouring
            words with each name. This repairs mishearings such as
            "opne" or "note pad" (two words that should be "notepad").

    Returns the name from `names`, or None.
    """
    if not text or not names:
        return None

    padded = f" {text} "
    exact = [n for n in names if f" {n} " in padded]
    if exact:
        return max(exact, key=len)
    if not fuzzy:
        return None

    words = text.split()
    best_name, best_ratio = None, 0.0
    for name in names:
        size = len(name.split())
        for width in range(max(1, size - 1), size + 2):
            for i in range(len(words) - width + 1):
                window = " ".join(words[i:i + width])
                ratio = difflib.SequenceMatcher(None, window, name).ratio()
                if ratio > best_ratio:
                    best_name, best_ratio = name, ratio
    return best_name if best_ratio >= cutoff else None
