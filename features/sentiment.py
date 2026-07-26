"""
features/sentiment.py
Detects whether what the user said sounds frustrated/negative, neutral,
or positive, so Raju can respond with a bit more patience when things
aren't going well.

Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) -- a
lexicon-based scorer, not a neural model or API. It works by looking
up words against a pre-built dictionary of sentiment scores (bundled
with the package) and combining them with simple rules (negation,
intensifiers like "very", punctuation, etc). Everything runs locally,
instantly, no internet needed after installation.

Install: pip install vaderSentiment
"""

import config


class SentimentFeature:
    def __init__(self):
        self._analyzer = None
        self._load_analyzer()

    def _load_analyzer(self):
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._analyzer = SentimentIntensityAnalyzer()
        except ImportError:
            print("[SentimentFeature] vaderSentiment not installed -- "
                  "sentiment-aware responses disabled. "
                  "Run: pip install vaderSentiment")
            self._analyzer = None

    def analyze(self, text):
        """
        Returns a dict: {"compound": float in [-1, 1], "label": str}.
        label is one of "negative", "neutral", "positive".
        If vaderSentiment isn't installed, always returns neutral --
        the rest of the assistant behaves exactly as if this feature
        didn't exist.
        """
        if not self._analyzer or not text:
            return {"compound": 0.0, "label": "neutral"}

        scores = self._analyzer.polarity_scores(text)
        compound = scores["compound"]

        if compound <= config.SENTIMENT_NEGATIVE_THRESHOLD:
            label = "negative"
        elif compound >= config.SENTIMENT_POSITIVE_THRESHOLD:
            label = "positive"
        else:
            label = "neutral"

        return {"compound": compound, "label": label}
