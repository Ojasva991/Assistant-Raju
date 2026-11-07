"""Tests for section E: the safe calculator. No microphone, no eval."""

import ast
import json
import os

import pytest

import config
from features import calculator
from features.calculator import CalcError, CalculatorFeature, evaluate, format_number, safe_eval
from features.numbers import words_to_number


class FakeVoice:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


# The 20 training sentences and the answers they must give.
TRAINING_ANSWERS = {
    "what is fifteen plus twenty": "35",
    "calculate two plus two": "4",
    "what is ten times five": "50",
    "add three and four": "7",
    "what is 100 divided by 4": "25",
    "subtract five from ten": "5",
    "what is 12 plus 7": "19",
    "calculate 15 times 3": "45",
    "what is nine minus four": "5",
    "calculate 50 divided by 5": "10",
    "what is twenty times two": "40",
    "what is 8 multiplied by 6": "48",
    "add 12 and 30": "42",
    "what is seventy minus twenty": "50",
    "calculate thirty plus forty": "70",
    "what is 144 divided by 12": "12",
    "multiply six by seven": "42",
    "what's five plus five": "10",
    "calculate one hundred minus ninety": "10",
    "what is sixteen divided by four": "4",
}


def test_expected_answers_cover_every_training_sentence():
    # If someone edits training_data.json, this test says the answers need updating.
    with open(config.TRAINING_DATA_PATH, encoding="utf-8") as f:
        sentences = set(json.load(f)["calculator"])
    assert sentences == set(TRAINING_ANSWERS)


@pytest.mark.parametrize("sentence, answer", sorted(TRAINING_ANSWERS.items()))
def test_training_sentences(sentence, answer):
    assert evaluate(sentence) == answer


@pytest.mark.parametrize("sentence, answer", [
    ("two plus three times four", "14"),            # precedence: times first
    ("two times three plus four", "10"),
    ("ten minus two minus three", "5"),             # left to right
    ("subtract 3 from 10", "7"),                    # Y minus X, not X minus Y
    ("subtract two plus one from ten", "7"),        # brackets around the subtracted part
    ("add 3 to 4", "7"),
    ("add one hundred and five and six", None),     # too confusing: must not guess
    ("what is 12 + 7", "19"),                       # symbols work too
    ("6 x 7", "42"),
    ("6 * 7", "42"),
    ("100 / 4", "25"),
    ("10 - 3", "7"),
    ("divide ten by three", "3.3333"),              # 4 decimals
    ("what is one divided by eight", "0.125"),
    ("0.1 plus 0.2", "0.3"),                        # no 0.30000000000000004
    ("two point five times four", "10"),            # 10.0 is spoken as 10
    ("what is twenty-five plus one", "26"),
    ("1,000 plus 5", "1005"),
    ("minus five plus ten", "5"),
    ("five times minus three", "-15"),
    ("what is one hundred and five minus five", "100"),
    ("calculate three plus four please", "7"),
])
def test_more_sentences(sentence, answer):
    if answer is None:
        with pytest.raises(CalcError):
            evaluate(sentence)
    else:
        assert evaluate(sentence) == answer


def test_divide_by_zero_is_polite():
    voice = FakeVoice()
    assert CalculatorFeature(voice).calculate("what is ten divided by zero") is None
    assert "divide by zero" in voice.said[-1]


def test_negative_answer_is_spoken_as_minus():
    voice = FakeVoice()
    assert CalculatorFeature(voice).calculate("three minus five") == "-2"
    assert voice.said[-1] == "The answer is minus 2"


def test_answer_is_spoken():
    voice = FakeVoice()
    CalculatorFeature(voice).calculate("what is fifteen plus twenty")
    assert voice.said == ["The answer is 35"]


@pytest.mark.parametrize("sentence", [
    "",
    "what is",
    "five six plus one",             # not a real number
    "what is 10 percent of 5",      # unknown word
    "banana plus apple",
    "plus",
    "( )",
])
def test_bad_input_gives_a_spoken_reason_not_a_crash(sentence):
    voice = FakeVoice()
    assert CalculatorFeature(voice).calculate(sentence) is None
    assert voice.said and "answer is" not in voice.said[0]


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo hi')",
    "open('x')",
    "2 ** 9",
    "2 // 3",
    "2 % 3",
    "'a' * 3",
    "True + 1",
    "1 if 1 else 2",
    "[1, 2]",
    "(lambda: 1)()",
    "abs(-1)",
    "1 < 2",
])
def test_safe_eval_refuses_anything_but_plain_arithmetic(expression):
    with pytest.raises(CalcError):
        safe_eval(expression)


def test_spoken_text_cannot_run_code():
    # Even if speech recognition produced code-like text, nothing runs.
    for text in ["__import__('os').system('echo hi')", "what is open('x')", "1; import os"]:
        with pytest.raises(CalcError):
            evaluate(text)


def test_source_has_no_builtin_eval_or_exec():
    # Looks at the real code (ast), so a mention in a comment or docstring is fine.
    path = os.path.join(os.path.dirname(calculator.__file__), "calculator.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not called & {"eval", "exec", "compile", "__import__"}


def test_very_long_input_is_refused():
    with pytest.raises(CalcError):
        safe_eval("1+" * 150 + "1")


def test_huge_result_does_not_crash():
    with pytest.raises(CalcError):
        safe_eval("1" + "0" * 400 + "/3")  # int too large for float division


@pytest.mark.parametrize("value, text", [
    (14, "14"), (14.0, "14"), (2.5, "2.5"), (3.33333, "3.3333"),
    (-0.00001, "0"), (-2.0, "-2"), (0.1 + 0.2, "0.3"), (1e20, "100000000000000000000"),
])
def test_format_number(value, text):
    assert format_number(value) == text


def test_format_number_refuses_infinity():
    with pytest.raises(CalcError):
        format_number(float("inf"))


# ---------------- the number-word parser ----------------
@pytest.mark.parametrize("words, value", [
    ("zero", 0), ("ten", 10), ("nineteen", 19), ("twenty five", 25),
    ("one hundred and five", 105), ("a hundred", 100), ("one thousand two hundred", 1200),
    ("two million three hundred thousand", 2300000), ("three thousand and four", 3004),
    ("two point five", 2.5), ("zero point zero five", 0.05),
])
def test_words_to_number(words, value):
    assert words_to_number(words.split()) == value


@pytest.mark.parametrize("words", [
    "", "five six", "ten ten", "twenty twenty", "hundred", "zero five", "five point",
    "point five", "twelve five", "one million one million", "banana", "one and",
])
def test_words_to_number_refuses_nonsense(words):
    # The word2number package answers 11 for "five six"; this parser must not.
    assert words_to_number(words.split()) is None
