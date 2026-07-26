"""
speech_engine.py
Text-to-speech. Uses pyttsx3 instead of win32com/SAPI so it also works
on Mac/Linux, not just Windows.

Note: pyttsx3's SAPI5 driver on Windows has a known bug where reusing
one engine instance across multiple speak() calls causes it to go
silent after the first sentence. The fix is to create a fresh engine
for each call instead of reusing one — that's what we do here.

Install: pip install pyttsx3
"""

import pyttsx3


class SpeechEngine:
    def __init__(self, rate=175, volume=1.0, on_speak=None):
        self.rate = rate
        self.volume = volume
        self.on_speak = on_speak  # optional callback(text) -- used by the GUI

    def speak(self, text):
        print(f"J: {text}")
        if self.on_speak:
            self.on_speak(text)
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
