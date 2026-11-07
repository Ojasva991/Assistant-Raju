"""
features/numbers.py
Turns English number words into a number: "twenty five" -> 25,
"one hundred and five" -> 105, "two point five" -> 2.5.

Why not just use the word2number package? I tested it: it accepts nonsense
without complaint ("five six" -> 11, "ten ten" -> 20, "a hundred five" -> 500).
For a calculator and for reminders a wrong answer is worse than "I did not
understand", so this small parser checks the grammar and returns None for
anything that is not a real English number.
"""

from typing import List, Optional, Union

Number = Union[int, float]

_ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine".split())}
_TEENS = {w: 10 + i for i, w in enumerate(
    "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}

# Words that can be part of a number (used by callers to find a run of words).
NUMBER_WORDS = (set(_ONES) | set(_TEENS) | set(_TENS) | set(_SCALES)
                | {"hundred", "point"})
SCALE_WORDS = set(_SCALES) | {"hundred"}


def words_to_number(words: List[str]) -> Optional[Number]:
    """Returns the number, or None if the words are not a valid number."""
    words = [w for w in words if w]
    if not words:
        return None

    # Decimal part: everything after "point" must be single digit words.
    if "point" in words:
        index = words.index("point")
        whole_words, decimal_words = words[:index], words[index + 1:]
        if not whole_words or not decimal_words or "point" in decimal_words:
            return None
        if any(w not in _ONES for w in decimal_words):
            return None
        whole = words_to_number(whole_words)
        if whole is None or isinstance(whole, float):
            return None
        digits = "".join(str(_ONES[w]) for w in decimal_words)
        return float(f"{whole}.{digits}")

    if words == ["zero"]:
        return 0
    if "zero" in words:
        return None  # "zero" only makes sense alone (or after "point")

    # "a hundred" / "a thousand": 'a' only works as the first word.
    if words[0] in ("a", "an"):
        if len(words) < 2 or words[1] not in SCALE_WORDS:
            return None
        words = ["one"] + words[1:]

    total = 0        # finished groups, for example the "3,000" in 3,250
    current = 0      # the group being built, always below 1000
    last_scale = None
    previous = None
    for i, word in enumerate(words):
        if word == "and":
            # "one hundred and five": only after hundred or a scale word,
            # and a number below one hundred must follow.
            if previous not in SCALE_WORDS or i + 1 >= len(words):
                return None
            if words[i + 1] not in _ONES and words[i + 1] not in _TEENS and words[i + 1] not in _TENS:
                return None
        elif word in _ONES:
            # 1-9 may follow nothing, "hundred", or a tens word ("twenty five").
            if not (current % 100 == 0 or (current % 100 >= 20 and current % 10 == 0)):
                return None
            current += _ONES[word]
        elif word in _TEENS:
            if current % 100 != 0:
                return None
            current += _TEENS[word]
        elif word in _TENS:
            if current % 100 != 0:
                return None
            current += _TENS[word]
        elif word == "hundred":
            if not 1 <= current <= 9:
                return None
            current *= 100
        elif word in _SCALES:
            scale = _SCALES[word]
            if current == 0 or (last_scale is not None and scale >= last_scale):
                return None
            total += current * scale
            current = 0
            last_scale = scale
        else:
            return None
        previous = word
    return total + current
