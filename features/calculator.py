"""
features/calculator.py
Parses simple spoken math like "what is fifteen plus twenty" and computes it.

Install: pip install word2number
"""

import re
from word2number import w2n

# operator map, longest/most specific phrases checked first to avoid partial matches
OP_PATTERNS = [
    (r"divided by|divide", "/"),
    (r"multiplied by|multiply|times", "*"),
    (r"plus|add(?:ed)? to|add", "+"),
    (r"minus|subtract", "-"),
]


class CalculatorFeature:
    def __init__(self, voice):
        self.voice = voice

    def calculate(self, text):
        """text is the full recognized sentence, e.g. 'what is fifteen plus twenty'."""
        text = text.lower().replace("what is", "").replace("calculate", "").strip()

        operator = None
        for pattern, op in OP_PATTERNS:
            if re.search(pattern, text):
                operator = op
                text = re.sub(pattern, "|", text, count=1)
                break

        if operator is None:
            self.voice.speak("I couldn't find a math operation in that.")
            return

        parts = [p.strip() for p in text.split("|")]
        if len(parts) != 2:
            self.voice.speak("Sorry, I couldn't understand the numbers.")
            return

        try:
            num1 = self._to_number(parts[0])
            num2 = self._to_number(parts[1])
        except ValueError:
            self.voice.speak("Sorry, I couldn't understand the numbers.")
            return

        result = self._apply(num1, num2, operator)
        self.voice.speak(f"The answer is {result}")

    def _to_number(self, text):
        text = text.strip()
        if text.replace(".", "", 1).isdigit():
            return float(text)
        return w2n.word_to_num(text)

    def _apply(self, a, b, op):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                return "undefined, you can't divide by zero"
            return a / b
