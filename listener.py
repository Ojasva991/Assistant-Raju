"""
listener.py
Speech-to-text via the microphone, with a text-input fallback for
demos where the mic might not cooperate.

Install: pip install SpeechRecognition pyaudio
"""

import speech_recognition as sr

import config


class Listener:
    def __init__(self, use_microphone=True):
        self.recognizer = sr.Recognizer()
        self.use_microphone = use_microphone

    def listen(self):
        """Listen via mic. Falls back to typed input if mic fails or is disabled."""
        if not self.use_microphone:
            return input("You (typed): ").strip().lower()

        try:
            with sr.Microphone(device_index=config.MIC_DEVICE_INDEX) as source:
                print("Listening...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
            query = self.recognizer.recognize_google(audio, language="en-in")
            print("User:", query)
            return query.lower()
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except Exception as e:
            print(f"[Listener] Mic error, falling back to text input: {e}")
            return input("You (typed): ").strip().lower()
