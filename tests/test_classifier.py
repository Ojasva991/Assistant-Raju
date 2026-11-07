"""
Tests for section A (intent classifier).
No microphone, speakers or internet needed.
Run:  python -m pytest tests -q
"""

import numpy as np
import pytest

import config
import intent_classifier as ic
from intent_classifier import IntentClassifier


@pytest.fixture(scope="module")
def clf():
    # Trained once for the whole file: training takes a moment.
    return IntentClassifier()


# ---------------- text cleaning ----------------
def test_numbers_look_the_same_after_masking():
    a = ic.normalize_text("What is fifteen plus twenty?")
    b = ic.normalize_text("what is 12 plus 7")
    assert a == b == "what is num plus num"


def test_neighbouring_number_words_become_one_token():
    assert ic.normalize_text("what is one hundred twenty plus 3") == "what is num plus num"


def test_punctuation_and_case_are_removed():
    assert ic.clean_text("OPEN NOTEPAD!") == "open notepad"
    assert ic.clean_text("What's the time?") == "whats the time"


def test_decimal_numbers_survive_cleaning():
    assert ic.clean_text("what is 3.5 plus 2") == "what is 3.5 plus 2"


# ---------------- training data ----------------
def test_training_data_has_27_intents_including_unknown():
    clean, masked, labels = ic.load_training_data()
    assert len(set(labels)) == 27
    assert "unknown" in labels
    assert len(clean) == len(masked) == len(labels)


def test_no_duplicate_or_conflicting_sentences():
    _, masked, labels = ic.load_training_data()
    pairs = list(zip(masked, labels))
    assert len(pairs) == len(set(pairs))              # no duplicates
    assert len(set(masked)) == len(masked)            # same text never has two labels


# ---------------- the "done when" sentences from the spec ----------------
@pytest.mark.parametrize("sentence, expected", [
    ("exit", "exit"),
    ("stop raju", "exit"),
    ("take screenshot", "screenshot"),
    ("take a screenshot", "screenshot"),
    ("what is the weather today", "unknown"),
])
def test_spec_sentences(clf, sentence, expected):
    assert clf.predict(sentence)[0] == expected


@pytest.mark.parametrize("sentence, expected", [
    ("Exit!", "exit"),
    ("STOP RAJU", "exit"),
    ("goodbye raju", "exit"),
    ("how much ram do i have", "system_stats"),
    ("what is the battery level", "system_stats"),
    ("read my clipboard", "clipboard"),
    ("thank you so much", "thanks"),
])
def test_rules_work_with_different_wording(clf, sentence, expected):
    intent, confidence = clf.predict(sentence)
    assert intent == expected
    assert confidence == 1.0           # rules always return confidence 1.0


def test_thanks_rule_does_not_swallow_a_real_command():
    # "thanks" followed by a command must go to the model, not the rule
    assert ic.match_rule("thanks, add a task") is None


def test_every_rule_is_correct_on_all_training_sentences():
    # A rule must never fire with the wrong intent on any training sentence.
    clean, _, labels = ic.load_training_data()
    for sentence, label in zip(clean, labels):
        rule = ic.match_rule(sentence)
        if rule is not None:
            assert rule == label, f"rule {rule!r} wrongly fired on {sentence!r} ({label})"


# ---------------- model + threshold ----------------
def test_normal_commands_still_reach_the_model(clf):
    assert clf.predict("OPEN NOTEPAD!")[0] == "open_app"
    assert clf.predict("what is 9 times 9")[0] == "calculator"
    assert clf.predict("remind me in fifteen minutes")[0] == "reminder_add"


def test_empty_and_gibberish_give_unknown(clf):
    assert clf.predict("") == ("unknown", 0.0)
    assert clf.predict("   !!!  ")[0] == "unknown"
    assert clf.predict("flibber jabber wocky")[0] == "unknown"


def test_low_confidence_becomes_unknown():
    # A threshold of 0.99 is so strict that the model should reject a model-only sentence.
    strict = IntentClassifier(threshold=0.99)
    intent, confidence = strict.predict("what is the current time")
    assert intent == "unknown"
    assert confidence < 0.99


def test_predict_returns_plain_python_types(clf):
    intent, confidence = clf.predict("open youtube")
    assert isinstance(intent, str) and isinstance(confidence, float)


# ---------------- accuracy (cross-validation) ----------------
def test_cross_validated_accuracy_is_far_above_the_old_model():
    """Honest check: every sentence is predicted by a model that never saw it.
    The old model scored 61.7% (one small split) / about 61% (same CV method)."""
    _, masked, labels = ic.load_training_data()
    pred, _ = ic.cv_predict(config.MODEL_NAME, masked, labels, folds=5, seed=0)
    accuracy = float((pred == np.array(labels)).mean())
    assert accuracy > 0.75


def test_chosen_model_is_not_worse_than_old_naive_bayes():
    _, masked, labels = ic.load_training_data()
    y = np.array(labels)
    old, _ = ic.cv_predict("naive_bayes", masked, labels, folds=5, seed=0)
    new, _ = ic.cv_predict(config.MODEL_NAME, masked, labels, folds=5, seed=0)
    assert (new == y).mean() >= (old == y).mean()


def test_train_and_report_prints_numbers(capsys):
    small = IntentClassifier()
    original = (config.CV_REPEATS,)
    config.CV_REPEATS = 1          # keep the test fast
    try:
        accuracy = small.train_and_report()
    finally:
        config.CV_REPEATS = original[0]
    out = capsys.readouterr().out
    assert "Logistic Regression" in out and "LinearSVC" in out and "Naive Bayes" in out
    assert 0.5 < accuracy <= 1.0
