"""
features/calculator.py
Spoken arithmetic: "what is fifteen plus twenty", "add three and four",
"subtract five from ten", "two plus three times four" (= 14).

Steps (kept separate so each one is easy to explain and to test):
  1. spoken_to_expression(): words -> a plain expression like "2+3*4".
  2. safe_eval(): evaluates it with Python's `ast` module. Only numbers,
     + - * / and brackets are allowed, so there is NO eval() and nothing
     else can ever run.
  3. format_number(): "14", not "14.0"; other numbers rounded to 4 decimals.
"""

import ast
import logging
import math
import operator
import re
from typing import List, Optional, Tuple, Union

from features.numbers import NUMBER_WORDS, SCALE_WORDS, words_to_number

log = logging.getLogger(__name__)

Number = Union[int, float]


class CalcError(Exception):
    """Something the user can fix. The message is safe to say out loud."""


# ---------------- step 1: words -> expression ----------------
_FILLER_START = {
    "what", "whats", "is", "the", "calculate", "compute", "calculator", "tell", "me",
    "how", "much", "can", "you", "please", "find", "answer", "to",
}
_FILLER_END = {"please", "equals", "equal", "is"}

# "add X and Y" style sentences become infix sentences. Each side is put in
# brackets so "multiply 2 plus 3 by 4" means (2+3)*4.
_REWRITES = [
    (re.compile(r"^add (.+?) and (.+)$"), r"( \1 ) plus ( \2 )"),
    (re.compile(r"^add (.+?) to (.+)$"), r"( \2 ) plus ( \1 )"),
    (re.compile(r"^subtract (.+?) from (.+)$"), r"( \2 ) minus ( \1 )"),  # Y minus X
    (re.compile(r"^multiply (.+?) by (.+)$"), r"( \1 ) times ( \2 )"),
    (re.compile(r"^divide (.+?) by (.+)$"), r"( \1 ) divided by ( \2 )"),
]
_SYMBOLS = {"+", "-", "*", "/", "(", ")"}
_WORD_OPS = {"plus": "+", "minus": "-", "times": "*", "x": "*"}
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _tokenize(text: str) -> List[str]:
    text = text.lower().replace("×", " * ").replace("÷", " / ")
    text = re.sub(r"[?!=]", " ", text)
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)         # 1,000 -> 1000
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)      # twenty-five
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)        # stray dots, not 2.5
    leftover = re.sub(r"[a-z0-9\s.+\-*/()]", "", text)
    if leftover:
        raise CalcError("I can only do simple arithmetic: plus, minus, times and divided by.")
    return re.findall(r"\d+(?:\.\d+)?|[a-z]+|[-+*/()]", text)


def _read_number_words(tokens: List[str], i: int) -> Tuple[Number, int]:
    """Reads a run of number words starting at i ("one hundred and five")."""
    j = i
    words: List[str] = []
    while j < len(tokens):
        word = tokens[j]
        next_word = tokens[j + 1] if j + 1 < len(tokens) else ""
        if word in NUMBER_WORDS:
            words.append(word)
        elif word in ("a", "an") and not words and next_word in SCALE_WORDS:
            words.append(word)  # "a hundred"
        elif (word == "and" and words and words[-1] in SCALE_WORDS
              and next_word in NUMBER_WORDS and next_word not in SCALE_WORDS):
            words.append(word)  # "one hundred AND five"
        else:
            break
        j += 1
    value = words_to_number(words)
    if value is None:
        raise CalcError(f"I didn't understand the number {' '.join(words)}.")
    return value, j


def spoken_to_expression(text: str) -> str:
    """'what is two plus three times four' -> '2+3*4'."""
    words = (text or "").lower().replace("'", "").split()  # what's -> whats
    while words and words[0] in _FILLER_START:
        words.pop(0)
    while words and words[-1] in _FILLER_END:
        words.pop()
    sentence = " ".join(words)
    if not sentence:
        raise CalcError("Tell me what to calculate, for example, fifteen plus twenty.")

    for pattern, replacement in _REWRITES:
        if pattern.match(sentence):
            sentence = pattern.sub(replacement, sentence)
            break

    tokens = _tokenize(sentence)
    out: List[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _SYMBOLS or _NUMBER.fullmatch(token):
            out.append(token)
            i += 1
        elif token in _WORD_OPS:
            out.append(_WORD_OPS[token])
            i += 1
        elif token in ("multiplied", "divided"):
            out.append("*" if token == "multiplied" else "/")
            i += 2 if i + 1 < len(tokens) and tokens[i + 1] == "by" else 1
        elif token in NUMBER_WORDS or token in ("a", "an"):
            value, i = _read_number_words(tokens, i)
            out.append(str(value))
        else:
            raise CalcError(f"I didn't understand the word {token} in that sum.")
    if not out:
        raise CalcError("I couldn't find any numbers in that.")
    return "".join(out)


# ---------------- step 2: safe evaluation ----------------
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> Number:
    # type(...) in (int, float) also rules out True/False, strings and complex numbers.
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval_node(node.operand))
    raise CalcError("I can only do simple arithmetic.")


def safe_eval(expression: str) -> Number:
    """Evaluates '2+3*4' without eval(). Anything but numbers, + - * / and
    brackets raises CalcError."""
    if len(expression) > 200:
        raise CalcError("That sum is too long for me.")
    try:
        tree = ast.parse(expression, mode="eval")
        return _eval_node(tree.body)
    except ZeroDivisionError:
        raise CalcError("You can't divide by zero.")
    except (SyntaxError, RecursionError):
        raise CalcError("I couldn't understand that sum.")
    except OverflowError:
        raise CalcError("That number is too big for me.")


# ---------------- step 3: nice output ----------------
def format_number(value: Number) -> str:
    """14.0 -> '14'; 3.33333 -> '3.3333'; -0.00001 -> '0'."""
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise CalcError("That number is too big for me.")
    rounded = round(value, 4)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.4f}".rstrip("0").rstrip(".")


def evaluate(text: str) -> str:
    """Spoken sentence in, formatted answer out ('35'). Raises CalcError."""
    return format_number(safe_eval(spoken_to_expression(text)))


class CalculatorFeature:
    def __init__(self, voice):
        self.voice = voice

    def calculate(self, text: str) -> Optional[str]:
        """text is the recognized sentence, e.g. 'what is fifteen plus twenty'.
        Speaks the answer and also returns it (None if it failed)."""
        try:
            answer = evaluate(text)
        except CalcError as e:
            self.voice.speak(str(e))
            return None
        spoken = f"minus {answer[1:]}" if answer.startswith("-") else answer
        self.voice.speak(f"The answer is {spoken}")
        return answer
