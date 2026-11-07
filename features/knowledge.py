"""
features/knowledge.py
Wikipedia-based "who is / tell me about" answers, with a small local
fallback knowledge base for when there's no internet connection.

Install: pip install wikipedia
"""

import json
import logging
import os
import re

import wikipedia

import config

log = logging.getLogger(__name__)

FALLBACK_PATH = os.path.join(config.DATA_DIR, "fallback_knowledge.json")

# Question words at the start of a query. Longest first, so "who was" is not cut as "who".
_PREFIX = re.compile(
    r"^(?:who is|who was|who are|what is|what was|what are|what's|who's|tell me about|"
    r"tell me more about|explain|define|describe)(?:\s+|$)", re.IGNORECASE)


def extract_topic(query: str) -> str:
    """'who was isaac newton' -> 'isaac newton'. Only the START is stripped, so a topic
    that contains the words (for example 'the who is a band') keeps them."""
    return _PREFIX.sub("", query.strip(), count=1).strip(" ?.!")


class KnowledgeFeature:
    def __init__(self, voice):
        self.voice = voice
        self._ensure_fallback_file()

    def _ensure_fallback_file(self):
        if not os.path.exists(FALLBACK_PATH):
            starter = {
                "python": "Python is a popular high-level programming language known for readable syntax.",
                "artificial intelligence": "Artificial intelligence is the field of building systems that can perform tasks that normally require human intelligence.",
            }
            with open(FALLBACK_PATH, "w", encoding="utf-8") as f:
                json.dump(starter, f, indent=4, ensure_ascii=False)

    def answer(self, query):
        topic = extract_topic(query)
        if not topic:
            self.voice.speak("Who or what would you like to know about?")
            return

        try:
            result = wikipedia.summary(topic, sentences=2)
            self.voice.speak(result)
        except wikipedia.exceptions.DisambiguationError:
            self.voice.speak("There are multiple results. Please be more specific.")
        except wikipedia.exceptions.PageError:
            self._try_fallback(topic)
        except Exception:
            # Likely no internet connection
            log.info("Wikipedia lookup failed, using the local fallback", exc_info=True)
            self._try_fallback(topic)

    def _try_fallback(self, topic):
        try:
            with open(FALLBACK_PATH, "r", encoding="utf-8") as f:
                local_kb = json.load(f)
        except (OSError, ValueError):
            log.exception("Could not read the fallback knowledge file")
            local_kb = {}
        answer = local_kb.get(topic.lower())
        if answer:
            self.voice.speak(f"(offline) {answer}")
        else:
            self.voice.speak("Sorry, I couldn't find information about that, and I'm offline.")
