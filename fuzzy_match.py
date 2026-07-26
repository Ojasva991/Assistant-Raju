"""
fuzzy_match.py
Lightweight fuzzy text matching using Python's built-in `difflib` —
no extra pip install needed. This is what lets J recover from mic
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
    of short wake phrases (e.g. "hey j" transcribed as "aj") without
    needing an exact substring match.

    Very short aliases (<=3 characters, e.g. "j", "aj") are matched
    EXACTLY, not fuzzily — fuzzy similarity ratios on very short
    strings are unstable and cause false triggers (e.g. "day" or
    "may" scoring deceptively close to "j"/"jay"). Longer aliases
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
