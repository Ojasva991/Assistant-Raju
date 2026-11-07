"""
intent_classifier.py
The "AI" part of Raju: maps a sentence to an intent.

How a sentence is handled (in this order):
  1. Clean it: lowercase, no punctuation.
  2. Rule table: a few exact patterns ("exit", "take a screenshot", ...)
     that must ALWAYS work. They return confidence 1.0.
  3. ML model: numbers are replaced by the token "num" so "fifteen plus
     twenty" and "12 plus 7" look the same, then the model predicts.
  4. If the model is not confident enough, or says "unknown", the
     result is "unknown" and the assistant asks the user to rephrase.

Training sentences live in training_data.json (not in the code).
The model is chosen by cross-validation, not by one lucky split.
Run `python intent_classifier.py` to see all the numbers.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.svm import LinearSVC

import config

log = logging.getLogger(__name__)

UNKNOWN = "unknown"

# ---------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------
_NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
    "thirty forty fifty sixty seventy eighty ninety hundred thousand".split()
)
_DIGITS = re.compile(r"\d+(\.\d+)?")


def clean_text(text: str) -> str:
    """Lowercase, remove punctuation. Numbers are kept as they are."""
    text = text.lower().replace("'", "").replace("-", " ")
    text = re.sub(r"[^a-z0-9. ]", " ", text)
    # keep a dot only inside a number like 3.5; drop all other dots
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)
    return " ".join(text.split())


def mask_numbers(clean: str) -> str:
    """Replace digits and number words with 'num'.
    Neighbouring numbers become ONE token ("one hundred twenty" -> "num"),
    so the model sees the same shape for any number."""
    out: List[str] = []
    for word in clean.split():
        if _DIGITS.fullmatch(word) or word in _NUMBER_WORDS:
            if not out or out[-1] != "num":
                out.append("num")
        else:
            out.append(word)
    return " ".join(out)


def normalize_text(text: str, numbers: bool = True) -> str:
    """Full preprocessing used for the model. numbers=False keeps the
    real numbers (the rule table does not need the mask)."""
    clean = clean_text(text)
    return mask_numbers(clean) if numbers else clean


# ---------------------------------------------------------------------
# Rule table: high-precision patterns checked BEFORE the model.
# Each pattern must match the WHOLE cleaned sentence (fullmatch), so a
# rule only fires when the sentence is clearly that command.
# ---------------------------------------------------------------------
_RAJU = r"(?:raju )?"
RULES = [(intent, re.compile(p)) for intent, p in [
    # exit / quit / stop raju / goodbye
    ("exit", _RAJU + r"(?:please )?(?:exit|quit|goodbye|good bye|bye)"
                     r"(?: (?:the )?(?:assistant|raju|app))?(?: please)?"),
    ("exit", _RAJU + r"stop (?:raju|the assistant|assistant|listening)"),
    # screenshot (any sentence that contains the word)
    ("screenshot", r".*\b(?:screenshot|screen shot|screen capture|capture (?:the |my )?screen)\b.*"),
    # clipboard
    ("clipboard", r".*\bclipboard\b.*"),
    ("clipboard", r"what did i (?:just )?copy"),
    # system stats: battery / cpu / ram as whole words
    ("system_stats", r".*\b(?:battery|cpu|ram)\b.*"),
    # thanks: only short thank-you sentences, so "thanks, add a task" is not caught
    ("thanks", _RAJU + r"(?:thanks|thank you|thankyou|cheers|much appreciated|appreciate it)"
                       r"(?: (?:so|very) much| a lot| raju| again)*"),
]]


def match_rule(text: str) -> Optional[str]:
    """Returns an intent if a rule matches the whole sentence, else None."""
    clean = clean_text(text)
    for intent, pattern in RULES:
        if pattern.fullmatch(clean):
            return intent
    return None


# ---------------------------------------------------------------------
# Training data
# ---------------------------------------------------------------------
def load_training_data(path: Optional[str] = None) -> Tuple[List[str], List[str], List[str]]:
    """
    Reads training_data.json and returns (clean, masked, labels).
      clean  = cleaned sentence (used by the rule table check)
      masked = same sentence with numbers replaced by 'num' (used by the model)
    Sentences that become identical after masking are kept only once.
    Why: "what is 12 plus 7" and "what is 5 plus 5" are the same to the
    model, and duplicates would leak between train and test folds and
    make cross-validation look better than it is.
    """
    path = path or config.TRAINING_DATA_PATH
    with open(path, "r", encoding="utf-8") as f:
        data: Dict[str, List[str]] = json.load(f)

    seen = set()
    clean_list: List[str] = []
    masked_list: List[str] = []
    labels: List[str] = []
    for intent in sorted(data):
        for sentence in data[intent]:
            clean = clean_text(sentence)
            masked = mask_numbers(clean)
            if (masked, intent) in seen:
                continue
            seen.add((masked, intent))
            clean_list.append(clean)
            masked_list.append(masked)
            labels.append(intent)
    return clean_list, masked_list, labels


# ---------------------------------------------------------------------
# Models (all give real probabilities, so "confidence" means the same thing)
# ---------------------------------------------------------------------
MODEL_NAMES = ("naive_bayes", "logreg", "linear_svc")

MODEL_DESCRIPTIONS = {
    "naive_bayes": "Naive Bayes on word counts (the old model)",
    "logreg": "TF-IDF (1-2 word pairs) + Logistic Regression",
    "linear_svc": "TF-IDF (1-2 word pairs) + LinearSVC (probability-calibrated)",
}


def build_model(name: str) -> Pipeline:
    if name == "naive_bayes":
        return make_pipeline(CountVectorizer(), MultinomialNB())
    if name == "logreg":
        # C=10: the default C=1 is too strict for such a small dataset
        return make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2)),
            LogisticRegression(C=10, max_iter=2000),
        )
    if name == "linear_svc":
        # LinearSVC has no probabilities, so wrap it in a calibrator.
        return make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2)),
            CalibratedClassifierCV(LinearSVC(C=1), cv=3, method="sigmoid"),
        )
    raise ValueError(f"Unknown model name: {name}")


# ---------------------------------------------------------------------
# Cross-validation helpers
# ---------------------------------------------------------------------
def cv_predict(name: str, masked: List[str], labels: List[str],
               folds: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """Out-of-fold predictions: every sentence is predicted by a model
    that never saw it. Returns (predicted labels, confidences)."""
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    proba = cross_val_predict(build_model(name), np.array(masked), np.array(labels),
                              cv=skf, method="predict_proba")
    classes = np.unique(labels)
    best = proba.argmax(axis=1)
    return classes[best], proba.max(axis=1)


def apply_decision(pred: np.ndarray, conf: np.ndarray, clean: List[str],
                   threshold: float, use_rules: bool) -> np.ndarray:
    """Same decision steps as IntentClassifier.predict, for many sentences."""
    final = np.where(conf < threshold, UNKNOWN, pred).astype(object)
    if use_rules:
        for i, sentence in enumerate(clean):
            rule = match_rule(sentence)
            if rule:
                final[i] = rule
    return final


def compare_models(folds: Optional[int] = None, repeats: Optional[int] = None,
                   path: Optional[str] = None) -> Dict[str, dict]:
    """
    Stratified k-fold cross-validation, repeated with different shuffles.
    Compares the plain model prediction (no threshold, no rules) of each
    model. Returns {model_name: {"acc_mean", "acc_std", "f1_mean", "runs"}}.
    """
    folds = folds or config.CV_FOLDS
    repeats = repeats or config.CV_REPEATS
    clean, masked, labels = load_training_data(path)
    y = np.array(labels)

    results: Dict[str, dict] = {}
    for name in MODEL_NAMES:
        accs, f1s, runs = [], [], []
        for r in range(repeats):
            pred, conf = cv_predict(name, masked, labels, folds, config.RANDOM_SEED + r)
            accs.append(float((pred == y).mean()))
            f1s.append(float(f1_score(y, pred, average="macro")))
            runs.append((pred, conf))
        results[name] = {
            "acc_mean": float(np.mean(accs)),
            "acc_std": float(np.std(accs)),
            "f1_mean": float(np.mean(f1s)),
            "runs": runs,
        }
    return results


def tune_threshold(runs: list, clean: List[str], labels: List[str],
                   use_rules: bool = True,
                   tolerance: float = 0.005) -> Tuple[float, float, List[Tuple[float, float]]]:
    """
    Tries thresholds 0.00 .. 0.95 on the cross-validated predictions and
    returns (chosen_threshold, accuracy_there, curve).
    Below the threshold the answer becomes "unknown", which is right for
    sentences whose true label is "unknown" and wrong for the others.

    Why not simply the top accuracy? Accuracy is almost flat for small
    thresholds, so the top point is meaningless (it could be 0.04, which
    rejects nothing). A wrong ACTION ("delete my files" -> exit) is worse
    than "please say that again", so we take the HIGHEST threshold that
    loses at most `tolerance` (0.5 points) of accuracy.
    """
    y = np.array(labels)
    curve = []
    for thr in np.arange(0.0, 0.96, 0.01):
        accs = [float((apply_decision(p, c, clean, thr, use_rules) == y).mean())
                for p, c in runs]
        curve.append((round(float(thr), 2), float(np.mean(accs))))
    best_acc = max(a for _, a in curve)
    ok = [(t, a) for t, a in curve if a >= best_acc - tolerance]
    best_thr, acc_there = ok[-1]
    return best_thr, acc_there, curve


# ---------------------------------------------------------------------
# The classifier used by the assistant
# ---------------------------------------------------------------------
class IntentClassifier:
    def __init__(self, model_name: Optional[str] = None,
                 threshold: Optional[float] = None,
                 data_path: Optional[str] = None):
        self.model_name = model_name or config.MODEL_NAME
        self.threshold = config.CONFIDENCE_THRESHOLD if threshold is None else threshold
        self.data_path = data_path
        self.model: Optional[Pipeline] = None
        self.train()

    def train(self) -> None:
        _, masked, labels = load_training_data(self.data_path)
        self.model = build_model(self.model_name)
        self.model.fit(np.array(masked), np.array(labels))
        log.info("Intent model trained: %s on %d sentences, threshold %.2f",
                 self.model_name, len(labels), self.threshold)

    def predict(self, text: str) -> Tuple[str, float]:
        """Returns (intent, confidence). Intent is 'unknown' when the model
        is not sure enough or when it thinks the sentence is not a command."""
        clean = clean_text(text or "")
        if not clean:
            return UNKNOWN, 0.0

        rule_intent = match_rule(clean)
        if rule_intent:
            return rule_intent, 1.0

        probs = self.model.predict_proba([mask_numbers(clean)])[0]
        best = int(probs.argmax())
        intent = str(self.model.classes_[best])
        confidence = float(probs[best])

        if confidence < self.threshold or intent == UNKNOWN:
            return UNKNOWN, confidence
        return intent, confidence

    def train_and_report(self) -> float:
        """Console report for your project write-up: cross-validated numbers
        for all three models, then the chosen model with rules and threshold.
        Returns the final cross-validated accuracy (rules + threshold)."""
        clean, masked, labels = load_training_data(self.data_path)
        print(f"[IntentClassifier] {len(labels)} sentences, {len(set(labels))} intents, "
              f"{config.CV_FOLDS}-fold stratified CV x {config.CV_REPEATS} repeats")
        print(f"{'Model':64s} {'Accuracy':>16s} {'Macro-F1':>9s}")

        results = compare_models(path=self.data_path)
        for name in MODEL_NAMES:
            r = results[name]
            mark = "  <- chosen" if name == self.model_name else ""
            print(f"{MODEL_DESCRIPTIONS[name]:64s} "
                  f"{r['acc_mean']:7.1%} +/- {r['acc_std']:4.1%} {r['f1_mean']:9.3f}{mark}")

        runs = results[self.model_name]["runs"]
        y = np.array(labels)
        thr, _, _ = tune_threshold(runs, clean, labels, use_rules=True)

        def acc_at(t: float, rules: bool) -> float:
            return float(np.mean([(apply_decision(p, c, clean, t, rules) == y).mean()
                                  for p, c in runs]))

        print(f"\nChosen model: {self.model_name}")
        print(f"  model only, no threshold:        {acc_at(0.0, False):.1%}")
        print(f"  model + threshold {thr:.2f}:           {acc_at(thr, False):.1%}")
        final = acc_at(thr, True)
        print(f"  model + threshold {thr:.2f} + rules:   {final:.1%}")
        pred, conf = runs[0]
        final_labels = apply_decision(pred, conf, clean, thr, True)
        is_unknown = y == UNKNOWN
        wrong_action = float(np.mean(final_labels[is_unknown] != UNKNOWN))
        rejected = float(np.mean(final_labels[~is_unknown] == UNKNOWN))
        print(f"  'unknown' sentences that wrongly trigger an action: {wrong_action:.1%}")
        print(f"  real commands that are wrongly rejected:            {rejected:.1%}")
        print(f"  best threshold found: {thr:.2f} "
              f"(config.CONFIDENCE_THRESHOLD is {config.CONFIDENCE_THRESHOLD:.2f})")
        if abs(thr - config.CONFIDENCE_THRESHOLD) > 0.03:
            print("  NOTE: update CONFIDENCE_THRESHOLD in config.py to the best value above.")
        return final


if __name__ == "__main__":
    # python intent_classifier.py  -> prints the accuracy report
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    IntentClassifier().train_and_report()
