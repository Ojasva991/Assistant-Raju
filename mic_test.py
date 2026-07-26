"""
mic_test.py
Standalone diagnostic — bypasses J entirely to isolate whether the
problem is your microphone/Windows setup, or something in the
assistant's code.

Run:
    py mic_test.py
"""

import speech_recognition as sr

# 1. List available microphones
print("=== Available microphones ===")
mics = sr.Microphone.list_microphone_names()
if not mics:
    print("NO MICROPHONES DETECTED AT ALL. This is a Windows/driver issue,")
    print("not a Python issue. Check Windows Sound settings.")
else:
    for i, name in enumerate(mics):
        print(f"  [{i}] {name}")

# 2. Try listening on the DEFAULT microphone
print("\n=== Testing default microphone ===")
recognizer = sr.Recognizer()

try:
    with sr.Microphone() as source:
        print("Adjusting for ambient noise... (stay quiet for 1 second)")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print(f"Energy threshold set to: {recognizer.energy_threshold}")
        print("Now SAY SOMETHING clearly within 5 seconds...")
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
    print("Audio captured! Sending to Google for recognition...")
    text = recognizer.recognize_google(audio, language="en-in")
    print(f"\nSUCCESS. You said: {text}")
except sr.WaitTimeoutError:
    print("\nFAILED: No speech detected in time. The mic isn't picking up "
          "sound at all, or the energy threshold is too high.")
except sr.UnknownValueError:
    print("\nPARTIAL: Audio was captured (mic works!) but Google couldn't "
          "understand the words. Try speaking louder/clearer, or check "
          "your internet connection.")
except OSError as e:
    print(f"\nFAILED: Microphone access error: {e}")
    print("This usually means Windows microphone privacy permissions are "
          "blocking Python, or no default input device is set.")
except Exception as e:
    print(f"\nFAILED with unexpected error: {type(e).__name__}: {e}")
