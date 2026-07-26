"""
features/knowledge.py
Wikipedia-based "who is / tell me about" answers, with a small local
fallback knowledge base for when there's no internet connection.

Install: pip install wikipedia
"""

import json
import os

import wikipedia

import config

FALLBACK_PATH = os.path.join(config.DATA_DIR, "fallback_knowledge.json")


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
            with open(FALLBACK_PATH, "w") as f:
                json.dump(starter, f, indent=4)

    def answer(self, query):
        topic = query.replace("who is", "").replace("tell me about", "").strip()
        if not topic:
            self.voice.speak("Who or what would you like to know about?")
            return

        try:
            result = wikipedia.summary(topic, sentences=2)
            self.voice.speak(result)
            print(result)
        except wikipedia.exceptions.DisambiguationError:
            self.voice.speak("There are multiple results. Please be more specific.")
        except wikipedia.exceptions.PageError:
            self._try_fallback(topic)
        except Exception:
            # Likely no internet connection
            self._try_fallback(topic)

    def _try_fallback(self, topic):
        with open(FALLBACK_PATH, "r") as f:
            local_kb = json.load(f)
        answer = local_kb.get(topic.lower())
        if answer:
            self.voice.speak(f"(offline) {answer}")
        else:
            self.voice.speak("Sorry, I couldn't find information about that, and I'm offline.")
